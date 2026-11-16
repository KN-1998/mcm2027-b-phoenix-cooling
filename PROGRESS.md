# PROGRESS — Problem B 进度

> 格式：每条一行，日期 + 谁 + 做了什么 + 交付物。

## 2026-11-16
- [全员] 工作区重建：A 题完整归档（231 MB），B 题目录骨架 + `PRACTICE_NOTES` 就位。
- [待办] 读题拆解 → `modeling/MODEL_SPEC.md` 骨架。

## 编程手提问（实时接口）

| 时间 | 提问 | 倾向解法 | 等级 | 建模手决定 |
|---|---|---|---|---|
| — | （暂无） | — | — | — |
- [建模手] 资料库建立：4 份官方 PDF 落地（2026/2025 高温响应计划、2025 逐周运营报告、县热监测方法学）+ 1 篇文献全文；队友交接包（题意译文/来源索引/分工）并入 `资料/09_队友交接参考/`。
- [建模手] 产出 `资料/00_数据主表.md`（A 已下载 / B 待取 / C 文献 / D 自建）与 `handoff/MODELER_HANDOFF_2026-11-16.md`。
- [待办] 编程手：最小原型（T1，≤200 行，4 条断言）。
- [待办] 建模手：12 区/8 点/可达矩阵/需求 四张 CSV。
- [建模手] 框架落地：`src/mch/`（schema/synthetic/access/demand/equity/metrics/static/dynamic/disruption/policy/validate）+ `src/exp/run_pipeline.py`；6 项测试通过；端到端出数（Q1–Q5）。
- [建模手] 扩展点标注完成：`[EXT-01]`–`[EXT-15]`，索引 `docs/EXTENSION_POINTS.md`；`docs/MODEL_CONTRACT.md` 骨架。
- [基建] 新建仓库 https://github.com/KN-1998/mcm2027-b-phoenix-cooling ，已邀请 shaoshuiyu0222、EveyGA（push 权限）。
- [建模手] 四张核心数据表落地：`districts.csv`(12) / `sites.csv`(21) / `access.csv`(252) / `demand.csv`(252)；生成脚本 `tools/build_data.py`；字典 `data/DATA_DICTIONARY.md`。
- [建模手] 需求用 2025 周报标定：全季 44,508 人次、峰值周日均 561.3 人次/日；模型峰值日 = 561.3 ✅。
- [建模手] 新增 `diagnostics.access_gap`：**零可达区 D07/D08/D10/D11**（30 分钟步行）；边际收益在 p=3 归零。
- [建模手] 修正 Q5 规则：改为"边际收益 ≥5 人次/日 且 ≥2% 才增购"，避免在结构性不可达区上无限加购。
- [建模手] Q2 公平优化落地：`solve_static_fair` / `efficiency_equity_frontier` / `attribute_unmet`，三个 runner（fairness / attribution / tradeoff）。
- [建模手] **核心结果：p=2 时效率最优留下一个区 100% 未满足；max-min 方案代价 +2.1 人次/日(+7%)、覆盖 −0.5pp，把最差区降到 32%**。
- [建模手] 归因：残余未满足全部是 `no_access`（不是容量、不是选点）；D08 结构性不可覆盖，需非枢纽手段。
- [建模手] 网络重构：既有冷却中心 10 个 + 容量 50/日（使容量成为约束）；D07/D10 各配一个候选点，D08 仅饮水站。
- [测试] 14 passed（新增 4 项公平性测试，含 p=2 权衡的存在性断言）。
- [建模手] EXT-14 开放时段落地：`src/mch/hours.py`（三段：白天45%/傍晚40%/夜间15%，站点覆盖≥50%计可用）；有效容量 = 容量 × 可用份额。
- [建模手] **关键发现：现有网络是"白天网络"**——白天 22 站开放，傍晚与夜间只有 1 个 24/7 中心。
- [建模手] **政策杠杆对比（p=3）**：延长固定中心到 22:00 使未满足 −93.1（130.5→37.4），是"再加三台枢纽"（−52.7）的 1.8 倍；移动枢纽延时无效（容量不绑定）。
- [建模手] 交接文档 `handoff/HANDOFF_2026-11-16.md`：三结果 + 论文主线 + T1–T5 TODO + 七条限制。
- [测试] 14 passed。
