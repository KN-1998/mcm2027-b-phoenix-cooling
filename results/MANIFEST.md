# 可引用结果清单

生成时间：2026-11-18T16:43:57

> **引用任何数字前**：确认 `git_sha` 与你手上的代码一致、`inputs` 与当前 `data/processed` 一致。
> 标 `dirty=true` 的运行说明当时工作区有未提交改动，**不能仅凭父提交复现**。

| 目录 | 提交 | 脏 | 关键参数 | 说明 |
|---|---|---|---|---|
| `levers` | `d13e099` | — | p=3, out=results/levers | p=3 基线口径；容量翻倍/枢纽延时为 ±0 表示容量不绑定 |
| `q2_attribution` | `d13e099` | ⚠️ | p=3, scenario=base, access_mode=walk_min, thresholds=20,30,45,60 | 未满足归因（只算激活站点） |
| `q2_objectives` | `d13e099` | ⚠️ | scenario=base, access_mode=walk_min, max_minutes=30.0, pmax=8 | 固定点集上的分配目标比较（非公平选址） |
| `q3_week` | `d13e099` | ⚠️ | p=3, max_minutes=30.0, top_k=3, shock_districts= | 七日累计；静态 vs 动态 DP；首日不计停服 |
| `q4_response` | `d13e099` | ⚠️ | p=3, mults=1.0,1.8,3.0, down_sites=R01,C01, down_vehicles=MCH-3,MCH-7 | 位置不可用 vs 车辆故障；超预算方案不计可执行收益 |
| `real_network` | `d13e099` | ⚠️ | modes=walk_min,transit_min, thresholds=20,30,45,60, pmax=8, out=results/real_network | MAG 2026 真实网络；区质心口径会高估不可达 |
| `run_csv` | `d13e099` | ⚠️ | p=3, max_minutes=30.0, capacity=250.0, seed=2027 | 端到端流水线输出 |
| `segments` | `d13e099` | ⚠️ | p=3, shares=0.3,0.5,0.7, out=results/segments | 无家可归者占比 0.3/0.5/0.7 情景 |
| `sweep` | `d13e099` | ⚠️ | p=0,2,3,4,6,8, access_modes=walk_min, scenarios=base, ushares= | 一维/多维参数扫描，每行一个配置 |
| `sweep_levers` | `3a4c535` | ⚠️ | p=3, access_modes=walk_min, scenarios=base, ushares= |  |
| `sweep_transit` | `2d74f7a` | ⚠️ | p=0,2,3,4,6,8, access_modes=transit_min, scenarios=base, ushares= | 公交口径（GTFS 站点的代理时间） |

## 输入哈希分布（同一输入应只有一种哈希）

| 输入 | 哈希 | 出现次数 |
|---|---|---:|
| `access.csv` | `dc990ef1d8658091` | 11 |
| `demand.csv` | `35475d9dc3154690` | 1 |
| `demand.csv` | `b6041bb74bbfbae3` | 10 |
| `districts.csv` | `0ad48911cabcdabb` | 10 |
| `districts.csv` | `cbe157664e20bb50` | 1 |
| `incoming/README.md` | `939c03c95ed9aa21` | 9 |
| `incoming/access_gtfs.csv` | `6389533cdf0f5367` | 9 |
| `incoming/acs_districts.csv` | `925f834bcfbc8bd6` | 9 |
| `incoming/sites_mag.csv` | `6479ea0864da206e` | 9 |
| `sites.csv` | `6576a3e4eb6867bc` | 11 |

## 单位

- `unmet_total`: 人次/日（day0 或该 runner 指定日）
- `unmet`: 人次/日或七日累计（看目录说明）
- `coverage_rate`: 比例
- `coverage`: 比例
- `worst_unmet_ratio`: 比例（全 12 区）
- `worst_excl_structural`: 比例（排除结构性不可达）
- `response_gain`: 人次/日
- `relocation_gain_7day`: 人次/七日累计
- `static_total_unmet`: 人次/七日累计
- `dynamic_total_unmet`: 人次/七日累计