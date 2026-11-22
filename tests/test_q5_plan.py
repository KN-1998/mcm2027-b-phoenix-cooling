from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "results" / "completion_20261121" / "base" / "q5" / "summary.json"


@unittest.skipUnless(PLAN.exists(), "先运行 run_q5_plan")
class TestQ5Plan(unittest.TestCase):
    """Schema/accounting checks of the published frozen baseline artifact.

    The independent current-code state/decision tests are test_q5_investment.
    """

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(PLAN.read_text(encoding="utf-8"))

    def test_all_scenarios_present(self):
        self.assertEqual(len(self.data["plans"]), 9)   # 3 预算 x 3 热浪

    def test_each_plan_has_five_years(self):
        for k, v in self.data["plans"].items():
            self.assertEqual(len(v["actions"]), 5, msg=k)

    def test_never_exceeds_budget(self):
        budgets = self.data["budgets"]
        for k, v in self.data["plans"].items():
            b = budgets[k.split("/")[0]]
            self.assertLessEqual(v["total_spend"], 5 * b + 1, msg=k)

    def test_cost_assumptions_declared(self):
        self.assertIn("hub_buy", self.data["cost_assumptions"])


if __name__ == "__main__":
    unittest.main()
