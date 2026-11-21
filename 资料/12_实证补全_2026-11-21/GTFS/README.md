# GTFS排班OD补全来源卡

研究日期：2026-11-21。使用原仓库已归档数据，不将当日最新feed回填2026年7月。

- 发布者：City of Phoenix；服务范围Valley Metro及Sky Harbor，America/Phoenix时区。
- 原包：`资料/02_降温网络/GTFS/mdb-147-202606160033/mdb-147-202606160033.zip`。
- 原SHA256：`d8d421ce9b5667024ae32d6428d8546074d7d35e2819a1b5ef689cc7c6cc38f6`。
- 归档直链：[MobilityData原包](https://files.mobilitydatabase.org/mdb-147/mdb-147-202606160033/mdb-147-202606160033.zip)。生产端点及获取manifest保留在原GTFS目录。
- 官方规则：[GTFS Schedule Reference](https://gtfs.org/documentation/schedule/reference/)，于2026-11-21打开核验calendar/calendar_dates、stop_times、frequencies、transfers条目。
- 本轮路由：`src/mch/gtfs_routing.py`；复算器：`src/exp/run_gtfs_validation.py`；专项测试：`tests/test_gtfs_routing.py`。
- 主说明：`docs/GTFS_VALIDATION_20261121.md`。

实质新增为有日期/出发时刻、包含上/下车权限和换乘的OD，替换“车站距离就是公交旅程”的旧代理。普通班次在明示有界模型内求最早到达，非exact频率为单headway等待上界情景或明确排除。步行、区代表位置、有限换乘、实时延误和前日service继承边界均明确披露。

结果分两层：`results/complete_20261121/gtfs`为MAG-only32目的；`gtfs_city_operations`为城市运营修正后34目的。不能将增加两站的收益归因于交通算法。两层都是条件模型对照，不是实际居民乘车或服务覆盖的实证验证。
