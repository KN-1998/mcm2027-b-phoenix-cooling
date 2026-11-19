"""Read-only Q5 v2 review: --repo REPOSITORY --out EVIDENCE_DIRECTORY."""
from pathlib import Path
import argparse, contextlib, copy, csv, io, json, sys
from unittest.mock import patch

parser=argparse.ArgumentParser()
parser.add_argument('--repo',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
repo,out=args.repo.resolve(),args.out.resolve()
out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo))
from src.exp import run_q5_plan as q5
from src.mch.loaders import load_instance
from src.mch.schema import District,Site,Instance

def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))

def run_case(name,budget=None,p0=2,heat=None):
    dest=out/name
    with contextlib.ExitStack() as stack:
        if budget is not None:stack.enter_context(patch.object(q5,'BUDGETS',{'case':budget}))
        if heat is not None:stack.enter_context(patch.object(q5,'HEAT',heat))
        stack.enter_context(patch.object(q5.runmeta,'write',return_value=None))
        with contextlib.redirect_stdout(io.StringIO()):
            code=q5.main(['--p0',str(p0),'--out',str(dest)])
    return {'exit_code':code,'rows':rows(dest/'plan.csv'),
            'summary':json.loads((dest/'summary.json').read_text(encoding='utf-8'))}

result={'reviewed_commit':'59ba2421ce3d1d1affc59b366d202c7526588585'}
default=run_case('default_reproduction')
saved=json.loads((repo/'results/q5_plan/summary.json').read_text(encoding='utf-8'))
result['default_runner']={'exit_code':default['exit_code'],'summary_matches_saved':default['summary']==saved}
result['default_first_years']=[r for r in default['rows'] if r['year']=='2027']

result['zero_budget']=run_case('zero_budget',0,heat={'flat':[1]*5})
result['zero_budget']['feasible_omitted_alternative_cost']=q5.annual_cost(0,None,False)
result['many_cuts_needed']=run_case('many_cuts_needed',240000,p0=8,heat={'flat':[1]*5})
result['many_cuts_needed']['feasible_omitted_two_active_cost']=q5.annual_cost(2,None,False)

inst=load_instance()
options=[]
for p in range(9):
    for ext in (None,21.,22.):
        for shuttle in (False,True):
            cost=q5.annual_cost(p,ext,shuttle,buy=max(0,p-2))
            unmet,worst=q5.evaluate(inst,p,ext,shuttle)
            options.append({'active_fleet':p,'extend_to':ext,'shuttle':shuttle,
                            'capital_for_new_above_initial_two':cost['capital'],
                            'total_first_year_cost':cost['total'],
                            'unmet':float(unmet),'worst':float(worst)})
frontier={}
for label,budget in q5.BUDGETS.items():
    affordable=[r for r in options if r['total_first_year_cost']<=budget]
    best=min(affordable,key=lambda r:(r['unmet'],r['total_first_year_cost']))
    actual=next(r for r in default['rows'] if r['budget_scenario']==label and r['heat_scenario']=='base' and r['year']=='2027')
    exact,_=q5.evaluate(inst,int(actual['fleet']),None if not actual['extend_to'] else float(actual['extend_to']),actual['shuttle']=='True')
    frontier[label]={'annual_budget':budget,'actual_runner_first_year':actual,
                     'actual_configuration_unrounded_unmet':float(exact),
                     'best_one_year_combination_under_same_costs':best,
                     'improvement_over_runner':round(float(exact)-best['unmet'],3)}
result['first_year_action_combination_frontier']=frontier
result['first_year_options']=options

d=District('D','D',1000,.1,.1,30000,.1,.5)
s=Site('C','C','cooling','D',0,0,1000,9,17)
single=Instance([d],[s],{('D','C'):1.},{('D',0):100.},1)
extended=q5.evaluate(single,0,21.,False)
other=q5.evaluate(single,0,None,True)
result['evaluation_purity_and_metric_fix']={'chosen_extension_unmet':float(extended[0]),
    'chosen_extension_worst':float(extended[1]),'implied_worst':float(extended[0])/100,
    'original_close_after_two_calls':s.close_hour,'other_candidate_unmet':float(other[0])}

checks={
    'default_summary_reproduces':result['default_runner']['summary_matches_saved'],
    'annual_hub_opex_matches_active_count_in_default':all(float(r['hub_opex'])==int(r['fleet'])*q5.COST['hub_ops'] for r in default['rows']),
    'default_budget_flags_match_full_recorded_costs':all((r['within_budget']=='True')==(float(r['total_cost'])<=float(r['budget'])) for r in default['rows']),
    'evaluate_is_pure':s.close_hour==17,
    'selected_worst_is_correct_in_old_counterexample':abs(float(extended[1])-float(extended[0])/100)<1e-6,
    'zero_budget_marks_infeasible_but_still_runs_one_vehicle':all(r['within_budget']=='False' and int(r['fleet'])==1 for r in result['zero_budget']['rows']),
    'one_cut_per_year_misses_affordable_starting_configuration':result['many_cuts_needed']['rows'][0]['within_budget']=='False' and q5.annual_cost(2,None,False)['total']<=240000,
    'single_action_rule_is_dominated_by_affordable_combination':frontier['base']['improvement_over_runner']>0}
result['checks']={k:bool(v) for k,v in checks.items()}
assert all(result['checks'].values()),result['checks']
(out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'checks':result['checks'],'frontier':frontier},ensure_ascii=True))
