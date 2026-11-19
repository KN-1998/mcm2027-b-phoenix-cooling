"""Read-only boundary checks. Run with --repo PATH --out PATH."""
from pathlib import Path
import argparse
import json
import sys
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument('--repo', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
repo, out = args.repo.resolve(), args.out.resolve()
out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(repo))
from src.mch.schema import District, Site, Instance
from src.mch.dynamic import solve_week_dp
from src.mch.disruption import plan_response
from src.mch.loaders import load_instance

districts = [District('D1', 'D1', 1000, .1, .1, 100000, .1, .5),
             District('D2', 'D2', 1000, .1, .1, 10000, .1, .5)]
sites = [Site('A', 'A', 'candidate_mch', 'D1', 0, 0, 250, 0, 24),
         Site('B', 'B', 'candidate_mch', 'D2', 0, 0, 250, 0, 24)]
demand = {('D1', 0): 100., ('D2', 0): 0., ('D1', 1): 0.,
          ('D2', 1): 50., ('D1', 2): 0., ('D2', 2): 100.}
fixture = Instance(districts, sites, {('D1', 'A'): 1, ('D2', 'B'): 1}, demand, 3)
with patch('src.mch.dynamic.move_time_hours', return_value=48.):
    week = solve_week_dp(fixture, 1, top_k=2)
response = plan_response(load_instance(), 8, mult=1., down_site='MCH-3')
result = {'reviewed_commit': '58dad31d0faf75a5a5742dcea47c314a1ac43fe9',
          'q3_multiday': week, 'q4_p8_closed_site': response,
          'scope': 'Deliberate algorithm boundary fixtures, not Phoenix observed journeys or capacity.',
          'checks': {'q3_still_serves_before_48h_arrival': bool(week['schedule'][2]['unmet'] == 0),
                     'q4_p8_loses_valid_partial_service_noop': bool(response['n_options'] == 0 and response['best'] is None)}}
assert all(result['checks'].values())
(out/'boundary_checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result['checks']))
