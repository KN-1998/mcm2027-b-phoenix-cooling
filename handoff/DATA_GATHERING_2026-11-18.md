# 资料搜集交接 — 2026-11-18

仓库：`mcm2027-b-phoenix-cooling`

本记录接续 `资料/00_数据主表.md`。新增数据均保留原始文件；没有把无法下载的网页/PDF记作本地资料，也没有从现有数据推断设施因果效果。

## 已取得并完成基本核验

| 主题 | 文件 | 核验与边界 |
|---|---|---|
| 公交 GTFS | `资料/02_降温网络/googletransit.zip` | 7,210,122 bytes；ZIP `testzip()` 无错误；13 个文件。`feed_info.txt` 标记 City of Phoenix、`GTFS_v4.5_20260914`，服务期 2026-10-26 至 2027-01-24。官方 Valley Metro 开发页说明静态 GTFS 在 Phoenix Open Data；该源当前返回 403，所以落地文件是 MobilityDatabase 的 2026-11-11 快照。链接：[Valley Metro 开发者资源](https://www.valleymetro.org/contact/developers-resources)、[MobilityDatabase feed](https://mobilitydatabase.org/feeds/gtfs/mdb-147)、[ZIP](https://files.mobilitydatabase.org/mdb-147/mdb-147-202611110057/mdb-147-202611110057.zip)。 |
| ACS 人口与脆弱性 | `资料/04_人口与地理/acs2024_5yr_phoenix_zcta_raw.json` | 39,270 bytes；JSON 解析通过；11 个 ZCTA（85003、85006、85008、85009、85015、85017、85031、85033、85035、85041、85051）。包含人口 B01003、收入 B19013、车辆可用性 B08201、年龄 B01001 的估计和误差值；ACS 2024 5-year，即 2020–2024 汇总估计。原始 API：[Census Reporter 查询](https://api.censusreporter.org/1.0/data/show/acs2024_5yr?table_ids=B01003%2CB19013%2CB08201%2CB01001&geo_ids=86000US85003%2C86000US85006%2C86000US85008%2C86000US85009%2C86000US85015%2C86000US85017%2C86000US85031%2C86000US85033%2C86000US85035%2C86000US85041%2C86000US85051)。注意 ZCTA 不是 Phoenix Urban Village。 |

## 找到入口，未拿到要求的完整原始数据

| 主题 | 可用来源 / 已确认信息 | 仍缺内容 |
|---|---|---|
| MAG 降温网络目录 | [MAG 官方页面](https://azmag.gov/Programs/Community-Initiatives/Heat-Relief-Network)、[互动地图](https://hrn.azmag.gov/map?lat=33.4545618&lng=-112.0709948)、[ArcGIS 元数据](https://geo.azmag.gov/arcgis/rest/services/maps/Heat_Relief_Network/MapServer?f=pjson)。网页可浏览部分 2026 点位；ArcGIS 元数据年份有歧义。 | 当前季全量站点导出（名称、地址/坐标、类型、开放时间）及可复用本地文件。不要将旧 GIS 服务当 2026 完整数据。 |
| Urban Village ACS | [Phoenix 2024 Community Assessment PDF](https://www.phoenix.gov/content/dam/phoenix/humanservicessite/documents/hsd-/2024%20hsd%20community%20assessment%20report%20year%202%20update%20and%20appendices%20-%20final.pdf) 提供部分 15 个 Village 的人口/年龄/收入，年份为 ACS 2018–2022。 | village 级无车家庭数据；PDF 本地副本。现有 ZCTA JSON 不可直接当 Village 数据。 |
| Phoenix 本地运营费用 | [2026 市议会材料](https://phoenix.legistar.com/LegislationDetail.aspx?From=RSS&GUID=6A1EF527-2071-479C-ACCC-B343C1C69F87&ID=7924230)：2025 多站点延时/夜间项目约 $4.3M，2026 项目需求约 $5.25M；[服务合同材料](https://phoenix.legistar.com/LegislationDetail.aspx?GUID=8DA9469F-1B49-4E07-8CF2-1ED4B4F37AA0&ID=7923913)：合同上限 $2.6M。 | 单个中心的实支成本、可容纳人数、人员排班/工资。上述数字是汇总或合同上限，不能拆成单站估计。 |
| 移动/临时中心案例 | [Tempe 市议会材料](https://www.tempe.gov/home/showpublisheddocument/116288/639035712865770000)：移动拖车以 $15,000 捐赠购置，ASU 协助改造，运营受到运输、供电、人员与监控成本约束；[州集装箱案例报道](https://www.axios.com/local/phoenix/2024/06/12/arizona-border-wall-shipping-container-cooling-center) 称计划改造 18 个。 | 每次部署成本、到访量/服务量、可复现运行台账；Tempe 原始 PDF 本地副本。集装箱 18 个是报道中的计划数，不是实测运营结果。 |
| 县级热健康数据 | [Maricopa 热监测页](https://www.maricopa.gov/1858/Heat-Surveillance)；[2025 年度死亡报告](https://www.maricopa.gov/ArchiveCenter/ViewFile/Item/6510)记录县级 430 例，含城市与部分 ZIP 事件地点；[2018–2022 多年发病报告](https://www.maricopa.gov/Archive.aspx?ADID=5855)。 | 实时急诊/住院仪表板当前标注暂不可用；未取得单独可分析的本地 ED 原始表。县级统计不构成中心的因果评估。年度报告 PDF 未保存到仓库。 |

## 论文/建模使用提醒

1. GTFS 是镜像快照，建公交行程时间前应检查服务日期、路线是否覆盖目标研究日，并记录镜像出处。
2. ACS 地理为 ZCTA，时段为 2020–2024 五年估计；合并或映射到规划区时必须说明空间转换，不可称为 Village 观测值。
3. 凤凰城热救助预算可作项目级预算背景，不可推成单站成本或每人次成本。
4. 2025 县级死亡数、城市/ZIP 事件地点与降温设施使用没有个体链接，不能写成设施减少/导致死亡的证据。
5. MAG 全量目录、逐中心容量与人力成本、移动设施利用率和急诊原始数据仍待队友补齐；无法取得时在论文限制中明确标注。
