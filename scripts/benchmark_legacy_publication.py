"""Observe explicit cold publication; separate from first-page performance gates.

Synthetic manual cohorts only. One sample per size is operational evidence,
not a P95 estimate or a production eligibility-rate prediction.
"""
import argparse
import json
import time
import tracemalloc
from unittest.mock import patch

from smoke_manual_history_baseline import ManualFixture
from local_inspection_service.storage.legacy_list_projection import LegacyListProjection


def measure(size):
    with ManualFixture() as fixture:
        populations = {
            'text_inspection_standards': [dict(id=f'manual_{i:05}', standard_type='manual', name=f'Manual {i}', created_at=i, updated_at=i) for i in range(size)],
            'text_inspection_manual_sessions': [dict(id=f'session_{i:05}', standard_id=f'manual_{i:05}', created_at=i, updated_at=i) for i in range(size)],
            'text_inspection_manual_pages': [dict(id=f'page_{i:05}', session_id=f'session_{i:05}', standard_id=f'manual_{i:05}', created_at=i, updated_at=i, status='completed', decision='MATCH', media_path='synthetic') for i in range(size)],
            'text_inspection_assets': [dict(id=f'asset_{i:05}', standard_id=f'manual_{i:05}', ordinal=1) for i in range(size)],
        }
        for table, rows in populations.items():
            fixture.insert(table, rows)
        del populations
        expected = fixture.traverse(True)
        assert len(expected) == size
        original = type(fixture.other)._cursor
        observed = {'source_json_utf8_bytes': 0, 'source_rows': 0}
        class Cursor:
            def __init__(self, inner): self.inner = inner; self.source = False
            def __getattr__(self, name): return getattr(self.inner, name)
            def execute(self, sql, *args, **kwargs):
                self.source = sql.startswith('SELECT id,raw_json::text AS raw_text')
                if sql.startswith('SELECT sequence FROM') and sql.endswith('FOR UPDATE'):
                    observed['lock_statement_started'] = time.perf_counter()
                result = self.inner.execute(sql, *args, **kwargs)
                return result
            def fetchall(self):
                rows = self.inner.fetchall()
                if self.source:
                    observed['source_rows'] += len(rows)
                    observed['source_json_utf8_bytes'] += sum(len(row[1].encode('utf8')) for row in rows)
                return rows
        def cursor(repository):
            inner = original(repository)
            return Cursor(inner) if repository is fixture.other else inner
        tracemalloc.start()
        started = time.perf_counter()
        try:
            with patch.object(type(fixture.other), '_cursor', cursor):
                published = LegacyListProjection(fixture.other).publish('alice')
            completed = time.perf_counter()
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        assert published
        assert fixture.other.connection.info.transaction_status == 0
        assert fixture.traverse() == expected
        assert observed['source_rows'] == size * 4
        assert observed['source_json_utf8_bytes'] > 0
        return dict(tasks=size, samples=1, traced_publication_seconds=completed-started,
                    peak_python_bytes=peak,
                    epoch_hold_upper_bound_seconds=completed-observed['lock_statement_started'],
                    source_rows=observed['source_rows'],
                    source_json_utf8_bytes=observed['source_json_utf8_bytes'],
                    synthetic_eligible_groups=size, synthetic_total_groups=size,
                    eligible_ratio=1.0,
                    limitations='traced single sample; lock upper bound includes SELECT waiting and cursor close; JSON payload bytes exclude wire overhead; synthetic manual eligibility only')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    reports = []
    try:
        for size in (1000, 10000):
            report = measure(size)
            reports.append(report)
            print(json.dumps(report), flush=True)
    finally:
        from pathlib import Path
        Path(args.output).write_text(json.dumps(reports, indent=2), encoding='utf8')


if __name__ == '__main__':
    main()
