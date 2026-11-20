"""Q5 investment planning with separate owned stock and active operations.

All costs and future heat paths are assumptions.  Exactness refers only to the
declared finite action set and a completely specified future scenario; it is not
an empirical forecast, a stochastic optimum, or a permit-ready investment plan.
"""
from __future__ import annotations

import copy
import math
from collections.abc import Callable, Sequence
from typing import Any

from .schema import Instance
from .static import solve_static

COST = {
    "hub_buy": 80_000,
    "hub_ops": 120_000,
    "extend_21": 1_500_000,
    "extend_22": 2_500_000,
    "shuttle": 400_000,
}


def evaluate(inst: Instance, p: int, extend_to: float | None, shuttle: bool,
             **solver_kwargs: Any) -> tuple[float, float]:
    """Representative-day unmet visits and worst district unmet proportion.

    The no-intervention case preserves the input operating hours.  An extension
    extends eligible daytime indoor cooling sites, without shortening sites
    already open later.  Daily capacity stays fixed, so this changes timing,
    not the assumed daily throughput.  Shuttle is only an access-threshold
    scenario (30 -> 45 minutes), not a simulated transport service.
    """
    local = copy.deepcopy(inst)
    if extend_to is not None:
        for site in local.sites:
            if site.kind != "cooling":
                continue
            calendar = (site.extra or {}).get("calendar_by_day")
            if calendar is not None:
                for rule in calendar.values():
                    # An extension buys additional hours on a known operating
                    # date. Unknown/explicitly closed days are never opened by
                    # inference, and overnight closing clocks are not moved.
                    op, cl = rule.get("open_hour", 0), rule.get("close_hour", 0)
                    if rule.get("status", "").startswith("open_") and cl > op:
                        rule.setdefault("source_close_hour", cl)
                        rule["close_hour"] = max(cl, float(extend_to))
                        rule["status"] = "open_policy_assumption"
                        rule["policy_source"] = "ASSUME_ANNUAL_EXTENSION_CONTRACT"
            elif site.close_hour > site.open_hour:
                site.close_hour = max(site.close_hour, float(extend_to))
    options = dict(solver_kwargs)
    if shuttle:
        options["max_minutes"] = float(options.get("shuttle_max_minutes", 45.0))
    else:
        options.setdefault("max_minutes", 30.0)
    options.pop("shuttle_max_minutes", None)
    sol = solve_static(local, p, **options)
    return float(sol.metrics['unmet_total_raw']), float(sol.metrics['worst_unmet_ratio_raw'])


def annual_cost(active: int, extend_to: float | None, shuttle: bool,
                buy: int = 0, costs: dict[str, float] | None = None) -> dict[str, float]:
    """Full current-year capital and operating expenditure in assumed USD/year."""
    costs = COST if costs is None else costs
    if active < 0 or buy < 0 or int(active) != active or int(buy) != buy:
        raise ValueError("active and buy must be nonnegative integer vehicle counts")
    if extend_to not in (None, 21, 21.0, 22, 22.0):
        raise ValueError("extension action must be None, 21 or 22")
    if any(not math.isfinite(float(costs[k])) or costs[k] < 0 for k in COST):
        raise ValueError("cost assumptions must be finite and nonnegative")
    ext = 0.0 if extend_to is None else float(costs["extend_21" if extend_to <= 21 else "extend_22"])
    result = {
        "capital": buy * float(costs["hub_buy"]),
        "hub_opex": active * float(costs["hub_ops"]),
        "extend": ext,
        "shuttle": float(costs["shuttle"]) if shuttle else 0.0,
    }
    result["total"] = sum(result.values())
    return result


def scenario_evaluator(inst: Instance, heat_multipliers: Sequence[float],
                       **solver_kwargs: Any) -> Callable[[int, int, float | None, bool], tuple[float, float]]:
    """Memoized service lookup, reusable across budgets and decision strategies."""
    cache: dict[tuple[int, int, float | None, bool], tuple[float, float]] = {}
    yearly_instances: dict[int, Instance] = {}

    def lookup(i: int, active: int, extension: float | None, shuttle: bool) -> tuple[float, float]:
        key = (i, active, extension, shuttle)
        if key not in cache:
            if i not in yearly_instances:
                local = copy.deepcopy(inst)
                local.demand = {k: v * float(heat_multipliers[i]) for k, v in inst.demand.items()}
                yearly_instances[i] = local
            cache[key] = evaluate(yearly_instances[i], active, extension, shuttle, **solver_kwargs)
        return cache[key]

    lookup.cache = cache  # type: ignore[attr-defined]
    return lookup


def plan_investment(inst: Instance | None, budgets: Sequence[float],
                    heat_multipliers: Sequence[float], p_start: int = 2,
                    p_max: int = 8, costs: dict[str, float] | None = None,
                    strategy: str = "dp", years: Sequence[int] | None = None,
                    operating_days: float | Sequence[float] = 1.0,
                    evaluator: Callable[[int, int, float | None, bool], tuple[float, float]] | None = None,
                    **solver_kwargs: Any) -> dict[str, Any]:
    """Plan a finite horizon, returning ``{'rows': ..., 'summary': ...}``.

    State O is owned stock; action A is active fleet, E is a renewable annual
    extension contract and S is a renewable access-support scenario. Purchases
    B and active operations A are independent: O'=O+B and 0<=A<=O'. Idle assets
    remain owned. No retirement, salvage,
    maintenance of stored units, procurement delay, inflation, or budget carry
    over is modeled: these are explicit assumptions, not measured zero costs.

    ``dp`` minimizes (cumulative weighted unmet visits, cumulative weighted
    worst-district unmet proportion, total spend) over the full finite set.
    ``rolling`` minimizes that year's same tuple, and ``maintain`` permits only
    existing assets with no extension/shuttle.  All receive identical exogenous
    demand paths and annual budgets.  Default operating_days=1 avoids turning
    a single modeled day into a claimed annual forecast.
    """
    n = len(budgets)
    if n == 0 or len(heat_multipliers) != n:
        raise ValueError("nonempty budgets and heat_multipliers must have equal lengths")
    if int(p_start) != p_start or int(p_max) != p_max or not 0 <= p_start <= p_max:
        raise ValueError("require integer 0 <= p_start <= p_max")
    if inst is not None and p_max > len(inst.candidate_sites()):
        raise ValueError("p_max exceeds the number of candidate deployment locations")
    if any(not math.isfinite(float(x)) or x < 0 for x in (*budgets, *heat_multipliers)):
        raise ValueError("budgets and heat multipliers must be finite and nonnegative")
    if strategy not in {"dp", "rolling", "maintain"}:
        raise ValueError("strategy must be dp, rolling or maintain")
    year_values = list(range(2027, 2027 + n)) if years is None else list(years)
    days = [float(operating_days)] * n if isinstance(operating_days, (int, float)) else list(operating_days)
    if len(year_values) != n or len(days) != n or any(not math.isfinite(x) or x <= 0 for x in days):
        raise ValueError("years/operating_days must match the horizon; days must be positive")
    costs = dict(COST if costs is None else costs)
    annual_cost(0, None, False, 0, costs)  # validate all cost fields even for a zero-budget plan
    if evaluator is None:
        if inst is None:
            raise ValueError("an instance or explicit service evaluator is required")
        evaluator = scenario_evaluator(inst, heat_multipliers, **solver_kwargs)

    # Each state retains only its best path: future feasible actions depend on
    # owned stock alone, since annual service contracts can expire/cancel.
    paths: dict[int, tuple[tuple[float, float, float], list[dict[str, Any]]]] = {
        p_start: ((0.0, 0.0, 0.0), [])
    }
    evaluated_actions = 0
    for i, year in enumerate(year_values):
        next_paths: dict[int, tuple[tuple[float, float, float], list[dict[str, Any]]]] = {}
        for owned, (objective, previous_rows) in paths.items():
            candidates = []
            max_stock = owned if strategy == "maintain" else p_max
            extensions = (None,) if strategy == "maintain" else (None, 21.0, 22.0)
            shuttles = (False,) if strategy == "maintain" else (False, True)
            for stock_after_purchase in range(owned, max_stock + 1):
                buy = stock_after_purchase - owned
                for active in range(stock_after_purchase + 1):
                    for extension in extensions:
                        for shuttle in shuttles:
                            cost = annual_cost(active, extension, shuttle, buy, costs)
                            if cost["total"] > float(budgets[i]) + 1e-8:
                                continue
                            unmet, worst = evaluator(i, active, extension, shuttle)
                            if not math.isfinite(unmet) or unmet < 0 or not 0 <= worst <= 1:
                                raise ValueError("service evaluator returned invalid unmet demand or proportion")
                            evaluated_actions += 1
                            candidates.append((unmet * days[i], worst * days[i], cost["total"],
                                               active, extension, shuttle, buy, cost, unmet, worst))
            if strategy != "dp":
                candidates = [min(candidates, key=lambda x: x[:3])]
            for option in candidates:
                weighted_unmet, weighted_worst, spend, active, extension, shuttle, buy, cost, unmet, worst = option
                stock = owned + buy
                key = (objective[0] + weighted_unmet, objective[1] + weighted_worst, objective[2] + spend)
                # A tie is resolved deterministically by enumeration order.
                if stock in next_paths and not key < next_paths[stock][0]:
                    continue
                baseline_unmet, _ = evaluator(i, owned, None, False)
                row = {
                    "year": year, "strategy": strategy,
                    "budget": float(budgets[i]), "heat_multiplier": float(heat_multipliers[i]),
                    "operating_days": days[i], "owned_before": owned, "owned": stock,
                    "active": active, "fleet": active, "buy": buy, "retire": 0,
                    "idled": stock - active, "extend_to": extension, "shuttle": shuttle,
                    "action": f"active={active},buy={buy},ext={extension},shuttle={int(shuttle)}",
                    "total_cost": spend, "capital": cost["capital"], "hub_opex": cost["hub_opex"],
                    "extend_cost": cost["extend"], "shuttle_cost": cost["shuttle"],
                    "within_budget": spend <= float(budgets[i]) + 1e-8,
                    "unmet_before": baseline_unmet, "unmet_after": unmet,
                    "worst_after": worst, "gain": baseline_unmet - unmet,
                    "weighted_unmet_visits": weighted_unmet,
                }
                next_paths[stock] = (key, previous_rows + [row])
        paths = next_paths
    objective, rows = min(paths.values(), key=lambda x: x[0])
    summary = {
        "strategy": strategy,
        "optimality": "exact_finite_state_scenario" if strategy == "dp" else "myopic_finite_actions",
        "total_spend": objective[2],
        "total_opex": sum(r["hub_opex"] + r["extend_cost"] + r["shuttle_cost"] for r in rows),
        "weighted_unmet_visits": objective[0],
        "mean_representative_day_unmet": objective[0] / sum(days),
        "all_within_budget": all(r["within_budget"] for r in rows),
        "final_fleet": rows[-1]["active"], "final_owned": rows[-1]["owned"],
        "final_extend": rows[-1]["extend_to"], "final_unmet": rows[-1]["unmet_after"],
        "actions": [r["action"] for r in rows], "evaluated_feasible_actions": evaluated_actions,
    }
    return {"rows": rows, "summary": summary, "cost_assumptions": costs,
            "scope": "Conditional representative-day service scenario; not validated annual demand or health outcomes.",
            "stock_assumptions": {"initial_procurement_sunk": True, "idle_stock_retained": True,
                                  "retirement_allowed": False, "storage_cost_assumed": 0,
                                  "procurement_lead_time_years_assumed": 0,
                                  "budget_carryover_allowed": False,
                                  "annual_contracts_can_cancel": True}}


def five_year_plan(inst: Instance, p_start: int = 2, p_max: int = 8,
                   unmet_trigger: float | None = None, min_gain: float | None = None,
                   min_ratio: float | None = None, **kwargs: Any) -> list[dict[str, Any]]:
    """Compatibility wrapper for callers of the retired threshold-only rule.

    Old trigger arguments are rejected when supplied, rather than silently
    ignored.  Use explicit annual budgets and observed revision rules instead.
    """
    if any(x is not None for x in (unmet_trigger, min_gain, min_ratio)):
        raise ValueError("threshold-only Q5 policy retired; call plan_investment with explicit budgets")
    budgets = kwargs.pop("budgets", [4_000_000] * 5)
    heat = kwargs.pop("heat_multipliers", [1.00, 1.03, 1.06, 1.09, 1.12])
    return plan_investment(inst, budgets, heat, p_start=p_start, p_max=p_max, **kwargs)["rows"]
