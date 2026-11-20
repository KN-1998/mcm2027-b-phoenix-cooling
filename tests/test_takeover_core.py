"""Independent small-model checks of Q3 DP and dated clock capacity.

The one-vehicle enumeration computes service by hand from interval endpoints;
it does not call the transition LP or any production capacity helper.
"""
from __future__ import annotations

import itertools
import unittest
from unittest.mock import patch

from src.mch.dynamic import solve_week_dp
from src.mch.hours import capacity_after_ready, capacity_on_service_day
from src.mch.schema import District, Instance, Site
from src.mch.static import _active_sites, _assign


def fixture(days=3):
    names = "ABC"
    districts = [District(k, k, 1000, .1, .1, 20000, .1, .5) for k in names]
    sites = [Site(k, k, "candidate_mch", k, 33.5 + i * .01, -112., 250, 9., 22.)
             for i, k in enumerate(names)]
    daily = [(500., 100., 20.), (80., 400., 40.), (20., 60., 500.)]
    demand = {(k, day): daily[day][i] for day in range(days) for i, k in enumerate(names)}
    instance = Instance(districts, sites, {(k, k): 1. for k in names}, demand, days,
                        {"unsheltered_share": .5})
    travel = {(a, b): 2. * abs(names.index(a) - names.index(b)) for a in names for b in names}
    return instance, travel


def brute_force_one_vehicle(inst, travel):
    # Both segment groups have been combined algebraically at share0.5.
    shares = {"day": .425, "evening": .415, "night": .16}
    windows = {"day": (9., 17.), "evening": (17., 22.), "night": (22., 33.)}
    total_demand = sum(inst.demand.values())
    by_path = {}
    for path in itertools.product("ABC", repeat=inst.horizon_days):
        served = 0.
        for day, sid in enumerate(path):
            arrival = 9. + (travel[path[day - 1], sid] if day else 0.)
            need = inst.demand[sid, day]
            for period, (lo, hi) in windows.items():
                hours = max(0., min(22., hi) - max(9., lo, arrival))
                served += min(need * shares[period], 250. / 13. * hours)
        by_path[path] = total_demand - served
    return by_path


class TestTakeoverCoreIndependent(unittest.TestCase):
    def test_dp_matches_exhaustive_paths_with_independent_service_formula(self):
        for days in (2, 3):
            inst, travel = fixture(days)
            with patch("src.mch.dynamic.move_time_hours", side_effect=lambda _, a, b: travel[a, b]):
                result = solve_week_dp(inst, 1)
            paths = brute_force_one_vehicle(inst, travel)
            self.assertAlmostEqual(result["dynamic_total_unmet"], min(paths.values()), places=5)
            static_best = min(value for path, value in paths.items() if len(set(path)) == 1)
            self.assertAlmostEqual(result["static_total_unmet"], static_best, places=5)
            self.assertLessEqual(result["dynamic_total_unmet"], result["static_total_unmet"] + 1e-6)
            chosen = tuple(day["combo"][0] for day in result["schedule"])
            self.assertAlmostEqual(paths[chosen], min(paths.values()), places=5)
            self.assertEqual(result["search_status"], "optimal_within_model")

    def test_cross_day_trip_is_explicitly_rejected(self):
        inst, _ = fixture()
        with patch("src.mch.dynamic.move_time_hours", side_effect=lambda _, a, b: 0. if a == b else 48.):
            with self.assertRaisesRegex(ValueError, "cross-day transit"):
                solve_week_dp(inst, 1)

    def test_constant_demand_retains_a_no_move_solution(self):
        inst, travel = fixture()
        for day in range(inst.horizon_days):
            for sid, need in zip("ABC", (500., 100., 20.)):
                inst.demand[sid, day] = need
        with patch("src.mch.dynamic.move_time_hours", side_effect=lambda _, a, b: travel[a, b]):
            result = solve_week_dp(inst, 1)
        self.assertAlmostEqual(result["dynamic_total_unmet"], result["static_total_unmet"], places=6)
        self.assertTrue(all(not day["moves"] for day in result["schedule"]))

    def test_top_k_reports_restricted_search(self):
        inst, travel = fixture()
        with patch("src.mch.dynamic.move_time_hours", side_effect=lambda _, a, b: travel[a, b]):
            result = solve_week_dp(inst, 1, top_k=1)
        self.assertEqual(result["search_status"], "restricted_state_heuristic")
        self.assertLessEqual(result["dynamic_total_unmet"], result["static_total_unmet"] + 1e-6)

    def test_morning_arrival_preserves_evening_capacity(self):
        site = Site("X", "X", "candidate_mch", "D", 0, 0, 130, 9., 22.)
        self.assertAlmostEqual(capacity_after_ready(site, 130., "day", 1.), 70.)
        self.assertAlmostEqual(capacity_after_ready(site, 130., "evening", 1.), 50.)

    def test_explicit_zero_capacity_remains_zero_in_period_assignment(self):
        inst, _ = fixture()
        inst.sites[0].capacity = 0
        inst.sites[0].extra["capacity_is_explicit"] = True
        result = _assign(inst, _active_sites(inst, ["A"]), 0, 30., 250.)
        self.assertEqual(sum(result.served.values()), 0.)

    def test_next_morning_uses_following_calendar_date(self):
        calendar = {"-1": {"open_hour": 0., "close_hour": 0.},
                    "0": {"open_hour": 8., "close_hour": 17.},
                    "1": {"open_hour": 0., "close_hour": 0.}}
        site = Site("X", "X", "cooling", "D", 0, 0, 90, 8., 17.,
                    extra={"calendar_by_day": calendar})
        self.assertAlmostEqual(capacity_on_service_day(site, 90., "day", 0), 80.)
        self.assertEqual(capacity_on_service_day(site, 90., "night", 0), 0.)
        calendar["1"] = {"open_hour": 8., "close_hour": 17.}
        self.assertAlmostEqual(capacity_on_service_day(site, 90., "night", 0), 10.)

    def test_mobile_daily_ceiling_rejects_unphysical_input(self):
        inst, _ = fixture()
        inst.sites[0].capacity = 251
        with self.assertRaisesRegex(ValueError,'250'):
            _assign(inst,_active_sites(inst,['A']),0,30.,250.)

    def test_overlapping_dated_windows_need_a_staffing_rule(self):
        site=Site('X','X','cooling','D',0,0,90,20,8,
                  extra={'calendar_by_day':{'-1':{'open_hour':20,'close_hour':8},
                                           '0':{'open_hour':6,'close_hour':17},
                                           '1':{'open_hour':0,'close_hour':0}}})
        with self.assertRaisesRegex(ValueError,'overlapping'):
            capacity_on_service_day(site,90,'day',0)


if __name__ == "__main__":
    unittest.main()
