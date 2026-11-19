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


# Q4 的车队守恒与"不搬"候选等不变量已迁移到 tests/test_q4_v3.py（v3 接口）。


if __name__ == "__main__":
    unittest.main()
