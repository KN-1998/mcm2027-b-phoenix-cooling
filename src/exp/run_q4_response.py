"""Q4：中断响应闭环（时刻表 + 24h 可行性 + 轻量压力测试）。

输出：
  scenario_table.csv   各种（损坏站点 × 冲击倍数）下的对比
  timeline.csv         每种情形的迁移时刻表
  stress.json          随机故障/冲击抽样下的响应达成率
"""
from __future__ import annotations

import argparse, csv, json, random
from pathlib import Path

from ..mch import runmeta
from ..mch.disruption import plan_response
from ..mch.loaders import load_instance


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p", type=int, default=3)
    ap.add_argument("--mults", default="1.0,1.8,3.0")
    ap.add_argument("--down-sites", default="R01,C01,MCH-3,MCH-7")
    ap.add_argument("--budget-hours", type=float, default=24.0)
    ap.add_argument("--stress-draws", type=int, default=100)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    runmeta.write(out, vars(a))

    inst = load_instance()
    mults = [float(x) for x in a.mults.split(",")]
    downs = [x for x in a.down_sites.split(",") if x]

    rows, timelines = [], []
    for down in downs:
        for mult in mults:
            r = plan_response(inst, a.p, mult=mult, down_site=down, budget_hours=a.budget_hours)
            rows.append({"down_site": down, "shock_mult": mult,
                         "base_unmet": r["base"]["unmet"],
                         "shock_only": r["shock_only"], "outage_only": r["outage_only"],
                         "no_response_unmet": r["both_no_response"]["unmet"],
                         "with_response_unmet": r["with_response"]["unmet"],
                         "response_gain": r["response_gain"],
                         "n_moves": len(r["moves"]),
                         "total_response_hours": r["total_response_hours"],
                         "feasible_24h": r["feasible_within_budget"]})
            for t in r["timeline"]:
                timelines.append({"down_site": down, "shock_mult": mult, **t})

    with (out / "scenario_table.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    if timelines:
        with (out / "timeline.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(timelines[0].keys())); w.writeheader(); w.writerows(timelines)

    # 轻量压力测试：随机抽一个枢纽故障 + 随机冲击倍数
    rng = random.Random(7)
    hubs = [s.id for s in inst.candidate_sites()]
    feas, gains, hours = 0, [], []
    for _ in range(a.stress_draws):
        down = rng.choice(hubs)
        mult = rng.choice([1.0, 1.5, 2.0, 3.0])
        r = plan_response(inst, a.p, mult=mult, down_site=down, budget_hours=a.budget_hours)
        feas += int(r["feasible_within_budget"])
        gains.append(r["response_gain"])
        hours.append(r["total_response_hours"])
    gains_sorted = sorted(gains)
    def pct(q):
        return gains_sorted[min(len(gains_sorted)-1, int(q*len(gains_sorted)))]
    stress = {"draws": a.stress_draws, "feasible_share": round(feas/a.stress_draws, 3),
              "gain_p10": pct(0.1), "gain_p50": pct(0.5), "gain_p90": pct(0.9),
              "max_response_hours": max(hours), "note": "故障为均匀抽样，不是实证概率"}
    (out / "stress.json").write_text(json.dumps(stress, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'损坏':7s} {'倍数':>4} {'不响应':>8} {'响应':>8} {'收益':>8} {'迁移':>4} {'耗时h':>6} {'24h':>4}")
    for r in rows:
        print(f"{r['down_site']:7s} {r['shock_mult']:4.1f} {r['no_response_unmet']:8.1f} "
              f"{r['with_response_unmet']:8.1f} {r['response_gain']:+8.1f} {r['n_moves']:4d} "
              f"{r['total_response_hours']:6.2f} {'是' if r['feasible_24h'] else '否':>4}")
    print(f"\n压力测试: 24h 达成率 {stress['feasible_share']:.0%}, 收益 P10/P50/P90 = "
          f"{stress['gain_p10']}/{stress['gain_p50']}/{stress['gain_p90']}, 最长 {stress['max_response_hours']}h")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
