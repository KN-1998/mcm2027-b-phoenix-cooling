"""Independent small timetables test dates, limits, permissions and clocks."""
import csv
import io
import zipfile
from pathlib import Path

import pytest

from src.mch.gtfs_routing import Timetable, seconds


def archive(tmp_path, trips, *, transfers=(), frequencies=(), calendar=None, exceptions=None):
    tables={
        'agency.txt':(["agency_id","agency_timezone"],[['A','America/Phoenix']]),
        'feed_info.txt':(['feed_start_date','feed_end_date'],[['20260701','20260731']]),
        'stops.txt':(['stop_id','stop_name','stop_lat','stop_lon','parent_station'],
                     [[k,k,33+i*.1,-112,''] for i,k in enumerate('ABC')]+[['BB','BB',33.10005,-112,'']]),
        'routes.txt':(['route_id'],[[x] for x in {t[1] for t in trips}]),
        'trips.txt':(['trip_id','route_id','service_id'],[[t[0],t[1],'S'] for t in trips]),
        'stop_times.txt':(['trip_id','stop_id','stop_sequence','arrival_time','departure_time','pickup_type','drop_off_type'],
            [[t[0],stop,i+1,at,at,pickup,dropoff] for t in trips for i,(stop,at,pickup,dropoff) in enumerate(t[2])]),
        'calendar_dates.txt':(['service_id','date','exception_type'],exceptions if exceptions is not None else [['S','20260720','1']]),
        'transfers.txt':(['from_stop_id','to_stop_id','transfer_type','min_transfer_time'],list(transfers)),
        'frequencies.txt':(['trip_id','start_time','end_time','headway_secs','exact_times'],list(frequencies)),
    }
    if calendar:tables['calendar.txt']=calendar
    path=tmp_path/'test.zip'
    with zipfile.ZipFile(path,'w') as z:
        for name,(head,rows) in tables.items():
            stream=io.StringIO();w=csv.writer(stream);w.writerow(head);w.writerows(rows);z.writestr(name,stream.getvalue())
    return path


def query(path,departure='09:00:00',**kwargs):
    tt=Timetable(path,'2026-07-20',**kwargs)
    return tt.route((33,-112),{'B':(33.1,-112),'C':(33.2,-112)},departure)


def trip(tid,a,ta,b,tb,pickup='0',dropoff='0'):
    return (tid,tid,[(a,ta,pickup,'0'),(b,tb,'0',dropoff)])


def test_calendar_dates_only_and_direct_walk(tmp_path):
    p=archive(tmp_path,[trip('T','A','09:05:00','B','09:20:00')])
    r=query(p)['B'];assert r['duration_minutes']==20
    tt=Timetable(p,'2026-07-21')
    assert tt.route((33,-112),{'B':(33.1,-112)},'09:00:00')['B']['mode']=='direct_walk_proxy'
    assert query(p)['B']['duration_minutes']<query(p)['C']['duration_minutes']


def test_remove_exception_overrides_calendar(tmp_path):
    cal=(['service_id','monday','tuesday','wednesday','thursday','friday','saturday','sunday','start_date','end_date'],
         [['S',1,1,1,1,1,1,1,'20260701','20260731']])
    p=archive(tmp_path,[trip('T','A','09:05:00','B','09:20:00')],calendar=cal,exceptions=[['S','20260720','2']])
    assert query(p)['B']['mode']=='direct_walk_proxy'


@pytest.mark.parametrize('pickup,dropoff',[('1','0'),('0','1'),('2','0'),('0','3')])
def test_no_board_or_alight_without_permission(tmp_path,pickup,dropoff):
    p=archive(tmp_path,[trip('T','A','09:05:00','B','09:20:00',pickup,dropoff)])
    assert query(p)['B']['mode']=='direct_walk_proxy'


def test_dated_clock_never_modulo24(tmp_path):
    assert seconds('25:20:00')==91200
    p=archive(tmp_path,[trip('T','A','25:05:00','B','25:20:00')])
    assert query(p,'25:00:00')['B']['arrival_time']=='25:20:00'


def test_transfer_buffer_and_boarding_limit(tmp_path):
    p=archive(tmp_path,[trip('T','A','09:05:00','B','09:20:00'),
                        trip('miss','B','09:21:00','C','09:30:00'),
                        trip('catch','B','09:23:00','C','09:40:00')])
    tt=Timetable(p,'2026-07-20')
    two=tt.route((33,-112),{'C':(33.2,-112)},'09:00:00',max_boardings=2)['C']
    one=tt.route((33,-112),{'C':(33.2,-112)},'09:00:00',max_boardings=1)['C']
    assert two['duration_minutes']==40 and two['boardings']==2
    assert one['mode']=='direct_walk_proxy'
    assert [x['trip_id'] for x in two['legs'] if x['kind']=='scheduled_ride']==['T','catch']


def test_cross_stop_minimum_transfer_not_added_twice(tmp_path):
    p=archive(tmp_path,[trip('T','A','09:05:00','B','09:20:00'),
                        trip('miss','BB','09:24:00','C','09:30:00'),
                        trip('catch','BB','09:26:00','C','09:40:00')],
              transfers=[['B','BB','2','300']])
    r=query(p)['C'];assert r['duration_minutes']==40
    leg=next(x for x in r['legs'] if x['kind']=='transfer_walk_and_buffer')
    assert leg['elapsed_seconds']==300


def test_prohibited_transfer_is_not_silently_allowed(tmp_path):
    p=archive(tmp_path,[trip('T','A','09:05:00','B','09:20:00'),
                        trip('T2','BB','09:26:00','C','09:40:00')],
              transfers=[['B','BB','3','']])
    assert query(p)['C']['mode']=='direct_walk_proxy'


def test_exact_frequency_is_expanded_to_real_departures(tmp_path):
    p=archive(tmp_path,[trip('F','A','00:00:00','B','00:10:00')],
              frequencies=[['F','09:00:00','10:00:00','600','1']])
    r=query(p,'09:01:00')['B'];assert r['duration_minutes']==19
    assert r['legs'][1]['trip_id']=='F@33000'


def test_nonexact_frequency_has_explicit_policy(tmp_path):
    p=archive(tmp_path,[trip('F','A','00:00:00','B','00:10:00')],
              frequencies=[['F','09:00:00','10:00:00','600','0']])
    r=query(p,'09:01:00')['B'];assert r['duration_minutes']==20
    assert r['legs'][1]['kind']=='headway_bound_ride'
    assert query(p,'09:01:00',frequency_policy='exclude_nonexact')['B']['mode']=='direct_walk_proxy'
    with pytest.raises(ValueError,match='non-exact'):query(p,frequency_policy='error')


def test_feed_range_and_time_errors_are_explicit(tmp_path):
    p=archive(tmp_path,[trip('T','A','09:05:00','B','09:20:00')])
    with pytest.raises(ValueError,match='feed range'):Timetable(p,'2026-08-01')
    with pytest.raises(ValueError):seconds('09:60:00')


def test_direct_walk_is_always_available_and_horizon_is_disclosed(tmp_path):
    p=archive(tmp_path,[trip('T','A','09:05:00','B','09:20:00')])
    tt=Timetable(p,'2026-07-20')
    r=tt.route((33,-112),{'near':(33.0001,-112)},'09:00:00')['near']
    assert r['mode']=='direct_walk_proxy' and r['duration_minutes']<1
    assert r['search_horizon_minutes']==240 and r['max_boardings']==3


def test_unsupported_specific_transfer_rule_fails_explicitly(tmp_path):
    p=archive(tmp_path,[trip('T','A','09:05:00','B','09:20:00')])
    with zipfile.ZipFile(p) as z:tables={name:z.read(name) for name in z.namelist()}
    tables['transfers.txt']=b'from_stop_id,to_stop_id,transfer_type,min_transfer_time,from_trip_id\nB,B,2,300,T\n'
    with zipfile.ZipFile(p,'w') as z:
        for name,data in tables.items():z.writestr(name,data)
    with pytest.raises(ValueError,match='richer label state'):query(p)


def test_headway_window_end_does_not_invent_guaranteed_departure(tmp_path):
    p=archive(tmp_path,[trip('F','A','00:00:00','B','00:10:00')],
              frequencies=[['F','09:00:00','10:00:00','600','0']])
    assert query(p,'09:59:00')['B']['mode']=='direct_walk_proxy'


def station_rule_fixture(tmp_path,transfer_rows):
    p=archive(tmp_path,[trip('T','A','09:05:00','B','09:20:00'),
                        trip('T2','BB','09:26:00','C','09:40:00')],transfers=transfer_rows)
    with zipfile.ZipFile(p) as z:tables={name:z.read(name) for name in z.namelist()}
    rows=list(csv.DictReader(io.StringIO(tables['stops.txt'].decode())))
    for row in rows:
        if row['stop_id']=='B':row['parent_station']='P'
        if row['stop_id']=='BB':row['parent_station']='Q'
    rows += [{'stop_id':'P','stop_name':'P','stop_lat':33.1,'stop_lon':-112,'parent_station':''},
             {'stop_id':'Q','stop_name':'Q','stop_lat':33.10005,'stop_lon':-112,'parent_station':''}]
    stream=io.StringIO();w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    tables['stops.txt']=stream.getvalue().encode()
    with zipfile.ZipFile(p,'w') as z:
        for name,data in tables.items():z.writestr(name,data)
    return p


def test_child_transfer_override_is_independent_of_csv_order(tmp_path):
    rules=[['P','Q','3',''],['B','BB','2','300']]
    results=[]
    for order in (rules,list(reversed(rules))):
        p=station_rule_fixture(tmp_path,order)
        tt=Timetable(p,'2026-07-20')
        assert tt.rules[tt.stop_index['B'],tt.stop_index['BB']]==(2,300)
        result=tt.route((33,-112),{'C':(33.2,-112)},'09:00:00')['C']
        results.append(result['duration_minutes'])
    assert results==[40.,40.]


def test_equal_specificity_transfer_conflict_is_rejected(tmp_path):
    # Each rule names one child endpoint and one parent endpoint, so neither
    # outranks the other for B->BB. Such ambiguity is not resolved by row order.
    for rules in ([['P','BB','3',''],['B','Q','2','300']],
                  [['B','Q','2','300'],['P','BB','3','']]):
        p=station_rule_fixture(tmp_path,rules)
        with pytest.raises(ValueError,match='equally specific'):Timetable(p,'2026-07-20')
