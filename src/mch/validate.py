"""断言集合：对应 handoff 里的 A1–A4，以及数据一致性检查。"""
from __future__ import annotations

from typing import Dict, List

from .schema import Instance, validate_instance
from .static import solve_static
from .static import Solution


def check_capacity(sol: Solution, capacity: float) -> None:
    """A1：每站服务量不超过容量。"""
    for sid, v in sol.served_by_site.items():
        if v > capacity + 1e-6:
            raise AssertionError(f"A1 容量超限 {sid}: {v} > {capacity}")


def check_nonnegative_unmet(inst: Instance, sol: Solution, day: int = 0) -> None:
    """A2：未满足量非负，且不超需求。"""
    for d in inst.districts:
        dem = inst.demand.get((d.id, day), 0.0)
        srv = sol.served.get((d.id, day), 0.0)
        if srv < -1e-9 or srv > dem + 1e-6:
            raise AssertionError(f"A2 分配越界 {d.id}: served={srv}, demand={dem}")


def check_zero_demand(inst: Instance, p: int = 2) -> None:
    """A3：零需求 ⇒ 零服务、零部署。"""
    saved = dict(inst.demand)
    inst.demand = {k: 0.0 for k in saved}
    sol = solve_static(inst, p)
    inst.demand = saved
    assert sol.metrics["served_total"] == 0.0, "A3 零需求仍有服务"
    assert all(v == 0 for v in sol.served_by_site.values()), "A3 零需求仍占用容量"


def check_determinism(inst: Instance, p: int = 2) -> None:
    """A4：同一输入两次运行结果一致。"""
    a = solve_static(inst, p)
    b = solve_static(inst, p)
    assert a.chosen == b.chosen, "A4 选址不一致"
    assert a.metrics == b.metrics, "A4 指标不一致"


def run_all(inst: Instance, p: int = 2, capacity: float = 250.0) -> List[str]:
    problems = validate_instance(inst)
    if problems:
        return problems
    check_zero_demand(inst, p)
    check_determinism(inst, p)
    sol = solve_static(inst, p)
    check_capacity(sol, capacity)
    check_nonnegative_unmet(inst, sol)
    return []
