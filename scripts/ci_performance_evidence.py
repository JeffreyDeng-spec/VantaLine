"""Bind complete performance protocols to current CI jobs and actual artifacts."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import zipfile
from datetime import datetime

from backend_ci import ROOT, digest, performance_plan
import verify_refactor_performance_protocol as protocol

PROTOCOL_SHA256 = 'f4aee7c8fac4f33c955a2a82670066575f996786914f46accbb6f9b056ffb819'
MANUAL_MEMBERS = {'legacy-projection.json', 'manual-history.json'}


def validate_manual_producer(artifact, job, run_id, attempt):
    assert artifact['name'] == f'manual-history-performance-{attempt}'
    assert not artifact['expired'] and artifact['workflow_run']['id'] == int(run_id)
    assert job['run_attempt'] == int(attempt) and job['status'] == 'completed' and job['conclusion'] == 'success'
    utc = lambda value: datetime.fromisoformat(value.replace('Z', '+00:00'))
    assert utc(job['started_at']) <= utc(artifact['created_at']) <= utc(job['completed_at']), 'manual artifact predates producer'


def validate_manual_raw(data, manual, directory):
    path = directory/'manual-job.log'
    path.write_bytes(data)
    rows, binding, _ = protocol.read(path)
    for name, ready in [('legacy-projection.json', True), ('manual-history.json', False)]:
        expected = [r for r in manual['files'][name]['rows'] if r.get('fixture') == 'ManualFixture']
        actual = [r for r in rows if r.get('fixture') == 'ManualFixture' and r.get('derived_published') is ready]
        assert actual == expected, 'manual raw cases differ from actual artifact'
    actual_ledgers = [r for r in rows if r.get('protocol') == 'manual-history-repeated-v1']
    expected_ledgers = [protocol.one(manual['files'][name]['rows'], lambda r:r.get('protocol') == 'manual-history-repeated-v1', 'manual ledger') for name in ('legacy-projection.json','manual-history.json')]
    assert actual_ledgers == expected_ledgers, 'manual raw ledger order differs'
    return binding


def check_protocol_source():
    assert hashlib.sha256((ROOT/'scripts/verify_refactor_performance_protocol.py').read_bytes()).hexdigest() == PROTOCOL_SHA256, 'numeric protocol source changed'


def validate_performance(manifest, report, commit, run_id, attempt):
    assert report['schema'] == 1 and report['manifest_sha256'] == digest(manifest)
    assert report['status'] == 'success' and report['completed_at'] and report['not_run'] == []
    for field, value in [('commit', commit), ('run_id', run_id), ('run_attempt', attempt)]:
        assert report[field] == str(value), f'wrong performance {field}'
    plan = performance_plan(manifest)
    assert [c['id'] for c in report['commands']] == [e['id'] for e in plan], 'incomplete/reordered performance'
    for expected, actual in zip(plan, report['commands']):
        assert all(actual[k] == expected[k] for k in ('id', 'group', 'run', 'env', 'cwd')), 'performance command differs'
        assert actual['status'] == 'success' and actual['returncode'] == 0
        assert type(actual['seconds']) in (int, float) and actual['seconds'] >= 0


def read_manual_artifact(data, artifact):
    assert artifact['digest'] == 'sha256:'+hashlib.sha256(data).hexdigest(), 'manual artifact digest mismatch'
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        assert len(names) == 2 and set(names) == MANUAL_MEMBERS, 'unexpected manual members'
        assert sum(i.file_size for i in archive.infolist()) <= 2*1024*1024
        return {name:archive.read(name) for name in names}


def validate_manual(manual):
    check_protocol_source()
    assert set(manual['files']) == MANUAL_MEMBERS
    for name, ready in [('legacy-projection.json', True), ('manual-history.json', False)]:
        item = manual['files'][name]
        assert len(protocol.manual(item['rows'], ready)) == 7
        assert item['bytes'] > 0 and len(item['sha256']) == 64


def collect(api, manifest, jobs, sha, run_id, attempt):
    check_protocol_source()
    performance_dir = ROOT/'backend-performance'
    report = json.loads((performance_dir/'performance.json').read_text())
    validate_performance(manifest, report, sha, run_id, attempt)
    rows = []; raw = []
    for entry in performance_plan(manifest):
        values, binding, _ = protocol.read(performance_dir/f"{entry['id']}.log")
        rows += values; raw.append(binding)
    assert protocol.original(rows)['count'] == {'raw':54, 'rounded':2}
    assert len(protocol.beta(rows)) == 16
    assert protocol.storage(rows)['snapshots'] == 2
    run = api.get(f'actions/runs/{run_id}')
    artifacts = api.get(f'actions/runs/{run_id}/artifacts?per_page=100')['artifacts']
    selected = [a for a in artifacts if a['name'] == f'manual-history-performance-{attempt}']
    assert len(selected) == 1, 'missing/duplicate current manual artifact'
    artifact = selected[0]
    producer = [j for j in jobs['jobs'] if j['name'] == 'manual-history-performance']
    assert len(producer) == 1
    validate_manual_producer(artifact, producer[0], run_id, attempt)
    assert artifact['workflow_run']['head_sha'] == run['head_sha']
    members = read_manual_artifact(api.raw(f"actions/artifacts/{artifact['id']}/zip"), artifact)
    manual = {'artifact':artifact, 'files':{}, 'job_id':None}
    for name, data in members.items():
        assert (ROOT/'manual-history-performance'/name).read_bytes() == data, 'downloaded manual bytes differ'
        manual['files'][name] = dict(rows=json.loads(data), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    validate_manual(manual)
    manual['raw_log'] = validate_manual_raw(api.raw(f"actions/jobs/{producer[0]['id']}/logs"), manual, ROOT/'backend-results')
    for name in ('backend-performance', 'manual-history-performance'):
        matches = [j for j in jobs['jobs'] if j['name'] == name]
        assert len(matches) == 1 and matches[0]['run_attempt'] == int(attempt) and matches[0]['conclusion'] == 'success'
        if name == 'backend-performance':report['job_id'] = matches[0]['id']
        else:manual['job_id'] = matches[0]['id']
    report['raw_logs'] = raw
    report['numeric_protocols'] = {'original_raw':54, 'original_rounded':2, 'beta':16, 'storage_snapshots':2}
    return report, manual


def validate_reused(manifest, receipt, jobs):
    report = receipt['performance']
    validate_performance(manifest, report, receipt['tested_sha'], receipt['run_id'], receipt['run_attempt'])
    assert report['numeric_protocols'] == {'original_raw':54, 'original_rounded':2, 'beta':16, 'storage_snapshots':2}
    assert [Path(e['path']).name for e in report['raw_logs']] == [e['id']+'.log' for e in performance_plan(manifest)]
    for entry in report['raw_logs']:
        assert type(entry['bytes']) is int and entry['bytes'] >= 0 and len(entry['sha256']) == 64
        if entry['bytes'] == 0:
            assert Path(entry['path']).name in {'check-298.log', 'check-299.log'}, 'empty protocol log'
            assert entry['sha256'] == hashlib.sha256(b'').hexdigest(), 'wrong empty preparation digest'
    validate_manual(receipt['manual'])
    for name, proof in [('backend-performance', report), ('manual-history-performance', receipt['manual'])]:
        actual = [j for j in jobs['jobs'] if j['name'] == name]
        assert len(actual) == 1 and proof['job_id'] == actual[0]['id'], 'wrong performance producer'
        if name == 'manual-history-performance':
            validate_manual_producer(proof['artifact'], actual[0], receipt['run_id'], receipt['run_attempt'])
            assert proof['raw_log']['bytes'] > 0 and len(proof['raw_log']['sha256']) == 64


def verify_reused_artifact(api, receipt, run):
    old = receipt['manual']['artifact']
    artifact = api.get(f"actions/artifacts/{old['id']}")
    assert all(artifact[k] == old[k] for k in ('id', 'name', 'digest', 'size_in_bytes'))
    assert not artifact['expired'] and artifact['workflow_run']['id'] == run['id']
    assert artifact['workflow_run']['head_sha'] == run['head_sha']
    members = read_manual_artifact(api.raw(f"actions/artifacts/{artifact['id']}/zip"), artifact)
    for name, data in members.items():
        item = receipt['manual']['files'][name]
        assert len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256']
        assert json.loads(data) == item['rows']
    import tempfile
    with tempfile.TemporaryDirectory() as temporary:
        binding = validate_manual_raw(api.raw(f"actions/jobs/{receipt['manual']['job_id']}/logs"), receipt['manual'], Path(temporary))
    assert all(binding[k] == receipt['manual']['raw_log'][k] for k in ('bytes', 'sha256')), 'manual raw producer changed'
