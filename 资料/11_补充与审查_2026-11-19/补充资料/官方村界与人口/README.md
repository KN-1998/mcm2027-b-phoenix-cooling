# 官方15村边界、村级人口与12模拟区候选表

原件于2026-11-18取得，2026-11-19完成交接核验。这里提供可追溯的替代数据，不自动覆盖当前模型。

## 来源与读取定位

- [Phoenix官方村界服务](https://maps.phoenix.gov/pub/rest/services/Public/Villages/MapServer)：15个Urban Villages。该站直连超时后，使用[City of Phoenix发布的ArcGIS同名服务](https://services.arcgis.com/cfKakmeHE95cgeEK/ArcGIS/rest/services/Villages/FeatureServer)。`phoenix_villages_item_raw.json`确认owner为`City_of_Phoenix`，accessInformation为City of Phoenix Planning；原始GeoJSON完整15条。保留项目metadata和许可链接，不声称该2026快照与历史ACS汇总使用的边界逐点相同。
- [2024 HSD Community Assessment Year 2 Update原件](https://www.phoenix.gov/content/dam/phoenix/humanservicessite/documents/hsd-/2024%20hsd%20community%20assessment%20report%20year%202%20update%20and%20appendices%20-%20final.pdf)：PDF第34页（印刷A-1）提供全部15村人口、家庭、65–74岁及75+人数；第37页（A-4）提供7档家庭收入分组。原表数据期为**ACS 2018–2022**，不能写成2024人口普查或2026实测。第34、37页已渲染核对列顺序、表头和脚注。
- [2025 HSD Community Needs Assessment原件](https://www.phoenix.gov/content/dam/phoenix/humanservicessite/documents/hsd-/2025_HSD_CommunityNeedsAssessment_Report.pdf)：148页，封面日期August 2025；用于较新的城市背景、出行及服务需求参考，不能与2024附录当作同一批村级数据。

原始下载URL、重定向后URL、字节数及完整SHA256见`source_downloads_retry.json`；ArcGIS项目身份见`boundary_item_provenance.json`和原始项目JSON。原站失败响应仅留在`source_downloads.json`作检索记录，不能当有效原件。

## 新增可用文件

| 文件 | 用途 |
|---|---|
| phoenix_15_villages_raw.geojson | 官方发布边界原始响应，经纬度EPSG:4326；用于真实设施点落区及后续空间交叉 |
| village_demographics_acs2018_2022.csv | 15村原公布人数、家庭数、65+人数与收入分组；比例由人数相除 |
| village_to_contest_district.csv | 严格采用仓库`districts.csv`的15→12合并规则，每村只出现一次；这份合并是比赛建模选择 |
| district_demographics_candidate_12.csv | 按上述规则加总的人口、家庭、65+人数及收入分组，供建模手接入前审定 |
| derive_village_demographics.py | 不联网重建三张CSV，读取原PDF和仓库映射，检查17列及村名不重不漏 |
| derived_validation.json | 原件/映射哈希、字段状态与总量核验 |

村人口合计1,620,649、家庭合计595,336，均与该报告Phoenix栏完全一致。D10按原仓库“North Gateway + Rio Vista”合并为22,949人；当前合成表为114,298人。这说明区级分布会实质影响需求配置，接入后必须重新标定并重跑，而不能只更新背景文字。

## 需要保留的边界

1. `pct_no_vehicle`保持空值。该村级附录没有可直接使用的无车家庭表，不能用“附近没有MAG设施”推断无人居住或无ACS，也不能填0。另一个`无车家庭普查区`目录提供后续可用来源；转村仍需真实空间映射及家庭分母。
2. 收入使用原表7档**家庭户数**先合并，再定位合并分布的中位数所在档。`median_income_bracket_lower/upper`是中位数区间；`median_income_uniform_bin_proxy_usd`只是假定档内均匀后的插值代理。落入100,000以上开放档时不捏造上界和精确中位数。不能把这个字段改名成观测的`median_income_usd`。
3. 原表收入脚注同时印有“ACS 2018–2022”和“2021 Inflation-Adjusted Dollars”；保留原文，不自行修订币值年。与2024美元预算比较时应查清并做明确通胀处理。
4. 源表没有逐项MOE，不输出虚假的置信区间。收入档户数与公布家庭总数的细微差别记录在CSV，不擅自调整原始数。
5. 此处完成的是**资料与候选派生表**。12区仍是题设允许的模拟聚合；现有求解器尚未接入这组新数据，过去的数值不因此获得现实验证。

在仓库根目录执行（需pypdf）：

```powershell
python '资料/11_补充与审查_2026-11-19/补充资料/官方村界与人口/derive_village_demographics.py' --repo .
```

接入建议：先固定整套地理单元与数据期，生成单独的真实地理情景；保留原合成情景用于算法验证。容量、需求率、树冠率和热暴露指数仍需分别标明来源，不能因人口表变真实而把整条记录标成全部实测。
