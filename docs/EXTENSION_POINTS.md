# 扩展点清单（EXT）

> 代码里所有可替换/可增强的位置都用 `[EXT-nn]` 标注，本文件是索引。
> 约定：**扩展点只改一个文件的一个函数，不改下游接口**。改完请补一条测试。

| ID | 位置 | 现状 | 怎么扩展 | 影响面 |
|---|---|---|---|---|
| **EXT-01** | `src/mch/schema.py` `SERVICE_RANK` | 4 类站点 + 候选点，按服务等级排 | 加"夜间开放/可带宠物/需预约"等属性 → 改 `eligibility()` | 分配资格、Q2/Q3 全覆盖 |
| **EXT-02** | `schema.District.extra` | 预留 dict | 加语言障碍、独居、慢性病率等 | 需求权重 |
| **EXT-03** | `schema.eligibility()` | 行程阈值 + 服务等级 | 加时间窗、开门时段、排队 | 全部分配结果 |
| **EXT-04** | `synthetic.build_instance()` | 合成 12×8 网络 | 实现 `loaders.load_real_instance()`，返回同一 `Instance` | 全流程 |
| **EXT-05** | `access.build_minutes()` | 直线距离 × 速度 | 接 GTFS（公交）/ OSM 路网（步行/驾车），返回分钟 | 可达矩阵 |
| **EXT-06** | `demand.RATE_BASE` | 0.004 人次/人/日（ASSUME） | 用 D3 逐周到访量反推 + 敏感性 | 需求规模 |
| **EXT-07** | `demand.vulnerability()` | 65+/无车/低收入 等权 | 改权重或换 CDC SVI 指标 | 需求分布与公平 |
| **EXT-08** | `equity.py` | Gini / 最差未满足率 / 最小覆盖 | 加 Atkinson、Theil、分位比 | Q2/Q5 结论 |
| **EXT-09** | `metrics.cost_breakdown()` + `configs/base.yaml` | 购置/日运营/迁移三档 ASSUME | 换真实预算或加贴现 | Q5 |
| **EXT-10** | `static.solve_static_milp()` | 抛 `NotImplementedError` | 接 pulp/ortools 做选址+分配联合最优 | Q2 精度（现为枚举+贪心，小算例已精确） |
| **EXT-11** | `dynamic.move_time_hours()` | 0.5 h 搭建 + 40 km/h | 接路网/时段拥堵 | Q3 迁移代价 |
| **EXT-12** | `disruption.run_disruption()` | 单中心失效 + 两区需求 ×1.8 | 加设备故障概率、路网中断、需求预测误差的蒙特卡洛 | Q4 |
| **EXT-13** | `policy.five_year_plan()` | 规则式（未满足率触发加 1 台） | 换动态规划/最优控制 | Q5 |
| **EXT-14** | `schema.Site.open_hour/close_hour` | **已建模但未进入约束** | 在 `_assign()` 加"服务时段 ∩ 需求时段"约束 | Q1/Q2/Q3（**优先做**） |
| **EXT-15** | `static._assign()` | 贪心 | 换最小费用流 / 匈牙利分配 | 分配最优性 |

---

## 已知的实现边界（不是 bug，但写论文要说明）

1. **`worst_unmet_ratio` 恒为 1.0**：合成可达矩阵里约 48% 的区—站链接 > 30 分钟步行，存在**没有任何 30 分钟内站点**的区 → 结构性零覆盖。这正是模型要暴露的"不公平"，不是计算错误。
   真实数据接入后（EXT-05）应复核：若仍为 1.0，说明阈值 `max_travel_minutes` 与城市尺度不匹配，需要按步行/公交分模式设阈值。
2. **开放时段未约束**（EXT-14）：目前所有站点视为全时段可用，会**高估**夜间与清晨的覆盖。
3. **既有站点容量 0 = 不限**：真实冷却中心容量未知，题目只给了 MCH 的 250 人次/日。
4. **分配是贪心**（EXT-15）：在固定选址下不一定全局最优；但因每区只按最近站贪心，误差有限，可作为基线。

---

## 加新功能的推荐顺序

1. **EXT-14 时间窗**（Q1/Q3 直接相关，题面点名"开放时间"）；
2. **EXT-05 真实可达矩阵**（数据一到就换）；
3. **EXT-10 MILP**（若评委追问"选址是否全局最优"）；
4. **EXT-12 不确定性蒙特卡洛**（Q4 的"测试设备故障/需求预测误差"）；
5. 其余按需。
