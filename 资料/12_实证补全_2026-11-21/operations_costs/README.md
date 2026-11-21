# 运营与费用的可核验边界

检索日期2026-11-21。本目录原始文件和HTTP状态见manifest.json；失败下载不伪装成成功。

1. Industrial Commission of Arizona，2025-09-29《New 2026 Minimum Wage—Effective January1,2026》p1，说明2026名义小时最低工资15.15美元。原始PDF经网页工具读到，直接HTTP下载403，记录为未保存；稳定来源：https://www.azica.gov/sites/default/files/2025-10/2026%20Minimum%20Wage.pdf 。[美国劳工部表](https://www.dol.gov/agencies/whd/mw-consolidated)提供独立机构交叉核验。仅作2026历史工资下界，不表示2027—2031法律水平、MCH岗位工资或已签合同。
2. City of Phoenix，City Council Policy Session，2026-02-24，File26-0336、OrdinanceS-52629提案。请求CBI项目合同最高260万美元、Justa最高13万美元，另有QVL授权增额；网页显示请求/议程，不把它叫实际支出或已执行采购。支持性服务、固定中心和移动单位范围不同，不能用总额除中心数得到MCH单价。原文HTML已保存；URL见manifest。
3. City of Phoenix，2026计划公告和两份城市刊物支持Jackson/Justa的地址与开放项目。Census Geocoder将20WJackson、1001WJefferson均匹配唯一地址，JSON保留原答复；坐标是派生街道地址插值，不是实测入口。公开网页有Justa街道名冲突，按两份正式城市刊物和计划采用Jefferson，保留冲突记录。

本轮没有找到与题设250访问人次/日MCH规格完全匹配、且包含本地安装/电力/人员的单位采购报价。因此购置成本仍是显式情景；没有把异地案例或固定设施合同升级成本地MCH实测价。

新增`annual_operating_envelope`以人员小时×名义工资×用工附加系数，加能源、耗材和维护构成可复算费用。所有岗位人数、热季天数、工资选择、能耗/电价、耗材与维护均标ASSUME并扫描；工资历史下界只作合理性检查。连续开放需实际轮班，两个同时在岗不表示由同两个人全年工作。储存费和报废仍未校准；默认零值只用于条件比较。
