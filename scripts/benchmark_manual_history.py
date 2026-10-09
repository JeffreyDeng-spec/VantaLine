"""Fixed full-endpoint manual history protocol; no HTTP transport timing."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import time
import tracemalloc
from unittest.mock import patch
from smoke_manual_history_baseline import ManualFixture, parent_register, BASELINE_SHA256, ROOT
from benchmark_label_summary_reads import CountingCursor, p95
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.legacy_list_projection import LegacyListProjection
from label_benchmark_evidence import snapshot, difference, preserve_primary

TASKS_SHA256 = 'ce5b2beaacf9b6d16957ed22470b2cec36da30596ad1fccab6f60cd4bf2bb086'
COMPARISON = 'manual full first page versus frozen tasks and complete manual helper'
PUBLISH_DERIVED = False


def arm(mode, variant):
    assert mode in ('AA', 'AB')
    return True if mode == 'AA' else variant


def measure(mode, repetition, size, reports):
    with ManualFixture() as f:
        populations = {
            'text_inspection_standards': [dict(id=f'manual_{i:05}', owner_user_id='alice', standard_type='manual', name=f'Manual {i}', created_at=i, updated_at=i) for i in range(size)],
            'text_inspection_manual_sessions': [dict(id=f'session_{i:05}', owner_user_id='alice', standard_id=f'manual_{i:05}', created_at=i, updated_at=i) for i in range(size)],
            'text_inspection_manual_pages': [dict(id=f'page_{i:05}', owner_user_id='alice', session_id=f'session_{i:05}', standard_id=f'manual_{i:05}', created_at=i, updated_at=i, status='completed', decision='MATCH', media_path='synthetic') for i in range(size)],
            'text_inspection_assets': [dict(id=f'asset_{i:05}', owner_user_id='alice', standard_id=f'manual_{i:05}', ordinal=1) for i in range(size)],
        }
        for name, values in populations.items():
            f.insert(name, values)
            table = f.writer._qualified_table(name)
            assert f.writer.connection.execute(f'SELECT count(*) FROM {table} WHERE owner_user_id=%s', ('alice',)).fetchone()[0] == size
            f.writer.connection.execute(f'ANALYZE {table}')
        f.writer.connection.commit()
        if PUBLISH_DERIVED:
            assert LegacyListProjection(f.other).publish(f.owner), "manual cohort not proven"
        expected = f.traverse(True)
        assert len(expected) == size and f.traverse() == expected
        assert [r['id'] for r in expected] == [f'legacy-manual:manual_{i:05}' for i in range(size-1, -1, -1)]
        del populations
        def cleanup_pages():
            f.writer.connection.execute(f"DELETE FROM {f.table} WHERE kind='page'"); f.writer.connection.commit()
        cleanup_pages()
        original = PostgresRuntimeRepository._cursor
        def run(variant, trace=False):
            calls = []
            def cursor(raw):
                result = original(raw)
                return CountingCursor(result, calls) if raw is f.reader else result
            gc.collect(); before = snapshot()
            if trace: tracemalloc.start()
            started = time.perf_counter()
            try:
                with patch.object(PostgresRuntimeRepository, '_cursor', cursor): page = f.page(arm(mode, variant))
                elapsed = time.perf_counter()-started
                peak = tracemalloc.get_traced_memory()[1] if trace else None
            finally:
                if trace: tracemalloc.stop()
            observed = difference(before, snapshot())
            assert page['items'] == expected[:100]
            expected_queries = 10 if arm(mode, variant) else (7 if PUBLISH_DERIVED else 12)
            assert len(calls) == expected_queries, (size, expected_queries, len(calls))
            cleanup_pages()
            return elapsed, peak, observed
        for _ in range(4): run(True); run(False)
        times = {True: [], False: []}; observations = {True: [], False: []}
        for iteration in range(31):
            for variant in ((True, False) if iteration%2 == 0 else (False, True)):
                elapsed, _, observed = run(variant)
                times[variant].append(elapsed); observations[variant].append(observed)
        peaks = {True: [], False: []}
        for iteration in range(3):
            for variant in ((True, False) if iteration%2 == 0 else (False, True)):
                _, peak, _ = run(variant, True); peaks[variant].append(peak)
        old, new = p95(times[True]), p95(times[False]); old_peak, new_peak = max(peaks[True]), max(peaks[False])
        report = dict(mode=mode, repetition=repetition, tasks=size, comparison=COMPARISON,
            fixture='ManualFixture', manual_baseline_sha256=BASELINE_SHA256, tasks_baseline_sha256=TASKS_SHA256,
            populations={name:size for name in ('standards','sessions','pages','assets')}, samples=31,
            old_seconds=times[True], new_seconds=times[False], old_p95_seconds=old, new_p95_seconds=new,
            old_peak_samples=peaks[True], new_peak_samples=peaks[False], old_peak_bytes=old_peak, new_peak_bytes=new_peak,
            old_queries=10, new_queries=(10 if mode == "AA" else (7 if PUBLISH_DERIVED else 12)), derived_published=PUBLISH_DERIVED, counting_scope='reader execute calls, including snapshot SQL; excludes setup/writer/commit/internal server work',
            latency_limit=max(old*1.25, old+.01), memory_limit=max(old_peak*1.25, old_peak+1024*1024),
            old_observations=observations[True], new_observations=observations[False])
        reports.append(report)
        try:
            assert new <= report['latency_limit'], 'manual first-page P95 regression'
            assert new_peak <= report['memory_limit'], 'manual first-page peak-memory regression'
        finally:
            preserve_primary(lambda: print(json.dumps(report), flush=True))


def execute_manual_protocol(measure, reports):
    plan = [('AA',0,1000)] + [('AB',rep,size) for rep in (1,2,3) for size in (1000,10000)]
    accounting = [dict(mode=mode,repetition=rep,tasks=size,status='not_run') for mode,rep,size in plan]
    try:
        for index, (mode, rep, size) in enumerate(plan):
            accounting[index]['status'] = 'running'
            try:
                offset = len(reports); measure(mode, rep, size, reports)
                actual = [(r['mode'],r['repetition'],r['tasks'],r['fixture'],r['manual_baseline_sha256'],r['tasks_baseline_sha256'],r['comparison']) for r in reports[offset:]]
                assert actual == [(mode,rep,size,'ManualFixture',BASELINE_SHA256,TASKS_SHA256,COMPARISON)], 'missing, duplicate, reordered or wrong baseline manual case'
            except BaseException:
                accounting[index]['status'] = 'failed'; raise
            accounting[index]['status'] = 'passed'
    finally:
        summary = dict(protocol='manual-history-repeated-v1',planned_aa_cases=1,planned_ab_cases=6,groups=accounting)
        reports.append(summary); preserve_primary(lambda: print(json.dumps(summary), flush=True))


def main():
    global PUBLISH_DERIVED
    parser = argparse.ArgumentParser(); parser.add_argument('--report'); parser.add_argument('--projection', action='store_true'); args = parser.parse_args(); reports = []
    PUBLISH_DERIVED = args.projection
    try:
        parent_register()
        assert hashlib.sha256((ROOT/'tests/backend_contract/label_history_tasks_baseline.py').read_bytes().replace(b'\r\n',b'\n')).hexdigest() == TASKS_SHA256
        execute_manual_protocol(measure, reports)
    finally:
        if args.report:
            def save():
                with Path(args.report).open('x',encoding='utf-8') as output: json.dump(reports, output, indent=2)
            preserve_primary(save)
    print('PASS manual A/A plus three complete1000/10000 repetitions; fixed query/memory/latency guards')


if __name__ == '__main__': main()
