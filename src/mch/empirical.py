"""Chronological validation of reported realized visits, not latent cooling demand.

The outcome is one fixed site's calendar-week intake count. These descriptive
forecast rules do not identify demand, geographic coverage or health effects.
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import re
from pathlib import Path
from typing import Sequence

import numpy as np
from scipy.optimize import nnls

MODELS = ('last_week', 'last_4_weeks_mean', 'nonnegative_AR1',
          'nonnegative_AR1_plus_lagged_heat_excess_100F')
BASELINES = MODELS[:2]
TRAIN_END = dt.date(2026, 7, 26)
SELECTION_END = dt.date(2026, 8, 23)
TEST_END = dt.date(2026, 9, 20)


def check_protocol(protocol: dict) -> None:
    """Fail on a changed split/model list instead of silently diverging from it."""
    expected = {
        'development_train_end':'2026-07-26',
        'development_selection':['2026-07-27','2026-08-23'],
        'locked_test':['2026-08-24','2026-09-20'],
        'models_fixed_before_full_extraction':list(MODELS),
    }
    for key,value in expected.items():
        if protocol.get(key)!=value:raise ValueError('locked protocol mismatch: '+key)


def _integer(token: str) -> int:
    return int(token.replace(',', ''))


def extract_weekly_visits(raw_dir: Path) -> list[dict]:
    """Parse the explicit weekly columns; never difference cumulative totals.

    Week dates are checked against each report header, not guessed from row
    order. Partial initial/final periods are retained with explicit exclusion.
    """
    from pypdf import PdfReader
    rows = []
    for path in sorted(raw_dir.glob('Week*.pdf')):
        week = int(re.match(r'Week(\d+)_', path.name).group(1))
        if week == 1:
            start, end = dt.date(2026,5,1), dt.date(2026,5,3)
        elif week == 22:
            start, end = dt.date(2026,9,21), dt.date(2026,9,30)
        else:
            start = dt.date(2026,5,4) + dt.timedelta(days=7*(week-2))
            end = start + dt.timedelta(days=6)
        pages = [p.extract_text() or '' for p in PdfReader(str(path)).pages]
        text = '\n'.join(pages)
        normalized = ' '.join(text.split())
        table = {}
        for key, expression in {
            'jackson':r'20\s+W\.?\s+Jackson\s+St\.?\s+([\d,]+)\s+([\d,]+)',
            'justa':r'Justa\s+Center\s+([\d,]+)\s+([\d,]+)',
            'cholla':r'Cholla\s+Library\*?\s+([\d,]+)\s+([\d,]+)',
            'aggregate':r'^\s*TOTAL[ \t]+([\d,]+)[ \t]+([\d,]+)[ \t\r]*$',
        }.items():
            matches = re.findall(expression,text if key=='aggregate' else normalized,re.I|re.M)
            if len(matches) != 1:
                raise ValueError(f'{path.name}: expected one {key} count pair, got {matches}')
            table[key+'_visits'], table[key+'_season_total'] = map(_integer,matches[0])
        table['aggregate_week_minus_site_sum'] = table['aggregate_visits']-sum(table[k+'_visits'] for k in ('jackson','justa','cholla'))
        table['aggregate_season_minus_site_sum'] = table['aggregate_season_total']-sum(table[k+'_season_total'] for k in ('jackson','justa','cholla'))
        at_a_glance = re.search(r'Report\s+Week\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)',normalized,re.I)
        table['overview_minus_aggregate_week'] = _integer(at_a_glance[2])-table['aggregate_visits'] if at_a_glance else None
        date_text = normalized[:180].lower()
        if start.strftime('%B').lower() not in date_text or str(end.day) not in date_text:
            raise ValueError(f'date header check failed: {path.name}')
        rows.append({'week_id':week,'start_date':start.isoformat(),'end_date':end.isoformat(),
                     'days':(end-start).days+1,'included_full_week':week not in (1,22),
                     **table,'source_pdf':path.name,'source_pdf_page':2,
                     'target_definition':'reported intake visits, not unique people or unmet demand'})
    rows.sort(key=lambda r:r['start_date'])
    if len(rows)!=22 or len({r['week_id'] for r in rows})!=22:
        raise ValueError('Expected all 22 posted 2026 reporting periods, without duplicates')
    for old,cur in zip(rows,rows[1:]):
        if dt.date.fromisoformat(cur['start_date']) != dt.date.fromisoformat(old['end_date'])+dt.timedelta(days=1):
            raise ValueError('gap or overlap in posted reporting dates')
        # Revisions/backfill can make this differ. Keep it as a quality flag,
        # never replace the week's directly reported target with the difference.
        cur['jackson_cumulative_difference'] = cur['jackson_season_total']-old['jackson_season_total']
        cur['jackson_week_minus_cumulative_difference'] = cur['jackson_visits']-cur['jackson_cumulative_difference']
    rows[0]['jackson_cumulative_difference']=rows[0]['jackson_visits']
    rows[0]['jackson_week_minus_cumulative_difference']=0
    return rows


def load_noaa_tmax(path: Path) -> dict[dt.date,float]:
    """NCEI daily-summaries standard units (F); retain only unflagged TMAX."""
    values={}
    with path.open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if row['STATION'] != 'USW00023183':
                raise ValueError('unexpected NOAA station')
            flags=row.get('TMAX_ATTRIBUTES','').split(',')
            if len(flags)>1 and flags[1]:
                raise ValueError('quality-flagged TMAX requires explicit review')
            value=float(row['TMAX'])
            if not math.isfinite(value) or not -50<=value<=150:
                raise ValueError('invalid Fahrenheit TMAX')
            date=dt.date.fromisoformat(row['DATE'])
            if date in values:raise ValueError('duplicate NOAA date')
            values[date]=value
    return values


def attach_week_weather(rows: Sequence[dict], tmax: dict[dt.date,float]) -> list[dict]:
    result=[]
    for row in rows:
        start=dt.date.fromisoformat(row['start_date'])
        dates=[start+dt.timedelta(days=i) for i in range(row['days'])]
        if any(d not in tmax for d in dates):
            raise ValueError('missing NOAA day; no weather interpolation allowed')
        values=[tmax[d] for d in dates]
        result.append({**row,'mean_tmax_f':float(np.mean(values)),
                       'max_tmax_f':max(values),'days_ge100f':sum(x>=100 for x in values)})
    return result


def _features(model: str, previous: dict) -> list[float]:
    if model=='nonnegative_AR1':return [1.0,float(previous['jackson_visits'])]
    if model=='nonnegative_AR1_plus_lagged_heat_excess_100F':
        return [1.0,float(previous['jackson_visits']),max(0.0,float(previous['mean_tmax_f'])-100)]
    raise ValueError('no fitted features for baseline')


def fit(model: str, history: Sequence[dict]) -> list[float]:
    if model not in MODELS:raise ValueError('unknown candidate')
    if model in BASELINES:return []
    if len(history)<3:raise ValueError('not enough training weeks')
    X=np.array([_features(model,history[i-1]) for i in range(1,len(history))])
    y=np.array([float(history[i]['jackson_visits']) for i in range(1,len(history))])
    return nnls(X,y)[0].tolist()


def predict(model: str, history: Sequence[dict], coefficients: Sequence[float]) -> float:
    """Prediction can only see past rows; the target week's row is not passed."""
    if not history:raise ValueError('empty history')
    if model=='last_week':return float(history[-1]['jackson_visits'])
    if model=='last_4_weeks_mean':
        return float(np.mean([float(r['jackson_visits']) for r in history[-4:]]))
    return max(0.0,float(np.dot(_features(model,history[-1]),coefficients)))


def score(rows: Sequence[dict]) -> dict:
    e=np.array([float(r['predicted'])-float(r['observed']) for r in rows])
    if not len(e):raise ValueError('empty evaluation set')
    return {'n':len(e),'mae_visits_per_week':float(np.mean(np.abs(e))),
            'rmse_visits_per_week':float(np.sqrt(np.mean(e**2))),
            'mean_signed_error_visits_per_week':float(np.mean(e))}


def validate(rows: Sequence[dict]) -> dict:
    """Fixed train/selection/test chronology, no test-score model reselection."""
    full=[r for r in rows if r['included_full_week']]
    if len(full)!=20:raise ValueError('Expected 20 full weeks under locked protocol')
    if full!=sorted(full,key=lambda r:r['start_date']):raise ValueError('weeks must be chronological')
    for old,cur in zip(full,full[1:]):
        if dt.date.fromisoformat(cur['start_date']) != dt.date.fromisoformat(old['end_date'])+dt.timedelta(days=1):
            raise ValueError('nonconsecutive full weeks invalidate lagged pairs')
    if any(not math.isfinite(float(r['jackson_visits'])) or float(r['jackson_visits'])<0 for r in full):
        raise ValueError('target must be finite and nonnegative')
    train=[r for r in full if dt.date.fromisoformat(r['end_date'])<=TRAIN_END]
    selection=[r for r in full if TRAIN_END<dt.date.fromisoformat(r['end_date'])<=SELECTION_END]
    test=[r for r in full if SELECTION_END<dt.date.fromisoformat(r['end_date'])<=TEST_END]
    if (len(train),len(selection),len(test))!=(12,4,4):raise ValueError('locked split changed')
    predictions=[];development={};coefficients={}
    for model in MODELS:
        beta=fit(model,train);history=list(train);p=[]
        coefficients[model]={'train':beta}
        for target in selection:
            row={'model':model,'split':'selection','start_date':target['start_date'],
                 'end_date':target['end_date'],'information_cutoff':history[-1]['end_date'],
                 'data_period_cutoff':history[-1]['end_date'],'actual_release_availability':'not_established',
                 'observed':target['jackson_visits'],'predicted':predict(model,history,beta)}
            p.append(row);history.append(target)
        predictions+=p;development[model]=score(p)
    best_baseline=min(BASELINES,key=lambda m:(development[m]['mae_visits_per_week'],MODELS.index(m)))
    best_complex=min(MODELS[2:],key=lambda m:(development[m]['mae_visits_per_week'],MODELS.index(m)))
    required=0.95*development[best_baseline]['mae_visits_per_week']
    selected=best_complex if required>0 and development[best_complex]['mae_visits_per_week']<=required else best_baseline
    test_scores={}
    # All candidates are shown diagnostically, but selected was fixed above.
    for model in MODELS:
        history=list(train)+list(selection);beta=fit(model,history)
        coefficients[model]['train_plus_selection']=beta;p=[]
        for target in test:
            row={'model':model,'split':'test','start_date':target['start_date'],
                 'end_date':target['end_date'],'information_cutoff':history[-1]['end_date'],
                 'data_period_cutoff':history[-1]['end_date'],'actual_release_availability':'not_established',
                 'observed':target['jackson_visits'],'predicted':predict(model,history,beta)}
            p.append(row);history.append(target)
        predictions+=p;test_scores[model]=score(p)
    return {'train_n':len(train),'selection_n':len(selection),'test_n':len(test),
            'development_scores':development,'test_scores':test_scores,'selected_model':selected,
            'selected_before_test':True,'selection_baseline':best_baseline,
            'complex_required_mae_at_most':required,'coefficients':coefficients,
            'predictions':predictions,'target':'20 W. Jackson St. weekly reported realized visits',
            'not_potential_demand_or_coverage_validation':True}
