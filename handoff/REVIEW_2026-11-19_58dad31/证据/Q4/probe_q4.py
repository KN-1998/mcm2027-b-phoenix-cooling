"""Read-only Q4 v3 audit: --repo SNAPSHOT --out DIRECTORY."""
from pathlib import Path
import argparse, json, os, subprocess, sys
from unittest.mock import patch

ap=argparse.ArgumentParser()
ap.add_argument('--repo',type=Path,required=True)
ap.add_argument('--out',type=Path,required=True)
a=ap.parse_args(); repo=a.repo.resolve(); out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo))
from src.mch.disruption import plan_response,apply_shock,pick_low_income
from src.mch.static import solve_static,_assign,_active_sites
from src.mch.schema import District,Site,Instance
from src.mch.loaders import load_instance

inst=load_instance()
result={'reviewed_commit':'58dad31d0faf75a5a5742dcea47c314a1ac43fe9'}
try: plan_response(inst,3,mult=1.,down_vehicle_at='MCH-1')
except ValueError as e:result['undeployed_vehicle_rejected']=str(e)
result['vehicle_MCH3_failure']=plan_response(inst,3,mult=1.,down_vehicle_at='MCH-3')
result['closed_candidate_tiny_budget']=plan_response(inst,3,mult=1.,down_site='MCH-3',budget_hours=.1)
result['closed_fixed_tiny_budget']=plan_response(inst,3,mult=1.,down_site='R01',budget_hours=.1)

ds=[District(x,x,1000,.1,.1,100000 if x in 'AB' else 10000,.1,.5) for x in 'ABCD']
ss=[Site(x,x,'candidate_mch',x,0.,0.,250,0.,24.) for x in 'ABCD']
test=Instance(ds,ss,{(x,x):1. for x in 'ABCD'},{(x,0):25. if x in 'AB' else 24.75 for x in 'ABCD'},1)
result['custom_base']=solve_static(test,2).chosen
shocked=apply_shock(test,pick_low_income(test,2),10.)
with patch('src.mch.dynamic.move_time_hours',return_value=2.):
    result['two_moves_serial']=plan_response(test,2,mult=10.,parallel=False,budget_hours=24.)
    result['two_moves_parallel']=plan_response(test,2,mult=10.,parallel=True,budget_hours=24.)
    result['parallel_tight_budget']=plan_response(test,2,mult=10.,parallel=True,budget_hours=2.5)
    true_parallel=_assign(shocked,_active_sites(shocked,('C','D')),0,30.,250.,downtime={'C':.8,'D':.8})
    result['parallel_feasible_witness']={'chosen':['C','D'],'moves':[{'from':'A','to':'C','depart_h':0.,'ready_h':2.},{'from':'B','to':'D','depart_h':0.,'ready_h':2.}],
       'total_hours':2.,'unmet':true_parallel.metrics['unmet_total'],'budget_hours':2.5}

times={('A','C'):2.,('A','D'):2.1,('B','C'):2.1,('B','D'):5.2}
with patch('src.mch.dynamic.move_time_hours',side_effect=lambda inst,src,dst:times.get((src,dst),1000.)):
    result['greedy_matching_response']=plan_response(test,2,mult=10.,budget_hours=5.)
    witness=_assign(shocked,_active_sites(shocked,('C','D')),0,30.,250.,downtime={'C':.79,'D':.58})
    result['better_matching_witness']={'chosen':['C','D'],'moves':[{'from':'B','to':'C','ready_h':2.1},{'from':'A','to':'D','ready_h':4.2}],
      'total_hours':4.2,'unmet':witness.metrics['unmet_total'],'budget_hours':5.,
      'metric_interpretation':'1D positions A=0,B=3.1,C=1.5,D=-1.6, duration=abs(x-y)+0.5 setup; e.g. one x unit is 40km at40km/h'}

cmd=[sys.executable,'-m','src.exp.run_q4_response','--p','3','--mults','1.0','--down-sites','MCH-3','--down-vehicles-at=','--budget-hours','0.1','--stress-draws','1','--out',str(out/'cli_tiny_budget')]
proc=subprocess.run(cmd,cwd=repo,capture_output=True,env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=90)
result['tiny_budget_cli']={'returncode':proc.returncode,'stderr':proc.stderr.decode('utf-8').replace(str(repo),'<REPO>').replace(str(out),'<OUT>')}
checks={
 'parallel_flag_has_identical_timeline':result['two_moves_parallel']['best']['timeline']==result['two_moves_serial']['best']['timeline'],
 'parallel_tight_budget_rejects_better_feasible_plan':result['parallel_tight_budget']['best']['unmet']>result['parallel_feasible_witness']['unmet'],
 'closed_candidate_loses_no_move_option':result['closed_candidate_tiny_budget']['best'] is None and result['closed_candidate_tiny_budget']['no_move']['chosen'],
 'greedy_matching_misses_better_feasible_plan':result['greedy_matching_response']['best']['unmet']>result['better_matching_witness']['unmet'],
 'tiny_budget_cli_printing_fixed':proc.returncode==0,
}
result['checks']={k:bool(v) for k,v in checks.items()}

# A relocation completed before a destination's late opening loses no opening hours.
# Explicit physical interpretation: decision09:00, eight-hour trip/setup, ready17:00,
# destination22:00-24:00. The API has no start-clock argument and still discounts80%.
window_ds=[District('A','A',1000,.1,.1,100000,.1,.5),
           District('B','B',1000,.1,.1,10000,.1,.5),
           District('Z','Z',1000,.1,.1,5000,.1,.5)]
window_ss=[Site('A','A','candidate_mch','A',0.,0.,250,9.,22.),
           Site('B','B','candidate_mch','B',0.,0.,250,22.,24.)]
window_inst=Instance(window_ds,window_ss,{('A','A'):1.,('B','B'):1.},
                     {('A',0):100.,('B',0):400.,('Z',0):0.},1)
with patch('src.mch.dynamic.move_time_hours',return_value=8.):
    window_response=plan_response(window_inst,1,mult=10.,budget_hours=24.)
window_shocked=apply_shock(window_inst,pick_low_income(window_inst,2),10.)
window_oracle=_assign(window_shocked,_active_sites(window_shocked,('B',)),0,30.,250.)
result['opening_window_not_intersected']={'response':window_response,
   'physical_scenario':'09:00 decision +8h travel/setup=17:00 ready, destination opens22:00-24:00; no operating-hour loss',
   'full_late_window_feasible_witness_unmet':window_oracle.metrics['unmet_total'],
   'current_API_has_no_response_start_clock_argument':True,
   'best_reported_unmet':window_response['best']['unmet']}
result['checks']['late_window_ignored_changes_choice']=bool(window_response['best']['chosen']==['A'] and window_oracle.metrics['unmet_total']<window_response['best']['unmet'])
(out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'checks':result['checks'],'parallel_reported_unmet':result['parallel_tight_budget']['best']['unmet'],'parallel_witness_unmet':result['parallel_feasible_witness']['unmet'],
 'matching_reported_unmet':result['greedy_matching_response']['best']['unmet'],'matching_witness_unmet':result['better_matching_witness']['unmet'],
 'failed_candidate_no_move_unmet':result['closed_candidate_tiny_budget']['no_move']['unmet']},ensure_ascii=True))
