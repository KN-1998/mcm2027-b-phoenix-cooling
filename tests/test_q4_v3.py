from __future__ import annotations

import unittest
from pathlib import Path

from src.mch.disruption import plan_response

DATA = Path(__file__).resolve().parents[1] / "data" / "processed"
HAVE = (DATA / "districts.csv").exists()


@unittest.skipUnless(HAVE, "run tools/build_data.py first")
class TestQ4V3(unittest.TestCase):
    """第四轮审查的核心不变量。"""

    @classmethod
    def setUpClass(cls):
        from src.mch.loaders import load_instance
        cls.inst = load_instance()

    def test_undeployed_vehicle_raises(self):
        """未部署的点报车辆故障必须报错，不能静默减车队。"""
        with self.assertRaises(ValueError):
            plan_response(self.inst, 3, mult=1.0, down_vehicle_at="MCH-1")

    def test_vehicle_failure_reduces_fleet_only(self):
        """车辆故障：车队 p-1，但场地仍可用 → 健康车可以搬过去，收益 >= 0。"""
        r = plan_response(self.inst, 3, mult=1.0, down_vehicle_at="MCH-3")
        self.assertEqual(r["fleet_healthy"], 2)
        self.assertIsNotNone(r["response_gain"])
        self.assertGreaterEqual(r["response_gain"], 0.0)

    def test_site_failure_keeps_fleet(self):
        r = plan_response(self.inst, 3, mult=1.8, down_site="C01")
        self.assertEqual(r["fleet_healthy"], 3)

    def test_gain_never_negative_when_no_move_feasible(self):
        """不搬始终是候选 → 报告的最优方案收益恒 >= 0。"""
        for kw in ({"down_site": "R01"}, {"down_vehicle_at": "MCH-3"},
                   {"down_site": "MCH-3"}):
            r = plan_response(self.inst, 3, mult=1.8, **kw)
            if r["response_gain"] is not None:
                self.assertGreaterEqual(r["response_gain"], 0.0, msg=str(kw))

    def test_no_move_is_candidate(self):
        """无中断时应报 0 收益、0 次迁移。"""
        r = plan_response(self.inst, 3, mult=1.0)
        self.assertEqual(r["response_gain"], 0.0)


if __name__ == "__main__":
    unittest.main()
