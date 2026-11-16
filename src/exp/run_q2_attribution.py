"""Q2 归因分析：未满足需求是"没得去/装不下/没选到"，并扫可达阈值。

用法：python -m src.exp.run_q2_attribution --p 3 --out results/q2_attribution
"""
from __future__ import annotations

import argparse, csv, json
from pathlib import Path

from ..mch.attribution import attribute_unmet
from ..mch.loaders import load_instance
from ..mch.static import solve_static


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p", type=int, default=3)
    ap.add_argument("--scenario", default="base", choices=["low", "base", "high"])
    ap.add_argument("--access-mode", default="walk_min", choices=["walk_min", "transit_min", "drive_min"])
    ap.add_argument("--thresholds", default="20,30,45,60")
    ap.add_argument("--capacity", type=float, default=250.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    inst = load_instance(scenario=a.scenario, access_mode=a.access_mode)
    ths = [float(x) for x in a.thresholds.split(",")]

    rows = []
    detail = {}
    for th in ths:
        sol = solve_static(inst, a.p, max_minutes=th, capacity=a.capacity)
        active = [x.id for x in inst.fixed_sites()] + list(sol.chosen)
        att = attribute_unmet(inst, sol, 0, th, a.capacity, active_sites=active)
        detail[str(th)] = att
        rows.append({"threshold_minutes": th, "p": a.p,
                     **{("unmet_" + k): v for k, v in att["by_reason"].items()},
                     "unmet_total": sol.metrics["unmet_total"],
                     "coverage_rate": sol.metrics["coverage_rate"],
                     "worst_unmet_ratio": sol.metrics["worst_unmet_ratio"],
                     "gini_coverage": sol.metrics["gini_coverage"],
                     "chosen": ",".join(sol.chosen)})

    with (out / "threshold_sweep.csv").open("w", newline="", encoding="utf-8-sig") as f:
        keys = sorted({k for r in rows for k in r})
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    (out / "attribution_detail.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== 阈值扫描 (p={a.p}, {a.access_mode}) ===")
    for r in rows:
        print(f"  {r['threshold_minutes']:>4.0f} min: 未满足 {r['unmet_total']:7.1f} | no_access {r.get('unmet_no_access',0):7.1f} "
              f"| capacity {r.get('unmet_capacity',0):6.1f} | selection {r.get('unmet_selection',0):6.1f} | 覆盖 {r['coverage_rate']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
