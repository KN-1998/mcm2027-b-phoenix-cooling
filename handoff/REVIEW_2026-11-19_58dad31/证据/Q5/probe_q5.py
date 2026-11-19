from pathlib import Path
import argparse,contextlib,copy,csv,io,json,sys
from unittest.mock import patch

ap=argparse.ArgumentParser(description='Read-only Q5 review reproductions for 58dad31d0faf')
ap.add_argument('--repo',type=Path,required=True)
ap.add_argument('--out',type=Path,required=True)
a=ap.parse_args()
ROOT=a.repo.resolve()
OUT=a.out.resolve();OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
from src.exp import run_q5_plan as q5
from src.mch.schema import District,Site,Instance
from src.mch.loaders import load_instance
from src.mch.static import solve_static

def load_csv(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def run_case(name,budget,p0=2,pmax=8,fixture=None,heat=None):
    out=OUT/name
    replacements={'BUDGETS':{'case':budget},'HEAT':heat or {'flat':[1.]*5}}
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.multiple(q5,**replacements))
        stack.enter_context(patch.object(q5.runmeta,'write',return_value=None))
        if fixture is not None:stack.enter_context(patch.object(q5,'load_instance',side_effect=lambda:copy.deepcopy(fixture)))
        with contextlib.redirect_stdout(io.StringIO()):
            code=q5.main(['--p0',str(p0),'--pmax',str(pmax),'--out',str(out)])
    return {'exit_code':code,'rows':load_csv(out/'plan.csv'),'summary':json.loads((out/'summary.json').read_text(encoding='utf-8'))}

result={'reviewed_commit':'58dad31d0faf75a5a5742dcea47c314a1ac43fe9'}
zero=run_case('zero_budget',0)
zero['annual_existing_hub_operating_cost_by_declared_assumption']=2*q5.COST['hub_ops']
result['zero_budget_still_operates']=zero
tiny=run_case('tiny_budget',200000)
tiny['first_year_actual_hub_only_cost_under_declared_assumption']=3*q5.COST['hub_ops']+q5.COST['hub_buy']
result['tiny_budget_wrongly_affordable']=tiny

d=District('D','D',1000,.1,.1,30000,.1,.5)
s=Site('C','C','cooling','D',0,0,1000,9,17)
inst=Instance([d],[s],{('D','C'):1.},{('D',i):100. for i in range(7)},7)
mut=run_case('wrong_worst',2000000,0,0,inst)
first=mut['rows'][0]
correct=copy.deepcopy(inst)
q5.unmet_for(correct,0,float(first['extend_to']) if first['extend_to'] else None,first['shuttle']=='True')
correct_metrics=solve_static(correct,0,max_minutes=45 if first['shuttle']=='True' else 30).metrics
mut['correct_chosen_config_worst']=correct_metrics['worst_unmet_ratio']
mut['correct_chosen_config_unmet']=correct_metrics['unmet_total']
result['worst_metric_state_leak']=mut

repo_summary=json.loads((ROOT/'results/q5_plan/summary.json').read_text(encoding='utf-8'))
repo_rows=load_csv(ROOT/'results/q5_plan/plan.csv')
result['saved_default_actions']={k:v['actions'] for k,v in repo_summary['plans'].items()}
result['low_mild_small_gain_still_buy']=[r for r in repo_rows if r['budget_scenario']=='low' and r['heat_scenario']=='mild' and float(r['gain'])<5]
baseinst=load_instance()
baseline_q2=solve_static(baseinst,2).metrics['unmet_total']
q5baseline=q5.unmet_for(baseinst,2,None,False)
result['baseline_hours_changed']={'standard_q2_p2_unmet':baseline_q2,'q5_p2_unmet':q5baseline}

# The planner evaluates only one action per year; show a legal combined configuration
# under its own 2027 $4m action-cost convention strictly improves its selected action.
check=load_instance()
single=q5.unmet_for(check,2,22,False)
joint=q5.unmet_for(check,3,22,True)
result['unexamined_affordable_joint_action']={'budget':4000000,
    'cost_as_current_action_convention':q5.COST['extend_22']+q5.COST['shuttle']+q5.COST['hub_buy']+q5.COST['hub_ops'],
    'selected_extend22_only_unmet':single,'extend22_plus_shuttle_plus_one_hub_unmet':joint,
    'note':'Uses the current one-time action-cost convention solely to isolate the restricted action set; recurring-cost omissions are independently audited.'}
result['simplest_joint_extension_plus_buy']={
    'budget':4000000,'current_cost_convention':q5.COST['extend_22']+q5.COST['hub_buy']+q5.COST['hub_ops'],
    'including_existing_two_hub_annual_ops':q5.COST['extend_22']+q5.COST['hub_buy']+3*q5.COST['hub_ops'],
    'unmet':q5.unmet_for(load_instance(),3,22,False)}
with contextlib.redirect_stdout(io.StringIO()):
    default_exit=q5.main(['--out',str(OUT/'default_run')])
reproduced=json.loads((OUT/'default_run/summary.json').read_text(encoding='utf-8'))
result['default_reproduction_exit_code']=default_exit
result['default_reproduction_summary_exactly_matches_saved']=reproduced==repo_summary
baseline=q5.unmet_for(load_instance(),2,None,False)
result['dollar_objective_documentation_counterexample']={
    '2027_selected_base_action':'extend_22',
    'selected_gain_per_million_usd':(baseline-q5.unmet_for(load_instance(),2,22,False))/(q5.COST['extend_22']/1e6),
    'available_buy_gain_per_million_usd':(baseline-q5.unmet_for(load_instance(),3,None,False))/((q5.COST['hub_buy']+q5.COST['hub_ops'])/1e6),
    'implemented_objective':'max(gain, -cost), not max gain/cost'}

result['checks']={
 'zero_budget_returns_feasible_nonzero_operating_fleet':all(r['within_budget']=='True' and r['fleet']=='2' and float(r['cost'])==0 for r in zero['rows']),
 'tiny_budget_hub_cost_exceeds_limit':tiny['first_year_actual_hub_only_cost_under_declared_assumption']>200000 and tiny['rows'][0]['within_budget']=='True',
 'chosen_worst_differs_from_written_worst':float(first['worst_unmet_ratio'])!=correct_metrics['worst_unmet_ratio'],
 'joint_affordable_and_better':result['unexamined_affordable_joint_action']['cost_as_current_action_convention']<=4000000 and joint<single,
 'default_has_low_gain_purchases':bool(result['low_mild_small_gain_still_buy'])}
assert all(result['checks'].values()),result['checks']
result['checks']={k:bool(v) for k,v in result['checks'].items()}
(OUT/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'checks':result['checks'],'wrong_worst_written':first['worst_unmet_ratio'],
                 'wrong_worst_correct':correct_metrics['worst_unmet_ratio'],
                 'joint_case':result['unexamined_affordable_joint_action']},ensure_ascii=True))
