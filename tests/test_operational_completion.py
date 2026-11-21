from __future__ import annotations
import copy
from unittest.mock import patch
import pytest
from src.mch.schema import Site,District,Instance
from src.mch.hours import capacity_on_service_day
from src.mch.static import _assign
from src.mch.operations import annual_operating_envelope,operational_status
from src.mch.policy import plan_robust_investment


def fixture():
    site=Site('M','M','candidate_mch','D',33.5,-112,130,9,22)
    inst=Instance([District('D','D',1000,.1,.1,20000,.1,.5)],[site],{('D','M'):1},{('D',0):1000},1)
    return inst,site


@pytest.mark.parametrize('field',['permit_by_day','power_by_day','site_access_by_day'])
def test_closed_resource_cannot_be_reopened_by_override(field):
    inst,site=fixture();site.extra[field]={'0':False}
    sol=_assign(inst,[site],0,30,250,cap_by_period_override={'M':{'day':1000,'evening':1000}})
    assert sum(sol.served.values())==0


def test_staffed_window_cuts_evening_without_renormalizing_day_rate():
    inst,site=fixture();site.extra['staffed_windows_by_day']={'0':[[9,17]],'1':[[17,22]]}
    assert capacity_on_service_day(site,130,'day',0)==80
    assert capacity_on_service_day(site,130,'evening',0)==0
    assert capacity_on_service_day(site,130,'day',1)==0
    assert capacity_on_service_day(site,130,'evening',1)==50


def test_overlapping_shifts_and_missing_confirmations_are_not_guessed():
    _,site=fixture();site.extra['staffed_windows_by_day']={'0':[[9,17],[16,22]]}
    with pytest.raises(ValueError,match='overlapping'):capacity_on_service_day(site,130,'day',0)
    site.extra['staffed_windows_by_day']={'0':[[9,17]]}
    with pytest.raises(ValueError,match='missing'):capacity_on_service_day(site,130,'day',1)


def test_cost_envelope_hand_calculation():
    cost=annual_operating_envelope(operating_days=10,open_hours=8,people_on_duty=2,
        hourly_wage=20,payroll_multiplier=1.25,electricity_kwh_per_hour=5,
        electricity_usd_per_kwh=.2,consumables_per_visit=.5,visits_per_day=100,
        maintenance_and_insurance=200,storage=50)
    assert cost['staff_hours']==160
    assert cost['total']==4000+80+500+200+50

def test_none_operational_fields_do_not_become_confirmations():
    _,site=fixture()
    site.extra={key:None for key in ('permit_by_day','power_by_day','site_access_by_day','staffed_windows_by_day')}
    status=operational_status(site,0)
    assert status['confirmed_fields']==[] and not status['fully_documented_inputs']


def test_robust_plan_is_common_to_paths_and_bounds_each_path():
    inst,_=fixture()
    def factory(_,path,**kwargs):
        return lambda year,p,extension,shuttle:(path[year]*(100-40*p),1-.4*p)
    prices={'hub_buy':1,'hub_ops':1,'extend_21':100,'extend_22':100,'shuttle':100}
    with patch('src.mch.policy.scenario_evaluator',side_effect=factory):
        result=plan_robust_investment(inst,[2,2],[[1,3],[2,1]],p_start=0,p_max=1,costs=prices)
    # One vehicle can be purchased in year1 and retained. Stagewise worst 2,3.
    assert result['summary']['weighted_unmet_visits']==2*60+3*60
    assert [r['active'] for r in result['rows']]==[1,1]
    assert all(r['weighted_unmet_visits']<=result['summary']['weighted_unmet_visits'] for r in result['fixed_plan_performance_by_path'])
    assert all(r['heat_multiplier'] is None for r in result['rows'])

@pytest.mark.parametrize('heat',[[-1],[float('nan')],[float('inf')]])
def test_robust_invalid_heat_is_not_an_exact_plan(heat):
    inst,_=fixture()
    with pytest.raises(ValueError):plan_robust_investment(inst,[0],[heat],p_start=0,p_max=0)

def test_myopic_strategy_is_not_mislabelled_as_robust_exact():
    inst,_=fixture()
    with pytest.raises(ValueError):plan_robust_investment(inst,[0],[[1]],p_start=0,p_max=0,strategy='rolling')
