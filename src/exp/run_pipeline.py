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
from ..mch.disruption import plan_response
from ..mch.policy import plan_investment
from ..mch.static import solve_static, sweep_p
from ..mch.diagnostics import access_gap
from ..mch.loaders import load_instance
from ..mch.dynamic import solve_week_dp
from ..mch.synthetic import build_instance
from ..mch.validate import run_all


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p", type=int, default=3, help="购置枢纽数")
    ap.add_argument("--max-minutes", type=float, default=30.0)
    ap.add_argument("--capacity", type=float, default=250.0, help="Fallback visits/day only when a site has no explicit capacity; not an override")
    ap.add_argument("--seed", type=int, default=2027)
    ap.add_argument("--data", choices=["csv", "synthetic"], default="csv")
    ap.add_argument("--scenario", default="base", choices=["low", "base", "high"])
    ap.add_argument("--access-mode", default="walk_min", choices=["walk_min", "transit_min", "drive_min"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--q3-top-k", type=int, default=0)
    ap.add_argument("--annual-budget", type=float, default=4_000_000, help="ASSUME annual USD including operations")
    ap.add_argument("--real-network", action="store_true")
    ap.add_argument("--start-date", default="2026-07-20")
    a = ap.parse_args(argv)

    out = Path(a.out)


    out.mkdir(parents=True, exist_ok=True)

    from ..mch import runmeta
    runmeta.write(out, vars(a))

    if a.data == "csv":
        inst = load_instance(scenario=a.scenario, access_mode=a.access_mode)
    else:
        if a.scenario != 'base':
            raise ValueError('synthetic generator supports only scenario=base; use CSV for low/high')
        inst = build_instance(seed=a.seed, access_mode=a.access_mode)
        demand_mod.fill_demand(inst)
        inst = demand_mod.calibrate(inst, target_total_daily=292.8)  # 2025 全季平均人次/日
    if a.real_network:
        from ..mch.realnet import build_real_instance
        if a.data != 'csv':
            raise ValueError('--real-network requires --data csv')
        inst = build_real_instance(access_mode=a.access_mode, scenario=a.scenario, start_date=a.start_date)

    problems = run_all(inst, p=a.p)
    if problems:
        print("实例校验失败:", problems)
        return 2

    # Q1 缺口
    q1 = solve_static(inst, 0, max_minutes=a.max_minutes, capacity=a.capacity)
    # Q2 选址 + 边际收益
    q2 = solve_static(inst, a.p, max_minutes=a.max_minutes, capacity=a.capacity)
    curve = sweep_p(inst, pmax=len(inst.candidate_sites()), max_minutes=a.max_minutes, capacity=a.capacity)
    # Q3 动态
    # R3：与独立 runner 共用唯一实现（DP），避免两套动态口径
    week = solve_week_dp(inst, a.p, max_minutes=a.max_minutes, capacity=a.capacity, top_k=a.q3_top_k)
    days = week["schedule"]
    # Q4 中断
    inst_for_q4 = copy.deepcopy(inst)   # 情景隔离：Q4 的冲击不得污染 Q5
    fixed_ids = {s.id for s in inst.fixed_sites() if s.kind in ('cooling','respite')}
    down_site = max(fixed_ids, key=lambda sid: (q2.served_by_site.get(sid,0),sid)) if fixed_ids else None
    q4 = plan_response(inst_for_q4, a.p, max_minutes=a.max_minutes, capacity=a.capacity,
                       down_site=down_site, budget_hours=24, initial_chosen=q2.chosen)
    # Q5 五年
    q5 = plan_investment(inst, [a.annual_budget]*5, [1,1.03,1.06,1.09,1.12],
                         p_start=a.p, p_max=len(inst.candidate_sites()),
                         max_minutes=a.max_minutes, capacity=a.capacity)

    summary = {
        "instance": {"districts": len(inst.districts), "sites": len(inst.sites),
                     "candidates": len(inst.candidate_sites()), "days": inst.horizon_days,
                     "note": inst.meta.get("note"), "data": a.data, "scenario": a.scenario, "access_mode": a.access_mode},
        "q1_access_gap": access_gap(inst, a.max_minutes),
        "q1_baseline_no_mch": q1.metrics,
        "q2_static": {"chosen": q2.chosen, **q2.metrics},
        "q3_dynamic": days,
        "q3_static_total_unmet": week["static_total_unmet"],
        "q3_dynamic_total_unmet": week["dynamic_total_unmet"],
        "q3_search_status": week["search_status"],
        "q3_assumptions":week["assumptions"],
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
    print("=== Q3 动态（统一 DP）===")
    print(f"  静态七日 {week['static_total_unmet']:.1f} -> 动态 {week['dynamic_total_unmet']:.1f}")
    for s in days:
        print(f"  day{s['day']}: {s['combo']}  unmet={s['unmet']:.0f}  moves={s['moves']}")
    print("=== Q4 中断 ===")
    print(json.dumps({k: q4.get(k) for k in ("shock_districts","down_site","response_gain","search")},
                     ensure_ascii=False))
    print("=== Q5 五年 ===")
    for row in q5['rows']:
        print("  ", row)
    print(f"\n结果写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
