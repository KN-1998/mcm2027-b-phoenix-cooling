"""Network diagnostics for Q1: which districts cannot reach any indoor cooling site."""
from __future__ import annotations

from typing import Dict, List

from .schema import COOLING, Instance, RESPITE

INDOOR = (COOLING, RESPITE, "candidate_mch")


def reachable_sites(inst: Instance, district_id: str, max_minutes: float = 30.0,
                   include_candidates: bool = False) -> List[str]:
    kinds = INDOOR if include_candidates else (COOLING, RESPITE)
    out = []
    for s in inst.sites:
        if s.kind not in kinds:
            continue
        t = inst.access.get((district_id, s.id))
        if t is not None and t <= max_minutes:
            out.append(s.id)
    return out


def access_gap(inst: Instance, max_minutes: float = 30.0) -> Dict[str, object]:
    zero: List[str] = []
    counts: Dict[str, int] = {}
    for d in inst.districts:
        ids = reachable_sites(inst, d.id, max_minutes)
        counts[d.id] = len(ids)
        if not ids:
            zero.append(d.id)
    return {"threshold_minutes": max_minutes, "zero_access_districts": zero,
            "reachable_counts": counts,
            "note": "hydration stations do not count as cooling capacity"}
