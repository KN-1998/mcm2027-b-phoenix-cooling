"""从 data/processed 的 CSV 载入 Instance（EXT-04 的真实数据入口）。

只依赖四个 CSV 的列名；换成真实 ACS/GTFS 数据时，保持列名不变即可。
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Tuple

from .schema import Instance, District, Site

ACCESS_MODES = ("walk_min", "transit_min", "drive_min")


def _rows(path: Path) -> List[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_instance(data_dir: str | Path | None = None, scenario: str = "base",
                  access_mode: str = "walk_min", horizon_days: int = 7) -> Instance:
    base = Path(data_dir) if data_dir else Path(__file__).resolve().parents[2] / "data" / "processed"
    if access_mode not in ACCESS_MODES:
        raise ValueError(f"access_mode 必须是 {ACCESS_MODES}")

    districts = [
        District(id=r["district_id"], name=r["district_name"], population=int(r["population"]),
                 pct_65plus=float(r["pct_65plus"]), pct_no_vehicle=float(r["pct_no_vehicle"]),
                 median_income=float(r["median_income_usd"]), canopy_pct=float(r["canopy_pct"]),
                 heat_exposure_index=float(r["heat_exposure_index"]),
                 lat=float(r["lat"]), lon=float(r["lon"]),
                 extra={"vulnerability": float(r["vulnerability"]),
                        "villages": r["villages_mapped"]})
        for r in _rows(base / "districts.csv")
    ]
    sites = [
        Site(id=r["site_id"], name=r["site_name"], kind=r["kind"], district_id=r["district_id"],
             lat=float(r["lat"]), lon=float(r["lon"]),
             capacity=int(float(r["capacity_visits_per_day"])),
             open_hour=float(r["open_hour"]), close_hour=float(r["close_hour"]),
             source=r.get("source", "ASSUME"))
        for r in _rows(base / "sites.csv")
    ]
    access: Dict[Tuple[str, str], float] = {
        (r["district_id"], r["site_id"]): float(r[access_mode]) for r in _rows(base / "access.csv")
    }
    demand: Dict[Tuple[str, int], float] = {
        (r["district_id"], int(r["day"])): float(r["demand_visits"])
        for r in _rows(base / "demand.csv") if r["scenario"] == scenario
    }
    return Instance(districts=districts, sites=sites, access=access, demand=demand,
                    horizon_days=horizon_days,
                    meta={"loaded_from": str(base), "scenario": scenario,
                          "access_mode": access_mode,
                          "note": "12 districts / 8 candidates are CONTEST fictions"})
