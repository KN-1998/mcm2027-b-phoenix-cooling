# 官方服务结果与运营资料补全

检索/下载日期：2026-11-21（Asia/Shanghai）。原件保留，`source_manifest.json`列机构、直接URL、文件路径、字节数和SHA256。

- `raw/Week*.pdf`：2026年22个报告期间的City of Phoenix Weekly Heat Response Report；周到访直接取第2页Report week列，不从累计列差分。Week1为3天、Week22为10天，主要检验排除。
- `raw/Heat Relief Sites 2026 Season Totals.pdf`：季末项目点范围/运营月份，未把图表抽取粘连数值自动用作目标。
- 同名`.txt`是pypdf派生检索文本，原始证据仍为PDF；关键计数与源错误已渲染原件核对。
- `weekly_index.html`：官方索引快照，Week8位于另一目录，未因URL缺`/2026/`而漏掉。
- `noaa_2026_phoenix_sky_harbor_daily_summaries.csv`：NOAA NCEI USW00023183、2026May—Sept、TMAX/TMIN、`units=standard`华氏、属性列保留。非GSOD站号猜测，实际使用daily-summaries API。
- `noaa_api_documentation.html`：官方请求、属性和单位说明快照。
- `official_operations/`：城市May6和July运营公告PDF，支持Jackson/Justa/Cholla地址和时窗。
- `source_operating_corrections.json`：明确字段来源、季节、MAG冲突和未给出的开门时刻；只作显式overlay，不改原MAG。
- `validation_protocol.json`：机器解析整包目标和拟合前固定的时间划分与候选；已披露检索时见到一个测试周值，非完全盲法或外部预注册。

解释、推导、真实时间留出、失败后退回基线与结论边界见 `docs/EMPIRICAL_VALIDATION_20261121.md`。该资料证明的是一个固定站周已实现服务记录及限定预测检验，不是全市潜在需求/实际覆盖或因果健康效果。
