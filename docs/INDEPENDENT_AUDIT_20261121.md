# 2026-11-21 独立数学与稿件审查

审查者：AI数学审查子代理；原实现主代理负责修复。对象为最新远程bdb74e8（其前两个提交只新增中文工作稿与输入重构）、当前M1—M6及Q2—Q5实现。本文不代表人类队员已复核。按用户最新范围，2702.tex保持远程bdb74e8原稿；涉及论文的内容改为交接建议，不提交论文改写。

## 本轮发现及动作

| 发现 | 原位置 | 影响 | 本轮处置 |
|---|---|---|---|
| 共同需求倍率被写成零搬迁收益的一般条件 | 2702.tex原摘要第69行、Q3第304行、议会信第434行 | 有限固定供给可改变剩余缺口排序，推论不成立 | 已交正文修正建议；增加两区同倍率反例（收益3.125）及独立测试 |
| 代理交通式漏60分钟/小时转换，且公交未写直步行备选 | 原稿第215行 | 公式量纲与实际代码不符 | 正确分钟式已列技术说明，建议区分MAG代理与历史processed公交站代理 |
| 正文只列时段容量，遗漏MCH每日250日总约束；选点≤p与代码恰好p未对齐 | 原稿第216—225行 | 特殊跨日/松时段上界下读者无法还原实际模型 | 建模说明已补日总上限、恰好p及空闲容量说明 |
| 公平仅报告指标，未推导不可行后真正max-min | 原稿第225行后 | 读者无法判断回退是否真公平优化 | 建模说明已补epsilon约束、两阶段z模型、容差及豁免边界 |
| 运行需求脆弱性函数未截断两个比率，但生成脚本/论文均截断 | mch.demand.vulnerability | 合法极端输入V=2，违反0—1并改变重建需求 | 已报主代理，主代理修复；本子代理测试合法极端V=1 |
| 零需求max-min返回t=1 | assign.solve_assignment_periods无变量分支 | 退化公平最优值语义错误 | 主代理修复，测试t=0 |
| MCH时段松上界合计400、实际日约束250时，利用率仍除400 | static._assign利用率分母 | 满负荷250被错报利用率.625 | 主代理修复，独立测试分母250/利用率1 |
| period override非有限未明确拒绝 | _assign容量覆盖 | NaN可被过滤/无穷可破坏模型输入 | 主代理修复，测试NaN/Inf/负值拒绝 |
| Gettel论文题名误写，HSD机构/报告题名误写 | 原参考文献第398、404行 | 来源可追溯性错误 | 按CDC原文与Phoenix报告封面列正确题录，供论文手更正 |
| 本地训练PDF被题录归为COMAP已发布2027正式题 | 原参考文献第389行 | 未经核实的来源权威归属 | 建议题录改为用户提供本地训练题，不认定正式发布 |

在本子代理专用文件tests/test_completion_invariants.py中17项通过，含8组period LP对全部割直接枚举的证书对照、共同倍率反例、epsilon与max-min、豁免、零需求、V截断、日上限利用率及非法覆盖。用的是约束对拍，不是现场有效性检验。最终测试统计以主代理冻结后整体运行记录为准。

## 引用核读与范围（访问2026-11-21）

1. **Gettel et al.（2025）**. *Notes from the Field: Assessment of Awareness, Use, and Access Barriers to Cooling Centers in Maricopa County, Arizona—August 1–September 15, 2023*. MMWR74(14),252—255. DOI10.15585/mmwr.mm7414a4。[CDC原文](https://www.cdc.gov/mmwr/volumes/74/wr/mm7414a4.htm)核对标题、作者、年份、页码及原文样本/定义。它是2023访客与公众调查，不能验证2025/2026全市逐日服务，也不支持把人次换算成减少死亡。
2. **City of Phoenix Human Services Department；Burns & Associates / Health Management Associates（2024）**. *2024 Community Assessment—2-Year Update*, March22,2024。[官方62页PDF](https://www.phoenix.gov/content/dam/phoenix/humanservicessite/documents/hsd-/2024%20hsd%20community%20assessment%20report%20year%202%20update%20and%20appendices%20-%20final.pdf)核对封面、作者页、目录，及已存原件PDF34/37页人口/收入脚注；不是Housing and Community Development Department的“Neighborhood and Demographic Profile”。原件已在既有补充资料中，未重复计为独立样本。
3. **Church, R.; ReVelle, C.（1974）**. *The Maximal Covering Location Problem*. Papers of the Regional Science Association32(1),101—118. DOI10.1111/j.1435-5597.1974.tb00902.x。[出版社题录](https://onlinelibrary.wiley.com/doi/pdf/10.1111/j.1435-5597.1974.tb00902.x)、[作者学术网页存放原文](https://people.geog.ucsb.edu/~forest/G294download/MAX_COVER_RLC_CSR.pdf)。核读原文103—105页的定义、式(1)—(8)、固定设施数与距离覆盖目标；未把原文二元覆盖式当作本题容量/时段LP的完整出处。正文只引用问题家族与本题改造，证明由技术附录自给。
4. **Daskin, M.S.（2013）**. *Network and Discrete Location: Models, Algorithms, and Applications*,2nded.,Wiley,ISBN9781118536964。[出版社题录](https://www.wiley.com/en-sg/network-and-discrete-location-models-algorithms-and-applications-2nd-edition-p-9781118536964)、[官方第1章样章](https://catalogimages.wiley.com/images/db/pdf/9780470905364.excerpt.pdf)。实际核读样章1—5页及章节结构，未阅读全文；只作为选址决策/目标范围背景，不虚配后续公式页码。
5. **Bellman, R.（1957）**. *Dynamic Programming*,PrincetonUniversityPress。已核对[出版社现行重印本题录](https://press.princeton.edu/books/ebook/9781400835386/dynamic-programming-pdf)及[2010版StuartDreyfus导言](https://assets.press.princeton.edu/chapters/i9234.pdf)前两页；不是已阅读全文1957原版。原文完整取得状态不得填写“已全文阅读”。本题Bellman式由状态、行动和归纳证明建立，不能仅凭参考书名成立。

没有绕过付费墙或登录限制；本轮不把有版权的整部教材全文复制进公开仓库。直接来源URL、正确题录与实际核读范围足以供队员复查；需要全文时由来源合法访问。

## 本轮证明和数据验证的分界

新增min-cut证书、端点测试和归纳推导只证明给定离散模型的实现及最优范围。新的真实周访客留出检验由实证模块负责：若预测目标为某些固定中心已实现访问量，即使验证通过，也不识别12区潜在需求、MCH真实容量或全市真实覆盖。新的GTFS模块验证排班路径与处理语义，不把计划时刻验证当作现场延误验证。上述边界不会因英文稿、图件和参考文献补齐而自动消失。
