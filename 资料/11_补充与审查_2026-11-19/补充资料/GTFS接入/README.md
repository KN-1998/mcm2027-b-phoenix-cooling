# GTFS 接入核验与用法

核验日期：2026-11-19。使用仓库已有夏季原包，未重新下载、未修改任何模型输入。原包的发布者字段为 City of Phoenix，运营机构含 Valley Metro 和 Phoenix Sky Harbor International Airport；本包保留原 ZIP 的完整 SHA256 和归档 URL。

## 本次补齐的内容

`verify_summer_gtfs.py` 仅依赖 Python 标准库，可从仓库中的两个 ZIP 重新生成 `gtfs_schedule_validation.json`。核验包括 ZIP CRC、各表记录数、feed_info、时区、指定服务日的有效 service/trip、跨午夜时刻以及一条完整的发布班次样例。结果中的“trip 数”是 `trips.txt` 记录数，频率班次尚未展开，不能称当日实际发车总数。

```powershell
python verify_summer_gtfs.py --repo <仓库根目录> --out <输出目录> --date 2026-07-20
```

| 项目 | mdb-147-202606160033 | mdb-147-202607280152 |
|---|---:|---:|
| 发布有效期 | 2026-04-27 至 2026-07-26 | 2026-07-27 至 2026-10-25 |
| 站点记录 | 8,029 | 8,027 |
| 线路记录 | 112 | 112 |
| trips 记录 | 18,252 | 18,157 |
| stop_times 记录 | 918,117 | 915,650 |
| calendar_dates 记录 | 1,739 | 2,049 |
| 2026-07-20 有效 service 数 | 20 | 0 |
| 2026-07-20 有效 trip 记录数 | 7,762 | 0 |
| 全包时刻达到或超过24小时的 stop_times 行 | 3,619 | 3,192 |

**两个包都没有 `calendar.txt`，这符合 GTFS 标准。** 它们用 `calendar_dates.txt` 逐日列服务，而不是从 service_id 中的 “Weekday” 字符串推断。第二包在7月20日没有服务覆盖；不得把它的7月27日以后班次直接用于7月20日，也不得把两个包同名 trip 当作额外班次重复叠加。

第一包的样例为7月20日有效的 `trip_id=23183006`、线路68CM：Granite Reef Senior Center 06:01 发车，Indian School Rd & Hayden Rd 06:34 到达，35个停站记录，计划车上时间33分钟。该样例位于区域网络中，仅用于验证表间连接和时刻解析；它不对应某个模拟区至 MCH 的完整旅程。第二包另用其首个有效日期7月27日提供单独标记的样例，保留7月20日结果为零。

## 建模手应按以下步骤接入

1. 先指定历史服务日期、当地出发时刻和情景使用的 feed 版本。`agency_timezone` 为 `America/Phoenix`；2026年计划表用于2027年研究时应标为历史代理。
2. 解析 `calendar.txt` 的星期及起止日（若有），然后应用 `calendar_dates.txt` 的新增/删除。只有日期有效的 service_id 所属 trip 才能进入路由。
3. 用 `trip_id` 连接 `trips` 与 `stop_times`，按 `stop_sequence` 排序；用 `stop_id` 连接坐标和名称。保留上下车限制、`timepoint` 和换乘要求。`24:30:00` 应解析为服务日起第88,200秒，不要取模变成同日00:30。
4. 计算起点至上车站步行、候车、乘车、换乘步行/等待及末站至设施步行，遵守 `transfers.txt`。`frequencies.txt` 中的4行也要处理，频率模板不应直接作为唯一一次固定发车。
5. 让直接步行成为备选方式：在相同步行可行性假设下，最短广义旅程不应超过可行的直接步行方案。区质心和候选点相距很近时，强制先走到远处公交站再返回会制造虚假的不可达。
6. 输出应包括服务日、出发时刻、到达时刻、trip/route/上下车站、换乘次数和步行段方法。缺少步行路网时可使用距离代理，但必须单独标注；不能把代理步行或计划班次耗时称为实测门到门旅行时间。

**当前 `stops` 坐标代理不足以完成上述路由。** “真实站点网络”与“交通时间算法”应分别做实验轴；替换固定设施时，候选点、出发时刻和交通计算方法应保持一致。距离公式与 GTFS 站点代理都需要清楚标注局限；两者的比较不能直接识别真实公交效果。

## 已核实的官方规范

原文来源：[GTFS Schedule Reference](https://gtfs.org/documentation/schedule/reference/)，页面标注修订日2026-04-27，本次于2026-11-19打开核验。

规范的 `calendar_dates.txt` 条目允许省略 `calendar.txt`、逐日列明服务；`Time` 与 `stop_times.txt` 条目要求跨服务日午夜的时刻保留大于24小时的写法；`frequencies.txt` 描述按发车间隔表示的班次。以上是对规范的独立概述，没有将计划时刻表解释为车辆实际运行观测。

原包由 MobilityData 的 [Valley Metro feed 归档页](https://mobilitydatabase.org/feeds/gtfs/mdb-147)取得；完整原件、发布端点、获取日期和校验记录已存原仓库 `资料/02_降温网络/GTFS/manifest_gtfs.json`。本补充 JSON 再次核对原件字节摘要，避免归档版本误配。
