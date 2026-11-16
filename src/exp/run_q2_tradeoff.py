"""Q2 效率 vs 公平：正确口径版。

关键修正（对照审查意见）：
- 不再"把 D08 需求清零"来回避结构性问题，而是用 diagnostics.structural_set 明示；
- max-min 用二分求"可达的最小最差未满足率"，而不是强设 ε=0；
- 同时报 worst(全部) 与 worst(排除结构性不可达)。
"""
from __future__ import annotations

import argparse, csv, json
from pathlib import Path

from ..mch.diagnostics import structural_set
from ..mch.loaders import load_instance
from ..mch.static import solve_static, solve_static_maxmin


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="base", choices=["low", "base", "high"])
    ap.add_argument("--access-mode", default="walk_min", choices=["walk_min", "transit_min", "drive_min"])
    ap.add_argument("--max-minutes", type=float, default=30.0)
    ap.add_argument("--capacity", type=float, default=250.0)
    ap.add_argument("--pmax", type=int, default=4)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    inst = load_instance(scenario=a.scenario, access_mode=a.access_mode)
    S = structural_set(inst, a.max_minutes)
    dem = {d.id: inst.demand[(d.id, 0)] for d in inst.districts}
    kw = dict(max_minutes=a.max_minutes, capacity=a.capacity)

    def worst_excl(sol):
        rs = [(dem[d.id] - sol.served.get((d.id, 0), 0.0)) / dem[d.id]
              for d in inst.districts if d.id not in S and dem[d.id] > 0]
        return round(max(rs), 4) if rs else 0.0

    rows = []
    for p in range(1, a.pmax + 1):
        e = solve_static(inst, p, **kw)
        m = solve_static_maxmin(inst, p, **kw)
        for name, sol in (("efficiency", e), ("max_min", m)):
            rows.append({"p": p, "strategy": name,
                         "unmet_total": round(sol.metrics["unmet_total"], 2),
                         "coverage_rate": round(sol.metrics["coverage_rate"], 4),
                         "worst_all": round(sol.metrics["worst_unmet_ratio"], 4),
                         "worst_excl_structural": worst_excl(sol),
                         "gini_coverage": round(sol.metrics["gini_coverage"], 4),
                         "chosen": ",".join(sol.chosen)})

    with (out / "tradeoff.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    (out / "summary.json").write_text(json.dumps(
        {"scenario": a.scenario, "access_mode": a.access_mode,
         "structural_unreachable": S, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"结构性不可达（任何选点都服务不到）: {S}")
    print(f"{'p':>2} | {'效率':>8} {'worst(全)':>9} {'worst(排结构)':>13} | {'max-min':>8} {'worst(全)':>9} {'worst(排结构)':>13}")
    for p in range(1, a.pmax + 1):
        e = next(r for r in rows if r["p"] == p and r["strategy"] == "efficiency")
        m = next(r for r in rows if r["p"] == p and r["strategy"] == "max_min")
        print(f"{p:>2} | {e['unmet_total']:8.1f} {e['worst_all']:9.0%} {e['worst_excl_structural']:13.0%} "
              f"| {m['unmet_total']:8.1f} {m['worst_all']:9.0%} {m['worst_excl_structural']:13.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
