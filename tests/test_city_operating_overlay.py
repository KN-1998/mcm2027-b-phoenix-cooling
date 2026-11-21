import copy
from src.mch.realnet import build_real_instance,apply_city_operating_corrections
from src.mch.static import solve_static

def test_official_overlay_is_explicit_and_preserves_registered_inventory():
    original=build_real_instance(access_mode='transit_min');saved=copy.deepcopy(original)
    revised=apply_city_operating_corrections(original)
    assert original==saved
    assert len(original.fixed_sites())==50 and len(revised.fixed_sites())==52
    lookup={s.id:s for s in revised.sites}
    assert lookup['MAG0068'].close_hour==21
    assert lookup['MAG0068'].extra['original_MAG_calendar']['0']['close_hour']==17
    assert lookup['CITY_JUSTA_2026'].extra['matched_address'].startswith('1001 W JEFFERSON ST,')
    assert lookup['CITY_JACKSON_24H_2026'].extra['source_capacity']=='ASSUME_OBSERVATION_COMPATIBLE_SCENARIO'
    assert all((d.id,s.id) in revised.access for d in revised.districts for s in revised.sites)
    second=apply_city_operating_corrections(revised,jackson_capacity=750,justa_capacity=300)
    second_sites={s.id:s for s in second.sites}
    assert second_sites['CITY_JACKSON_24H_2026'].capacity==750
    assert second_sites['CITY_JUSTA_2026'].capacity==300
    assert second_sites['MAG0068'].open_hour==9
    assert second_sites['MAG0068'].extra['original_MAG_calendar']['0']['close_hour']==17

def test_omitted_fixed_respite_supply_is_not_limited_by_mobile_250_ceiling():
    inst=apply_city_operating_corrections(build_real_instance(access_mode='transit_min'),jackson_capacity=500)
    jackson=next(s for s in inst.sites if s.id=='CITY_JACKSON_24H_2026')
    assert jackson.kind=='respite' and jackson.capacity==500
    # This checks consistent resource accounting, not a forecast of actual visits.
    before=solve_static(build_real_instance(access_mode='transit_min'),0)
    after=solve_static(inst,0)
    assert after.metrics['unmet_total_raw']<=before.metrics['unmet_total_raw']
