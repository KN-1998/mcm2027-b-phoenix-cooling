"""Q2 静态选址-分配。

主算法：**枚举候选组合 + 需求优先的容量约束贪心分配**。
规模：8 选 p，C(8,p) ≤ 70，完全可枚举；因此结果对小算例是**精确最优**（在给定分配规则下）。

[EXT-10] 需要严格联合最优（同时优化选址与分配）时，用 solve_static_milp()：
         已留接口，依赖 pulp/ortools，未安装时自动跳过，不影响主流程。
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import demand as demand_mod
from .equity import equity_summary
from .metrics import cost_breakdown, totals, unmet_by_district, utilization
from .schema import COOLING, Instance, Site


@dataclass
class Solution:
    chosen: List[str]
    served: Dict[Tuple[str, int], float] = field(default_factory=dict)
    served_by_site: Dict[str, float] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    day: int = 0


def _active_sites(inst: Instance, chosen: Sequence[str], exclude: Sequence[str] = ()) -> List[Site]:
    ex = set(exclude)
    sites = [s for s in inst.fixed_sites() if s.id not in ex and s.kind in (COOLING, "respite")]
    sites += [s for s in inst.candidate_sites() if s.id in chosen]
    return sites


def _assign(inst: Instance, sites: List[Site], day: int, max_minutes: float,
            capacity: float, weights: Optional[Dict[str, float]] = None) -> Solution:
    """需求优先贪心：按 (需求 × 权重) 从大到小分配，每区取最近且有余量的站点。"""
    weights = weights or {}
    dem = {d.id: inst.demand.get((d.id, day), 0.0) for d in inst.districts}
    order = sorted(inst.districts, key=lambda d: -(dem[d.id] * weights.get(d.id, 1.0)))

    remaining = {}
    for s in sites:
        cap = s.capacity if s.capacity and s.capacity > 0 else capacity
        remaining[s.id] = float(cap)

    served: Dict[Tuple[str, int], float] = {}
    by_site: Dict[str, float] = {s.id: 0.0 for s in sites}

    for d in order:
        need = dem[d.id]
        if need <= 0:
            served[(d.id, day)] = 0.0
            continue
        opts = []
        for s in sites:
            t = inst.access.get((d.id, s.id))
            if t is None or t > max_minutes or remaining[s.id] <= 0:
                continue
            opts.append((t, s))
        opts.sort(key=lambda x: x[0])
        left = need
        for t, s in opts:
            if left <= 0:
                break
            take = min(left, remaining[s.id])
            if take <= 0:
                continue
            remaining[s.id] -= take
            by_site[s.id] += take
            left -= take
        served[(d.id, day)] = need - left

    srv = {d.id: served.get((d.id, day), 0.0) for d in inst.districts}
    m = totals(dem, srv)
    m.update(equity_summary(dem, srv))
    util = utilization(by_site, {s.id: (s.capacity or capacity) for s in sites})
    m["utilization_mean"] = round(sum(util.values()) / len(util), 4) if util else 0.0
    return Solution(chosen=[s.id for s in sites if s.kind == "candidate_mch"],
                    served=served, served_by_site=by_site, metrics=m, day=day)


def solve_static(inst: Instance, p: int, max_minutes: float = 30.0,
                 capacity: float = 250.0, day: int = 0,
                 exclude_sites: Sequence[str] = (),
                 weights: Optional[Dict[str, float]] = None) -> Solution:
    """返回 p 个候选点的最优组合（按 未满足总量 → Gini → 最差区 字典序）。"""
    cands = [s.id for s in inst.candidate_sites() if s.id not in set(exclude_sites)]
    if p > len(cands):
        raise ValueError(f"p={p} 超过候选点数 {len(cands)}")

    best: Optional[Solution] = None
    for combo in itertools.combinations(cands, p):
        sol = _assign(inst, _active_sites(inst, combo, exclude_sites), day, max_minutes,
                      capacity, weights)
        key = (sol.metrics["unmet_total"], sol.metrics["gini_coverage"],
               sol.metrics["worst_unmet_ratio"])
        if best is None or key < (best.metrics["unmet_total"], best.metrics["gini_coverage"],
                                  best.metrics["worst_unmet_ratio"]):
            best = sol
    assert best is not None
    return best


def sweep_p(inst: Instance, pmax: int = 8, **kw) -> List[Dict[str, float]]:
    """Q2 的边际收益曲线：p 从 0 到 pmax。"""
    rows = []
    for p in range(0, pmax + 1):
        sol = solve_static(inst, p, **kw) if p > 0 else _assign(
            inst, _active_sites(inst, ()), kw.get("day", 0),
            kw.get("max_minutes", 30.0), kw.get("capacity", 250.0), kw.get("weights"))
        row = {"p": p}
        row.update(sol.metrics)
        rows.append(row)
    return rows


def solve_static_milp(*args, **kwargs):  # pragma: no cover - 可选路径
    """[EXT-10] MILP 接口占位。

    建议实现：变量 y_j ∈ {0,1} 选点、x_ij ≥ 0 分配；
    目标 min Σ_i U_i；约束 Σ_j y_j ≤ p、Σ_i x_ij ≤ C y_j、x_ij ≤ D_i a_ij、U_i = D_i − Σ_j x_ij。
    公平：加 max_i U_i/D_i ≤ ε 或加权目标。
    """
    raise NotImplementedError("MILP 后端未实现：见 docs/EXTENSION_POINTS.md#EXT-10")
