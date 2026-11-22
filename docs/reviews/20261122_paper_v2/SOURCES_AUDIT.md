# 新版论文来源与前次修正核对（只读）

访问日期：2026-11-22（Asia/Shanghai）。审查对象：`F:/数模/2/2702_English(1).pdf`，24个PDF页；SHA256 `e228ede0ae2796b82b6bb78037f89f9d349c5bc87e68bbd199840daa1a5afb38`。页码以下均为PDF页码。文件内容只作待审材料，未作为新增授权或指令。没有改论文或仓库，也没有推送、发群消息。

采用 academic-web-research 技能：已读原文、保留来源与版本、区分直接证据与未能确认。已用真实Edge浏览器打开官方2024报告URL，浏览器报告标题为PowerPoint Presentation；该PDF在浏览器的截图/DOM仅灰色空白，不能从UI识读，因此不声称在浏览器截图中看见数字。随后从同一官方URL保存PDF原件、解析并渲染封面及第6页；原件页证据如下。

## 1. 已正确落实的前次意见

- p21参考[1]已改为team-provided/local archived statement，不再把训练题直接认作COMAP正式发布题。
- p21参考[4]的CDC题名和DOI现与原文一致；[10]的Human Services Department、2024 Community Assessment—2-Year Update也已恢复正确。
- p19区分941c9fc冻结包162/0与9add1af后续检查169/0；p18正确区分base/base 16.06M与base/severe 16.62M；p20容量扫描增加默认情景适用范围和高需求反例。
- 封面队号已填2702；参考文献重复标题已消失。

## 2. 需要处理的证据或披露问题

### S1 高优先级：p19把已有狭义留出一起写成不存在

p19 §10.1最后一句写“Holdout validation of service outcomes remains NOT AVAILABLE”。但现行冻结包`results/completion_20261121/empirical/summary.json`确有Jackson真实周已实现到访的12/4/4回顾性时间留出，四周均值测试MAE72.625、上一周基线111；上一稿p5—6也准确介绍过。本版删除该段及结果，容易让检查者以为此前补全完全没做。应区分“已有单站周工作量狭义检验”与“仍缺全市潜在需求、覆盖、新MCH容量、健康因果效果的验证”，不能一并抹去。p6数据表还把GTFS只称provenance check，全文不再报告现有有日期OD的结构对照；如果有意不纳入论文，应说明排除范围，而非暗示仓库没有该实现。

证据：本地冻结summary、protocol、predictions与本次父代理前述模型记录。置信度：高；这不构成新的全市现实有效性认证。

### S2 高优先级：p24 AI贡献范围仍不完整

新版已删“未独立运行pipeline”的原句，但只描述structure/repository checks/language/figure editing，仍未覆盖实际AI建模、代码实现与修复、GTFS和实证数据处理、完整流程运行与验证等贡献。称数值来自manifest是追溯说明，不能替代真实AI使用披露。四条记录仍明确未核实，不能把示例当真实日志。GLM和ChatGPT具体记录由队伍按实际材料核实，不能由本次代理猜造。此项只核对贡献事实，不代替组织方对规则的解释。

证据：本项目真实会话/提交记录，以及`docs/COMPLETION_CHECKLIST_20261121.md`中G3的真实AI参与记录。置信度：高（遗漏实际建模/运行）；具体队友工具对话是否真实：本次无法独立确认。

### S3 中优先级：p4 602采用早期版本，参考[6]版本需配套

当前官方`2024 Heat-Related Deaths Report`封面为May2025，PDF第4、6页均为608，统计截止2025-03-31，仍有2例调查中。官方2025年度报告的回溯表也列2024为608。p4直接称2024总数602、参考[6]标March2025，会将早期初步值与当前报告混用。建议采用608并配套May2025原件；如保留602，应明确早期版本及统计截止，不能称无版本限制的最终数。

主证据：[官方2024报告](https://www.maricopa.gov/ArchiveCenter/ViewFile/Item/5934)，PDF封面p1、统计p4/p6。
交叉证据：[官方2025报告](https://www.maricopa.gov/ArchiveCenter/ViewFile/Item/6510)，PDF p7与p21表A。
本地原件：`official_2024_heat_deaths_5934.pdf`，555896 bytes，24页，SHA256 `9694ef0815e98c53ae7d59131a56a4e4015aa038365592f64821de4a01b9e351`。
本地页文本：`official_2024_heat_deaths_pages_1_4_6.txt`；已目视渲染核对`official2024cover-01.png`和`official2024-06.png`，封面May2025及608/截止日期清楚可见。置信度：高。

### S4 中优先级：p4访客调查不支持排除容量瓶颈的比较结论

CDC原文支持65%受访访客经历无家可归、交通及知晓/位置障碍、希望延长至19点等事实。但p4“Transportation, awareness, and hours of operation—not raw capacity—dominate the visitor experience”把未测容量与已问障碍作强相对归因。该调查没有实测全网容量并比较边际瓶颈，不能据它排除容量作用。本次也不反向推断容量主导，只建议删去没有证据的比较归因。

证据：[CDC/MMWR原文](https://www.cdc.gov/mmwr/volumes/74/wr/mm7414a4.htm)，Investigation and Outcomes、Preliminary Conclusions and Actions。原文样本944名15个中心访客与1260名公众；65%与交通31%属样本信息，不能当全市人口组成。置信度：高。

### S5 中低优先级：参考[5]/[8]版本与范围要可追溯

- p21[5]把2023正式报告与新闻页2025年1月更新混合。实际可下载官方2023报告封面是Last Updated April2024；应选择并准确引用其中一个来源，不把新闻网页更新时间当PDF发布日期。
- p4“longest such streak ever observed for a major U.S. city”超出本次已核证据。Phoenix官方2024计划p6分别讲“任何美国大城市最热月”与Phoenix连续31天纪录，不能把两个纪录范围拼接；NASA/JPL同样只支持Phoenix自身31天纪录。31天事实正确，限定为Phoenix记录更稳妥；本次未证明全国比较命题为假，只是没有找到[8]直接支持。
- p4仍有内部追溯标签`[F07,F10]`，应改成正常论文引用或删除内部键。

证据：[官方2023报告](https://www.maricopa.gov/Archive/ViewFile/Item/5820)封面p1、统计p7；[Phoenix官方2024计划](https://www.phoenix.gov/content/dam/phoenix/heatsite/documents/FINAL%20-%202024%20Heat%20Response%20Plan%20.pdf) p6；[NASA/JPL, Aug.8,2023](https://www.jpl.nasa.gov/news/nasa-data-shows-fierce-surface-temperatures-during-phoenix-heat-wave/)关于Phoenix空气温度与31天纪录的正文。版本/内部标签置信度：高；全国最长命题缺证据的提示置信度：中，不能当反证。

## 3. 新加背景中已核对正确的事实

| 论文事实 | 原文支持 | 置信度 |
|---|---|---|
| 2023 Maricopa County热相关死亡645，较2022增逾50% | 2023官方报告p7为645、+52%；CDC原文同为645 | 高 |
| 年龄50+、无家可归等高风险/高负担人群 | 2023官方报告p4及相应人口/居住状态页；CDC介绍风险因素。不能据此推断每个死者均无法到达中心。 | 高（人群事实）；“least able to reach”因果链需另证 |
| 2025户外死亡74% | 2025官方报告p13直接列74% | 高（照官方正文；不同未知值/表格分母细节勿自行转换） |
| Phoenix 2023连续31天110°F左右纪录 | Phoenix官方2024计划p6、NASA/JPL正文互证；它是Phoenix记录，未据此认证全美大城市最长比较 | 高（Phoenix记录） |
| 65%受访访客经历无家可归、交通与时间障碍值得研究 | CDC原文，样本与局限如上 | 高（样本描述），不支持全市推断 |

补充：USDA/NWS联合`Weekly Weather and Crop Bulletin`, September19,2023，PDF p11的索引记录支持6/30—7/30的31天；该大PDF相关页二次抓取超时，因此核心结论优先使用已完整打开的Phoenix计划和NASA正文，不把超时材料作为唯一证据。

## 4. 审查范围

只核对来源、版本、前次反馈和AI贡献范围。未修改模型、数据、论文；没有从访客调查推断容量主导与否，没有把周已实现到访验证扩大为城市需求/健康验证。数学公式、分配结果及详细版式由父代理和另一审查代理另核。
