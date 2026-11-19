"""Q5 五年投资与运营计划（2027–2031）——v2，补全年运营记账。

第五轮审查修正：
1. **存量设备每年都要计运营费**（v1 只在新购当年收费，等于后续免费运行）；
2. 预算约束按**当年完整支出**（资本开支 + 全部在役枢纽运维 + 延时 + 接驳）判断；
3. 允许"减车"（停运一台）作为候选，预算不足时不是默认免费继续；
4. `worst_unmet_ratio` 必须按**被选中的方案**重算，不能沿用最后一次评估的候选。

成本参数全部标 ASSUME（缺本地实测），因此只做排序建议。

用法：
    python -m src.exp.run_q5_plan --out results/q5_plan
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from ..mch import runmeta
from ..mch.loaders import load_instance
from ..mch.static import solve_static

# ---- 成本假设（ASSUME）----
COST = {
    "hub_buy": 80_000,       # 单台购置
    "hub_ops": 120_000,      # 单台**每年**运营
    "extend_21": 1_500_000,  # 全城固定中心延到 21:00（每年）
    "extend_22": 2_500_000,  # 延到 22:00（每年）
    "shuttle": 400_000,      # 接驳/外展（每年）
}

BUDGETS = {"low": 2_000_000, "base": 4_000_000, "high": 6_000_000}
HEAT = {
    "mild":   [1.00, 1.00, 1.02, 1.02, 1.03],
    "base":   [1.00, 1.03, 1.06, 1.09, 1.12],
    "severe": [1.05, 1.12, 1.20, 1.28, 1.36],
}


def evaluate(inst, p: int, extend_to, shuttle: bool):
    """返回 (unmet, worst)。**不修改 inst**（避免上一版"最后一个候选污染指标"的问题）。"""
    import copy
    local = copy.deepcopy(inst)
    for s in local.sites:
        if s.kind == "cooling":
            s.close_hour = 17.0 if extend_to is None else float(extend_to)
        if s.kind == "candidate_mch":
            s.close_hour = 19.0
    thr = 45.0 if shuttle else 30.0
    sol = solve_static(local, p, max_minutes=thr)
    return sol.metrics["unmet_total"], sol.metrics["worst_unmet_ratio"]


def annual_cost(p: int, extend_to, shuttle: bool, buy: int = 0) -> dict:
    opex = p * COST["hub_ops"]
    ext = 0 if extend_to is None else (COST["extend_21"] if extend_to <= 21 else COST["extend_22"])
    sh = COST["shuttle"] if shuttle else 0
    cap = buy * COST["hub_buy"]
    return {"capital": cap, "hub_opex": opex, "extend": ext, "shuttle": sh,
            "total": cap + opex + ext + sh}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", type=int, default=2, help="2027 期初车队（购置视为沉没成本）")
    ap.add_argument("--pmax", type=int, default=8)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    runmeta.write(out, vars(a))

    rows = []
    for bname, budget in BUDGETS.items():
        for hname, mults in HEAT.items():
            p, ext, shuttle = a.p0, None, False
            for i, year in enumerate(range(2027, 2032)):
                inst = load_instance()
                for k in list(inst.demand):
                    inst.demand[k] *= mults[i]

                cur_unmet, cur_worst = evaluate(inst, p, ext, shuttle)
                base_cost = annual_cost(p, ext, shuttle)

                cands = []

                def add(action, pp, ee, ss, buy, note):
                    c = annual_cost(pp, ee, ss, buy)
                    unmet, worst = evaluate(inst, pp, ee, ss)
                    cands.append({"action": action, "p": pp, "ext": ee, "shuttle": ss,
                                  "cost": c["total"], "cost_detail": c,
                                  "unmet": round(unmet, 2), "worst": round(worst, 4),
                                  "gain": round(cur_unmet - unmet, 2), "note": note})

                add("keep", p, ext, shuttle, 0, "维持现状（仍计运维）")
                if p < a.pmax:
                    add("buy_hub", p + 1, ext, shuttle, 1, "增购 1 台（含购置与全部运维）")
                if ext is None:
                    add("extend_21", p, 21.0, shuttle, 0, "固定中心延到 21:00")
                if ext in (None, 21.0):
                    add("extend_22", p, 22.0, shuttle, 0, "固定中心延到 22:00")
                if not shuttle:
                    add("shuttle", p, ext, True, 0, "接驳/外展（阈值 30→45 分钟代理）")
                if p > 1:
                    add("cut_hub", p - 1, ext, shuttle, 0, "停运 1 台以压运维")

                affordable = [c for c in cands if c["cost"] <= budget]
                if not affordable:
                    # 预算连运行现状都不够：只能减车，直到可行或到 1 台
                    affordable = [c for c in cands if c["action"] == "cut_hub"] or \
                                 [min(cands, key=lambda c: c["cost"])]
                best = max(affordable, key=lambda c: (c["gain"], -c["cost"]))
                p, ext, shuttle = best["p"], best["ext"], best["shuttle"]

                rows.append({"budget_scenario": bname, "budget": budget,
                             "heat_scenario": hname, "year": year,
                             "action": best["action"], "note": best["note"],
                             "total_cost": best["cost"],
                             "capital": best["cost_detail"]["capital"],
                             "hub_opex": best["cost_detail"]["hub_opex"],
                             "extend_cost": best["cost_detail"]["extend"],
                             "shuttle_cost": best["cost_detail"]["shuttle"],
                             "within_budget": best["cost"] <= budget,
                             "fleet": p, "extend_to": ext, "shuttle": shuttle,
                             "unmet_before": round(cur_unmet, 2),
                             "unmet_after": best["unmet"],
                             "worst_after": best["worst"],
                             "gain": best["gain"]})

    with (out / "plan.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    summary = {}
    for bname in BUDGETS:
        for hname in HEAT:
            sel = [r for r in rows if r["budget_scenario"] == bname and r["heat_scenario"] == hname]
            summary[f"{bname}/{hname}"] = {
                "total_spend": sum(r["total_cost"] for r in sel),
                "total_opex": sum(r["hub_opex"] + r["extend_cost"] + r["shuttle_cost"] for r in sel),
                "all_within_budget": all(r["within_budget"] for r in sel),
                "final_fleet": sel[-1]["fleet"],
                "final_extend": sel[-1]["extend_to"],
                "final_unmet": sel[-1]["unmet_after"],
                "actions": [r["action"] for r in sel],
            }
    (out / "summary.json").write_text(
        json.dumps({"cost_assumptions": COST, "budgets": BUDGETS, "heat": HEAT,
                    "note": "成本为 ASSUME；预算按当年完整支出（资本+全部运维+延时+接驳）判定",
                    "plans": summary}, ensure_ascii=False, indent=2), encoding="utf-8")

    for k, v in summary.items():
        print(f"{k:14s} 花费 ${v['total_spend']:>11,} (运维 ${v['total_opex']:>10,}) "
              f"车队 {v['final_fleet']} 延时 {v['final_extend']} "
              f"末年未满足 {v['final_unmet']:.1f} 全可行 {v['all_within_budget']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
