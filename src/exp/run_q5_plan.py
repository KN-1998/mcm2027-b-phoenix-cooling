"""Q5 finite-state scenario planning, rolling and existing-stock baselines.

Run: python -m src.exp.run_q5_plan --out results/q5_plan
Inputs, prices, budgets and future heat paths are conditional assumptions.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from ..mch import runmeta
from ..mch.loaders import load_instance
from ..mch.policy import COST, annual_cost, evaluate, plan_investment, scenario_evaluator

BUDGETS = {"low": 2_000_000, "base": 4_000_000, "high": 6_000_000}
HEAT = {
    "mild": [1.00, 1.00, 1.02, 1.02, 1.03],
    "base": [1.00, 1.03, 1.06, 1.09, 1.12],
    "severe": [1.05, 1.12, 1.20, 1.28, 1.36],
}


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p0", type=int, default=2, help="Initially owned stock; original purchase is sunk")
    parser.add_argument("--pmax", type=int, default=8)
    parser.add_argument("--operating-days", type=float, default=1,
                        help="ASSUME repeated representative days/year; 1 reports an unannualized planning score")
    parser.add_argument("--cost-scales", default="0.5,0.75,1,1.25,1.5,2",
                        help="Joint hub purchase/operations price multipliers; contracts held fixed")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    inst = load_instance()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    runmeta.write(out, vars(args), {"experiment": "Q5 finite-state DP and matched-action baselines"})
    evaluators = {name: scenario_evaluator(inst, heat) for name, heat in HEAT.items()}
    rows, baseline_rows, comparisons = [], [], []
    summaries, baseline_summaries = {}, {}
    for heat_name, heat in HEAT.items():
        for budget_name, budget in BUDGETS.items():
            scenario = f"{budget_name}/{heat_name}"
            plans = {}
            for strategy in ("dp", "rolling", "maintain"):
                result = plan_investment(inst, [budget] * 5, heat, p_start=args.p0,
                                         p_max=args.pmax, strategy=strategy,
                                         operating_days=args.operating_days,
                                         evaluator=evaluators[heat_name])
                plans[strategy] = result
                decorated = [{"budget_scenario": budget_name, "heat_scenario": heat_name, **r}
                             for r in result["rows"]]
                if strategy == "dp":
                    rows.extend(decorated)
                    summaries[scenario] = result["summary"]
                else:
                    baseline_rows.extend(decorated)
                    baseline_summaries[f"{scenario}/{strategy}"] = result["summary"]
            dp, rolling, maintain = (plans[s]["summary"] for s in ("dp", "rolling", "maintain"))
            comparisons.append({"scenario": scenario,
                                "dp_unmet_score": dp["weighted_unmet_visits"],
                                "rolling_unmet_score": rolling["weighted_unmet_visits"],
                                "maintain_unmet_score": maintain["weighted_unmet_visits"],
                                "dp_gain_vs_rolling": rolling["weighted_unmet_visits"] - dp["weighted_unmet_visits"],
                                "dp_gain_vs_maintain": maintain["weighted_unmet_visits"] - dp["weighted_unmet_visits"],
                                "dp_total_spend": dp["total_spend"],
                                "rolling_total_spend": rolling["total_spend"],
                                "maintain_total_spend": maintain["total_spend"],
                                "all_budgets_feasible": all(p["summary"]["all_within_budget"] for p in plans.values())})
            print(f"{scenario:14} unmet score={dp['weighted_unmet_visits']:.3f}; "
                  f"DP gain vs rolling={comparisons[-1]['dp_gain_vs_rolling']:.3f}; "
                  f"owned/active={dp['final_owned']}/{dp['final_fleet']}; cost=${dp['total_spend']:,.0f}")

    sensitivity = []
    for scale in [float(x) for x in args.cost_scales.split(",") if x.strip()]:
        costs = dict(COST)
        costs["hub_buy"] *= scale
        costs["hub_ops"] *= scale
        result = plan_investment(inst, [BUDGETS["base"]] * 5, HEAT["base"],
                                 p_start=args.p0, p_max=args.pmax, costs=costs,
                                 operating_days=args.operating_days, evaluator=evaluators["base"])
        summary = result["summary"]
        sensitivity.append({"hub_cost_scale": scale, "first_active": result["rows"][0]["active"],
                            "first_buy": result["rows"][0]["buy"],
                            "first_extend": result["rows"][0]["extend_to"],
                            "first_shuttle": result["rows"][0]["shuttle"],
                            "final_owned": summary["final_owned"], "final_active": summary["final_fleet"],
                            "unmet_score": summary["weighted_unmet_visits"],
                            "total_spend": summary["total_spend"],
                            "actions": " | ".join(summary["actions"])})

    write_csv(out / "plan.csv", rows)
    write_csv(out / "baselines.csv", baseline_rows)
    write_csv(out / "comparison.csv", comparisons)
    write_csv(out / "cost_sensitivity.csv", sensitivity)
    payload = {
        "cost_assumptions": COST, "budgets": BUDGETS, "heat": HEAT,
        "operating_days_assumed": args.operating_days,
        "scope": "Conditional service scenario; not validated annual visits, avoided deaths or a procurement quote.",
        "objective": "Lexicographic cumulative weighted unmet visits, cumulative weighted worst district ratio, total expenditure",
        "exactness": "DP exact over finite annual actions and the specified fully known scenario, conditional on inner service solver",
        "actions": "buy=0..pmax-owned; active=0..owned+buy; annual extension=None/21/22; shuttle=False/True",
        "stock_assumptions": result["stock_assumptions"],
        "note": "All prices/budgets/heat multipliers ASSUME. Contracts may cancel annually; idle stock retained; no salvage, storage cost, lead time or budget carryover.",
        "plans": summaries, "baselines": baseline_summaries,
        "evaluator_cache_entries": {h: len(e.cache) for h, e in evaluators.items()},
    }
    (out / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
