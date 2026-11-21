"""Explicit import of one dated, one-departure routing scenario for planning."""
from pathlib import Path
import copy,csv,hashlib,math

def apply_reference_gtfs_access(inst,path: str|Path,departure: str='09:00:00'):
    source=Path(path)
    with source.open(encoding='utf-8-sig',newline='') as f:
        rows=[r for r in csv.DictReader(f) if r['departure']==departure]
    if not rows:raise ValueError('no OD rows for requested reference departure')
    dates={r['service_date'] for r in rows}
    if len(dates)!=1 or next(iter(dates))!=str(inst.meta.get('calendar_start_date')):
        raise ValueError('routing date must match the dated network reference start')
    needed={(d.id,s.id) for d in inst.districts for s in inst.sites if s.kind in ('cooling','respite','candidate_mch')}
    values={}
    for row in rows:
        key=row['district_id'],row['site_id']
        if key in values:raise ValueError('duplicate OD pair in reference departure')
        value=float(row['duration_minutes'])
        if not math.isfinite(value) or value<0:raise ValueError('invalid routing duration')
        values[key]=value
    if not needed<=values.keys():raise ValueError('routing matrix does not cover this indoor/candidate inventory')
    out=copy.deepcopy(inst);out.access={k:v for k,v in values.items() if k in needed}
    out.meta['access_mode']='gtfs_reference_one_departure'
    out.meta['reference_access']={'path':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'date':next(iter(dates)),'departure':departure,
        'scope':'One reference departure repeated in all planning periods/days; not a time-dependent seven-day empirical transit forecast',
        'routing_semantics':'Published GTFS plus assumed walking/frequency policy; see the OD experiment manifest'}
    return out
