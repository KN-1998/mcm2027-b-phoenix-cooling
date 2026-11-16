from __future__ import annotations

import unittest
from pathlib import Path

from src.mch.diagnostics import access_gap
from src.mch.loaders import load_instance
from src.mch.schema import validate_instance
from src.mch.static import solve_static

DATA = Path(__file__).resolve().parents[1] / "data" / "processed"
HAVE = (DATA / "districts.csv").exists()


@unittest.skipUnless(HAVE, "run tools/build_data.py first")
class TestCsvData(unittest.TestCase):
    def test_valid(self):
        inst = load_instance()
        self.assertEqual(validate_instance(inst), [])
        self.assertEqual(len(inst.districts), 12)
        self.assertEqual(len(inst.candidate_sites()), 8)

    def test_calibration_peak(self):
        """峰值日全城合计应等于观测峰值周日均 561.3。"""
        inst = load_instance(scenario="base")
        totals = {day: sum(inst.demand[(d.id, day)] for d in inst.districts) for day in range(inst.horizon_days)}
        peak = max(totals.values())
        self.assertAlmostEqual(peak, 561.3, delta=1.0)

    def test_access_gap_present(self):
        inst = load_instance()
        gap = access_gap(inst)
        self.assertGreater(len(gap["zero_access_districts"]), 0)

    def test_solve_on_csv(self):
        inst = load_instance()
        sol = solve_static(inst, 3)
        self.assertEqual(len(sol.chosen), 3)
        self.assertLessEqual(sol.metrics["unmet_total"], sol.metrics["demand_total"] + 1e-6)


if __name__ == "__main__":
    unittest.main()
