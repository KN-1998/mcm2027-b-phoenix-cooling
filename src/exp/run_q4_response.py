"""Q4 闭环（v3）：场地不可用 vs 车辆故障；按响应后未满足量选优。

输出：
  scenario_table.csv   各种（损坏对象 × 冲击倍数）下的对比
  timeline.csv         每种情形的最优迁移时刻表
  stress.json          随机故障/冲击抽样下的响应可行率与收益分布
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

from ..mch import runmeta
from ..mch.disruption import plan_response
from ..mch.loaders import load_instance


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p", type=int, default=3)
    ap.add_argument("--mults", default="1.0,1.8,3.0")
    ap.add_argument("--down-sites", default="R01,C01")          # 场地不可用
    ap.add_argument("--down-vehicles-at", default="MCH-3,MCH-7")  # 车辆故障（按所在点指定）
    ap.add_argument("--budget-hours", type=float, default=24.0)
    ap.add_argument("--stress-draws", type=int, default=100)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    runmeta.write(out, vars(a))

    inst = load_instance()
    mults = [float(x) for x in a.mults.split(",")]
    sites = [x for x in a.down_sites.split(",") if x]
    vehicles = [x for x in a.down_vehicles_at.split(",") if x]

    rows, timelines = [], []
    cases = [("site", x) for x in sites] + [("vehicle", x) for x in vehicles]
    for kind, down in cases:
        for mult in mults:
            kw = {"down_site": down} if kind == "site" else {"down_vehicle_at": down}
            try:
                r = plan_response(inst, a.p, mult=mult, budget_hours=a.budget_hours, **kw)
            except ValueError as e:
                rows.append({"kind": kind, "down": down, "shock_mult": mult,
                             "fleet_healthy": None, "no_move": None, "best": None,
                             "gain": None, "n_moves": None, "hours": None,
                             "feasible": None, "note": str(e)})
                continue
            b = r["best"]
            rows.append({"kind": kind, "down": down, "shock_mult": mult,
                         "fleet_healthy": r["fleet_healthy"],
                         "no_move": r["no_move"]["unmet"],
                         "best": b["unmet"] if b else None,
                         "gain": r["response_gain"],
                         "n_moves": b["n_moves"] if b else None,
                         "hours": b["total_hours"] if b else None,
                         "feasible": r["feasible_any"],
                         "note": ""})
            if b:
                for m in b["timeline"]:
                    timelines.append({"kind": kind, "down": down, "shock_mult": mult, **m})

    with (out / "scenario_table.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    if timelines:
        with (out / "timeline.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(timelines[0].keys()))
            w.writeheader()
            w.writerows(timelines)

    # 压力测试：车辆故障只在**已部署**点抽样；场地故障抽固定站点
    rng = random.Random(7)
    base = plan_response(inst, a.p, mult=1.0)
    deployed = base["best"]["chosen"] if base["best"] else []
    fixed = [s.id for s in inst.sites if s.kind in ("cooling", "respite")]
    feas, gains = 0, []
    for _ in range(a.stress_draws):
        mult = rng.choice([1.0, 1.5, 2.0, 3.0])
        if rng.random() < 0.5 and deployed:
            kw = {"down_vehicle_at": rng.choice(deployed)}
        else:
            kw = {"down_site": rng.choice(fixed)}
        r = plan_response(inst, a.p, mult=mult, budget_hours=a.budget_hours, **kw)
        feas += int(r["feasible_any"])
        gains.append(r["response_gain"] or 0.0)
    gs = sorted(gains)

    def pct(q):
        return gs[min(len(gs) - 1, int(q * len(gs)))]

    stress = {"draws": a.stress_draws, "feasible_share": round(feas / a.stress_draws, 3),
              "gain_p10": pct(0.1), "gain_p50": pct(0.5), "gain_p90": pct(0.9),
              "note": "车辆故障只在已部署点抽样；场地故障抽固定站点"}
    (out / "stress.json").write_text(json.dumps(stress, ensure_ascii=False, indent=2), encoding="utf-8")

    def fmt(v, spec="{:.1f}"):
        return "NA" if v is None else spec.format(v)

    print("类型    损坏    倍数  车队     不搬     最优     收益 迁移  耗时h 可行")
    for r in rows:
        print(f"{r['kind']:7s} {r['down']:7s} {r['shock_mult']:4.1f} "
              f"{str(r['fleet_healthy'] or 'NA'):>4} {fmt(r['no_move']):>8} {fmt(r['best']):>8} "
              f"{fmt(r['gain'], '{:+.1f}'):>8} {str(r['n_moves'] or '-'):>4} "
              f"{fmt(r['hours'], '{:.2f}'):>6} {str(r['feasible']):>4}")
    print(f"\n压力测试: 可行率 {stress['feasible_share']:.0%}, 收益 P10/P50/P90 = "
          f"{stress['gain_p10']}/{stress['gain_p50']}/{stress['gain_p90']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
