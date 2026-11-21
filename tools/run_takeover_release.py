"""Run and fingerprint the frozen modeler release; never rewrites old run metadata.

Usage: python tools/run_takeover_release.py --out results/takeover_20261120
Install reportlab+pypdf, or pass --pdf-python for a separate document runtime.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.mch import runmeta


def read_json(path):return json.loads(path.read_text(encoding='utf-8'))
def read_csv(path):
    with path.open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='results/takeover_20261120')
    parser.add_argument('--pdf-python',default=sys.executable)
    args=parser.parse_args();out=ROOT/args.out;out.mkdir(parents=True,exist_ok=True)
    if runmeta.meta({})['worktree_dirty']:
        raise RuntimeError('Commit source/tests/tools/inputs first. No dirty-source release is permitted.')
    code_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    jobs=[('tests',[sys.executable,'-m','pytest','tests','-q','-rs']),
          ('data_validation',[sys.executable,'tools/validate_takeover_data.py','--out',str(out/'data_validation')]),
          ('core',[sys.executable,'-m','src.exp.run_takeover_evidence','--out',str(out/'core')]),
          ('q3',[sys.executable,'-m','src.exp.run_q3_week','--p','3','--out',str(out/'q3')]),
          ('q4',[sys.executable,'-m','src.exp.run_q4_response','--stress-draws','100','--out',str(out/'q4')]),
          ('q5',[sys.executable,'-m','src.exp.run_q5_plan','--cost-scales','0.5,0.75,1,1.25,1.5,2,3,5,10','--out',str(out/'q5')]),
          ('pipeline',[sys.executable,'-m','src.exp.run_pipeline','--p','3','--out',str(out/'pipeline')]),
          ('dated_pipeline',[sys.executable,'-m','src.exp.run_pipeline','--p','3','--real-network',
                              '--access-mode','transit_min','--out',str(out/'dated_pipeline')]),
          ('model_chain',[args.pdf_python,'tools/render_model_chain.py','--out',str(out/'model_chain.pdf')])]
    records=[]
    env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1'}
    for name,command in jobs:
        print('RUN '+name,flush=True)
        start=datetime.now(timezone.utc).isoformat()
        result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
        (out/(name+'.log')).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        records.append({'name':name,'command':command,'started_utc':start,'exit_code':result.returncode})
        if result.returncode:raise RuntimeError(name+' failed; see log')
        print('PASS '+name,flush=True)
    # Every experiment must name the actual frozen source, not a parent or a
    # later result commit. Fingerprints also detect mutations during the run.
    metas=[]
    for path in out.rglob('run_meta.json'):
        payload=read_json(path)
        if payload['git_sha']!=code_sha or payload['worktree_dirty']:
            raise RuntimeError('non-frozen experiment: '+str(path))
        for rel,sha in payload['source_sha256'].items():
            if hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()!=sha:
                raise RuntimeError('source changed during release: '+rel)
        for rel,sha in payload['inputs'].items():
            if hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()!=sha:
                raise RuntimeError('input changed during release: '+rel)
        metas.append(path.relative_to(ROOT).as_posix())
    make_report(out,code_sha)
    inputs=runmeta.meta(vars(args))
    manifest={'generated_at_utc':datetime.now(timezone.utc).isoformat(),
              'source_commit':code_sha,'source_and_inputs':inputs,'runs':records,'experiment_metadata':metas,
              'scope':'Frozen conditional modeling release; empirical service validation and human team sign-off pending',
              'pdf_authoring_runtime':args.pdf_python,
              'sha256':{p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(out.rglob('*')) if p.is_file() and p.name!='release_manifest.json'}}
    (out/'release_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FROZEN SOURCE '+code_sha,flush=True)
    print('DELIVERY '+str(out),flush=True)


def make_report(out,sha):
    core=read_json(out/'core/summary.json');q4=read_json(out/'q4/stress.json')
    q5=read_csv(out/'q5/comparison.csv');frontier=read_csv(out/'core/p_frontier.csv')
    cases=read_csv(out/'q4/scenario_table.csv');data=read_json(out/'data_validation/summary.json')
    tests=(out/'tests.log').read_text(encoding='utf-8')
    test_summary=next((line for line in reversed(tests.splitlines()) if ' passed' in line),'See tests.log')
    f=lambda n:f'{float(n):.3f}'
    lines=['# 本轮冻结结果与解释','',f'数值源提交：`{sha}`。结果/图均为条件模型输出，非真实覆盖或健康预测。',
           '',f'数值验收：**{test_summary}**。详见tests.log；历史发布样例的结构检查与当前代码独立数值测试分开解释。',
           '', '## Q1—Q2：固定网络、移动站与公平',
           '',f"默认日需求{f(core['baseline']['demand_total'])}人次；固定网络缺口{f(core['baseline']['unmet_total_raw'])}，"
              f"3辆MCH缺口{f(core['p3']['unmet_total_raw'])}，所选{core['p3']['chosen']}。",
           '', '这是合成区/需求/候选位置和交通输入的条件结果，不能把这些编号当作已批准的实际部署点。',
           '', '| p | 效率缺口 | max-min缺口 | 全区最差率(max-min) | 非豁免最差率 | 新增1辆的边际人次 |',
           '|---|---|---|---|---|---|']
    for r in frontier:
        lines.append(f"| {r['p']} | {f(r['efficiency_unmet'])} | {f(r['maxmin_unmet'])} | {f(r['maxmin_worst_all'])} | {f(r['maxmin_worst_nonexempt'])} | {f(r['marginal_unmet_reduction'])} |")
    lines+=['','非豁免口径只用于公开的公平约束集合；默认豁免D08仍保留在全区统计。p=7→8无边际服务，不代表真实新增地点永远无价值。',
            '',f"同一p3部署删除时段约束后服务上界{f(core['timing_ablation']['pooled_day_served'])}，"
               f"原分时服务{f(core['timing_ablation']['period_served'])}。差值说明聚合全天容量可能乐观，不能当成实测延时收益。",
            '', '## Q3：搬迁何时有意义',
            '',f"默认7日固定/动态缺口均{f(core['baseline_week_static'])}（无搬迁收益）。"
               f"D05在第3—5天需求×3时，同一外生需求下固定{f(core['shock_week_static'])}、动态{f(core['shock_week_dynamic'])}，"
               f"减少{f(core['shock_week_static']-core['shock_week_dynamic'])}人次。全状态/全匹配最优仅在同日移动和既定候选集内成立。",
            '', '## Q4：故障、道路/公交阻断与预测误差',
            '', '| 故障 | 需求倍数 | 不搬缺口 | 响应缺口 | 收益 | 就绪耗时h |', '|---|---|---|---|---|---|']
    for r in cases:
        if r['kind']=='vehicle' and r['down']=='MCH-3':
            lines.append(f"| {r['down']}车辆失效 | {r['shock_mult']} | {r['no_move']} | {r['best']} | {r['gain']} | {r['hours']} |")
    lines+=['',f"100次给定分布抽样的收益P10/P50/P90={q4['gain_p10']}/{q4['gain_p50']}/{q4['gain_p90']}人次；"
               f"正收益份额{q4['positive_gain_share']}。每次不搬与响应共享故障、需求、乘客行程倍数、搬迁时长倍数与事故前部署。",
            '', '不搬必可选，所以行动可行份额1不能解释为系统实际可靠率或24小时恢复概率。全区最差率逐样本保留；本算法效率优先，不保证公平最优。',
            '', '## Q5：跨年库存和滚动基线',
            '', '本表初始拥有2辆；主pipeline初始拥有3辆，二者参数不同。金额是假设年度全成本，默认代表日权重为1，不是年度客流预测。',
            '', '| 预算/热路径 | 五年DP缺口分数 | 滚动分数 | DP改善 | 现有资产基线分数 |', '|---|---|---|---|---|']
    for r in q5:
        lines.append(f"| {r['scenario']} | {f(r['dp_unmet_score'])} | {f(r['rolling_unmet_score'])} | {f(r['dp_gain_vs_rolling'])} | {f(r['maintain_unmet_score'])} |")
    lines+=['','DP知道完整未来热路径，属于条件规划基准。提前购买但暂不开工有时可改善未来预算受限方案；不是可以准确预知2027—2031热浪。',
            '', '## 稳健性、真实核验与交接',
            '', '以下只标采样翻转区间，不声称精确临界点：']
    for flip in core['sampled_site_set_flip_brackets']:
        lines.append(f"- {flip['axis']}：{flip['sampled_interval']}，{flip['old']} → {flip['new']}。")
    lines+=['','完整27行OAT在core/oat.csv；成本0.5—10倍结果在q5/cost_sensitivity.csv。费用轴范围不相同，不作“参数重要性”排序。',
            '', '真实输入核验：350站日格、逐日规则与旧包络、15村聚合结果见data_validation/summary.json。它不是独立服务结果检验；预登记现场采样/成块留出仍未执行。',
            '', '发现关键现场OD、配员、日历、费用或需求超出区间，先更新输入与可行集再求解；不自动按本表购买或派车。',
            '', '![条件边际与真实站点库存情景](core/frontiers.png)',
            '', '图源：本轮冻结CSV，绘图脚本src/exp/run_takeover_evidence.py::make_figures。左图使用合成需求/区位；右图加入MAG来源登记与日历，其余仍为假设/派生。单位均为代表日未满足人次。',
            '', '![逐区条件缺口](core/district_gaps.png)',
            '', '图源：core/district_gap.csv；固定网络与+3 MCH共用需求、交通和容量。未满足人次不是未服务独立居民。']
    (out/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    claims=[
        ('C01','贪心可以阻塞其他区；联合LP需保留','M1/M3','core/minimal_case.json','lp.objective=19; greedy_served=10','数值假设算例，不是实测'),
        ('C02','效率与max-min可能存在代价','M3/A14','core/p_frontier.csv','p=2 efficiency_unmet/maxmin_unmet; worst_all/nonexempt','豁免D08公开保留全区率'),
        ('C03','分时约束不能用全天容量替代','M2/M3','core/timing_ablation.json','period_served,pooled_day_served,same_sites','日池化是乐观上界，不是实测收益'),
        ('C04','默认七日无搬迁收益，局部冲击可有收益','M2/M4','core/weeks.json','baseline; same_exogenous_shock_static_and_dynamic','同日旅行、并行crew、初日就绪、有限候选集'),
        ('C05','车辆故障后可通过调度减少缺口','M2/M5','q4/scenario_details.json','kind=vehicle/down=MCH-3/response_gain,search','给定事故09点、已许可场地、假设移动时间'),
        ('C06','压力分位是条件抽样，不是现实可靠率','M5','q4/stress_draws.json','draw,gain,passenger_access_multiplier,initial_chosen','分布ASSUME；不搬恒可选'),
        ('C07','库存与开工分开可改善跨年预算方案','M6','q5/comparison.csv','dp_gain_vs_rolling; low scenarios','DP预知未来，价格/采购时滞/储存均假设'),
        ('C08','关键假设可改变站点组合','M2/M3/A03-A12','core/summary.json','sampled_site_set_flip_brackets','只知采样区间，非精确阈值'),
        ('C09','逐日MAG来源重构正确但服务验证仍缺','A12','data_validation/summary.json','calendar.legacy_weekday_envelope_mae_hours,calendar.revised_day_lookup_mae_hours,calendar.raw_csv_weekday_cell_mismatches,population,service_outcome_validation.status','同源重构不是独立实际营业/客流验证'),
    ]
    with (out/'CLAIM_EVIDENCE.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['claim_id','claim','formula_assumptions','result_file','fields','limits',
                                   'source_commit','code_config','figure_text','reviewer'])
        for cid,claim,formula,path,field,limit in claims:
            w.writerow([cid,claim,formula,path,field,limit,sha,'run_meta.json + release_manifest.json run commands',
                        'RESULTS.md / frontiers.png as applicable','AI primary self-check; AI Q4/data independent checks; human team pending'])


if __name__=='__main__':main()
