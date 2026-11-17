"""Q3 七天调度（薄封装）：唯一实现在 mch.dynamic.solve_week_dp。

用法：
    python -m src.exp.run_q3_week --p 3 --out results/q3_week
    python -m src.exp.run_q3_week --p 3 --shock-districts D05 --shock-days 3 --shock-mult 2
"""
from __future__ import annotations

import argparse, csv, json
from pathlib import Path

from ..mch import runmeta
from ..mch.dynamic import solve_week_dp
from ..mch.loaders import load_instance


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p", type=int, default=3)
    ap.add_argument("--max-minutes", type=float, default=30.0)
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--shock-districts", default="")
    ap.add_argument("--shock-days", default="")
    ap.add_argument("--shock-mult", type=float, default=1.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    runmeta.write(out, vars(a))

    inst = load_instance()
    if a.shock_districts and a.shock_days:
        sd = [x for x in a.shock_districts.split(",") if x]
        sdays = [int(x) for x in a.shock_days.split(",") if x != ""]
        for k, v in list(inst.demand.items()):
            if k[0] in sd and k[1] in sdays:
                inst.demand[k] = v * a.shock_mult

    res = solve_week_dp(inst, a.p, max_minutes=a.max_minutes, top_k=a.top_k)
    rows = []
    for d in res["schedule"]:
        rows.append({"day": d["day"], "combo": ",".join(d["combo"]),
                     "moves": ";".join(f"{m['from']}->{m['to']}({m['hours']}h)" for m in d["moves"]) or "-",
                     "unmet": d["unmet"]})
    with (out / "week.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    summary = {"p": a.p, "top_k": a.top_k,
               "shock": {"districts": a.shock_districts, "days": a.shock_days, "mult": a.shock_mult},
               "static_best": res["static_best"],
               "static_total_unmet": res["static_total_unmet"],
               "dynamic_total_unmet": res["dynamic_total_unmet"],
               "relocation_gain_7day": round(res["static_total_unmet"] - res["dynamic_total_unmet"], 2),
               "relocation_gain_per_day": round((res["static_total_unmet"] - res["dynamic_total_unmet"]) / inst.horizon_days, 2),
               "schedule": rows}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"p={a.p} 冲击={a.shock_districts} x{a.shock_mult}")
    print(f"  固定部署（七日）: {res['static_total_unmet']:8.2f}")
    print(f"  动态部署（七日）: {res['dynamic_total_unmet']:8.2f}")
    print(f"  搬迁收益        : {summary['relocation_gain_7day']:+8.2f} /七日 "
          f"（{summary['relocation_gain_per_day']:+.2f}/日）")
    for r in rows:
        print(f"    day{r['day']}: {r['combo']:22s} {r['moves']:24s} {r['unmet']:7.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
