"""一条命令做参数扫描：p x 可达模式 x 情景 x 无家可归者比例 x（可选）延时。

产出长表 sweep.csv（一行一个配置），可直接画图或喂给优化器。

示例：
    python -m src.exp.run_sweep --out results/sweep ^
        --p 0,1,2,3,4,6,8 --access-modes walk_min,transit_min ^
        --scenarios base --ushares 0.3,0.5,0.7
"""
from __future__ import annotations

import argparse, csv, itertools
from pathlib import Path

from ..mch import runmeta
from ..mch.diagnostics import structural_set
from ..mch.static import solve_static
from .common import ACCESS_MODES, SCENARIOS, parse_list


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p", default="3", help="逗号分隔的候选枢纽数")
    ap.add_argument("--access-modes", default="walk_min")
    ap.add_argument("--scenarios", default="base")
    ap.add_argument("--ushares", default="", help="逗号分隔；空则用 CSV 值")
    ap.add_argument("--max-minutes", default="30", help="逗号分隔的阈值")
    ap.add_argument("--extend-fixed", default="", help="逗号分隔的延长时刻，如 22 或 19,22")
    ap.add_argument("--capacity-override", default="", help="逗号分隔的容量覆盖值")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    runmeta.write(out, vars(a))

    from .common import build_instance
    import types

    ps = parse_list(a.p, int)
    modes = [x for x in a.access_modes.split(",") if x]
    scen = [x for x in a.scenarios.split(",") if x]
    ushares = parse_list(a.ushares, float) or [None]
    ths = parse_list(a.max_minutes, float)
    exts = parse_list(a.extend_fixed, float) or [None]
    caps = parse_list(a.capacity_override, float) or [None]

    rows = []
    for p, mode, sc, us, th, ext, cap in itertools.product(
            ps, modes, scen, ushares, ths, exts, caps):
        args = types.SimpleNamespace(scenario=sc, access_mode=mode, ushare=us,
                                     extend_fixed_to=ext, mch_close=None)
        inst = build_instance(args)
        sol = solve_static(inst, p, max_minutes=th, override=cap)
        S = structural_set(inst, th)
        per = sol.metrics.get("served_by_period", {})
        rows.append({
            "p": p, "access_mode": mode, "scenario": sc, "ushare": us,
            "max_minutes": th, "extend_fixed_to": ext, "capacity_override": cap,
            "unmet_total": round(sol.metrics["unmet_total"], 2),
            "coverage_rate": round(sol.metrics["coverage_rate"], 4),
            "worst_unmet_ratio": round(sol.metrics["worst_unmet_ratio"], 4),
            "structural": ",".join(S),
            "served_day": round(float(per.get("day", 0)), 2),
            "served_evening": round(float(per.get("evening", 0)), 2),
            "served_night": round(float(per.get("night", 0)), 2),
            "chosen": ",".join(sol.chosen),
        })
        print(f"  p={p} {mode} {sc} us={us} th={th} ext={ext} cap={cap}: "
              f"未满足 {rows[-1]['unmet_total']:.1f} 覆盖 {rows[-1]['coverage_rate']:.3f}")

    with (out / "sweep.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"\n{len(rows)} 个配置 -> {out/'sweep.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
