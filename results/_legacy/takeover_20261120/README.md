# 2026-11-20 冻结建模包

先读 [结果及解释](RESULTS.md)、[结论证据表](CLAIM_EVIDENCE.csv)、[建模交付说明](../../docs/TAKEOVER_2026-11-20.md) 和 [验收状态](../../docs/TAKEOVER_CHECKLIST.md)。

- 数值源版本：`d070f5d3a90929836d210f4e6002c9dbc00a8449`。
- 94项测试通过，7项旧结果依赖测试跳过；原因见 `tests.log`。
- 各实验均记录该源提交、`worktree_dirty=false`、完整源/输入SHA256、参数及运行环境。
- `release_manifest.json`记录运行命令及结果文件指纹；它不包含自身哈希。
- `model_chain.pdf`为已渲染检查的两页推导，不是最终英文比赛论文。
- 这些是条件资源配置结果；缺乏独立服务响应留出、真实OD、逐站容量及采购/运营报价验证，不能据此承诺实际覆盖率或签采购方案。

复算：切换到上述源提交后安装 `requirements.txt`，文档另需 `reportlab`、`pypdf`，运行：

```text
python tools/run_takeover_release.py --out results/reproduce_takeover
```

如文档库在独立Python中，可指定 `--pdf-python`；实际本轮调用的路径与各命令在manifest中保留。只重算数值也可按仓库README逐项运行。

目录：`core`含Q1/Q2、27行OAT、时段消融、逐格分配和图；`q3`含七日调度；`q4`含故障、100次逐样本配对与时间线；`q5`含九情景DP/滚动/现有资产比较和成本扫描；`pipeline/dated_pipeline`分别是合成基础输入与MAG登记日历情景下的统一五问流水线；`data_validation`只做真实输入来源重构。
