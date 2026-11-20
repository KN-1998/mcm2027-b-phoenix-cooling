"""Regression tests for semantic input failures found in the independent audit."""
from __future__ import annotations

import copy
import csv
from pathlib import Path

import pytest

from src.mch.incoming import apply_incoming
from src.mch.loaders import load_instance
from src.mch.realnet import (MAG_CSV, apply_official_demographics, build_real_instance,
                            calendar_for_date, load_mag_sites, site_on_day)


def _write(path, text):
    path.write_text(text, encoding="utf-8")


def test_capacity_only_overlay_never_rebuilds_demand(tmp_path):
    inst = load_instance()
    original = dict(inst.demand)
    sid = inst.sites[0].id
    _write(tmp_path / "sites_mag.csv", f"site_id,capacity\n{sid},177\n")
    apply_incoming(inst, tmp_path, rebuild_derived=True)
    assert inst.demand == original
    assert inst.meta["incoming"]["rebuild_needed"] == []
    assert not inst.meta["incoming"].get("rebuilt", False)


def test_observed_cells_win_after_requested_model_rebuild(tmp_path):
    from src.mch.demand import district_day_demand
    inst = load_instance()
    original = dict(inst.demand)
    inst.meta["demand_scale"] = 0.1
    original_district = copy.copy(inst.districts[0])
    _write(tmp_path / "acs_districts.csv", "district_id,median_income_usd\nD01,20000\n")
    _write(tmp_path / "demand_observed.csv", "district_id,day,demand_visits\nD01,0,123\n")
    apply_incoming(inst, tmp_path, rebuild_derived=True)
    assert inst.demand[("D01", 0)] == 123
    assert inst.demand[("D01", 1)] == pytest.approx(
        original[("D01", 1)] * district_day_demand(inst.districts[0], 1) /
        district_day_demand(original_district, 1))
    assert inst.demand[("D02", 0)] == original[("D02", 0)]
    assert inst.meta["incoming"]["rebuilt_districts"] == ["D01"]


def test_unknown_observation_does_not_create_unknown_district_or_day(tmp_path):
    inst = load_instance()
    original = dict(inst.demand)
    _write(tmp_path / "demand_observed.csv", "district_id,day,demand_visits\nZZ,0,5\nD01,99,5\n")
    apply_incoming(inst, tmp_path)
    assert inst.demand == original
    assert len(inst.meta["incoming"]["unmatched"]["demand_observed"]) == 2


@pytest.mark.parametrize("bad", ["nan", "inf", "-1"])
def test_invalid_observed_demand_rejected(tmp_path, bad):
    _write(tmp_path / "demand_observed.csv", f"district_id,day,demand_visits\nD01,0,{bad}\n")
    with pytest.raises(ValueError):
        apply_incoming(load_instance(), tmp_path)


def test_coordinate_overlay_marks_stale_access_without_inventing_times(tmp_path):
    inst = load_instance()
    old_access = dict(inst.access)
    sid = inst.sites[0].id
    _write(tmp_path / "sites_mag.csv", f"site_id,lat,lon\n{sid},33.1,-112.2\n")
    with pytest.raises(ValueError, match="stale access"):
        apply_incoming(copy.deepcopy(inst), tmp_path, rebuild_derived=True)
    apply_incoming(inst, tmp_path, rebuild_derived=True, allow_stale_access=True)
    assert inst.access == old_access
    assert len(inst.meta["incoming"]["stale_access_links"]) == len(inst.districts)


def test_slight_population_change_preserves_processed_demand_scale(tmp_path):
    inst = load_instance()
    old_population = inst.districts[0].population
    old_demand = dict(inst.demand)
    _write(tmp_path / "acs_districts.csv", f"district_id,population\nD01,{old_population + 1}\n")
    apply_incoming(inst, tmp_path, rebuild_derived=True)
    for day in range(inst.horizon_days):
        assert inst.demand[("D01", day)] == pytest.approx(
            old_demand[("D01", day)] * (old_population + 1) / old_population)
    assert sum(v for (d, day), v in inst.demand.items() if day == 0) < 506


def test_zero_old_model_requires_explicit_scale_for_new_positive_population(tmp_path):
    inst = load_instance()
    inst.districts[0].population = 0
    for day in range(inst.horizon_days):
        inst.demand[("D01", day)] = 0
    _write(tmp_path / "acs_districts.csv", "district_id,population\nD01,100\n")
    with pytest.raises(ValueError, match="Cannot identify prior demand scale"):
        apply_incoming(copy.deepcopy(inst), tmp_path, rebuild_derived=True)
    inst.meta["demand_scale"] = 0.1
    apply_incoming(inst, tmp_path, rebuild_derived=True)
    assert inst.demand[("D01", 0)] > 0


def test_observation_from_previous_overlay_remains_protected(tmp_path):
    inst = load_instance()
    _write(tmp_path / "demand_observed.csv", "district_id,day,demand_visits\nD01,0,123\n")
    apply_incoming(inst, tmp_path)
    (tmp_path / "demand_observed.csv").unlink()
    _write(tmp_path / "acs_districts.csv", "district_id,median_income_usd\nD01,20000\n")
    apply_incoming(inst, tmp_path, rebuild_derived=True)
    assert inst.demand[("D01", 0)] == 123


@pytest.mark.parametrize("column,value", [("capacity", "2.5"), ("lat", "91"), ("open_hour", "25")])
def test_invalid_site_input_is_not_silently_coerced(tmp_path, column, value):
    inst = load_instance()
    _write(tmp_path / "sites_mag.csv", f"site_id,{column}\n{inst.sites[0].id},{value}\n")
    with pytest.raises(ValueError):
        apply_incoming(inst, tmp_path)


def test_century_weekdays_never_merge_and_blank_sunday_is_unknown():
    sites = load_mag_sites(start_date="2026-07-20", horizon_days=7)
    century = next(s for s in sites if "Century Library" in s.name)
    monday, tuesday, sunday = [site_on_day(century, i) for i in (0, 1, 6)]
    assert (monday.open_hour, monday.close_hour) == (9, 17)
    assert (tuesday.open_hour, tuesday.close_hour) == (10, 18)
    assert (sunday.open_hour, sunday.close_hour) == (0, 0)
    assert sunday.extra["selected_calendar_rule"]["status"] == "unknown_blank_pair"
    assert sunday.extra["selected_calendar_rule"]["availability_policy"] == "conservative_zero_assumed"
    # Selection returns views; evaluating Tuesday cannot corrupt Monday.
    assert (century.open_hour, century.close_hour) == (9, 17)


def test_source_end_dates_and_holidays_are_enforced_before_active_flag():
    with MAG_CSV.open(encoding="utf-8-sig", newline="") as f:
        row = next(r for r in csv.DictReader(f) if "Century Library" in r["Location"])
    assert calendar_for_date(row, "2026-07-04")["status"] == "closed_explicit"
    assert calendar_for_date(row, "2026-07-03")["status"] == "unknown_holiday_observance"
    assert calendar_for_date(row, "2026-11-18")["status"] == "outside_posted_source_date_range"
    assert calendar_for_date(row, "2026-07-03", {"2026-07-03": "regular"})["status"] == "open_clock_pair"


def test_unknown_policy_can_fail_closed_instead_of_silently_assuming():
    with pytest.raises(ValueError, match="Unknown MAG hours"):
        load_mag_sites(start_date="2026-11-18", horizon_days=1, unknown_hours="error")
    for site in load_mag_sites(start_date="2026-11-18", horizon_days=1):
        assert site.open_hour == site.close_hour == 0


def test_calendar_cannot_silently_reuse_day_zero():
    site = load_mag_sites(horizon_days=1)[0]
    assert set(site.extra["calendar_by_day"]) == {"-1", "0", "1"}
    with pytest.raises(ValueError, match="calendar missing"):
        site_on_day(site, 2)


def test_transit_proxy_includes_direct_walk_for_both_network_parts():
    walking = build_real_instance(access_mode="walk_min")
    transit = build_real_instance(access_mode="transit_min")
    assert all(transit.access[k] <= walking.access[k] for k in walking.access)
    assert transit.meta["access_schedule_routing"] is False
    assert len(transit.candidate_sites()) == 8
    assert all(s.id.startswith("MAG") for s in transit.fixed_sites())


def test_official_population_overlay_does_not_fabricate_vehicle_or_demand():
    inst = load_instance()
    original_demand = dict(inst.demand)
    vehicles = {d.id: d.pct_no_vehicle for d in inst.districts}
    apply_official_demographics(inst)
    assert sum(d.population for d in inst.districts) == 1620649
    assert inst.demand == original_demand
    assert all(d.pct_no_vehicle == vehicles[d.id] for d in inst.districts)
    assert inst.meta["demographics_overlay"]["demand_rebuilt"] is False
