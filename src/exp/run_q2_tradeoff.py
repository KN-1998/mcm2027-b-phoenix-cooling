"""Q2 核心结果：效率 vs 公平的权衡表（p=1..4）。

输出 results/q2_tradeoff/tradeoff.csv，每行一个 (p, 策略)：
  strategy = efficiency_first | max_min
并给出"买公平"的代价：Δ未满足、Δ覆盖、最差区改善。
"""
from __future__ import annotations

import argparse, csv, json
from pathlib import Path

from ..mch.loaders import load_instance
from ..mch.static import solve_static, solve_static_fair


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="base", choices=["low", "base", "high"])
    ap.add_argument("--access-mode", default="walk_min", choices=["walk_min", "transit_min", "drive_min"])
    ap.add_argument("--max-minutes", type=float, default=30.0)
    ap.add_argument("--capacity", type=float, default=250.0)
    ap.add_argument("--pmax", type=int, default=4)
    ap.add_argument("--exclude-districts", default="D08")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    inst = load_instance(scenario=a.scenario, access_mode=a.access_mode)
    excl = [x for x in a.exclude_districts.split(",") if x]
    structural = {d.id: round(inst.demand[(d.id, 0)], 2) for d in inst.districts if d.id in excl}
    if excl:
        inst.demand = {k: (0.0 if k[0] in excl else v) for k, v in inst.demand.items()}
    kw = dict(max_minutes=a.max_minutes, capacity=a.capacity)

    rows, trade = [], []
    for p in range(1, a.pmax + 1):
        eff = solve_static(inst, p, **kw)
        fair = solve_static_fair(inst, p, equity_cap=0.0, **kw)
        for name, sol in (("efficiency_first", eff), ("max_min", fair)):
            rows.append({"p": p, "strategy": name,
                         "unmet_total": sol.metrics["unmet_total"],
                         "coverage_rate": sol.metrics["coverage_rate"],
                         "worst_unmet_ratio": sol.metrics["worst_unmet_ratio"],
                         "gini_coverage": sol.metrics["gini_coverage"],
                         "chosen": ",".join(sol.chosen)})
        trade.append({"p": p,
                      "unmet_cost": round(fair.metrics["unmet_total"] - eff.metrics["unmet_total"], 2),
                      "unmet_cost_pct": round(100 * (fair.metrics["unmet_total"] - eff.metrics["unmet_total"])
                                              / max(1e-9, eff.metrics["unmet_total"]), 1),
                      "coverage_loss_pp": round(100 * (eff.metrics["coverage_rate"] - fair.metrics["coverage_rate"]), 2),
                      "worst_before": eff.metrics["worst_unmet_ratio"],
                      "worst_after": fair.metrics["worst_unmet_ratio"],
                      "efficiency_pick": ",".join(eff.chosen),
                      "fair_pick": ",".join(fair.chosen)})

    with (out / "tradeoff.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with (out / "tradeoff_cost.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(trade[0].keys())); w.writeheader(); w.writerows(trade)
    (out / "summary.json").write_text(json.dumps({"scenario": a.scenario, "access_mode": a.access_mode,
        "excluded_structural": structural, "tradeoff": trade}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== 效率 vs 公平（{a.access_mode}, 阈值 {a.max_minutes:.0f} min, 已排除结构性区 {excl}）===")
    for t in trade:
        print(f"  p={t['p']}: 效率选 {t['efficiency_pick']:20s} 最差区 {t['worst_before']:.0%}"
              f"  ->  公平选 {t['fair_pick']:20s} 最差区 {t['worst_after']:.0%}"
              f"  | 代价 +{t['unmet_cost']:.1f} 人次/日 (+{t['unmet_cost_pct']:.0f}%), 覆盖 -{t['coverage_loss_pp']:.1f}pp")
    print(f"\n结构性无法覆盖（需非枢纽手段）: {structural}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
