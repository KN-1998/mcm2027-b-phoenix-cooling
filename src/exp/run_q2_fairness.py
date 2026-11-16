"""Q2 公平性分析：效率-公平前沿 + "是否留下高需求区"的判定。

用法：python -m src.exp.run_q2_fairness --p 3 --out results/q2_fairness
"""
from __future__ import annotations

import argparse, csv, json
from pathlib import Path

from ..mch.loaders import load_instance
from ..mch.static import efficiency_equity_frontier, solve_static, solve_static_fair


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p", type=int, default=3)
    ap.add_argument("--scenario", default="base", choices=["low", "base", "high"])
    ap.add_argument("--access-mode", default="walk_min", choices=["walk_min", "transit_min", "drive_min"])
    ap.add_argument("--max-minutes", type=float, default=30.0)
    ap.add_argument("--capacity", type=float, default=250.0)
    ap.add_argument("--exclude-districts", default="", help="逗号分隔，结构性无法靠枢纽覆盖的区")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    inst = load_instance(scenario=a.scenario, access_mode=a.access_mode)
    excl = [x for x in a.exclude_districts.split(",") if x]
    structural = {d.id: inst.demand[(d.id, 0)] for d in inst.districts if d.id in excl}
    if excl:
        inst.demand = {k: (0.0 if k[0] in excl else v) for k, v in inst.demand.items()}
    kw = dict(max_minutes=a.max_minutes, capacity=a.capacity)

    base = solve_static(inst, a.p, **kw)                      # 效率优先（现状）
    fair = solve_static_fair(inst, a.p, equity_cap=0.0, **kw)  # 严格公平（max-min）
    front = efficiency_equity_frontier(inst, a.p, **kw)

    with (out / "frontier.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(front[0].keys())); w.writeheader(); w.writerows(front)

    summary = {
        "instance": {"scenario": a.scenario, "access_mode": a.access_mode, "p": a.p,
                     "excluded_structural_districts": excl},
        "structural_demand_excluded": structural,
        "efficiency_first": {"chosen": base.chosen, **base.metrics},
        "max_min": {"chosen": fair.chosen, **fair.metrics},
        "left_behind": {
            "worst_ratio_efficiency": base.metrics["worst_unmet_ratio"],
            "worst_ratio_maxmin": fair.metrics["worst_unmet_ratio"],
            "coverage_gain": round(base.metrics["coverage_rate"] - 0.0, 4),
            "verdict": ("average access improves while the worst district stays at "
                        f"{base.metrics['worst_unmet_ratio']:.0%} unmet"
                        if base.metrics["worst_unmet_ratio"] >= 0.99 else "no district fully left behind"),
        },
        "frontier": front,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== 效率优先 p={a.p} === chosen={base.chosen}")
    print(f"  覆盖 {base.metrics['coverage_rate']:.3f}  最差区未满足率 {base.metrics['worst_unmet_ratio']:.3f}  Gini {base.metrics['gini_coverage']:.3f}")
    print(f"=== max-min p={a.p} === chosen={fair.chosen}")
    print(f"  覆盖 {fair.metrics['coverage_rate']:.3f}  最差区未满足率 {fair.metrics['worst_unmet_ratio']:.3f}")
    print("=== 前沿 ===")
    for r in front:
        print(f"  cap={r['equity_cap']:.2f} -> 未满足 {r['unmet_total']:7.1f}  最差区 {r['worst_unmet_ratio']:.3f}  覆盖 {r['coverage_rate']:.3f}  可行={r['cap_met']}  {r['chosen']}")
    print(json.dumps(summary["left_behind"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
