"""需求模型 D(i,t)。

公式（可替换，见 [EXT-06]）：
    D(i,t) = population_i * rate_base * exposure_i * vuln_i * day_factor(t)
其中 vuln_i 由 65+ 比例、无车比例、收入反向归一化加权得到。
标定：用 2025 逐周报告的总到访量（人次数）做总量比例校准。
"""
from __future__ import annotations

from typing import Dict, List

from .schema import District, Instance

# 每人每热日的基线"想去降温空间"的比率（人次/人/日），
# [EXT-06] 该值没有直接观测，属于 ASSUME；用总到访量反推并做敏感性。
RATE_BASE = 0.004

DAY_FACTOR = [1.00, 1.05, 1.18, 1.30, 1.22, 1.08, 0.95]  # 7 天热浪曲线（ASSUME）


def vulnerability(d: District) -> float:
    """归一化脆弱性 0-1：65+、无车、低收入三项等权。

    [EXT-07] 加入语言、独居、慢性病等时，在此改权重并重跑敏感性。
    """
    income_term = max(0.0, min(1.0, (110_000 - d.median_income) / 72_000))
    return round((d.pct_65plus / 0.30 + d.pct_no_vehicle / 0.35 + income_term) / 3.0, 4)


def district_day_demand(d: District, day: int) -> float:
    v = vulnerability(d)
    return RATE_BASE * d.population * (0.4 + 0.6 * d.heat_exposure_index) * (0.6 + 0.8 * v) * DAY_FACTOR[day % 7]


def fill_demand(inst: Instance, rate_base: float = RATE_BASE) -> Instance:
    inst.demand = {}
    for d in inst.districts:
        for day in range(inst.horizon_days):
            inst.demand[(d.id, day)] = district_day_demand(d, day)
    return inst


def calibrate(inst: Instance, target_total_daily: float) -> Instance:
    """把某一天的总需求缩放到目标总量（用于对齐真实到访人次量级）。"""
    base = sum(inst.demand[(d.id, 0)] for d in inst.districts) or 1.0
    k = target_total_daily / base
    inst.demand = {k_: v * k for k_, v in inst.demand.items()}
    inst.meta["demand_scale"] = k
    return inst
