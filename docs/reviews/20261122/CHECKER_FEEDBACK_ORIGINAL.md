# 修正建议文档（检查者反馈）

- 被审版本：`6f13bc27801589c5bb646512847fbaa4c2498ff5`（2026-11-21）
- 检查日期：2026-11-21
- 检查方式：**独立重建该提交的完整工作树后复跑**，不读取作者结论作为证据
- 检查者角色：仅检查与反馈，不修改模型代码

---

## 0. 总体判定

**建模与代码内容：可以接受。**
真实时间留出、两条 GTFS 路由、许可/供电/配员约束、共享搬迁队、成本区间与稳健预算都已落地，
边界陈述诚实（"单站工作量，不能证明全市需求/覆盖"）。162 项测试与关键数值我都能复现。

**交付卫生：尚不可接受。**
旧结果仍在仓库中与权威批次并列、表头数字过时、关键表格列义歧义。
这三项不会让模型变错，但会让**复核人和论文手拿到错数字**，是当前最容易造成实际损失的问题。

**建议：先做 §2 的三项，再进入论文与答辩阶段。**

---

## 1. 我已独立验证通过的（不建议再改）

| # | 声明 | 我的验证 | 结果 |
|---|---|---|---|
| V1 | 162 项测试通过 | 重建工作树后 `python -m pytest tests -q` | **162 passed**（复现时需数据完整、已装 `pypdf`） |
| V2 | 周到访检验 MAE 72.625 | `python -m src.exp.run_empirical_validation` | `last_4_weeks_mean` 测试 MAE **72.625**，上一周基线 **111.000** |
| V3 | 复杂模型未过开发门槛 | 读 `empirical/summary.json` | 开发期 AR1 系 172.2 / 基线 78.4，按"至少改善 5%"规则淘汰 |
| V4 | 未偷用测试周信息 | 读 `protocol.forecast_information` | 仅用上一周观测与气温；并**主动披露**检索阶段已见过 9/14–20 数值 |
| V5 | 源表内部矛盾未被"修好" | `quality_flags.source_table_arithmetic_inconsistencies` | 保留 11 与 27 两处差异，未篡改官方数据 |

**额外实测（对你们有利，建议写进 RESULTS）**：

| 固定站容量（人次/日） | p=0 缺口 |
|---|---|
| 50 | 307.6 |
| 120 / 250 / 472 / 500 | **305.5（几乎不变）** |

> 把固定站容量放大到 10 倍，缺口只动 **2.1 人次**。
> 这能直接回应"50/日是不是拍脑袋容量"的质疑：**缺口由可达性驱动，不由容量驱动**。

---

## 2. 必须修正（P1–P3）

### P1 旧结果与权威批次并列，且存在数字冲突 ⚠️ 最优先

**位置**：`results/`（当前 **30 个目录**）

**现象**：

- 权威批次是 `results/completion_20261121/` 与 `results/takeover_20261120/`；
- 其余 **12 个目录**仍带旧 `run_meta.json`：
  `levers`、`q2_attribution`、`q2_objectives`、`q3_week`、`q4_response`、`q5_plan`、`real_network`、`run_csv`、`segments`、`sweep` → `99add35`；
  `sweep_levers` → `46a0d7f`；`sweep_transit` → `2d74f7a`（且 `dirty=true`）；
- `results/` 下**没有 README** 说明哪一批可引用。

**具体冲突（可直接验证）**：

| 指标 | 旧 `results/q5_plan/` | 新 `completion_20261121` |
|---|---|---|
| 五年花费 | **$15.90M** | **$16.62M** |
| 车队口径 | `fleet`（在役=库存） | `owned/active/buy/retire/idled` |
| `note` 字段 | **乱码**（`鎴愭湰涓?ASSUME`） | 正常 |

**影响**：论文手或队友按目录名取数时，会引到**已被推翻的口径**，且无法从文件本身看出它过时。

**建议改法（任一）**：
1. 旧目录整体移入 `results/_legacy/`，并在 `results/README.md` 写明"仅 `completion_20261121/` 可引用"；
2. 或删除旧目录（结果可由脚本重跑，历史价值低于误引风险）。

**验收标准**：
- [ ] `results/README.md` 存在，且只指向 `completion_20261121/`；
- [ ] `ls results/*/run_meta.json | grep -v completion_20261121` 为空（或全部位于 `_legacy/`）；
- [ ] 抽查 `results/q5_plan/plan.csv` 已不再可被误取。

---

### P2 `takeover_20261120/RESULTS.md` 表头数字过时

**位置**：`results/takeover_20261120/RESULTS.md` **第 5 行**

**现象**：写的是

```
数值验收：**94 passed, 7 skipped, 1 warning in 7.86s**
```

**当前实际**：`162 passed`（0 skipped）。旧的 7 条"旧结果依赖"测试现在会运行并通过。

**影响**：复核人看到"7 skipped"会怀疑有测试被长期跳过；与环境实际不符。

**建议改法**：改为可区分批次的两段，例如

```
冻结批次（d070f5d）记录：94 passed, 7 skipped。
当前 HEAD（6f13bc2）复核：162 passed, 0 skipped。
```

**验收标准**：
- [ ] 文件中不再出现与当前 HEAD 矛盾的测试计数；
- [ ] 若保留历史数字，必须显式标注"该数字属于冻结批次，不是当前 HEAD"。

---

### P3 Q1 表的列义歧义（容易被误读）

**位置**：`results/takeover_20261120/RESULTS.md` L13（表头）、L17（p=2 行）

```
| p | 效率缺口 | max-min缺口 | 全区最差率(max-min) | 非豁免最差率 | 新增1辆的边际人次 |
| 2 |  248.547 |   262.520   |        1.000        |    0.575     |      21.739      |
```

**问题**：`0.575` 是 **max-min 解**的非豁免最差率；**效率解的非豁免最差率是 1.000**（我实测确认）。
两列紧邻"效率缺口"，读者极易把 0.575 当成效率解的性能。（我在上一轮就误读过一次。）

**建议改法（任一）**：
1. 拆成两组列：`效率解：缺口 / 全区最差 / 非豁免最差` 与 `max-min解：缺口 / 全区最差 / 非豁免最差`；
2. 或把列名写成 `max-min解·全区最差率`、`max-min解·非豁免最差率`，并补一列 `效率解·非豁免最差率`。

**验收标准**：
- [ ] p=2 行能一眼看出效率解最差率 = 1.000、max-min 解 = 0.575；
- [ ] 效率解与 max-min 解的指标不再共享未限定的列名。

---

## 3. 建议修正（P4–P5，非阻塞）

### P4 实证测试的失败模式不友好

**位置**：`tests/test_empirical_validation.py`

**现象**：依赖 23 份 PDF 与 `pypdf`。缺任一项时是**硬失败**（`ModuleNotFoundError` / `EOF marker not found`），
看起来像代码坏了。我在复现时就因此误报过 8 个失败。

**建议**：加 `skipUnless` 并在 skip 理由里写清"缺少 pypdf 或周报 PDF 不完整"，例如：

```python
@unittest.skipUnless(PYPdf_OK and all_pdfs_present, "需要 pypdf 与 23 份完整周报 PDF")
```

**验收标准**：干净环境下没有 PDF 时，该测试显示为 **skipped 且带原因**，而不是 failed。

### P5 主结果没有引用"容量自证伪"这一节

**位置**：`results/completion_20261121/README.md` 与 `docs/EMPIRICAL_VALIDATION_20261121.md`

**现象**：`capacity_assumption_falsification`（Jackson 某周 3,304 人次 → 至少某天 ≥472）写得很到位，
但主结果段落没有指向它。这是本轮**最有力的自我检验**，容易被漏读。

**建议**：在 RESULTS 的 Q1 附近加一行指针，并配一句"容量 120–500 的扫描显示缺口几乎不变（我实测 305.5→305.5）"。

---

## 4. 澄清：以下问题**不是**你们的缺陷

我在复现过程中先报出过 8 个测试失败与 `EOF marker not found`，事后定位为**我这边的环境问题**：

1. GitHub pack 传输截断 → 我先用稀疏克隆，缺 `资料/`；
2. 压缩包下载不完整 → tar 截断在 GTFS zip；
3. 中文路径在 Windows tar 下乱码 → 需 Python `tarfile` 解包；
4. 未装 `pypdf`；
5. 我下载的 PDF 有 2 份被截断（超大 PDF 超时）。

数据补齐后：**162 passed，一次全绿**。请在复核记录中不要把这当作你们的回归。

---

## 5. 复现方法（我用的）

```powershell
# 1) 取该提交（pack 不稳时用 tarball）
curl -L -o rev.tgz https://codeload.github.com/KN-1998/mcm2027-b-phoenix-cooling/tar.gz/6f13bc2
# 2) 用 Python tarfile 解包（避免 Windows tar 中文乱码）
python -c "import tarfile;tarfile.open('rev.tgz').extractall('rev')"
# 3) 依赖
python -m pip install -r requirements.txt
# 4) 测试与关键流程
python -m pytest tests -q
python -m src.exp.run_empirical_validation --out tmp/emp
```

我保留了一份完整可运行副本（`D:\_rev_cmp`），需要复核任何一项可直接在其上验。

---

## 6. 优先级与验收汇总

| 优先级 | 项 | 验收 |
|---|---|---|
| **P1** | 旧结果隔离 + `results/README.md` | 旧 `run_meta` 不再与权威批次并列 |
| **P2** | RESULTS 表头测试计数 | 不再与当前 HEAD 矛盾 |
| **P3** | Q1 表列义 | p=2 行两解指标可区分 |
| P4 | 实证测试 skip 化 | 缺 PDF/pypdf 时 skipped 而非 failed |
| P5 | 主结果引用容量自证伪 + 容量扫描 | RESULTS 中有指针与一行扫描结论 |

**完成 P1–P3 后，本交付即可进入论文与答辩阶段；P4–P5 可与论文并行。**
