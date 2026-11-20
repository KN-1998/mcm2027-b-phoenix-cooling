"""核心数据结构与校验。

约定
----
- 所有量都带单位，单位写在字段注释里。
- 类型标签：OBS 观测 / PLAN 官方计划 / LIT 文献 / SCENARIO 题目虚构 / ASSUME 假设 / NEED 待建。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# [EXT-01] 站点类型：题面只区分服务等级，如需加入"夜间开放/可带宠物"等属性，
#          在 SiteKind 增枚举并在 eligibility() 里加规则，不要改下游接口。
RESPITE = "respite"          # 可休息/过夜
COOLING = "cooling"          # 室内空调 + 饮水
HYDRATION = "hydration"      # 仅饮水
DONATION = "donation"        # 仅物资
CANDIDATE = "candidate_mch"  # 移动枢纽候选点

SERVICE_RANK = {DONATION: 0, HYDRATION: 1, COOLING: 2, CANDIDATE: 2, RESPITE: 3}


@dataclass
class District:
    """规划区（题目虚构的 12 个区，非 Phoenix 官方 village）。"""
    id: str
    name: str
    population: int                 # 人
    pct_65plus: float               # 0-1
    pct_no_vehicle: float           # 0-1
    median_income: float            # USD/年
    canopy_pct: float               # 0-1，树冠覆盖（热暴露代理）
    heat_exposure_index: float      # 0-1，归一化热暴露（NEED：由 LST/气温构造）
    lat: float = 0.0
    lon: float = 0.0
    # [EXT-02] 脆弱性可扩展：加入语言障碍、独居、慢性病等，然后更新 demand 权重
    extra: Dict[str, float] = field(default_factory=dict)


@dataclass
class Site:
    """既有站点或候选 MCH 点。"""
    id: str
    name: str
    kind: str                       # 见 RESPITE/COOLING/...
    district_id: str
    lat: float
    lon: float
    capacity: int = 0               # 人次/日；0 触发调用者的显式默认值，绝不表示已观测无限容量
    open_hour: float = 8.0          # 24h 制
    close_hour: float = 17.0
    source: str = "ASSUME"          # OBS/PLAN/SCENARIO/ASSUME
    # B7：字段级来源（class/坐标/容量/时段各自独立标注）
    extra: Dict[str, object] = field(default_factory=dict)


@dataclass
class Instance:
    districts: List[District]
    sites: List[Site]
    access: Dict[Tuple[str, str], float]      # (district_id, site_id) -> 分钟
    demand: Dict[Tuple[str, int], float]      # (district_id, day) -> 人次/日
    horizon_days: int = 7
    meta: Dict[str, object] = field(default_factory=dict)

    def candidate_sites(self) -> List[Site]:
        return [s for s in self.sites if s.kind == CANDIDATE]

    def fixed_sites(self) -> List[Site]:
        return [s for s in self.sites if s.kind != CANDIDATE]


def validate_instance(inst: Instance) -> List[str]:
    """返回问题清单；空表示通过。任何模型运行前都应调用。"""
    problems: List[str] = []
    import math
    d_ids = {d.id for d in inst.districts}
    s_ids = {s.id for s in inst.sites}

    if len(d_ids) != len(inst.districts):
        problems.append("district id 重复")
    if len(s_ids) != len(inst.sites):
        problems.append("site id 重复")
    if len(inst.districts) == 0:
        problems.append("没有区")

    for (di, sj), t in inst.access.items():
        if di not in d_ids:
            problems.append(f"access 含未知区 {di}")
        if sj not in s_ids:
            problems.append(f"access 含未知站点 {sj}")
        if not math.isfinite(t) or t < 0:
            problems.append(f"行程时间为负 {di}-{sj}")

    for (di, day), value in inst.demand.items():
        if di not in d_ids:
            problems.append(f"demand 含未知区 {di}")
        if not math.isfinite(value) or value < 0:
            problems.append(f"需求为负 {di}-day{day}")

    for d in inst.districts:
        if d.population < 0 or not (0 <= d.pct_no_vehicle <= 1):
            problems.append(f'{d.id} 人口或无车比例非法')
        if not (0 <= d.pct_65plus <= 1):
            problems.append(f"{d.id} pct_65plus 越界")
        if not (0 <= d.heat_exposure_index <= 1):
            problems.append(f"{d.id} heat_exposure_index 越界")

    for s in inst.sites:
        if s.kind not in SERVICE_RANK:
            problems.append(f"{s.id} 未知站点类型 {s.kind}")
        if not (0 <= s.open_hour <= 24 and 0 <= s.close_hour <= 24):
            problems.append(f"{s.id} 开放小时须在0至24内")
        if not math.isfinite(s.capacity) or s.capacity < 0:
            problems.append(f"{s.id} 容量为负")
        if s.kind == CANDIDATE and s.capacity > 250:
            problems.append(f'{s.id} 移动枢纽超过250人次/运营日上限')

    return problems


def eligibility(site: Site, minutes: float, need_kind: str = COOLING,
                max_minutes: float = 30.0) -> bool:
    """该站点能否服务该需求类型。

    [EXT-03] 现状：按服务等级 >= 需求等级 + 行程时间阈值。
              若要区分"仅白天/仅夜间"或"需预约"，在此扩展。
    """
    if minutes > max_minutes:
        return False
    return SERVICE_RANK.get(site.kind, 0) >= SERVICE_RANK.get(need_kind, 2)
