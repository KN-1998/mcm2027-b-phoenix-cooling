"""Checks that detect target leakage, changing splits and calendar-gap errors."""
import copy
import datetime as dt
from pathlib import Path

import pytest

from src.mch.empirical import (validate,predict,score,MODELS,check_protocol,
                              extract_weekly_visits,load_noaa_tmax,attach_week_weather)


def fixture():
    start=dt.date(2026,5,4)
    return [{'start_date':(start+dt.timedelta(days=7*i)).isoformat(),
             'end_date':(start+dt.timedelta(days=7*i+6)).isoformat(),
             'included_full_week':True,'jackson_visits':100+i*10,
             'mean_tmax_f':95+i*.5} for i in range(20)]


def test_test_targets_cannot_change_selection_or_fitted_coefficients():
    original=fixture();changed=copy.deepcopy(original)
    for row in changed[-4:]:row['jackson_visits']*=100
    a,b=validate(original),validate(changed)
    assert a['selected_model']==b['selected_model']
    assert a['development_scores']==b['development_scores']
    assert a['coefficients']==b['coefficients']
    for model in MODELS:
        x=[r for r in a['predictions'] if r['model']==model and r['split']=='test'][0]
        y=[r for r in b['predictions'] if r['model']==model and r['split']=='test'][0]
        assert x['predicted']==y['predicted']


def test_predictions_only_receive_prior_rows_and_strictly_prior_cutoff():
    result=validate(fixture())
    assert all(p['information_cutoff']<p['start_date'] for p in result['predictions'])
    assert predict('last_week',[{'jackson_visits':17}],[])==17
    assert predict('last_4_weeks_mean',[{'jackson_visits':x} for x in [2,4,6,8]],[])==5


def test_gap_or_unsorted_calendar_is_rejected():
    rows=fixture();rows[7],rows[8]=rows[8],rows[7]
    with pytest.raises(ValueError,match='chronological'):validate(rows)
    rows=fixture();rows[8]['start_date']='2026-06-30'
    with pytest.raises(ValueError):validate(rows)


def test_test_target_nan_and_negative_are_rejected():
    for bad in (float('nan'),-1):
        rows=fixture();rows[-1]['jackson_visits']=bad
        with pytest.raises(ValueError,match='nonnegative'):validate(rows)


def test_error_metrics_have_correct_sign_and_units():
    result=score([{'observed':10,'predicted':12},{'observed':10,'predicted':6}])
    assert result['mae_visits_per_week']==3
    assert result['mean_signed_error_visits_per_week']==-1
    assert result['rmse_visits_per_week']==pytest.approx(10**.5)


def test_changed_protocol_is_not_silently_ignored():
    with pytest.raises(ValueError,match='protocol mismatch'):check_protocol({})


def test_zero_error_baseline_is_not_replaced_by_unnecessary_complexity():
    rows=fixture()
    for row in rows:row['jackson_visits']=100
    result=validate(rows)
    assert result['selected_model']=='last_week'


SOURCE=Path(__file__).resolve().parents[1]/'资料'/'12_实证补全_2026-11-21'


@pytest.mark.skipif(not (SOURCE/'raw').exists(),reason='official empirical source packet absent')
def test_official_weekly_columns_and_partial_periods_reconstruct_without_differencing():
    rows=extract_weekly_visits(SOURCE/'raw')
    assert len(rows)==22
    assert sum(bool(r['included_full_week']) for r in rows)==20
    june=[r for r in rows if r['week_id']==8][0]
    assert june['jackson_visits']==3304
    assert june['jackson_season_total']==12371
    assert june['aggregate_visits']==4282
    # Preserve the original documented inconsistency rather than 'repair' data.
    early=[r for r in rows if r['week_id']==2][0]
    assert early['aggregate_season_minus_site_sum']==-11
    weather=load_noaa_tmax(SOURCE/'noaa_2026_phoenix_sky_harbor_daily_summaries.csv')
    matched=attach_week_weather(rows,weather)
    assert len(matched)==22
    assert all(0<r['mean_tmax_f']<150 for r in matched)
