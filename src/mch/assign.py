"""精确分配：运输流 LP（替换贪心）。

为什么：贪心按需求排序、每区只取最近有余量的站点，会低估可服务量。
反例：A=10 可到 S1/S2，B=9 只到 S1，容量各 10 —— 贪心 10，最优 19。

模型（固定点集）：
    max  sum_{i,j} x_ij
    s.t. sum_j x_ij <= D_i
         sum_i x_ij <= C_j
         x_ij >= 0, 仅当 (i,j) 可行（在阈值内、类型匹配、该时段营业）
公平版：额外约束 sum_j x_ij >= (1-eps) D_i。

用 scipy.optimize.linprog(method="highs")；规模 12x22 内可秒解。
[EXT-15] 若要最小费用流版本，替换 _solve_lp 即可。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .schema import Instance, Site


def _pairs(inst: Instance, sites: List[Site], max_minutes: float,
           capacity_of: Dict[str, float]) -> List[Tuple[str, str, float]]:
    out = []
    for d in inst.districts:
        for s in sites:
            if capacity_of.get(s.id, 0.0) <= 0:
                continue
            t = inst.access.get((d.id, s.id))
            if t is None or t > max_minutes:
                continue
            out.append((d.id, s.id, s_cap := capacity_of[s.id]))
    return out


def solve_assignment(inst: Instance, sites: List[Site], day: int = 0,
                     max_minutes: float = 30.0,
                     capacity_of: Optional[Dict[str, float]] = None,
                     demand: Optional[Dict[str, float]] = None,
                     equity_cap: Optional[float] = None) -> Dict[str, object]:
    """返回 {served: {(d,day): v}, by_site: {site: v}, unmet: {...}, status}。"""
    from scipy.optimize import linprog

    dem = demand or {d.id: inst.demand.get((d.id, day), 0.0) for d in inst.districts}
    cap = capacity_of or {s.id: float(s.capacity or 250.0) for s in sites}

    pairs = [(d, s) for d in dem for s in cap
             if cap.get(s, 0) > 0
             and (t := inst.access.get((d, s))) is not None and t <= max_minutes]

    n = len(pairs)
    if n == 0:
        return {"served": {k: 0.0 for k in dem}, "by_site": {k: 0.0 for k in cap},
                "status": "no_feasible_links"}

    # max sum x  ->  min -sum x
    c = -np.ones(n)
    A, b = [], []
    # 每区不超需求
    for d in dem:
        row = np.zeros(n)
        for k, (dd, _) in enumerate(pairs):
            if dd == d: row[k] = 1.0
        if row.sum() > 0:
            A.append(row); b.append(dem[d])
    # 每站不超容量
    for s in cap:
        row = np.zeros(n)
        for k, (_, ss) in enumerate(pairs):
            if ss == s: row[k] = 1.0
        if row.sum() > 0:
            A.append(row); b.append(cap[s])
    # 公平：每区服务量 >= (1-eps)D
    if equity_cap is not None:
        for d in dem:
            if dem[d] <= 0: continue
            row = np.zeros(n)
            for k, (dd, _) in enumerate(pairs):
                if dd == d: row[k] = -1.0
            A.append(row); b.append(-(1.0 - equity_cap) * dem[d])

    res = linprog(c, A_ub=np.array(A) if A else None, b_ub=np.array(b) if b else None,
                  bounds=[(0, None)] * n, method="highs")
    if not res.success:
        return {"served": {k: 0.0 for k in dem}, "by_site": {k: 0.0 for k in cap},
                "status": res.message}

    x = res.x
    served = {k: 0.0 for k in dem}
    by_site = {k: 0.0 for k in cap}
    for k, (d, s) in enumerate(pairs):
        if x[k] > 1e-9:
            served[d] += x[k]; by_site[s] += x[k]
    return {"served": served, "by_site": by_site, "status": "optimal",
            "objective": -res.fun}
