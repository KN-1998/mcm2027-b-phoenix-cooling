from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.mch.disruption import plan_response

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
HAVE = (DATA / "districts.csv").exists()
PLAN = ROOT / "results" / "takeover_20261120" / "q5" / "summary.json"
Q5 = PLAN.parent / 'plan.csv'


@unittest.skipUnless(HAVE, "run tools/build_data.py first")
class TestQ4V4(unittest.TestCase):
    """第五轮审查的验收项。"""

    @classmethod
    def setUpClass(cls):
        from src.mch.loaders import load_instance
        cls.inst = load_instance()

    def test_no_move_always_candidate_when_site_closed(self):
        """关闭已部署点时，不搬必须仍然可行（P2-A）。"""
        r = plan_response(self.inst, 3, mult=1.0, down_site="MCH-3")
        self.assertTrue(r["feasible_any"])
        self.assertIsNotNone(r["best"])
        self.assertGreaterEqual(r["response_gain"], 0.0)

    def test_p8_closed_site_has_option(self):
        """p=8 关闭一个已部署点不应出现"零可行方案"（审查反例）。"""
        r = plan_response(self.inst, 8, mult=1.0, down_site="MCH-3")
        self.assertGreater(r["n_options"], 0)
        self.assertTrue(r["feasible_any"])
        self.assertAlmostEqual(r["no_move"]["unmet"], 189.439, delta=0.5)

    def test_parallel_not_serial(self):
        """并行就绪时间不超过串行（P2-B）。"""
        a = plan_response(self.inst, 3, mult=1.0, down_site="MCH-3", parallel=True)
        b = plan_response(self.inst, 3, mult=1.0, down_site="MCH-3", parallel=False)
        if a["best"]["action"] == "relocate" and b["best"]["action"] == "relocate":
            self.assertLessEqual(a["best"]["total_hours"], b["best"]["total_hours"] + 1e-9)


@unittest.skipUnless(PLAN.exists() and Q5.exists(), "先运行 run_q5_plan")
class TestQ5Accounting(unittest.TestCase):
    """Q5 年度记账（第五轮 P1）。"""

    def test_every_year_charges_fleet_opex(self):
        import csv
        rows = list(csv.DictReader(Q5.open(encoding="utf-8-sig")))
        cost = json.loads(PLAN.read_text(encoding="utf-8"))["cost_assumptions"]
        for r in rows:
            fleet = int(r["fleet"])
            self.assertAlmostEqual(float(r["hub_opex"]), fleet * cost["hub_ops"], delta=1.0)

    def test_budget_respected(self):
        import csv
        rows = list(csv.DictReader(Q5.open(encoding="utf-8-sig")))
        for r in rows:
            self.assertLessEqual(float(r["total_cost"]), float(r["budget"]) + 1.0, msg=str(r["year"]))

    def test_worst_fraction_has_valid_range(self):
        """The frozen-artifact statistic is a proportion; no equity optimum implied."""
        import csv
        rows = list(csv.DictReader(Q5.open(encoding="utf-8-sig")))
        self.assertTrue(all(0.0 <= float(r["worst_after"]) <= 1.0 for r in rows))


if __name__ == "__main__":
    unittest.main()
