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
    if a == b:
        return 0.0                     # 原地留驻：不搬迁、不搭建（第六轮审查）
    from math import hypot
    km = hypot((sa.lat - sb.lat) * 111.0, (sa.lon - sb.lon) * 95.0)
    return round(0.5 + km / 40.0, 2)   # 0.5 h 搭建 + 40 km/h 行驶


def crew_drive_hours(inst: Instance, a: str, b: str) -> float:
    """Crew repositioning time without another vehicle's setup operation."""
    from math import hypot
    if a == b:return 0.0
    lookup = {s.id:s for s in inst.sites}
    sa,sb = lookup[a],lookup[b]
    return round(hypot((sa.lat-sb.lat)*111,(sa.lon-sb.lon)*95)/40,2)


def solve_dynamic(inst: Instance, p: int, max_minutes: float = 30.0,
                  capacity: float = 250.0, downtime_frac: float | None = None,
                  move_penalty: float = 0.0, use_move_time: bool = True) -> List[Solution]:
    """Compatibility entry point replaying the authoritative full-state DP.

    Fixed downtime fractions and arbitrary move-penalty objectives are retired;
    callers must use the explicit clock model and its documented objective.
    """
    if downtime_frac is not None or move_penalty != 0 or not use_move_time:
        raise ValueError('legacy fixed downtime/move penalty retired; use solve_week_dp')
    from .hours import PERIODS, capacity_on_service_day
    from .realnet import site_on_day
    result = solve_week_dp(inst,p,max_minutes,capacity)
    lookup = {s.id:s for s in inst.candidate_sites()}
    output = []
    for row in result['schedule']:
        day = row['day']; caps = {}
        for move in row['moves']:
            site = site_on_day(lookup[move['to']],day)
            base = float(site.capacity) if site.extra.get('capacity_is_explicit') else float(site.capacity or capacity)
            caps[site.id] = {h:capacity_on_service_day(site,base,h,day,move['hours']) for h in PERIODS}
        sol = _assign(inst,_active_sites(inst,row['combo']),day,max_minutes,capacity,
                      cap_by_period_override=caps)
        sol.metrics.update({'moves':row['moves'],'search_status':result['search_status']})
        output.append(sol)
    return output


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
                  capacity: float = 250.0, top_k: int = 0,
                  open_hours: float = 10.0) -> Dict[str, object]:
    """Daily-state DP, exact within the stated same-day relocation model.

    top_k=0 uses all combinations; positive K is an explicitly restricted-state
    heuristic. Trips over 24h are rejected: overnight transit needs extra state.
    All bijections of the previous fleet to today's sites are evaluated,
    including useful swaps at common sites. Crews relocate in parallel at 09:00.
    open_hours is retained only for API compatibility, not used as a capacity
    divisor. Arrival intersects each site's actual operating window instead.
    """
    import itertools
    from .hours import PERIODS, capacity_on_service_day
    from .realnet import site_on_day
    sites = {s.id: s for s in inst.candidate_sites()}
    if not 0 <= p <= len(sites) or inst.horizon_days < 1 or top_k < 0:
        raise ValueError("invalid p, horizon, or top_k")
    travel = {(a, b): move_time_hours(inst, a, b) for a in sites for b in sites}
    if any(t < 0 or t > 24 for t in travel.values()):
        raise ValueError("Q3 requires all relocation trips within 24h; cross-day transit is outside this model")
    days = list(range(inst.horizon_days))
    combos = list(itertools.combinations(sites, p))
    def unmet(sol, day):
        return max(0.0, sum(inst.demand.get((d.id, day), 0.0) for d in inst.districts)
                   - sum(sol.served.values()))
    gross = {(day, combo): unmet(_assign(inst, _active_sites(inst, combo), day,
                                        max_minutes, capacity), day)
             for day in days for combo in combos}
    static_best = min(combos, key=lambda c: (sum(gross[d,c] for d in days), c))
    static_total = sum(gross[d,static_best] for d in days)
    states = set(combos) if top_k == 0 else {static_best}
    if top_k:
        for day in days:
            states.update(sorted(combos, key=lambda c: (gross[day,c], c))[:top_k])
    states = sorted(states)
    cache, selected_moves = {}, {}
    evaluated = 0
    def transition(day, prev, cur):
        nonlocal evaluated
        key = (day, prev, cur)
        if key in cache: return cache[key]
        if not prev or prev == cur:
            cache[key], selected_moves[key] = gross[day,cur], []
            return cache[key]
        best = None
        for permutation in itertools.permutations(prev):
            moves = [{"from": a, "to": b, "hours": travel[a,b]}
                     for a,b in zip(permutation, cur) if a != b]
            caps = {}
            for move in moves:
                sid = move["to"]; site = site_on_day(sites[sid], day)
                base = float(site.capacity) if site.extra.get('capacity_is_explicit') else float(site.capacity or capacity)
                caps[sid] = {h: capacity_on_service_day(site, base, h, day, move["hours"]) for h in PERIODS}
            sol = _assign(inst, _active_sites(inst, cur), day, max_minutes,
                          capacity, cap_by_period_override=caps)
            evaluated += 1
            score = (unmet(sol, day), max(m["hours"] for m in moves), permutation)
            if best is None or score < best[0]: best = (score, moves)
        cache[key], selected_moves[key] = best[0][0], best[1]
        return cache[key]
    values = {c: gross[0,c] for c in states}
    back = {0: {c: () for c in states}}
    for day in days[1:]:
        nxt, links = {}, {}
        previous = sorted(values, key=lambda pv: (values[pv], pv))
        for cur in states:
            best_value, best_prev = float("inf"), None
            for prev in previous:
                # Gross service ignores downtime, hence is a lower bound on unmet.
                # Equality may be pruned because only total unmet is optimized.
                if values[prev] + gross[day,cur] >= best_value - 1e-9: continue
                score = values[prev] + transition(day, prev, cur)
                if score < best_value:
                    best_value, best_prev = score, prev
            nxt[cur], links[cur] = best_value, best_prev
        values, back[day] = nxt, links
    last = min(values, key=lambda c: (values[c], c))
    total = values[last]
    path, cur = [], last
    for day in reversed(days):
        path.append(cur); cur = back[day][cur]
    path.reverse()
    schedule = []
    for day, cur in enumerate(path):
        prev = path[day-1] if day else ()
        cost = transition(day, prev, cur)
        schedule.append({"day": day, "combo": list(cur),
                         "moves": selected_moves[day,prev,cur], "unmet": round(cost,6)})
    lower = sum(min(gross[d,c] for c in combos) for d in days)
    return {"p": p, "static_best": list(static_best),
            "static_total_unmet": round(static_total,6),
            "dynamic_total_unmet": round(total,6), "schedule": schedule,
            "candidates": [list(c) for c in states], "top_k": top_k,
            "search_status": "optimal_within_model" if top_k == 0 else "restricted_state_heuristic",
            "daily_oracle_lower_bound": round(lower,6),
            "absolute_gap_to_lower_bound": round(max(0,total-lower),6),
            "transition_lp_evaluations": evaluated,
            "assumptions": {"service_day_start":9,"parallel_crews_required":p,
                            "initial_deployment_ready":True,"max_trip_hours":24,
                            "matching_includes_common_site_swaps":True,
                            "travel_model":"0.5h setup + coordinate distance / 40kmh"}}
