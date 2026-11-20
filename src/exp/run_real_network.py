"""真实网络（MAG 2026 公开快照）下的可达性与选址。

对比两套"现有网络"：
  synthetic  ：每区质心各有一个合成冷却中心（早期版本）
  MAG_REAL   ：MAG 2026 公开快照的 24 个降温中心 + 26 个饮水站
输出：results/real_network/{district_access.csv, sweep.csv, summary.json}
"""
from __future__ import annotations

import argparse, csv, json
from pathlib import Path

from ..mch import runmeta
from ..mch.realnet import build_real_instance
from ..mch.schema import COOLING
from ..mch.static import solve_static


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="walk_min,transit_min")
    ap.add_argument("--thresholds", default="20,30,45,60")
    ap.add_argument("--pmax", type=int, default=8)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    runmeta.write(out, vars(a))

    ths = [float(x) for x in a.thresholds.split(",")]
    rows, sweeps, summary = [], [], {}

    for mode in [x for x in a.modes.split(",") if x]:
        inst = build_real_instance(access_mode=mode)
        cool = [s for s in inst.sites if s.kind == COOLING]
        for d in inst.districts:
            times = sorted(inst.access[(d.id, s.id)] for s in cool)
            rows.append({"mode": mode, "district_id": d.id, "n_cooling": len(cool),
                         "nearest_min": times[0], "median_min": times[len(times)//2],
                         **{f"n_within_{int(t)}": sum(1 for x in times if x <= t) for t in ths}})
        for p in range(0, a.pmax + 1):
            sol = solve_static(inst, p)
            sweeps.append({"mode": mode, "p": p,
                           "unmet": round(sol.metrics["unmet_total"], 2),
                           "coverage": round(sol.metrics["coverage_rate"], 4),
                           "worst_unmet_ratio": round(sol.metrics["worst_unmet_ratio"], 4),
                           "chosen": ",".join(sol.chosen)})
        # 有多少区在阈值内至少有 1 个真实降温中心
        summary[mode] = {
            "n_fixed_cooling": len(cool),
            **{f"districts_with_cooling_within_{int(t)}":
               sum(1 for d in inst.districts
                   if any(inst.access[(d.id, s.id)] <= t for s in cool))
               for t in ths},
        }

    with (out / "district_access.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with (out / "sweep.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(sweeps[0].keys())); w.writeheader(); w.writerows(sweeps)
    summary["note"] = ("Conditional scenario: synthetic district centers; centroid bias has no fixed direction. "
                       "Counts describe source indoor-site inventory, not dated opening or measured population access. "
                       "All access is a distance/speed proxy with direct walk option, not GTFS routing.")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    for mode, s in summary.items():
        if mode == "note": continue
        print(f"{mode}: 固定降温中心 {s['n_fixed_cooling']} 个 | "
              + " | ".join(f"≤{int(t)}min 有站点的区 {s[f'districts_with_cooling_within_{int(t)}']}/12"
                           for t in ths))
    print()
    for r in sweeps:
        if r["mode"] == "walk_min":
            print(f"  walk p={r['p']}: 未满足 {r['unmet']:7.1f} 覆盖 {r['coverage']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
