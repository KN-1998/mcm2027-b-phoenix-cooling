"""Explicit city-programme corrections, staffing and nonanticipative cost plans."""
from __future__ import annotations
import argparse,copy,csv,json
from pathlib import Path
from ..mch import runmeta
from ..mch.loaders import load_instance
from ..mch.realnet import build_real_instance,apply_city_operating_corrections
from ..mch.static import solve_static
from ..mch.operations import annual_operating_envelope,operational_status
from ..mch.policy import COST,plan_investment,plan_robust_investment,scenario_evaluator
from .run_q5_plan import HEAT

def csvout(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True)
    a=parser.parse_args(argv);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    runmeta.write(out,vars(a))
    original=build_real_instance(access_mode='transit_min')
    full=apply_city_operating_corrections(original)
    hours_only=copy.deepcopy(full)
    hours_only.sites=[s for s in hours_only.sites if not s.id.startswith('CITY_')]
    inventory=[]
    for label,inst in [('MAG_registered',original),('city_Cholla_hours_only',hours_only),('city_hours_and_two_omitted_sites',full)]:
        for p in range(9):
            sol=solve_static(inst,p)
            inventory.append({'scenario':label,'p':p,'fixed_inventory_rows':len(inst.fixed_sites()),
                              'unmet':sol.metrics['unmet_total_raw'],'chosen':','.join(sol.chosen),
                              'worst_all':sol.metrics['worst_unmet_ratio_raw']})
    csvout(out/'official_inventory_contrast.csv',inventory)
    cap_rows=[]
    # Train-only site intake gives lower bounds on at least one day's visits.
    # The scenario ceilings below are not estimated physical capacities.
    for jackson in (472,500,750,1000):
        for justa in (169,200,300):
            inst=apply_city_operating_corrections(original,jackson_capacity=jackson,justa_capacity=justa)
            sol=solve_static(inst,3)
            cap_rows.append({'jackson_daily_ceiling_assumed':jackson,'justa_daily_ceiling_assumed':justa,
                'unmet':sol.metrics['unmet_total_raw'],'chosen':','.join(sol.chosen),
                'source_scope':'2026 published programme; ceilings assumed, not observed constant throughput'})
    csvout(out/'added_site_capacity_sensitivity.csv',cap_rows)
    operating=[]
    for label in ('assumed_fully_staffed','mobile_staff_09_17','mobile_power_loss_MCH3','mobile_permit_loss_MCH3'):
        inst=load_instance()
        if label=='mobile_staff_09_17':
            for s in inst.candidate_sites():s.extra['staffed_windows_by_day']={'0':[[9,17]]}
        if label in ('mobile_power_loss_MCH3','mobile_permit_loss_MCH3'):
            key='power_by_day' if 'power' in label else 'permit_by_day'
            next(s for s in inst.candidate_sites() if s.id=='MCH-3').extra[key]={'0':False}
        sol=solve_static(inst,3)
        operating.append({'scenario':label,'unmet':sol.metrics['unmet_total_raw'],'chosen':','.join(sol.chosen)})
    csvout(out/'operational_constraint_contrast.csv',operating)
    dump(out/'operational_input_status.json',[operational_status(s,0) for s in load_instance().candidate_sites()])
    profiles={
        'low':dict(operating_days=90,open_hours=10,people_on_duty=2,hourly_wage=20,payroll_multiplier=1.2,
                   maintenance_and_insurance=8000),
        'base':dict(operating_days=150,open_hours=10,people_on_duty=2,hourly_wage=25,payroll_multiplier=1.3,
                    maintenance_and_insurance=10000),
        'high':dict(operating_days=180,open_hours=10,people_on_duty=2,hourly_wage=35,payroll_multiplier=1.45,
                    maintenance_and_insurance=15000)}
    envelopes={}
    for name,kwargs in profiles.items():
        envelopes[name]=annual_operating_envelope(**kwargs,electricity_kwh_per_hour=5,
            electricity_usd_per_kwh=.2,consumables_per_visit=.5,visits_per_day=250,storage=0)
    dump(out/'operating_cost_envelopes.json',{'profiles':envelopes,
        'historical_context':'2026 Arizona wage floor15.15 from official release, not future MCH wage or law advice; all chosen staffing/wage/energy/consumable values ASSUME.',
        'not_used_as_mobile_unit_quotes':{'CBI_2026_requested_programme_max':2600000,'Justa_requested_programme_max':130000},
        'contract_scope':'City Council File26-0336 request; supportive services/fixed programmes, not observed expenditure or MCH unit cost.'})
    base=load_instance()
    service_tables={name:scenario_evaluator(base,path) for name,path in HEAT.items()}
    plans={};rows=[]
    for name,envelope in envelopes.items():
        costs=dict(COST);costs['hub_ops']=envelope['total']
        for annual_budget in (2_000_000,4_000_000):
            budget=[annual_budget]*5
            robust=plan_robust_investment(base,budget,list(HEAT.values()),p_start=2,p_max=8,costs=costs,
                                          scenario_evaluators=list(service_tables.values()))
            plans[f'{name}/{annual_budget}']=robust
            for index,(heat_name,path) in enumerate(HEAT.items()):
                oracle=plan_investment(base,budget,path,p_start=2,p_max=8,costs=costs,evaluator=service_tables[heat_name])
                rolling=plan_investment(base,budget,path,p_start=2,p_max=8,costs=costs,strategy='rolling',evaluator=service_tables[heat_name])
                actual=robust['fixed_plan_performance_by_path'][index]['weighted_unmet_visits']
                rows.append({'cost_profile':name,'heat_path':heat_name,'annual_budget':annual_budget,'annual_hub_ops_assumed':envelope['total'],
                             'clairvoyant_dp_unmet':oracle['summary']['weighted_unmet_visits'],
                             'current_heat_rolling_unmet':rolling['summary']['weighted_unmet_visits'],
                             'fixed_robust_plan_unmet_on_path':actual,
                             'robust_rectangular_upper_bound':robust['summary']['weighted_unmet_visits'],
                             'robust_plan_all_budgets_feasible':robust['summary']['all_within_budget']})
    csvout(out/'nonanticipative_plan_comparison.csv',rows);dump(out/'robust_plan_details.json',plans)
    dump(out/'summary.json',{'scope':'Matched conditional planning; official published schedules and intake counts do not validate latent district demand or actual deployment.',
        'city_overlay':full.meta['city_operating_overlay'],'inventory_scenarios':3,'added_capacity_scenarios':len(cap_rows),
        'staffing_scenarios':len(operating),'robust_cost_profiles':list(envelopes),'annual_budget_scenarios':[2000000,4000000],
        'nonanticipative_definition':'One ex-ante action sequence; year/stock/budget known, future heat not used; rectangular annual maxima bound every supplied heat path.',
        'information_difference':'clairvoyant DP knows full heat; rolling sees current year heat; robust does not. Do not attribute differences solely to algorithm quality.'})
    print('City/operations/cost scenarios complete',flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
