"""Build numeric macros and evidence links from actual frozen output fields."""
from pathlib import Path
import argparse,csv,json,re,hashlib

def load(path):return json.loads(path.read_text(encoding='utf-8'))
def csvrows(path):
    with path.open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))

def build(out:Path):
    base=load(out/'base/core/summary.json');emp=load(out/'empirical/summary.json')
    gtfs=load(out/'gtfs_city/summary.json');tests=(out/'base/tests.log').read_text(encoding='utf-8')
    count=int(re.findall(r'(\d+) passed',tests)[-1])
    selected=emp['selected_model'];mae=emp['test_scores'][selected]['mae_visits_per_week']
    persistent=emp['test_scores']['last_week']['mae_visits_per_week']
    response=load(out/'base/dated_pipeline/summary.json')['q4_disruption']
    stress=load(out/'base/q4/stress.json')
    vehicle={float(r['shock_mult']):r for r in csvrows(out/'base/q4/scenario_table.csv') if r['kind']=='vehicle' and r['down']=='MCH-3'}
    # This is a signed model contrast, deliberately not an empirical route MAE.
    diffs=[float(r['routing_minus_proxy_minutes']) for r in csvrows(out/'gtfs_city/od_by_departure.csv')]
    import statistics
    macros={'EmpiricalTrainN':emp['train_n'],'EmpiricalSelectN':emp['selection_n'],'EmpiricalTestN':emp['test_n'],
            'EmpiricalMAE':f'{mae:.3f}','PersistenceMAE':f'{persistent:.3f}',
            'EmpiricalGainPct':f'{100*(persistent-mae)/persistent:.2f}',
            'TransitODN':gtfs['od_rows'],'TransitMedian':f'{statistics.median(diffs):.3f}',
            'TransitRouteScope':'at most three boardings, a 240-minute transit search, and assumed walking and frequency waits',
            'CoreUnmet':f"{base['p3']['unmet_total_raw']:.3f}",
            'CoreBaseline':f"{base['baseline']['unmet_total_raw']:.3f}",
            'WeekStatic':f"{base['baseline_week_static']:.3f}",'WeekDynamic':f"{base['baseline_week_dynamic']:.3f}",
            'TestsPassed':count}
    macros.update({'QfourDown':response['down_site'],'QfourNoMove':f"{response['no_move']['unmet']:.3f}",
        'QfourBest':f"{response['best']['unmet']:.3f}",'QfourGain':f"{response['response_gain']:.3f}",
        'QfourHours':f"{response['best']['total_hours']:.2f}",'VehicleNoMove':vehicle[1.]['no_move'],
        'VehicleBest':vehicle[1.]['best'],'VehicleGainOne':vehicle[1.]['gain'],
        'VehicleGainMid':vehicle[1.8]['gain'],'VehicleGainHigh':vehicle[3.]['gain'],
        'StressPten':stress['gain_p10'],'StressPmedian':stress['gain_p50'],'StressPninety':stress['gain_p90'],
        'StressPosPct':f"{100*stress['positive_gain_share']:.1f}"})
    (out/'model_numbers.json').write_text(json.dumps(macros,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'number_sources.json').write_text(json.dumps({'macros':macros,
        'source_files':['base/core/summary.json','base/tests.log','empirical/summary.json','gtfs_city/summary.json','gtfs_city/od_by_departure.csv','base/dated_pipeline/summary.json','base/q4/stress.json','base/q4/scenario_table.csv'],
        'sha256':{rel:hashlib.sha256((out/rel).read_bytes()).hexdigest() for rel in ['base/core/summary.json','base/tests.log','empirical/summary.json','gtfs_city/summary.json','gtfs_city/od_by_departure.csv','base/dated_pipeline/summary.json','base/q4/stress.json','base/q4/scenario_table.csv']}},ensure_ascii=False,indent=2),encoding='utf-8')
    ops=csvrows(out/'operations/official_inventory_contrast.csv')
    selected_ops=[r for r in ops if r['p']=='3']
    lines=['# 本轮建模、代码与验证交付','',
        '本包是2026-11-21补全版。先看模型说明、数值结果及证据表，再按manifest命令复算。未把来源重构、数值对拍、排班核验和真实结果检验混成一项。',
        '',f'数值测试：{count}项通过。历史发布样例的结构/账目检查与当前代码的独立最小割、全序列、资源边界测试分别解释。',
        '', '## 这次真正补上了什么',
        '',f'1. 官方同站实际周到访的12/4/4时间划分。只用开发期选出的{selected}，测试MAE{mae:.3f}人次/周；上一周基线{persistent:.3f}，相对差{100*(persistent-mae)/persistent:.2f}%。复杂模型未过选择门槛，已采用简单基线。',
        '2. 23份官方周报/季末报告、NOAA逐日气温及官方运营刊物，保留源错误与来源冲突、原件和指纹；目标直接取weekly列，不从有修订的累计列造真值。',
        '3. 补主要遗漏Jackson/Justa及Cholla延时的显式运营层。地址采用官方刊物，Census街道插值不冒充实测入口，原MAG快照不修改。500/200日容量是兼容已实现工作量的假设情景，不是测得的容量上限。',
        f"4. 原MAG层1152条、修正运营层{gtfs['od_rows']}条GTFS参考OD，独立原始旅程核验；与同层距离代理的差别是结构差，不是实测误差。",
        '5. 许可/供电/场地/配员窗口进入供给式；单共享搬迁队计任务间重定位，初始队伍位置固定于事故前。已修复重复overlay、鲁棒标签、零需求公平值、V截断和日上限利用率等新反例。',
        '6. 用人员小时、工资、能耗、耗材和维护推导费用区间，另比较不预知热路径的共享稳健计划。没有拿固定设施合同总额除站点数充作移动单位价格。',
        '7. 补全严格推导/最小割证明、独立审查、模型交接和可复算证据。数字由同一CSV/JSON生成；按用户要求，论文写作与排版暂停，不改队友原稿。',
        '', '## 同输入运营层对照（p=3，距离/速度代理）',
        '', '| 网络情景 | 缺口人次/代表日 | 选址 |','|---|---|---|']
    for row in selected_ops:lines.append(f"| {row['scenario']} | {float(row['unmet']):.3f} | {row['chosen']} |")
    lines+=['','上述对照只改变明确的运营资料/新增站点假设，原区中心、需求和其他容量仍是条件输入。排班OD另用同一运营层比对，见gtfs_city/matched_inventory_siting.csv。',
        '', '## 验证边界及失败后的动作',
        '', '周到访检验是回顾性逐周一步计算，假定前周记录已可用；实际发布时延未知，检索时见过一个测试周值，不能称完全盲或已证明可提前一周上线。只有四个相关测试周，不制造独立样本置信区间。它验证一个固定站已实现工作量的有限预测目标，不能推成12区潜在需求或新移动站的真实覆盖率。',
        '', 'GTFS核验支持发布时刻、service日期和权限处理；步行接驳、频率等候、实时延误、无障碍及block续乘仍有限域。若主流水线导入参考OD，明确把一个出发时刻重复用于全部规划时段/日期，只能作统一结构情景，不伪装七日时变实测路由。',
        '', '没有匹配本题规格的本地完整移动单位采购报价，不能用检索不到的数据编成实测数。费用和吞吐参数保留范围；不依赖这些缺口的数学结论、数据反证和本次狭义检验已实际完成。',
        '', '三位队员个人理解、签名及本训练具体AI规则的确认无法由程序代办；本包已提供答辩算例与全部复算入口，不把这些人的动作伪写成完成。',
        '', '![真实周到访检验](empirical/empirical_validation.png)',
        '', '图为官方单站周观测与模型预测；训练/选择/测试块、单位和基线在图及CSV中保留。',
        '', '![排班结构对照](gtfs_city/routing_structure.png)',
        '', '图是发布排班加假设步行模型与距离代理的比较，非现场行程误差。']
    (out/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    claims=[
        ['N01','真实同站周到访回顾性检验','empirical/summary.json','test_scores,last_4_weeks_mean;train_n/selection_n/test_n','MAE visits/week','One-step, report availability unverified, one test value previously seen'],
        ['N02','容量与小时假设被真实资料约束','empirical/capacity_reconciliation.csv','train-only at_least_one_day_count_lower_bound','visits on at least one day','Not a constant capacity estimate; no transfer to MCH or all libraries'],
        ['N03','官方运营层改变条件网络','operations/official_inventory_contrast.csv','scenario,p,unmet,chosen','visits/representative day','same demand/proxy; added capacities assumed; published hours not door logs'],
        ['N04','排班语义与路径收支核验','gtfs_city/independent_source_leg_audits.json','ride_checks,full_itinerary_time_residual_seconds','seconds','Published schedule verification, not observed travel'],
        ['N05','交通结构能改变可达与选址','gtfs_city/matched_inventory_siting.csv','access_case,unmet_visits,chosen','visits/day','Same facilities/demand; limited boardings/walking/headway model'],
        ['N06','运营条件直接限制供给','operations/operational_constraint_contrast.csv','scenario,unmet,chosen','visits/day','Missing confirmations remain assumptions, not permits'],
        ['N07','不预知未来的共享稳健计划','operations/nonanticipative_plan_comparison.csv','fixed_robust_plan_unmet_on_path,robust_rectangular_upper_bound','weighted unmet visits','Rectangular annual worst cases; information differs from oracle/rolling'],
        ['N08','模型的数值与数学证书','base/tests.log','passed tests; test_completion_invariants.py','numerical equalities/inequalities','Not empirical citywide validity'],
        ['N09','默认零搬迁收益不能泛化','../../docs/TECHNICAL_DERIVATION_20261121.md','common multiplier counterexample','3.125 visits in synthetic counterexample','Fixed supply need not scale with demand'],
    ]
    with (out/'CLAIM_EVIDENCE.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['claim','statement','result_file','fields','unit','scope']);writer.writerows(claims)
    return macros

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);args=parser.parse_args()
    print(json.dumps(build(Path(args.out)),ensure_ascii=False,indent=2))
