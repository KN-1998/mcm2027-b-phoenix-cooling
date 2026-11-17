"""分群敏感性：无家可归者占比（0.3/0.5/0.7）如何改变时段结构与未满足量。

观测只给出"市运营中心到访者中 69%-83% 自述无家可归"，这是选择效应，
不能当全市比例；因此作为情景参数扫描，而不是标定值。
"""
from __future__ import annotations

import argparse, csv, json
from pathlib import Path

from ..mch.loaders import load_instance
from ..mch.static import solve_static


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p", type=int, default=3)
    ap.add_argument("--shares", default="0.3,0.5,0.7")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    from ..mch import runmeta

    runmeta.write(out, vars(a))
    rows = []
    for us in [float(x) for x in a.shares.split(",")]:
        inst = load_instance()
        inst.meta["unsheltered_share"] = us
        sol = solve_static(inst, a.p)
        per = sol.metrics.get("served_by_period", {})
        rows.append({"unsheltered_share": us, "p": a.p,
                     "unmet_total": round(sol.metrics["unmet_total"], 2),
                     "coverage_rate": round(sol.metrics["coverage_rate"], 4),
                     "worst_unmet_ratio": round(sol.metrics["worst_unmet_ratio"], 4),
                     "served_day": round(float(per.get("day", 0)), 2),
                     "served_evening": round(float(per.get("evening", 0)), 2),
                     "served_night": round(float(per.get("night", 0)), 2),
                     "chosen": ",".join(sol.chosen)})
    with (out / "segment_sensitivity.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    (out / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"p={a.p} 分群敏感性：")
    for r in rows:
        print(f"  ushare={r['unsheltered_share']:.1f}: 未满足 {r['unmet_total']:7.1f} "
              f"覆盖 {r['coverage_rate']:.3f} 夜间服务 {r['served_night']:5.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
