"""Real PostgreSQL generation, old-writer invalidation and HTTP contracts."""
import copy
import json
from pathlib import Path
import sys
import unittest
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from psycopg.rows import dict_row
from psycopg.errors import NotNullViolation, LockNotAvailable
from smoke_manual_history_baseline import ManualFixture
from local_inspection_service.storage.legacy_list_projection import LegacyListProjection, normalize, _decode_source
from local_inspection_service.storage.label_inspection import LabelRepository
from local_inspection_service.storage.legacy_projection_schema import TABLES, migration_sql
from verify_migration_safety import validate_sql


def populate(f):
    f.insert('text_inspection_standards', [dict(id='a', standard_type='manual', name='A', updated_at=1),
                                          dict(id='b', standard_type='manual', name='B', updated_at=2)])
    f.insert('text_inspection_manual_sessions', [dict(id='session', standard_id='a', updated_at=3),
                                                dict(id='orphan', updated_at=2)])
    f.insert('text_inspection_manual_pages', [dict(id='p', session_id='session', standard_id='b', created_at=5, decision='MATCH'),
                                            dict(id='overlap', session_id='orphan', standard_id='a', created_at=4)])
    f.insert('text_inspection_records', [dict(id='r', standard_type='manual', standard_id='a', created_at=6, decision=None)])
    f.insert('text_inspection_assets', [dict(id='asset', standard_id='a', ordinal=1)])


class Contracts(unittest.TestCase):
    def test_real_endpoint_counts_cross_membership_owner_detail_and_cursor(self):
        with ManualFixture() as f:
            populate(f)
            expected = f.traverse(True)
            store = LegacyListProjection(f.other)
            self.assertTrue(store.publish('alice'))
            with patch.object(LabelRepository, 'legacy', side_effect=AssertionError('manual raw source reread')):
                # Beta remains its original separately sampled SQL list reader.
                self.assertEqual(f.traverse(), expected)
            self.assertIsNone(f.repo.list_legacy_summary('bob', []))
            page = f.page(limit=1)
            f.insert('text_inspection_manual_pages', [dict(id='new', standard_id='a', created_at=99, decision='DIFFERENCES')])
            self.assertIsNone(f.repo.list_legacy_summary('alice', []))
            items = page['items'][:]
            while page['next_cursor']:
                page = f.page(cursor=page['next_cursor'], limit=1)
                items.extend(page['items'])
            self.assertEqual(items, expected)
            self.assertEqual(f.traverse(), f.traverse(True))
            self.assertTrue(store.publish('alice'))
            f.reader.connection.row_factory = dict_row
            f.other.connection.row_factory = dict_row
            self.assertTrue(store.publish('alice'))
            self.assertEqual(f.traverse(), f.traverse(True))
            f.repo.legacy('alice', 'standards')
            self.assertIsNone(f.repo.list_legacy_summary('alice', []))
            f.repo._legacy_cache.clear()
            for malformed in ([], {}, "", 0):
                self.assertIsNone(f.repo.list_legacy_summary("alice", [{"legacy_id": malformed}]))
            self.assertIsNone(f.repo.list_legacy_summary('alice', [{'legacy_id': 'a'}]))

    def test_non_manual_standard_cannot_supply_manual_history_clock(self):
        with ManualFixture() as f:
            f.insert('text_inspection_standards', [
                dict(id='label', standard_type='label', name='L', updated_at=1000),
                dict(id='manual', standard_type='manual', name='M', updated_at=2)])
            f.insert('text_inspection_manual_pages', [
                dict(id='cross-kind', standard_id='label', created_at=1, decision='MATCH')])
            expected = f.traverse(True)
            manual = next(row for row in expected if row['id'] == 'legacy-manual:label')
            self.assertEqual(manual['updated_at'], 1)
            self.assertEqual(manual['name'], '原说明书订单缺失')
            self.assertTrue(LegacyListProjection(f.other).publish('alice'))
            with patch.object(LabelRepository, 'legacy', side_effect=AssertionError('raw reread')):
                self.assertEqual(f.traverse(), expected)

    def test_every_old_writer_source_and_truncate_invalidate(self):
        for name in TABLES.values():
            with self.subTest(table=name), ManualFixture() as f:
                populate(f)
                store = LegacyListProjection(f.other)
                self.assertTrue(store.publish('alice'))
                table = f.writer._qualified_table(name)
                f.insert(name, [dict(id='extra', standard_type='manual',
                                    standard_id='b', created_at=20, ordinal=2)])
                self.assertIsNone(f.repo.list_legacy_summary('alice', []))
                self.assertTrue(store.publish('alice'))
                f.writer.connection.execute(f'DELETE FROM {table} WHERE id=%s', ('extra',))
                f.writer.connection.commit()
                self.assertIsNone(f.repo.list_legacy_summary('alice', []))
                self.assertTrue(store.publish('alice'))
                f.writer.connection.execute(f'UPDATE {table} SET raw_json=raw_json WHERE owner_user_id=%s', ('alice',))
                f.writer.connection.commit()
                self.assertIsNone(f.repo.list_legacy_summary('alice', []))
                self.assertTrue(store.publish('alice'))
                f.writer.connection.execute(f'TRUNCATE {table}')
                f.writer.connection.commit()
                self.assertIsNone(f.repo.list_legacy_summary('alice', []))

    def test_replace_operations_commit_and_rollback_invalidate_atomically(self):
        for operation in ('replace_all', 'replace_tables'):
            with self.subTest(operation=operation), ManualFixture() as f:
                populate(f)
                store = LegacyListProjection(f.other)
                self.assertTrue(store.publish('alice'))
                expected = f.traverse()
                def replace(commit):
                    if operation == 'replace_all':
                        f.writer.replace_all('text_inspection_manual_pages', [], commit=commit)
                    else:
                        f.writer.replace_tables({'text_inspection_manual_pages': [],
                                                 'text_inspection_records': []}, commit=commit)
                replace(False)
                self.assertEqual(f.traverse(), expected)
                f.writer.connection.rollback()
                self.assertEqual(f.traverse(), expected)
                replace(True)
                self.assertIsNone(f.repo.list_legacy_summary('alice', []))
                self.assertEqual(f.traverse(), f.traverse(True))

    def test_final_epoch_lock_rejects_competing_publisher_and_writer(self):
        with ManualFixture() as f:
            populate(f)
            store = LegacyListProjection(f.other)
            self.assertTrue(store.publish('alice'))
            expected = f.traverse()
            acquired, release = Event(), Event()
            original = f.other._cursor
            class BlockingCursor:
                def __init__(self): self.inner = original()
                def __getattr__(self, name): return getattr(self.inner, name)
                def execute(self, sql, *args, **kwargs):
                    result = self.inner.execute(sql, *args, **kwargs)
                    if sql.startswith('SELECT sequence FROM') and sql.endswith('FOR UPDATE'):
                        acquired.set()
                        if not release.wait(5): raise TimeoutError('test epoch barrier')
                    return result
            contender = f.raw()
            cursor_factory = type(f.other)._cursor
            def selected_cursor(repository):
                return BlockingCursor() if repository is f.other else cursor_factory(repository)
            with patch.object(type(f.other), '_cursor', selected_cursor), ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(store.publish, 'alice')
                try:
                    self.assertTrue(acquired.wait(5))
                    self.assertEqual(f.traverse(), expected)
                    with self.assertRaises(LockNotAvailable):
                        LegacyListProjection(contender).publish('alice')
                    self.assertEqual(contender.connection.info.transaction_status, 0)
                    f.writer.connection.execute("SET LOCAL lock_timeout='100ms'")
                    with self.assertRaises(LockNotAvailable):
                        f.writer.connection.execute(
                            f'UPDATE {f.writer._qualified_table("text_inspection_manual_pages")} '
                            'SET raw_json=raw_json WHERE id=%s', ('p',))
                    f.writer.connection.rollback()
                    self.assertEqual(f.traverse(), expected)
                finally:
                    release.set()
                self.assertTrue(pending.result(timeout=5))
            self.assertEqual(f.traverse(), expected)
            f.writer.connection.execute(
                f'UPDATE {f.writer._qualified_table("text_inspection_manual_pages")} '
                'SET raw_json=raw_json WHERE id=%s', ('p',))
            f.writer.connection.commit()
            self.assertIsNone(f.repo.list_legacy_summary('alice', []))

    def test_cas_rejects_commit_during_proof_and_rolls_back_derived_changes(self):
        with ManualFixture() as f:
            populate(f)
            store = LegacyListProjection(f.other)
            def change(sources):
                f.writer.connection.execute(f'UPDATE {f.writer._qualified_table("text_inspection_manual_pages")} '
                                            'SET raw_json=raw_json WHERE id=%s', ('p',))
                f.writer.connection.commit()
                return normalize(sources)
            with patch('local_inspection_service.storage.legacy_list_projection.normalize', side_effect=change):
                self.assertFalse(store.publish('alice'))
            self.assertIsNone(f.repo.list_legacy_summary('alice', []))
            self.assertTrue(store.publish('alice'))
            prior = f.traverse()
            with patch('local_inspection_service.storage.legacy_list_projection.json.dumps', side_effect=RuntimeError('synthetic')):
                with self.assertRaises(RuntimeError):
                    store.publish('alice')
            self.assertEqual(f.traverse(), prior)
            self.assertEqual(f.other.connection.info.transaction_status, 0)

    def test_ties_unknown_shapes_mixed_and_deep_payloads_use_original(self):
        with ManualFixture() as f:
            populate(f)
            store = LegacyListProjection(f.other)
            f.insert('text_inspection_records', [dict(id='tie', standard_type='manual', standard_id='a', created_at=6, decision='MATCH')])
            self.assertFalse(store.publish('alice'))
            self.assertEqual(f.traverse(), f.traverse(True))
            f.writer.connection.execute(f'DELETE FROM {f.writer._qualified_table("text_inspection_records")} WHERE id=%s', ('tie',))
            f.writer.connection.commit()
            f.insert('text_inspection_standards', [dict(id='label', standard_type='label', name='L')])
            self.assertTrue(store.publish('alice'))
            self.assertEqual(f.traverse(), f.traverse(True))
            f.writer.connection.execute(f'DELETE FROM {f.writer._qualified_table("text_inspection_standards")} WHERE id=%s', ('label',))
            f.writer.connection.commit()
            data = 'deep'
            for _ in range(40):
                data = {'nested': data}
            f.writer.connection.execute(f'UPDATE {f.writer._qualified_table("text_inspection_manual_pages")} '
                                        'SET raw_json=jsonb_set(raw_json,\'{unknown}\',%s::jsonb) WHERE id=%s', (json.dumps(data), 'p'))
            f.writer.connection.commit()
            self.assertFalse(store.publish('alice'))
            self.assertEqual(f.traverse(), f.traverse(True))

    def test_partial_derived_insert_failure_rolls_back_deleted_rows_and_readiness(self):
        with ManualFixture() as f:
            populate(f)
            store = LegacyListProjection(f.other)
            self.assertTrue(store.publish('alice'))
            expected = f.traverse()
            def generation():
                rows = f.writer.connection.execute(
                    f'SELECT group_id,kind,ordinal,raw_json FROM {store.rows} '
                    'WHERE owner_user_id=%s ORDER BY group_id,kind,ordinal', ('alice',)).fetchall()
                ready = f.writer.connection.execute(
                    f'SELECT sequence,projection_version FROM {store.ready} WHERE owner_user_id=%s',
                    ('alice',)).fetchone()
                f.writer.connection.commit()
                return rows, ready
            prior = generation()
            original = type(f.other)._cursor
            opened, events = [], []
            sentinel = RuntimeError('partial derived insertion sentinel')
            class FailingCursor:
                def __init__(self, inner): self.inner = inner; opened.append(inner)
                def __getattr__(self, name): return getattr(self.inner, name)
                def execute(self, sql, *args, **kwargs):
                    result = self.inner.execute(sql, *args, **kwargs)
                    if sql.startswith(f'DELETE FROM {store.rows}'):
                        events.append('deleted')
                    return result
                def executemany(self, sql, values, *args, **kwargs):
                    self.inner.executemany(sql, values[:1], *args, **kwargs)
                    events.append('inserted-one')
                    raise sentinel
            def cursor(repository):
                inner = original(repository)
                return FailingCursor(inner) if repository is f.other else inner
            with patch.object(type(f.other), '_cursor', cursor):
                with self.assertRaises(RuntimeError) as raised:
                    store.publish('alice')
            self.assertIs(raised.exception, sentinel)
            self.assertEqual(events, ['deleted', 'inserted-one'])
            self.assertTrue(opened[-1].closed)
            self.assertEqual(f.other.connection.info.transaction_status, 0)
            self.assertEqual(generation(), prior)
            self.assertEqual(f.traverse(), expected)
            self.assertTrue(store.publish('alice'))

    def test_overwritten_tokens_still_require_old_decoder_compatibility(self):
        for hidden in ('[' * 1200 + '0' + ']' * 1200, '9' * 700, 'NaN', '1e1000', '-0.0'):
            inner = '{"hidden":' + hidden + ',"hidden":0,"id":"page"}'
            self.assertIsNone(_decode_source(json.dumps(inner)))
        self.assertEqual(_decode_source(json.dumps('{"hidden":"[] 1e1000", "id":"page"}')),
                         {"hidden": "[] 1e1000", "id": "page"})

    def test_nonlatest_label_errors_and_manual_asset_errors_cannot_be_filtered_out(self):
        cases = [('text_inspection_records', 'old-label', 'diagnostics', 1),
                 ('text_inspection_records', 'old-label', 'diagnostics', {'elapsed_ms': 'bad'}),
                 ('text_inspection_assets', 'asset', 'ordinal', {})]
        for table, identity, field, malformed in cases:
            with self.subTest(field=field), ManualFixture() as f:
                populate(f)
                f.insert('text_inspection_assets', [dict(id='second-asset', standard_id='a', ordinal=2)])
                f.insert('text_inspection_standards', [dict(id='label', standard_type='label', name='L')])
                f.insert('text_inspection_records', [
                    dict(id='old-label', standard_type='label', standard_id='label', created_at=10, status='completed'),
                    dict(id='latest-label', standard_type='label', standard_id='label', created_at=20, status='completed')])
                f.writer.connection.execute(
                    f'UPDATE {f.writer._qualified_table(table)} SET raw_json=jsonb_set(raw_json,%s::text[],%s::jsonb) WHERE id=%s',
                    ([field], json.dumps(malformed), identity))
                f.writer.connection.commit()
                self.assertFalse(LegacyListProjection(f.other).publish('alice'))
                for query in ('', 'definitely-no-matching-order'):
                    outcomes = []
                    for baseline in (True, False):
                        try:
                            f.traverse(baseline, q=query)
                        except Exception as error:
                            outcomes.append((type(error).__name__, str(error)))
                        else:
                            self.fail('malformed history was hidden')
                    self.assertEqual(outcomes[0], outcomes[1])

    def test_mixed_label_orphan_unicode_batch_visibility_and_time_dependent_fallback(self):
        with ManualFixture() as f:
            populate(f)
            f.insert('text_inspection_standards', [dict(id='label', standard_type='label', name='Label'),
                     dict(id='unused-batch', standard_type='label', import_source='label-batch-v3', name='Hidden')])
            f.insert('text_inspection_records', [dict(id='古', standard_type='label', standard_id='label', created_at=8, decision='MATCH', status='completed'),
                     dict(id='z', standard_type='label', standard_id='label', created_at=8, decision='DIFFERENCES', status='failed'),
                     dict(id='orphan-label', standard_type='label', standard_id='gone', created_at=1)])
            store = LegacyListProjection(f.other)
            self.assertTrue(store.publish('alice'))
            self.assertEqual(f.traverse(), f.traverse(True))
            self.assertNotIn('legacy:unused-batch', {row['id'] for row in f.traverse()})
            expected = f.traverse(True)
            with patch.object(LabelRepository, 'legacy', side_effect=AssertionError('raw sources reread')):
                self.assertEqual(f.traverse(), expected)
            f.writer.connection.execute(f"UPDATE {f.writer._qualified_table('text_inspection_records')} SET raw_json=jsonb_set(raw_json,%s::text[],%s::jsonb) WHERE id=%s", (["status"], json.dumps("attempting"), "z"))
            f.writer.connection.commit()
            self.assertFalse(store.publish('alice'))
            self.assertEqual(f.traverse(), f.traverse(True))

    def test_owner_transfer_null_owner_rollback_delete_and_unknown_version(self):
        with ManualFixture() as f:
            populate(f)
            store = LegacyListProjection(f.other)
            self.assertTrue(store.publish('alice'))
            expected = f.traverse()
            source = f.writer._qualified_table('text_inspection_manual_pages')
            f.writer.connection.execute(f"UPDATE {source} SET owner_user_id=%s WHERE id=%s", ('bob', 'p'))
            self.assertEqual(f.traverse(), expected)  # Uncommitted old writer remains invisible.
            f.writer.connection.rollback()
            self.assertEqual(f.traverse(), expected)
            f.writer.connection.execute(f"UPDATE {source} SET owner_user_id=%s WHERE id=%s", ('bob', 'p'))
            f.writer.connection.commit()
            self.assertIsNone(f.repo.list_legacy_summary('alice', []))
            self.assertTrue(store.publish('bob'))
            with self.assertRaises(NotNullViolation):
                f.writer.connection.execute(f"UPDATE {source} SET owner_user_id=NULL WHERE id=%s", ('p',))
            f.writer.connection.rollback()
            self.assertIsNotNone(f.repo.list_legacy_summary('bob', []))
            self.assertTrue(store.publish('alice'))
            f.writer.connection.execute(f"UPDATE {store.ready} SET projection_version=999 WHERE owner_user_id=%s", ('alice',))
            f.writer.connection.execute(f"UPDATE {store.rows} SET raw_json=%s::jsonb WHERE kind=%s", (json.dumps({'created_at':'bad-cast'}), 'page'))
            f.writer.connection.commit()
            self.assertIsNone(f.repo.list_legacy_summary('alice', []))
            self.assertEqual(f.traverse(), f.traverse(True))
            self.assertTrue(store.publish('alice'))
            f.writer.connection.execute(f"DELETE FROM {source} WHERE owner_user_id=%s", ('alice',))
            f.writer.connection.commit()
            self.assertIsNone(f.repo.list_legacy_summary('alice', []))

    def test_missing_feature_falls_back_and_schema_replay_does_not_reset_epoch(self):
        with ManualFixture() as f:
            populate(f)
            store = LegacyListProjection(f.other)
            self.assertTrue(store.publish('alice'))
            expected = f.traverse()
            from local_inspection_service.storage.postgres_schema import postgres_ddl
            f.writer.connection.execute(postgres_ddl(f.schema))
            f.writer.connection.commit()
            self.assertEqual(f.traverse(), expected)
            f.writer.connection.execute(f'DROP TABLE {store.ready}')
            f.writer.connection.commit()
            self.assertEqual(f.traverse(), f.traverse(True))

    def test_owner_transfer_invalidates_both_existing_ready_generations(self):
        with ManualFixture() as f:
            populate(f)
            f.insert('text_inspection_standards', [dict(id='bob-standard', owner_user_id='bob', standard_type='manual')])
            f.insert('text_inspection_manual_pages', [dict(id='bob-page', owner_user_id='bob', standard_id='bob-standard', created_at=2)])
            store = LegacyListProjection(f.other)
            for owner in ('alice', 'bob'):
                self.assertTrue(store.publish(owner))
            before = {owner: f.repo.list_legacy_summary(owner, []) for owner in ('alice', 'bob')}
            self.assertTrue(all(value is not None for value in before.values()))
            source = f.writer._qualified_table('text_inspection_manual_pages')
            f.writer.connection.execute(f'UPDATE {source} SET owner_user_id=%s WHERE id=%s', ('bob', 'p'))
            for owner in ('alice', 'bob'):
                self.assertEqual(f.repo.list_legacy_summary(owner, []), before[owner])
            f.writer.connection.rollback()
            for owner in ('alice', 'bob'):
                self.assertEqual(f.repo.list_legacy_summary(owner, []), before[owner])
            f.writer.connection.execute(f'UPDATE {source} SET owner_user_id=%s WHERE id=%s', ('bob', 'p'))
            f.writer.connection.commit()
            for owner in ('alice', 'bob'):
                self.assertIsNone(f.repo.list_legacy_summary(owner, []))

    def test_actual_asset_writers_finish_after_epoch_or_source_wait(self):
        for mode in ('add/add', 'document/patch', 'document/same-patch', 'document/lazy-save'):
            with self.subTest(mode=mode):
                self.assert_actual_writers(mode)

    def assert_actual_writers(self, mode):
        with ManualFixture() as f:
            f.insert('text_inspection_standards', [
                dict(id=identity, owner_user_id='alice', standard_type='label',
                     name=identity, status='draft', revision_number=0)
                for identity in ('label-a', 'label-b')])
            if mode != 'add/add':
                f.insert('text_inspection_assets', [dict(id='asset-'+identity,
                    standard_id=identity, owner_user_id='alice', ordinal=1,
                    asset_kind='label_candidate', status='candidate', sha256='f'*64,
                    created_at=1, updated_at=1) for identity in ('label-a', 'label-b')])
            store = LegacyListProjection(f.reader)
            self.assertTrue(store.publish('alice'))
            first_inserted, second_started, release = Event(), Event(), Event()
            second = f.raw()
            original = type(f.other)._cursor
            assets = f.writer._qualified_table('text_inspection_assets')
            class ObservedCursor:
                def __init__(self, repository): self.repository=repository; self.inner=original(repository)
                def __getattr__(self, name): return getattr(self.inner, name)
                def execute(self, sql, *args, **kwargs):
                    first_write = sql.startswith(f'INSERT INTO {assets}') if mode == 'add/add' else sql.startswith(f'UPDATE {f.writer._qualified_table("text_inspection_standards")}')
                    second_write = sql.startswith('SELECT pg_advisory_xact_lock') if mode == 'document/same-patch' else (sql.startswith(f'UPDATE {assets}') if mode == 'document/patch' else sql.startswith(f'INSERT INTO {assets}'))
                    if second_write and self.repository is second:
                        second_started.set()
                    result = self.inner.execute(sql, *args, **kwargs)
                    if first_write and self.repository is f.other:
                        first_inserted.set()
                        if not release.wait(5): raise TimeoutError('native asset barrier')
                    return result
            def cursor(repository):
                return ObservedCursor(repository) if repository in (f.other, second) else original(repository)
            def add(repository, identity):
                if mode != 'add/add' and repository is f.other:
                    def change(standard, current_assets):
                        standard['updated_at'] = 2
                        for asset in current_assets: asset['updated_at'] = 2
                        return {'changed': True}
                    return repository.mutate_text_document(identity, 'alice', change)
                if mode in ('document/patch', 'document/same-patch'):
                    return repository.patch_text_inspection_asset(identity, 'asset-'+identity,
                        'alice', 'exclude', updated_at=2, revision_id='patch-'+identity)
                if mode == 'document/lazy-save':
                    from local_inspection_service.text_inspection.record_store import record_row
                    return repository.upsert_row('text_inspection_assets', record_row('assets',
                        dict(id='asset-label-a', standard_id='label-a', owner_user_id='alice',
                            asset_kind='label_candidate', status='candidate', sha256='f'*64,
                            ordinal=1, created_at=1, updated_at=3)))
                return repository.add_text_inspection_standard_asset(identity, 'alice',
                    dict(id='asset-'+identity, owner_user_id='alice', standard_id=identity,
                         asset_kind='label_candidate', status='candidate', sha256='f'*64,
                         created_at=1, updated_at=1), revision_id='revision-'+identity, updated_at=2)
            with patch.object(type(f.other), '_cursor', cursor), ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(add, f.other, 'label-a')
                try:
                    self.assertTrue(first_inserted.wait(5))
                    second_standard = 'label-a' if mode in ('document/lazy-save', 'document/same-patch') else 'label-b'
                    pending = pool.submit(add, second, second_standard)
                    self.assertTrue(second_started.wait(5))
                    blockers = []
                    for _ in range(100):
                        blockers = f.writer.connection.execute(
                            'SELECT pg_blocking_pids(%s)',
                            (second.connection.info.backend_pid,)).fetchone()[0]
                        f.writer.connection.commit()
                        if f.other.connection.info.backend_pid in blockers:
                            break
                        time.sleep(.01)
                    self.assertIn(f.other.connection.info.backend_pid, blockers)
                    with self.assertRaises(LockNotAvailable):
                        f.writer.connection.execute(
                            f'SELECT id FROM {f.writer._qualified_table("text_inspection_standards")} '
                            'WHERE id=%s FOR UPDATE NOWAIT', (second_standard,))
                    f.writer.connection.rollback()
                    self.assertFalse(pending.done())
                finally:
                    release.set()
                a, b = first.result(timeout=5), pending.result(timeout=5)
            if mode == 'add/add':
                self.assertEqual((a[1]['id'], b[1]['id']), ('label-a', 'label-b'))
            elif mode in ('document/patch', 'document/same-patch'):
                self.assertTrue(a['changed'])
                self.assertEqual(b[0]['status'], 'excluded')
            else:
                self.assertTrue(a['changed'])
                self.assertEqual(second.fetch_by_primary_key('text_inspection_assets',
                    {'id': 'asset-label-a'})['updated_at'], 3)
            self.assertEqual(f.other.connection.info.transaction_status, 0)
            self.assertEqual(second.connection.info.transaction_status, 0)
            self.assertIsNone(f.repo.list_legacy_summary('alice', []))
            self.assertTrue(store.publish('alice'))
            self.assertEqual(f.traverse(), f.traverse(True))

    def test_exact_migration_exception_does_not_authorize_mutated_sql(self):
        audited = migration_sql()
        validate_sql(audited, 'manual-derived')
        for sql in (audited.replace('legacy_projection_ready', 'users'),
                    audited.replace('sequence=sequence+1', 'sequence=0'),
                    audited.replace('SECURITY DEFINER', 'SECURITY INVOKER'),
                    audited.replace('COMMIT;', 'DELETE FROM vantaline.users; COMMIT;')):
            with self.assertRaises(ValueError):
                validate_sql(sql, 'mutated')


if __name__ == '__main__':
    unittest.main()
