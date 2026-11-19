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
                  parallel: bool = False, top_combos: int = 3,
                  top_matchings: int = 3) -> Dict[str, object]:
    """Q4 闭环 v5（第六轮审查修正）。

    1. **所有候选结构统一**：都含 `timeline`、`feasible`、`action`，`no_move` 的 timeline 为空表；
    2. **原地留驻不计时**：`from == to` 的车辆 ready=0，不占队列、不扣容量、不计搬迁次数；
    3. **按响应后净服务选优**：对每个目标点集枚举匹配与串行顺序，先判期限，再算净服务，
       最小运输时间只作次级指标（不再"先按总时间挑一个"）。
    4. 容量仍按 `1 - ready/open_hours` 近似（未引入墙钟时间轴，已在输出中标注）。
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

    stay_sites = [x for x in current if x != down_site]
    no_move_sol = _assign(shocked, _active_sites(shocked, tuple(stay_sites), blocked),
                          0, max_minutes, capacity)
    no_move = {"action": "no_move", "chosen": list(stay_sites),
               "unmet": round(no_move_sol.metrics["unmet_total"], 3),
               "timeline": [], "total_hours": 0.0, "n_moves": 0,
               "feasible": True, "idle": len(stay_sites) < fleet}

    def matchings(cur, tgt):
        """生成 cur→tgt 的匹配（每台车最多一个目标；可留驻）。"""
        cur = [c for c in cur]
        tgt = list(tgt)
        if len(cur) <= 4 and len(tgt) <= 4:
            out = []
            for perm in itertools.permutations(cur, min(len(cur), len(tgt))):
                out.append(list(zip(perm, tgt)))
            # 也允许部分车辆闲置（目标少于车辆）
            if len(tgt) < len(cur):
                for perm in itertools.permutations(cur, len(tgt)):
                    out.append(list(zip(perm, tgt)))
            # 去重
            seen, uniq = set(), []
            for m in out:
                key = tuple((c, t) for c, t in m)
                if key not in seen:
                    seen.add(key)
                    uniq.append(m)
            return uniq
        pairs, used = [], set()
        for t in tgt:
            cand = [(move_time_hours(inst, c, t), c) for c in cur if c not in used]
            if not cand:
                pairs.append((None, t)); continue
            h, c = min(cand); used.add(c); pairs.append((c, t))
        return [pairs]

    def timeline_for(pairs, order):
        """顺序执行；from==to 视为已就绪，不占队列。"""
        if parallel:
            tl = []
            for c, t in pairs:
                h = 0.0 if c == t else float(move_time_hours(inst, c, t))
                tl.append({"from": c, "to": t, "depart_h": 0.0, "travel_h": round(h, 2),
                           "ready_h": round(h, 2), "in_place": c == t})
            total = max([x["ready_h"] for x in tl], default=0.0)
            return tl, round(total, 2)
        clock, tl = 0.0, []
        for idx in order:
            c, t = pairs[idx]
            if c == t:
                tl.append({"from": c, "to": t, "depart_h": 0.0, "travel_h": 0.0,
                           "ready_h": 0.0, "in_place": True})
                continue
            h = float(move_time_hours(inst, c, t))
            tl.append({"from": c, "to": t, "depart_h": round(clock, 2), "travel_h": round(h, 2),
                       "ready_h": round(clock + h, 2), "in_place": False})
            clock += h
        return tl, round(clock, 2)

    def capacity_factor(ready_h):
        return max(0.0, 1.0 - min(open_hours, float(ready_h)) / open_hours)

    cand_ids = [s.id for s in inst.candidate_sites() if s.id not in blocked]
    k = min(fleet, len(cand_ids))

    # 先用"不计停服"的未满足量粗排，取 top_combos 再做完整调度
    quick = []
    if k > 0:
        for combo in itertools.combinations(cand_ids, k):
            sol = _assign(shocked, _active_sites(shocked, tuple(combo), blocked),
                          0, max_minutes, capacity)
            quick.append((sol.metrics["unmet_total"], combo))
        quick.sort()
        quick = quick[:max(1, top_combos)]
    else:
        quick = []

    options = [no_move]
    for _proxy, combo in quick:
        # 匹配候选（按"最大就绪"或"总时间"排序，取前 top_matchings）
        ms = matchings(current, list(combo))

        def score(m):
            hs = [0.0 if c == t else float(move_time_hours(inst, c, t)) for c, t in m]
            return max(hs) if parallel else sum(hs)

        ms = sorted(ms, key=score)[:max(1, top_matchings)]
        for m in ms:
            orders = [tuple(range(len(m)))]
            if not parallel and len(m) <= 3:
                orders = list(itertools.permutations(range(len(m))))
            for order in orders:
                tl, total = timeline_for(m, order)
                if total > budget_hours:
                    continue
                down = {x["to"]: capacity_factor(x["ready_h"]) for x in tl if not x.get("in_place")}
                sol = _assign(shocked, _active_sites(shocked, tuple(combo), blocked),
                              0, max_minutes, capacity, downtime=down)
                options.append({"action": "relocate", "chosen": list(combo),
                                "unmet": round(sol.metrics["unmet_total"], 3),
                                "timeline": tl, "total_hours": total,
                                "n_moves": sum(1 for x in tl if not x.get("in_place")),
                                "feasible": True})

    feasible = [o for o in options if o.get("feasible", True)]
    best = min(feasible, key=lambda o: (o["unmet"], o["total_hours"])) if feasible else None
    gain = None if best is None else round(no_move["unmet"] - best["unmet"], 3)

    return {
        "shock_districts": low, "shock_multiplier": mult,
        "down_site": down_site, "down_vehicle_at": down_vehicle_at,
        "fleet_nominal": p, "fleet_healthy": fleet,
        "base": {"chosen": list(base.chosen), "unmet": round(base.metrics["unmet_total"], 3)},
        "shock_only": round(solve_static(shocked, p, **kw).metrics["unmet_total"], 3),
        "no_move": no_move, "best": best, "response_gain": gain,
        "gain_definition": "no_move_unmet - best_feasible_unmet（不搬恒在候选内）",
        "n_options": len(options), "n_feasible": len(feasible),
        "budget_hours": budget_hours, "feasible_any": bool(feasible),
        "parallel": parallel,
        "capacity_note": "停服按 1-ready/open_hours 近似；原地留驻 ready=0，不扣容量",
    }


def plan_response_legacy(inst: Instance, p: int = 3, mult: float = 1.8,
                         down_site: str | None = None, down_vehicle: str | None = None,
                         budget_hours: float = 24.0, max_minutes: float = 30.0,
                         capacity: float = 250.0, open_hours: float = 10.0) -> Dict[str, object]:
    """旧接口（v2）：保留兼容，语义为 down_vehicle=车辆在某点故障且该点同时不可用。"""
    return plan_response(inst, p, mult=mult, down_site=down_site,
                         down_vehicle_at=down_vehicle, budget_hours=budget_hours,
                         max_minutes=max_minutes, capacity=capacity, open_hours=open_hours)
