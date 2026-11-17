"""政策杠杆对比：延长固定中心营业时间 / 扩容 / 加购枢纽，哪个最有效？

用法：python -m src.exp.run_levers --p 3 --out results/levers
"""
from __future__ import annotations

import argparse, csv, json, copy
from pathlib import Path

from ..mch.loaders import load_instance
from ..mch.static import solve_static


def solve_variant(p, extend_fixed_to=None, cap_fixed=None, mch_close=None, cap_hub=250.0):
    inst = load_instance()
    for s in inst.sites:
        if s.kind == "cooling":
            if extend_fixed_to is not None:
                s.close_hour = extend_fixed_to
            if cap_fixed is not None:
                s.capacity = cap_fixed
        if s.kind == "candidate_mch" and mch_close is not None:
            s.close_hour = mch_close
    return solve_static(inst, p, capacity=cap_hub)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p", type=int, default=3)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    from ..mch import runmeta
    runmeta.write(out, vars(a))

    rows = []
    def add(name, sol, note=""):
        rows.append({"lever": name, "p": a.p,
                     "unmet_total": sol.metrics["unmet_total"],
                     "coverage_rate": sol.metrics["coverage_rate"],
                     "worst_unmet_ratio": sol.metrics["worst_unmet_ratio"],
                     "gini_coverage": sol.metrics["gini_coverage"],
                     "chosen": ",".join(sol.chosen), "note": note})

    base = solve_variant(a.p)
    add("baseline", base, "fixed centers 9-17 cap 50; hubs 9-19 cap 250")
    add("extend_fixed_hours_22", solve_variant(a.p, extend_fixed_to=22.0), "fixed centers open until 22:00")
    add("double_fixed_capacity", solve_variant(a.p, cap_fixed=100), "fixed center capacity 50 -> 100")
    add("both_hours_and_capacity", solve_variant(a.p, extend_fixed_to=22.0, cap_fixed=100), "A + B")
    add("extend_hub_hours_22", solve_variant(a.p, mch_close=22.0), "mobile hubs open until 22:00")
    for p in (a.p + 1, a.p + 2, a.p + 3):
        add(f"buy_{p}_hubs", solve_variant(p), f"fleet size {p}")

    with (out / "levers.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    (out / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    b = rows[0]["unmet_total"]
    print(f"基线未满足 {b:.1f} 人次/日")
    for r in rows[1:]:
        print(f"  {r['lever']:26s} 未满足 {r['unmet_total']:7.1f}  ({r['unmet_total']-b:+7.1f})  覆盖 {r['coverage_rate']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
