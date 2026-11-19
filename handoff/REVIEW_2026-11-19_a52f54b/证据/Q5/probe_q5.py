"""Read-only Q5 audit at a52f54ba7b32. --repo PATH --out PATH."""
from pathlib import Path
import argparse, contextlib, csv, io, json, sys
from unittest.mock import patch

ap=argparse.ArgumentParser()
ap.add_argument('--repo',type=Path,required=True)
ap.add_argument('--out',type=Path,required=True)
a=ap.parse_args();repo=a.repo.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo))
from src.exp import run_q5_plan as q5
from src.mch.loaders import load_instance
from src.mch.schema import District,Site,Instance

def read_rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def run_case(name,budget,p0=2,heat=None):
    dest=out/name
    with patch.object(q5,'BUDGETS',{'case':budget}),patch.object(q5,'HEAT',heat or {'flat':[1.]*5}),patch.object(q5.runmeta,'write',return_value=None),contextlib.redirect_stdout(io.StringIO()):
        code=q5.main(['--p0',str(p0),'--out',str(dest)])
    return {'exit_code':code,'rows':read_rows(dest/'plan.csv'),
            'summary':json.loads((dest/'summary.json').read_text(encoding='utf-8'))}

result={'reviewed_commit':'a52f54ba7b3213c1354992b8d94b221ebced6727'}
default=out/'default_reproduction'
with patch.object(q5.runmeta,'write',return_value=None),contextlib.redirect_stdout(io.StringIO()):
    code=q5.main(['--out',str(default)])
saved=json.loads((repo/'results/q5_plan/summary.json').read_text(encoding='utf-8'))
generated=json.loads((default/'summary.json').read_text(encoding='utf-8'))
default_rows=read_rows(default/'plan.csv')
result['default']={'exit_code':code,'summary_matches_saved':generated==saved,
                   'first_year_rows':[r for r in default_rows if r['year']=='2027']}
result['old_many_cut_example']=run_case('many_cuts',240000,p0=8)
result['zero_start_zero_budget']=run_case('zero_start',0,p0=0)
result['zero_budget_positive_start']=run_case('zero_budget',0,p0=2)

inst=load_instance()
actual=next(r for r in default_rows if r['budget_scenario']=='base' and r['heat_scenario']=='base' and r['year']=='2027')
actual_unmet=float(q5.evaluate(inst,int(actual['fleet']),float(actual['extend_to']),actual['shuttle']=='True')[0])
witness_cost=q5.annual_cost(4,22.,False,2)
witness_unmet=float(q5.evaluate(inst,4,22.,False)[0])
result['two_new_hubs_omitted']={'actual':actual,'actual_unrounded_unmet':actual_unmet,
   'witness':{'fleet':4,'extend_to':22.,'shuttle':False,'cost':witness_cost,'unmet':witness_unmet},
   'gain':round(actual_unmet-witness_unmet,3)}

ownership=run_case('ownership',1000000,p0=8,heat={'stress_jump':[1.,4.,4.,4.,4.]})
hot=load_instance();hot.demand={k:v*4 for k,v in hot.demand.items()}
ownership['witness_existing_eight_opex']=q5.annual_cost(8,None,False,0)
ownership['algorithm_rebuy_eight_cost']=q5.annual_cost(8,None,False,1)
ownership['existing_eight_unmet']=float(q5.evaluate(hot,8,None,False)[0])
ownership['fixture_scope']='Deliberate demand-jump state-transition test, not a Phoenix forecast. Existing8 assets are mothballed then reactivated; no disposal or repurchase is assumed.'
result['ownership_active_count_conflation']=ownership

d=District('D','D',1000,.1,.1,30000,.1,.5);s=Site('C','C','cooling','D',0,0,1000,9,17)
fixture=Instance([d],[s],{('D','C'):1.},{('D',0):100.},1)
u,w=q5.evaluate(fixture,0,21.,False)
result['old_metric_case']={'unmet':float(u),'worst':float(w),'original_close':s.close_hour}
checks={
 'default_reproduces':generated==saved,
 'default_opex_correct':all(float(r['hub_opex'])==int(r['fleet'])*q5.COST['hub_ops'] for r in default_rows),
 'old_multi_cut_fixed':result['old_many_cut_example']['rows'][0]['fleet']=='2' and result['old_many_cut_example']['rows'][0]['within_budget']=='True',
 'old_metric_purity_fixed':abs(float(w)-.16)<1e-6 and s.close_hour==17,
 'p_plus_one_limit_omits_better_affordable_pair_buy':witness_cost['total']<=4000000 and witness_unmet<actual_unmet,
 'mothballed_asset_mistakenly_requires_new_purchase':ownership['rows'][0]['fleet']=='7' and ownership['witness_existing_eight_opex']['total']<=1000000<ownership['algorithm_rebuy_eight_cost']['total'] and ownership['existing_eight_unmet']<float(ownership['rows'][1]['unmet_after']),
 'zero_start_labels_cost_feasible_config_infeasible':result['zero_start_zero_budget']['rows'][0]['action']=='infeasible' and result['zero_start_zero_budget']['rows'][0]['within_budget']=='True'}
result['checks']={k:bool(v) for k,v in checks.items()}
assert all(result['checks'].values()),result['checks']
(out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result['checks'],ensure_ascii=True))
