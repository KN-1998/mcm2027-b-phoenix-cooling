# 2027 MCM Problem B — Keeping Phoenix Cool

> 新赛题工作区（2026-11-16 起）。上个赛题（A：Where Does the Sand Go?）已完整归档：
> `D:\MCM2027A_archive_20261116.zip`（231 MB / 1140 文件，SHA256 `b9ca1463…1539c1`）。
> 本目录**只含 B 题内容**，外加 `PRACTICE_NOTES/` 里从 A 题提炼的经验。

## 题目

**Can Mobile Cooling Hubs Make Heat Relief More Equitable and Resilient?**
Phoenix, AZ。2027–2031 年移动降温枢纽（MCH）规划。测试规模：12 个规划区、8 个候选点、单枢纽 ≤250 visitor-visits/日。

题面原文：`problem/2027_MCM_B_Keeping_Phoenix_Cool.pdf`

## 五问

1. **找缺口**：表征各区热暴露、降温需求、到现有设施的可达性（类型/开放时间/行程时间/脆弱人群）；给出可解释的"未满足降温需求"度量，说明哪些可标定、哪些是假设。
2. **设计公平网络**：几个枢纽、放哪、需求如何分配；平衡预算、可达性、容量、利用率、公平；检验"提高平均可达性是否把高需求区落下"；判断边际收益何时消失。
3. **应对 7 天热浪**：连续 7 天、需求逐日变化；给出部署与搬迁时刻表（含搭建、行程、运营时长、人力、服务中断）；固定 vs 动态同口径比较；判断何时搬迁值得。
4. **应对中断与不确定性**：一个主要固定中心因断电停用、两个低收入区需求骤升；**24 小时内重新分配**；测试设备故障、道路/公交中断、需求预测误差；权衡效率-公平-可靠性。
5. **五年策略**：2027–2031 分阶段投资与运营计划；如何随预算/热浪强度/社区需求调整；给出**触发修订的信号**；区分稳健结论与敏感结论。

## 提交要求

- ≤25 页英文报告（含 1 页摘要 + 1 页给 Phoenix City Council 的信）
- 数据说明、模型定义、数值比较、验证/合理性检查、不确定性分析、可执行建议

## 题面点名的四个"不可混"

1. hydration station ≠ cooling center
2. visitor-visits/day ≠ 同时在场人数 ≠ 独立服务人数
3. 记录的 heat-related deaths ≠ 某设施的因果效应
4. 模拟的区/候选点 ≠ 官方 Phoenix 规划 designation

## 先读这两份

- **`资料/00_数据主表.md`** —— 所有数据源、本地文件、访问状态、用途与边界（已下载 4 份官方 PDF）
- **`handoff/MODELER_HANDOFF_2026-11-16.md`** —— 建模交接：五问映射、四条不可混、模型骨架、给编程手的第一批任务

## 目录

```
资料/             数据主表 + 官方计划/健康/文献（含队友交接参考）
problem/          题面 PDF
PRACTICE_NOTES/   A 题经验（教训/合同模板/合规/验证）+ AI 政策 + 参考论文
modeling/         模型合同（待写：MODEL_SPEC / DECISIONS / params）
handoff/          编程合同（待写：CODER_SPEC）
src/ tests/ tools/ 代码
results/ figures/ 结果与图
configs/ data/    配置与数据
meta/             规划、评审记录
```

## 第一步（建议）

1. 读题 → 写 `modeling/MODEL_SPEC.md` 骨架（符号表 + 四个不可混 + 未满足需求定义）；
2. **同时**写 `tests/` 里的第一条断言（零需求 ⇒ 零部署），别等模型完美；
3. 收集数据源（MAG Heat Relief Network、Maricopa 县热病监测、公交/行程时间、区级人口与收入）。
