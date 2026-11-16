"""Q5 五年分期与触发规则。

[EXT-13] 现为规则式：p_t 由未满足率触发。可换成动态规划/最优控制。
"""
from __future__ import annotations

from typing import Dict, List

from .schema import Instance
from .static import solve_static


def five_year_plan(inst: Instance, p_start: int = 2, p_max: int = 8,
                   unmet_trigger: float = 0.25, **kw) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    p = p_start
    for year in range(2027, 2032):
        sol = solve_static(inst, p, **kw)
        rows.append({"year": year, "hubs": p,
                     "unmet_total": sol.metrics["unmet_total"],
                     "coverage_rate": sol.metrics["coverage_rate"],
                     "worst_unmet_ratio": sol.metrics["worst_unmet_ratio"],
                     "trigger_add_hub": bool(sol.metrics["worst_unmet_ratio"] > unmet_trigger)})
        if sol.metrics["worst_unmet_ratio"] > unmet_trigger and p < p_max:
            p += 1
    return rows
