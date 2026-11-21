"""Official 2026 realized-visit chronological validation and failure reporting."""
from __future__ import annotations
import argparse,csv,hashlib,json
from pathlib import Path
from ..mch import runmeta
from ..mch.empirical import extract_weekly_visits,load_noaa_tmax,attach_week_weather,validate,check_protocol,TRAIN_END

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'资料'/'12_实证补全_2026-11-21'

def csv_write(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True)
    a=p.parse_args(argv);out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    protocol=json.loads((SOURCE/'validation_protocol.json').read_text(encoding='utf-8'))
    check_protocol(protocol)
    raw=extract_weekly_visits(SOURCE/'raw')
    rows=attach_week_weather(raw,load_noaa_tmax(SOURCE/'noaa_2026_phoenix_sky_harbor_daily_summaries.csv'))
    csv_write(out/'weekly_observations.csv',rows)
    result=validate(rows);predictions=result.pop('predictions')
    csv_write(out/'predictions.csv',predictions)
    selected=result['selected_model'];test=result['test_scores'];last=test['last_week']['mae_visits_per_week']
    selected_mae=test[selected]['mae_visits_per_week']
    calibration_rows=[r for r in rows if r['included_full_week'] and r['end_date']<=TRAIN_END.isoformat()]
    max_week=max(calibration_rows,key=lambda r:r['jackson_visits']/r['days'])
    result.update({'protocol':protocol,'target_scope':'One existing 24/7 respite center; calendar-week realized intake visits, not latent unmet demand or mobile capacity',
                   'selected_test_mae_improvement_vs_last_week':last-selected_mae,
                   'selected_beats_last_week_test':selected_mae<last,
                   'test_outcome_action':'Retain selected baseline/forecast only as a descriptive workload benchmark; do not feed it into district latent demand or claim service-coverage validation.',
                   'capacity_assumption_falsification':{
                       'site':'20 W. Jackson St.','week':max_week['start_date']+'/'+max_week['end_date'],
                       'visits':max_week['jackson_visits'],'days':max_week['days'],
                       'calibration_scope':'train only, complete weeks ending no later than 2026-07-26',
                       'mean_realized_visits_per_day':max_week['jackson_visits']/max_week['days'],
                       'at_least_one_day_visits_lower_bound':-(-max_week['jackson_visits']//max_week['days']),
                       'interpretation':'Pigeonhole lower bound on at least one day, not a constant daily capacity estimate and not transferable to other sites/MCH.'},
                   'quality_flags':{'weekly_minus_cumulative_difference_nonzero':[
                       {'week':r['week_id'],'difference':r['jackson_week_minus_cumulative_difference']} for r in rows if r['jackson_week_minus_cumulative_difference']!=0],
                       'source_table_arithmetic_inconsistencies':[
                           {k:r[k] for k in ('week_id','aggregate_week_minus_site_sum','aggregate_season_minus_site_sum','overview_minus_aggregate_week')}
                           for r in rows if r['aggregate_week_minus_site_sum'] or r['aggregate_season_minus_site_sum'] or r['overview_minus_aggregate_week']]},
                   'limitations':['Only four chronological test weeks; serial dependence; no iid confidence interval.',
                                  'One held-out week value was seen during source discovery; retrospective, not fully blinded or prospective.',
                                  'Archive counts may reflect reporting revisions; original release latency unavailable.',
                                  'No district origins, turned-away demand, causal counterfactual or mobile-unit capacity in these data.',
                                  'NOAA natural/climatological dates differ from the planning model 09:00 service day; this submodel uses report calendar weeks.']})
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    # Explicit reconciliation: neither synthetic R01 nor MAG source inventory
    # is silently replaced by the observed Jackson center.
    reconciliation=[]
    for key,name,kind in [('jackson','20 W. Jackson St.','24/7 respite intake visits'),
                          ('justa','Justa Center','extended-hour intake visits'),
                          ('cholla','Cholla Library','heat-staff engagements, not all library visits')]:
        full=calibration_rows
        peak=max(full,key=lambda r:r[key+'_visits']/r['days'])
        reconciliation.append({'site':name,'observed_measure':kind,'peak_full_week_start':peak['start_date'],
            'peak_full_week_end':peak['end_date'],'weekly_reported_count':peak[key+'_visits'],
            'source_pdf':peak['source_pdf'],'source_pdf_page':2,
            'observed_mean_count_per_day':peak[key+'_visits']/7,
            'at_least_one_day_count_lower_bound':-(-peak[key+'_visits']//7),
            'calibration_scope':'train only, complete weeks ending no later than 2026-07-26',
            'not_constant_capacity_estimate':True,
            'mapping_to_processed_R01':'No automatic mapping: R01 location/capacity synthetic, type inspired by official plan',
            'mapping_to_MAG_REAL':('MAG0068/ID68 Cholla Library matched by source name/address; registered hours conflict with official extended operations' if key=='cholla'
                                   else 'No matching Jackson/Justa source row identified in the 50-record snapshot'),
            'capacity_use':('Not a capacity observation: staff engagements omit other library visitors' if key=='cholla'
                            else 'At least one day realized-visit lower bound only; not constant capacity or upper bound'),
            'model_action':'Retain original data; use explicit omitted-site/capacity structural scenario, never copy this count to all fixed sites or MCH'})
    csv_write(out/'capacity_reconciliation.csv',reconciliation)
    paths=sorted(p for p in SOURCE.rglob('*') if p.is_file() and p.suffix.lower() in ('.pdf','.csv','.json','.html'))
    runmeta.write(out,vars(a),{'experiment':'Retrospective chronological validation of realized weekly visits',
                  'empirical_input_sha256':{x.relative_to(ROOT).as_posix():hashlib.sha256(x.read_bytes()).hexdigest() for x in paths}})
    draw(out,rows,predictions,selected)
    print(json.dumps({'selected_model':selected,'test_scores':test,'capacity_lower_bound':result['capacity_assumption_falsification']},ensure_ascii=False))
    return 0

def draw(out,rows,predictions,selected):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    full=[r for r in rows if r['included_full_week']]
    fig,axes=plt.subplots(1,2,figsize=(10.5,3.8),layout='constrained')
    ax=axes[0];dates=[r['end_date'][5:] for r in full]
    ax.plot(range(20),[r['jackson_visits'] for r in full],'o-',color='#164b73',label='Reported Jackson visits')
    ax.axvspan(11.5,15.5,alpha=.12,color='orange',label='Selection block')
    ax.axvspan(15.5,19.5,alpha=.12,color='green',label='Locked test block')
    ax.set_xticks([0,4,8,12,16,19],[dates[i] for i in [0,4,8,12,16,19]])
    ax.set(xlabel='2026 week ending (month-day)',ylabel='Realized intake visits / week',title='Official same-site observations')
    ax.legend(fontsize=7)
    ax=axes[1]
    target=[p for p in predictions if p['split']=='test' and p['model']==selected]
    baseline=[p for p in predictions if p['split']=='test' and p['model']=='last_week']
    x=range(4);ax.plot(x,[p['observed'] for p in target],'ko-',label='Observed')
    ax.plot(x,[p['predicted'] for p in baseline],'s--',label='Last-week baseline')
    ax.plot(x,[p['predicted'] for p in target],'^--',label='Development-selected rule')
    ax.set_xticks(list(x),[p['end_date'][5:] for p in target]);ax.set(xlabel='2026 test week ending',ylabel='Realized intake visits / week',title='No test-based model reselection')
    ax.legend(fontsize=7)
    for ax in axes:ax.grid(alpha=.2)
    fig.savefig(out/'empirical_validation.png',dpi=190);fig.savefig(out/'empirical_validation.pdf');plt.close(fig)

if __name__=='__main__':raise SystemExit(main())
