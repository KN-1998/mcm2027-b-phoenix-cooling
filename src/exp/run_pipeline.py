"""端到端流水线：Q1 缺口 -> Q2 选址 -> Q3 动态 -> Q4 中断 -> Q5 五年。

用法：
    python -m src.exp.run_pipeline --p 3 --out results/run_demo
所有输出写到 out 目录（json + csv），便于审计。
"""
from __future__ import annotations

import argparse, copy
import csv
import json
from pathlib import Path

from ..mch import demand as demand_mod
from ..mch import dynamic as dyn
from ..mch.disruption import run_disruption
from ..mch.policy import five_year_plan
from ..mch.static import solve_static, sweep_p
from ..mch.diagnostics import access_gap
from ..mch.loaders import load_instance
from ..mch.synthetic import build_instance
from ..mch.validate import run_all


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p", type=int, default=3, help="购置枢纽数")
    ap.add_argument("--max-minutes", type=float, default=30.0)
    ap.add_argument("--capacity", type=float, default=250.0)
    ap.add_argument("--seed", type=int, default=2027)
    ap.add_argument("--data", choices=["csv", "synthetic"], default="csv")
    ap.add_argument("--scenario", default="base", choices=["low", "base", "high"])
    ap.add_argument("--access-mode", default="walk_min", choices=["walk_min", "transit_min", "drive_min"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out)


    out.mkdir(parents=True, exist_ok=True)

    from ..mch import runmeta
    runmeta.write(out, vars(a))

    if a.data == "csv":
        inst = load_instance(scenario=a.scenario, access_mode=a.access_mode)
    else:
        inst = build_instance(seed=a.seed)
        demand_mod.fill_demand(inst)
        inst = demand_mod.calibrate(inst, target_total_daily=292.8)  # 2025 全季平均人次/日

    problems = run_all(inst, p=a.p)
    if problems:
        print("实例校验失败:", problems)
        return 2

    # Q1 缺口
    q1 = solve_static(inst, 0, max_minutes=a.max_minutes, capacity=a.capacity)
    # Q2 选址 + 边际收益
    q2 = solve_static(inst, a.p, max_minutes=a.max_minutes, capacity=a.capacity)
    curve = sweep_p(inst, pmax=8, max_minutes=a.max_minutes, capacity=a.capacity)
    # Q3 动态
    days = dyn.solve_dynamic(inst, a.p, max_minutes=a.max_minutes, capacity=a.capacity)
    # Q4 中断
    inst_for_q4 = copy.deepcopy(inst)   # 情景隔离：Q4 的冲击不得污染 Q5
    q4 = run_disruption(inst_for_q4, a.p, max_minutes=a.max_minutes, capacity=a.capacity)
    # Q5 五年
    q5 = five_year_plan(inst, p_start=max(1, a.p - 1), p_max=8,
                        max_minutes=a.max_minutes, capacity=a.capacity)

    summary = {
        "instance": {"districts": len(inst.districts), "sites": len(inst.sites),
                     "candidates": len(inst.candidate_sites()), "days": inst.horizon_days,
                     "note": inst.meta.get("note"), "data": a.data, "scenario": a.scenario, "access_mode": a.access_mode},
        "q1_access_gap": access_gap(inst, a.max_minutes),
        "q1_baseline_no_mch": q1.metrics,
        "q2_static": {"chosen": q2.chosen, **q2.metrics},
        "q3_dynamic": [{"day": s.day, "chosen": s.chosen, **s.metrics} for s in days],
        "q4_disruption": q4,
        "q5_plan": q5,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "marginal_curve.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(curve[0].keys()))
        w.writeheader(); w.writerows(curve)

    gap = access_gap(inst, a.max_minutes)
    print("=== Q1 access gaps (no indoor cooling within threshold) ===")
    print("  districts:", gap["zero_access_districts"])
    print("=== Q1 无 MCH 基线 ===")
    print(json.dumps(q1.metrics, ensure_ascii=False))
    print("=== Q2 p=%d ===" % a.p)
    print("选址:", q2.chosen)
    print(json.dumps(q2.metrics, ensure_ascii=False))
    print("=== Q3 动态（逐日选址）===")
    for s in days:
        print(f"  day{s.day}: {s.chosen}  unmet={s.metrics['unmet_total']:.0f}  cov={s.metrics['coverage_rate']:.3f}")
    print("=== Q4 中断 ===")
    print(json.dumps({k: q4[k] for k in ("shock_districts","down_site","delta_unmet","response_hours")}, ensure_ascii=False))
    print("=== Q5 五年 ===")
    for row in q5:
        print("  ", row)
    print(f"\n结果写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
