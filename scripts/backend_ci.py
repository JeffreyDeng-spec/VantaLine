"""Explicit backend CI inventory, isolated runner, evidence gate and balancing tool.

Only synthetic tests are run here. The manifest preserves shell/env variants from
7bb2475; performance protocols have their own workflow, never the release gate.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'scripts/backend_ci_manifest.json'
BENCHMARKS = {
    'benchmark_label_history_statistics.py', 'benchmark_label_summary_reads.py',
    'benchmark_label_projection.py', 'benchmark_label_legacy_index.py',
    'benchmark_label_run_batch.py',
}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def digest(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def load_manifest(path=MANIFEST):
    manifest = json.loads(Path(path).read_text())
    assert manifest['schema'] == 1 and manifest['shard_count'] == 12
    checks = manifest['checks']
    ids = [item['id'] for item in checks + manifest['performance']]
    assert len(ids) == len(set(ids)), 'duplicate command identity'
    assert {item['shard'] for item in checks} == set(range(12)), 'missing shard'
    groups = defaultdict(set)
    for item in checks:
        groups[item['group']].add(item['shard'])
        assert item['cwd'] == '.' and '\n' not in item['run']
    assert all(len(shards) == 1 for shards in groups.values()), 'dependency group split'
    names = {next((name for name in BENCHMARKS if name in item['run']), None)
             for item in manifest['performance']}
    assert len(manifest['performance']) == 5 and names == BENCHMARKS
    assert not any('python scripts/benchmark_' in item['run'] for item in checks)
    return manifest


def verify(manifest):
    inventory = [{'run':e['run'], 'env':e['env'], 'cwd':e['cwd']}
                 for e in sorted(manifest['checks'] + manifest['performance'], key=lambda e:e['id'])]
    fingerprint = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
    assert fingerprint == (ROOT/'scripts/backend_ci_baseline.sha256').read_text().strip(), 'baseline command/env coverage changed'
    # PyYAML is part of the unchanged production lock, not needed by the gate.
    import yaml
    workflow = yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())
    shards = workflow['jobs']['backend-shards']
    assert shards['strategy']['matrix']['shard'] == list(range(12))
    assert shards['strategy']['fail-fast'] is False
    assert shards['strategy']['max-parallel'] == 12
    pr_trigger = workflow.get('on', workflow.get(True, {})).get('pull_request')
    assert pr_trigger is None or isinstance(pr_trigger, dict) and 'paths' not in pr_trigger
    for name in ['artifact-storage','doc-image-runtime','source-safety','release-package',
                 'documentation','frontend','codex-comparison']:
        assert workflow['jobs'][name]['needs'] == ['backend-shards']
        assert workflow['jobs'][name]['if'] == 'always()'
    gate_job = workflow['jobs']['backend-plc']
    assert gate_job['needs'] == ['backend-shards'] and gate_job['if'] == 'always()'
    performance = yaml.safe_load((ROOT/'.github/workflows/backend-performance.yml').read_text())
    triggers = performance.get('on', performance.get(True))
    assert triggers['schedule'] == [{'cron': '0 19 * * *'}]
    release = yaml.safe_load((ROOT/'.github/workflows/release-production.yml').read_text())
    release_triggers = release.get('on', release.get(True))
    assert release_triggers['workflow_run']['workflows'] == ['CI']
    for item in inventory:
        subprocess.run(['bash', '-n', '-c', item['run']], check=True)
    print(f"Coverage: {len(manifest['checks'])} ordinary commands + 5 unchanged benchmarks; 12 isolated shards.")


def execute(item, output, timeout=480):
    env = os.environ.copy()
    env.update(item['env'])
    record = {'id':item['id'], 'group':item['group'], 'run':item['run'],
              'started_at':timestamp(), 'status':'failed'}
    start = time.monotonic()
    print(f"::group::{item['id']} {item['run']}", flush=True)
    try:
        # Stream the same stdout to Actions and a durable artifact. Shell retains
        # the original assignment/expansion semantics and fails on pipeline errors.
        with (output / f"{item['id']}.log").open('w') as log:
            process = subprocess.Popen(['bash', '-eo', 'pipefail', '-c', item['run']],
                cwd=ROOT/item['cwd'], env=env, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True)
            try:
                record['returncode'] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                record['returncode'] = 124
                record['error'] = 'command timeout; process group terminated'
        # Flush at each command boundary; no buffering obscures its timing.
        print((output/f"{item['id']}.log").read_text(errors='replace'), flush=True)
        record['status'] = 'success' if record['returncode'] == 0 else 'failed'
    except Exception as error:
        record['error'] = f'{type(error).__name__}: {error}'
        record['returncode'] = 1
    finally:
        record['seconds'] = round(time.monotonic()-start, 3)
        record['completed_at'] = timestamp()
        print(f"{item['id']}: {record['status']} in {record['seconds']}s\n::endgroup::", flush=True)
    return record


def write_report(path, report):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2)+'\n')
    temporary.replace(path)


def run_shard(manifest, shard, output):
    assert 0 <= shard < 12
    output.mkdir(parents=True, exist_ok=True)
    report = {'schema':1, 'manifest_sha256':digest(manifest), 'shard':shard,
              'commit':os.environ.get('GITHUB_SHA', ''), 'run_id':os.environ.get('GITHUB_RUN_ID', ''),
              'run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT', ''),
              'started_at':timestamp(), 'status':'failed', 'commands':[]}
    path = output/f'shard-{shard}.json'
    write_report(path, report)
    checks = [item for item in manifest['checks'] if item['shard'] == shard]
    failed = False
    try:
        for item in checks:
            if failed and not item.get('always'):
                report['commands'].append({'id':item['id'], 'status':'skipped'})
            else:
                record = execute(item, output)
                report['commands'].append(record)
                failed |= record['status'] != 'success'
            write_report(path, report)
        report['status'] = 'failed' if failed else 'success'
    finally:
        report['completed_at'] = timestamp()
        write_report(path, report)
    return 1 if failed else 0


def validate_reports(manifest, reports, matrix_result, commit=None, run_id=None, attempt=None):
    assert matrix_result == 'success', f'matrix {matrix_result}; refusing green gate'
    assert len(reports) == 12, 'missing or extra shard report'
    assert {r['shard'] for r in reports} == set(range(12)), 'duplicate/missing shard'
    for report in reports:
        assert report['schema'] == 1 and report['manifest_sha256'] == digest(manifest)
        assert report['status'] == 'success' and report.get('completed_at'), 'incomplete shard'
        for field, expected in [('commit', commit), ('run_id', run_id), ('run_attempt', attempt)]:
            if expected is not None:
                assert report[field] == expected, f'stale {field}'
        expected = [item['id'] for item in manifest['checks'] if item['shard'] == report['shard']]
        actual = [item['id'] for item in report['commands']]
        assert actual == expected, 'missing, duplicate or reordered command'
        assert all(item['status'] == 'success' and item.get('returncode') == 0
                   and isinstance(item.get('seconds'), (int,float))
                   for item in report['commands']), 'failed/skipped/incomplete command'


def parse_time(value):
    return datetime.fromisoformat(value.replace('Z','+00:00'))


def summarize(manifest, reports, jobs):
    relevant = [job for job in jobs['jobs'] if job['name'].startswith('backend-shard-')]
    assert {job['name'] for job in relevant} == {f'backend-shard-{i}' for i in range(12)}, 'missing job timing'
    assert len(relevant) == 12 and all(j['conclusion']=='success' for j in relevant)
    earliest = min(parse_time(j['started_at']) for j in relevant)
    # Includes any later shard queueing and the aggregate job so the wall clock
    # cannot be made smaller by adding runner concurrency delays.
    seconds = (datetime.now(timezone.utc)-earliest).total_seconds()
    lines = ['## Backend CI evidence',
             f'Backend wall time through gate validation: **{seconds:.1f}s** (target ≤300s).',
             'Includes setup, later shard queueing and aggregation; initial GitHub queue excluded.',
             '', '| Shard | Job seconds (setup + tests) | Test seconds |', '| --- | ---: | ---: |']
    by_shard = {r['shard']:r for r in reports}
    for job in sorted(relevant,key=lambda j:int(j['name'].rsplit('-',1)[1])):
        shard = int(job['name'].rsplit('-',1)[1])
        duration=(parse_time(job['completed_at'])-parse_time(job['started_at'])).total_seconds()
        lines.append(f"| {shard} | {duration:.1f} | {sum(c['seconds'] for c in by_shard[shard]['commands']):.1f} |")
    lines += ['', '### Slowest 20 commands', '', '| Command | Seconds |', '| --- | ---: |']
    commands = [c for r in reports for c in r['commands']]
    for item in sorted(commands,key=lambda c:c['seconds'],reverse=True)[:20]:
        lines.append(f"| `{item['run'].replace('|','&#124;')}` | {item['seconds']:.3f} |")
    return '\n'.join(lines)+'\n'


def gate(manifest, directory, matrix_result, jobs):
    reports = [json.loads(p.read_text()) for p in sorted(directory.glob('shard-*.json'))]
    validate_reports(manifest, reports, matrix_result, os.environ.get('GITHUB_SHA'),
                     os.environ.get('GITHUB_RUN_ID'),os.environ.get('GITHUB_RUN_ATTEMPT'))
    summary = summarize(manifest, reports, json.loads(jobs.read_text()))
    print(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as handle:handle.write(summary)


def performance(manifest, output):
    output.mkdir(parents=True, exist_ok=True)
    # Frozen baseline used by the unchanged legacy benchmark is fetched and
    # hash-verified independently of ordinary smoke preparation.
    prep = [item for item in manifest['checks'] if item['run'].startswith('git fetch') and 'cf9c615' in item['run']
            or item['run'].startswith(('test ', 'git show ')) and 'cf9c615' in item['run']]
    checks = [item for item in manifest['checks'] if 'ci_benchmark_storage.py' in item['run']]
    start_checks = [item for item in checks if not item.get('always')]
    final_checks = [item for item in checks if item.get('always')]
    report = {'schema':1, 'manifest_sha256':digest(manifest), 'commands':[], 'status':'failed'}
    failed = False
    try:
        for item in start_checks + prep + manifest['performance']:
            record = execute(item, output, timeout=3000)
            report['commands'].append(record)
            write_report(output/'performance.json',report)
            if record['status'] != 'success':
                failed = True
                break
    except BaseException:
        failed = True
        raise
    finally:
        for item in final_checks:
            record = execute(item, output)
            report['commands'].append(record)
            failed |= record['status'] != 'success'
        report['status'] = 'failed' if failed else 'success'
        write_report(output/'performance.json',report)
    return int(failed)


def rebalance(manifest, directory):
    reports = [json.loads(p.read_text()) for p in directory.rglob('shard-*.json')]
    validate_reports(manifest, reports, 'success')
    times = {c['id']:c['seconds'] for r in reports for c in r['commands']}
    groups = defaultdict(list)
    for item in manifest['checks']:groups[item['group']].append(item)
    loads = [0.0]*12
    for name,items in sorted(groups.items(), key=lambda kv:(-sum(times[e['id']] for e in kv[1]),kv[0])):
        shard = min(range(12),key=lambda i:(loads[i],i))
        for item in items:item['shard']=shard
        loads[shard] += sum(times[e['id']] for e in items)
    MANIFEST.write_text(json.dumps(manifest,indent=2)+'\n')
    print('Fixed shard test-second estimates:', [round(value,2) for value in loads])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    sub.add_parser('verify')
    run=sub.add_parser('run');run.add_argument('--shard',type=int,required=True);run.add_argument('--output',type=Path,required=True)
    perf=sub.add_parser('performance');perf.add_argument('--output',type=Path,required=True)
    gate_parser=sub.add_parser('gate');gate_parser.add_argument('--results',type=Path,required=True);gate_parser.add_argument('--jobs',type=Path,required=True);gate_parser.add_argument('--matrix-result',required=True)
    balance=sub.add_parser('rebalance');balance.add_argument('--results',type=Path,required=True)
    args=parser.parse_args();manifest=load_manifest()
    if args.action=='verify':verify(manifest)
    elif args.action=='run':return run_shard(manifest,args.shard,args.output)
    elif args.action=='performance':return performance(manifest,args.output)
    elif args.action=='gate':gate(manifest,args.results,args.matrix_result,args.jobs)
    elif args.action=='rebalance':rebalance(manifest,args.results)
    return 0


if __name__=='__main__':sys.exit(main())
