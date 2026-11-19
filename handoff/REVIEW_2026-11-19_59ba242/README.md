# 第六轮审查与复现证据

日期2026-11-19；审查版本`59ba2421ce3d1d1affc59b366d202c7526588585`。

先读[综合审查](第六轮建模审查.md)，论文手可参考[假设卡修订草案](假设卡修订草案.md)。本包保留已修状态，并提供当前剩余问题的具体反例。模型源码和已有结果未修改。

本轮49项测试通过；主pipeline与独立Q5运行正常，独立Q5默认结果可复现。**独立Q4默认CLI因best=no_move缺timeline崩溃**，应优先处理。留驻车辆计时、匹配/任务顺序、Q5行动组合及新假设卡保证也需修订。

## 一键核验

在仓库根目录、使用仓库NumPy/SciPy环境运行：

```powershell
python 'handoff/REVIEW_2026-11-19_59ba242/证据/Q4/probe_q4.py' --repo . --out tmp/review6_q4
python 'handoff/REVIEW_2026-11-19_59ba242/证据/Q5/probe_q5.py' --repo . --out tmp/review6_q5
python 'handoff/REVIEW_2026-11-19_59ba242/证据/文档/probe_docs.py' --repo . --out tmp/review6_docs
```

脚本只在内存或指定独立目录复现，不改源文件。边界夹具用于算法验收，不是Phoenix实测。修复后“旧问题仍存在”的断言应相应失败，再改成正确性验收；不得为了通过旧复现脚本恢复bug。

`证据/`含Q4、Q5、文档专项详报与JSON；`验证记录.json`含环境和执行结果；`SHA256_MANIFEST.json`校验本包。所用原始资料和文献仍在前次交付目录，本轮没有重复下载或另造参数。
