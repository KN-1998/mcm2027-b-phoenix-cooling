# MAG公开视图的逐星期、节假日与有效期材料

来源为MAG官方HRN Public view于2026-11-18取得的原始响应，项目[官方身份入口](https://www.arcgis.com/home/item.html?id=bd08dde5206543018fe41da60d2551a7)，[图层入口](https://services1.arcgis.com/MdyCMZnX1raZ7TS3/arcgis/rest/services/HRN_Public_view/FeatureServer/0)。本次直接复用已核验原件，没有重新搜索、补写或改变源记录。

三个派生JSON分别保留该公开视图全部122条、源Year=2026的121条，以及其中Phoenix的50条。每条完整保存45项原属性和原几何，另外把七个weekday开关门字段、五个holiday字段分别规范为规则。原始响应、独立count/ID列表、官方项目metadata放在`原始响应/`。这些数量说明完整下载了这一视图，不证明2026全年站点均已列入，也不证明采集日仍然开放。

字段与判定：

| 字段/状态 | 含义与使用方式 |
|---|---|
| raw_attributes/raw_geometry | 原始属性与几何完整保留，不改变null、空字符串和数值类型 |
| start_date_raw/end_date_raw | 源公布有效日期；不能用Active=Yes覆盖已结束的日期范围 |
| weekday_rules | Monday至Sunday独立规则，不将最早开门和最晚关门拼成每天的共同营业窗 |
| open_raw/close_raw | 原始开关门文本；解析的分钟数只是本地钟表时间，不是有时区的绝对时刻 |
| open_missingness/close_missingness | 区分key_absent、null、blank_string、value |
| open_clock_pair | 两个钟表字段均可解析，保留分别开关门时间和跨午夜标志 |
| unknown_blank_pair | 两个字段为空，表示缺少明确开关门字段；不自动解释为Closed，也不默认9–17 |
| unknown_incomplete_pair | 只给单边时刻，需核验运营者或Hours/Note，不能补造另一边 |
| closed_explicit | 源字段明确Closed；常见于holiday列，可确实与空白区分 |
| inherit_selected_weekday | holiday为Regular Hours，继承所选实际日期对应weekday，不继承全周并集 |
| open_special_clock_pair | holiday明确给出特殊时段，保留该段；未解析文本标unknown并保留raw |
| capacity_visits_per_day | 始终null；源视图没有访客日容量，不能写0冒充无限，也不能写50冒充实测 |

源Hours与Note保留供人工核对，但本转换不把人类语言中未列出的星期擅自推断为明确Closed。比如Century Library星期一9–17、星期二10–18，分别保留；星期日字段空白保留unknown。节假日Closed则明确closed。

使用`python build_mag_calendar.py`可在不联网的情况下复现全部派生文件和核验。脚本提供`resolve_date(record, date_iso, holiday_field=None, holiday_check_complete=False)`：先检查源公布日期范围，再选实际星期；调用者须显式完成当地节假日/观察日核对，或指定源holiday列。没有完成节假日核对时只返回候选weekday规则和待核状态，不直接声称当天开门。此方法不预测2027–2031营业安排。

本材料用于替代真实网络loader把Mo–Fr取min/max后推广到7天的做法；尚未修改模型。正式接入仍需确定热浪起始日期、节假日观察日规则、未知时段处理方案，并对缺失容量单独做假设与敏感性分析。

来源、转换脚本及交付文件SHA256见`来源与文件哈希.json`；具体缺失分布见`日历缺失与范围摘要.json`。Year=2025但日期写2026的那条源记录保留在122原视图中，按Year筛出的121/50版本排除它，不擅自改正来源矛盾。
