"""Dated GTFS journeys, independent source-leg audit and matched network contrast.

python -m src.exp.run_gtfs_validation --out results/complete_20261121/gtfs
"""
from __future__ import annotations
import argparse
import copy
import csv
import datetime as dt
import hashlib
import io
import json
import statistics
import zipfile
from pathlib import Path

from ..mch import runmeta
from ..mch.gtfs_routing import Timetable, clock
from ..mch.realnet import build_real_instance
from ..mch.static import solve_static

ROOT=Path(__file__).resolve().parents[2]
DEFAULT=ROOT/'资料/02_降温网络/GTFS/mdb-147-202606160033/mdb-147-202606160033.zip'


def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def csvout(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def independent_leg_audit(archive,itineraries,sample_limit=8):
    """Re-read source strings with separate arithmetic, not the router structs.

    Checks published times and permissions of each chosen ride, then independently
    adds access/transfer/wait/egress to verify the full itinerary is temporally
    feasible. This is feed-record validation, not observed vehicle performance.
    """
    chosen=[];used=set()
    for item in itineraries:
        rides=[leg for leg in item['result']['legs'] if leg['kind']=='scheduled_ride']
        if rides and item['district_id'] not in used:
            chosen.append(item);used.add(item['district_id'])
        if len(chosen)>=sample_limit:break
    if len(chosen)<sample_limit:
        signatures={(x['district_id'],x['site_id'],x['departure']) for x in chosen}
        for item in itineraries:
            key=(item['district_id'],item['site_id'],item['departure'])
            if key not in signatures and any(leg['kind']=='scheduled_ride' for leg in item['result']['legs']):
                chosen.append(item);signatures.add(key)
            if len(chosen)>=sample_limit:break
    wanted={leg['trip_id'].split('@')[0] for item in chosen for leg in item['result']['legs']
            if leg['kind'] in ('scheduled_ride','headway_bound_ride')}
    records={tid:[] for tid in wanted}
    with zipfile.ZipFile(archive) as z:
        trip_sources={r['trip_id']:r for r in csv.DictReader(io.TextIOWrapper(z.open('trips.txt'),encoding='utf-8-sig')) if r['trip_id'] in wanted}
        target_date=dt.date.fromisoformat(chosen[0]['result']['service_date']) if chosen else None
        datecode=target_date.strftime('%Y%m%d') if target_date else ''
        active=set()
        if 'calendar.txt' in z.namelist():
            for row in csv.DictReader(io.TextIOWrapper(z.open('calendar.txt'),encoding='utf-8-sig')):
                if row['start_date']<=datecode<=row['end_date'] and row[target_date.strftime('%A').lower()]=='1':active.add(row['service_id'])
        if 'calendar_dates.txt' in z.namelist():
            for row in csv.DictReader(io.TextIOWrapper(z.open('calendar_dates.txt'),encoding='utf-8-sig')):
                if row['date']==datecode:
                    if row['exception_type']=='1':active.add(row['service_id'])
                    elif row['exception_type']=='2':active.discard(row['service_id'])
        for r in csv.DictReader(io.TextIOWrapper(z.open('stop_times.txt'),encoding='utf-8-sig')):
            if r['trip_id'] in wanted:records[r['trip_id']].append(r)
    for rows in records.values():rows.sort(key=lambda r:int(r['stop_sequence']))
    def rawseconds(value):
        values=[int(x) for x in value.split(':')]
        return values[0]*60*60+values[1]*60+values[2]
    audits=[]
    for item in chosen:
        result=item['result'];now=result['departure_seconds'];checks=[]
        for leg in result['legs']:
            kind=leg['kind']
            if kind in ('access_walk_proxy','egress_walk_proxy'):now+=leg['seconds']
            elif kind=='transfer_walk_and_buffer':
                assert leg['elapsed_seconds']>=leg['walk_seconds']
                assert leg['elapsed_seconds']>=leg['source_min_transfer_seconds']
                now+=leg['elapsed_seconds']
            else:
                rows=records[leg['trip_id'].split('@')[0]]
                source_trip=trip_sources[leg['trip_id'].split('@')[0]]
                assert source_trip['service_id'] in active and source_trip['route_id']==leg['route_id']
                a=rows[leg['from_sequence_index']];b=rows[leg['to_sequence_index']]
                assert a['stop_id']==leg['from_stop'] and b['stop_id']==leg['to_stop']
                assert a.get('pickup_type','') in ('','0') and b.get('drop_off_type','') in ('','0')
                source_dep,source_arr=rawseconds(a['departure_time']),rawseconds(b['arrival_time'])
                assert leg['departure_seconds']+1e-7>=now
                if kind=='scheduled_ride' and '@' not in leg['trip_id']:
                    assert source_dep==leg['departure_seconds'] and source_arr==leg['arrival_seconds']
                else:
                    assert abs((leg['arrival_seconds']-leg['departure_seconds'])-(source_arr-source_dep))<1e-7
                checks.append({'trip':leg['trip_id'],'route':leg['route_id'],'from_stop':a['stop_id'],'to_stop':b['stop_id'],
                               'active_service_id':source_trip['service_id'],'service_date':result['service_date'],
                               'published_departure':a['departure_time'],'published_arrival':b['arrival_time'],
                               'published_ride_seconds':source_arr-source_dep,'boarding_wait_seconds':leg['departure_seconds']-now,
                               'permission_checked':True})
                now=leg['arrival_seconds']
        assert abs(now-result['arrival_seconds'])<1e-6
        audits.append({'district_id':item['district_id'],'site_id':item['site_id'],'departure':item['departure'],
                       'duration_minutes':result['duration_minutes'],'independent_arrival_seconds':now,
                       'full_itinerary_time_residual_seconds':now-result['arrival_seconds'],'ride_checks':checks})
    return audits


def source_trip_examples(archive,timetable):
    """Examples are derived from raw strings, not a claim these are optimal OD."""
    regular=[trip for trip in timetable.trips if trip.frequency is None]
    overnight=next((trip for trip in regular if any(st.arrival>=86400 for st in trip.times)),None)
    ordinary=next((trip for trip in regular if trip.id=='23183006'),regular[0] if regular else None)
    frequency=next(iter(timetable.frequency_templates),None)
    wanted={trip.id for trip in (ordinary,overnight,frequency) if trip is not None};raw={tid:[] for tid in wanted}
    with zipfile.ZipFile(archive) as z:
        for row in csv.DictReader(io.TextIOWrapper(z.open('stop_times.txt'),encoding='utf-8-sig')):
            if row['trip_id'] in wanted:raw[row['trip_id']].append(row)
    def sec(clock):
        hour,minute,second=map(int,clock.split(':'));return hour*3600+minute*60+second
    examples=[]
    for tid,rows in raw.items():
        rows.sort(key=lambda r:int(r['stop_sequence']));a,b=rows[0],rows[-1]
        examples.append({'trip_id':tid,'stops':len(rows),'first_stop':a['stop_id'],'last_stop':b['stop_id'],
                         'first_departure_string':a['departure_time'],'last_arrival_string':b['arrival_time'],
                         'raw_elapsed_seconds':sec(b['arrival_time'])-sec(a['departure_time']),
                         'contains_after_24h':any(sec(r['arrival_time'])>=86400 for r in rows),
                         'is_frequency_template':frequency is not None and tid==frequency.id})
    # Real SkyTrain template: 09:01 arrival at first platform; assume at most
    # its 270-second headway wait, then preserve the template running time.
    if frequency is not None:
        freq_example=next(x for x in examples if x['is_frequency_template'])
        freq_example['headway_bound_hand_example']={
            'ready_at_first_stop':'09:01:00','assumed_wait_seconds':frequency.frequency[2],
            'bound_departure':clock(9*3600+60+frequency.frequency[2]),
            'bound_last_arrival':clock(9*3600+60+frequency.frequency[2]+freq_example['raw_elapsed_seconds']),
            'not_a_published_fixed_departure':True}
    return examples


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',default=str(DEFAULT));parser.add_argument('--date',default='2026-07-20')
    parser.add_argument('--departures',default='09:00:00,13:00:00,17:00:00')
    parser.add_argument('--max-boardings',type=int,default=3);parser.add_argument('--horizon-minutes',type=float,default=240)
    parser.add_argument('--frequency-policy',choices=('headway_bound','exclude_nonexact','error'),default='headway_bound')
    parser.add_argument('--city-operations',action='store_true',
                        help='Use the explicit City operating-site correction layer; keep separate from the MAG-only experiment')
    parser.add_argument('--out',required=True);args=parser.parse_args(argv)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    timetable=Timetable(args.archive,args.date,frequency_policy=args.frequency_policy)
    inst=build_real_instance(access_mode='transit_min',start_date=args.date)
    if args.city_operations:
        from ..mch.realnet import apply_city_operating_corrections
        corrected=apply_city_operating_corrections(inst)
        if corrected is not None:inst=corrected
    destinations={s.id:(s.lat,s.lon) for s in inst.sites if s.kind in ('cooling','respite','candidate_mch')}
    depart=[x.strip() for x in args.departures.split(',')]
    if not depart:raise ValueError('at least one departure is required')
    runmeta.write(out,vars(args),{'gtfs_dependency':timetable.metadata,
                                'scope':'Dated published-transit plus proxy walking; no observed travel-time validation.'})
    rows=[];itineraries=[];by_depart={d:{} for d in depart}
    for d in inst.districts:
        for time in depart:
            result=timetable.route((d.lat,d.lon),destinations,time,max_boardings=args.max_boardings,horizon_minutes=args.horizon_minutes)
            for sid,r in result.items():
                proxy=inst.access[d.id,sid]
                rows.append({'district_id':d.id,'site_id':sid,'service_date':args.date,'departure':time,
                             'duration_minutes':r['duration_minutes'],'proxy_minutes':proxy,
                             'routing_minus_proxy_minutes':r['duration_minutes']-proxy,'mode':r['mode'],
                             'boardings':r['boardings'],'contains_headway_bound':any(x['kind']=='headway_bound_ride' for x in r['legs']),
                             'arrival_clock_service_day':r['arrival_time']})
                itineraries.append({'district_id':d.id,'site_id':sid,'departure':time,'result':r})
                by_depart[time][d.id,sid]=r['duration_minutes']
    csvout(out/'od_by_departure.csv',rows);dump(out/'itineraries.json',itineraries)
    frequency_sensitivity=[]
    affected=[x for x in itineraries if any(leg['kind']=='headway_bound_ride' for leg in x['result']['legs'])]
    if affected:
        without=copy.copy(timetable);without.trips=[trip for trip in timetable.trips if trip.frequency is None]
        without.frequency_policy='exclude_nonexact';query_cache={}
        locations={d.id:(d.lat,d.lon) for d in inst.districts}
        for item in affected:
            key=(item['district_id'],item['departure'])
            if key not in query_cache:
                query_cache[key]=without.route(locations[key[0]],destinations,key[1],max_boardings=args.max_boardings,horizon_minutes=args.horizon_minutes)
            old=item['result']['duration_minutes'];new=query_cache[key][item['site_id']]['duration_minutes']
            assert new+1e-7>=old
            frequency_sensitivity.append({'district_id':key[0],'departure':key[1],'site_id':item['site_id'],
                                          'headway_bound_minutes':old,'exclude_nonexact_minutes':new,
                                          'difference_minutes':new-old,'changes_30min_classification':(old<=30)!=(new<=30)})
    dump(out/'frequency_policy_sensitivity.json',frequency_sensitivity)
    audits=independent_leg_audit(args.archive,itineraries)
    dump(out/'independent_source_leg_audits.json',audits)
    dump(out/'source_trip_hand_examples.json',source_trip_examples(args.archive,timetable))
    # Same fixed/candidate inventory, demand, capacities, opening and threshold.
    # The sole changed field is the passenger travel-time matrix.
    contrasts=[]
    cases={'distance_speed_proxy':dict(inst.access),**by_depart}
    median={};maximum={};percentile=[]
    for d in inst.districts:
        for sid in destinations:
            values=[by_depart[time][d.id,sid] for time in depart]
            median[d.id,sid]=statistics.median(values);maximum[d.id,sid]=max(values)
            percentile.append({'district_id':d.id,'site_id':sid,'sampled_departures':len(values),
                               'minimum_minutes':min(values),'median_minutes':statistics.median(values),
                               'maximum_minutes':max(values)})
    cases['sampled_median']=median;cases['sampled_maximum']=maximum
    for case,access in cases.items():
        local=copy.deepcopy(inst);local.access=access
        for p in (0,1,2,3,4,7,8):
            sol=solve_static(local,p)
            contrasts.append({'access_case':case,'p':p,'unmet_visits':sol.metrics['unmet_total_raw'],
                              'worst_unmet_fraction':sol.metrics['worst_unmet_ratio_raw'],
                              'chosen':','.join(sol.chosen),'threshold_minutes':30})
    csvout(out/'sampled_departure_summary.csv',percentile);csvout(out/'matched_inventory_siting.csv',contrasts)
    differences=[r['routing_minus_proxy_minutes'] for r in rows]
    link_flip=sum((r['duration_minutes']<=30)!=(r['proxy_minutes']<=30) for r in rows)
    summary={'evidence_type':'published timetable routing plus independent source-record and numerical validation',
             'not_observed_passenger_travel_validation':True,'feed':timetable.metadata,
             'network_layer':'city_operating_corrections_on_MAG' if args.city_operations else 'MAG_source_inventory_only',
             'od_rows':len(rows),'districts':len(inst.districts),'indoor_and_candidate_destinations':len(destinations),
             'departures':depart,'transit_journeys_chosen':sum(r['mode']!='direct_walk_proxy' for r in rows),
             'headway_bound_journeys_chosen':sum(r['contains_headway_bound'] for r in rows),
             'nonexact_exclusion_changed_30min_links':sum(r['changes_30min_classification'] for r in frequency_sensitivity),
             'routing_minus_proxy_minutes':{'median':statistics.median(differences),'min':min(differences),'max':max(differences)},
             'links_whose_30min_classification_changes':link_flip,
             'independent_source_audits':len(audits),'maximum_itinerary_time_residual_seconds':max((abs(r['full_itinerary_time_residual_seconds']) for r in audits),default=None),
             'matched_siting_p3':[r for r in contrasts if r['p']==3],
             'scope':'Earliest arrival over bounded boardings/horizon, except nonexact headway service uses declared waiting bound. Walking and representative origins remain assumptions. Departure quantiles describe selected departure clocks, not a probability distribution or empirical error.',
             'input_sha256':{Path(args.archive).relative_to(ROOT).as_posix() if Path(args.archive).is_relative_to(ROOT) else str(args.archive):timetable.metadata['archive_sha256']}}
    dump(out/'summary.json',summary)
    make_figure(out,rows,contrasts,args.city_operations)
    print(json.dumps({k:summary[k] for k in ('od_rows','transit_journeys_chosen','links_whose_30min_classification_changes','independent_source_audits')},ensure_ascii=False))
    return 0


def make_figure(out,rows,contrasts,city_layer):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,3.8),layout='constrained')
    axes[0].scatter([r['proxy_minutes'] for r in rows],[r['duration_minutes'] for r in rows],s=9,alpha=.35)
    limit=max(max(r['proxy_minutes'],r['duration_minutes']) for r in rows)
    axes[0].plot([0,limit],[0,limit],color='grey',linewidth=1)
    axes[0].set(xlabel='Distance-speed proxy (minutes)',ylabel='GTFS + assumed walking (minutes)',
                title='Model comparison; not observed error')
    cases=['distance_speed_proxy','09:00:00','13:00:00','17:00:00']
    p3={r['access_case']:r['unmet_visits'] for r in contrasts if r['p']==3}
    axes[1].bar(range(4),[p3[k] for k in cases],color=['#7096bb','#d28762','#d28762','#d28762'])
    axes[1].set_xticks(range(4),['Proxy','GTFS 09h','GTFS 13h','GTFS 17h'],rotation=15)
    axes[1].set(ylabel='Conditional unmet visits/day',title='Same inventory and demand; p=3')
    layer='City operating correction layer' if city_layer else 'MAG source inventory only'
    fig.suptitle(layer+' | 2026-07-20 | <=3 boardings, 240-minute transit horizon',fontsize=10)
    for ax in axes:ax.grid(alpha=.15,axis='y')
    fig.savefig(out/'routing_structure.png',dpi=190);fig.savefig(out/'routing_structure.pdf');plt.close(fig)


if __name__=='__main__':raise SystemExit(main())
