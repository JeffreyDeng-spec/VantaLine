"""Frozen manual history helper and full endpoint comparison before read optimization."""
import copy
import functools
import hashlib
import json
from pathlib import Path
import sys
from types import FunctionType, ModuleType
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.label_inspection import manual_history
import smoke_label_history_statistics as statistics
ROOT = Path(__file__).resolve().parents[1]
BASELINE_SHA256 = '52b31c4afe4ba42d2bd0ee9a5b1111fe3b5390b3e528848ce557e795c0d4227e'


@functools.lru_cache(maxsize=1)
def frozen_manual():
    path = ROOT / 'tests/backend_contract/manual_history_baseline.py'
    data = path.read_bytes().replace(b'\r\n', b'\n')
    assert hashlib.sha256(data).hexdigest() == BASELINE_SHA256, 'frozen manual helper changed'
    module = ModuleType('frozen_manual_history')
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


@functools.lru_cache(maxsize=1)
def parent_register():
    original = statistics.parent_register()
    namespace = dict(original.__globals__)
    namespace['manual_history'] = frozen_manual()
    return FunctionType(original.__code__, namespace, original.__name__, original.__defaults__, original.__closure__)


class ManualFixture(statistics.StatisticsFixture):
    def __enter__(self):
        # Capture before patching the adapter used by StatisticsFixture.
        register = parent_register()
        with patch.object(statistics, 'parent_register', return_value=register):
            return super().__enter__()


class MemoryRepository:
    def __init__(self, data): self.data = copy.deepcopy(data); self.calls = []
    def legacy(self, owner, kind):
        self.calls.append((owner, kind))
        return self.data.get(kind, [])


def outcome(function, data):
    try: return ('value', function(MemoryRepository(data), 'alice'))
    except Exception as error: return ('error', type(error).__name__, str(error))


class ManualContracts(unittest.TestCase):
    def test_mixed_duplicate_orphan_grouping_and_stable_detail_order(self):
        data = dict(
            standards=[dict(id='a', standard_type='manual', name='A'), dict(id='b', standard_type='manual', name='B')],
            sessions=[dict(id='duplicate', standard_id='a', updated_at=3), dict(id='duplicate', standard_id='b', updated_at=4),
                      dict(id='orphan', updated_at=2)],
            pages=[dict(id='dual', session_id='duplicate', standard_id='a', created_at=5, media_path='photo'),
                   dict(id='detached', session_id='orphan', created_at=1)],
            records=[dict(id='record', standard_id='a', standard_type='manual', created_at=5, media_path=''),
                     dict(id='ignored', standard_id='unknown', created_at=99)],
            assets=[dict(id='second', standard_id='a', ordinal=2), dict(id='first', standard_id='a', ordinal=1)])
        expected = outcome(frozen_manual().rows, data)
        self.assertEqual(outcome(manual_history.rows, data), expected)
        rows = {r['id']: r for r in expected[1]}
        self.assertEqual([r['id'] for r in rows['legacy-manual:a']['manual_history']['pages']], ['dual', 'record'])
        self.assertEqual([r['id'] for r in rows['legacy-manual:b']['manual_history']['pages']], ['dual'])
        self.assertEqual([r['id'] for r in rows['legacy-manual:a']['manual_history']['standards']], ['first', 'second'])
        self.assertTrue(rows['legacy-manual:a']['manual_history']['pages'][0]['has_photo'])
        for identity in ['legacy-manual:a', 'legacy-manual:dual', 'legacy-manual:orphan']:
            self.assertEqual(manual_history.resolve(MemoryRepository(data), 'alice', identity),
                             frozen_manual().resolve(MemoryRepository(data), 'alice', identity))

    def test_wrong_shape_and_detail_validation_are_not_hidden(self):
        baseline = dict(standards=[dict(id='a', standard_type='manual')])
        cases = [dict(standards=[None]), dict(sessions=[{}]), dict(pages=[{}]),
                 dict(records=[None]), dict(assets=[dict(standard_id='a')]),
                 dict(assets=[dict(id='one', standard_id='a', ordinal=None), dict(id='two', standard_id='a', ordinal=2)]),
                 dict(sessions=[dict(id='s', standard_id='a', updated_at='invalid')]),
                 dict(pages=[dict(id='page', standard_id=['invalid'])])]
        for delta in cases:
            with self.subTest(delta=delta):
                data = {**baseline, **delta}; expected = outcome(frozen_manual().rows, data)
                self.assertEqual(expected[0], 'error'); self.assertEqual(outcome(manual_history.rows, data), expected)

    def test_frozen_helper_and_endpoint_namespace_do_not_follow_candidate_patch(self):
        original = frozen_manual().rows
        with patch.object(manual_history, 'rows', side_effect=AssertionError('candidate changed')):
            self.assertEqual(original(MemoryRepository({}), 'alice'), [])
            self.assertIs(parent_register().__globals__['manual_history'].rows, original)
            self.assertEqual(outcome(manual_history.rows, {})[0], 'error')


def postgres_contract():
    with ManualFixture() as f:
        f.insert('label_inspection_objects', [f.task('native'), f.run('native-run', 'native')])
        f.insert('text_inspection_standards', [dict(id='manual', owner_user_id='alice', standard_type='manual', name='Manual', updated_at=2),
            dict(id='neighbor', owner_user_id='bob', standard_type='manual', name='Neighbor')])
        f.insert('text_inspection_records', [dict(id='manual-record', owner_user_id='alice', standard_id='manual',
            standard_type='manual', created_at=4, updated_at=4, status='completed', decision='DIFFERENCES')])
        f.insert('text_inspection_assets', [dict(id='asset', owner_user_id='alice', standard_id='manual', ordinal=1)])
        original = f.traverse(True)
        assert f.traverse() == original
        assert 'legacy-manual:manual' in {r['id'] for r in original}
        assert 'legacy-manual:neighbor' not in {r['id'] for r in original}
        for params in [dict(q='Manual'), dict(source='legacy_manual'), dict(result='DIFFERENCES')]:
            selected = f.traverse(**params)
            assert selected == f.traverse(True, **params)
            assert {r['id'] for r in selected} == {'legacy-manual:manual'}
            actual = f.client.get(statistics.api.PREFIX+'/tasks', params=params)
            parent = f.parent_client.get(statistics.api.PREFIX+'/tasks', params=params)
            assert actual.status_code == parent.status_code == 200
            assert actual.json() == parent.json()
        page = f.page(True, limit=1); captured = page['items'][:]
        f.insert('label_inspection_objects', [f.task('new')])
        f.change('native', {**f.task('native'), 'name':'renamed', 'updated_at':100})
        while page['next_cursor']:
            page = f.page(cursor=page['next_cursor'], limit=1); captured.extend(page['items'])
        assert captured == original
        with patch.object(manual_history, 'rows', side_effect=AssertionError('candidate changed')):
            assert f.traverse(True)
            try: f.traverse()
            except AssertionError as error: assert str(error) == 'candidate changed'
            else: raise AssertionError('candidate unexpectedly used frozen helper')
        f.owner = 'bob'
        assert f.traverse() == f.traverse(True)
        assert {r['id'] for r in f.traverse()} == {'legacy-manual:neighbor'}
        print('PASS actual PostgreSQL mixed manual/native, owner/filter/cursor and independent frozen helper')


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ManualContracts)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful(): raise SystemExit(1)
    if '--postgres' in sys.argv: postgres_contract()
