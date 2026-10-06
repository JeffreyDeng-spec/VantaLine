"""Differential indexed grouping against the independent frozen manual helper."""
import copy
from functools import partial
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from smoke_manual_history_baseline import frozen_manual, manual_history, MemoryRepository, outcome
import smoke_manual_history_baseline as m
INDEXED = partial(manual_history.rows, indexed=True)


class IndexedHistory(unittest.TestCase):
    def test_seeded_duplicate_orphan_order_and_overlap_differential(self):
        for seed in range(160):
            rng=random.Random(seed)
            standards=[dict(id=rng.choice(['a','b','c']),standard_type='manual',name=str(i),updated_at=i) for i in range(6)]
            sessions=[dict(id=rng.choice(['s','t','u']),standard_id=rng.choice(['a','b','c',None,'']),created_at=i%3) for i in range(7)]
            pages=[dict(id='p'+str(i),session_id=rng.choice(['s','t','u',None,'']),standard_id=rng.choice(['a','b','c','gone',None,'']),created_at=i%2,media_path=rng.choice(['',None,'synthetic'])) for i in range(11)]
            records=[dict(id='r'+str(i),standard_type=rng.choice(['manual','label']),standard_id=rng.choice(['a','b','gone',None]),created_at=i%2) for i in range(5)]
            assets=[dict(id='asset'+str(i),standard_id=rng.choice(['a','b','c','gone']),ordinal=rng.choice([-1,0,1,2])) for i in range(9)]
            data=dict(standards=standards,sessions=sessions,pages=pages,records=records,assets=assets)
            with self.subTest(seed=seed):self.assertEqual(outcome(INDEXED,data),outcome(frozen_manual().rows,data))

    def test_equal_ordinals_keep_both_forward_and_reverse_source_order(self):
        for ids in (['z', 'a'], ['a', 'z']):
            data=dict(standards=[dict(id='first',standard_type='manual'),dict(id='second',standard_type='manual')],
                      assets=[dict(id=identity,standard_id='first',ordinal=1) for identity in ids])
            repo=MemoryRepository(data)
            with patch.object(manual_history,'_indexes',wraps=manual_history._indexes) as observed:
                rows=INDEXED(repo,'alice')
            self.assertEqual(observed.call_count,1)
            self.assertEqual(rows,frozen_manual().rows(MemoryRepository(data),'alice'))
            first=next(row for row in rows if row['id']=='legacy-manual:first')
            self.assertEqual([asset['id'] for asset in first['manual_history']['standards']],ids)

    def test_error_shapes_and_precedence_match_original(self):
        base=dict(standards=[dict(id='a',standard_type='manual'),dict(id='b',standard_type='manual')])
        cases=[dict(sessions=[{}]),dict(pages=[{}]),dict(records=[None]),dict(assets=[dict(standard_id='a')]),
               dict(assets=[dict(id='one',standard_id='a',ordinal=None),dict(id='two',standard_id='a',ordinal=1)]),
               dict(sessions=[dict(id='s',standard_id='a',updated_at='bad')],assets=[dict(standard_id='b')]),
               dict(pages=[dict(id='p',standard_id=['bad'])]),dict(standards=[None]),
               dict(sessions=[dict(id='s',standard_id='a',updated_at=None)],assets=[None])]
        for delta in cases:
            with self.subTest(delta=delta):
                data={**base,**delta};expected=outcome(frozen_manual().rows,data)
                self.assertEqual(expected[0],'error');self.assertEqual(outcome(INDEXED,data),expected)

    def test_empty_single_group_and_default_detail_skip_index(self):
        with patch.object(manual_history,'_indexes',side_effect=AssertionError('unneeded index')):
            self.assertEqual(INDEXED(MemoryRepository({}),'alice'),[])
            data=dict(standards=[dict(id='a',standard_type='manual')])
            self.assertEqual(outcome(INDEXED,data),outcome(frozen_manual().rows,data))
            data['standards'].append(dict(id='b',standard_type='manual'))
            self.assertEqual(outcome(manual_history.rows,data),outcome(frozen_manual().rows,data))
        repo=MemoryRepository({});INDEXED(repo,'alice')
        self.assertNotIn(('alice','assets'),repo.calls)

    def test_cached_assets_are_loaded_once_after_key_discovery(self):
        data=dict(standards=[dict(id='a',standard_type='manual'),dict(id='b',standard_type='manual')])
        repo=MemoryRepository(data);self.assertEqual(INDEXED(repo,'alice'),frozen_manual().rows(MemoryRepository(data),'alice'))
        self.assertEqual(repo.calls,[('alice',name) for name in ('standards','sessions','pages','records','assets')])
        class FailedAssets(MemoryRepository):
            def legacy(self,owner,kind):
                if kind=='assets':raise RuntimeError('assets read')
                return super().legacy(owner,kind)
        for function in (INDEXED,frozen_manual().rows):
            with self.assertRaisesRegex(RuntimeError,'assets read'):function(FailedAssets(data),'alice')
            invalid={**data,'pages':[{}]}
            with self.assertRaises(KeyError):function(FailedAssets(invalid),'alice')

    def test_huge_integer_proof_does_not_convert_to_float(self):
        huge=10**1000
        data=dict(standards=[dict(id='a',standard_type='manual',updated_at=huge),dict(id='b',standard_type='manual')],
                  pages=[dict(id='page',standard_id='a',created_at=huge)],assets=[dict(id='asset',standard_id='a',ordinal=huge)])
        self.assertEqual(outcome(INDEXED,data),outcome(frozen_manual().rows,data))
        self.assertFalse(manual_history._number(float('inf')));self.assertFalse(manual_history._number(float('nan')))


@unittest.skipUnless('--postgres' in sys.argv, 'requires isolated synthetic PostgreSQL')
class IndexedPostgres(unittest.TestCase):
    def test_real_PG_multigroup_branch_ties_and_raw_duplicate_ids(self):
        with m.ManualFixture() as f:
            f.insert('text_inspection_standards', [dict(id=x, owner_user_id='alice', standard_type='manual', name=x) for x in ['a', 'b', 'c']])
            f.insert('text_inspection_manual_sessions', [dict(id='s1', owner_user_id='alice', standard_id='a'), dict(id='s2', owner_user_id='alice', standard_id='b')])
            table = f.writer._qualified_table('text_inspection_manual_sessions')
            f.writer.connection.execute(f"""UPDATE {table} SET raw_json=jsonb_set(raw_json,'{{id}}','"duplicate"')""")
            f.writer.connection.commit()
            f.insert('text_inspection_manual_pages', [dict(id='page', owner_user_id='alice', session_id='duplicate', standard_id='c', created_at=5, decision='MATCH')])
            f.insert('text_inspection_records', [dict(id='record', owner_user_id='alice', standard_id='a', standard_type='manual', created_at=5, decision='DIFFERENCES')])
            f.insert('text_inspection_assets', [dict(id='z', owner_user_id='alice', standard_id='a', ordinal=1), dict(id='a-asset', owner_user_id='alice', standard_id='a', ordinal=2)])
            assets = f.writer._qualified_table('text_inspection_assets')
            f.writer.connection.execute(f"UPDATE {assets} SET raw_json=jsonb_set(raw_json,'{{ordinal}}','1')")
            f.writer.connection.commit()
            original = m.manual_history._indexes
            seen = []

            def observe(repo, *args):
                result = original(repo, *args)
                seen.append((type(repo).__name__, result is not None))
                return result
            expected = f.traverse(True)
            with patch.object(m.manual_history, '_indexes', observe):
                actual = f.traverse()
            self.assertEqual(actual, expected)
            self.assertEqual(seen, [('LabelRepository', True)])
            mapped = {r['id']: r for r in actual}
            self.assertEqual(mapped['legacy-manual:a']['run_count'], 2)
            self.assertEqual(mapped['legacy-manual:b']['run_count'], 1)
            self.assertEqual(mapped['legacy-manual:c']['run_count'], 1)
            self.assertEqual(mapped['legacy-manual:a']['decision'], 'MATCH')
            old = m.frozen_manual().rows(f.repo, 'alice')
            new = INDEXED(f.repo, 'alice')
            self.assertEqual(old, new)
            a = next((r for r in new if r['id'] == 'legacy-manual:a'))
            self.assertEqual([x['id'] for x in a['manual_history']['pages']], ['page', 'record'])
            source_ids = [x['id'] for x in f.repo.legacy('alice', 'assets') if x.get('standard_id') == 'a']
            self.assertCountEqual(source_ids, ['z', 'a-asset'])
            self.assertEqual([x['id'] for x in a['manual_history']['standards']], source_ids)
            page = f.page(True, limit=1)
            captured = page['items'][:]
            f.insert('text_inspection_standards', [dict(id='new', owner_user_id='alice', standard_type='manual', name='new')])
            while page['next_cursor']:
                page = f.page(cursor=page['next_cursor'], limit=1)
                captured.extend(page['items'])
            self.assertEqual(captured, expected)


if __name__=='__main__':unittest.main(argv=[arg for arg in sys.argv if arg != '--postgres'])
