"""Q5 五年投资与运营计划（2027–2031）。

设计原则（对应第三/四轮审查）：
1. **每年重新决策**，而不是重复求同一个第 0 日问题；
2. 四类行动：保留 / 增购枢纽 / 延长固定中心营业 / 接驳（可達性改善）；
3. 三档预算 × 三档热浪强度情景；
4. 输出每年的**预算可行性、花费、未满足量**与**可观察触发信号**；
5. 成本参数全部标 `ASSUME` 并给区间——因为缺"移动枢纽实际成本"（M9），
   所以结论只做**排序建议**，不做绝对金额承诺。

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

# ---- 成本假设（ASSUME；缺本地实测，只用于排序）----
COST = {
    "hub_buy": 80_000,       # 单台移动枢纽购置（ASSUME；Tempe 案例为捐赠 $15k）
    "hub_ops": 120_000,      # 单台年运营（2 FTE + 燃油 + 维护，ASSUME）
    "extend_21": 1_500_000,  # 全城固定中心延到 21:00（ASSUME，量级参考 ~$4.3M 项目）
    "extend_22": 2_500_000,  # 延到 22:00（ASSUME）
    "shuttle": 400_000,      # 接驳/外展（ASSUME）
}

BUDGETS = {"low": 2_000_000, "base": 4_000_000, "high": 6_000_000}
# 热浪强度：对潜在需求的年乘数（ASSUME，2027 起）
HEAT = {
    "mild":     [1.00, 1.00, 1.02, 1.02, 1.03],
    "base":     [1.00, 1.03, 1.06, 1.09, 1.12],
    "severe":   [1.05, 1.12, 1.20, 1.28, 1.36],
}


def unmet_for(inst, p: int, extend_to: float | None, shuttle: bool) -> float:
    """给定当年配置，算未满足人次/日（day0）。"""
    for s in inst.sites:
        if s.kind == "cooling":
            s.close_hour = 17.0 if extend_to is None else float(extend_to)
        if s.kind == "candidate_mch":
            s.close_hour = 19.0
    thr = 30.0
    if shuttle:
        # 接驳：把 30 分钟阈值放宽到 45 分钟，作为"最后一公里"改善的代理
        thr = 45.0
    return solve_static(inst, p, max_minutes=thr).metrics["unmet_total"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", type=int, default=2, help="2027 起始车队")
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
                mult = mults[i]
                inst = load_instance()
                inst.demand = {k: v * mult for k, v in inst.demand.items()}
                cur = unmet_for(inst, p, ext, shuttle)

                # 候选动作（含"保留"）
                cands = [{"action": "keep", "cost": 0, "p": p, "ext": ext, "shuttle": shuttle,
                          "note": "维持现状"}]
                if p < a.pmax:
                    cands.append({"action": "buy_hub", "cost": COST["hub_buy"] + COST["hub_ops"],
                                  "p": p + 1, "ext": ext, "shuttle": shuttle,
                                  "note": "增购 1 台（购置+首年运营）"})
                if ext is None:
                    cands.append({"action": "extend_21", "cost": COST["extend_21"],
                                  "p": p, "ext": 21.0, "shuttle": shuttle,
                                  "note": "固定中心延到 21:00"})
                if ext in (None, 21.0):
                    cands.append({"action": "extend_22", "cost": COST["extend_22"],
                                  "p": p, "ext": 22.0, "shuttle": shuttle,
                                  "note": "固定中心延到 22:00"})
                if not shuttle:
                    cands.append({"action": "shuttle", "cost": COST["shuttle"],
                                  "p": p, "ext": ext, "shuttle": True,
                                  "note": "接驳/外展（阈值 30→45 分钟代理）"})

                scored = []
                for c in cands:
                    after = unmet_for(inst, c["p"], c["ext"], c["shuttle"])
                    gain = cur - after
                    c["after"] = round(after, 2)
                    c["gain"] = round(gain, 2)
                    c["per_musd"] = round(gain / (c["cost"] / 1e6), 1) if c["cost"] else None
                    scored.append(c)

                affordable = [c for c in scored if c["cost"] <= budget]
                best = max(affordable, key=lambda c: (c["gain"], -c["cost"]))
                p, ext, shuttle = best["p"], best["ext"], best["shuttle"]

                # 可观察触发信号：当年未满足率或用车的紧急程度
                worst = solve_static(inst, p, max_minutes=30.0 if not shuttle else 45.0).metrics["worst_unmet_ratio"]
                trigger = []
                if worst >= 0.9:
                    trigger.append("最差区未满足率≥90%")
                if cur - best["after"] < 5:
                    trigger.append("本年动作收益<5 人次/日")
                rows.append({"budget_scenario": bname, "budget": budget,
                             "heat_scenario": hname, "year": year,
                             "action": best["action"], "note": best["note"],
                             "cost": best["cost"], "within_budget": best["cost"] <= budget,
                             "fleet": p, "extend_to": ext, "shuttle": shuttle,
                             "unmet_before": round(cur, 2), "unmet_after": best["after"],
                             "gain": best["gain"], "gain_per_musd": best["per_musd"],
                             "worst_unmet_ratio": round(worst, 4),
                             "trigger": ";".join(trigger)})

    with (out / "plan.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # 汇总：每条情景的五年累计花费与末年被满足量
    summary = {}
    for bname in BUDGETS:
        for hname in HEAT:
            sel = [r for r in rows if r["budget_scenario"] == bname and r["heat_scenario"] == hname]
            summary[f"{bname}/{hname}"] = {
                "total_spend": sum(r["cost"] for r in sel),
                "final_fleet": sel[-1]["fleet"],
                "final_extend": sel[-1]["extend_to"],
                "final_unmet": sel[-1]["unmet_after"],
                "actions": [r["action"] for r in sel],
            }
    (out / "summary.json").write_text(
        json.dumps({"cost_assumptions": COST, "budgets": BUDGETS, "heat": HEAT,
                    "plans": summary}, ensure_ascii=False, indent=2), encoding="utf-8")

    for k, v in summary.items():
        print(f"{k:16s} 花费 ${v['total_spend']:>10,} 车队 {v['final_fleet']} "
              f"延时 {v['final_extend']} 末年未满足 {v['final_unmet']:.1f}  {v['actions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
