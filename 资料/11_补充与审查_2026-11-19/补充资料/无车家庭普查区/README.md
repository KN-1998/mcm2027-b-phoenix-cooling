# Maricopa 普查区无车家庭：ACS 2024 五年估计

检索日期：**2026-11-19**。数据年份：**2020–2024**。地域：Arizona 州04、Maricopa 县013的 **1,009 个 Census Tract**。这些是全县普查区，不是 Phoenix 市内普查区子集，也不是题目的12个模拟区。

## 取得了什么

`maricopa_tract_no_vehicle_acs2024_5yr.csv` 提供每个普查区的11位GEOID、名称、总家庭数、无车家庭数、两项计数的90%置信水平误差范围（MOE），以及无车家庭比例的点估计。

| Census 变量 | 含义 | 分母/单位 |
|---|---|---|
| B08201_001E | 总家庭数估计 | 家庭/户，不是人口 |
| B08201_001M | 总家庭数MOE | 户，90%置信水平 |
| B08201_002E | No vehicle available 家庭数估计 | 户 |
| B08201_002M | 无车家庭数MOE | 户，90%置信水平 |

`pct_no_vehicle_fraction` 为002E/001E，范围0–1。例如0.10表示10%，不是0.10%。16个普查区总家庭数为0，这些区的比例留空，不能强行填0。原始响应完整保留表B08201其他栏目；派生CSV只抽取本任务需要的两项计数及误差。

## 来源与直接下载的区别

**数值响应来自 Census Reporter 的 ACS 镜像**，不是由本次任务从美国人口普查局API直接取得。镜像响应内 `release.id=acs2024_5yr`、`years=2020-2024`；表的 universe 为 `Households`，002栏目名称为 `No vehicle available`。

- [全部普查区镜像响应](https://api.censusreporter.org/1.0/data/show/acs2024_5yr?table_ids=B08201&geo_ids=140%7C05000US04013)
- [另行取得的Maricopa县总数镜像响应](https://api.censusreporter.org/1.0/data/show/acs2024_5yr?table_ids=B08201&geo_ids=05000US04013)
- [人口普查局官方B08201变量字典](https://api.census.gov/data/2024/acs/acs5/groups/B08201.json)
- [人口普查局官方变量字典HTML](https://api.census.gov/data/2024/acs/acs5/groups/B08201.html)
- [官方2024 ACS五年数据开发者页面](https://www.census.gov/data/developers/data-sets/acs-5year.2024.html)

本次对 Census 官方数据API的无key查询被重定向至 `https://api.census.gov/data/missing_key.html`，HTTP状态仍为200，但正文是Missing Key网页，不能当作成功取得JSON。官方开发者页面现已说明所有数据查询需API key。没有代用户注册key，也没有绕过验证。官方变量元数据JSON/HTML均已成功下载。

Census Reporter 首次请求返回403并提示 `use a user agent specific to your project`。按服务提示设置本项目描述性 User-Agent 后，正常返回200和JSON；未使用伪装浏览器、验证码绕过或私人凭据。完整URL、哈希和真实失败记录见本目录JSON。重新下载时可使用 `MCM-Phoenix-Heat-Relief-Research/1.0 (+https://github.com/KN-1998/mcm2027-b-phoenix-cooling)` 作为User-Agent。

## 实际核验

`derive_no_vehicle_tracts.py` 已执行成功。1,009个GEOID唯一且全部属于04013；所有估计完整，无车户数均介于0和总家庭数之间。各普查区合计总家庭数 **1,730,696**、无车家庭数 **88,150**，两者都与单独下载的县级同表同年份响应完全相等。由此得到的全县无车家庭比例约5.09%，不能直接移给 Phoenix 或每个模拟区。

比例的MOE没有计算，也没有声称统计显著性。原始计数MOE逐项保留。`validation.json`记录核验结果及源文件和CSV的SHA256。

可在本目录运行：

```powershell
python derive_no_vehicle_tracts.py
```

亦可用 `--input RAW_JSON --county COUNTY_JSON --out OUTPUT_DIRECTORY`，脚本只写派生结果，不修改原始响应或模型输入。

## 如何接入12区

先用官方村界和普查区边界定义空间对应关系，或以更细地理单元构建有依据的权重；不能仅按ZIP/站点地址给整区分配人口。整普查区归并时，应使用 `sum(无车户数)/sum(总家庭数)`。跨界普查区需要明确家庭分配权重；面积权重只是假设，不能称实测家庭分布。原始GEOID需按字符串保存，以免丢失前导0。

**不能简单相加MOE**。合并计数的近似MOE及比例MOE需依据ACS官方统计说明处理，同时说明协方差/抽样近似；本材料没有做村级MOE推断。

root同时补充的Phoenix 2024社区评估村表引用 **2018–2022 ACS**，本表为 **2020–2024 ACS**。不要把不同期别的分子、分母或年龄指标混在一起后统称同年观察。可以建立两个单独的校准情景，或先获得统一期别的全部指标再接入。

本次没有将这些县级普查区自动映射到15村或12模拟区，也没有覆盖现有合成模型。材料关闭的是“原始区级无车户数和家庭分母缺失”这项取数缺口；空间映射和统一期别仍需完成。
