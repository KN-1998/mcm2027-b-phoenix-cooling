"""Small independent service fixtures verify Q5 stock, budgets and DP optimality."""
from __future__ import annotations

import copy
import itertools
import unittest
from unittest.mock import patch

from src.mch.policy import annual_cost, evaluate, plan_investment, scenario_evaluator
from src.mch.schema import District, Instance, Site


def costs(buy=1, ops=1):
    return {"hub_buy": buy, "hub_ops": ops, "extend_21": 10_000,
            "extend_22": 20_000, "shuttle": 10_000}


class TestQ5Investment(unittest.TestCase):
    def test_zero_budget_zero_stock_is_feasible(self):
        result = plan_investment(None, [0] * 5, [1] * 5, p_start=0, p_max=2,
                                 costs=costs(), evaluator=lambda i, p, e, s: (10 - p, 1))
        self.assertTrue(result["summary"]["all_within_budget"])
        self.assertEqual(result["summary"]["weighted_unmet_visits"], 50)
        self.assertTrue(all(r["active"] == r["buy"] == r["total_cost"] == 0 for r in result["rows"]))

    def test_idle_assets_can_reactivate_without_purchase(self):
        result = plan_investment(None, [14, 16], [1, 4], p_start=8, p_max=8,
                                 costs=costs(buy=80, ops=2),
                                 evaluator=lambda i, p, e, s: (max(0, [7, 8][i] - p), 0))
        first, second = result["rows"]
        self.assertEqual((first["active"], first["owned"], first["idled"]), (7, 8, 1))
        self.assertEqual((second["active"], second["owned"], second["buy"]), (8, 8, 0))
        self.assertEqual(second["capital"], 0)
        self.assertEqual(second["hub_opex"], 16)

    def test_more_than_one_purchase_is_available(self):
        result = plan_investment(None, [8], [1], p_start=0, p_max=4,
                                 costs=costs(), evaluator=lambda i, p, e, s: (4 - p, 0))
        self.assertEqual(result["rows"][0]["buy"], 4)
        self.assertEqual(result["rows"][0]["active"], 4)
        self.assertEqual(result["rows"][0]["total_cost"], 8)

    def test_future_budget_shortfall_distinguishes_dp_from_rolling(self):
        evaluator = lambda i, p, e, s: (max(0, [1, 2][i] - p), 0)
        common = dict(inst=None, budgets=[6, 2], heat_multipliers=[1, 1], p_start=0,
                      p_max=2, costs=costs(buy=2, ops=1), evaluator=evaluator)
        dp = plan_investment(**common, strategy="dp")
        rolling = plan_investment(**common, strategy="rolling")
        self.assertEqual(dp["summary"]["weighted_unmet_visits"], 0)
        self.assertEqual(rolling["summary"]["weighted_unmet_visits"], 1)
        self.assertEqual(dp["rows"][0]["buy"], 2)
        self.assertEqual(dp["rows"][0]["active"], 1)
        self.assertEqual(dp["rows"][0]["idled"], 1)
        self.assertEqual(dp["summary"]["total_spend"], 7)
        self.assertEqual(rolling["rows"][0]["buy"], 1)

    def test_budget_components_and_stock_conservation(self):
        price = costs(buy=3, ops=2)
        result = plan_investment(None, [9, 4, 12], [1, 1, 1], p_start=1, p_max=4,
                                 costs=price, evaluator=lambda i, p, e, s: (10 - p, 0.5))
        owned = 1
        for row in result["rows"]:
            self.assertEqual(row["owned_before"], owned)
            self.assertEqual(row["owned"], owned + row["buy"] - row["retire"])
            self.assertLessEqual(row["active"], row["owned"])
            self.assertEqual(row["total_cost"], sum(row[k] for k in ("capital", "hub_opex", "extend_cost", "shuttle_cost")))
            self.assertLessEqual(row["total_cost"], row["budget"])
            self.assertEqual(row["hub_opex"], row["active"] * 2)
            owned = row["owned"]

    def test_dp_matches_independent_complete_sequence_enumeration(self):
        budget, price = [6, 2, 4], costs(buy=2, ops=1)
        demand = [1, 2, 3]
        all_paths = []
        for action_path in itertools.product(itertools.product(range(4), range(4)), repeat=3):
            owned, unmet, spend, feasible = 0, 0, 0, True
            for i, (buy, active) in enumerate(action_path):
                owned += buy
                cost = 2 * buy + active
                feasible &= cost <= budget[i] and active <= owned <= 3
                unmet += max(0, demand[i] - active)
                spend += cost
            if feasible:
                all_paths.append((unmet, 0, spend))
        result = plan_investment(None, budget, [1] * 3, p_start=0, p_max=3, costs=price,
                                 evaluator=lambda i, p, e, s: (max(0, demand[i] - p), 0))
        summary = result["summary"]
        self.assertEqual((summary["weighted_unmet_visits"], 0, summary["total_spend"]), min(all_paths))

    def test_contract_can_expire_when_budget_disappears(self):
        price = costs()
        price["extend_21"] = 1
        result = plan_investment(None, [1, 0], [1, 1], p_start=0, p_max=0, costs=price,
                                 evaluator=lambda i, p, e, s: (0 if e else 5, 0))
        self.assertEqual(result["rows"][0]["extend_to"], 21)
        self.assertIsNone(result["rows"][1]["extend_to"])

    def test_preserves_original_hours_and_does_not_mutate_instance(self):
        inst = Instance([District("D", "D", 10, 0, 0, 1, 0, 0)],
                        [Site("F", "F", "cooling", "D", 0, 0, 50, 9, 20),
                         Site("M", "M", "candidate_mch", "D", 0, 0, 250, 9, 22)],
                        {}, {("D", 0): 10})
        original = copy.deepcopy(inst)
        observed = []

        def solve(local, p, **kwargs):
            observed.append([(s.open_hour, s.close_hour) for s in local.sites])
            return type("Sol", (), {"metrics": {"unmet_total": 3, "worst_unmet_ratio": .3,
                                               'unmet_total_raw':3,'worst_unmet_ratio_raw':.3}})()

        with patch("src.mch.policy.solve_static", side_effect=solve):
            self.assertEqual(evaluate(inst, 1, None, False), (3, .3))
            evaluate(inst, 1, 21, False)
            lookup = scenario_evaluator(inst, [2])
            self.assertEqual(lookup(0, 1, None, False), lookup(0, 1, None, False))
        self.assertEqual(observed[0], [(9, 20), (9, 22)])
        self.assertEqual(observed[1], [(9, 21), (9, 22)])
        self.assertEqual(len(observed), 3)
        self.assertEqual(inst, original)

    def test_invalid_domain_is_rejected(self):
        common = dict(inst=None, budgets=[1], heat_multipliers=[1], evaluator=lambda *args: (0, 0))
        with self.assertRaises(ValueError):
            plan_investment(**common, p_start=-1)
        with self.assertRaises(ValueError):
            plan_investment(**{**common, "budgets": [-1]})
        with self.assertRaises(ValueError):
            plan_investment(**common, costs={**costs(), "hub_ops": -1})

    def test_calendar_extension_enters_actual_service_lp(self):
        # Evening-only modeled demand is served only if the source day's
        # known-open calendar is really extended inside site_on_day.
        fixed = Site("F", "F", "cooling", "D", 0, 0, 1000, 9, 17,
                     extra={"calendar_by_day": {
                         "-1": {"status": "closed_explicit", "open_hour": 0, "close_hour": 0},
                         "0": {"status": "open_clock_pair", "open_hour": 9, "close_hour": 17},
                         "1": {"status": "unknown_blank_pair", "open_hour": 0, "close_hour": 0},
                         "2": {"status": "closed_explicit", "open_hour": 0, "close_hour": 0},
                         "3": {"status": "closed_explicit", "open_hour": 0, "close_hour": 0},
                     }})
        inst = Instance([District("D", "D", 10, 0, 0, 1, 0, 0)], [fixed],
                        {("D", "F"): 1}, {("D", 0): 100, ("D", 1): 100, ("D", 2): 100},
                        horizon_days=3, meta={"unsheltered_share": 1})
        original = copy.deepcopy(inst)
        unmet_base, _ = evaluate(inst, 0, None, False)
        unmet_extended, _ = evaluate(inst, 0, 22, False)
        self.assertLess(unmet_extended, unmet_base)
        self.assertEqual(evaluate(inst, 0, 22, False, day=1)[0], 100)
        self.assertEqual(evaluate(inst, 0, 22, False, day=2)[0], 100)
        self.assertEqual(inst, original)


if __name__ == "__main__":
    unittest.main()
