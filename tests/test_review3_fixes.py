from __future__ import annotations

import unittest
from pathlib import Path

from src.mch.hours import PERIODS, capacity_in_period
from src.mch.schema import District, Instance, Site
from src.mch.static import _active_sites, _assign

DATA = Path(__file__).resolve().parents[1] / "data" / "processed"
HAVE = (DATA / "districts.csv").exists()


def _inst(open_h, close_h):
    D = [District("A", "A", 100, 0.1, 0.1, 50000, 0.1, 0.5)]
    S = [Site("X", "X", "cooling", "A", 0, 0, 50, open_h, close_h)]
    return Instance(D, S, {("A", "X"): 1}, {("A", 0): 100.0}, 1)


class TestPeriodFilter(unittest.TestCase):
    """R4：纯晚间/纯夜间站点不应被整体排除。"""

    def test_evening_only_site_serves(self):
        from src.mch.assign import solve_assignment_periods
        from src.mch.hours import split_demand_mixed
        inst = _inst(17, 22)
        s = inst.sites[0]
        caps = {"X": {h: capacity_in_period(s, 50.0, h) for h in PERIODS}}
        dems = {"A": split_demand_mixed(100.0, 0.5)}
        out = solve_assignment_periods(inst, inst.sites, 0, 30.0, caps, dems)
        self.assertGreater(sum(out["served"].values()), 30.0)

    def test_night_only_site_serves(self):
        from src.mch.assign import solve_assignment_periods
        from src.mch.hours import split_demand_mixed
        inst = _inst(0, 9)
        s = inst.sites[0]
        caps = {"X": {h: capacity_in_period(s, 50.0, h) for h in PERIODS}}
        dems = {"A": split_demand_mixed(100.0, 0.5)}
        out = solve_assignment_periods(inst, inst.sites, 0, 30.0, caps, dems)
        self.assertGreater(sum(out["served"].values()), 10.0)


from src.mch.disruption import plan_response  # noqa: E402


@unittest.skipUnless(HAVE, "run tools/build_data.py first")
class TestFleetConservation(unittest.TestCase):
    """R1：车辆故障后健康车队减一，且故障车不得成为搬迁来源。"""

    def test_vehicle_failure_reduces_fleet(self):
        from src.mch.loaders import load_instance
        inst = load_instance()
        r = plan_response(inst, 3, mult=1.8, down_vehicle="MCH-3")
        self.assertEqual(r["fleet_healthy"], 2)
        origins = {m["from"] for m in r["moves"] if m["from"]}
        self.assertNotIn("MCH-3", origins)

    def test_site_unavailable_keeps_fleet(self):
        from src.mch.loaders import load_instance
        inst = load_instance()
        r = plan_response(inst, 3, mult=1.8, down_site="MCH-3")
        self.assertEqual(r["fleet_healthy"], 3)
        self.assertLessEqual(len(r["moves"]), 3)

    def test_infeasible_gain_not_counted(self):
        from src.mch.loaders import load_instance
        inst = load_instance()
        r = plan_response(inst, 3, mult=1.8, down_site="MCH-3", budget_hours=0.1)
        if not r["feasible_within_budget"]:
            self.assertIsNone(r["response_gain"])
            self.assertIsNotNone(r["response_gain_infeasible"])


if __name__ == "__main__":
    unittest.main()
