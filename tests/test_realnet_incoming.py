from __future__ import annotations

import tempfile
import shutil
import unittest
from pathlib import Path

from src.mch.loaders import load_instance
from src.mch.incoming import apply_incoming

DATA = Path(__file__).resolve().parents[1] / "data" / "processed"
HAVE = (DATA / "districts.csv").exists()
MAG = Path(__file__).resolve().parents[1] / "资料" / "02_降温网络" / "MAG" / "phoenix_2026_public_view_sites.csv"


@unittest.skipUnless(MAG.exists(), "MAG snapshot not present")
class TestRealNetwork(unittest.TestCase):
    def test_mag_sites_loaded(self):
        from src.mch.realnet import load_mag_sites
        sites = load_mag_sites()
        self.assertGreater(len(sites), 30)
        self.assertTrue(all(s.lat and s.lon for s in sites))
        kinds = {s.kind for s in sites}
        self.assertIn("cooling", kinds)

    @unittest.skipUnless(HAVE, "run tools/build_data.py first")
    def test_instance_has_real_and_candidates(self):
        from src.mch.realnet import build_real_instance
        inst = build_real_instance()
        self.assertEqual(len(inst.candidate_sites()), 8)
        self.assertGreaterEqual(len(inst.sites), 40)
        self.assertEqual(inst.meta.get("network"), "MAG_REAL")


@unittest.skipUnless(HAVE, "run tools/build_data.py first")
class TestIncomingMapping(unittest.TestCase):
    def test_income_and_unmatched(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "acs_districts.csv").write_text(
                "district_id,median_income_usd,unknown_col\nD01,20000,x\nZZ,1,1\n", encoding="utf-8")
            (tmp / "sites_mag.csv").write_text(
                "site_id,lat,lon\nC01,35,-113\nREAL_NEW,33,-112\n", encoding="utf-8")
            inst = apply_incoming(load_instance(), tmp)
            d1 = next(d for d in inst.districts if d.id == "D01")
            self.assertAlmostEqual(d1.median_income, 20000.0)
            log = inst.meta["incoming"]
            self.assertIn("ZZ", log["unmatched"]["districts"])
            self.assertIn("REAL_NEW", log["unmatched"]["sites"])
            self.assertIn("unknown_col", log["ignored_columns"]["districts"])
            self.assertIn("demand", " ".join(log["rebuild_needed"]))
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
