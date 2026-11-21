"""Bounded earliest-arrival routing on a dated GTFS feed.

Scheduled trips are scanned exactly within max_boardings and journey horizon.
Non-exact frequency service is either excluded explicitly or uses a disclosed
one-headway maximum-wait assumption. Access/egress/transfer walking is a detoured
great-circle proxy, never an observed pedestrian route. No real-time claim.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import math
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from scipy.spatial import cKDTree

EARTH_KM = 6371.0


def seconds(value: str) -> int:
    """Service-day time, deliberately preserving 24:xx and later hours."""
    try:
        h, m, s = (int(x) for x in value.split(':'))
    except (ValueError, AttributeError):
        raise ValueError(f'invalid GTFS clock {value!r}') from None
    if h < 0 or not 0 <= m < 60 or not 0 <= s < 60:
        raise ValueError(f'invalid GTFS clock {value!r}')
    return 3600*h + 60*m + s


def clock(value: float) -> str:
    value = int(round(value))
    return f'{value//3600:02d}:{value//60%60:02d}:{value%60:02d}'


def haversine(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    x = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(lon2-lon1)/2)**2
    return 2*EARTH_KM*math.asin(math.sqrt(min(1., max(0., x))))


@dataclass(frozen=True)
class StopTime:
    stop: int
    arrival: int
    departure: int
    pickup: bool
    dropoff: bool


@dataclass(frozen=True)
class Trip:
    id: str
    route: str
    times: tuple[StopTime, ...]
    frequency: tuple[int, int, int] | None = None


class Timetable:
    def __init__(self, archive: str | Path, date: str, *, frequency_policy='headway_bound',
                 walk_kmh=4.8, walk_detour=1.35, access_walk_km=1.2,
                 transfer_walk_km=.5, transfer_buffer_seconds=120):
        if frequency_policy not in ('headway_bound', 'exclude_nonexact', 'error'):
            raise ValueError('invalid frequency policy')
        parameters=(walk_kmh,walk_detour,access_walk_km,transfer_walk_km,transfer_buffer_seconds)
        if not all(math.isfinite(x) for x in parameters) or walk_kmh <= 0 or walk_detour < 1 or access_walk_km < 0 or transfer_walk_km < 0 or transfer_buffer_seconds < 0:
            raise ValueError('invalid walking or transfer parameter')
        self.archive = Path(archive)
        self.date = dt.date.fromisoformat(date)
        self.walk_kmh, self.walk_detour = walk_kmh, walk_detour
        self.access_walk_km, self.transfer_walk_km = access_walk_km, transfer_walk_km
        self.transfer_buffer = transfer_buffer_seconds
        self.frequency_policy = frequency_policy
        with zipfile.ZipFile(self.archive) as z:
            names = {Path(name).name:name for name in z.namelist() if not name.endswith('/')}
            def rows(name):
                if name not in names: return iter(())
                return csv.DictReader(io.TextIOWrapper(z.open(names[name]), encoding='utf-8-sig', newline=''))
            feed = list(rows('feed_info.txt'))
            datecode = self.date.strftime('%Y%m%d')
            for r in feed:
                if r.get('feed_start_date') and datecode < r['feed_start_date'] or r.get('feed_end_date') and datecode > r['feed_end_date']:
                    raise ValueError('requested date lies outside published feed range')
            agencies = list(rows('agency.txt'))
            zones = {r['agency_timezone'] for r in agencies}
            if zones != {'America/Phoenix'}:
                raise ValueError('only a single America/Phoenix service timezone is supported')
            active = set()
            weekday = self.date.strftime('%A').lower()
            for r in rows('calendar.txt'):
                if r['start_date'] <= datecode <= r['end_date'] and r[weekday] == '1': active.add(r['service_id'])
            for r in rows('calendar_dates.txt'):
                if r['date'] == datecode:
                    if r['exception_type'] == '1': active.add(r['service_id'])
                    elif r['exception_type'] == '2': active.discard(r['service_id'])
                    else: raise ValueError('invalid calendar exception type')
            rawstops = list(rows('stops.txt'))
            self.stop_ids = [r['stop_id'] for r in rawstops]
            if len(set(self.stop_ids)) != len(self.stop_ids): raise ValueError('duplicate stop_id')
            self.stop_index = {k:i for i,k in enumerate(self.stop_ids)}
            self.stop_names = [r['stop_name'] for r in rawstops]
            self.coords = np.array([[float(r['stop_lat']),float(r['stop_lon'])] for r in rawstops])
            if not np.isfinite(self.coords).all(): raise ValueError('nonfinite stop location')
            parents = {r['stop_id']:r.get('parent_station') for r in rawstops}
            route_info = {r['route_id']:r for r in rows('routes.txt')}
            for r in route_info.values():
                if r.get('continuous_pickup', '') not in ('', '1') or r.get('continuous_drop_off', '') not in ('', '1'):
                    raise ValueError('continuous/on-demand route service requires a different router')
            selected = {r['trip_id']:r for r in rows('trips.txt') if r['service_id'] in active}
            frequencies = {}
            for r in rows('frequencies.txt'):
                if r['trip_id'] not in selected: continue
                f=(seconds(r['start_time']),seconds(r['end_time']),int(r['headway_secs']),r.get('exact_times','0') or '0')
                if not 0 <= f[0] < f[1] or f[2] <= 0 or f[3] not in ('0','1'): raise ValueError('invalid frequency row')
                frequencies.setdefault(r['trip_id'],[]).append(f)
            for group in frequencies.values():
                group.sort()
                if any(a[1]>b[0] for a,b in zip(group,group[1:])): raise ValueError('overlapping frequency windows')
            times = {tid:[] for tid in selected}
            restrictions = {'pickup_excluded':0,'dropoff_excluded':0,'approximate_timepoint_rows':0,'after_24h_rows':0}
            for r in rows('stop_times.txt'):
                tid=r['trip_id']
                if tid not in selected: continue
                if any(r.get(k) for k in ('start_pickup_drop_off_window','end_pickup_drop_off_window','location_group_id','location_id')):
                    raise ValueError('on-demand stop windows are unsupported')
                if r.get('continuous_pickup','') not in ('','1') or r.get('continuous_drop_off','') not in ('','1'):
                    raise ValueError('continuous/on-demand stop service is unsupported')
                if not r['arrival_time'] or not r['departure_time']:
                    raise ValueError('missing published stop time; no unvalidated interpolation performed')
                arrival, departure = seconds(r['arrival_time']),seconds(r['departure_time'])
                if departure<arrival: raise ValueError('departure before arrival')
                if r.get('pickup_type','') not in ('','0','1','2','3') or r.get('drop_off_type','') not in ('','0','1','2','3'):
                    raise ValueError('invalid pickup or dropoff permission')
                pickup=r.get('pickup_type','') in ('','0');dropoff=r.get('drop_off_type','') in ('','0')
                restrictions['pickup_excluded']+=not pickup;restrictions['dropoff_excluded']+=not dropoff
                restrictions['approximate_timepoint_rows']+=r.get('timepoint')=='0'
                restrictions['after_24h_rows']+=max(arrival,departure)>=86400
                times[tid].append((int(r['stop_sequence']),StopTime(self.stop_index[r['stop_id']],arrival,departure,pickup,dropoff)))
            self.trips=[];self.frequency_templates=[];excluded=0;expanded=0;nonexact=0
            for tid, t in times.items():
                t.sort(key=lambda x:x[0])
                if len({x[0] for x in t})!=len(t): raise ValueError('duplicate trip stop_sequence')
                ts=tuple(x[1] for x in t)
                if len(ts)<2: continue
                if any(a.departure>b.arrival for a,b in zip(ts,ts[1:])): raise ValueError('nonmonotone published trip times')
                route=selected[tid]['route_id']
                if tid not in frequencies:self.trips.append(Trip(tid,route,ts));continue
                for start,end,headway,exact in frequencies[tid]:
                    if exact=='1':
                        for first_dep in range(start,end,headway):
                            shift=first_dep-ts[0].departure
                            shifted=tuple(StopTime(x.stop,x.arrival+shift,x.departure+shift,x.pickup,x.dropoff) for x in ts)
                            self.trips.append(Trip(f'{tid}@{first_dep}',route,shifted));expanded+=1
                    else:
                        nonexact+=1
                        pattern=Trip(tid,route,ts,(start,end,headway))
                        self.frequency_templates.append(pattern)
                        if frequency_policy=='error': raise ValueError('non-exact frequency service present; choose explicit policy')
                        if frequency_policy=='exclude_nonexact':excluded+=1;continue
                        self.trips.append(pattern)
            self.rules={};rule_priority={}
            for r in rows('transfers.txt'):
                if any(r.get(k) for k in ('from_trip_id','to_trip_id','from_route_id','to_route_id')):
                    raise ValueError('trip/route-specific transfer rules require richer label state')
                if r.get('transfer_type','0') not in ('','0','2','3'):
                    raise ValueError('timed/in-seat transfer types are outside this router')
                a,b=r['from_stop_id'],r['to_stop_id'];kind=int(r.get('transfer_type') or 0)
                if kind==2 and not r.get('min_transfer_time'):
                    raise ValueError('minimum transfer time missing for type 2')
                if int(r.get('min_transfer_time') or 0)<0:raise ValueError('negative minimum transfer time')
                # Expand station-level rules to children, as required by GTFS.
                aa=[sid for sid in self.stop_ids if sid==a or parents.get(sid)==a]
                bb=[sid for sid in self.stop_ids if sid==b or parents.get(sid)==b]
                for sa in aa:
                    for sb in bb:
                        pair=(self.stop_index[sa],self.stop_index[sb])
                        rule=(kind,int(r.get('min_transfer_time') or 0))
                        # Explicit child-stop endpoints are more specific than
                        # a station-level rule inherited by those children.
                        # Never let CSV ordering decide an ambiguous override.
                        priority=int(sa==a)+int(sb==b)
                        previous_priority=rule_priority.get(pair,-1)
                        if priority==previous_priority and self.rules[pair]!=rule:
                            raise ValueError('conflicting equally specific transfer rules')
                        if priority>previous_priority:
                            self.rules[pair]=rule;rule_priority[pair]=priority
        rad=np.radians(self.coords)
        self.xyz=np.column_stack((np.cos(rad[:,0])*np.cos(rad[:,1]),np.cos(rad[:,0])*np.sin(rad[:,1]),np.sin(rad[:,0])))
        self.tree=cKDTree(self.xyz)
        self.footpaths=self._build_footpaths()
        self.metadata={'archive_sha256':hashlib.sha256(self.archive.read_bytes()).hexdigest(),
                       'service_date':date,'active_services':len(active),'active_trip_records':len(selected),
                       'router_trip_patterns':len(self.trips),'calendar_txt_present':'calendar.txt' in names,
                       'frequency_nonexact_rows':nonexact,'frequency_rows_excluded':excluded,
                       'exact_frequency_departures_expanded':expanded,'frequency_policy':frequency_policy,
                       'previous_service_days_included':False,'block_continuations_inferred':False,
                       'latest_regular_arrival_seconds':max((st.arrival for trip in self.trips if trip.frequency is None for st in trip.times),default=None),
                       'latest_frequency_window_last_stop_bound_seconds':max((trip.frequency[1]+trip.times[-1].arrival-trip.times[0].departure for trip in self.frequency_templates),default=None),
                       'stop_based_transfer_rules':len(self.rules),'restriction_counts':restrictions,
                       'transfer_rule_precedence':'explicit child endpoints over inherited station endpoints; equal-specificity conflicts rejected',
                       'walking':{'speed_kmh':walk_kmh,'detour':walk_detour,'access_egress_limit_km':access_walk_km,
                                  'generated_transfer_limit_km':transfer_walk_km,'transfer_buffer_seconds':transfer_buffer_seconds},
                       'scope':'Published times, with bounded boardings/search horizon and assumed walking. Headway-bound service is not a fixed timetable or actual maximum-wait guarantee.'}

    def walk_seconds(self,a,b):
        return haversine(*a,*b)*self.walk_detour/self.walk_kmh*3600

    def connectors(self,point,limit_km):
        lat,lon=np.radians(point)
        xyz=(math.cos(lat)*math.cos(lon),math.cos(lat)*math.sin(lon),math.sin(lat))
        chord=2*math.sin(limit_km/self.walk_detour/EARTH_KM/2)+1e-12
        return [(i,self.walk_seconds(point,self.coords[i])) for i in self.tree.query_ball_point(xyz,chord)]

    def _build_footpaths(self):
        out=[]
        for i,point in enumerate(self.coords):
            options=dict(self.connectors(point,self.transfer_walk_km));options[i]=0.
            for a,b in self.rules:
                if a==i:options[b]=self.walk_seconds(point,self.coords[b])
            out.append([(j,t,*self.rules.get((i,j),(0,0))) for j,t in options.items()
                        if self.rules.get((i,j),(0,0))[0]!=3])
        return out

    def route(self,origin,destinations:dict[str,tuple[float,float]],departure:str|int,
              *,max_boardings=3,horizon_minutes=240):
        if not isinstance(max_boardings,int) or not 1<=max_boardings<=8 or not math.isfinite(horizon_minutes) or horizon_minutes<=0:raise ValueError('invalid routing search bounds')
        start=seconds(departure) if isinstance(departure,str) else int(departure)
        if start<0:raise ValueError('negative departure')
        end=start+horizon_minutes*60
        n=len(self.stop_ids);inf=float('inf')
        ready=[inf]*n;ready_paths=[None]*n
        for i,walk in self.connectors(origin,self.access_walk_km):
            ready[i]=start+walk
            ready_paths[i]=[{'kind':'access_walk_proxy','to_stop':self.stop_ids[i],'seconds':walk}]
        best={}
        for name,point in destinations.items():
            walk=self.walk_seconds(origin,point)
            best[name]={'duration_minutes':walk/60,'arrival_seconds':start+walk,'mode':'direct_walk_proxy',
                        'boardings':0,'legs':[{'kind':'direct_walk_proxy','seconds':walk}]}
        egress={name:self.connectors(point,self.access_walk_km) for name,point in destinations.items()}
        updates=0
        for boarding in range(1,max_boardings+1):
            arrival=[inf]*n;paths=[None]*n
            for trip in self.trips:
                board=None;phase=inf
                first=trip.times[0].departure
                for k,st in enumerate(trip.times):
                    if board is not None and st.dropoff:
                        at=st.arrival if trip.frequency is None else st.arrival+phase
                        if at<=end and at<arrival[st.stop]-1e-9:
                            arrival[st.stop]=at;updates+=1
                            bidx,bdep,bpath=board
                            paths[st.stop]=bpath+[{'kind':'scheduled_ride' if trip.frequency is None else 'headway_bound_ride',
                                'trip_id':trip.id,'route_id':trip.route,'from_stop':self.stop_ids[trip.times[bidx].stop],
                                'to_stop':self.stop_ids[st.stop],'departure_seconds':bdep,'arrival_seconds':at,
                                'from_sequence_index':bidx,'to_sequence_index':k}]
                    if not st.pickup or ready[st.stop]==inf:continue
                    if trip.frequency is None:
                        if board is None and ready[st.stop]<=st.departure and st.departure<=end:
                            board=(k,st.departure,ready_paths[st.stop])
                    else:
                        fstart,fend,headway=trip.frequency;offset=st.departure-first
                        dep=max(ready[st.stop],fstart+offset)+headway
                        if dep<fend+offset and dep<=end and dep-st.departure<phase:
                            phase=dep-st.departure;board=(k,dep,ready_paths[st.stop])
            for name,connectors in egress.items():
                for stop,walk in connectors:
                    at=arrival[stop]+walk
                    if at<=end and at<best[name]['arrival_seconds']-1e-9:
                        best[name]={'duration_minutes':(at-start)/60,'arrival_seconds':at,
                                    'mode':'gtfs_with_assumed_walk','boardings':boarding,
                                    'legs':paths[stop]+[{'kind':'egress_walk_proxy','from_stop':self.stop_ids[stop],'seconds':walk}]}
            if boarding==max_boardings:break
            ready=[inf]*n;ready_paths=[None]*n
            for i,at in enumerate(arrival):
                if at==inf:continue
                for j,walk,kind,minimum in self.footpaths[i]:
                    # min_transfer_time is total elapsed interchange time, not
                    # an extra time added on top of the same walking interval.
                    slack=max(walk,minimum if kind==2 else self.transfer_buffer)
                    value=at+slack
                    if value<ready[j]-1e-9:
                        ready[j]=value;ready_paths[j]=paths[i]+[{'kind':'transfer_walk_and_buffer',
                            'from_stop':self.stop_ids[i],'to_stop':self.stop_ids[j],
                            'walk_seconds':walk,'elapsed_seconds':slack,'source_min_transfer_seconds':minimum}]
            if all(x==inf for x in ready):break
        for result in best.values():
            result.update({'service_date':self.date.isoformat(),'departure_seconds':start,
                           'arrival_time':clock(result['arrival_seconds']),'max_boardings':max_boardings,
                           'search_horizon_minutes':horizon_minutes,'label_updates':updates,
                           'frequency_policy':self.frequency_policy})
        return best
