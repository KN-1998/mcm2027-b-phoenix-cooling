"""Q4 correctness checks derived from audit counterexamples and clock geometry."""
from __future__ import annotations

import unittest

from src.mch.disruption import plan_response
from src.mch.hours import capacity_after_ready
from src.mch.schema import District, Instance, Site


def district(did, income=10000):
    return District(did, did, 1000, .1, .1, income, .1, .5)


def site(sid, did, lat):
    return Site(sid, sid, "candidate_mch", did, lat, -112., 250, 9., 22.)


def pruning_fixture():
    districts = [district("A", 100000), district("B", 10000), district("C", 20000)]
    sites = [site("A", "A", 33.5),
             *[site("B" + str(n), "B", lat) for n, lat in enumerate([33.9, 34., 34.1], 1)],
             site("E", "C", 33.51)]
    access = {("A", "A"): 1., **{("B", "B" + str(n)): 1. for n in range(1, 4)},
              ("C", "E"): 1.}
    demand = {("A", 0): 100., ("B", 0): 99., ("C", 0): 95.}
    return Instance(districts, sites, access, demand, 1)


class TestQ4Takeover(unittest.TestCase):
    def test_default_exact_search_recovers_deadline_feasible_response(self):
        inst = pruning_fixture()
        exact = plan_response(inst, 1, mult=2., budget_hours=1.)
        heuristic = plan_response(inst, 1, mult=2., budget_hours=1., search_mode="heuristic")
        self.assertEqual(exact["search"]["mode"], "exact")
        self.assertEqual(exact["best"]["chosen"], ["E"])
        self.assertLess(exact["best"]["unmet"], heuristic["best"]["unmet"] - 70.)
        self.assertEqual(heuristic["search"]["optimality_status"], "heuristic_no_global_certificate")

    def test_arrival_reduces_only_the_affected_operating_period(self):
        s = site("X", "A", 33.5)
        # 130 visits in 13 opening hours => 10 visits/h. Arrive at10:00.
        self.assertAlmostEqual(capacity_after_ready(s, 130., "day", 1.), 70.)
        self.assertAlmostEqual(capacity_after_ready(s, 130., "evening", 1.), 50.)
        self.assertEqual(capacity_after_ready(s, 130., "night", 1.), 0.)
        # Arrival19:00 only leaves three evening hours; no renormalization.
        self.assertEqual(capacity_after_ready(s, 130., "day", 10.), 0.)
        self.assertAlmostEqual(capacity_after_ready(s, 130., "evening", 10.), 30.)

    def test_after_service_day_arrival_has_zero_capacity(self):
        s = site("X", "A", 33.5)
        self.assertEqual(sum(capacity_after_ready(s, 250., h, 24.)
                             for h in ("day", "evening", "night")), 0.)

    def test_overnight_window_is_intersected_on_unwrapped_clock(self):
        s = Site("N", "N", "candidate_mch", "A", 33.5, -112., 120, 20., 8.)
        self.assertAlmostEqual(capacity_after_ready(s, 120., "evening", 0.), 20.)
        self.assertAlmostEqual(capacity_after_ready(s, 120., "night", 0.), 100.)
        self.assertAlmostEqual(capacity_after_ready(s, 120., "night", 14.), 90.)

    def test_partial_response_can_idle_a_vehicle_from_closed_site(self):
        inst = Instance([district("B"), district("C")],
                        [site("A", "B", 35.), site("B", "B", 33.5), site("E", "C", 33.51)],
                        {("B", "B"): 1., ("C", "E"): 1.},
                        {("B", 0): 100., ("C", 0): 200.}, 1)
        result = plan_response(inst, 2, mult=1., initial_chosen=["A", "B"],
                               down_site="A", budget_hours=1.,crew_start_site='B')
        self.assertEqual(result["best"]["chosen"], ["E"])
        self.assertTrue(result["best"]["idle"])
        self.assertGreater(result["response_gain"], 70.)

    def test_original_deployment_is_fixed_before_forecast_error(self):
        inst = pruning_fixture()
        inst.demand = {key: value * 3. for key, value in inst.demand.items()}
        result = plan_response(inst, 1, initial_chosen=["A"], down_vehicle_at="A")
        self.assertEqual(result["base"]["chosen"], ["A"])
        self.assertEqual(result["fleet_healthy"], 0)
        self.assertEqual(result["best"]["chosen"], [])

    def test_vehicle_at_common_site_may_move_and_be_replaced(self):
        # Keeping B's vehicle in place would send distant A to high-demand C.
        # Instead B->C first and A->B retains service at B and reaches C early.
        inst = Instance([district(k) for k in "ABC"],
                        [site(k, k, lat) for k, lat in zip("ABC", [33., 33.5, 33.51])],
                        {(k, k): 1. for k in "ABC"},
                        {("A", 0): 100., ("B", 0): 10., ("C", 0): 600.}, 1)
        result = plan_response(inst, 2, mult=1., initial_chosen=["A", "B"],
                               down_site="A", budget_hours=5.,crew_start_site='B')
        self.assertEqual(result["best"]["chosen"], ["B", "C"])
        pairs = [(m["from"], m["to"]) for m in result["best"]["timeline"]]
        self.assertEqual(pairs, [("B", "C"), ("A", "B")])
        self.assertAlmostEqual(result["best"]["timeline"][0]["ready_h"], .53)
        second=result['best']['timeline'][1]
        self.assertGreater(second['crew_reposition_h'],1)
        self.assertAlmostEqual(second['depart_h'],.53+second['crew_reposition_h'])
        tight=plan_response(inst,2,mult=1.,initial_chosen=['A','B'],down_site='A',budget_hours=3.,crew_start_site='B')
        self.assertEqual(tight['best']['chosen'],['C'])

    def test_invalid_deadline_is_rejected(self):
        with self.assertRaises(ValueError):
            plan_response(pruning_fixture(), 1, budget_hours=25.)

    def test_explicit_zero_capacity_is_not_replaced_by_cli_default(self):
        sites = [site("A", "A", 33.), site("B", "B", 33.5), site("D", "D", 33.51)]
        sites[0].capacity = 0
        sites[0].extra["capacity_is_explicit"] = True
        inst = Instance([district(k) for k in ("A", "B", "D")], sites,
                        {(k, k): 1. for k in ("A", "B", "D")},
                        {("A", 0): 200., ("B", 0): 0., ("D", 0): 600.}, 1)
        result = plan_response(inst, 2, mult=1., initial_chosen=["A", "B"], budget_hours=3.)
        self.assertIn("A", result["best"]["chosen"])
        for sid, caps in result["best"].get("capacity_by_period", {}).items():
            if sid == "A":
                self.assertEqual(sum(caps.values()), 0.)
        # A provides zero visits, D at most250 and B has no demand.
        # A phantom 250-capacity A would violate this physical lower bound.
        self.assertGreaterEqual(result["best"]["unmet"], 800. - 250.)


if __name__ == "__main__":
    unittest.main()
