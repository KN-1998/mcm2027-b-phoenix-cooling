"""Q4 中断与 24 小时重规划。

情景：一个主要固定中心（默认 R01, 24/7 respite）因断电停用；
      两个低收入且公交差的区需求上升；移动枢纽须在 24 h 内重分配。
[EXT-12] 可扩展：设备故障概率、路网中断、需求预测误差的蒙特卡洛。
"""
from __future__ import annotations

import copy

from typing import Dict, List, Sequence

from .schema import Instance
from .static import Solution, solve_static


def pick_low_income(inst: Instance, k: int = 2) -> List[str]:
    ranked = sorted(inst.districts, key=lambda d: (d.median_income, -d.pct_no_vehicle))
    return [d.id for d in ranked[:k]]


def apply_shock(inst: Instance, districts: Sequence[str], mult: float = 1.8) -> Instance:
    """返回**新实例**（不修改输入）。重复调用同一输入结果一致。"""
    out = copy.deepcopy(inst)
    for (did, day), v in list(out.demand.items()):
        if did in districts:
            out.demand[(did, day)] = v * mult
    out.meta = dict(out.meta)
    out.meta["shock"] = {"districts": list(districts), "multiplier": mult}
    return out


def run_disruption(inst: Instance, p: int, max_minutes: float = 30.0,
                   capacity: float = 250.0, down_site: str = "R01",
                   mult: float = 1.8) -> Dict[str, object]:
    before = solve_static(inst, p, max_minutes=max_minutes, capacity=capacity, day=0)
    low = pick_low_income(inst, 2)
    # A1 修复：必须接收冲击后的**副本**，否则需求激增根本没进入求解
    shocked = apply_shock(inst, low, mult)
    after_shock = solve_static(shocked, p, max_minutes=max_minutes, capacity=capacity, day=0,
                               exclude_sites=[down_site])
    return {
        "baseline": before.metrics,
        "after_disruption": after_shock.metrics,
        "shock_districts": low,
        "down_site": down_site,
        "delta_unmet": round(after_shock.metrics["unmet_total"] - before.metrics["unmet_total"], 3),
        "response_hours_assumed": 24.0,   # 假设值，不是求解出来的恢复时间
        "response_hours_modeled": False,
    }

def plan_response(inst: Instance, p: int = 3, mult: float = 1.8,
                  down_site: str | None = None, down_vehicle_at: str | None = None,
                  budget_hours: float = 24.0, max_minutes: float = 30.0,
                  capacity: float = 250.0, open_hours: float = 10.0,
                  parallel: bool = False) -> Dict[str, object]:
    """Q4 闭环 v3（第四轮审查修正）。

    语义分离（审查第 1、3 条）：
      - `down_site`：**场地**不可用（任何车都不能在该点服务，但车可以开走）。
      - `down_vehicle_at`：**停在某点的车**故障（该场地仍可用，可由别的健康车占用）。
        车队由 p 降为 p−1；故障车永远不能作为迁出来源。
    选点规则（审查第 2 条）：把"不搬"作为候选，**按响应后的未满足量**在所有可行方案中选最优，
    因此报告的最优方案净收益恒 ≥ 0（负收益只作为被拒绝的候选出现）。
    容量（审查第 5 条）：按"就绪时刻与营业窗口的交集"折算该车当天可服务小时，而不是固定 2 小时。
    """
    from .dynamic import plan_moves
    from .static import _assign, _active_sites

    kw = dict(max_minutes=max_minutes, capacity=capacity, day=0)
    base = solve_static(inst, p, **kw)
    low = pick_low_income(inst, 2)
    shocked = apply_shock(inst, low, mult)

    if down_vehicle_at and down_vehicle_at not in base.chosen:
        raise ValueError(f"down_vehicle_at={down_vehicle_at} 不在当前部署中；未部署车辆故障不应改变车队")

    fleet = p - (1 if down_vehicle_at else 0)
    blocked = [x for x in (down_site,) if x]

    # 不搬：维持原点位；故障车所在点若无车则无人服务（场地仍可用但没车）
    stay_sites = [x for x in base.chosen if x != down_site]
    if down_vehicle_at:
        stay_sites = [x for x in stay_sites if x != down_vehicle_at]
    no_move = _assign(shocked, _active_sites(shocked, tuple(stay_sites), blocked),
                      0, max_minutes, capacity)

    # 计算"从当前部署出发、搬到目标点集"的就绪时刻与容量折减
    current = [x for x in base.chosen if x != down_vehicle_at]

    def schedule_to(target):
        moves = plan_moves(inst, tuple(current), tuple(target))
        t = 0.0
        timeline = []
        for m in moves:
            travel = float(m["hours"])       # move_time_hours 已含搭建
            ready = t + travel
            timeline.append({"from": m["from"], "to": m["to"], "depart_h": round(t, 2),
                             "travel_h": round(travel, 2), "ready_h": round(ready, 2)})
            # 串行：同一班组的下一台从上一台就绪后开始；并行走各自就绪
            t = max(t, ready) if parallel else ready
        ready_by_site = {m["to"]: m["ready_h"] for m in timeline}
        return timeline, ready_by_site, t

    def capacity_factor(ready_h):
        # 就绪前不可服务：按该车当天可服务小时占比折算
        return max(0.0, 1.0 - min(open_hours, float(ready_h)) / open_hours)

    # 枚举可达的点位集合（枚举而非贪心），含"不搬"
    import itertools
    cand_ids = [s.id for s in inst.candidate_sites() if s.id not in blocked]
    options = []
    for combo in itertools.combinations(cand_ids, fleet):
        timeline, ready_by_site, total_t = schedule_to(combo)
        downtime = {sid: capacity_factor(h) for sid, h in ready_by_site.items()}
        sol = _assign(shocked, _active_sites(shocked, tuple(combo), blocked),
                      0, max_minutes, capacity, downtime=downtime)
        options.append({"chosen": list(combo), "unmet": round(sol.metrics["unmet_total"], 3),
                        "timeline": timeline, "total_hours": round(total_t, 2),
                        "feasible": total_t <= budget_hours,
                        "n_moves": sum(1 for m in timeline if m["from"])})

    feasible = [o for o in options if o["feasible"]]
    best = min(feasible, key=lambda o: o["unmet"]) if feasible else None
    no_move_unmet = round(no_move.metrics["unmet_total"], 3)
    best_unmet = best["unmet"] if best else None
    gain = None if best is None else round(no_move_unmet - best_unmet, 3)

    # 被"不搬"支配的候选（用于解释为什么不该搬）
    dominated = sorted([o for o in feasible if o["unmet"] > no_move_unmet],
                       key=lambda o: o["unmet"])[:3]

    return {
        "shock_districts": low, "shock_multiplier": mult,
        "down_site": down_site, "down_vehicle_at": down_vehicle_at,
        "fleet_nominal": p, "fleet_healthy": fleet,
        "base": {"chosen": list(base.chosen), "unmet": round(base.metrics["unmet_total"], 3)},
        "shock_only": round(solve_static(shocked, p, **kw).metrics["unmet_total"], 3),
        "no_move": {"chosen": list(stay_sites), "unmet": no_move_unmet},
        "best": best,
        "response_gain": gain,
        "gain_definition": "no_move_unmet - best_feasible_unmet（按响应后未满足量选优，恒 >= 0）",
        "dominated_examples": [{"chosen": o["chosen"], "unmet": o["unmet"]} for o in dominated],
        "n_options": len(options), "n_feasible": len(feasible),
        "budget_hours": budget_hours,
        "feasible_any": bool(feasible),
        "parallel": parallel,
    }


def plan_response_legacy(inst: Instance, p: int = 3, mult: float = 1.8,
                         down_site: str | None = None, down_vehicle: str | None = None,
                         budget_hours: float = 24.0, max_minutes: float = 30.0,
                         capacity: float = 250.0, open_hours: float = 10.0) -> Dict[str, object]:
    """旧接口（v2）：保留兼容，语义为 down_vehicle=车辆在某点故障且该点同时不可用。"""
    return plan_response(inst, p, mult=mult, down_site=down_site,
                         down_vehicle_at=down_vehicle, budget_hours=budget_hours,
                         max_minutes=max_minutes, capacity=capacity, open_hours=open_hours)
