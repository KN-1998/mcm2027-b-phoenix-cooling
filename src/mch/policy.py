"""Q5 五年分期：只在**边际收益足够**时增购枢纽。

修正点：原规则"最差区未满足率超阈值就加一台"会在结构性不可达区上无限加购。
改为：加购只有当 p+1 相对 p 的未满足量下降超过 min_gain（人次/日）或相对于当前未满足的 min_ratio 时才触发。
"""
from __future__ import annotations

from typing import Dict, List

from .schema import Instance
from .static import solve_static


def five_year_plan(inst: Instance, p_start: int = 2, p_max: int = 8,
                   unmet_trigger: float = 0.25, min_gain: float = 5.0,
                   min_ratio: float = 0.02, **kw) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    p = p_start
    for year in range(2027, 2032):
        cur = solve_static(inst, p, **kw)
        nxt = solve_static(inst, p + 1, **kw) if p < p_max else None
        gain = (cur.metrics["unmet_total"] - nxt.metrics["unmet_total"]) if nxt else 0.0
        rel = (gain / cur.metrics["unmet_total"]) if cur.metrics["unmet_total"] > 0 else 0.0
        add = bool(nxt and gain >= min_gain and rel >= min_ratio)
        rows.append({"year": year, "hubs": p,
                     "unmet_total": cur.metrics["unmet_total"],
                     "coverage_rate": cur.metrics["coverage_rate"],
                     "worst_unmet_ratio": cur.metrics["worst_unmet_ratio"],
                     "next_hub_gain": round(gain, 2),
                     "add_hub": add})
        if add:
            p += 1
    return rows
