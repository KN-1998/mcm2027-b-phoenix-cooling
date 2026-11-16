"""未满足需求的归因：到底是"没得去"、"去了装不下"，还是"车不够"。

判据（逐区）：
  1. no_access  : 在给定阈值内没有任何可服务室内站点 → 加枢纽也救不了（除非加在可达范围内）
  2. capacity   : 有可达站点，但这些站点的日容量之和 < 当日需求
  3. selection  : 有可达且有容量，但本次选点没覆盖到（可以靠换 p 或换位置改善）
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .schema import COOLING, RESPITE, Instance
from .static import Solution

INDOOR = (COOLING, RESPITE, "candidate_mch")


def feasible_sites(inst: Instance, district_id: str, max_minutes: float,
                   include_candidates: bool = True) -> List[str]:
    kinds = INDOOR if include_candidates else (COOLING, RESPITE)
    out = []
    for s in inst.sites:
        if s.kind not in kinds:
            continue
        t = inst.access.get((district_id, s.id))
        if t is not None and t <= max_minutes:
            out.append(s.id)
    return out


def attribute_unmet(inst: Instance, sol: Solution, day: int = 0,
                    max_minutes: float = 30.0, capacity: float = 250.0,
                    active_sites: Optional[Sequence[str]] = None) -> Dict[str, object]:
    rows = []
    for d in inst.districts:
        dem = inst.demand.get((d.id, day), 0.0)
        served = sol.served.get((d.id, day), 0.0)
        unmet = max(0.0, dem - served)
        feas = feasible_sites(inst, d.id, max_minutes)
        if active_sites is not None:
            feas = [x for x in feas if x in set(active_sites)]
        if unmet <= 1e-9:
            reason = "served"
        elif not feas:
            reason = "no_access"
        else:
            cap_sum = 0.0
            for sid in feas:
                s = next(x for x in inst.sites if x.id == sid)
                cap_sum += (s.capacity if s.capacity and s.capacity > 0 else capacity)
            reason = "capacity" if cap_sum < dem else "selection"
        rows.append({"district_id": d.id, "demand": round(dem, 2), "served": round(served, 2),
                     "unmet": round(unmet, 2), "feasible_sites": len(feas), "reason": reason})
    totals: Dict[str, float] = {}
    for r in rows:
        totals[r["reason"]] = round(totals.get(r["reason"], 0.0) + r["unmet"], 2)
    return {"day": day, "max_minutes": max_minutes, "rows": rows, "by_reason": totals}
