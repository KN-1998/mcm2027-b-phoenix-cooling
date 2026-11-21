"""Explicit operating permissions, staffed windows and auditable cost envelopes.

Missing confirmations remain assumptions, never automatically verified facts.
Clock windows use the model's unwrapped service day [09:00, next09:00].
"""
from __future__ import annotations
import math
from typing import Mapping


def staffed_windows(site, day: int) -> list[tuple[float,float]]:
    extra=site.extra or {}
    for key in ('permit_by_day','power_by_day','site_access_by_day'):
        rules=extra.get(key)
        if rules is not None:
            if str(day) not in rules:raise ValueError(f'{site.id}: {key}/day{day} missing')
            status=rules[str(day)]
            if type(status) is not bool:raise ValueError(f'{key} requires explicit boolean')
            if not status:return []
    rules=extra.get('staffed_windows_by_day')
    if rules is None:return [(9.,33.)]
    if str(day) not in rules:raise ValueError(f'{site.id}: staffed window missing for day{day}')
    windows=[]
    for lo,hi in rules[str(day)]:
        lo,hi=float(lo),float(hi)
        if not (math.isfinite(lo) and math.isfinite(hi) and 9<=lo<hi<=33):
            raise ValueError('staffed windows must be disjoint intervals within [9,33]')
        windows.append((lo,hi))
    windows.sort()
    if any(a[1]>b[0]+1e-9 for a,b in zip(windows,windows[1:])):
        raise ValueError('overlapping staffed windows double count staff coverage')
    return windows


def operational_status(site,day: int) -> dict:
    fields=('permit_by_day','power_by_day','site_access_by_day','staffed_windows_by_day')
    present=[k for k in fields if (site.extra or {}).get(k) is not None]
    return {'site':site.id,'day':day,'confirmed_fields':present,
            'assumed_fields':[k for k in fields if k not in present],
            'staffed_windows':staffed_windows(site,day),
            'fully_documented_inputs':len(present)==len(fields),
            'not_a_field_inspection':True}


def annual_operating_envelope(*, operating_days: int, open_hours: float,
        people_on_duty: int, hourly_wage: float, payroll_multiplier: float,
        electricity_kwh_per_hour: float=0, electricity_usd_per_kwh: float=0,
        consumables_per_visit: float=0, visits_per_day: float=0,
        maintenance_and_insurance: float=0, storage: float=0) -> dict:
    """Bottom-up annual operating cost; every unobserved input stays ASSUME.

    Wage is a scenario rate, not an asserted MCH contract or future legal rate.
    No salvage, downtime or duplicate capital is hidden in annual operations.
    """
    values=locals().copy()
    if any(not math.isfinite(float(v)) or float(v)<0 for v in values.values()):
        raise ValueError('cost inputs must be finite and nonnegative')
    if int(operating_days)!=operating_days or int(people_on_duty)!=people_on_duty or open_hours>24:
        raise ValueError('days/people must be integers; open hours <=24')
    if payroll_multiplier<1:raise ValueError('payroll multiplier must include base wage')
    staff_hours=operating_days*open_hours*people_on_duty
    components={'staff':staff_hours*hourly_wage*payroll_multiplier,
                'power':operating_days*open_hours*electricity_kwh_per_hour*electricity_usd_per_kwh,
                'consumables':operating_days*visits_per_day*consumables_per_visit,
                'maintenance_insurance':maintenance_and_insurance,'storage':storage}
    return {'staff_hours':staff_hours,'components':components,'total':sum(components.values()),
            'inputs':values,'scope':'ASSUME operating envelope; not a procurement quote or empirical annual cost'}
