"""Q4 emergency reallocation on a 09:00-to-next-09:00 service day.

Small fleets enumerate destinations, vehicle assignments and serial move orders.
Gross service (no relocation downtime) supplies a valid optimistic bound. Larger
fleets use an explicitly labelled heuristic unless exact search is requested.
"""
from __future__ import annotations

import copy
import itertools
import math
from typing import Dict, List, Sequence

from .schema import Instance
from .static import solve_static


def pick_low_income(inst: Instance, k: int = 2) -> List[str]:
    # Income is primary; no-vehicle share breaks equal-income ties. This is a
    # scenario rule, not a claim that these are measured transit-poorest areas.
    ranked = sorted(inst.districts, key=lambda d: (d.median_income, -d.pct_no_vehicle))
    return [d.id for d in ranked[:k]]


def apply_shock(inst: Instance, districts: Sequence[str], mult: float = 1.8) -> Instance:
    if not math.isfinite(mult) or mult < 0:
        raise ValueError("shock multiplier must be finite and nonnegative")
    out = copy.deepcopy(inst)
    for (did, day), value in list(out.demand.items()):
        if did in districts:
            out.demand[(did, day)] = value * mult
    out.meta = dict(out.meta)
    out.meta["shock"] = {"districts": list(districts), "multiplier": mult}
    return out


def run_disruption(inst: Instance, p: int, max_minutes: float = 30.0,
                   capacity: float = 250.0, down_site: str = "R01",
                   mult: float = 1.8) -> Dict[str, object]:
    """Legacy static comparison; relocation timing is not modeled here."""
    before = solve_static(inst, p, max_minutes=max_minutes, capacity=capacity, day=0)
    low = pick_low_income(inst, 2)
    shocked = apply_shock(inst, low, mult)
    after = solve_static(shocked, p, max_minutes=max_minutes, capacity=capacity,
                         day=0, exclude_sites=[down_site])
    return {"baseline": before.metrics, "after_disruption": after.metrics,
            "shock_districts": low, "down_site": down_site,
            "delta_unmet": round(after.metrics["unmet_total"] - before.metrics["unmet_total"], 3),
            "response_hours_assumed": 24.0, "response_hours_modeled": False}


def plan_response(inst: Instance, p: int = 3, mult: float = 1.8,
                  down_site: str | None = None, down_vehicle_at: str | None = None,
                  budget_hours: float = 24.0, max_minutes: float = 30.0,
                  capacity: float = 250.0, open_hours: float = 10.0,
                  parallel: bool = False, top_combos: int = 3,
                  top_matchings: int = 3, search_mode: str = "auto",
                  travel_time_multiplier: float = 1.0,
                  initial_chosen: Sequence[str] | None = None,
                  crew_start_site: str | None = None) -> Dict[str, object]:
    """Minimize unmet visits, then response makespan, under stated assumptions.

    ``auto`` is exact for <=4 healthy vehicles and explicitly heuristic above
    that size. ``exact`` enumerates every vehicle assignment and every serial
    order for any size; its factorial runtime is the caller's responsibility.
    ``heuristic`` uses the supplied top-K limits and a greedy matching for >4.
    ``open_hours`` is retained for API compatibility; window intersections now
    determine usable capacity, so it does not rescale the daily capacity.
    """
    from .dynamic import move_time_hours as base_move_time_hours, crew_drive_hours
    from .hours import PERIODS, capacity_on_service_day
    from .realnet import site_on_day
    from .static import _active_sites, _assign

    if p < 0 or p > len(inst.candidate_sites()):
        raise ValueError("p must be between zero and the number of candidate sites")
    if not math.isfinite(budget_hours) or not 0 <= budget_hours <= 24:
        raise ValueError("response deadline must be within the modeled 24-hour service day")
    if search_mode not in {"auto", "exact", "heuristic"}:
        raise ValueError("search_mode must be auto, exact or heuristic")
    if not math.isfinite(travel_time_multiplier) or travel_time_multiplier <= 0:
        raise ValueError("travel_time_multiplier must be finite and positive")

    def move_time_hours(instance, origin, target):
        return round(float(base_move_time_hours(instance, origin, target)) * travel_time_multiplier, 2)
    known = {s.id for s in inst.sites}
    if crew_start_site is not None and crew_start_site not in known:
        raise ValueError('unknown initial crew site')
    if down_site and down_site not in known:
        raise ValueError(f"unknown closed site: {down_site}")
    kw = dict(max_minutes=max_minutes, capacity=capacity, day=0)
    if initial_chosen is None:
        base = solve_static(inst, p, **kw)
    else:
        ids = list(initial_chosen)
        eligible = {s.id for s in inst.candidate_sites()}
        if len(ids) != p or len(set(ids)) != p or not set(ids) <= eligible:
            raise ValueError("initial_chosen must contain p distinct candidate site IDs")
        base = _assign(inst, _active_sites(inst, ids), 0, max_minutes, capacity)
    crew_start_was_provided=crew_start_site is not None
    if crew_start_site is None and base.chosen:
        # Freeze crew position with the pre-incident deployment; do not choose
        # a free initial location separately for every candidate response.
        crew_start_site=base.chosen[0]
    low = pick_low_income(inst, 2)
    shocked = apply_shock(inst, low, mult)
    if down_vehicle_at and down_vehicle_at not in base.chosen:
        raise ValueError(f"down_vehicle_at={down_vehicle_at} 不在当前部署中；未部署车辆故障不应改变车队")
    fleet = p - int(bool(down_vehicle_at))
    mode = ("exact" if fleet <= 4 else "heuristic") if search_mode == "auto" else search_mode
    blocked = [down_site] if down_site else []
    current = [x for x in base.chosen if x != down_vehicle_at]
    stay_sites = [x for x in current if x != down_site]
    demand_total = sum(shocked.demand.get((d.id, 0), 0.0) for d in shocked.districts)

    def unmet_raw(sol):
        return float(max(0.0, demand_total - sum(sol.served.values())))

    stay_sol = _assign(shocked, _active_sites(shocked, stay_sites, blocked),
                       0, max_minutes, capacity)
    no_move = {"action": "no_move", "chosen": stay_sites,
               'worst_unmet_ratio_all':stay_sol.metrics['worst_unmet_ratio_raw'],
               "unmet": round(unmet_raw(stay_sol), 3), "timeline": [],
               "total_hours": 0.0, "n_moves": 0, "feasible": True,
               "idle": len(stay_sites) < fleet, "_raw": unmet_raw(stay_sol)}
    options = [no_move]
    best = no_move
    counts = {"destination_sets_total": 0, "destination_sets_evaluated": 0,
              "destination_sets_pruned_by_bound": 0, "matchings_generated": 0,
              "timelines_tested": 0, "deadline_feasible_timelines": 0,
              "assignment_lp_evaluations": 0}

    def generate_matchings(target):
        if mode == "exact" or len(current) <= 4:
            return (list(zip(origin, target)) for origin in
                    itertools.permutations(current, len(target)))
        pairs, used = [], set()
        for t in target:
            choices = [(move_time_hours(inst, c, t), c) for c in current if c not in used]
            if not choices:
                return iter(())
            _, c = min(choices)
            used.add(c)
            pairs.append((c, t))
        return iter([pairs])

    def matching_score(pairs):
        hours = [0.0 if c == t else float(move_time_hours(inst, c, t)) for c, t in pairs]
        return max(hours, default=0.0) if parallel else sum(hours)

    def timeline_for(pairs, order):
        clock, timeline = 0.0, []
        crew_location = crew_start_site
        # Stationary vehicles are immediately available independently of queue.
        for c, t in pairs:
            if c == t:
                timeline.append({"from": c, "to": t, "depart_h": 0.0,
                                 "travel_h": 0.0, "ready_h": 0.0, 'crew_reposition_h':0.0,"in_place": True})
        for idx in order:
            c, t = pairs[idx]
            hours = float(move_time_hours(inst, c, t))
            reposition = 0.0 if parallel or crew_location is None else round(
                crew_drive_hours(inst,crew_location,c)*travel_time_multiplier,2)
            depart = 0.0 if parallel else clock + reposition
            timeline.append({"from": c, "to": t, "depart_h": round(depart, 2),
                             "travel_h": round(hours, 2), "ready_h": round(depart + hours, 2),
                             'crew_reposition_h':reposition,"in_place": False})
            if not parallel:
                clock = depart + hours
                crew_location = t
        makespan = max((x["ready_h"] for x in timeline), default=0.0)
        return timeline, makespan

    cand_ids = sorted(s.id for s in inst.candidate_sites() if s.id not in blocked)
    k = min(fleet, len(cand_ids))
    quick = []
    # Exact action space includes idling vehicles. Requiring all healthy
    # vehicles to relocate can exclude a useful partial response under a tight
    # deadline, especially when a current deployment site becomes unavailable.
    sizes = range(k + 1) if mode == "exact" else [k]
    for size in sizes:
        for combo in itertools.combinations(cand_ids, size):
            sol = _assign(shocked, _active_sites(shocked, combo, blocked),
                          0, max_minutes, capacity)
            quick.append((unmet_raw(sol), combo))
    quick.sort()
    counts["destination_sets_total"] = len(quick)
    if mode == "heuristic":
        quick = quick[:max(1, top_combos)]

    for lower_bound, combo in quick:
        # Capacities after travel cannot exceed capacities at zero downtime.
        # Equality alone cannot prune because response time is a tie-breaker.
        if lower_bound > best["_raw"] + 1e-8 or (
                abs(lower_bound - best["_raw"]) <= 1e-8 and best["total_hours"] == 0.0):
            counts["destination_sets_pruned_by_bound"] += 1
            continue
        counts["destination_sets_evaluated"] += 1
        matchings = generate_matchings(combo)
        if mode == "heuristic":
            matchings = sorted(matchings, key=matching_score)[:max(1, top_matchings)]
        for pairs in matchings:
            counts["matchings_generated"] += 1
            moving = tuple(i for i, (c, t) in enumerate(pairs) if c != t)
            if parallel:
                orders = [moving]
            elif mode == "exact" or len(moving) <= 3:
                orders = itertools.permutations(moving)
            else:
                orders = [moving]
            for order in orders:
                counts["timelines_tested"] += 1
                timeline, total = timeline_for(pairs, order)
                if total > budget_hours + 1e-9:
                    continue
                counts["deadline_feasible_timelines"] += 1
                sites = _active_sites(shocked, combo, blocked)
                ready = {m["to"]: m["ready_h"] for m in timeline}
                caps = {}
                for site in sites:
                    site = site_on_day(site, 0)
                    if site.id not in ready:
                        continue
                    cap = (float(site.capacity) if site.extra.get("capacity_is_explicit") or
                           (site.capacity and site.capacity > 0) else capacity)
                    caps[site.id] = {h: capacity_on_service_day(site, cap, h, 0, ready[site.id])
                                     for h in PERIODS}
                sol = _assign(shocked, sites, 0, max_minutes, capacity,
                              cap_by_period_override=caps)
                counts["assignment_lp_evaluations"] += 1
                raw = unmet_raw(sol)
                option = {"action": "relocate", "chosen": list(combo),
                          'worst_unmet_ratio_all':sol.metrics['worst_unmet_ratio_raw'],
                          "unmet": round(raw, 3), "timeline": timeline,
                          "total_hours": total, "n_moves": len(moving),
                          "feasible": True, "idle": len(combo) < fleet,
                          "capacity_by_period": caps, "_raw": raw}
                options.append(option)
                if (raw, total) < (best["_raw"], best["total_hours"]):
                    best = option

    gain = round(no_move["_raw"] - best["_raw"], 3)
    # All plans, including no-move, are explicitly feasible capacity allocations.
    result = {
        "shock_districts": low, "shock_multiplier": mult,
        "down_site": down_site, "down_vehicle_at": down_vehicle_at,
        "fleet_nominal": p, "fleet_healthy": fleet,
        "base": {"chosen": list(base.chosen), "unmet": round(base.metrics["unmet_total"], 3)},
        "shock_only": round(solve_static(shocked, p, **kw).metrics["unmet_total"], 3),
        "no_move": {k: v for k, v in no_move.items() if k != "_raw"},
        "best": {k: v for k, v in best.items() if k != "_raw"},
        "response_gain": gain,
        "gain_definition": "no_move_unmet - best_feasible_unmet; paired identical shocked demand",
        "n_options": len(options), "n_feasible": len(options),
        "budget_hours": budget_hours, "feasible_any": True, "parallel": parallel,
        "search": {"requested_mode": search_mode, "mode": mode,
                   "optimality_status": "exact_for_stated_discrete_model" if mode == "exact" else "heuristic_no_global_certificate",
                   "top_combos": None if mode == "exact" else max(1, top_combos),
                   "top_matchings": None if mode == "exact" else max(1, top_matchings),
                   **counts},
        "response_start_hour": 9.0, "service_day_end_hour": 33.0,
        "travel_time_multiplier": travel_time_multiplier,
        "initial_deployment_source": "specified_before_shock" if initial_chosen is not None else "unshocked_static_plan",
        "capacity_note": "daily_capacity/original_open_hours times operating-window overlap after arrival; 09:00-next09:00 service day",
        "travel_note": "assumed straight-line distance/speed plus setup; scheduled/observed road travel not available",
        "staffing_note": "parallel assumes one driver/setup team per moving vehicle; serial includes shared-team driving from previous destination to next origin",
        'crew_start_site':crew_start_site,
        'crew_start_assumption':'specified' if crew_start_was_provided else 'shared crew at first pre-incident deployed site; parallel crews at their vehicles',
        'origin_service_assumption':'moving units go offline at incident; waiting-to-depart service is conservatively not credited',
    }
    return result


def plan_response_legacy(inst: Instance, p: int = 3, mult: float = 1.8,
                         down_site: str | None = None, down_vehicle: str | None = None,
                         budget_hours: float = 24.0, max_minutes: float = 30.0,
                         capacity: float = 250.0, open_hours: float = 10.0) -> Dict[str, object]:
    """Compatibility: down_vehicle identifies the failed vehicle's original site."""
    return plan_response(inst, p, mult=mult, down_site=down_site,
                         down_vehicle_at=down_vehicle, budget_hours=budget_hours,
                         max_minutes=max_minutes, capacity=capacity, open_hours=open_hours)
