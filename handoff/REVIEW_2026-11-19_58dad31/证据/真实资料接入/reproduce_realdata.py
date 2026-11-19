"""Read-only reproduction of five real-data integration issues at 58dad31d0faf.

Usage: python reproduce_realdata.py --repo PATH_TO_REPOSITORY --out OUTPUT_DIR
Writes only to --out and temporary input fixtures; never edits model/data files.
Dependencies: repository runtime requirements (NumPy/SciPy).
"""
from __future__ import annotations
import argparse,csv,hashlib,json,sys,tempfile
from pathlib import Path

def read_csv(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();repo=a.repo.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(repo))
    from src.mch import realnet
    from src.mch.loaders import load_instance
    from src.mch.incoming import apply_incoming
    from src.mch.runmeta import input_hashes
    from src.mch.static import solve_static

    source_paths=['src/mch/realnet.py','src/mch/incoming.py','src/mch/runmeta.py',
        'src/mch/static.py','src/mch/demand.py','src/mch/loaders.py','src/mch/schema.py',
        '资料/02_降温网络/MAG/phoenix_2026_public_view_sites.csv',
        '资料/02_降温网络/MAG/derived/phoenix_2026_public_view_sites.csv',
        '资料/08_原始摘录/zcta_to_district.json',
        '资料/04_人口与地理/acs2024_5yr_phoenix_zcta_raw.json']
    source_paths += ['data/processed/'+n for n in ['districts.csv','sites.csv','access.csv','demand.csv']]
    source_paths += [p.relative_to(repo).as_posix() for p in (repo/'data/incoming').glob('*') if p.is_file()]
    before={p:sha(repo/p) for p in source_paths}
    raw=read_csv(repo/'资料/02_降温网络/MAG/phoenix_2026_public_view_sites.csv')
    cooling=[r for r in raw if r['HeatRelief_Type']=='Cooling Center']
    century=next(r for r in raw if 'Century Library' in r['Location'])
    calendar={'cooling_records':len(cooling),
        'cooling_sunday_blank_clock_pair':sum(not r['SundayOpen'] and not r['SundayClose'] for r in cooling),
        'century_original':{k:century[k] for k in ['MondayOpen','MondayClose','TuesdayOpen','TuesdayClose','SundayOpen','SundayClose','Start_Date','End_Date']},
        'century_model_daily_hours':list(realnet._hours(century)),
        'note':'Blank weekday fields are unknown, not independently proven closed; the loader nevertheless repeats a daily min/max envelope.'}

    base=load_instance(access_mode='transit_min')
    real=realnet.build_real_instance(access_mode='transit_min')
    diffs=[]
    for d in base.districts:
        for s in base.candidate_sites():
            x,y=base.access[(d.id,s.id)],real.access[(d.id,s.id)]
            diffs.append({'district':d.id,'site':s.id,'base_stop_proxy_min':x,
                'realnet_linear_proxy_min':y,'difference_min':y-x})
    diffs.sort(key=lambda r:abs(r['difference_min']),reverse=True)
    p3=solve_static(real,3)
    for d in base.districts:
        for s in base.candidate_sites():real.access[(d.id,s.id)]=base.access[(d.id,s.id)]
    controlled=solve_static(real,3)
    d10=next(d for d in base.districts if d.id=='D10')
    mch8=next(s for s in base.candidate_sites() if s.id=='MCH-8')
    direct=realnet._hav(d10.lat,d10.lon,mch8.lat,mch8.lon)*realnet.DETOUR/realnet.SPEED['walk_min']*60
    transit={'largest_candidate_proxy_changes':diffs[:5],
        'p3_all_linear':{'unmet':p3.metrics['unmet_total'],'chosen':p3.chosen},
        'p3_retain_base_candidate_proxy':{'unmet':controlled.metrics['unmet_total'],'chosen':controlled.chosen},
        'nearby_direct_walk_counterexample':{'district':'D10','site':'MCH-8',
            'district_coords':[d10.lat,d10.lon],'site_coords':[mch8.lat,mch8.lon],
            'direct_walk_proxy_min':round(direct,3),'base_forced_stop_proxy_min':base.access[('D10','MCH-8')]},
        'note':'Both implementations are proxies. The baseline stop proxy is not a genuine scheduled path; it omits the direct-walk alternative. Retaining it above isolates the traffic-axis confound, not a claim that it is ground truth.'}

    with tempfile.TemporaryDirectory() as td:
        temp=Path(td)
        (temp/'sites_mag.csv').write_text('site_id,capacity\nC01,100\n',encoding='utf-8')
        inst=load_instance();before_total=sum(v for (d,day),v in inst.demand.items() if day==0)
        apply_incoming(inst,temp,rebuild_derived=True)
        after_total=sum(v for (d,day),v in inst.demand.items() if day==0)
    with tempfile.TemporaryDirectory() as td:
        temp=Path(td)
        (temp/'acs_districts.csv').write_text('district_id,population\nD01,150776\n',encoding='utf-8')
        (temp/'demand_observed.csv').write_text('district_id,day,demand_visits\nD01,0,123\n',encoding='utf-8')
        inst=apply_incoming(load_instance(),temp,rebuild_derived=True)
        observed={'provided_D01_day0':123,'result_D01_day0':inst.demand[('D01',0)],'log':inst.meta['incoming']}
    rebuild={'capacity_only_C01_50_to_100':{'daily_demand_before':before_total,'daily_demand_after':after_total},
        'observed_demand_overwritten':observed,
        'note':'These cases explicitly enable rebuild_derived=True; the default loader does not enable rebuilding.'}

    mapping=json.loads((repo/'资料/08_原始摘录/zcta_to_district.json').read_text(encoding='utf-8'))
    acs=json.loads((repo/'资料/04_人口与地理/acs2024_5yr_phoenix_zcta_raw.json').read_text(encoding='utf-8'))
    used={}
    for d,r in mapping.items():
        for z in r['zctas']:used.setdefault(z,[]).append(d)
    mapping_check={'incoming_acs_rows':len(read_csv(repo/'data/incoming/acs_districts.csv')),
        'reused_whole_zctas':{z:ds for z,ds in used.items() if len(ds)>1},
        'mapped_district_population_sum':sum(r['pop'] for r in mapping.values()),
        'no_vehicle_percent':{d:{'draft':r['no_veh_pct'],'household_denominator_correct':100*sum(acs['data']['86000US'+z]['B08201']['estimate']['B08201002'] for z in r['zctas'])/sum(acs['data']['86000US'+z]['B08201']['estimate']['B08201001'] for z in r['zctas'])} for d,r in mapping.items()},
        'note':'This mapping JSON is a draft, not loaded by the current solver; income medians cannot be combined as population-weighted medians.'}

    original_mag=realnet.MAG_CSV
    hashes_before=input_hashes()
    original_p0=solve_static(realnet.build_real_instance(),0).metrics['unmet_total']
    try:
        with tempfile.TemporaryDirectory() as td:
            altered=Path(td)/'mag_fixture.csv'
            with altered.open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(raw[0]));w.writeheader()
                w.writerows(r for r in raw if r['HeatRelief_Type']!='Cooling Center')
            realnet.MAG_CSV=altered
            alternate_p0=solve_static(realnet.build_real_instance(),0).metrics['unmet_total']
            hashes_after=input_hashes()
    finally:realnet.MAG_CSV=original_mag
    hash_check={'hashed_inputs_identical_after_alternate_MAG_fixture':hashes_before==hashes_after,
        'original_p0_unmet':original_p0,'fixture_without_cooling_p0_unmet':alternate_p0,
        'recorded_input_names':sorted(hashes_before),
        'actual_MAG_repository_path':'资料/02_降温网络/MAG/phoenix_2026_public_view_sites.csv',
        'note':'Only an in-memory source-path override to a temporary CSV is used; no repository file is edited.'}
    result={'reviewed_commit':'58dad31d0faf75a5a5742dcea47c314a1ac43fe9',
        'source_hashes_sha256':before,
        'calendar_envelope':calendar,'traffic_axis_confound':transit,
        'rebuild_order_and_calibration':rebuild,'zcta_mapping_draft':mapping_check,
        'MAG_input_hash_omission':hash_check,
        'MAG_alias_records_equal_to_preserved_derived':raw==read_csv(repo/'资料/02_降温网络/MAG/derived/phoenix_2026_public_view_sites.csv'),
        'repository_input_files_unchanged':all(sha(repo/p)==digest for p,digest in before.items())}
    assert result['repository_input_files_unchanged']
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'five_cases_completed':True,'repository_input_files_unchanged':True,
        'calendar_daily_envelope':calendar['century_model_daily_hours'],
        'p3_unmet_linear_and_controlled':[p3.metrics['unmet_total'],controlled.metrics['unmet_total']],
        'capacity_only_demand_before_after':[before_total,after_total],
        'MAG_omission_changes_result_with_same_hashes':original_p0!=alternate_p0 and hashes_before==hashes_after},ensure_ascii=True))

if __name__=='__main__':main()
