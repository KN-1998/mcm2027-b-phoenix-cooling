"""Q3 七天热浪：逐日部署与迁移。

模型：每天选 p 个候选点；若与前一天不同，产生迁移代价与**停服时间**，
停服期间该枢纽可用容量按 downtime_frac 缩减。
[EXT-11] 若需要精确的迁移路径（车辆路径），在 move_time_hours() 里接路网。
"""
from __future__ import annotations

from typing import Dict, List, Sequence

from .schema import Instance
from .static import Solution, _active_sites, _assign, solve_static


def move_time_hours(inst: Instance, a: str, b: str) -> float:
    """两个候选点之间的迁移时间（小时）。[EXT-11] 现用直线距离代理。"""
    sa = next(s for s in inst.sites if s.id == a)
    sb = next(s for s in inst.sites if s.id == b)
    from math import hypot
    km = hypot((sa.lat - sb.lat) * 111.0, (sa.lon - sb.lon) * 95.0)
    return round(0.5 + km / 40.0, 2)   # 0.5 h 搭建 + 40 km/h 行驶


def solve_dynamic(inst: Instance, p: int, max_minutes: float = 30.0,
                  capacity: float = 250.0, downtime_frac: float = 0.5,
                  move_penalty: float = 0.0) -> List[Solution]:
    """逐日贪心：当天的组合在"未满足 + 迁移惩罚"上最优。"""
    prev: Sequence[str] = ()
    out: List[Solution] = []
    for day in range(inst.horizon_days):
        best = None
        base = solve_static(inst, p, max_minutes=max_minutes, capacity=capacity, day=day)
        candidates = [base]
        # 复用昨天的方案（迁移成本为 0）
        if prev:
            reuse = _assign(inst, _active_sites(inst, tuple(prev)), day, max_minutes, capacity)
            candidates.append(reuse)
        for sol in candidates:
            changed = len(set(sol.chosen) ^ set(prev))
            penalty = move_penalty * changed
            if changed:
                # 停服：迁移当天的有效容量下降
                sol = _assign(inst, _active_sites(inst, tuple(sol.chosen)), day,
                              max_minutes, capacity * (1.0 - downtime_frac))
                sol.metrics["downtime_applied"] = downtime_frac
            sol.metrics["move_penalty"] = round(penalty, 3)
            sol.metrics["n_changed"] = changed
            score = sol.metrics["unmet_total"] + penalty
            if best is None or score < best[0]:
                best = (score, sol)
        assert best is not None
        out.append(best[1])
        prev = best[1].chosen
    return out
