"""Read-only Q4 v4 review fixtures for a52f54ba7b32. --repo PATH --out PATH."""
from pathlib import Path
import argparse,json,math,os,subprocess,sys

ap=argparse.ArgumentParser()
ap.add_argument('--repo',type=Path,required=True)
ap.add_argument('--out',type=Path,required=True)
a=ap.parse_args();repo=a.repo.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(repo))
from src.mch.disruption import plan_response,apply_shock,pick_low_income
from src.mch.dynamic import move_time_hours
from src.mch.loaders import load_instance
from src.mch.schema import District,Site,Instance
from src.mch.static import _assign,_active_sites,solve_static

result={'reviewed_commit':'a52f54ba7b3213c1354992b8d94b221ebced6727'}
inst=load_instance()
result['p8_closed_candidate']=plan_response(inst,8,mult=1.,down_site='MCH-3')
result['default_vehicle3_failure']=plan_response(inst,3,mult=1.,down_vehicle_at='MCH-3')
result['default_vehicle3_one_hour_budget']=plan_response(inst,3,mult=1.,down_vehicle_at='MCH-3',budget_hours=1.)
true_stay=_assign(inst,_active_sites(inst,('MCH-3','MCH-8')),0,30.,250.,downtime={'MCH-3':.913})
result['vehicle3_one_hour_feasible_witness']={'chosen':['MCH-3','MCH-8'],
    'timeline':[{'from':'MCH-7','to':'MCH-3','depart_h':0.,'ready_h':.87}],
    'unchanged_site':'MCH-8','total_hours':.87,'n_moves':1,'unmet':true_stay.metrics['unmet_total']}

# Actual model Euclidean travel formula, plus its 0.5h setup; no travel-time patch.
def physical_fixture(positions,demands,km_per_unit=40.):
    ds=[District(x,x,1000,.1,.1,100000 if x in 'AB' else 10000,.1,.5) for x in 'ABCD']
    ss=[Site(x,x,'candidate_mch',x,33.5+positions[x][0]*km_per_unit/111.,
             -112.+positions[x][1]*km_per_unit/95.,250,0.,24.) for x in 'ABCD']
    return Instance(ds,ss,{(x,x):1. for x in 'ABCD'},{(x,0):float(demands[x]) for x in 'ABCD'},1)

# Sum-minimizing assignment: 0.55+0.95=1.50h.  Feasible parallel matching:
# 0.76+0.76=1.52h but max0.76h, within0.80h budget.  Positions are realizable in2D.
dx=(3.1**2+2.6**2-4.5**2)/(2*3.1)
dy=math.sqrt(2.6**2-dx**2)
pos={'A':(0.,0.),'B':(3.1,0.),'C':(.5,0.),'D':(dx,dy)}
f=physical_fixture(pos,{'A':25,'B':25,'C':24.75,'D':24.75},km_per_unit=4.)
shocked=apply_shock(f,pick_low_income(f,2),10.)
r=plan_response(f,2,mult=10.,parallel=True,budget_hours=.80)
factor={s:1-move_time_hours(f,src,s)/10 for src,s in [('B','C'),('A','D')]}
w=_assign(shocked,_active_sites(shocked,('C','D')),0,30.,250.,downtime=factor)
result['parallel_min_sum_not_makespan']={'response':r,'positions_arbitrary_units':pos,
 'km_per_unit':4.,'travel_matrix':{src+'->'+dst:move_time_hours(f,src,dst) for src in 'AB' for dst in 'CD'},
 'witness':{'chosen':['C','D'],'pairs':[{'from':'B','to':'C','ready_h':.76},{'from':'A','to':'D','ready_h':.76}],
            'total_hours':.76,'unmet':w.metrics['unmet_total']}}

# Identical2h cross travel, but processing high-demandD before low-demandC improves net service.
rad=1.5/math.sqrt(2)
g=physical_fixture({'A':(-rad,0.),'B':(rad,0.),'C':(0.,rad),'D':(0.,-rad)},
                   {'A':25.,'B':25.,'C':10.,'D':24.75})
shocked_g=apply_shock(g,pick_low_income(g,2),10.)
rr=plan_response(g,2,mult=10.,parallel=False,budget_hours=5.)
ww=_assign(shocked_g,_active_sites(shocked_g,('C','D')),0,30.,250.,downtime={'D':.8,'C':.6})
result['serial_order_not_enumerated']={'response':rr,'cross_travel_hours':2.,
 'witness':{'chosen':['C','D'],'timeline':[{'from':'B','to':'D','depart_h':0.,'ready_h':2.},
                                                        {'from':'A','to':'C','depart_h':2.,'ready_h':4.}],
            'total_hours':4.,'unmet':ww.metrics['unmet_total']}}

# Verify old parallel bug is actually fixed on the former equal2h fixture.
same=physical_fixture({'A':(-rad,0.),'B':(rad,0.),'C':(0.,rad),'D':(0.,-rad)},
                      {'A':25.,'B':25.,'C':24.75,'D':24.75})
result['parallel_equal2h_fixed']=plan_response(same,2,mult=10.,parallel=True,budget_hours=2.5)
old_match=physical_fixture({'A':(0.,0.),'B':(3.1,0.),'C':(1.5,0.),'D':(-1.6,0.)},
                          {'A':25.,'B':25.,'C':24.75,'D':24.75})
result['former_greedy_matching_fixed']=plan_response(old_match,2,mult=10.,budget_hours=5.)

cmd=[sys.executable,'-m','src.exp.run_q4_response','--stress-draws','1','--out',str(out/'cli_default')]
p=subprocess.run(cmd,cwd=repo,capture_output=True,env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=90)
result['default_cli']={'returncode':p.returncode,'stderr':p.stderr.decode('utf-8').replace(str(repo),'<REPO>').replace(str(out),'<OUT>')}
# Pruning without downtime can exclude the only useful deadline-feasible relocation.
# All MCH capacities are250, all opening windows09-22; actual travel formula is unchanged.
prune_ds=[District('A','A',1000,.1,.1,100000,.1,.5),
          District('B','B',1000,.1,.1,10000,.1,.5),District('C','C',1000,.1,.1,20000,.1,.5)]
prune_ss=[Site('A','A','candidate_mch','A',33.5,-112.,250,9.,22.),
          *[Site('B'+str(n),'B'+str(n),'candidate_mch','B',lat,-112.,250,9.,22.)
            for n,lat in enumerate([33.9,34.,34.1],1)],
          Site('E','E','candidate_mch','C',33.51,-112.,250,9.,22.)]
prune_inst=Instance(prune_ds,prune_ss,{('A','A'):1.,**{('B','B'+str(n)):1. for n in range(1,4)},('C','E'):1.},
                    {('A',0):100.,('B',0):99.,('C',0):95.},1)
pruned=plan_response(prune_inst,1,mult=2.,budget_hours=1.)
complete=plan_response(prune_inst,1,mult=2.,budget_hours=1.,top_combos=99,top_matchings=99)
intermediate=plan_response(prune_inst,1,mult=2.,budget_hours=1.,top_combos=10,top_matchings=10)
result['topK_pruning']={'default_top3':pruned,'K10':intermediate,'all_combos':complete,
    'travel_from_A':{s.id:move_time_hours(prune_inst,'A',s.id) for s in prune_ss if s.id!='A'},
    'fixture':{'capacity':250,'open_hours':'09-22','demand_before':{'A':100,'B':99,'C':95},
               'shock':['B','C'],'multiplier':2,'coordinates':{s.id:[s.lat,s.lon] for s in prune_ss}},
    'scope':'Unbounded topK heuristic example, not Phoenix measured demand or routes'}
checks={
 'p8_noop_feasible':result['p8_closed_candidate']['feasible_any'],
 'parallel_equal2h_fixed':result['parallel_equal2h_fixed']['best']['total_hours']==2.,
 'former_greedy_matching_fixed':result['former_greedy_matching_fixed']['best']['total_hours']==4.2,
 'default_cli_runs':p.returncode==0,
 'in_place_zero_time':all(m['travel_h']==0 and m['ready_h']==0 for m in result['default_vehicle3_failure']['best']['timeline'] if m['from']==m['to']),
 'one_hour_response_fixed':result['default_vehicle3_one_hour_budget']['best']['unmet']<=true_stay.metrics['unmet_total']+1e-6,
 'parallel_matching_old_case_fixed':r['best']['unmet']<=w.metrics['unmet_total']+1e-6,
 'serial_order_old_case_fixed':rr['best']['unmet']<=ww.metrics['unmet_total']+1e-6,
 'topK_default_misses_better_feasible_plan':pruned['best']['unmet']>complete['best']['unmet'],
}
result['checks']={k:bool(v) for k,v in checks.items()}
assert all(result['checks'].values()),result['checks']
(out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result['checks'],ensure_ascii=True))
