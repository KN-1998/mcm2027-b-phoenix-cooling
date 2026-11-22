"""Matched-input baselines, ablations and sensitivity for the modeler handoff.

python -m src.exp.run_takeover_evidence --out results/takeover_20261120/core
Outputs are conditional visits, not people reached or avoided deaths.
"""
from __future__ import annotations
import argparse
import copy
import csv
import json
from pathlib import Path

from ..mch import runmeta
from ..mch.assign import solve_assignment, solve_assignment_periods
from ..mch.diagnostics import structural_set
from ..mch.dynamic import solve_week_dp
from ..mch.hours import PERIODS, capacity_on_service_day
from ..mch.loaders import load_instance
from ..mch.realnet import build_real_instance
from ..mch.schema import District, Instance, Site
from ..mch.static import _active_sites, _assign, _greedy_fill, solve_static, solve_static_maxmin


def save_json(path, data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


def save_csv(path, rows):
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def brief(sol):
    return {'chosen':','.join(sol.chosen), **sol.metrics}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True)
    a=parser.parse_args(argv);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    runmeta.write(out,vars(a))
    base=load_instance(); baseline=solve_static(base,0); p3=solve_static(base,3)
    districts=[]
    for d in base.districts:
        demand=base.demand[d.id,0];before=baseline.served.get((d.id,0),0);after=p3.served.get((d.id,0),0)
        districts.append({'district_id':d.id,'population_scenario':d.population,
                          'pct65_scenario':d.pct_65plus,'no_vehicle_scenario':d.pct_no_vehicle,
                          'demand_visits':demand,'fixed_only_unmet':demand-before,
                          'p3_unmet':demand-after,'p3_unmet_fraction':(demand-after)/demand if demand else 0})
    save_csv(out/'district_gap.csv',districts)
    save_csv(out/'p3_allocations.csv',p3.allocations)
    frontier=[]
    for p in range(9):
        eff=solve_static(base,p);fair=solve_static_maxmin(base,p)
        frontier.append({'p':p,'efficiency_unmet':eff.metrics['unmet_total_raw'],
                         'maxmin_unmet':fair.metrics['unmet_total_raw'],
                         'efficiency_worst_all':eff.metrics['worst_unmet_ratio_raw'],
                         'efficiency_worst_nonexempt':eff.metrics['worst_unmet_ratio_nonexempt_raw'],
                         'maxmin_worst_all':fair.metrics['worst_unmet_ratio_raw'],
                         'maxmin_worst_nonexempt':fair.metrics['worst_unmet_ratio_nonexempt_raw'],
                         'exempt':','.join(fair.metrics['equity_exempt']),
                         'efficiency_chosen':','.join(eff.chosen),'maxmin_chosen':','.join(fair.chosen)})
    for i,row in enumerate(frontier):
        row['marginal_unmet_reduction']=0 if i==0 else frontier[i-1]['efficiency_unmet']-row['efficiency_unmet']
    save_csv(out/'p_frontier.csv',frontier)
    # OAT: one changed assumption per row; unequal ranges are not an importance ranking.
    rows=[]
    axes={'demand_scale':[.5,.75,1,1.25,1.5,2,3],
          'unsheltered_share':[0,.3,.5,.7,1],
          'max_minutes':[20,25,30,35,45,60],
          'mobile_daily_capacity':[50,100,125,175,250],
          'fixed_daily_capacity':[20,50,100,250]}
    for axis,values in axes.items():
        for value in values:
            inst=copy.deepcopy(base);kw={}
            if axis=='demand_scale':inst.demand={k:v*value for k,v in inst.demand.items()}
            if axis=='unsheltered_share':inst.meta['unsheltered_share']=value
            if axis=='max_minutes':kw['max_minutes']=value
            if axis=='mobile_daily_capacity':
                for s in inst.candidate_sites():s.capacity=value
            if axis=='fixed_daily_capacity':
                for s in inst.fixed_sites():s.capacity=value
            sol=solve_static(inst,3,**kw)
            rows.append({'axis':axis,'value':value,'unmet':sol.metrics['unmet_total_raw'],
                         'worst':sol.metrics['worst_unmet_ratio_raw'],'chosen':','.join(sol.chosen)})
    save_csv(out/'oat.csv',rows)
    flips=[]
    for axis in axes:
        subset=[r for r in rows if r['axis']==axis]
        for prev,cur in zip(subset,subset[1:]):
            if prev['chosen']!=cur['chosen']:
                flips.append({'axis':axis,'sampled_interval':[prev['value'],cur['value']],
                              'old':prev['chosen'],'new':cur['chosen'],
                              'scope':'sampled bracket, not an exact threshold'})
    # Same input, remove period constraints only. This is a supply upper bound.
    act=_active_sites(base,p3.chosen)
    cap={s.id:sum(capacity_on_service_day(s,float(s.capacity or 250),h,0) for h in PERIODS) for s in act}
    dem={d.id:base.demand[d.id,0] for d in base.districts}
    daily=solve_assignment(base,act,0,30,cap,dem)
    ablation={'period_served':sum(p3.served.values()),'pooled_day_served':sum(daily['served'].values()),
              'same_sites':p3.chosen,'interpretation':'Dropping timing constraints gives an optimistic daily-capacity bound, not observed benefit.'}
    save_json(out/'timing_ablation.json',ablation)
    # True minimal hand-check: 19 visits can be served; demand-first greedy traps 9.
    ds=[District('A','A',1,0,0,1,0,0),District('B','B',1,0,0,1,0,0)]
    ss=[Site(k,k,'cooling','A',0,0,10,9,17) for k in ('S1','S2')]
    toy=Instance(ds,ss,{('A','S1'):1,('A','S2'):2,('B','S1'):1},{('A',0):10,('B',0):9},1)
    caph={s.id:{h:10 if h=='day' else 0 for h in PERIODS} for s in ss}
    demh={d.id:{h:toy.demand[d.id,0] if h=='day' else 0 for h in PERIODS} for d in ds}
    lp=solve_assignment_periods(toy,ss,0,30,caph,demh)
    greedy,_,_=_greedy_fill(toy,ss,{'A':10,'B':9},30,{'S1':10,'S2':10})
    assert abs(sum(lp['served'].values())-19)<1e-7 and sum(greedy.values())==10
    save_json(out/'minimal_case.json',{'input':{'A_demand':10,'B_demand':9,'each_capacity':10,
                'links':['A-S1','A-S2','B-S1'],'period':'day'},'hand_solution':'B->S1=9,A->S2=10',
                'lp':lp,'greedy_served':sum(greedy.values()),'evidence_type':'numerical hypothetical case'})
    save_csv(out/'minimal_case_flows.csv',lp['allocations'])
    # Default temporal profile scales all districts similarly: preserve no-gain finding.
    week=solve_week_dp(base,3)
    shock=copy.deepcopy(base)
    for day in (2,3,4):shock.demand['D05',day]*=3
    shocked_week=solve_week_dp(shock,3)
    save_json(out/'weeks.json',{'baseline':week,'same_exogenous_shock_static_and_dynamic':shocked_week,
              'shock_spec':{'district':'D05','days':[2,3,4],'multiplier':3}})
    # Real inventory experiment: every site and candidate uses the same travel proxy.
    inventory=[];calendar=[]
    for mode in ('walk_min','transit_min'):
        inst=build_real_instance(access_mode=mode)
        for p in range(9):
            sol=solve_static(inst,p)
            inventory.append({'access_mode':mode,'p':p,'unmet':sol.metrics['unmet_total_raw'],
                              'chosen':','.join(sol.chosen),'worst':sol.metrics['worst_unmet_ratio_raw']})
        for day in range(7):
            sol=solve_static(inst,3,day=day)
            calendar.append({'access_mode':mode,'day':day,'unmet':sol.metrics['unmet_total_raw'],
                             'chosen':','.join(sol.chosen)})
    save_csv(out/'dated_inventory_sweep.csv',inventory);save_csv(out/'dated_week.csv',calendar)
    save_json(out/'summary.json',{'scope':'Conditional allocation; no visitor-outcome holdout available',
              'baseline':brief(baseline),'p3':brief(p3),'structural_under_given_network':structural_set(base),
              'sampled_site_set_flip_brackets':flips,'timing_ablation':ablation,
              'baseline_week_static':week['static_total_unmet'],'baseline_week_dynamic':week['dynamic_total_unmet'],
              'shock_week_static':shocked_week['static_total_unmet'],'shock_week_dynamic':shocked_week['dynamic_total_unmet']})
    make_figures(out)
    print(json.dumps({'rows_oat':len(rows),'flip_brackets':len(flips),'weekly_gain':week['static_total_unmet']-week['dynamic_total_unmet'],
                      'shock_weekly_gain':shocked_week['static_total_unmet']-shocked_week['dynamic_total_unmet']},ensure_ascii=False))
    return 0


def make_figures(out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    def rows(name):
        with (out/name).open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))
    fig,axes=plt.subplots(1,2,figsize=(10,3.7),layout='constrained')
    frontier=rows('p_frontier.csv')
    axes[0].plot([int(r['p']) for r in frontier],[float(r['efficiency_unmet']) for r in frontier],'o-',label='Efficiency LP')
    axes[0].plot([int(r['p']) for r in frontier],[float(r['maxmin_unmet']) for r in frontier],'s--',label='Max-min LP')
    axes[0].set(xlabel='Active mobile hubs',ylabel='Unmet visits / representative day',title='Capacity and fairness tradeoff')
    axes[0].legend(fontsize=8)
    inventory=rows('dated_inventory_sweep.csv')
    for mode,label in [('walk_min','Walk proxy'),('transit_min','Transit + direct walk proxy')]:
        sub=[r for r in inventory if r['access_mode']==mode]
        axes[1].plot([int(r['p']) for r in sub],[float(r['unmet']) for r in sub],'o-',label=label)
    axes[1].set(xlabel='Active mobile hubs',ylabel='Unmet visits / representative day',title='Dated MAG inventory scenario')
    axes[1].legend(fontsize=8)
    for ax in axes:ax.grid(alpha=.2)
    fig.savefig(out/'frontiers.png',dpi=190);fig.savefig(out/'frontiers.pdf');plt.close(fig)
    gap=rows('district_gap.csv');fig,ax=plt.subplots(figsize=(8,3.5),layout='constrained')
    x=list(range(len(gap)))
    ax.bar([i-.2 for i in x],[float(r['fixed_only_unmet']) for r in gap],.4,label='Existing fixed network')
    ax.bar([i+.2 for i in x],[float(r['p3_unmet']) for r in gap],.4,label='Fixed network + 3 MCH')
    ax.set_xticks(x,[r['district_id'] for r in gap]);ax.set(ylabel='Unmet visits / day',title='Conditional district gaps: synthetic demand and geography')
    ax.legend(fontsize=8);fig.savefig(out/'district_gaps.png',dpi=190);plt.close(fig)


if __name__=='__main__':raise SystemExit(main())
