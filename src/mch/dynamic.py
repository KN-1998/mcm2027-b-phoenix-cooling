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
                  move_penalty: float = 0.0, use_move_time: bool = True) -> List[Solution]:
    """逐日贪心对照版（不是 DP；DP 见 src/exp/run_q3_week.py）。

    修正点：
    1. 停服**只作用于当天新搬入的枢纽**（不再对所有选中枢纽一起折减）；
    2. 通过 `_assign(..., downtime={sid: factor})` 显式下传，
       不再依赖会被 s.capacity 覆盖的 capacity 参数；
    3. `move_time_hours` 真正参与：停服因子 = 1 - 迁移小时 / 营业小时。
    """
    prev: Sequence[str] = ()
    out: List[Solution] = []
    open_hours = 10.0

    for day in range(inst.horizon_days):
        base = solve_static(inst, p, max_minutes=max_minutes, capacity=capacity, day=day)
        cands = [base]
        if prev:
            cands.append(_assign(inst, _active_sites(inst, tuple(prev)), day,
                                 max_minutes, capacity))
        best = None
        for sol in cands:
            changed = [x for x in sol.chosen if x not in prev] if day > 0 else []
            downtime = {}
            for sid in changed:
                if use_move_time and prev:
                    hours = min(move_time_hours(inst, prev[0], sid), open_hours)
                    downtime[sid] = max(0.0, 1.0 - hours / open_hours)
                elif changed:
                    downtime[sid] = 1.0 - downtime_frac
            scored = _assign(inst, _active_sites(inst, tuple(sol.chosen)), day,
                             max_minutes, capacity, downtime=downtime) if downtime else sol
            scored.metrics["moved_in"] = list(changed)
            scored.metrics["downtime_factor"] = {k: round(v, 3) for k, v in downtime.items()}
            scored.metrics["move_penalty"] = round(move_penalty * len(changed), 3)
            score = scored.metrics["unmet_total"] + scored.metrics["move_penalty"]
            if best is None or score < best[0]:
                best = (score, scored)
        assert best is not None
        out.append(best[1])
        prev = best[1].chosen
    return out
