"""MAG source inventory with date-specific hours and explicit travel proxies.

Observed: source name/location/type/local-clock text. Assumed: visits/day,
district centroids, demand, detour and travel speeds. This is not GTFS routing.
Blank schedule cells remain unknown; the default conservative scenario gives
them zero available hours and records that modelling policy.
"""
from __future__ import annotations

import copy
import csv
import datetime as dt
import math
import re
from pathlib import Path
from typing import Dict, List, Mapping, Tuple

from .schema import COOLING, DONATION, HYDRATION, RESPITE, Instance, Site

ROOT = Path(__file__).resolve().parents[2]
MAG_CSV = ROOT / "资料" / "02_降温网络" / "MAG" / "phoenix_2026_public_view_sites.csv"
DEMOGRAPHICS_CSV = (ROOT / "资料" / "11_补充与审查_2026-11-19" / "补充资料" /
                    "官方村界与人口" / "district_demographics_candidate_12.csv")
KIND_MAP = {"cooling center": COOLING, "hydration station": HYDRATION,
            "respite center": RESPITE, "donation site": DONATION}
SPEED = {"walk_min": 4.8, "transit_min": 15.0, "drive_min": 30.0}
DETOUR = 1.35
WAIT = 10.0
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
# Actual 2026 holiday dates. July 3 observance is not assumed from July 4 text.
HOLIDAYS_2026 = {"2026-05-25": "MemorialDay", "2026-06-19": "Juneteenth",
                 "2026-07-04": "IndependenceDay", "2026-09-07": "LaborDay",
                 "2026-10-12": "ColumbusDay"}


def _hav(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = p2 - p1, math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, max(0.0, x))))


def _clock(value) -> float | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*", value, re.I)
    if not match:
        return None
    hour, minute = int(match[1]), int(match[2] or 0)
    if not 1 <= hour <= 12 or not 0 <= minute < 60:
        return None
    return hour % 12 + (12 if match[3].upper() == "PM" else 0) + minute / 60


def _pair(open_value, close_value) -> dict:
    values = [str(v or "").strip() for v in (open_value, close_value)]
    is_closed = [v.lower() == "closed" for v in values]
    if any(is_closed):
        status = "closed_explicit" if all(c or not v for c, v in zip(is_closed, values)) else "unknown_conflicting_closed_and_clock"
        return {"status": status}
    if not any(values):
        return {"status": "unknown_blank_pair"}
    op, cl = _clock(open_value), _clock(close_value)
    if op is None or cl is None or op == cl:
        return {"status": "unknown_incomplete_unparsed_or_equal_pair"}
    return {"status": "open_clock_pair", "open_hour": op, "close_hour": cl}


def calendar_for_date(row: Mapping, date: str | dt.date,
                      holiday_overrides: Mapping[str, str] | None = None) -> dict:
    """Resolve posted dates and the chosen weekday without merging weekdays.

    A holiday override maps an ISO date to one of the five source holiday field
    names or 'regular'. Source range is checked first; Active=Yes never extends it.
    """
    date = dt.date.fromisoformat(date) if isinstance(date, str) else date
    result = {"date": date.isoformat(), "weekday": DAYS[date.weekday()]}
    try:
        lo = dt.date.fromisoformat(str(row.get("Start_Date")))
        hi = dt.date.fromisoformat(str(row.get("End_Date")))
    except ValueError:
        return {**result, "status": "unknown_missing_or_unparsed_source_date_range"}
    if not lo <= date <= hi:
        return {**result, "status": "outside_posted_source_date_range"}
    iso = date.isoformat()
    override = (holiday_overrides or {}).get(iso)
    if iso == "2026-07-03" and override is None:
        return {**result, "status": "unknown_holiday_observance"}
    holiday = override if override is not None else HOLIDAYS_2026.get(iso)
    if holiday and holiday != "regular":
        if holiday not in set(HOLIDAYS_2026.values()):
            raise ValueError("holiday override must name a source holiday field or 'regular'")
        raw = str(row.get(holiday) or "").strip()
        result["holiday_field"] = holiday
        if raw.lower() == "closed":
            return {**result, "status": "closed_explicit"}
        if raw.lower() != "regular hours":
            parts = re.split(r"\s*[-–—]\s*", raw)
            rule = _pair(*parts) if len(parts) == 2 else {"status": "unknown_holiday_hours"}
            return {**result, **rule}
    day = DAYS[date.weekday()]
    return {**result, **_pair(row.get(day + "Open"), row.get(day + "Close"))}


def site_on_day(site: Site, day: int) -> Site:
    """Return a shallow site view with the resolved operating window for day.

    Non-calendar sites keep their original schedule. A calendar site never
    silently reuses day zero when day is absent.
    """
    calendar = (site.extra or {}).get("calendar_by_day")
    if calendar is None:
        return site
    key = str(day)
    if key not in calendar:
        raise ValueError(f"calendar missing {site.id}/day{day}")
    rule = calendar[key]
    view = copy.copy(site)
    view.open_hour = float(rule.get("open_hour", 0.0))
    view.close_hour = float(rule.get("close_hour", 0.0))
    view.extra = {**(site.extra or {}), "selected_calendar_rule": rule}
    return view


def load_mag_sites(path: Path | None = None, *, start_date: str = "2026-07-20",
                   horizon_days: int = 7, unknown_hours: str = "closed",
                   holiday_overrides: Mapping[str, str] | None = None,
                   assumed_cooling_capacity: int = 50) -> List[Site]:
    if horizon_days < 1:
        raise ValueError("horizon_days must be positive")
    if unknown_hours not in ("closed", "error"):
        raise ValueError("unknown_hours must be 'closed' or 'error'")
    if assumed_cooling_capacity < 0:
        raise ValueError("assumed_cooling_capacity must be nonnegative")
    start = dt.date.fromisoformat(start_date)
    source = Path(path) if path else MAG_CSV
    with source.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        kind = KIND_MAP.get((row.get("HeatRelief_Type") or "").strip().lower())
        if kind is None:
            continue
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (TypeError, ValueError, KeyError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("MAG coordinate out of range")
        calendar = {}
        # Keep adjacent civil dates so a 09:00-to-next-09:00 service day can
        # intersect overnight carry-in and next-morning source windows exactly.
        for day in range(-1, horizon_days + 1):
            rule = calendar_for_date(row, start + dt.timedelta(days=day), holiday_overrides)
            if not rule["status"].startswith("open_"):
                unknown = rule["status"] != "closed_explicit"
                if unknown and unknown_hours == "error":
                    raise ValueError(f"Unknown MAG hours: {row['OBJECTID']} {rule}")
                rule.update(open_hour=0.0, close_hour=0.0,
                            availability_policy="conservative_zero_assumed" if unknown else "explicit_source_closed")
            calendar[str(day)] = rule
        first = calendar["0"]
        out.append(Site(
            id=f"MAG{str(row['OBJECTID']).zfill(4)}", name=(row.get("Location") or "").strip(),
            kind=kind, district_id="", lat=lat, lon=lon,
            capacity=assumed_cooling_capacity if kind in (COOLING, RESPITE) else 0,
            open_hour=first["open_hour"], close_hour=first["close_hour"], source="MAG_REAL",
            extra={"organization": (row.get("Organization") or "").strip(),
                   "address": (row.get("Address") or "").strip(),
                   "snapshot": row.get("source_snapshot_date"), "calendar_by_day": calendar,
                   "calendar_start_date": start_date, "unknown_hours_policy": unknown_hours,
                   "calendar_horizon_days": horizon_days,
                   "source_date_range": [row.get("Start_Date"), row.get("End_Date")],
                   "source_capacity": "ASSUME_NOT_SUPPLIED_BY_MAG",
                   "capacity_is_explicit": True,
                   "source_hours": "OBS_SOURCE_TEXT_DATE_RESOLVED",
                   "source_location": "OBS_MAG_EPSG4326", "source_kind": "OBS_MAG"}))
    return out


def build_real_instance(access_mode: str = "walk_min", scenario: str = "base",
                        horizon_days: int = 7, *, start_date: str = "2026-07-20",
                        unknown_hours: str = "closed", assumed_cooling_capacity: int = 50,
                        holiday_overrides: Mapping[str, str] | None = None) -> Instance:
    from .loaders import load_instance
    if access_mode not in SPEED:
        raise ValueError(f"access_mode must be one of {tuple(SPEED)}")
    base = load_instance(access_mode=access_mode, scenario=scenario, horizon_days=horizon_days)
    fixed = load_mag_sites(start_date=start_date, horizon_days=horizon_days,
                           unknown_hours=unknown_hours, assumed_cooling_capacity=assumed_cooling_capacity,
                           holiday_overrides=holiday_overrides)
    for site in fixed:
        site.district_id = min(base.districts, key=lambda d: _hav(d.lat, d.lon, site.lat, site.lon)).id
    sites = fixed + base.candidate_sites()
    access: Dict[Tuple[str, str], float] = {}
    for district in base.districts:
        for site in sites:
            km = _hav(district.lat, district.lon, site.lat, site.lon) * DETOUR
            walk = km / SPEED["walk_min"] * 60
            if access_mode == "transit_min":
                minutes = min(walk, km / SPEED["transit_min"] * 60 + WAIT)
            elif access_mode == "walk_min":
                minutes = walk
            else:
                minutes = km / SPEED["drive_min"] * 60
            access[(district.id, site.id)] = round(minutes, 1)
    return Instance(
        districts=base.districts, sites=sites, access=access, demand=dict(base.demand),
        horizon_days=horizon_days,
        meta={**base.meta, "network": "MAG_REAL", "n_fixed": len(fixed),
              "n_candidates": len(base.candidate_sites()), "calendar_start_date": start_date,
              "unknown_hours_policy": unknown_hours,
              "access_method": "haversine_detour_speed_proxy_with_direct_walk_option",
              "access_schedule_routing": False,
              "access_parameters": {"detour": DETOUR, "speed_kmh": SPEED, "wait_minutes": WAIT},
              "input_paths": [str(MAG_CSV)],
              "note": "MAG source inventory and dated hours; capacities/demand/centroids/travel remain conditional assumptions"})


def apply_official_demographics(inst: Instance, path: Path | None = None) -> Instance:
    """Explicit ACS2018–22 population/age overlay; no invented vehicle fraction.

    Demand is deliberately unchanged. Caller must choose and document a demand
    recalculation/calibration before using this as a different demand scenario.
    Income-bin interpolation remains a derived proxy and is not auto-applied.
    """
    source = Path(path) if path else DEMOGRAPHICS_CSV
    with source.open(encoding="utf-8-sig", newline="") as f:
        rows = {r["district_id"]: r for r in csv.DictReader(f)}
    if set(rows) != {d.id for d in inst.districts}:
        raise ValueError("official demographic overlay must match all district IDs exactly")
    for district in inst.districts:
        row = rows[district.id]
        district.population = int(row["population"])
        district.pct_65plus = float(row["pct_65plus"])
        district.extra = {**(district.extra or {}),
                          "population_source": "HSD2024_ACS2018_2022_DERIVED_VILLAGE_COUNTS",
                          "age_source": "HSD2024_ACS2018_2022_DERIVED_VILLAGE_COUNTS",
                          "mapping_status": row["mapping_status"],
                          "vehicle_fraction_source": "UNCHANGED_MODEL_INPUT_NOT_IN_THIS_TABLE"}
    inst.meta["demographics_overlay"] = {"path": str(source), "acs_period": "2018-2022",
        "applied_fields": ["population", "pct_65plus"], "demand_rebuilt": False,
        "required_next_step": "choose explicit demand recalculation; remaining vulnerability inputs are assumptions"}
    return inst
