"""用 MAG 公布的 2026 真实站点清单构建实例（现有网络），候选 MCH 仍来自题面。

与 `synthetic.py` 的区别：**固定网络是真实的**（名称/坐标/类型/营业时间来自
`资料/02_降温网络/MAG/phoenix_2026_public_view_sites.csv`），只有 12 个规划区与
8 个候选 MCH 是题面/合成。
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Dict, List, Tuple

from .schema import COOLING, DONATION, HYDRATION, RESPITE, District, Instance, Site

ROOT = Path(__file__).resolve().parents[2]
MAG_CSV = ROOT / "资料" / "02_降温网络" / "MAG" / "phoenix_2026_public_view_sites.csv"

KIND_MAP = {
    "cooling center": COOLING,
    "hydration station": HYDRATION,
    "respite center": RESPITE,
    "donation site": DONATION,
}

SPEED = {"walk_min": 4.8, "transit_min": 15.0, "drive_min": 30.0}
DETOUR = 1.35
WAIT = 10.0


def _hav(a, b, c, d):
    R0 = 6371.0
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = p2 - p1, math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R0 * math.asin(math.sqrt(x))


def _hours(row: dict) -> Tuple[float, float]:
    """从周一到周五的开/关门时间取代表值；解析失败按 9-17。"""
    def parse(t):
        t = (t or "").strip().upper().replace(" ", "")
        if not t:
            return None
        pm = "PM" in t
        t = t.replace("AM", "").replace("PM", "")
        hh, _, mm = t.partition(":")
        try:
            h = int(hh); m = int(mm) if mm else 0
        except ValueError:
            return None
        if pm and h != 12:
            h += 12
        if not pm and h == 12:
            h = 0
        return h + m / 60.0
    opens = [parse(row.get(f"{d}Open")) for d in ("Monday","Tuesday","Wednesday","Thursday","Friday")]
    closes = [parse(row.get(f"{d}Close")) for d in ("Monday","Tuesday","Wednesday","Thursday","Friday")]
    o = min([x for x in opens if x is not None], default=9.0)
    c = max([x for x in closes if x is not None], default=17.0)
    if c <= o:
        c = min(24.0, o + 8.0)
    return float(o), float(c)


def load_mag_sites(path: Path | None = None) -> List[Site]:
    p = Path(path) if path else MAG_CSV
    rows = list(csv.DictReader(p.open(encoding="utf-8-sig")))
    out: List[Site] = []
    for r in rows:
        kind = KIND_MAP.get((r.get("HeatRelief_Type") or "").strip().lower())
        if kind is None:
            continue
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except (TypeError, ValueError):
            continue
        o, c = _hours(r)
        out.append(Site(id=f"MAG{r['OBJECTID']:>04s}", name=(r.get("Location") or "").strip(),
                        kind=kind, district_id="", lat=lat, lon=lon,
                        capacity=50 if kind == COOLING else 0,
                        open_hour=o, close_hour=c,
                        source="MAG_REAL",
                        extra={"organization": (r.get("Organization") or "").strip(),
                               "address": (r.get("Address") or "").strip(),
                               "snapshot": r.get("source_snapshot_date")}))
    return out


def build_real_instance(access_mode: str = "walk_min", scenario: str = "base",
                        horizon_days: int = 7) -> Instance:
    from .loaders import load_instance
    base = load_instance(access_mode=access_mode, scenario=scenario, horizon_days=horizon_days)
    districts = base.districts
    fixed = load_mag_sites()
    cands = base.candidate_sites()
    # 每个真实站点归到最近的规划区
    for s in fixed:
        s.district_id = min(districts, key=lambda d: _hav(d.lat, d.lon, s.lat, s.lon)).id
    sites = fixed + cands

    access: Dict[Tuple[str, str], float] = {}
    for d in districts:
        for s in sites:
            km = _hav(d.lat, d.lon, s.lat, s.lon) * DETOUR
            if access_mode == "walk_min":
                t = km / SPEED["walk_min"] * 60
            elif access_mode == "transit_min":
                t = km / SPEED["transit_min"] * 60 + WAIT
            else:
                t = km / SPEED["drive_min"] * 60
            access[(d.id, s.id)] = round(t, 1)

    return Instance(districts=districts, sites=sites, access=access,
                    demand=dict(base.demand), horizon_days=horizon_days,
                    meta={**base.meta, "network": "MAG_REAL",
                          "n_fixed": len(fixed), "n_candidates": len(cands),
                          "note": "fixed network from MAG 2026 public view; districts and candidates are contest/synthetic"})
