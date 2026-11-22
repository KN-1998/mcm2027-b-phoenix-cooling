"""Recheck reviewer claims and build an unambiguous index without rewriting frozen runs.

Run after committing source: python tools/review_delivery.py
"""
from pathlib import Path
import argparse
import copy
import csv
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.mch import runmeta
from src.mch.loaders import load_instance
from src.mch.static import solve_static, solve_static_maxmin
from tools.run_takeover_release import make_report


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def rows(path):
    with path.open(encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def save_rows(path, data):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='docs/reviews/20261122')
    args = parser.parse_args()
    out = (ROOT / args.out).resolve()
    if not out.is_relative_to((ROOT / 'docs/reviews').resolve()):
        raise ValueError('Review output must stay within docs/reviews; frozen results are read-only.')
    out.mkdir(parents=True, exist_ok=True)
    runtime = runmeta.meta(vars(args))
    if runtime['worktree_dirty']:
        raise RuntimeError('Commit source, tests and inputs before this review run')
    frozen = ROOT / 'results/completion_20261121'
    manifest_digest = sha(frozen / 'completion_manifest.json')
    manifest = load(frozen / 'completion_manifest.json')
    for relative, digest in manifest['sha256'].items():
        assert sha(frozen / relative) == digest, relative
    for meta_path in frozen.rglob('run_meta.json'):
        data = load(meta_path)
        assert data['git_sha'] == manifest['source_commit'] and not data['worktree_dirty']
        # The solver and inputs are unchanged; presentation/test tools have changed.
        for relative, digest in data['inputs'].items():
            assert sha(ROOT / relative) == digest, relative
        for relative, digest in data['source_sha256'].items():
            if relative.startswith('src/mch/'):
                assert sha(ROOT / relative) == digest, relative

    tests = subprocess.run([sys.executable, '-m', 'pytest', 'tests', '-q', '-rs'],
                           cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    (out / 'tests.log').write_text(tests.stdout + '\n' + tests.stderr, encoding='utf-8')
    if tests.returncode or re.search(r'\b\d+ skipped\b', tests.stdout):
        raise RuntimeError('Review requires passing tests and zero skips; see tests.log')
    passed = int(re.findall(r'(\d+) passed', tests.stdout)[-1])

    inst = load_instance()
    old_frontier = rows(frozen / 'base/core/p_frontier.csv')
    frontier = []
    for old in old_frontier:
        p = int(old['p'])
        eff, fair = solve_static(inst, p), solve_static_maxmin(inst, p)
        row = {'p': p, 'efficiency_unmet': eff.metrics['unmet_total_raw'],
               'efficiency_worst_all': eff.metrics['worst_unmet_ratio_raw'],
               'efficiency_worst_nonexempt': eff.metrics['worst_unmet_ratio_nonexempt_raw'],
               'maxmin_unmet': fair.metrics['unmet_total_raw'],
               'maxmin_worst_all': fair.metrics['worst_unmet_ratio_raw'],
               'maxmin_worst_nonexempt': fair.metrics['worst_unmet_ratio_nonexempt_raw'],
               'marginal_unmet_reduction': float(old['marginal_unmet_reduction'])}
        for field in ('efficiency_unmet', 'efficiency_worst_all', 'maxmin_unmet',
                      'maxmin_worst_all', 'maxmin_worst_nonexempt'):
            assert abs(row[field] - float(old[field])) < 1e-7, (p, field)
        frontier.append(row)
    p2 = frontier[2]
    assert p2['efficiency_worst_nonexempt'] == 1.0
    assert abs(p2['maxmin_worst_nonexempt'] - .575) < 1e-8
    save_rows(out / 'q1_objective_metrics.csv', frontier)

    scans = []
    for scale in (1, 3, 10):
        for capacity in (50, 100, 120, 250, 472, 500):
            case = copy.deepcopy(inst)
            case.demand = {key: value * scale for key, value in case.demand.items()}
            for site in case.fixed_sites():
                site.capacity = capacity
            sol = solve_static(case, 0)
            scans.append({'demand_scale': scale, 'all_fixed_capacity_assumed': capacity,
                          'p': 0, 'unmet_visits': sol.metrics['unmet_total_raw']})
    save_rows(out / 'capacity_scan.csv', scans)

    # Exercise the real report writer on a scratch copy, never the frozen package.
    with tempfile.TemporaryDirectory(prefix='phoenix_report_review_') as temp:
        scratch = Path(temp) / 'base'
        shutil.copytree(frozen / 'base', scratch)
        save_rows(scratch / 'core/p_frontier.csv', frontier)
        make_report(scratch, manifest['source_commit'])
        report = (scratch / 'RESULTS.md').read_text(encoding='utf-8')
        assert '效率解·非豁免最差率' in report and 'max-min解·非豁免最差率' in report
        assert '| 2 | 248.547 | 1.000 | 1.000 | 262.520 | 1.000 | 0.575 |' in report

    for script in ('tools/run_takeover_release.py', 'tools/run_completion_release.py'):
        guard = subprocess.run([sys.executable, script, '--out', str(frozen)], cwd=ROOT,
                               capture_output=True, text=True, encoding='utf-8')
        assert guard.returncode != 0 and 'Refusing to overwrite' in guard.stderr
    guard = subprocess.run([sys.executable, 'tools/review_delivery.py', '--out', str(frozen / 'base')],
                           cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    assert guard.returncode != 0 and 'Review output must stay within' in guard.stderr
    assert sha(frozen / 'completion_manifest.json') == manifest_digest
    for relative, digest in manifest['sha256'].items():
        assert sha(frozen / relative) == digest, relative

    inventory = load(out / 'archive_inventory.json')['files']
    indexed = {}
    raw_index = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=ROOT)
    for item in raw_index.split(b'\0'):
        if item:
            metadata, name = item.split(b'\t', 1)
            mode, blob, stage = metadata.decode().split()
            indexed[name.decode('utf-8')] = (mode, blob)
    for item in inventory:
        assert indexed[item['archived']] == (item['mode'], item['blob'])
        if item['old'] in indexed:
            assert item['old'] in {
                'results/takeover_20261120/core/district_gaps.png',
                'results/takeover_20261120/core/frontiers.png'}
            assert indexed[item['old']][1] == item['blob']

    costs = {row['scenario']: float(row['dp_total_spend'])
             for row in rows(frozen / 'base/q5/comparison.csv')}
    assert costs['base/base'] == 16060000 and costs['base/severe'] == 16620000
    lines = ['# 结果唯一入口与口径说明', '',
             '当前五问数值、图和实证的唯一冻结批次是 [completion_20261121](completion_20261121/README.md)。',
             '数值源为 `941c9fc`，发布提交为 `6f13bc2`；本次只修订索引/展示、资料测试与防覆盖保护，不把旧结果改签成新运算。', '',
             '## 测试计数属于不同批次', '',
             '| 批次 | 通过 | 跳过 | 解释 |', '|---|---|---|---|',
             '| 11月20日历史源 d070f5d | 94 | 7 | 历史冻结日志，不是当前代码状态 |',
             '| 11月21日数值源 941c9fc | 162 | 0 | 当前冻结数值包随附的验收 |',
             f'| 11月22日本次审查代码 | {passed} | 0 | 新增缺包/损坏输入检验；[本次日志](../docs/reviews/20261122/tests.log) |', '',
             '## Q1—Q2：每个指标明确所属目标解', '',
             '下表数值由相同求解器和输入复算，并逐项匹配冻结CSV；效率解的非豁免列是本次补记，非从max-min列借用。', '',
             '| p | 效率解·缺口 | 效率解·全区最差率 | 效率解·非豁免最差率 | max-min解·缺口 | max-min解·全区最差率 | max-min解·非豁免最差率 |',
             '|---|---|---|---|---|---|---|']
    for row in frontier:
        lines.append('| ' + str(row['p']) + ' | ' + ' | '.join(f'{row[key]:.3f}' for key in (
            'efficiency_unmet', 'efficiency_worst_all', 'efficiency_worst_nonexempt',
            'maxmin_unmet', 'maxmin_worst_all', 'maxmin_worst_nonexempt')) + ' |')
    lines += ['', 'D08只在公开的非豁免诊断集合之外，仍保留在全区统计；这里的率是未满足份额，越小越好。', '',
              '## 容量检验及范围', '',
              '真实训练周Jackson到访3304次，推得至少某天≥472次；这是该站某日已实现工作量的下界，不是日容量上限，不能转移到其他站。',
              '证据：[容量调和CSV](completion_20261121/empirical/capacity_reconciliation.csv)、[完整实证说明](../docs/EMPIRICAL_VALIDATION_20261121.md)。', '',
              '另在合成默认需求、原可达及营业时窗下，把所有固定站的假设日容量50→500，p=0缺口307.611→305.511；120/250/472/500均为305.511。',
              '这只能说明该情景扫描的边际瓶颈；需求×3时同一扫描1067.803→916.534，需求×10时4550.000→3076.112，容量仍能显著影响结果。不能据此验证真实容量或把距离与营业时窗效应分离。',
              '[本次18行情景扫描](../docs/reviews/20261122/capacity_scan.csv)。', '',
              '## Q5：费用必须连同情景名引用', '',
              '| 情景 | 五年DP费用（USD） |', '|---|---|',
              f"| base/base | {costs['base/base']:,.0f} |", f"| base/severe | {costs['base/severe']:,.0f} |", '',
              '英文稿的base/base $16.06M与冻结结果一致；反馈中的$16.62M属于base/severe。[原始对照CSV](completion_20261121/base/q5/comparison.csv)。', '',
              '## 历史与复算', '',
              '旧结果原样归档在 `_legacy/`，禁止用于当前取数；[历史说明](_legacy/README.md)记录94/7等计数的所属版本，原manifest和文件字节保留。',
              '`takeover_20261120/core/`只保留队友2702.tex引用的两张原图片及说明，保持编译路径兼容，没有旧plan.csv或run_meta。',
              '冻结包内部的原RESULTS.md保留以便校验原哈希；其中Q1列义由本页更正，不能按未限定的旧表头取数。',
              '当前复算请输出到新空目录，例如 `python tools/run_completion_release.py --out tmp/reproduce_completion`；程序拒绝覆盖已有目录。',
              '本次处理与英文稿审查见[反馈核对记录](../docs/reviews/20261122/REVIEW.md)。论文文件未改。', '']
    (ROOT / 'results/README.md').write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    receipt = {'generated_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'review_runtime': runtime, 'frozen_numeric_source': manifest['source_commit'],
               'frozen_result_hashes_unchanged': len(manifest['sha256']),
               'unchanged_scope': 'All frozen numeric inputs and src/mch solvers; presentation and tests updated',
               'archived_original_blob_count': len(inventory), 'tests_passed': passed, 'tests_skipped': 0,
               'q1_rows_recomputed_and_matched': len(frontier), 'capacity_scenarios': len(scans),
               'report_template_and_no_overwrite_guards_passed': True,
               'sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(out.iterdir())
                          if p.is_file() and p.name != 'review_manifest.json'}}
    receipt['sha256']['results/README.md'] = sha(ROOT / 'results/README.md')
    (out / 'review_manifest.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2),
                                               encoding='utf-8', newline='\n')
    print(json.dumps({key: receipt[key] for key in ('tests_passed', 'tests_skipped',
          'frozen_result_hashes_unchanged', 'archived_original_blob_count',
          'q1_rows_recomputed_and_matched', 'capacity_scenarios')}, indent=2))


if __name__ == '__main__':
    main()
