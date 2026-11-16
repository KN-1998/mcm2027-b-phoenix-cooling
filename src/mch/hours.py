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

# ---------------------------------------------------------------------------
# P1-2 修正：时段容量按"营业时长内的吞吐率"计算，而不是把日容量乘需求占比
# ---------------------------------------------------------------------------

def window_length(site: Site) -> float:
    return ((site.close_hour - site.open_hour) if site.open_hour <= site.close_hour
            else 24.0 - site.open_hour + site.close_hour)


def overlap_hours(site: Site, period: str) -> float:
    p0, p1 = PERIODS[period]
    return _overlap(site.open_hour, site.close_hour, p0, p1)


def capacity_in_period(site: Site, daily_capacity: float, period: str) -> float:
    """该站在该时段最多能服务的人次。

    吞吐率 = 日容量 / 营业时长（小时），再乘该时段的营业重叠小时数。
    关门 => 0；全日营业 => 日容量 x 时段占比（与需求占比一致时才不产生偏差）。
    """
    L = window_length(site)
    if L <= 0 or daily_capacity <= 0:
        return 0.0
    return daily_capacity * overlap_hours(site, period) / L


def split_demand(total: float) -> Dict[str, float]:
    return {h: total * DEMAND_SHARE[h] for h in PERIODS}

# ---------------------------------------------------------------------------
# P1-5 后半：分群时段结构（有住所 / 无家可归者）
# ---------------------------------------------------------------------------
# 观测依据：2025 周报显示市运营休息/延时中心的到访者中 69%-83% 自述无家可归。
# 但这是"到访者中"的比例（选择效应），不能直接当全市人口比例。
# 因此把"无家可归者占比"作为**情景参数**，并给区间。
UNSHELTERED_SHARE = {"low": 0.30, "base": 0.50, "high": 0.70}

PERIOD_SHARES_BY_SEGMENT = {
    "housed":       {"day": 0.55, "evening": 0.38, "night": 0.07},
    "unsheltered":  {"day": 0.30, "evening": 0.45, "night": 0.25},
}


def mixed_period_shares(unsheltered_share: float) -> Dict[str, float]:
    u = max(0.0, min(1.0, float(unsheltered_share)))
    return {h: (1 - u) * PERIOD_SHARES_BY_SEGMENT["housed"][h]
               + u * PERIOD_SHARES_BY_SEGMENT["unsheltered"][h]
            for h in PERIODS}


def split_demand_mixed(total: float, unsheltered_share: float) -> Dict[str, float]:
    sh = mixed_period_shares(unsheltered_share)
    return {h: total * sh[h] for h in PERIODS}
