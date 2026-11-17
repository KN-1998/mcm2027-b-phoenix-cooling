from __future__ import annotations

import unittest
from pathlib import Path

from src.exp.common import parse_list, worst_excluding
from src.mch.loaders import load_instance

DATA = Path(__file__).resolve().parents[1] / "data" / "processed"
HAVE = (DATA / "districts.csv").exists()


class TestCommonHelpers(unittest.TestCase):
    def test_parse_list(self):
        self.assertEqual(parse_list("1,2,3", int), [1, 2, 3])
        self.assertEqual(parse_list("", float), [])
        self.assertEqual(parse_list("0.5", float), [0.5])


@unittest.skipUnless(HAVE, "run tools/build_data.py first")
class TestSweepConsistency(unittest.TestCase):
    def test_ushare_monotone(self):
        """无家可归者比例越高，未满足量不应下降（夜间需求更高）。"""
        from src.mch.static import solve_static
        vals = []
        for us in (0.3, 0.5, 0.7):
            inst = load_instance()
            inst.meta["unsheltered_share"] = us
            vals.append(solve_static(inst, 3).metrics["unmet_total"])
        self.assertLessEqual(vals[0], vals[1] + 1e-6)
        self.assertLessEqual(vals[1], vals[2] + 1e-6)

    def test_worst_excluding_ignores_structural(self):
        from src.mch.static import solve_static
        inst = load_instance()
        sol = solve_static(inst, 3)
        self.assertLessEqual(worst_excluding(inst, sol, ["D08"]), 1.0)


if __name__ == "__main__":
    unittest.main()
