# MODEL_CONTRACT（骨架，待填）

> 本文件是"要建什么"的合同。规则同 A 题：**符号、单位、口径一旦冻结，其他文档不得另写一套。**

## 1. 符号表

| 符号 | 定义 | 单位 | 类型 |
|---|---|---|---|
| $i=1..12$ | 规划区（**模拟**，非官方 village） | — | SCENARIO |
| $j=1..8$ | 候选 MCH 点（**模拟**） | — | SCENARIO |
| $k$ | 既有站点（respite/cooling/hydration/donation） | — | SCENARIO |
| $t=0..6$ | 热浪第 $t+1$ 天 | 天 | SCENARIO |
| $D_{it}$ | 区 $i$ 第 $t$ 天降温需求 | 人次/日 | NEED（由人口×暴露×脆弱性构造） |
| $t_{ij}$ | 区 $i$ 到点 $j$ 行程时间 | 分钟 | NEED（EXT-05） |
| $C$ | 单枢纽容量 | 250 人次/日 | SCENARIO |
| $p$ | 购置枢纽数 | 台 | 决策 |
| $y_j$ | 是否在 $j$ 设点 | 0/1 | 决策 |
| $x_{ijt}$ | 区 $i$ 第 $t$ 天分配给 $j$ 的人次 | 人次 | 决策 |
| $U_{it}$ | 未满足需求 | 人次 | 派生 |

## 2. 不可混用的量（题面点名）

1. `visitor-visits` ≠ 同时在场人数 ≠ 去重人数
2. hydration station ≠ cooling center
3. 记录死亡 ≠ 设施因果效应
4. 模拟 12 区 ≠ 官方 Phoenix designation

## 3. 目标与约束

待定稿。骨架：

- 目标（字典序）：① 最小化 $\sum_{i,t} U_{it}$；② 最小化 Gini(覆盖率)；③ 最小化最差区未满足率
- 约束：$\sum_j y_j \le p$；$\sum_i x_{ijt} \le C y_j$；$x_{ijt} \le D_{it} a_{ij}$；$U_{it}=D_{it}-\sum_j x_{ijt}$

> 公平的两种写法（约束式 / 加权式）都要报，见 `handoff/MODELER_HANDOFF_2026-11-16.md` §3.2。

## 4. 决策记录 D1…

（待填：每定一次口径记一条，日期 + 裁决 + 理由）

## 5. 验收判据

见 `tests/test_smoke.py`：A1 容量、A2 非负、A3 零需求、A4 可复现、覆盖单调性。
