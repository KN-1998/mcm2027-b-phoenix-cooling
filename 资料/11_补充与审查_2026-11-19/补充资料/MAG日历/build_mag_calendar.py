"""Conservative calendar normalization; source attributes remain unchanged.

Run: python build_mag_calendar.py
No network, model change, capacity imputation, or weekday/holiday extrapolation.
"""
from __future__ import annotations
import argparse,collections,datetime as dt,hashlib,json,re
from pathlib import Path

DAYS=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
HOLIDAYS=['MemorialDay','Juneteenth','IndependenceDay','LaborDay','ColumbusDay']
URL='https://services1.arcgis.com/MdyCMZnX1raZ7TS3/arcgis/rest/services/HRN_Public_view/FeatureServer/0/query?where=1%3D1&outFields=%2A&returnGeometry=true&outSR=4326&f=pjson'
SNAPSHOT='2026-11-18'

def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def blank(v):return v is None or isinstance(v,str) and not v.strip()
def missingness(a,k):
    if k not in a:return 'key_absent'
    if a[k] is None:return 'null'
    if isinstance(a[k],str) and not a[k].strip():return 'blank_string'
    return 'value'
def minute(v):
    if not isinstance(v,str):return None
    m=re.fullmatch(r'\s*(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*',v,re.I)
    if not m:return None
    h=int(m[1]);n=int(m[2] or 0)
    if not 1<=h<=12 or not 0<=n<60:return None
    return (h%12+(12 if m[3].upper()=='PM' else 0))*60+n
def interval(op,cl):
    a,b=minute(op),minute(cl)
    if a is None or b is None:return None
    # Equal clocks are ambiguous: do not infer 24-hour opening.
    if a==b:return None
    return {'open_minute_local':a,'close_minute_local':b,'crosses_midnight':b<a}
def weekday(a,day):
    op,cl=a.get(day+'Open'),a.get(day+'Close')
    out={'open_raw':op,'close_raw':cl,
         'open_missingness':missingness(a,day+'Open'),
         'close_missingness':missingness(a,day+'Close')}
    if any(isinstance(x,str) and x.strip().lower()=='closed' for x in [op,cl]):
        out['status']='closed_explicit' if all(blank(x) or str(x).strip().lower()=='closed' for x in [op,cl]) else 'conflicting_closed_and_time'
    elif blank(op) and blank(cl):out['status']='unknown_blank_pair'
    elif blank(op) or blank(cl):out['status']='unknown_incomplete_pair'
    elif (iv:=interval(op,cl)) is not None:out.update(status='open_clock_pair',**iv)
    else:out['status']='unknown_unparsed_or_equal_pair'
    return out
def holiday(a,k):
    raw=a.get(k);out={'raw':raw,'missingness':missingness(a,k)}
    if blank(raw):out['status']='unknown_blank'
    elif str(raw).strip().lower()=='closed':out['status']='closed_explicit'
    elif str(raw).strip().lower()=='regular hours':out['status']='inherit_selected_weekday'
    else:
        parts=re.split(r'\s*[-–—]\s*',str(raw).strip())
        iv=interval(*parts) if len(parts)==2 else None
        if iv is None:out['status']='unknown_unparsed_special_hours'
        else:out.update(status='open_special_clock_pair',**iv)
    return out
def normalize(f):
    a=f['attributes'];g=f.get('geometry',{})
    return {'objectid':a.get('OBJECTID'),'globalid':a.get('globalid'),
        'city':a.get('City'),'source_year':a.get('Year'),
        'site_name':a.get('Location'),'service_type':a.get('HeatRelief_Type'),
        'longitude':g.get('x'),'latitude':g.get('y'),'crs':'EPSG:4326',
        'start_date_raw':a.get('Start_Date'),'end_date_raw':a.get('End_Date'),
        'active_raw':a.get('Active'),'general_hours_raw':a.get('Hours'),'note_raw':a.get('Note'),
        'weekday_rules':{day:weekday(a,day) for day in DAYS},
        'holiday_rules':{k:holiday(a,k) for k in HOLIDAYS},
        'capacity_visits_per_day':None,'capacity_status':'not_supplied_by_source',
        'raw_attributes':a,'raw_geometry':g}

def resolve_date(record,date_iso,holiday_field=None,holiday_check_complete=False):
    """Return a source-clock rule without assuming missing cells mean closed.

    Caller must identify holiday observance. No automatic holiday-date mapping or
    timezone/transport calculation is implied. Outside posted date range is only
    a source-range flag, not independent proof of actual operation/closure.
    """
    day=dt.date.fromisoformat(date_iso)
    selected=DAYS[day.weekday()]
    out={'date':date_iso,'weekday':selected,'source_year':record['source_year'],
         'capacity_visits_per_day':None,'capacity_status':'not_supplied_by_source'}
    start,end=record.get('start_date_raw'),record.get('end_date_raw')
    if not start or not end:return {**out,'status':'unknown_missing_source_date_range'}
    try:lo,hi=dt.date.fromisoformat(start),dt.date.fromisoformat(end)
    except (TypeError,ValueError):return {**out,'status':'unknown_unparsed_source_date_range'}
    if not lo<=day<=hi:return {**out,'status':'outside_posted_source_date_range'}
    if holiday_field is not None:
        if holiday_field not in HOLIDAYS:raise ValueError('Unknown source holiday field')
        rule=record['holiday_rules'][holiday_field]
        if rule['status']=='inherit_selected_weekday':rule=record['weekday_rules'][selected]
        return {**out,'holiday_field':holiday_field,'rule':rule,'status':rule['status']}
    if not holiday_check_complete:return {**out,'status':'requires_holiday_observance_check','weekday_rule':record['weekday_rules'][selected]}
    rule=record['weekday_rules'][selected]
    return {**out,'rule':rule,'status':rule['status']}

def summary(records):
    return {'count':len(records),'year_counts':dict(collections.Counter(str(r['source_year']) for r in records)),
        'city_counts':dict(collections.Counter(str(r['city']) for r in records)),
        'service_type_counts':dict(collections.Counter(str(r['service_type']) for r in records)),
        'weekday_status_counts':{d:dict(collections.Counter(r['weekday_rules'][d]['status'] for r in records)) for d in DAYS},
        'holiday_status_counts':{h:dict(collections.Counter(r['holiday_rules'][h]['status'] for r in records)) for h in HOLIDAYS},
        'source_end_dates':dict(collections.Counter(str(r['end_date_raw']) for r in records)),
        'active_yes_but_posted_end_before_snapshot':sum(str(r['active_raw']).lower()=='yes' and isinstance(r['end_date_raw'],str) and r['end_date_raw']<SNAPSHOT for r in records),
        'capacity_supplied_count':0}

def main():
    ap=argparse.ArgumentParser()
    here=Path(__file__).resolve().parent
    ap.add_argument('--source',type=Path,default=here/'原始响应/query_all_fields.json')
    ap.add_argument('--out',type=Path,default=here)
    args=ap.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
    raw=load(args.source);features=raw['features'];records=[normalize(f) for f in features]
    rawids=[f['attributes']['OBJECTID'] for f in features]
    assert not raw.get('exceededTransferLimit',False)
    assert len(rawids)==len(set(rawids))==122
    count=load(here/'原始响应/count.json')['count']
    ids=load(here/'原始响应/ids.json')['objectIds']
    assert count==len(records) and set(ids)==set(rawids)
    year=[r for r in records if str(r['source_year'])=='2026']
    phoenix=[r for r in year if str(r['city']).strip().lower()=='phoenix']
    assert len(year)==121 and len(phoenix)==50
    for name,data in [('mag_public_view_calendar_122.json',records),('mag_year2026_calendar_121.json',year),('phoenix_year2026_calendar_50.json',phoenix)]:
        write(out/name,{'source_url':URL,'retrieved_date':SNAPSHOT,
            'scope':'Complete public-view response, not a full-season or currently-open inventory.',
            'source_sha256':digest(args.source),'time_basis':'Source local-clock text; no timezone or date extrapolation.',
            'records':data})
    summaries={'all_public_view_122':summary(records),'source_year2026_121':summary(year),'phoenix_source_year2026_50':summary(phoenix)}
    write(out/'日历缺失与范围摘要.json',summaries)
    # Preserve every source attribute exactly, including null versus blank string.
    assert all(r['raw_attributes']==f['attributes'] for r,f in zip(records,features))
    for r in records:
        assert r['capacity_visits_per_day'] is None
        assert len(r['weekday_rules'])==7 and len(r['holiday_rules'])==5
        for rule in r['weekday_rules'].values():
            if blank(rule['open_raw']) and blank(rule['close_raw']):assert rule['status']=='unknown_blank_pair'
    century=next(r for r in phoenix if 'Century Library' in r['site_name'])
    assert century['weekday_rules']['Monday']['close_minute_local']==17*60
    assert century['weekday_rules']['Tuesday']['open_minute_local']==10*60
    assert century['weekday_rules']['Sunday']['status']=='unknown_blank_pair'
    assert resolve_date(century,'2026-06-23',holiday_check_complete=True)['rule']['open_minute_local']==10*60
    assert resolve_date(century,'2026-06-28',holiday_check_complete=True)['status']=='unknown_blank_pair'
    assert resolve_date(century,'2026-07-04',holiday_field='IndependenceDay')['status']=='closed_explicit'
    assert resolve_date(century,'2026-11-18',holiday_check_complete=True)['status']=='outside_posted_source_date_range'
    write(out/'核验.json',{'count_id_sets_match':True,'no_transfer_truncation':True,'unique_ids':True,
        'raw_attributes_exactly_preserved':True,'null_blank_missingness_preserved':True,
        'no_capacity_imputation':True,'weekday_rules_not_merged':True,'holiday_explicit_closed_preserved':True,
        'source_range_applied_before_active_flag':True,'counts':{'public_view':122,'year2026':121,'phoenix2026':50}})
    write(out/'来源与文件哈希.json',{'publisher':'Maricopa Association of Governments',
        'source_url':URL,'item_url':'https://www.arcgis.com/home/item.html?id=bd08dde5206543018fe41da60d2551a7',
        'retrieved_date':SNAPSHOT,'derivation':'Conservative local transformation; no additional source collection.',
        'files':[{'path':p.relative_to(out).as_posix(),'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(out.rglob('*')) if p.is_file() and p.name!='来源与文件哈希.json']})
    print(json.dumps({'rows':len(records),'year2026':len(year),'phoenix2026':len(phoenix),'all_checks_passed':True},ensure_ascii=True))

if __name__=='__main__':main()
