"""Q4：有时钟约束的重调度、精确小规模搜索和条件压力测试。

输出：
  scenario_table.csv   各种（损坏对象 × 冲击倍数）下的对比
  timeline.csv         每种情形的最优迁移时刻表
  stress.json          随机故障/冲击抽样下的响应可行率与收益分布
"""
from __future__ import annotations

import argparse
import copy
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
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--search-mode", choices=("auto", "exact", "heuristic"), default="auto")
    ap.add_argument("--top-combos", type=int, default=3)
    ap.add_argument("--top-matchings", type=int, default=3)
    ap.add_argument("--parallel", action="store_true")
    ap.add_argument('--passenger-access-scales',default='1,1.5,2',
                    help='ASSUME road/transit disruption multipliers for passenger travel times')
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.stress_draws < 0:
        ap.error("--stress-draws must be nonnegative")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    runmeta.write(out, vars(a))

    inst = load_instance()
    passenger_scales=[float(x) for x in a.passenger_access_scales.split(',')]
    if not passenger_scales or any(not 1 <= x < float('inf') for x in passenger_scales):
        ap.error('passenger access scales must be finite and at least one')
    search_kw = dict(search_mode=a.search_mode, top_combos=a.top_combos,
                     top_matchings=a.top_matchings, parallel=a.parallel)
    mults = [float(x) for x in a.mults.split(",")]
    sites = [x for x in a.down_sites.split(",") if x]
    vehicles = [x for x in a.down_vehicles_at.split(",") if x]

    rows, timelines, details = [], [], []
    cases = [("site", x) for x in sites] + [("vehicle", x) for x in vehicles]
    for kind, down in cases:
        for mult in mults:
            kw = {"down_site": down} if kind == "site" else {"down_vehicle_at": down}
            try:
                r = plan_response(inst, a.p, mult=mult, budget_hours=a.budget_hours, **search_kw, **kw)
            except ValueError as e:
                rows.append({"kind": kind, "down": down, "shock_mult": mult,
                             "fleet_healthy": None, "no_move": None, "best": None,
                             "gain": None, "n_moves": None, "hours": None,
                             "feasible": None, "search_status": None,
                             'no_move_worst':None,'response_worst':None,
                             "timelines_tested": None, "note": str(e)})
                continue
            details.append({"kind": kind, "down": down, "shock_mult": mult, "response": r})
            b = r["best"]
            rows.append({"kind": kind, "down": down, "shock_mult": mult,
                         "fleet_healthy": r["fleet_healthy"],
                         "no_move": r["no_move"]["unmet"],
                         "best": b["unmet"] if b else None,
                         "gain": r["response_gain"],
                         "n_moves": b["n_moves"] if b else None,
                         "hours": b["total_hours"] if b else None,
                         "feasible": r["feasible_any"],
                         "search_status": r["search"]["optimality_status"],
                         'no_move_worst':r['no_move']['worst_unmet_ratio_all'],
                         'response_worst':b['worst_unmet_ratio_all'],
                         "timelines_tested": r["search"]["timelines_tested"],
                         "note": ""})
            if b:
                for m in b["timeline"]:
                    timelines.append({"kind": kind, "down": down, "shock_mult": mult, **m})

    if rows:
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
    rng = random.Random(a.seed)
    base = plan_response(inst, a.p, mult=1.0, **search_kw)
    deployed = base["base"]["chosen"]
    fixed = [s.id for s in inst.sites if s.kind in ("cooling", "respite")]
    feas, gains, stress_rows, cache = 0, [], [], {}
    for draw in range(a.stress_draws):
        mult = rng.choice([1.0, 1.5, 2.0, 3.0])
        road_mult = rng.choice([1.0, 1.5, 2.0])
        forecast_scale = rng.choice([0.8, 1.0, 1.2])
        passenger_scale = rng.choice(passenger_scales)
        if rng.random() < 0.5 and deployed:
            kw = {"down_vehicle_at": rng.choice(deployed)}
        else:
            kw = {"down_site": rng.choice(fixed)}
        key = (tuple(kw.items()), mult, road_mult, forecast_scale, passenger_scale)
        if key not in cache:
            draw_inst = copy.deepcopy(inst)
            draw_inst.demand = {k: v * forecast_scale for k, v in inst.demand.items()}
            draw_inst.access = {k:v*passenger_scale for k,v in inst.access.items()}
            cache[key] = plan_response(draw_inst, a.p, mult=mult,
                                      travel_time_multiplier=road_mult,
                                      initial_chosen=deployed,
                                      budget_hours=a.budget_hours, **search_kw, **kw)
        r = cache[key]
        feas += int(r["feasible_any"])
        gains.append(r["response_gain"] or 0.0)
        stress_rows.append({"draw": draw, "shock_multiplier": mult,
                            "relocation_time_multiplier": road_mult,
                            "demand_forecast_scale": forecast_scale,
                            'passenger_access_multiplier':passenger_scale,
                            'initial_chosen':deployed,
                            "failure": kw, "no_move_unmet": r["no_move"]["unmet"],
                            "response_unmet": r["best"]["unmet"], "gain": r["response_gain"],
                            "feasible": r["feasible_any"],
                            'no_move_worst':r['no_move']['worst_unmet_ratio_all'],
                            'response_worst':r['best']['worst_unmet_ratio_all'],
                            "search_status": r["search"]["optimality_status"]})
    gs = sorted(gains)

    def pct(q):
        return gs[min(len(gs) - 1, int(q * len(gs)))] if gs else None

    stress = {"draws": a.stress_draws, "seed": a.seed,
              "feasible_share": round(feas / a.stress_draws, 3) if a.stress_draws else None,
              "positive_gain_share": round(sum(g > 0 for g in gains) / len(gains), 3) if gains else None,
              'passenger_access_scales':passenger_scales,
              "gain_p10": pct(0.1), "gain_p50": pct(0.5), "gain_p90": pct(0.9),
              "note": "ASSUME scenario draws: deployed vehicle/fixed site failure, demand forecast x0.8/1/1.2, relocation time x1/1.5/2 and passenger access-time multipliers. Every strategy in a draw shares all disrupted inputs and the original initial deployment. No-move is always feasible; feasible_share is an action-feasibility check, not observed reliability or restoration probability."}
    (out / "stress.json").write_text(json.dumps(stress, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "stress_draws.json").write_text(json.dumps(stress_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "scenario_details.json").write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")

    def fmt(v, spec="{:.1f}"):
        return "NA" if v is None else spec.format(v)

    print("类型    损坏    倍数  车队     不搬     最优     收益 迁移  耗时h 可行")
    for r in rows:
        print(f"{r['kind']:7s} {r['down']:7s} {r['shock_mult']:4.1f} "
              f"{str(r['fleet_healthy'] or 'NA'):>4} {fmt(r['no_move']):>8} {fmt(r['best']):>8} "
              f"{fmt(r['gain'], '{:+.1f}'):>8} {str(r['n_moves'] or '-'):>4} "
              f"{fmt(r['hours'], '{:.2f}'):>6} {str(r['feasible']):>4}")
    print(f"\n压力测试: 行动可行份额 {stress['feasible_share']}, 收益 P10/P50/P90 = "
          f"{stress['gain_p10']}/{stress['gain_p50']}/{stress['gain_p90']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
