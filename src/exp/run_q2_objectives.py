"""Q2 效率 vs 公平（正确口径）。

方法：固定"效率最优选点"，比较两种**分配**：
  efficiency = 最大化总服务量
  max_min    = 先最小化最差未满足率 t，再在该 t 下最大化总服务量
两者都用运输流 LP（同一日口径，便于直接比较分配本身）。
"""
from __future__ import annotations

import argparse, csv, json
from pathlib import Path

from ..mch.assign import solve_assignment, solve_assignment_maxmin
from ..mch.diagnostics import structural_set
from ..mch.loaders import load_instance
from ..mch.static import _active_sites, _effective_capacity, solve_static


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="base", choices=["low", "base", "high"])
    ap.add_argument("--access-mode", default="walk_min", choices=["walk_min", "transit_min", "drive_min"])
    ap.add_argument("--max-minutes", type=float, default=30.0)
    ap.add_argument("--pmax", type=int, default=8)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    from ..mch import runmeta

    runmeta.write(out, vars(a))
    inst = load_instance(scenario=a.scenario, access_mode=a.access_mode)
    S = structural_set(inst, a.max_minutes)
    dem = {d.id: inst.demand[(d.id, 0)] for d in inst.districts}

    def worst(sv):
        rs = [(dem[d] - sv.get(d, 0.0)) / dem[d] for d in dem
              if d not in S and dem[d] > 0]
        return round(max(rs), 4) if rs else 0.0

    rows = []
    for p in range(1, a.pmax + 1):
        base = solve_static(inst, p, max_minutes=a.max_minutes, mode="daily")
        act = _active_sites(inst, base.chosen)
        # A6 修复：评估用的容量口径必须与选址时一致（默认 availability）
        cap = _effective_capacity(inst, act, 250.0)
        eff = solve_assignment(inst, act, 0, a.max_minutes, cap, dem)
        mm = solve_assignment_maxmin(inst, act, 0, a.max_minutes, cap, dem, exempt=S)
        for name, res in (("efficiency", eff), ("max_min", mm)):
            rows.append({"p": p, "strategy": name,
                         "served_total": round(sum(res["served"].values()), 2),
                         "worst_excl_structural": worst(res["served"]),
                         "t_star": round(res.get("t", 0.0), 4) if name == "max_min" else None,
                         "chosen": ",".join(base.chosen)})

    with (out / "allocation_objectives.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    (out / "summary.json").write_text(json.dumps(
        {"scenario": a.scenario, "access_mode": a.access_mode,
         "structural_unreachable": S, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"结构性不可达: {S}")
    print(f"{'p':>2} | {'效率: 服务/最差':>18} | {'max-min: 服务/最差':>20}")
    for p in range(1, a.pmax + 1):
        e = next(r for r in rows if r["p"] == p and r["strategy"] == "efficiency")
        m = next(r for r in rows if r["p"] == p and r["strategy"] == "max_min")
        print(f"{p:>2} | {e['served_total']:8.1f} / {e['worst_excl_structural']:5.0%} "
              f"| {m['served_total']:8.1f} / {m['worst_excl_structural']:6.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
