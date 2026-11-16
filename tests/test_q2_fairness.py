from __future__ import annotations

import unittest
from pathlib import Path

from src.mch.loaders import load_instance
from src.mch.static import efficiency_equity_frontier, solve_static, solve_static_fair

DATA = Path(__file__).resolve().parents[1] / "data" / "processed"
HAVE = (DATA / "districts.csv").exists()


def _inst_without(structural=("D08",)):
    inst = load_instance()
    inst.demand = {k: (0.0 if k[0] in structural else v) for k, v in inst.demand.items()}
    return inst


@unittest.skipUnless(HAVE, "run tools/build_data.py first")
class TestFairness(unittest.TestCase):
    def test_cap_respected_when_feasible(self):
        inst = _inst_without()
        sol = solve_static_fair(inst, 3, equity_cap=0.5)
        self.assertTrue(sol.metrics["equity_cap_met"])
        self.assertLessEqual(sol.metrics["worst_unmet_ratio"], 0.5 + 1e-9)

    def test_tradeoff_exists_at_p2(self):
        """Q2 的核心结论：p=2 时效率最优会把一个区留成 100% 未满足。"""
        inst = _inst_without()
        eff = solve_static(inst, 2)
        fair = solve_static_fair(inst, 2, equity_cap=0.0)
        self.assertGreater(eff.metrics["worst_unmet_ratio"], 0.99)
        self.assertLess(fair.metrics["worst_unmet_ratio"], 0.5)
        self.assertGreaterEqual(fair.metrics["unmet_total"], eff.metrics["unmet_total"] - 1e-9)

    def test_frontier_monotone(self):
        """cap 放宽时，未满足量不应上升（可行集变大）。"""
        inst = _inst_without()
        rows = efficiency_equity_frontier(inst, 2, caps=(1.0, 0.5, 0.2))
        unmets = [r["unmet_total"] for r in rows]
        self.assertLessEqual(unmets[0], unmets[1] + 1e-6)
        self.assertLessEqual(unmets[1], unmets[2] + 1e-6)

    def test_structural_not_fixable(self):
        """D08 在任何 p 下都服务不到 —— 需要非枢纽手段。"""
        inst = load_instance()
        without = _inst_without(())
        sol = solve_static(without, 8)
        served_d08 = sol.served.get(("D08", 0), 0.0)
        self.assertEqual(served_d08, 0.0)


if __name__ == "__main__":
    unittest.main()
