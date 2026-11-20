"""Explicit input overlays; observations are applied after requested derivations.

Changing an operating capacity never changes demand. Coordinate changes require
an independently rebuilt access table; this module does not invent GTFS times.
"""
from __future__ import annotations

import csv
import copy
import math
from pathlib import Path
from typing import Dict, List

from .schema import Instance

DISTRICT_MAP = {
    "population": "population", "pct_65plus": "pct_65plus",
    "pct_no_vehicle": "pct_no_vehicle", "median_income_usd": "median_income",
    "median_income": "median_income", "canopy_pct": "canopy_pct",
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


def _present(value) -> bool:
    return value is not None and str(value).strip() != ""


def _number(value, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def apply_incoming(inst: Instance, base: Path | None = None,
                   rebuild_derived: bool = False,
                   allow_stale_access: bool = False) -> Instance:
    base = Path(base) if base else Path(__file__).resolve().parents[2] / "data" / "incoming"
    log: Dict[str, object] = {"files": [], "changed": {}, "unmatched": {},
                              "ignored_columns": {}, "rebuild_needed": [], "applied": False}
    if not base.exists():
        inst.meta["incoming"] = log
        return inst
    demand_dirty = set()
    coordinate_dirty = set()
    old_districts = {d.id: copy.copy(d) for d in inst.districts}
    old_demand = dict(inst.demand)
    protected_observations = {tuple(cell) for cell in
        inst.meta.get("incoming", {}).get("observed_cells_applied_last", [])}

    f = base / "sites_mag.csv"
    if f.exists() and (rows := _rows(f)):
        changed = 0
        unmatched, ignored = [], set()
        by_id = {s.id: s for s in inst.sites}
        for row in rows:
            sid = (row.get("site_id") or row.get("id") or "").strip()
            site = by_id.get(sid)
            if site is None:
                unmatched.append(sid)
                continue  # New sites require an explicit site + access constructor.
            for col, value in row.items():
                if col in ("site_id", "id", "name", "district_id") or not _present(value):
                    continue
                if col not in SITE_MAP:
                    ignored.add(col)
                    continue
                attr, cast = SITE_MAP[col]
                numeric = None if cast is str else _number(value, f"{sid}/{col}")
                if attr == "capacity" and numeric != int(numeric):
                    raise ValueError(f"{sid}/capacity must be an integer number of visits/day")
                converted = cast(value) if cast is str else cast(numeric)
                if attr == "capacity" and converted < 0:
                    raise ValueError(f"{sid}/capacity must be nonnegative")
                if attr == "lat" and not -90 <= converted <= 90:
                    raise ValueError(f"{sid}/lat out of range")
                if attr == "lon" and not -180 <= converted <= 180:
                    raise ValueError(f"{sid}/lon out of range")
                if attr in ("open_hour", "close_hour") and not 0 <= converted <= 24:
                    raise ValueError(f"{sid}/{attr} out of range")
                if getattr(site, attr) != converted:
                    setattr(site, attr, converted)
                    changed += 1
                    if attr in ("lat", "lon"):
                        coordinate_dirty.add(sid)
            site.extra = dict(site.extra or {})
            site.extra["incoming_fields"] = [c for c in SITE_MAP if _present(row.get(c))]
            if _present(row.get("capacity")):
                site.extra["capacity_is_explicit"] = True
        log["files"].append(f.name)
        log["changed"]["sites"] = changed
        if unmatched:
            log["unmatched"]["sites"] = unmatched
        if ignored:
            log["ignored_columns"]["sites"] = sorted(ignored)

    f = base / "acs_districts.csv"
    if f.exists() and (rows := _rows(f)):
        changed = 0
        unmatched, ignored = [], set()
        by_id = {d.id: d for d in inst.districts}
        for row in rows:
            district = by_id.get(row.get("district_id"))
            if district is None:
                unmatched.append(row.get("district_id"))
                continue
            for col, value in row.items():
                if col == "district_id" or not _present(value):
                    continue
                attr = DISTRICT_MAP.get(col)
                if attr is None:
                    ignored.add(col)
                    continue
                numeric = _number(value, f"{district.id}/{col}")
                if attr == "population" and (numeric < 0 or int(numeric) != numeric):
                    raise ValueError("population must be a nonnegative integer")
                if attr == "median_income" and numeric < 0:
                    raise ValueError("median income must be nonnegative")
                if attr in ("pct_65plus", "pct_no_vehicle", "canopy_pct", "heat_exposure_index") and not 0 <= numeric <= 1:
                    raise ValueError(f"{district.id}/{col} must be in [0,1]")
                converted = int(numeric) if attr == "population" else numeric
                if getattr(district, attr) != converted:
                    setattr(district, attr, converted)
                    changed += 1
                    # Canopy does not enter district_day_demand directly.
                    if attr != "canopy_pct":
                        demand_dirty.add(district.id)
            district.extra = dict(district.extra or {})
            district.extra["incoming_fields"] = [c for c in DISTRICT_MAP if _present(row.get(c))]
        log["files"].append(f.name)
        log["changed"]["districts"] = changed
        if unmatched:
            log["unmatched"]["districts"] = unmatched
        if ignored:
            log["ignored_columns"]["districts"] = sorted(ignored)

    # Preserve the existing cell's scenario/calibration scale: D_new =
    # D_old * f(new attributes) / f(old attributes). Resetting to RATE_BASE
    # would undo the processed scenario scale (~505 -> ~4,600 visits/day).
    # Existing observed cells remain observations, not model-derived targets.
    if rebuild_derived and demand_dirty:
        from .demand import district_day_demand
        scales = {}
        explicit_scale = inst.meta.get("demand_scale")
        if explicit_scale is not None:
            explicit_scale = _number(explicit_scale, "demand_scale")
            if explicit_scale < 0:
                raise ValueError("demand_scale must be nonnegative")
        for district in inst.districts:
            if district.id in demand_dirty:
                for day in range(inst.horizon_days):
                    key = (district.id, day)
                    if key in protected_observations:
                        continue
                    old_model = district_day_demand(old_districts[district.id], day)
                    new_model = district_day_demand(district, day)
                    if key in old_demand and old_model > 0:
                        scale = old_demand[key] / old_model
                    elif key in old_demand and old_demand[key] == 0 and new_model == 0:
                        scale = 0.0
                    elif explicit_scale is not None:
                        scale = explicit_scale
                    else:
                        raise ValueError(f"Cannot identify prior demand scale for {key}; provide explicit demand_scale")
                    inst.demand[key] = scale * new_model
                    scales[f"{district.id}/{day}"] = scale
        log["rebuilt"] = True
        log["rebuilt_districts"] = sorted(demand_dirty)
        log["rebuild_method"] = "preserve_original_cell_scale_times_attribute_model_ratio"
        log["rebuild_cell_scales"] = scales
    elif demand_dirty:
        log["rebuild_needed"].append("demand(脆弱性变化后需显式重算需求)")

    f = base / "access_gtfs.csv"
    supplied_access = set()
    if f.exists() and (rows := _rows(f)):
        changed = 0
        unmatched = []
        mode = inst.meta.get("access_mode", "walk_min")
        d_ids, s_ids = {d.id for d in inst.districts}, {s.id for s in inst.sites}
        for row in rows:
            key = (row.get("district_id"), row.get("site_id"))
            if key[0] not in d_ids or key[1] not in s_ids:
                unmatched.append(f"{key[0]}/{key[1]}")
                continue
            if _present(row.get(mode)):
                value = _number(row[mode], f"access/{key}")
                if value < 0:
                    raise ValueError("access time must be nonnegative")
                inst.access[key] = value
                supplied_access.add(key)
                changed += 1
        log["files"].append(f.name)
        log["changed"]["access"] = changed
        if unmatched:
            log["unmatched"]["access"] = unmatched
    missing_coordinate_links = [f"{d.id}/{sid}" for sid in sorted(coordinate_dirty)
                                for d in inst.districts if (d.id, sid) not in supplied_access]
    if missing_coordinate_links:
        log["rebuild_needed"].append("access(坐标变化后需重建可达矩阵)")
        log["stale_access_links"] = missing_coordinate_links
        log["stale_access_explicitly_allowed"] = bool(allow_stale_access)
        if not allow_stale_access:
            inst.meta["incoming"] = log
            raise ValueError("Coordinate overlay leaves stale access links; supply a complete access table or explicitly set allow_stale_access=True for diagnostics")

    f = base / "demand_observed.csv"
    if f.exists() and (rows := _rows(f)):
        changed, unmatched = 0, []
        d_ids = {d.id for d in inst.districts}
        observed_cells = []
        for row in rows:
            district_id = row.get("district_id")
            day = int(row.get("day", 0))
            if district_id not in d_ids or not 0 <= day < inst.horizon_days:
                unmatched.append(f"{district_id}/{day}")
                continue
            if _present(row.get("demand_visits")):
                value = _number(row["demand_visits"], "demand_observed")
                if value < 0:
                    raise ValueError("observed demand must be nonnegative")
                inst.demand[(district_id, day)] = value
                observed_cells.append([district_id, day])
                changed += 1
        log["files"].append(f.name)
        log["changed"]["demand_observed"] = changed
        protected_observations.update(tuple(cell) for cell in observed_cells)
        log["observed_cells_applied_last"] = [list(cell) for cell in sorted(protected_observations)]
        if unmatched:
            log["unmatched"]["demand_observed"] = unmatched

    log["applied"] = any(log["changed"].values())
    if protected_observations:
        log["observed_cells_applied_last"] = [list(cell) for cell in sorted(protected_observations)]
    inst.meta["incoming"] = log
    return inst
