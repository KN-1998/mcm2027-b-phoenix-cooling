"""效率与成本指标。"""
from __future__ import annotations

from typing import Dict, List


def unmet_by_district(demand: Dict[str, float], served: Dict[str, float]) -> Dict[str, float]:
    return {k: max(0.0, v - served.get(k, 0.0)) for k, v in demand.items()}


def totals(demand: Dict[str, float], served: Dict[str, float]) -> Dict[str, float]:
    d = sum(demand.values())
    s = sum(served.values())
    return {
        "demand_total": round(d, 3),
        "served_total": round(s, 3),
        "unmet_total": round(max(0.0, d - s), 3),
        "coverage_rate": round(s / d, 6) if d > 0 else 1.0,
    }


def utilization(served_by_site: Dict[str, float], capacity: Dict[str, int]) -> Dict[str, float]:
    out = {}
    for sid, cap in capacity.items():
        if cap and cap > 0:
            out[sid] = round(served_by_site.get(sid, 0.0) / cap, 4)
    return out


def cost_breakdown(buy: int, days: int, c_buy: float, c_day: float, moves: int = 0, c_move: float = 0.0) -> Dict[str, float]:
    """[EXT-09] 成本结构：购置 + 日运营 + 迁移。真实预算未知，见 configs/costs.yaml。"""
    capex = buy * c_buy
    opex = buy * days * c_day
    move = moves * c_move
    return {"capex": round(capex, 2), "opex": round(opex, 2), "move": round(move, 2),
            "total": round(capex + opex + move, 2)}
