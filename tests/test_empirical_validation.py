"""Checks that detect target leakage, changing splits and calendar-gap errors."""
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import re
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
WEATHER_FILE='noaa_2026_phoenix_sky_harbor_daily_summaries.csv'
SOURCE_RECOVERY=('Restore the official source packet from Git (including source_manifest.json, '
                 'the 22 Week PDFs and the NOAA CSV); install dependencies with '
                 'python -m pip install -r requirements.txt.')


def _require_official_source_packet(source, *, pypdf_available=None):
    """Skip absent prerequisites, but never conceal corrupt delivered inputs.

    Only the source-reconstruction integration test calls this check.  The
    seven synthetic statistical tests above remain independent of the packet.
    The season-total PDF and operations publications are not used by this test.
    """
    manifest=source/'source_manifest.json'
    if not manifest.is_file():
        pytest.skip('Official empirical integration test needs source_manifest.json. '+SOURCE_RECOVERY)
    try:
        entries=json.loads(manifest.read_text(encoding='utf-8'))
        weeks=[e for e in entries if re.fullmatch(r'raw/Week\d+_[^/]+\.pdf',e['path'])]
        weather=[e for e in entries if e['path']==WEATHER_FILE]
        ids=[int(re.search(r'Week(\d+)_',e['path'])[1]) for e in weeks]
        if sorted(ids)!=list(range(1,23)) or len(weather)!=1:
            raise ValueError('expected one manifest entry for each Week1–22 and the NOAA CSV')
        required=weeks+weather
        for e in required:
            if not re.fullmatch('[0-9a-f]{64}',e['sha256']):
                raise ValueError('invalid SHA256 for '+e['path'])
    except (OSError,ValueError,KeyError,TypeError) as exc:
        pytest.fail('Official empirical source manifest is invalid: '+str(exc)+'. '+SOURCE_RECOVERY,pytrace=False)
    # Check every present source before deciding to skip missing prerequisites.
    # A partial checkout with a second, truncated file is a corruption failure.
    missing=[]
    for e in required:
        path=source/e['path']
        if not path.is_file():
            missing.append(e['path'])
        elif hashlib.sha256(path.read_bytes()).hexdigest()!=e['sha256']:
            pytest.fail('Official empirical source SHA256 mismatch: '+e['path']+'. '+SOURCE_RECOVERY,pytrace=False)
    if pypdf_available is None:
        pypdf_available=importlib.util.find_spec('pypdf') is not None
    absent=(['pypdf'] if not pypdf_available else [])+missing
    if absent:
        pytest.skip('Official empirical integration test missing: '+', '.join(absent)+'. '+SOURCE_RECOVERY)


def test_official_weekly_columns_and_partial_periods_reconstruct_without_differencing():
    _require_official_source_packet(SOURCE)
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
    weather=load_noaa_tmax(SOURCE/WEATHER_FILE)
    matched=attach_week_weather(rows,weather)
    assert len(matched)==22
    assert all(0<r['mean_tmax_f']<150 for r in matched)


def _synthetic_source_packet(tmp_path):
    """Tiny byte fixtures for prerequisite/integrity handling, not PDF parsing."""
    entries=[]
    for week in range(1,23):
        name=f'raw/Week{week}_fixture.pdf'
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'%PDF-fixture\n'+str(week).encode('ascii')+b'\n%%EOF\n')
        entries.append({'path':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    path=tmp_path/WEATHER_FILE;path.write_bytes(b'STATION,TMAX\nUSW00023183,100\n')
    entries.append({'path':WEATHER_FILE,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    # An unused season-total entry must not make this test depend on that PDF.
    entries.append({'path':'raw/Heat Relief Sites 2026 Season Totals.pdf','sha256':'0'*64})
    (tmp_path/'source_manifest.json').write_text(json.dumps(entries),encoding='utf-8')
    return entries


def test_empirical_preflight_skips_absent_packet_with_recovery_instruction(tmp_path):
    with pytest.raises(pytest.skip.Exception,match='source_manifest.json.*Restore'):
        _require_official_source_packet(tmp_path,pypdf_available=True)


def test_empirical_preflight_skips_missing_prerequisites_with_specific_reason(tmp_path):
    _synthetic_source_packet(tmp_path)
    with pytest.raises(pytest.skip.Exception,match='missing: pypdf'):
        _require_official_source_packet(tmp_path,pypdf_available=False)
    (tmp_path/'raw/Week2_fixture.pdf').unlink()
    (tmp_path/WEATHER_FILE).unlink()
    with pytest.raises(pytest.skip.Exception) as skipped:
        _require_official_source_packet(tmp_path,pypdf_available=True)
    assert 'raw/Week2_fixture.pdf' in str(skipped.value)
    assert WEATHER_FILE in str(skipped.value)


def test_empirical_preflight_does_not_skip_truncation_even_with_missing_inputs(tmp_path):
    _synthetic_source_packet(tmp_path)
    path=tmp_path/'raw/Week1_fixture.pdf'
    path.write_bytes(path.read_bytes()[:-8])
    (tmp_path/'raw/Week2_fixture.pdf').unlink()
    with pytest.raises(pytest.fail.Exception,match='SHA256 mismatch: raw/Week1_fixture.pdf.*Restore'):
        _require_official_source_packet(tmp_path,pypdf_available=False)


def test_empirical_preflight_requires_only_inputs_used_by_reconstruction(tmp_path):
    _synthetic_source_packet(tmp_path)
    _require_official_source_packet(tmp_path,pypdf_available=True)
    assert not (tmp_path/'raw/Heat Relief Sites 2026 Season Totals.pdf').exists()


def test_empirical_preflight_rejects_incomplete_manifest_instead_of_skipping(tmp_path):
    entries=_synthetic_source_packet(tmp_path)
    (tmp_path/'source_manifest.json').write_text(json.dumps(entries[1:]),encoding='utf-8')
    with pytest.raises(pytest.fail.Exception,match='manifest is invalid.*Week1–22'):
        _require_official_source_packet(tmp_path,pypdf_available=True)
