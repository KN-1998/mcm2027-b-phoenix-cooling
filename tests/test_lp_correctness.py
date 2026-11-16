from __future__ import annotations

import unittest
from pathlib import Path

from src.mch.loaders import load_instance
from src.mch.schema import District, Instance, Site
from src.mch.static import _active_sites, _assign, solve_static

DATA = Path(__file__).resolve().parents[1] / "data" / "processed"
HAVE = (DATA / "districts.csv").exists()


def _d(i):
    return District(i, i, 1, 0.1, 0.1, 50000, 0.1, 0.5)


class TestLpAssignment(unittest.TestCase):
    def test_greedy_counterexample_now_optimal(self):
        """审查者反例：A=10 可到 S1/S2，B=9 只到 S1，容量各 10 -> 最优 19。"""
        D = [_d("A"), _d("B")]
        S = [Site("S1", "S1", "cooling", "A", 0, 0, 10, 0, 24),
             Site("S2", "S2", "cooling", "A", 0, 0, 10, 0, 24)]
        inst = Instance(D, S, {("A", "S1"): 1, ("A", "S2"): 2, ("B", "S1"): 1, ("B", "S2"): 999},
                        {("A", 0): 10.0, ("B", 0): 9.0}, 1)
        sol = _assign(inst, _active_sites(inst, ()), 0, 30.0, 250.0)
        self.assertAlmostEqual(sum(sol.served.values()), 19.0, places=6)

    def test_nonnegative_and_bounded(self):
        inst = Instance([_d("A")], [Site("S1", "S1", "cooling", "A", 0, 0, 5, 0, 24)],
                        {("A", "S1"): 1}, {("A", 0): 10.0}, 1)
        sol = _assign(inst, _active_sites(inst, ()), 0, 30.0, 250.0)
        self.assertLessEqual(sol.served[("A", 0)], 10.0 + 1e-9)
        self.assertLessEqual(sol.served[("A", 0)], 5.0 + 1e-9)


@unittest.skipUnless(HAVE, "run tools/build_data.py first")
class TestCapacityParameter(unittest.TestCase):
    def test_override_changes_result(self):
        """审查者 P1-3：capacity 入口必须真正生效。"""
        a = solve_static(load_instance(), 3, override=20.0)
        b = solve_static(load_instance(), 3, override=250.0)
        self.assertNotAlmostEqual(a.metrics["unmet_total"], b.metrics["unmet_total"], places=3)
        self.assertGreater(a.metrics["unmet_total"], b.metrics["unmet_total"])


if __name__ == "__main__":
    unittest.main()
