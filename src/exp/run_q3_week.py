"""Q3：七天热浪里的搬迁 vs 延时。

三件事：
1. 静态：一周用同一组 p 个点位
2. 上界（oracle）：每天自由换点、不付搬迁代价
3. 动态（DP）：允许换点，但搬过的枢纽当天容量按停服折减；只在"每日前 k 优组合"里搜

输出：results/q3_week/{week.csv, summary.json, dispatch.csv}
"""
from __future__ import annotations

import argparse, csv, itertools, json
from pathlib import Path
from typing import Dict, List, Tuple

from ..mch.assign import solve_assignment_flow
from ..mch.hours import PERIODS, capacity_in_period, split_demand_mixed
from ..mch.loaders import load_instance
from ..mch.static import _active_sites

RELOC_DOWN = 0.8   # 搬迁当天：停服 2h / 营业 10h -> 容量 80%
TOP_K = 3          # 每天保留的候选组合数（控制 DP 规模）


def day_unmet(inst, combo, day, max_minutes=30.0, cap_override=None,
              downtime_sites=(), ushare=0.5) -> float:
    """给定点位组合与当天，返回未满足人次（逐时段 max-flow 求和）。"""
    act = _active_sites(inst, combo)
    total_dem = sum(inst.demand.get((d.id, day), 0.0) for d in inst.districts)
    served = 0.0
    for h in PERIODS:
        cap_h, dem_h = {}, {}
        for s in act:
            base = cap_override if cap_override is not None else float(s.capacity or 250.0)
            if s.id in downtime_sites:
                base *= RELOC_DOWN
            cap_h[s.id] = capacity_in_period(s, base, h)
        shares = split_demand_mixed(1.0, ushare)
        for d in inst.districts:
            dem_h[d.id] = inst.demand.get((d.id, day), 0.0) * shares[h]
        out = solve_assignment_flow(inst, act, day, max_minutes, cap_h, dem_h)
        served += sum(out["served"].values())
    return round(total_dem - served, 3)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p", type=int, default=3)
    ap.add_argument("--max-minutes", type=float, default=30.0)
    ap.add_argument("--top-k", type=int, default=TOP_K)
    ap.add_argument("--shock-districts", default="", help="逗号分隔，如 D09,D03")
    ap.add_argument("--shock-days", default="", help="逗号分隔天索引，如 3,4")
    ap.add_argument("--shock-mult", type=float, default=1.0, help="冲击区需求倍数")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    from ..mch import runmeta

    runmeta.write(out, vars(a))
    inst = load_instance()
    ushare = float(inst.meta.get("unsheltered_share", 0.5))
    if a.shock_districts and a.shock_days:
        sd = [x for x in a.shock_districts.split(",") if x]
        sdays = [int(x) for x in a.shock_days.split(",") if x != ""]
        for k, v in list(inst.demand.items()):
            if k[0] in sd and k[1] in sdays:
                inst.demand[k] = v * a.shock_mult
    days = list(range(inst.horizon_days))
    combos = list(itertools.combinations([s.id for s in inst.candidate_sites()], a.p))

    # 1) 每天、每个组合的未满足（无搬迁折减）
    table: Dict[Tuple[int, Tuple[str, ...]], float] = {}
    for day in days:
        for c in combos:
            table[(day, c)] = day_unmet(inst, c, day, a.max_minutes, None, (), ushare)

    # 2) 静态：一周同一组点
    static_best = min(combos, key=lambda c: sum(table[(d, c)] for d in days))
    static_total = round(sum(table[(d, static_best)] for d in days), 2)

    # 3) oracle 上界：每天独立最优（不付搬迁）
    per_day_best = {d: min(combos, key=lambda c: table[(d, c)]) for d in days}
    oracle_total = round(sum(table[(d, per_day_best[d])] for d in days), 2)

    # 4) DP：状态=当天组合；转移代价=搬过的枢纽当天的容量折减（重新求解）
    cand = set()
    for d in days:
        for c in sorted(combos, key=lambda c: table[(d, c)])[: a.top_k]:
            cand.add(c)
    cand = sorted(cand)
    trans_cache: Dict[Tuple[int, Tuple[str, ...], Tuple[str, ...]], float] = {}

    def transition_unmet(day, prev, cur) -> float:
        key = (day, prev, cur)
        if key not in trans_cache:
            moved = tuple(x for x in cur if x not in prev)
            trans_cache[key] = day_unmet(inst, cur, day, a.max_minutes, None, moved, ushare)
        return trans_cache[key]

    INF = float("inf")
    V = {c: transition_unmet(days[0], (), c) for c in cand}   # 第一天不算搬迁
    back: Dict[int, Dict[Tuple[str, ...], Tuple[str, ...]]] = {0: {c: () for c in cand}}
    for d in days[1:]:
        NV, bk = {}, {}
        for cur in cand:
            best_prev, best_val = None, INF
            for prev, v in V.items():
                val = v + transition_unmet(d, prev, cur)
                if val < best_val:
                    best_val, best_prev = val, prev
            NV[cur] = best_val; bk[cur] = best_prev
        V, back[d] = NV, bk
    last = min(V, key=lambda c: V[c])
    dyn_total = round(V[last], 2)

    path: List[Tuple[str, ...]] = []
    cur = last
    for d in reversed(days):
        path.append(cur)
        cur = back[d][cur]
    path.reverse()

    rows = []
    for i, d in enumerate(days):
        c = path[i]
        prev = path[i - 1] if i > 0 else ()
        moved = [x for x in c if x not in prev]
        rows.append({"day": d, "combo": ",".join(c), "moved_in": ",".join(moved) or "-",
                     "unmet": round(transition_unmet(d, prev, c), 2),
                     "unmet_static": round(table[(d, static_best)], 2),
                     "unmet_oracle": round(table[(d, per_day_best[d])], 2)})

    with (out / "week.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    summary = {
        "p": a.p, "days": len(days), "combos": len(combos), "top_k": a.top_k,
        "static_best": list(static_best), "static_total_unmet": static_total,
        "oracle_total_unmet": oracle_total,
        "dynamic_dp_total_unmet": dyn_total,
        "relocation_gain_vs_static": round(static_total - dyn_total, 2),
        "oracle_headroom": round(static_total - oracle_total, 2),
        "reloc_downtime_factor": RELOC_DOWN,
        "per_day": rows,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"p={a.p} | 组合 {len(combos)} | 动态候选 {len(cand)}")
    print(f"  静态（同一组点）  : {static_total:8.1f}  {static_best}")
    print(f"  oracle（自由换点）: {oracle_total:8.1f}   [{oracle_total/static_total-1:+.1%}]")
    print(f"  动态 DP（含停服） : {dyn_total:8.1f}   [{dyn_total/static_total-1:+.1%}]")
    for r in rows:
        print(f"    day{r['day']}: {r['combo']:22s} 搬入 {r['moved_in']:12s} 未满足 {r['unmet']:7.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
