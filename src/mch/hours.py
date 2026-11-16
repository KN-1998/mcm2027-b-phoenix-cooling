"""EXT-14：开放时段 -> 可用服务份额。

把一天切成三段（与 2025 周报的到访高峰一致）：
  day     09:00-17:00（8 h）  需求占比 45%
  evening 17:00-22:00（5 h）  需求占比 40%   <- 周报显示 16-20 时是第二高峰
  night   22:00-09:00（11 h）需求占比 15%   <- 无家可归者夜间需求

站点对某时段的"覆盖"判定：营业窗口覆盖该时段 >= 50% 的小时数。
站点可用份额 = 其覆盖时段的需求占比之和。

[EXT-14] 若换成逐小时需求曲线，把 DEMAND_SHARE 换成 24 维向量即可。
"""
from __future__ import annotations

from typing import Dict, Tuple

from .schema import Instance, Site

PERIODS: Dict[str, Tuple[float, float]] = {
    "day": (9.0, 17.0),
    "evening": (17.0, 22.0),
    "night": (22.0, 9.0),   # 跨零点
}
DEMAND_SHARE: Dict[str, float] = {"day": 0.45, "evening": 0.40, "night": 0.15}
COVER_MIN = 0.5


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    """两个区间的重叠长度（支持跨越 0 点的窗口）。"""
    def segs(x0, x1):
        return [(x0, x1)] if x0 <= x1 else [(x0, 24.0), (0.0, x1)]
    total = 0.0
    for s0, s1 in segs(a0, a1):
        for t0, t1 in segs(b0, b1):
            total += max(0.0, min(s1, t1) - max(s0, t0))
    return total


def period_covered(site: Site, period: str) -> bool:
    p0, p1 = PERIODS[period]
    length = (p1 - p0) if p0 <= p1 else (24.0 - p0 + p1)
    if length <= 0:
        return False
    return _overlap(site.open_hour, site.close_hour, p0, p1) / length >= COVER_MIN


def availability_share(site: Site) -> float:
    return round(sum(DEMAND_SHARE[p] for p in PERIODS if period_covered(site, p)), 4)


def availability_table(inst: Instance) -> Dict[str, float]:
    return {s.id: availability_share(s) for s in inst.sites}


def period_mix(inst: Instance) -> Dict[str, Dict[str, float]]:
    """每个站点覆盖的时段，便于论文列表。"""
    return {s.id: {p: period_covered(s, p) for p in PERIODS} for s in inst.sites}
