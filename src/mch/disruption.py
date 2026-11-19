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
                  parallel: bool = False, exact_matching: bool = True) -> Dict[str, object]:
    """Q4 闭环 v4（第五轮审查修正）。

    修正点：
      P2-A：**始终**把"不搬/闲置"作为候选（关闭已部署点时也合法）；
            活动点数 ≤ 健康车队数，不要求恰好用满。
      P2-B：`parallel=True` 时各车**各自从 0 时刻出发**，总耗时取最大值；串行才累加。
      P2-C：目标点集内**精确枚举车辆匹配**（当前部署 ≤4 台时用排列），不再只用贪心。
      时钟：停服折减按 `1 - ready/open_hours`（仍是近似；文档已如实标注，
            未实现"决策钟点 + 营业窗交集"，因为模型没有引入墙钟时间轴）。
    """
    import itertools

    from .dynamic import move_time_hours
    from .static import _assign, _active_sites

    kw = dict(max_minutes=max_minutes, capacity=capacity, day=0)
    base = solve_static(inst, p, **kw)
    low = pick_low_income(inst, 2)
    shocked = apply_shock(inst, low, mult)

    if down_vehicle_at and down_vehicle_at not in base.chosen:
        raise ValueError(f"down_vehicle_at={down_vehicle_at} 不在当前部署中；未部署车辆故障不应改变车队")

    fleet = p - (1 if down_vehicle_at else 0)
    blocked = [x for x in (down_site,) if x]
    current = [x for x in base.chosen if x != down_vehicle_at]

    # ---------- 不搬（含闲置）：始终是候选 ----------
    stay_sites = [x for x in current if x != down_site]
    no_move_sol = _assign(shocked, _active_sites(shocked, tuple(stay_sites), blocked),
                          0, max_minutes, capacity)
    no_move = {"action": "no_move", "chosen": list(stay_sites),
               "unmet": round(no_move_sol.metrics["unmet_total"], 3),
               "total_hours": 0.0, "n_moves": 0, "idle": len(stay_sites) < fleet}

    def best_matching(cur_sites, target_sites):
        """精确枚举车辆匹配（≤4 台）或贪心（更多）。返回 [(from,to,hours)]。"""
        cur = [x for x in cur_sites if x]
        tgt = list(target_sites)
        if not cur or not tgt:
            return [(None, t, 0.0) for t in tgt]

        def cost(perm):
            return sum(move_time_hours(inst, c, t) for c, t in perm)

        if exact_matching and len(cur) <= 4 and len(tgt) <= 4:
            best, best_v = None, float("inf")
            for combo in itertools.permutations(cur, min(len(cur), len(tgt))):
                perm = list(zip(combo, tgt))
                v = cost(perm)
                if v < best_v:
                    best, best_v = perm, v
            pairs = best or list(zip(cur, tgt))
        else:
            # 贪心：每次取最近的未占用配对
            pairs, used = [], set()
            for t in tgt:
                cand = [(move_time_hours(inst, c, t), c) for c in cur if c not in used]
                if not cand:
                    pairs.append((None, t))
                    continue
                h, c = min(cand)
                used.add(c)
                pairs.append((c, t))
        return [(c, t, move_time_hours(inst, c, t)) for c, t in pairs]

    def schedule_to(target):
        pairs = best_matching(current, list(target))
        timeline = []
        if parallel:
            # 各车 0 时刻同时出发
            for c, t, h in pairs:
                ready = float(h)
                timeline.append({"from": c, "to": t, "depart_h": 0.0,
                                 "travel_h": round(float(h), 2), "ready_h": round(ready, 2)})
            total = max([m["ready_h"] for m in timeline], default=0.0)
        else:
            clock = 0.0
            for c, t, h in pairs:
                ready = clock + float(h)
                timeline.append({"from": c, "to": t, "depart_h": round(clock, 2),
                                 "travel_h": round(float(h), 2), "ready_h": round(ready, 2)})
                clock = ready
            total = clock
        ready_by_site = {m["to"]: m["ready_h"] for m in timeline}
        return timeline, ready_by_site, round(total, 2)

    def capacity_factor(ready_h):
        return max(0.0, 1.0 - min(open_hours, float(ready_h)) / open_hours)

    # ---------- 枚举目标点集：规模取 min(健康车队, 可用候选) ----------
    cand_ids = [s.id for s in inst.candidate_sites() if s.id not in blocked]
    k = min(fleet, len(cand_ids))
    options = [no_move]
    if k > 0:
        for combo in itertools.combinations(cand_ids, k):
            timeline, ready_by_site, total_t = schedule_to(combo)
            downtime = {sid: capacity_factor(h) for sid, h in ready_by_site.items()}
            sol = _assign(shocked, _active_sites(shocked, tuple(combo), blocked),
                          0, max_minutes, capacity, downtime=downtime)
            options.append({"action": "relocate", "chosen": list(combo),
                            "unmet": round(sol.metrics["unmet_total"], 3),
                            "timeline": timeline, "total_hours": total_t,
                            "feasible": total_t <= budget_hours,
                            "n_moves": sum(1 for m in timeline if m["from"])})

    feasible = [o for o in options if o.get("feasible", True)]
    best = min(feasible, key=lambda o: o["unmet"]) if feasible else None
    gain = None if best is None else round(no_move["unmet"] - best["unmet"], 3)

    return {
        "shock_districts": low, "shock_multiplier": mult,
        "down_site": down_site, "down_vehicle_at": down_vehicle_at,
        "fleet_nominal": p, "fleet_healthy": fleet,
        "base": {"chosen": list(base.chosen), "unmet": round(base.metrics["unmet_total"], 3)},
        "shock_only": round(solve_static(shocked, p, **kw).metrics["unmet_total"], 3),
        "no_move": no_move,
        "best": best,
        "response_gain": gain,
        "gain_definition": "no_move_unmet - best_feasible_unmet（不搬始终在候选内，故 >= 0）",
        "n_options": len(options), "n_feasible": len(feasible),
        "budget_hours": budget_hours, "feasible_any": bool(feasible),
        "parallel": parallel, "exact_matching": exact_matching,
        "capacity_note": "停服按 1-ready/open_hours 近似；未引入墙钟时间轴与营业窗交集",
    }


def plan_response_legacy(inst: Instance, p: int = 3, mult: float = 1.8,
                         down_site: str | None = None, down_vehicle: str | None = None,
                         budget_hours: float = 24.0, max_minutes: float = 30.0,
                         capacity: float = 250.0, open_hours: float = 10.0) -> Dict[str, object]:
    """旧接口（v2）：保留兼容，语义为 down_vehicle=车辆在某点故障且该点同时不可用。"""
    return plan_response(inst, p, mult=mult, down_site=down_site,
                         down_vehicle_at=down_vehicle, budget_hours=budget_hours,
                         max_minutes=max_minutes, capacity=capacity, open_hours=open_hours)
