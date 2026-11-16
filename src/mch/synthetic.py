"""合成算例生成器：12 个规划区 × 8 个候选点。

题面明确允许构造合成网络，但要求「明确记录生成规则」——本文件就是那份规则。
[EXT-04] 换成真实数据时：实现 loaders.load_real_instance()，保持 Instance 结构不变。
"""
from __future__ import annotations

import math
import random
from typing import Dict, Tuple

from .schema import (CANDIDATE, COOLING, HYDRATION, RESPITE, District, Instance,
                     Site)

# 12 个区：名称借用 Phoenix urban village 的风格，但**不是官方区界**（题面虚构）
DISTRICT_NAMES = [
    "Central City", "Encanto", "Alhambra", "Camelback East", "Deer Valley",
    "Desert View", "Estrella", "Laveen", "Maryvale", "North Gateway",
    "Paradise Valley", "South Mountain",
]

# 8 个候选点：模拟位置（题面虚构），分布在不同区
CANDIDATE_SPEC = [
    ("MCH-1", "Central City", 0), ("MCH-2", "Encanto", 1),
    ("MCH-3", "Maryvale", 8), ("MCH-4", "South Mountain", 11),
    ("MCH-5", "Camelback East", 3), ("MCH-6", "Deer Valley", 4),
    ("MCH-7", "Laveen", 7), ("MCH-8", "Desert View", 5),
]


def make_districts(seed: int = 2027) -> list:
    rng = random.Random(seed)
    out = []
    for idx, name in enumerate(DISTRICT_NAMES):
        # 人口 45k-180k，与 Phoenix 村级规模同量级
        pop = rng.randint(45_000, 180_000)
        # 脆弱性维度：与真实城市分布同向（低收入区往往树冠少、无车比例高）
        income = rng.choice([38_000, 45_000, 52_000, 61_000, 74_000, 92_000, 110_000])
        no_veh = max(0.02, min(0.35, (110_000 - income) / 300_000 + rng.uniform(-0.03, 0.03)))
        canopy = max(0.02, min(0.45, income / 400_000 + rng.uniform(-0.05, 0.05)))
        pct65 = max(0.06, min(0.30, rng.uniform(0.08, 0.26)))
        # 热暴露：与树冠负相关，加噪
        heat = max(0.05, min(0.99, 0.85 - 1.2 * canopy + rng.uniform(-0.08, 0.08)))
        out.append(District(
            id=f"D{idx+1:02d}", name=name, population=pop, pct_65plus=round(pct65, 3),
            pct_no_vehicle=round(no_veh, 3), median_income=float(income),
            canopy_pct=round(canopy, 3), heat_exposure_index=round(heat, 3),
        ))
    return out


def make_sites(districts: list) -> list:
    """既有网络（按 Phoenix 实际结构简化）+ 8 个候选移动枢纽点。"""
    by_name = {d.name: d for d in districts}
    sites = []
    # 既有：每个区 1 个冷却中心（借图书馆）——数量级参考 2025 年的 17 个市图书馆
    for i, d in enumerate(districts[:8]):
        sites.append(Site(id=f"C{i+1:02d}", name=f"{d.name} Cooling Center", kind=COOLING,
                          district_id=d.id, lat=33.45 + 0.02 * i, lon=-112.07 + 0.02 * i,
                          capacity=0, open_hour=9.0, close_hour=17.0, source="SCENARIO"))
    # 既有：4 个饮水站（不可当冷却容量）
    for i, d in enumerate(districts[8:12]):
        sites.append(Site(id=f"H{i+1:02d}", name=f"{d.name} Hydration Station", kind=HYDRATION,
                          district_id=d.id, lat=33.40 + 0.02 * i, lon=-112.10 + 0.02 * i,
                          capacity=0, open_hour=10.0, close_hour=16.0, source="SCENARIO"))
    # 1 个 24/7 避暑中心（对应 Phoenix 的 24/7 respite）
    sites.append(Site(id="R01", name="24/7 Respite Center", kind=RESPITE,
                      district_id=districts[0].id, lat=33.448, lon=-112.074,
                      capacity=120, open_hour=0.0, close_hour=24.0, source="SCENARIO"))
    # 8 个候选 MCH
    for sid, dname, _ in CANDIDATE_SPEC:
        d = by_name[dname]
        sites.append(Site(id=sid, name=f"{dname} MCH Candidate", kind=CANDIDATE,
                          district_id=d.id, lat=d.lat or 33.45, lon=d.lon or -112.07,
                          capacity=250, open_hour=9.0, close_hour=19.0, source="SCENARIO"))
    return sites


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def make_access(districts: list, sites: list) -> Dict[Tuple[str, str], float]:
    """[EXT-05] 现状：直线距离 × 模式速度（分钟）。
              换成真实 GTFS/路网时：只替换本函数，下游只认 minutes。
    """
    mode_speed_kmh = {"walk": 4.8, "transit": 15.0, "drive": 30.0}
    out = {}
    for d in districts:
        for s in sites:
            km = _haversine_km(d.lat or 33.45 + (hash(d.id) % 40 - 20) / 1000.0,
                               d.lon or -112.07 + (hash(d.id) % 30 - 15) / 1000.0,
                               s.lat, s.lon)
            # 默认按步行（2025 运营报告：63% 步行/骑行到达）
            out[(d.id, s.id)] = round(km / mode_speed_kmh["walk"] * 60.0, 1)
    return out


def build_instance(seed: int = 2027, horizon_days: int = 7) -> Instance:
    districts = make_districts(seed)
    sites = make_sites(districts)
    access = make_access(districts, sites)
    # 需求先记 0，由 demand.py 填充（保持职责单一）
    return Instance(districts=districts, sites=sites, access=access, demand={},
                    horizon_days=horizon_days,
                    meta={"generator": "synthetic.build_instance", "seed": seed,
                          "note": "12 districts x 8 candidates are CONTEST FICTIONS, not official Phoenix areas"})
