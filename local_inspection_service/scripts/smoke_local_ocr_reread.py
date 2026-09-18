"""Offline reread geometry, strict evidence, durable claims and deadline checks."""
import copy
import hashlib
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from local_inspection_service import local_ocr_reread as reread
from local_inspection_service import evidence_matching as matching
from local_inspection_service import qwen_evidence_jobs as jobs
from local_inspection_service import qwen_ocr_evidence as ocr
from local_inspection_service import standard_preparation as engine
from local_inspection_service.text_inspection.comparison_ports import ComparisonRecords, ComparisonMedia


def observation(text='Batterv Pack', identity='o'):
    return dict(id=identity, text=text, type='text', polygon=[[20,30],[130,30],[130,50],[20,50]],
                box=[.1,.15,.65,.25], order=0, confidence=None)


ELEMENTS = [dict(id='e', text='Battery Pack', type='text', state='keep', box=[.1,.1,.7,.2])]


class Tests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new('RGB', (200,200), 'white')
        self.rows = matching.direct(ELEMENTS, [observation()])
        self.request = matching.candidates(self.rows, [observation()])
        self.region = reread.select(self.image, self.request, [observation()])[0]

    def test_geometry_and_pixel_transport(self):
        self.assertEqual(self.region['source_box'], [16,26,134,54])
        self.assertEqual(self.region['padding'], 64)
        plain = reread.text_region(self.region)
        self.assertEqual(plain['input_size'], self.region['content_size'])
        self.assertEqual(plain['padding'], 0)
        raw = [dict(observation('Battery Pack'), polygon=[[64,64],[64+self.region['content_size'][0],64],
            [64+self.region['content_size'][0],64+self.region['content_size'][1]],[64,64+self.region['content_size'][1]]])]
        rows, mapped = reread.merge(self.rows, ELEMENTS, raw, self.region, 'advanced_recognition', 'a')
        self.assertEqual(rows[0]['state'], 'matched')
        self.assertEqual(mapped[0]['polygon'], [[16,26],[134,26],[134,54],[16,54]])
        self.assertEqual(rows[0]['evidence'][0]['evidence_id'], mapped[0]['id'])

    def test_padding_text_rejected_and_coarse_bounds_explicit(self):
        rows, mapped = reread.merge(self.rows, ELEMENTS, [observation('Battery Pack')], self.region, 'advanced_recognition', 'a')
        self.assertNotEqual(rows[0]['state'], 'matched')
        self.assertEqual(mapped, [])
        rows, mapped = reread.merge(self.rows, ELEMENTS, [observation('Battery Pack')], reread.text_region(self.region), 'text_recognition', 'b')
        self.assertEqual(rows[0]['state'], 'matched')
        self.assertEqual(mapped[0]['coordinate_precision'], 'crop_region_only')

    def test_independent_views_no_fuzzy_success(self):
        for text in ['Battery', 'Pack', 'Battery pack', 'Batterv Pack']:
            rows, _ = reread.merge(self.rows, ELEMENTS, [observation(text)], reread.text_region(self.region), 'text_recognition', 'b')
            self.assertNotEqual(rows[0]['state'], 'matched')
        done = matching.direct(ELEMENTS, [observation('Battery Pack')])
        rows, _ = reread.merge(done, ELEMENTS, [observation('wrong')], self.region, 'text_recognition', 'c')
        self.assertEqual(rows, done)
        self.assertFalse(reread.needs_text(self.region, self.request, done))

    def test_selection_limits_and_invalid_geometry(self):
        obs = [observation(identity=str(i)) for i in range(30)]
        request = dict(elements=[dict(element_id=str(i), expected='Battery Pack', evidence_ids=[str(i)]) for i in range(30)])
        self.assertEqual(len(reread.select(self.image, request, obs)), 8)
        obs[0]['polygon'][0][0] = float('nan')
        self.assertEqual(len(reread.select(self.image, request, obs)), 7)

    def test_small_padding_overhang_is_coarse_not_clamped(self):
        cw, ch = self.region['content_size']
        overhang = dict(observation('Battery Pack'), polygon=[[64,64],[65+cw,64],[65+cw,64+ch],[64,64+ch]])
        rows, mapped = reread.merge(self.rows, ELEMENTS, [overhang], self.region, 'advanced_recognition', 'c')
        self.assertEqual(rows[0]['state'], 'matched')
        self.assertEqual(mapped[0]['coordinate_precision'], 'crop_region_only')

    def test_job_claim_cache_account_and_no_auto_pass(self):
        store, files, calls = {}, {}, []
        def save(kind, value, insert_only=False):
            key = (kind, value['id'])
            if insert_only and key in store:
                return False
            store[key] = copy.deepcopy(value)
            return True
        def update(kind, value):
            old = store.get((kind, value['id']))
            if not old or old['status'] != 'attempting' or old['owner_user_id'] != value['owner_user_id']:
                return False
            return save(kind, value)
        def owned(kind, identity, owner):
            value = store.get((kind, identity))
            return copy.deepcopy(value) if value and value['owner_user_id'] == owner else None
        namespace = SimpleNamespace(_text_v2_save=save, _text_v2_update_attempt=update, _text_v2_owned=owned,
            _text_v2_media_path=lambda owner, standard, name: '/'+owner+'/'+standard+'/'+name,
            _text_v2_write=lambda path, blob: files.update({path:blob}),
            sha256_bytes=lambda data: hashlib.sha256(data).hexdigest(), clear_thread_runtime_repository_selection=lambda: None)
        blob = engine.png(self.image)
        def recognize(settings, data, size, timeout, **kwargs):
            self.assertTrue(any(k[0] == 'ocr_evidence' and v['status'] == 'attempting' for k,v in store.items()))
            calls.append(kwargs)
            if kwargs.get('region_text'):
                return [observation('Battery Pack')], {'usage': {'input_tokens': 2}}
            return [observation()], {}
        def run(identity, owner='u', enabled=True, deadline=120):
            record = dict(id=identity, owner_user_id=owner, standard_id='s', standard_asset_id='a',
                source_sha256=namespace.sha256_bytes(blob), status='attempting', created_at=time.time(), deadline_at=time.time()+deadline,
                diagnostics=dict(template=dict(id='t', elements=ELEMENTS), external_calls=0,
                    reread_version=reread.VERSION if enabled else None))
            save('records', record)
            with patch.object(ocr, 'recognize', recognize), patch.object(jobs, 'llm', return_value=({'mappings': []}, {})):
                jobs.run(
                    ComparisonRecords(lambda kind: [], save, owned, update, copy.deepcopy),
                    ComparisonMedia(namespace._text_v2_media_path, namespace._text_v2_write, namespace.sha256_bytes),
                    namespace.clear_thread_runtime_repository_selection,
                    SimpleNamespace(media=lambda *args: blob), record, blob, dict(model='test',api_key='fixture'), None)
            return store['records', identity]
        first = run('first')
        self.assertEqual(len(calls), 3)
        self.assertEqual(first['status'], 'completed')
        self.assertTrue(first['diagnostics']['element_presence_satisfied'])
        self.assertEqual(first['decision'], 'REVIEW_REQUIRED')
        again = run('again')
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(t['cache_hit'] for t in again['diagnostics']['rereads']))
        run('other', 'v')
        self.assertEqual(len(calls), 6)
        for key, value in store.items():
            if key[0] == 'ocr_evidence' and value.get('mode'):
                value['status'] = 'unknown'
        pending = run('pending')
        self.assertEqual(len(calls), 6)
        self.assertFalse(pending['diagnostics']['element_presence_satisfied'])
        off = run('off', enabled=False)
        self.assertNotIn('rereads', off['diagnostics'])
        count = len(calls)
        expired = run('expired', deadline=-1)
        self.assertEqual(len(calls), count)
        self.assertEqual(expired['status'], 'review_required')
        self.assertEqual(expired['diagnostics']['phase'], 'timeout')


if __name__ == '__main__':
    unittest.main()
