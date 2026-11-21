"""Independent certificates and boundary cases for the completion release.

The min-cut oracle enumerates cuts directly and never calls a production LP or
another network solver. It checks the modeled period/day constraints, not the
truth of the input demand or actual travel times.
"""
from __future__ import annotations

import itertools
import math
import random

import pytest

from src.mch.assign import solve_assignment_periods
from src.mch.demand import vulnerability
from src.mch.dynamic import solve_week_dp
from src.mch.schema import District, Instance, Site
from src.mch.static import _active_sites, _assign


def district(k):
    return District(k,k,1000,.1,.1,50000,.1,.5)


def cut_oracle(demand, capacity, links, mobile):
    """Enumerate every finite source-sink cut of the tiny period network."""
    periods=sorted(next(iter(demand.values())))
    dp=[('d',i,h) for i in demand for h in periods]
    sp=[('s',j,h) for j in capacity for h in periods]
    sn=[('site',j) for j in capacity]
    vertices=dp+sp+sn
    big=1+sum(sum(x.values()) for x in demand.values())+sum(sum(x.values()) for x in capacity.values())
    edges=[]
    for i,dem in demand.items():
        for h in periods:edges.append(('SRC',('d',i,h),dem[h]))
    for i,j in links:
        for h in periods:edges.append((('d',i,h),('s',j,h),big))
    for j,caps in capacity.items():
        for h in periods:edges.append((('s',j,h),('site',j),caps[h]))
        edges.append((('site',j),'SNK',min(250,sum(caps.values())) if j in mobile else sum(caps.values())))
    best=math.inf
    for bits in itertools.product((False,True),repeat=len(vertices)):
        left={'SRC'}|{v for v,inside in zip(vertices,bits) if inside}
        best=min(best,sum(c for u,v,c in edges if u in left and v not in left))
    return best


@pytest.mark.parametrize('seed',range(8))
def test_period_lp_equals_independent_cut_certificate(seed):
    rng=random.Random(seed)
    ds=[district(k) for k in ('A','B')]
    ss=[Site('F','F','cooling','A',0,0,100,9,22),
        Site('M','M','candidate_mch','B',0,0,250,9,22)]
    links={(i,j) for i in ('A','B') for j in ('F','M') if rng.random()<.8}
    dem={i:{h:rng.randrange(0,301,25) for h in ('day','evening')} for i in ('A','B')}
    caps={j:{h:rng.randrange(0,301,50) for h in ('day','evening')} for j in ('F','M')}
    inst=Instance(ds,ss,{key:1 for key in links},{},1)
    actual=solve_assignment_periods(inst,ss,cap_by_period=caps,dem_by_period=dem)
    expected=cut_oracle(dem,caps,links,{'M'})
    assert actual['status']=='optimal'
    assert sum(actual['served'].values())==pytest.approx(expected,abs=1e-7)
    assert sum(a['visits'] for a in actual.get('allocations',[]))==pytest.approx(expected,abs=1e-7)


def test_common_demand_scaling_can_make_relocation_useful():
    # Identical A:B demand shares each day, but fixed capacity at A changes the
    # residual benefit of an extra vehicle. This refutes a general zero-gain rule.
    ds=[district(k) for k in 'AB']
    ss=[Site('F','F','cooling','A',0,0,50,9,17),
        Site('MA','MA','candidate_mch','A',33.,-112.,250,9,17),
        Site('MB','MB','candidate_mch','B',33.01,-112.,250,9,17)]
    dem={('A',0):100.,('B',0):75.,('A',1):500.,('B',1):375.}
    inst=Instance(ds,ss,{('A','F'):0.,('A','MA'):0.,('B','MB'):0.},dem,2,{'unsheltered_share':.5})
    result=solve_week_dp(inst,1)
    assert dem['A',1]/dem['A',0]==dem['B',1]/dem['B',0]==5
    # Hand check: day shares .425; fixed serves42.5+50. Mobile B->A serves
    #31.875+162.5; the .53h relocation still leaves enough day capacity.
    assert result['static_total_unmet']==pytest.approx(766.25)
    assert result['dynamic_total_unmet']==pytest.approx(763.125)
    assert [r['combo'] for r in result['schedule']]==[['MB'],['MA']]
    assert result['static_total_unmet']-result['dynamic_total_unmet']==pytest.approx(3.125)


def test_epsilon_infeasibility_and_exact_maxmin_are_different_outputs():
    ds=[district(k) for k in 'AB'];ss=[Site('F','F','cooling','A',0,0,100,9,17)]
    inst=Instance(ds,ss,{('A','F'):1.,('B','F'):1.},{},1)
    dem={i:{'day':100.} for i in 'AB'};caps={'F':{'day':100.}}
    infeasible=solve_assignment_periods(inst,ss,cap_by_period=caps,dem_by_period=dem,equity_cap=.4)
    fair=solve_assignment_periods(inst,ss,cap_by_period=caps,dem_by_period=dem,objective='maxmin')
    assert infeasible['status']=='infeasible'
    assert fair['status']=='optimal'
    assert fair['t']==pytest.approx(.5)
    assert fair['served']['A']==pytest.approx(50.,abs=1e-6)
    assert fair['served']['B']==pytest.approx(50.,abs=1e-6)


def test_exemption_changes_constraint_not_the_actual_unserved_district():
    ds=[district(k) for k in 'AB'];ss=[Site('F','F','cooling','A',0,0,100,9,17)]
    inst=Instance(ds,ss,{('A','F'):1.,('B','F'):1.},{},1)
    out=solve_assignment_periods(inst,ss,cap_by_period={'F':{'day':100.}},
                                dem_by_period={i:{'day':100.} for i in 'AB'},
                                equity_exempt=['B'],objective='maxmin')
    assert out['t']==pytest.approx(0.)
    assert out['served']['A']==pytest.approx(100.)
    assert out['served']['B']==pytest.approx(0.,abs=1e-6)


def test_zero_demand_has_zero_worst_fraction():
    inst=Instance([district('A')],[],{},{},1)
    out=solve_assignment_periods(inst,[],dem_by_period={'A':{'day':0.}},objective='maxmin')
    assert out['status']=='optimal'
    assert out['t']==0


def test_vulnerability_is_bounded_at_legal_extreme_demographics():
    d=district('A');d.pct_65plus=.9;d.pct_no_vehicle=.7;d.median_income=10000
    assert vulnerability(d)==1.


def test_mobile_utilization_uses_daily_ceiling_not_sum_of_loose_period_bounds():
    # Two nonoverlapping opening-date windows contribute to one09->next09
    # service day; daily ceiling remains250 rather than500. No override adds
    # new capacity, so operational availability still only removes supply.
    s=Site('M','M','candidate_mch','A',0,0,250,9,10,
           extra={'calendar_by_day':{'-1':{'open_hour':0.,'close_hour':0.},
                                      '0':{'open_hour':9.,'close_hour':10.},
                                      '1':{'open_hour':0.,'close_hour':8.}}})
    inst=Instance([district('A')],[s],{('A','M'):1.},{('A',0):1000.},1,{'unsheltered_share':.5})
    sol=_assign(inst,_active_sites(inst,['M']),0,30,250)
    assert sum(sol.served.values())==pytest.approx(250.)
    assert sol.metrics['utilization_by_site']['M']==pytest.approx(1.)


@pytest.mark.parametrize('bad',[math.nan,math.inf,-1.])
def test_nonfinite_or_negative_override_rejected(bad):
    s=Site('M','M','candidate_mch','A',0,0,250,9,22)
    inst=Instance([district('A')],[s],{('A','M'):1.},{('A',0):100.},1)
    with pytest.raises(ValueError):
        _assign(inst,_active_sites(inst,['M']),0,30,250,cap_by_period_override={'M':{'day':bad}})
