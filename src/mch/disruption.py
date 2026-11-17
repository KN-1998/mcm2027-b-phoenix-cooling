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
                  down_site: str = "R01", budget_hours: float = 24.0,
                  max_minutes: float = 30.0, capacity: float = 250.0,
                  setup_hours: float = 0.5, open_hours: float = 10.0) -> Dict[str, object]:
    """Q4 闭环：把"24 小时响应"做成可执行时刻表，而不是一个常数。

    分解（同一实例、同一日）：
      base      : 无冲击、无停用
      shock_only: 有冲击、无停用
      outage_only: 无冲击、有停用
      both      : 冲击 + 停用，枢纽**不动**（不响应）
      response  : 冲击 + 停用，枢纽**搬到新最优**（扣迁移/搭建的容量损失）
    """
    from .dynamic import plan_moves
    from .static import _assign, _active_sites

    kw = dict(max_minutes=max_minutes, capacity=capacity, day=0)
    base = solve_static(inst, p, **kw)
    low = pick_low_income(inst, 2)
    shocked = apply_shock(inst, low, mult)

    shock_only = solve_static(shocked, p, **kw)
    outage_only = solve_static(inst, p, exclude_sites=[down_site], **kw)

    # 不响应：维持原点位，但停用 down_site
    stay_sites = [x for x in base.chosen if x != down_site]
    # 不响应：维持原点位，且 down_site 必须真的停用
    stay = _assign(shocked, _active_sites(shocked, tuple(stay_sites), [down_site]),
                   0, max_minutes, capacity)

    # 响应：搬到冲击后的新最优
    target = solve_static(shocked, p, exclude_sites=[down_site], **kw)
    moves = plan_moves(inst, tuple(stay_sites + [down_site]), target.chosen)

    timeline, t = [], 0.0
    for m in moves:
        travel = float(m["hours"])
        ready = t + travel + setup_hours
        timeline.append({"from": m["from"], "to": m["to"], "depart_h": round(t, 2),
                         "travel_h": round(travel, 2), "arrive_h": round(t + travel, 2),
                         "open_h": round(ready, 2)})
        t = ready
    feasible = t <= budget_hours

    down = {}
    for m in moves:
        if m["to"]:
            down[m["to"]] = max(0.0, 1.0 - min(open_hours, float(m["hours"]) + setup_hours) / open_hours)
    with_resp = _assign(shocked, _active_sites(shocked, tuple(target.chosen), [down_site]),
                        0, max_minutes, capacity, downtime=down)

    return {
        "shock_districts": low, "shock_multiplier": mult, "down_site": down_site,
        "base": {"chosen": list(base.chosen), "unmet": round(base.metrics["unmet_total"], 3)},
        "shock_only": round(shock_only.metrics["unmet_total"], 3),
        "outage_only": round(outage_only.metrics["unmet_total"], 3),
        "both_no_response": {"chosen": list(stay.chosen), "unmet": round(stay.metrics["unmet_total"], 3)},
        "with_response": {"chosen": list(target.chosen), "unmet": round(with_resp.metrics["unmet_total"], 3)},
        "response_gain": round(stay.metrics["unmet_total"] - with_resp.metrics["unmet_total"], 3),
        "moves": moves, "timeline": timeline,
        "total_response_hours": round(t, 2), "budget_hours": budget_hours,
        "feasible_within_budget": bool(feasible), "response_hours_modeled": True,
    }
