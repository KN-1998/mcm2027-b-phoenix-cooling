from __future__ import annotations

import unittest

from src.mch import demand as demand_mod
from src.mch.static import solve_static, sweep_p
from src.mch.synthetic import build_instance
from src.mch.validate import (check_capacity, check_determinism,
                              check_nonnegative_unmet, check_zero_demand)
from src.mch.schema import validate_instance


def make_instance(p=2):
    inst = build_instance(seed=2027)
    demand_mod.fill_demand(inst)
    demand_mod.calibrate(inst, 3000.0)
    return inst


class TestFeasibility(unittest.TestCase):
    def test_instance_valid(self):
        inst = make_instance()
        self.assertEqual(validate_instance(inst), [])

    def test_a1_capacity(self):
        inst = make_instance()
        sol = solve_static(inst, 3)
        check_capacity(sol, 250.0)

    def test_a2_nonnegative(self):
        inst = make_instance()
        sol = solve_static(inst, 3)
        check_nonnegative_unmet(inst, sol)

    def test_a3_zero_demand(self):
        inst = make_instance()
        check_zero_demand(inst, 2)

    def test_a4_determinism(self):
        inst = make_instance()
        check_determinism(inst, 2)


class TestMonotonic(unittest.TestCase):
    def test_more_hubs_not_worse(self):
        """p 增加时未满足需求不应上升（覆盖单调性）。"""
        inst = make_instance()
        curve = sweep_p(inst, pmax=5)
        unmets = [r["unmet_total"] for r in curve]
        for a, b in zip(unmets, unmets[1:]):
            self.assertLessEqual(b, a + 1e-6, f"未满足需求随 p 上升: {unmets}")


if __name__ == "__main__":
    unittest.main()
