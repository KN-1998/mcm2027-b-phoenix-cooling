"""Q3 七天热浪：逐日部署与迁移。

模型：每天选 p 个候选点；若与前一天不同，产生迁移代价与**停服时间**，
停服期间该枢纽可用容量按 downtime_frac 缩减。
[EXT-11] 若需要精确的迁移路径（车辆路径），在 move_time_hours() 里接路网。
"""
from __future__ import annotations

from typing import Dict, List, Sequence

from .schema import Instance
from .static import Solution, _active_sites, _assign, solve_static


def move_time_hours(inst: Instance, a: str, b: str) -> float:
    """两个候选点之间的迁移时间（小时）。[EXT-11] 现用直线距离代理。"""
    sa = next(s for s in inst.sites if s.id == a)
    sb = next(s for s in inst.sites if s.id == b)
    from math import hypot
    km = hypot((sa.lat - sb.lat) * 111.0, (sa.lon - sb.lon) * 95.0)
    return round(0.5 + km / 40.0, 2)   # 0.5 h 搭建 + 40 km/h 行驶


def solve_dynamic(inst: Instance, p: int, max_minutes: float = 30.0,
                  capacity: float = 250.0, downtime_frac: float = 0.5,
                  move_penalty: float = 0.0, use_move_time: bool = True) -> List[Solution]:
    """逐日贪心对照版（不是 DP；DP 见 src/exp/run_q3_week.py）。

    修正点：
    1. 停服**只作用于当天新搬入的枢纽**（不再对所有选中枢纽一起折减）；
    2. 通过 `_assign(..., downtime={sid: factor})` 显式下传，
       不再依赖会被 s.capacity 覆盖的 capacity 参数；
    3. `move_time_hours` 真正参与：停服因子 = 1 - 迁移小时 / 营业小时。
    """
    prev: Sequence[str] = ()
    out: List[Solution] = []
    open_hours = 10.0

    for day in range(inst.horizon_days):
        base = solve_static(inst, p, max_minutes=max_minutes, capacity=capacity, day=day)
        cands = [base]
        if prev:
            cands.append(_assign(inst, _active_sites(inst, tuple(prev)), day,
                                 max_minutes, capacity))
        best = None
        for sol in cands:
            changed = [x for x in sol.chosen if x not in prev] if day > 0 else []
            downtime = {}
            for sid in changed:
                if use_move_time and prev:
                    hours = min(move_time_hours(inst, prev[0], sid), open_hours)
                    downtime[sid] = max(0.0, 1.0 - hours / open_hours)
                elif changed:
                    downtime[sid] = 1.0 - downtime_frac
            scored = _assign(inst, _active_sites(inst, tuple(sol.chosen)), day,
                             max_minutes, capacity, downtime=downtime) if downtime else sol
            scored.metrics["moved_in"] = list(changed)
            scored.metrics["downtime_factor"] = {k: round(v, 3) for k, v in downtime.items()}
            scored.metrics["move_penalty"] = round(move_penalty * len(changed), 3)
            score = scored.metrics["unmet_total"] + scored.metrics["move_penalty"]
            if best is None or score < best[0]:
                best = (score, scored)
        assert best is not None
        out.append(best[1])
        prev = best[1].chosen
    return out

def plan_moves(inst: Instance, prev: Sequence[str], cur: Sequence[str]) -> List[dict]:
    """把"迁出集合"与"迁入集合"一一配对（A4 修复）。

    旧实现用 prev[0] 当所有车的迁出点；从 (A,B) 到 (A,C) 时应为 B->C。
    这里按"迁出点与迁入点距离最小"贪心配对，多出的迁入点视为新部署。
    """
    removed = [x for x in prev if x not in cur]
    added = [x for x in cur if x not in prev]
    moves = []
    for target in added:
        if removed:
            src = min(removed, key=lambda r: move_time_hours(inst, r, target))
            removed.remove(src)
            moves.append({"from": src, "to": target,
                          "hours": move_time_hours(inst, src, target)})
        else:
            moves.append({"from": None, "to": target, "hours": 0.0})   # 新部署，不计迁移
    return moves


def solve_week_dp(inst: Instance, p: int, max_minutes: float = 30.0,
                  capacity: float = 250.0, top_k: int = 3,
                  open_hours: float = 10.0) -> Dict[str, object]:
    """七天 DP（唯一权威实现）。状态=当天点位组合；转移=搬入枢纽当天容量折减。

    与 run_q3_week 的差别：这里把"每日最优表"和 DP 都放在同一处，
    主 pipeline 与独立 runner 共用，避免两套实现不一致。
    """
    import itertools
    from .assign import solve_assignment_periods
    from .hours import PERIODS, capacity_in_period, split_demand_mixed

    ushare = float(inst.meta.get("unsheltered_share", 0.5))
    days = list(range(inst.horizon_days))
    combos = list(itertools.combinations([s.id for s in inst.candidate_sites()], p))

    def day_unmet(combo, day, downtime_sites=()) -> float:
        act = _active_sites(inst, combo)
        total = sum(inst.demand.get((d.id, day), 0.0) for d in inst.districts)
        cap_h, dem_h = {}, {}
        for s in act:
            base = float(s.capacity or capacity)
            if s.id in downtime_sites:
                base *= max(0.0, 1.0 - min(open_hours, 2.0) / open_hours)
            cap_h[s.id] = {h: capacity_in_period(s, base, h) for h in PERIODS}
        for d in inst.districts:
            dem_h[d.id] = split_demand_mixed(inst.demand.get((d.id, day), 0.0), ushare)
        out = solve_assignment_periods(inst, act, day, max_minutes, cap_h, dem_h)
        return round(total - sum(out["served"].values()), 3)

    table = {(d, c): day_unmet(c, d) for d in days for c in combos}
    static_best = min(combos, key=lambda c: sum(table[(d, c)] for d in days))
    static_total = round(sum(table[(d, static_best)] for d in days), 2)

    cand = {tuple(static_best)}   # 保证"不搬"永远可选
    for d in days:
        for c in sorted(combos, key=lambda c: table[(d, c)])[:top_k]:
            cand.add(c)
    cand = sorted(cand)
    cache = {}

    def trans(day, prev, cur):
        key = (day, prev, cur)
        if key not in cache:
            moved = tuple(x for x in cur if x not in prev) if prev else ()
            cache[key] = day_unmet(cur, day, moved)
        return cache[key]

    INF = float("inf")
    V = {c: trans(days[0], (), c) for c in cand}
    back = {0: {c: () for c in cand}}
    for d in days[1:]:
        NV, bk = {}, {}
        for cur in cand:
            prev_best = min(V, key=lambda pv: V[pv] + trans(d, pv, cur))
            NV[cur] = V[prev_best] + trans(d, prev_best, cur)
            bk[cur] = prev_best
        V, back[d] = NV, bk
    last = min(V, key=lambda c: V[c])

    path, cur = [], last
    for d in reversed(days):
        path.append(cur); cur = back[d][cur]
    path.reverse()

    schedule = []
    for i, d in enumerate(days):
        prev = path[i - 1] if i > 0 else ()
        schedule.append({"day": d, "combo": list(path[i]),
                         "moves": plan_moves(inst, prev, path[i]) if i > 0 else [],
                         "unmet": trans(d, prev, path[i])})
    return {"p": p, "static_best": list(static_best), "static_total_unmet": static_total,
            "dynamic_total_unmet": round(V[last], 2), "schedule": schedule,
            "candidates": [list(c) for c in cand]}
