"""Audit saved run metadata without treating CRLF/LF conversion as data alteration."""
from pathlib import Path
import argparse
import hashlib
import json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    repo, out = args.repo.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in sorted((repo / 'results').rglob('run_meta.json')):
        meta = json.loads(p.read_text(encoding='utf-8-sig'))
        checks = []
        for name, expected in meta.get('inputs', {}).items():
            source = repo / 'data' / ('incoming' if name.startswith('incoming/') else 'processed') / name.removeprefix('incoming/')
            if source.exists():
                data = source.read_bytes()
                lf = data.replace(b'\r\n', b'\n')
                candidates = {'raw_bytes': data, 'LF': lf, 'CRLF': lf.replace(b'\n', b'\r\n')}
                values = {k: hashlib.sha256(v).hexdigest()[:len(expected)] for k, v in candidates.items()}
                matches = [k for k, v in values.items() if v == expected]
            else:
                values, matches = {}, []
            checks.append({'input': name, 'expected': expected, 'hash_candidates': values,
                           'matching_representations': matches})
        rows.append({'path': p.relative_to(repo).as_posix(), 'git_sha': meta.get('git_sha'),
                     'worktree_dirty': meta.get('worktree_dirty'), 'inputs': checks})
    top = [r for r in rows if len(Path(r['path']).parts) == 3]
    nested = [r for r in rows if len(Path(r['path']).parts) > 3]
    real_meta = json.loads((repo / 'results/real_network/run_meta.json').read_text(encoding='utf-8'))
    segments = json.loads((repo / 'results/segments/summary.json').read_text(encoding='utf-8'))
    result = {'reviewed_commit': 'c506b539fa61ac57b04fb822c8557e1cf3b003de',
              'top_level_meta_count': len(top),
              'top_level_clean_count': sum(not r['worktree_dirty'] for r in top),
              'top_level_shas': sorted({r['git_sha'] for r in top}),
              'nested_meta_count_not_in_top_level_manifest': len(nested),
              'raw_input_hash_mismatches': sum(not any(k == 'raw_bytes' for k in c['matching_representations']) for r in rows for c in r['inputs']),
              'inputs_not_explained_by_any_line_ending_representation': [
                  {'run': r['path'], 'input': c['input']} for r in rows for c in r['inputs'] if not c['matching_representations']],
              'note': 'Line-ending matching is a diagnostic, not proof of the exact bytes originally read. Raw hashes remain recorded; files are never normalized on disk.',
              'real_network_recorded_input_names': sorted(real_meta['inputs']),
              'MAG_actual_dependency_missing_from_metadata': '资料/02_降温网络/MAG/phoenix_2026_public_view_sites.csv',
              'segments_summary': segments,
              'segments_endpoint_increase_percent': 100 * (segments[-1]['unmet_total']/segments[0]['unmet_total']-1),
              'runs': rows}
    (out / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in {'runs', 'segments_summary', 'real_network_recorded_input_names'}}, ensure_ascii=True))


if __name__ == '__main__':
    main()
