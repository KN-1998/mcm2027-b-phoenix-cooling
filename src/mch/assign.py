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
                     equity_cap: Optional[float] = None,
                     equity_exempt: Sequence[str] = ()) -> Dict[str, object]:
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
        exempt = set(equity_exempt)
        for d in dem:
            if dem[d] <= 0 or d in exempt: continue   # 物理不可达区不参与 ε 约束
            row = np.zeros(n)
            for k, (dd, _) in enumerate(pairs):
                if dd == d: row[k] = -1.0
            A.append(row); b.append(-(1.0 - equity_cap) * dem[d])

    res = linprog(c, A_ub=np.array(A) if A else None, b_ub=np.array(b) if b else None,
                  bounds=[(0, None)] * n, method="highs")
    if not res.success:
        return {"served": {k: 0.0 for k in dem}, "by_site": {k: 0.0 for k in cap},
                "status": "infeasible" if "infeasible" in (res.message or "").lower() else str(res.message)}

    x = res.x
    served = {k: 0.0 for k in dem}
    by_site = {k: 0.0 for k in cap}
    for k, (d, s) in enumerate(pairs):
        if x[k] > 1e-9:
            served[d] += x[k]; by_site[s] += x[k]
    return {"served": served, "by_site": by_site, "status": "optimal",
            "objective": -res.fun}

def solve_assignment_maxmin(inst: Instance, sites, day: int = 0,
                            max_minutes: float = 30.0,
                            capacity_of=None,
                            demand=None,
                            exempt: Sequence[str] = ()):
    """真正的 max-min LP：最小化"最差未满足率" t，再在 t* 下最大化总服务量。

    变量 [x_ij..., t]；约束 sum_j x_ij + D_i t >= D_i（即 U_i/D_i <= t）。
    """
    from scipy.optimize import linprog

    dem = demand or {d.id: inst.demand.get((d.id, day), 0.0) for d in inst.districts}
    cap = capacity_of or {s.id: float(s.capacity or 250.0) for s in sites}
    pairs = [(d, s) for d in dem if dem[d] > 0 for s in cap
             if cap.get(s, 0) > 0
             and (t := inst.access.get((d, s))) is not None and t <= max_minutes]
    if not pairs:
        return {"served": {k: 0.0 for k in dem}, "by_site": {k: 0.0 for k in cap},
                "status": "no_feasible_links", "t": 1.0}
    n = len(pairs)
    ex = set(exempt)

    # 阶段 1：min t
    c = np.zeros(n + 1); c[-1] = 1.0
    A, b = [], []
    for d in dem:
        if dem[d] <= 0 or d in ex: continue
        row = np.zeros(n + 1); row[-1] = dem[d]
        for k, (dd, _) in enumerate(pairs):
            if dd == d: row[k] = 1.0
        A.append(-row); b.append(-dem[d])
    for s in cap:
        row = np.zeros(n + 1)
        for k, (_, ss) in enumerate(pairs):
            if ss == s: row[k] = 1.0
        if row.sum() > 0:
            A.append(row); b.append(cap[s])
    # 需求上限：不能把一个区的服务量算超其需求（否则 t 可被"多服务"压低）
    for d in dem:
        if dem[d] <= 0: continue
        row = np.zeros(n + 1)
        for k, (dd, _) in enumerate(pairs):
            if dd == d: row[k] = 1.0
        if row.sum() > 0:
            A.append(row); b.append(dem[d])
    bounds = [(0, None)] * n + [(0, 1)]
    r1 = linprog(c, A_ub=np.array(A), b_ub=np.array(b), bounds=bounds, method="highs")
    if not r1.success:
        return {"served": {k: 0.0 for k in dem}, "by_site": {k: 0.0 for k in cap},
                "status": "infeasible", "t": 1.0}
    tstar = float(r1.x[-1])

    # 阶段 2：在 t* 下最大化总服务
    c2 = np.zeros(n + 1); c2[:n] = -1.0
    A2, b2 = list(A), list(b)
    A2.append(np.array([0.0] * n + [1.0])); b2.append(tstar + 1e-9)
    r2 = linprog(c2, A_ub=np.array(A2), b_ub=np.array(b2), bounds=bounds, method="highs")
    if not r2.success:
        return {"served": {k: 0.0 for k in dem}, "by_site": {k: 0.0 for k in cap},
                "status": "stage2_failed", "t": tstar}

    x = r2.x[:n]
    served = {k: 0.0 for k in dem}; by_site = {k: 0.0 for k in cap}
    for k, (d, s) in enumerate(pairs):
        if x[k] > 1e-9:
            served[d] += x[k]; by_site[s] += x[k]
    return {"served": served, "by_site": by_site, "status": "optimal", "t": tstar,
            "objective": -r2.fun}
