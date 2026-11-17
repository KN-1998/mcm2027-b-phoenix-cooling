"""Q4 中断与 24 小时重规划。

情景：一个主要固定中心（默认 R01, 24/7 respite）因断电停用；
      两个低收入且公交差的区需求上升；移动枢纽须在 24 h 内重分配。
[EXT-12] 可扩展：设备故障概率、路网中断、需求预测误差的蒙特卡洛。
"""
from __future__ import annotations

import copy

from typing import Dict, List, Sequence

from .schema import Instance
from .static import Solution, solve_static


def pick_low_income(inst: Instance, k: int = 2) -> List[str]:
    ranked = sorted(inst.districts, key=lambda d: (d.median_income, -d.pct_no_vehicle))
    return [d.id for d in ranked[:k]]


def apply_shock(inst: Instance, districts: Sequence[str], mult: float = 1.8) -> Instance:
    """返回**新实例**（不修改输入）。重复调用同一输入结果一致。"""
    out = copy.deepcopy(inst)
    for (did, day), v in list(out.demand.items()):
        if did in districts:
            out.demand[(did, day)] = v * mult
    out.meta = dict(out.meta)
    out.meta["shock"] = {"districts": list(districts), "multiplier": mult}
    return out


def run_disruption(inst: Instance, p: int, max_minutes: float = 30.0,
                   capacity: float = 250.0, down_site: str = "R01",
                   mult: float = 1.8) -> Dict[str, object]:
    before = solve_static(inst, p, max_minutes=max_minutes, capacity=capacity, day=0)
    low = pick_low_income(inst, 2)
    # A1 修复：必须接收冲击后的**副本**，否则需求激增根本没进入求解
    shocked = apply_shock(inst, low, mult)
    after_shock = solve_static(shocked, p, max_minutes=max_minutes, capacity=capacity, day=0,
                               exclude_sites=[down_site])
    return {
        "baseline": before.metrics,
        "after_disruption": after_shock.metrics,
        "shock_districts": low,
        "down_site": down_site,
        "delta_unmet": round(after_shock.metrics["unmet_total"] - before.metrics["unmet_total"], 3),
        "response_hours_assumed": 24.0,   # 假设值，不是求解出来的恢复时间
        "response_hours_modeled": False,
    }
