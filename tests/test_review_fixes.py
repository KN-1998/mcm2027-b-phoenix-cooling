from __future__ import annotations

import unittest
from pathlib import Path

from src.mch.disruption import apply_shock
from src.mch.hours import PERIODS, capacity_in_period
from src.mch.loaders import load_instance
from src.mch.schema import District, Instance, Site
from src.mch.static import _active_sites, _assign

DATA = Path(__file__).resolve().parents[1] / "data" / "processed"
HAVE = (DATA / "districts.csv").exists()


class TestCapacityConservation(unittest.TestCase):
    """P1：时段容量之和必须等于日容量（不能重复折减）。"""

    def _check(self, open_h, close_h):
        s = Site("X", "X", "cooling", "D", 0, 0, 250, open_h, close_h)
        total = sum(capacity_in_period(s, 250.0, h) for h in PERIODS)
        self.assertAlmostEqual(total, 250.0, places=6)
        return {h: capacity_in_period(s, 250.0, h) for h in PERIODS}

    def test_9_17(self):
        caps = self._check(9, 17)
        self.assertAlmostEqual(caps["day"], 250.0, places=6)   # 全部在白天
        self.assertEqual(caps["night"], 0.0)

    def test_9_19(self):
        caps = self._check(9, 19)
        self.assertAlmostEqual(caps["day"], 200.0, places=6)   # 8/10
        self.assertAlmostEqual(caps["evening"], 50.0, places=6)  # 2/10

    def test_24_7(self):
        self._check(0, 24)


class TestShockPurity(unittest.TestCase):
    """P1：Q4 冲击不得修改输入，重复调用结果一致。"""

    def _inst(self):
        D = [District("A", "A", 1, 0.1, 0.1, 50000, 0.1, 0.5)]
        S = [Site("S", "S", "cooling", "A", 0, 0, 100, 0, 24)]
        return Instance(D, S, {("A", "S"): 1}, {("A", 0): 10.0}, 1)

    def test_input_unchanged(self):
        inst = self._inst()
        before = dict(inst.demand)
        apply_shock(inst, ["A"], 1.8)
        self.assertEqual(inst.demand, before)

    def test_idempotent(self):
        inst = self._inst()
        a = apply_shock(inst, ["A"], 1.8)
        b = apply_shock(inst, ["A"], 1.8)
        self.assertAlmostEqual(a.demand[("A", 0)], b.demand[("A", 0)])
        self.assertAlmostEqual(a.demand[("A", 0)], 18.0)


class TestDowntimeScopedToMoved(unittest.TestCase):
    """P1：停服只作用于搬入的枢纽，未搬的容量不变。"""

    def test_only_moved_site_reduced(self):
        D = [District("A", "A", 1, 0.1, 0.1, 50000, 0.1, 0.5)]
        S = [Site("S1", "S1", "candidate_mch", "A", 0, 0, 100, 0, 24),
             Site("S2", "S2", "candidate_mch", "A", 0, 0, 100, 0, 24)]
        inst = Instance(D, S, {("A", "S1"): 1, ("A", "S2"): 1}, {("A", 0): 300.0}, 1)
        full = _assign(inst, S, 0, 30.0, 250.0, mode="daily")
        half = _assign(inst, S, 0, 30.0, 250.0, downtime={"S1": 0.5}, mode="daily")
        self.assertAlmostEqual(full.served[("A", 0)], 200.0, places=6)
        self.assertAlmostEqual(half.served[("A", 0)], 150.0, places=6)   # 100*0.5 + 100


@unittest.skipUnless(HAVE, "run tools/build_data.py first")
class TestEquityExemption(unittest.TestCase):
    def test_global_structural_set_used(self):
        from src.mch.diagnostics import structural_set
        from src.mch.static import solve_static_fair
        inst = load_instance()
        expected = structural_set(inst)
        sol = solve_static_fair(inst, 2, equity_cap=0.9)
        self.assertEqual(list(sol.metrics.get("equity_exempt", [])), expected)


if __name__ == "__main__":
    unittest.main()
