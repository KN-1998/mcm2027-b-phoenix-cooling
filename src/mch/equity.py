"""公平度量。

本题最容易丢分的地方：只报平均值。至少同时报
  1) Gini（覆盖率的分布不均）
  2) 最差区未满足率 max_i U_i/D_i
  3) 高需求区的加权覆盖率
[EXT-08] 可加入 Atkinson 指数、Theil、分位数比。
"""
from __future__ import annotations

from typing import Dict, List


def gini(values: List[float]) -> float:
    xs = sorted(v for v in values if v is not None)
    n = len(xs)
    if n == 0 or sum(xs) == 0:
        return 0.0
    cum = 0.0
    for i, x in enumerate(xs, 1):
        cum += i * x
    return round((2 * cum) / (n * sum(xs)) - (n + 1) / n, 6)


def worst_unmet_ratio(demand: Dict[str, float], served: Dict[str, float]) -> float:
    ratios = []
    for k, v in demand.items():
        if v > 0:
            ratios.append((v - served.get(k, 0.0)) / v)
    return round(max(ratios), 6) if ratios else 0.0


def coverage_by_district(demand: Dict[str, float], served: Dict[str, float]) -> Dict[str, float]:
    return {k: (served.get(k, 0.0) / v if v > 0 else 1.0) for k, v in demand.items()}


def equity_summary(demand: Dict[str, float], served: Dict[str, float]) -> Dict[str, float]:
    cov = coverage_by_district(demand, served)
    covs = list(cov.values())
    return {
        "coverage_min": round(min(covs), 6) if covs else 0.0,
        "coverage_mean": round(sum(covs) / len(covs), 6) if covs else 0.0,
        "gini_coverage": gini(covs),
        "worst_unmet_ratio": worst_unmet_ratio(demand, served),
    }
