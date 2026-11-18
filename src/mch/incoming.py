"""真实资料接入钩子（"留空"机制）。

把文件放进 `data/incoming/`，**文件名固定**，程序自动覆盖对应字段，并在 `inst.meta["incoming"]`
里记录：覆盖字段数、未匹配行、忽略的列、是否需要重建派生量。

R6 修正：
  1. `median_income_usd` 现在映射到 `District.median_income`（此前 setattr 了模型不读的同名属性）；
  2. 新站点不再静默丢弃：记录到 `unmatched_sites`，并提示需要配套的可达矩阵；
  3. 未匹配的行/未知列全部列入日志；
  4. 改坐标/改容量后，派生量（需求、可达）**不会自动重建**，用 `rebuild_needed` 明确提示，
     并可用 `rebuild_derived=True` 触发重建（需求按 demand.district_day_demand 重算）。
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

from .schema import Instance

DISTRICT_MAP = {
    "population": "population",
    "pct_65plus": "pct_65plus",
    "pct_no_vehicle": "pct_no_vehicle",
    "median_income_usd": "median_income",      # 显式映射（R6）
    "median_income": "median_income",
    "canopy_pct": "canopy_pct",
    "heat_exposure_index": "heat_exposure_index",
}
SITE_MAP = {
    "lat": ("lat", float), "lon": ("lon", float), "kind": ("kind", str),
    "open_hour": ("open_hour", float), "close_hour": ("close_hour", float),
    "capacity": ("capacity", int),
}


def _rows(p: Path) -> List[dict]:
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def apply_incoming(inst: Instance, base: Path | None = None,
                   rebuild_derived: bool = False) -> Instance:
    base = Path(base) if base else Path(__file__).resolve().parents[2] / "data" / "incoming"
    log: Dict[str, object] = {"files": [], "changed": {}, "unmatched": {}, "ignored_columns": {},
                              "rebuild_needed": [], "applied": False}
    if not base.exists():
        inst.meta["incoming"] = log
        return inst

    # ---------- 站点 ----------
    f = base / "sites_mag.csv"
    if f.exists() and _rows(f):
        rows = _rows(f); changed = 0; unmatched, ignored = [], set()
        known_ids = {s.id for s in inst.sites}
        for r in rows:
            sid = (r.get("site_id") or r.get("id") or "").strip()
            site = next((s for s in inst.sites if s.id == sid), None)
            if site is None:
                unmatched.append(sid)          # R6：不再静默丢弃
                continue
            for col, val in r.items():
                if col in ("site_id", "id", "name", "district_id"):
                    continue
                if col not in SITE_MAP:
                    if str(val).strip(): ignored.add(col)
                    continue
                attr, cast = SITE_MAP[col]
                if str(val).strip() != "":
                    setattr(site, attr, cast(val)); changed += 1
            site.extra = dict(site.extra or {}); site.extra["source_kind"] = "MAG_REAL"
        log["files"].append(f.name); log["changed"]["sites"] = changed
        if unmatched: log["unmatched"]["sites"] = unmatched
        if ignored: log["ignored_columns"]["sites"] = sorted(ignored)
        if changed: log["rebuild_needed"].append("access(坐标变化后需重建可达矩阵)")

    # ---------- 区属性 ----------
    f = base / "acs_districts.csv"
    if f.exists() and _rows(f):
        rows = _rows(f); changed = 0; unmatched, ignored = [], set()
        for r in rows:
            d = next((x for x in inst.districts if x.id == r.get("district_id")), None)
            if d is None:
                unmatched.append(r.get("district_id")); continue
            for col, val in r.items():
                if col == "district_id" or str(val).strip() == "":
                    continue
                attr = DISTRICT_MAP.get(col)
                if attr is None:
                    ignored.add(col); continue
                cast = int if attr == "population" else float
                setattr(d, attr, cast(val)); changed += 1
            d.extra = dict(d.extra or {}); d.extra["source"] = "ACS_REAL"
        log["files"].append(f.name); log["changed"]["districts"] = changed
        if unmatched: log["unmatched"]["districts"] = unmatched
        if ignored: log["ignored_columns"]["districts"] = sorted(ignored)
        if changed: log["rebuild_needed"].append("demand(脆弱性变化后需重算需求)")

    # ---------- 可达矩阵 ----------
    f = base / "access_gtfs.csv"
    if f.exists() and _rows(f):
        changed = 0; unmatched = []
        mode = inst.meta.get("access_mode", "walk_min")
        for r in _rows(f):
            key = (r.get("district_id"), r.get("site_id"))
            if key not in inst.access:
                unmatched.append(f"{key[0]}/{key[1]}"); continue
            if str(r.get(mode, "")).strip() != "":
                inst.access[key] = float(r[mode]); changed += 1
        log["files"].append(f.name); log["changed"]["access"] = changed
        if unmatched: log["unmatched"]["access"] = unmatched[:20]

    # ---------- 观测需求 ----------
    f = base / "demand_observed.csv"
    if f.exists() and _rows(f):
        changed = 0
        for r in _rows(f):
            key = (r.get("district_id"), int(r.get("day", 0)))
            if str(r.get("demand_visits", "")).strip() != "":
                inst.demand[key] = float(r["demand_visits"]); changed += 1
        log["files"].append(f.name); log["changed"]["demand_observed"] = changed

    # ---------- 派生量重建 ----------
    if rebuild_derived and (log["changed"].get("districts") or log["changed"].get("sites")):
        from .demand import district_day_demand
        for d in inst.districts:
            for day in range(inst.horizon_days):
                inst.demand[(d.id, day)] = district_day_demand(d, day)
        log["rebuilt"] = True

    log["applied"] = bool(log["changed"])
    inst.meta["incoming"] = log
    return inst
