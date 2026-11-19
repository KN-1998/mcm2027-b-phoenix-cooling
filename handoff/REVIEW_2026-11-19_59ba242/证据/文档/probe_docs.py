"""Read-only checks for assumptions and public-result claims at 59ba2421ce3d."""
from pathlib import Path
import argparse, copy, hashlib, json, sys

ap=argparse.ArgumentParser()
ap.add_argument('--repo',type=Path,required=True)
ap.add_argument('--out',type=Path,required=True)
a=ap.parse_args();repo=a.repo.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo))
from src.mch.loaders import load_instance
from src.mch.realnet import build_real_instance
from src.mch.static import solve_static
from src.mch.schema import District,Site,Instance

result={'reviewed_commit':'59ba2421ce3d1d1affc59b366d202c7526588585'}
base=load_instance();s1=solve_static(base,3)
double=copy.deepcopy(base);double.demand={k:v*2 for k,v in double.demand.items()};s2=solve_static(double,3)
result['A2_default_demand_doubled']={
 'base_unmet':s1.metrics['unmet_total'],'twice_base_unmet':2*s1.metrics['unmet_total'],
 'double_demand_unmet':s2.metrics['unmet_total'],'base_chosen':s1.chosen,'double_chosen':s2.chosen}

d=[District('D1','D1',1000,.1,.1,30000,.1,.5),District('D2','D2',1000,.1,.1,30000,.1,.5)]
sites=[Site('C','C','cooling','D1',0,0,50,0,24),
       Site('A','A','candidate_mch','D1',0,0,250,9,22),
       Site('B','B','candidate_mch','D2',0,0,250,9,22)]
fixture=Instance(d,sites,{('D1','C'):1.,('D1','A'):1.,('D2','B'):1.},
                 {('D1',0):100.,('D2',0):75.},1)
f1=solve_static(fixture,1)
twice=copy.deepcopy(fixture);twice.demand={k:v*2 for k,v in twice.demand.items()};f2=solve_static(twice,1)
result['A2_valid_capacity_ranking_counterexample']={
 'fixture':{'district_demands':[100,75],'fixed_C_capacity':50,'C_hours':[0,24],
            'candidate_A_B_capacity_each':250,'candidate_hours':[9,22],
            'reachability':'D1->C,A and D2->B only; all finite edges1min'},
 'base_chosen':f1.chosen,'double_chosen':f2.chosen,
 'base_unmet':f1.metrics['unmet_total'],'double_unmet':f2.metrics['unmet_total']}

real=build_real_instance()
result['D08_current_realnet_access']={
 'fixed_cooling_within30':[s.id for s in real.fixed_sites() if s.kind in ('cooling','respite') and real.access.get(('D08',s.id),9999)<=30],
 'candidate_times_minutes':{s.id:real.access.get(('D08',s.id)) for s in real.candidate_sites()},
 'note':'Distance proxies from a synthetic demand point, not independently observed access.'}

pipeline=json.loads((repo/'results/run_csv/summary.json').read_text(encoding='utf-8-sig'))
result['A12_pipeline_fairness']={k:pipeline['q2_static'].get(k) for k in ['worst_unmet_ratio','worst_unmet_ratio_nonexempt']}
segments=json.loads((repo/'results/segments/summary.json').read_text(encoding='utf-8-sig'))
result['A4_current_segments']={'rows':segments,'endpoint_increase_percent':100*(segments[-1]['unmet_total']/segments[0]['unmet_total']-1)}
summary=json.loads((repo/'results/q5_plan/summary.json').read_text(encoding='utf-8-sig'))
result['q5_saved_opex_shares']={k:v['total_opex']/v['total_spend'] for k,v in summary['plans'].items()}
result['q5_runmeta']=json.loads((repo/'results/q5_plan/run_meta.json').read_text(encoding='utf-8-sig'))
result['dependency_source_sha256']={p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in ['src/mch/realnet.py','src/mch/incoming.py','src/mch/runmeta.py','src/exp/run_pipeline.py']}
result['checks']={
 'default_unmet_is_not_proportional_to_demand':bool(abs(s2.metrics['unmet_total']-2*s1.metrics['unmet_total'])>1e-6),
 'a_valid_fixture_changes_optimal_placement':f1.chosen!=f2.chosen,
 'A4_saved_increase_is_not15percent':abs(result['A4_current_segments']['endpoint_increase_percent']-15)>1,
}
assert all(result['checks'].values())
(out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:result[k] for k in ['A2_default_demand_doubled','A2_valid_capacity_ranking_counterexample','D08_current_realnet_access','checks']},ensure_ascii=True))
