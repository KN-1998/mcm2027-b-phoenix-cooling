# 2026-11-21 建模与代码补全入口

本轮基于队友最新bdb74e8，补资料、推导、代码和验证。用户已明确“论文先不写”，因此2702.tex保持该远程版本；本轮不上传论文改写、英文稿或论文排版产物。涉及文字/引用错误只列在模型交接中供论文手处理。

## 已补实质缺口

- 取得2026官方逐周/季末报告、NOAA逐日气温及运营资料，完成Jackson同站12/4/4的回顾性滚动一步验证。开发期淘汰复杂模型，选前四周均值，测试MAE72.625人次/周，上一周基线111；部分已见值、四周小样本与发布时延未知均披露。
- 保留原MAG，另建官方运营纠正层：补Jackson/Justa，纠正Cholla延时。Census坐标为派生地址插值；容量500/200仍是明确情景，不把到访下界当容量实测上限。
- 新增有日期GTFS路由：原登记层1152、运营层1224条参考OD；处理24点后时间、乘降、换乘、频率与直接步行，并用独立原始旅程和小例验证。它不是实测行程。
- 将许可、供电、场地、配员窗口接到容量式；共享队伍计任务间重定位且起点事故前固定。修复重复overlay、极端脆弱性、零需求公平值、利用率、转移优先级等反例。
- 给出透明运营费用包络和不预知未来的共享稳健计划，和当前年滚动、完美预知DP分开比较。没有把固定项目合同请求当移动单位采购价。
- 补齐严格推导、最小割证书、状态充分性证明、独立审查及复算指南。共同需求倍率不保证零搬迁收益，已给可复算反例。

## 结果与运行

正式结果：`results/completion_20261121/README.md`、`CLAIM_EVIDENCE.csv`、`model_numbers.json`；源版本、完整输入/输出指纹及命令见`completion_manifest.json`。先冻结源，再重跑，不给旧结果改签版本。

```text
python -m pip install -r requirements.txt
python -m pip install reportlab
python tools/run_completion_release.py --out results/completion_20261121
```

`--pdf-python`只用于两页核心推导说明的文档运行时，不编译论文。单项入口为`run_empirical_validation`、`run_gtfs_validation`、`run_completion_evidence`。统一五问支持`--real-network --city-operations`，也可显式导入`--gtfs-reference-od`；单一出发时刻重复用于各日/时段只是统一结构情景，不能伪装七日时变实测交通。

当前可验证范围见`COMPLETION_CHECKLIST_20261121.md`。周已实现到访检验不识别未到访/拒绝需求、全市覆盖、新MCH容量或健康因果效果。现场OD、真实配员许可与匹配规格报价未公开取得时，保留范围和不确定性，不能编造填齐。

给论文手的接口是`MODELER_HANDOFF_20261121.md`，不是论文正文；个人理解练习见`DEFENSE_GUIDE_20261121.md`，不代签队员掌握或组织规则确认。
