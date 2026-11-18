# 数据字典（`data/processed/`）

> 生成脚本：`tools/build_data.py`（**唯一来源**，改数据就改脚本再重跑，不要手改 CSV）。
> 重新生成：`python tools/build_data.py`
> 载入：`src/mch/loaders.py` → `load_instance(scenario=..., access_mode=...)`

## 0. 可信层级（每条记录带 `source` 字段）

| 标签 | 含义 | 本数据集中的例子 |
|---|---|---|
| `OBS_2025` | 2025 年官方周报直接读出 | 全季 44 508 人次、峰值周日均 561.3 人次/日 |
| `PLAN_2026` | 官方计划/网络文本 | 站点类型（respite/cooling/hydration/donation）、24/7 中心存在 |
| `SYNTHETIC_ESTIMATE` | 类合成，量级来自公开常识，非 ACS 实测 | 区人口、收入、65+、无车、树冠、热暴露 |
| `CONTEST` | 题面虚构 | 12 区、8 候选点、250 人次/日 |
| `ESTIMATE_LINEAR` | 直线距离 × 绕行系数 ÷ 速度 | 全部行程时间 |

> **写论文时必须标注**：12 区是"模拟规划区"，不是 Phoenix 官方 designation；8 个候选点是虚构；行程时间是直线代理，不是 GTFS。

---

## 1. `districts.csv`（12 行）

| 列 | 类型 | 单位 | 说明 |
|---|---|---|---|
| `district_id` | str | — | `D01`–`D12` |
| `district_name` | str | — | 名称；多村合并的用 `–` 连接 |
| `villages_mapped` | str | — | 由哪些 urban village 聚合（**Phoenix 实际 15 个村 → 12 区**） |
| `population` | int | 人 | 按 1.65M 总量等比缩放 |
| `pct_65plus` | float | 0–1 | 65 岁以上比例 |
| `pct_no_vehicle` | float | 0–1 | 无车家庭比例 |
| `median_income_usd` | float | USD/年 | 家庭收入中位数 |
| `canopy_pct` | float | 0–1 | 树冠覆盖（热暴露代理） |
| `heat_exposure_index` | float | 0–1 | 归一化热暴露（与树冠负相关） |
| `vulnerability` | float | 0–1 | = (65+/0.30 + 无车/0.35 + 低收入项)/3 |
| `lat`/`lon` | float | 度 | 近似质心 |
| `source` / `note` | str | — | 可信层级与说明 |

**校准（2026-11-17）**：人口、收入中位数、65+、无车比例已按 **ACS 2024 1-year（Phoenix city, 16000US0455000）** 校准：
城市合计人口 1,673,122、收入中位数 $85,246、65+ 12.9%、无车家庭 **7.42%**（B25044: 003 业主无车 8,523 + 010 租户无车 38,296 / 001 总户数 631,270）。
**区内差异仍为假设**（保持相对排序，按比例缩放/平移命中城市总量）。

**已知限制**：区级分布不是 ACS 实测。真实 ACS 接入点见 `docs/EXTENSION_POINTS.md` EXT-04。

## 2. `sites.csv`（22 行 = 14 既有 + 8 候选）

| 列 | 类型 | 单位 | 说明 |
|---|---|---|---|
| `site_id` | str | — | `C01`–`C08` 冷却中心、`H01`–`H04` 饮水站、`R01` 24/7 休息中心、`MCH-1..8` 候选 |
| `kind` | str | — | `cooling` / `hydration` / `respite` / `donation` / `candidate_mch` |
| `district_id` | str | — | 所属区 |
| `capacity_visits_per_day` | int | 人次/日 | 既有冷却中心取 **50**（ASSUME，使容量成为真实约束）；饮水站 0（不构成降温容量）；候选点 250（题面） |
| `open_hour`/`close_hour` | float | 24h 制 | 既有设施按常规办公时间；`R01` 为 0–24 |
| `source` | str | — | `PLAN_2026` / `CONTEST` |

**重要约定**：`boundary` 类设施不可互换——`hydration` 只供水，**不计入降温容量**（题面明确）。分配时的资格规则见 `schema.eligibility()`。

## 3. `access.csv`（264 行 = 12 区 × 22 站）

| 列 | 类型 | 单位 | 说明 |
|---|---|---|---|
| `km` | float | km | 直线距离 × **1.35** 绕行系数 |
| `walk_min` | float | 分钟 | 4.8 km/h |
| `transit_min` | float | 分钟 | 15 km/h + **10 分钟候车** |
| `drive_min` | float | 分钟 | 30 km/h |
| `source` | str | — | `ESTIMATE_LINEAR` |

**GTFS 实测（2026-11-18）**：`data/incoming/access_gtfs.csv` 用 City of Phoenix GTFS（8,101 站）重算公交时间：
步行到最近站 + 10 min 候车 + 站间直线×1.4/25 km/h + 下车步行。**仅在 `--access-mode transit_min` 时生效**。

**已知限制**：直线代理会**低估**实际行程（尤其跨河/高速），且未含时段拥堵；GTFS 为 City of Phoenix feed，不含 Valley Metro 全部区域线路。真实 GTFS 接入点：EXT-05。
**当前选择的默认模式**：`walk_min`（依据：2025 周报逐周显示 **56%–66% 步行/骑行**到达，末周为 56%）。**注意：早季 63% 不能代表全季。**

## 4. `demand.csv`（504 行 = 3 情景 × 12 区 × 7 天 × 2 分群）

| 列 | 类型 | 单位 | 说明 |
|---|---|---|---|
| `scenario` | str | — | `low`(×0.5) / `base`(×1.0) / `high`(×2.0) |
| `district_id` | str | — | — |
| `day` | int | 0–6 | 热浪第 1–7 天 |
| `segment` | str | — | `housed` / `unsheltered`（无家可归者占比为**情景参数**，基础 0.5） |
| `demand_visits` | float | 人次/日 | 该分群的需求，见公式；两分群相加 = 区日需求 |
| `heat_exposure`, `vulnerability` | float | 0–1 | 复述，便于核查 |
| `note` | str | — | 标定说明 |

**分群时段结构**（P1-5）：`housed` 白天/傍晚/夜间 = 0.55/0.38/0.07；`unsheltered` = 0.30/0.45/0.25。
混合后随无家可归者占比变化；观测的 69%–83% 是**到访者中的比例（选择效应）**，故只做情景扫描。

**公式**
$$D_{i,t}=k\cdot \text{pop}_i\,(0.4+0.6E_i)(0.6+0.8V_i)\,f_t,\quad f=[1.00,1.05,1.18,1.30,1.22,1.08,0.95]$$

**标定**：选 $k$ 使 7 天峰值日全城合计 = **561.3 人次/日**（2025 观测峰值周日均）。

**校验值**（`calibration.json`）：

| 量 | 观测 | 模型 |
|---|---|---|
| 全季平均 | 292.8 人次/日 | base 情景 day0 合计 431.6（day0 是热浪日，不是全季平均，**不直接可比**） |
| 峰值周日均 | 561.3 人次/日 | day3（$f=1.30$）合计 561.3 ✅ |

**已知限制**：观测只覆盖**市运营的休息/延时降温中心**，MAG 全网（图书馆、社区中心等）未计入 → `base` 应视为**下界**，`high`(×2) 覆盖未观测部分。

---

## 5. 复现与校验

```powershell
python tools/build_data.py          # 重建四张表
python -m pytest tests -q           # 含 CSV 载入与校验
python -m src.exp.run_pipeline --p 3 --data csv --out results/run_csv
```

**当前诊断结论**（`--data csv`，walk/30min）：
- **零可达区 = D07 / D08 / D10 / D11**（无任何室内降温设施在 30 分钟步行内；D08 只有饮水站，按题面不能替代）；
- 网络覆盖 p=0 时 77.6%，p=3 时 82.6%；
- **边际收益在 p=3 归零**——残余未满足需求是**结构性不可达**，不是枢纽数量不足。这正好回答 Q2"何时再加一个枢纽几乎无益"。

---

## 6. 预留字段（真实资料接入后替换）

> 机制：把文件放进 `data/incoming/`（见该目录 README），程序自动覆盖，无需改代码。
> 状态：⬜ 待填 / ✅ 已填 / ➖ 不适用

| 目标 | 现在的值 | 将被什么替换 | 状态 |
|---|---|---|---|
| 站点坐标 | 区质心（`SYNTHETIC(centroid)`） | `data/incoming/sites_mag.csv` 的 `lat/lon` | ⬜ M1 |
| 站点类型 | 按 2026 计划推断 | 同上 `kind` | ⬜ M1 |
| 站点容量 | 固定中心 50 / 枢纽 250（ASSUME） | 同上 `capacity` | ⬜ M4/M9 |
| 开放时段 | 9–17 / 9–19（ASSUME） | 同上 `open_hour/close_hour` | ⬜ M1 |
| 区人口/65+/无车/收入 | 城市总量已按 ACS 校准，**区内为假设** | `data/incoming/acs_districts.csv` | ⬜ M7 |
| 行程时间 | 直线 × 1.35 ÷ 速度 | `data/incoming/access_gtfs.csv` | ⬜ M8 |
| 观测需求 | 由 2025 峰值周总量标定的潜在需求 | `data/incoming/demand_observed.csv` | ⬜ 选填 |
| 运营成本 | 仅有芝加哥 Pilsen 量级参照 | **暂无接入位**（`src/mch/metrics.cost_breakdown` 预留） | ⬜ M9 |
| 热暴露 | 区级指数（估计） | 暂无接入位（需 Shade Study / LST） | ⬜ M6 |

**填完后必须重跑**：`tools/build_data.py` → `pytest` → `run_levers` / `run_sweep` / `run_q4_response`，并在 `run_meta.json` 里核对 `inputs` 哈希已变。
