from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "results" / "q5_plan" / "summary.json"


@unittest.skipUnless(PLAN.exists(), "先运行 run_q5_plan")
class TestQ5Plan(unittest.TestCase):
    """Q5 计划的结构性不变量。"""

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

    def test_first_action_is_extension(self):
        """所有情景的第一年都包含延时（v3 组合动作下按 extend_to 判定，不看动作字符串）。"""
        import csv
        rows = list(csv.DictReader((ROOT / "results" / "q5_plan" / "plan.csv").open(encoding="utf-8-sig")))
        first = [r for r in rows if r["year"] == "2027"]
        self.assertTrue(first)
        for r in first:
            self.assertNotEqual(r["extend_to"], "", msg=(r["budget_scenario"], r["heat_scenario"]))

    def test_cost_assumptions_declared(self):
        self.assertIn("hub_buy", self.data["cost_assumptions"])


if __name__ == "__main__":
    unittest.main()
