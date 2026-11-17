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
from .hours import PERIODS, availability_table, capacity_in_period, split_demand, split_demand_mixed
from .assign import (solve_assignment, solve_assignment_flow,
                     solve_assignment_periods)
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


def _effective_capacity(inst: Instance, sites: List[Site], capacity: float,
                       availability: Optional[Dict[str, float]] = None,
                       downtime: Optional[Dict[str, float]] = None,
                       override: Optional[float] = None) -> Dict[str, float]:
    """逐站有效容量。

    优先级：站点自带 capacity > 0 用它，否则用 capacity（CLI 缺省）。
    再乘开放时段份额与停服折减（均为 1.0 表示不受影响）。
    """
    avail = availability if availability is not None else availability_table(inst)
    out = {}
    for s in sites:
        if override is not None:
            base = float(override)                       # 显式覆盖（容量敏感性分析用）
        elif s.capacity and s.capacity > 0:
            base = float(s.capacity)                     # 站点自带（CSV/题面）
        else:
            base = float(capacity)                       # 缺省
        out[s.id] = base * float(avail.get(s.id, 1.0)) * float((downtime or {}).get(s.id, 1.0))
    return out


def _assign(inst: Instance, sites: List[Site], day: int, max_minutes: float,
            capacity: float, weights: Optional[Dict[str, float]] = None,
            availability: Optional[Dict[str, float]] = None,
            downtime: Optional[Dict[str, float]] = None,
            override: Optional[float] = None,
            solver: str = "lp",
            mode: str = "period",
            equity_cap: Optional[float] = None,
            equity_exempt: Sequence[str] = ()) -> Solution:
    """需求优先贪心：按 (需求 × 权重) 从大到小分配，每区取最近且有余量的站点。"""
    weights = weights or {}
    dem = {d.id: inst.demand.get((d.id, day), 0.0) for d in inst.districts}
    order = sorted(inst.districts, key=lambda d: -(dem[d.id] * weights.get(d.id, 1.0)))

    dem = {d.id: inst.demand.get((d.id, day), 0.0) for d in inst.districts}

    if mode == "period":
        # P1-2：按时段显式分配。容量 = 日容量 x 该时段营业重叠小时 / 营业时长。
        # 时段拆分由 capacity_in_period 完成，这里不能再乘 available 份额（否则重复折减）
        no_discount = {x.id: 1.0 for x in inst.sites}
        cap_daily = _effective_capacity(inst, sites, capacity, no_discount, downtime, override)
        ushare = float(inst.meta.get("unsheltered_share", 0.5))
        cap_h = {s.id: {h: capacity_in_period(s, cap_daily.get(s.id, 0.0), h) for h in PERIODS}
                 for s in sites}
        dem_h = {d.id: split_demand_mixed(dem[d.id], ushare) for d in inst.districts}
        # A2 修复：跨时段单个 LP，公平约束施加在"日未满足率"上
        out = solve_assignment_periods(inst, sites, day, max_minutes, cap_h, dem_h,
                                       equity_cap=equity_cap, equity_exempt=equity_exempt)
        lp_status = out.get("status", "unknown")
        if out["status"] != "optimal":
            # 不可行时退回无公平约束的可行解，并如实标记（不返回零服务）
            out = solve_assignment_periods(inst, sites, day, max_minutes, cap_h, dem_h)
            lp_status = f"equity_infeasible_fallback:{lp_status}"
        raw = {d.id: out["served"].get(d.id, 0.0) for d in inst.districts}
        by_site = {s.id: out["by_site"].get(s.id, 0.0) for s in sites}
        by_period = {h: round(v, 3) for h, v in out.get("served_by_period", {}).items()}
    else:
        cap_eff = _effective_capacity(inst, sites, capacity, availability, downtime, override)
        if solver == "flow" and equity_cap is None:
            out = solve_assignment_flow(inst, sites, day, max_minutes, cap_eff, dem)
            raw = out["served"]
            by_site = {s.id: out["by_site"].get(s.id, 0.0) for s in sites}
            lp_status = out["status"]
        elif solver == "lp":
            out = solve_assignment(inst, sites, day, max_minutes, cap_eff, dem,
                                   equity_cap=equity_cap, equity_exempt=equity_exempt)
            raw = out["served"]
            by_site = {s.id: out["by_site"].get(s.id, 0.0) for s in sites}
            lp_status = out["status"]
        else:
            raw, by_site, lp_status = _greedy_fill(inst, sites, dem, max_minutes, cap_eff)
        by_period = {}
    served: Dict[Tuple[str, int], float] = {(d, day): raw.get(d, 0.0) for d in dem}

    srv = {d.id: served.get((d.id, day), 0.0) for d in inst.districts}
    m = totals(dem, srv)
    m.update(equity_summary(dem, srv))
    util = utilization(by_site, {s.id: (s.capacity or capacity) for s in sites})
    m["utilization_mean"] = round(sum(util.values()) / len(util), 4) if util else 0.0
    ex = set(equity_exempt or ())
    ratios = [(dem[d.id] - srv.get(d.id, 0.0)) / dem[d.id]
              for d in inst.districts if dem[d.id] > 0 and d.id not in ex]
    m["worst_unmet_ratio_nonexempt"] = round(max(ratios), 6) if ratios else 0.0
    if by_period:
        m["served_by_period"] = by_period
    m["solver_status"] = locals().get("lp_status", "unknown")
    if availability is None:
        m["availability_applied"] = True
    return Solution(chosen=[s.id for s in sites if s.kind == "candidate_mch"],
                    served=served, served_by_site=by_site, metrics=m, day=day)


def _greedy_fill(inst: Instance, sites: List[Site], dem: Dict[str, float],
                 max_minutes: float, cap_eff: Dict[str, float]):
    """旧版贪心分配，仅作对照（已知次优，勿用于主结果）。"""
    order = sorted(inst.districts, key=lambda d: -dem.get(d.id, 0.0))
    remaining = dict(cap_eff)
    raw = {d.id: 0.0 for d in inst.districts}
    by_site = {s.id: 0.0 for s in sites}
    for d in order:
        need = dem.get(d.id, 0.0)
        if need <= 0:
            continue
        opts = sorted((inst.access[(d.id, s.id)], s.id) for s in sites
                      if (d.id, s.id) in inst.access
                      and inst.access[(d.id, s.id)] <= max_minutes
                      and remaining.get(s.id, 0.0) > 0)
        left = need
        for _t, sid in opts:
            if left <= 0:
                break
            take = min(left, remaining[sid])
            remaining[sid] -= take
            by_site[sid] += take
            left -= take
        raw[d.id] = need - left
    return raw, by_site, "greedy"


def solve_static(inst: Instance, p: int, max_minutes: float = 30.0,
                 capacity: float = 250.0, day: int = 0,
                 exclude_sites: Sequence[str] = (),
                 weights: Optional[Dict[str, float]] = None,
                 override: Optional[float] = None,
                 mode: str = "period",
                 solver: str = "lp") -> Solution:
    """返回 p 个候选点的最优组合（按 未满足总量 → Gini → 最差区 字典序）。"""
    cands = [s.id for s in inst.candidate_sites() if s.id not in set(exclude_sites)]
    if p > len(cands):
        raise ValueError(f"p={p} 超过候选点数 {len(cands)}")

    best: Optional[Solution] = None
    for combo in itertools.combinations(cands, p):
        sol = _assign(inst, _active_sites(inst, combo, exclude_sites), day, max_minutes,
                      capacity, weights, override=override, mode=mode, solver=solver)
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
        # B2 修复：p=0 与 p>0 走同一条参数通路
        sol = solve_static(inst, p, **kw) if p > 0 else _assign(
            inst, _active_sites(inst, ()), kw.get("day", 0),
            kw.get("max_minutes", 30.0), kw.get("capacity", 250.0), kw.get("weights"),
            mode=kw.get("mode", "period"), override=kw.get("override"),
            solver=kw.get("solver", "lp"))
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

# ---------------------------------------------------------------------------
# 公平版本（Q2 的核心）：把"最差区"从事后统计变成约束
# ---------------------------------------------------------------------------

def solve_static_fair(inst: Instance, p: int, equity_cap: float = 0.3,
                      max_minutes: float = 30.0, capacity: float = 250.0,
                      day: int = 0, exclude_sites: Sequence[str] = (),
                      weights: Optional[Dict[str, float]] = None,
                      override: Optional[float] = None,
                      mode: str = "period") -> Solution:
    """在 max_i (U_i/D_i) <= equity_cap 的可行组合里，最小化总未满足量。

    若无组合可行，退化为"最小化最差区未满足率"（max-min），并在 metrics 里标记
    equity_cap_met=False —— 这是要如实报告的结论，不是失败。
    """
    cands = [s.id for s in inst.candidate_sites() if s.id not in set(exclude_sites)]
    if p > len(cands):
        raise ValueError("p 超过候选点数")

    feasible = []
    infeasible = []
    for combo in itertools.combinations(cands, p):
        act = _active_sites(inst, combo, exclude_sites)
        # 结构性豁免：在"全部固定站点 + 全部候选点"上一次算出，所有组合共用
        from .diagnostics import structural_set as _structural
        exempt = _structural(inst, max_minutes)
        sol = _assign(inst, act, day, max_minutes,
                      capacity, weights, override=override, equity_cap=equity_cap,
                      equity_exempt=exempt, mode=mode)
        worst = sol.metrics.get("worst_unmet_ratio_nonexempt", sol.metrics["worst_unmet_ratio"])
        sol.metrics["equity_cap"] = equity_cap
        sol.metrics["equity_cap_met"] = bool(worst <= equity_cap + 1e-9)
        sol.metrics["equity_exempt"] = list(exempt)
        (feasible if worst <= equity_cap + 1e-9 else infeasible).append(sol)

    if feasible:
        return min(feasible, key=lambda s: (s.metrics["unmet_total"], s.metrics["gini_coverage"]))
    if not infeasible:
        raise AssertionError("没有候选组合")
    return min(infeasible, key=lambda s: (s.metrics.get("worst_unmet_ratio_nonexempt",
                                                         s.metrics["worst_unmet_ratio"]),
                                           s.metrics["unmet_total"]))


def efficiency_equity_frontier(inst: Instance, p: int, caps: Sequence[float] = (0.1, 0.2, 0.3, 0.5, 0.75, 1.0),
                               **kw) -> List[Dict[str, object]]:
    """扫 equity_cap，得到 效率（未满足量）— 公平（最差区）前沿。"""
    rows: List[Dict[str, object]] = []
    for cap in caps:
        sol = solve_static_fair(inst, p, equity_cap=cap, **kw)
        rows.append({
            "p": p, "equity_cap": cap,
            "worst_unmet_ratio": sol.metrics["worst_unmet_ratio"],
            "unmet_total": sol.metrics["unmet_total"],
            "coverage_rate": sol.metrics["coverage_rate"],
            "coverage_min": sol.metrics["coverage_min"],
            "gini_coverage": sol.metrics["gini_coverage"],
            "cap_met": sol.metrics["equity_cap_met"],
            "chosen": ",".join(sol.chosen),
        })
    return rows

def solve_static_maxmin(inst: Instance, p: int, max_minutes: float = 30.0,
                        capacity: float = 250.0, day: int = 0,
                        iterations: int = 8, **kw) -> Solution:
    """max-min：先找能达到的最小"最差未满足率"，再在该约束下最小化总未满足。

    做法：对 ε 二分可行域（ε 越小越难满足）。
    """
    lo, hi = 0.0, 1.0
    best_feasible = None
    for _ in range(iterations):
        mid = (lo + hi) / 2.0
        sol = solve_static_fair(inst, p, equity_cap=mid, max_minutes=max_minutes,
                                capacity=capacity, day=day, **kw)
        if sol.metrics.get("equity_cap_met"):
            best_feasible = sol
            hi = mid
        else:
            lo = mid
    if best_feasible is None:
        return solve_static_fair(inst, p, equity_cap=1.0, max_minutes=max_minutes,
                                 capacity=capacity, day=day, **kw)
    return solve_static_fair(inst, p, equity_cap=hi, max_minutes=max_minutes,
                             capacity=capacity, day=day, **kw)
