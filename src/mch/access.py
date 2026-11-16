"""可达性与资格：距离 -> 时间 -> 可服务。

[EXT-05] 真实数据的接入点集中在这里：
        - load_gtfs(...) 用公交时刻表算 t_ij
        - load_osm(...)  用路网算驾车/步行时间
   下游只使用 minutes，替换实现即可。
"""
from __future__ import annotations

from typing import Dict, Tuple

from .schema import COOLING, Instance, eligibility


def build_minutes(inst: Instance) -> Dict[Tuple[str, str], float]:
    return dict(inst.access)


def feasible_links(inst: Instance, minutes: Dict[Tuple[str, str], float],
                   max_minutes: float = 30.0,
                   need_kind: str = COOLING) -> Dict[Tuple[str, str], bool]:
    out = {}
    for s in inst.sites:
        for d in inst.districts:
            t = minutes.get((d.id, s.id))
            out[(d.id, s.id)] = bool(t is not None and eligibility(s, t, need_kind, max_minutes))
    return out
