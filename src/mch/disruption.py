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
                  down_site: str | None = None, down_vehicle: str | None = None,
                  budget_hours: float = 24.0, max_minutes: float = 30.0,
                  capacity: float = 250.0, open_hours: float = 10.0) -> Dict[str, object]:
    """Q4 闭环（R1/R2 修正版）：区分"位置不可用"与"车辆故障"，并守住车队守恒。

    - `down_site`：某个**位置**不可用（如断电）。设备可以搬走，车队仍是 p 台。
    - `down_vehicle`：某台**移动枢纽设备**故障。健康车队变为 p-1 台，
      故障车**不得**再被当作可搬迁车辆投入服务。
    - 迁移时间沿用 `move_time_hours`（已含 0.5 h 搭建），不再重复加 setup。
    - 串行调度：第 k 台车在它自己开业前的等待期同样不可服务（按开业时刻折算停服）。
    - 超出 `budget_hours` 的方案照实计算，但标记为不可执行，且**不计入可执行收益**。
    """
    from .dynamic import plan_moves
    from .static import _assign, _active_sites

    kw = dict(max_minutes=max_minutes, capacity=capacity, day=0)
    base = solve_static(inst, p, **kw)
    low = pick_low_income(inst, 2)
    shocked = apply_shock(inst, low, mult)

    # 健康车队：故障车退出
    fleet = p - (1 if down_vehicle else 0)
    if fleet < 0:
        raise ValueError("fleet < 0")

    # 事前部署（合理起点）：若故障车在部署中，它不能算作可用
    before_healthy = [x for x in base.chosen if x != down_vehicle]

    # 不响应：位置限制 + 车辆故障，都体现在可用集合里
    stay_pool = [x for x in before_healthy if x != down_site]
    stay = _assign(shocked, _active_sites(shocked, tuple(stay_pool), [down_site] if down_site else []),
                   0, max_minutes, capacity)

    # 响应：健康车队重新选点（数量为 fleet），再算迁移
    target = solve_static(shocked, fleet, exclude_sites=[x for x in (down_site, down_vehicle) if x], **kw)

    moves = plan_moves(inst, tuple(before_healthy), tuple(target.chosen))

    timeline, t = [], 0.0
    for m in moves:
        travel = float(m["hours"])          # move_time_hours 已含搭建
        ready = t + travel
        timeline.append({"from": m["from"], "to": m["to"], "depart_h": round(t, 2),
                         "travel_h": round(travel, 2), "arrive_h": round(t + travel, 2),
                         "open_h": round(ready, 2)})
        t = ready
    feasible = t <= budget_hours

    # 停服：按该车自己的开业时刻（含排队等待）
    down = {}
    for m in timeline:
        down[m["to"]] = max(0.0, 1.0 - min(open_hours, m["open_h"]) / open_hours)
    with_resp = _assign(shocked, _active_sites(shocked, tuple(target.chosen),
                                              [x for x in (down_site, down_vehicle) if x]),
                        0, max_minutes, capacity, downtime=down)

    gain = round(stay.metrics["unmet_total"] - with_resp.metrics["unmet_total"], 3)
    # 车队守恒自检
    origins = {m["from"] for m in moves if m["from"]}
    assert len(origins) <= fleet, "搬迁车数超过健康车队"
    if down_vehicle:
        assert down_vehicle not in origins, "故障车不得被当作可搬迁车辆"

    return {
        "shock_districts": low, "shock_multiplier": mult,
        "down_site": down_site, "down_vehicle": down_vehicle,
        "fleet_nominal": p, "fleet_healthy": fleet,
        "base": {"chosen": list(base.chosen), "unmet": round(base.metrics["unmet_total"], 3)},
        "shock_only": round(solve_static(shocked, p, **kw).metrics["unmet_total"], 3),
        "no_response": {"chosen": list(stay.chosen), "unmet": round(stay.metrics["unmet_total"], 3)},
        "with_response": {"chosen": list(target.chosen), "unmet": round(with_resp.metrics["unmet_total"], 3)},
        "response_gain": gain if feasible else None,
        "response_gain_infeasible": None if feasible else gain,
        "moves": moves, "timeline": timeline,
        "total_response_hours": round(t, 2), "budget_hours": budget_hours,
        "feasible_within_budget": bool(feasible),
        "response_hours_modeled": True,
    }
