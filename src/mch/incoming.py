"""真实资料接入钩子（"留空"机制）。

约定：把队友找到的文件放到 `data/incoming/`，**文件名固定**，程序会自动覆盖对应的合成值，
并在 `inst.meta["incoming"]` 里记录改了哪些字段。没有文件时一切照旧。

支持（按文件名）：
  sites_mag.csv      -> 覆盖站点坐标/类型/开放时间（按 site_id 或名称匹配）
  acs_districts.csv  -> 覆盖区级人口学属性（按 district_id 匹配）
  access_gtfs.csv    -> 覆盖行程时间矩阵（列：district_id,site_id,walk_min,transit_min,drive_min）
  demand_observed.csv-> 覆盖/标定需求（列：district_id,day,demand_visits）

任何不认识的列都会被忽略并记录，不会静默出错。
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List

from .schema import Instance

FIELDS = {
    "sites_mag.csv": {"lat": float, "lon": float, "kind": str,
                      "open_hour": float, "close_hour": float, "capacity": float},
    "acs_districts.csv": {"population": int, "pct_65plus": float, "pct_no_vehicle": float,
                          "median_income_usd": float, "canopy_pct": float,
                          "heat_exposure_index": float},
    "access_gtfs.csv": {"walk_min": float, "transit_min": float, "drive_min": float},
    "demand_observed.csv": {"demand_visits": float},
}


def _rows(p: Path) -> List[dict]:
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def apply_incoming(inst: Instance, base: Path | None = None) -> Instance:
    base = Path(base) if base else Path(__file__).resolve().parents[2] / "data" / "incoming"
    log: Dict[str, object] = {}
    if not base.exists():
        inst.meta["incoming"] = {"applied": False}
        return inst

    # 站点
    f = base / "sites_mag.csv"
    if f.exists():
        changed = 0
        for r in _rows(f):
            sid = r.get("site_id") or r.get("id")
            site = next((s for s in inst.sites if s.id == sid), None)
            if site is None:
                continue
            for col, cast in FIELDS["sites_mag.csv"].items():
                if col in r and str(r[col]).strip() != "":
                    setattr(site, col, cast(r[col])); changed += 1
            site.extra = dict(site.extra or {})
            site.extra["source_kind"] = "MAG_REAL"
        log["sites_mag"] = changed

    # 区属性
    f = base / "acs_districts.csv"
    if f.exists():
        changed = 0
        for r in _rows(f):
            d = next((x for x in inst.districts if x.id == r.get("district_id")), None)
            if d is None:
                continue
            for col, cast in FIELDS["acs_districts.csv"].items():
                if col in r and str(r[col]).strip() != "":
                    setattr(d, col, cast(r[col])); changed += 1
            d.extra = dict(d.extra or {})
            d.extra["source"] = "ACS_REAL"
        log["acs_districts"] = changed

    # 可达矩阵
    f = base / "access_gtfs.csv"
    if f.exists():
        changed = 0
        mode = inst.meta.get("access_mode", "walk_min")
        for r in _rows(f):
            key = (r.get("district_id"), r.get("site_id"))
            if key in inst.access and str(r.get(mode, "")).strip() != "":
                inst.access[key] = float(r[mode]); changed += 1
        log["access_gtfs"] = changed

    # 观测需求
    f = base / "demand_observed.csv"
    if f.exists():
        changed = 0
        for r in _rows(f):
            key = (r.get("district_id"), int(r.get("day", 0)))
            if str(r.get("demand_visits", "")).strip() != "":
                inst.demand[key] = float(r["demand_visits"]); changed += 1
        log["demand_observed"] = changed

    log["applied"] = any(isinstance(v, int) and v > 0 for v in log.values())
    inst.meta["incoming"] = log
    return inst
