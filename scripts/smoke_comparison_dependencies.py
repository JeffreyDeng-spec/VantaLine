"""Offline submission, captured dependencies, durable calls and late CAS behavior."""
import copy
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from PIL import Image
from local_inspection_service.text_inspection import comparison_jobs as comparison
from local_inspection_service import standard_preparation_compare as compatibility
from local_inspection_service.text_inspection.comparison_ports import ComparisonRecords, ComparisonMedia, ComparisonModels
from local_inspection_service import qwen_evidence_jobs as qwen
from local_inspection_service import standard_preparation as engine


class Fixture:
    def __init__(self, case, owner='alice'):
        temporary = tempfile.TemporaryDirectory(); case.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.owner = owner
        self.store = {}; self.events = []; self.workers = []; self.timers = []; self.clears = 0
        self.calls = []; self.provider_hook = lambda: None; self.fail_thread = False
        self.image = Image.new('RGB', (200, 100), 'white'); self.blob = engine.png(self.image)
        self.template = dict(id='template', sha256='prepared-hash', elements=[
            dict(id='e1', type='text', text='A20', state='keep', box=[.1,.1,.5,.2], clean_box=[.1,.1,.5,.2])])
        self.standard = dict(id='standard', current_revision_id='revision', revision_number=2, name='fixture')
        self.asset = dict(id='asset', ordinal=1)
        self.config = dict(provider='qwen', model='document-model', api_key='fixture', base_url='https://dashscope.aliyuncs.com')
        self.usage = Mock()
        self.mapping = Mock(side_effect=AssertionError('no mapping call expected'))
        self.namespace = dict(_text_v2_load=self.load, _text_v2_save=self.save, _text_v2_owned=self.owned,
            _text_v2_update_attempt=self.update, _text_v2_public=copy.deepcopy, _text_v2_media_path=self.path,
            _text_v2_write=self.write, sha256_bytes=lambda b: hashlib.sha256(b).hexdigest(), os=os,
            ai_detection_settings=self.settings, TEXT_INSPECTION_EXTERNAL_VLM_ENABLED=True,
            clear_thread_runtime_repository_selection=self.clear, record_model_call=self.usage)
        self.jobs = SimpleNamespace(observe=lambda *a,**k: self.observations(), media=lambda *a: self.blob)

    def load(self, kind): return [copy.deepcopy(v) for (k,_),v in self.store.items() if k == kind]
    def owned(self, kind, identity, owner):
        value = self.store.get((kind, identity))
        return copy.deepcopy(value) if value and value['owner_user_id'] == owner else None
    def save(self, kind, value, insert_only=False):
        self.events.append(('save', kind, value['id'], value.get('status'), insert_only))
        key = (kind, value['id'])
        if insert_only and key in self.store: return False
        self.store[key] = copy.deepcopy(value); return True
    def update(self, kind, value):
        old = self.store.get((kind, value['id']))
        self.events.append(('cas', kind, value['id'], value['status']))
        if not old or old['status'] != 'attempting' or old['owner_user_id'] != value['owner_user_id']: return False
        return self.save(kind, value)
    def path(self, owner, standard, name): return self.root / owner / standard / name
    def write(self, path, blob):
        self.events.append(('write', str(path))); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(blob)
    def settings(self, purpose):
        self.events.append(('settings', purpose))
        return {**self.config, 'model': qwen.ocr.MODEL} if purpose == 'ocr' else self.config
    def clear(self): self.clears += 1
    def observations(self): return [dict(id='o1', type='text', text='A20', confidence=1.0, box=[.1,.1,.5,.2], polygon=[[20,10],[120,10],[120,30],[20,30]], provenance='qwen_ocr')]
    def recognize(self, *args, **kwargs):
        claims = [v for (k,_),v in self.store.items() if k == 'ocr_evidence']
        assert any(v['status'] == 'attempting' for v in claims)
        records = [v for (k,_),v in self.store.items() if k == 'records']
        assert any(v['diagnostics'].get('model_audits') for v in records)
        assert kwargs['record_usage'] is self.usage
        self.calls.append(kwargs); self.provider_hook()
        return self.observations(), {}
    def model_ports(self):
        ns=self.namespace
        return ComparisonModels(ns['ai_detection_settings'], ns['TEXT_INSPECTION_EXTERNAL_VLM_ENABLED'], ns.get('record_model_call'))
    def submit(self, request='request_001', qwen_enabled=False, upload=None, reread_enabled=False):
        fixture = self
        class Thread:
            def __init__(self, **kwargs): self.kwargs = kwargs
            def start(self):
                if fixture.fail_thread: raise RuntimeError('thread unavailable')
                fixture.workers.append(self.kwargs)
        env = {'VANTALINE_QWEN_OCR_ACCOUNTS': self.owner if qwen_enabled else '', 'VANTALINE_QWEN_REREAD_ACCOUNTS': self.owner if reread_enabled else ''}
        with patch.dict(os.environ, env), patch.object(comparison.threading, 'Thread', Thread):
            ns=self.namespace
            return comparison.submit(
                ComparisonRecords(ns['_text_v2_load'],ns['_text_v2_save'],ns['_text_v2_owned'],ns['_text_v2_update_attempt'],ns['_text_v2_public']),
                ComparisonMedia(ns['_text_v2_media_path'],ns['_text_v2_write'],ns['sha256_bytes']), self.model_ports(),
                ns['clear_thread_runtime_repository_selection'],lambda name,default,env=ns['os']:env.getenv(name,default),
                self.jobs, self.owner, 'fixture', self.standard,
                self.asset, {'preparation': self.template}, self.blob if upload is None else upload, request, None)
    def run(self):
        fixture = self
        class Timer:
            def __init__(self, interval, callback): self.interval=interval; self.callback=callback; self.cancelled=False; fixture.timers.append(self)
            def start(self): pass
            def cancel(self): self.cancelled=True
        task = self.workers.pop(0)
        with patch.object(qwen.threading, 'Timer', Timer), patch.object(qwen.ocr, 'recognize', self.recognize), patch.object(qwen, 'llm', self.mapping):
            task['target'](*task['args'])


class ComparisonContracts(unittest.TestCase):
    def setUp(self):
        self.assertIs(compatibility.submit,comparison.submit); self.assertIs(compatibility.run,comparison.run)
        network = patch('requests.post', side_effect=AssertionError('offline contract attempted network'))
        network.start(); self.addCleanup(network.stop)

    def test_duplicate_conflict_owner_isolation_and_captured_callbacks(self):
        first, second = Fixture(self), Fixture(self, 'bob')
        one = first.submit(); two = second.submit()
        self.assertEqual(first.submit()['id'], one['id']); self.assertEqual(len(first.workers), 1)
        with self.assertRaises(HTTPException) as caught: first.submit(upload=b'different-before-decode')
        self.assertEqual(caught.exception.status_code, 409)
        self.assertNotEqual(one['id'], two['id'])
        first.namespace['_text_v2_save'] = Mock(side_effect=AssertionError('later callback used'))
        first.run(); second.run()
        self.assertEqual(first.store['records',one['id']]['status'], 'completed')
        self.assertEqual(second.store['records',two['id']]['owner_user_id'], 'bob')
        self.assertEqual((first.clears, second.clears), (1,1))
        first.namespace['_text_v2_save'].assert_not_called()
        self.assertEqual(Path(one['source_path']).read_bytes(), first.blob)
        self.assertTrue(one['diagnostics']['source_preview']['display_only'])

    def test_admission_and_thread_failure_leave_evidence_without_replay(self):
        f=Fixture(self); f.namespace['TEXT_INSPECTION_EXTERNAL_VLM_ENABLED']=False
        with self.assertRaises(HTTPException) as caught: f.submit(qwen_enabled=True)
        self.assertEqual(caught.exception.status_code,409); self.assertEqual(f.store,{}); self.assertEqual(f.workers,[])
        f=Fixture(self); f.template['elements']=[]
        with self.assertRaises(HTTPException): f.submit()
        self.assertEqual(f.store,{}); self.assertEqual(list(f.root.rglob('*')),[])
        f=Fixture(self); f.fail_thread=True
        with self.assertRaisesRegex(RuntimeError,'thread unavailable'): f.submit(qwen_enabled=True)
        self.assertEqual(len(f.load('records')),1); self.assertEqual(f.load('records')[0]['status'],'attempting')
        count=len(f.events); prior=f.submit(qwen_enabled=True)
        self.assertEqual(prior['status'],'attempting'); self.assertEqual(len(f.events),count); self.assertEqual(f.calls,[])

    def test_paid_claim_unknown_cache_and_account_boundary(self):
        f=Fixture(self)
        def unknown(): raise TimeoutError('unknown fixture outcome')
        f.provider_hook=unknown
        record=f.submit(qwen_enabled=True); f.run()
        self.assertEqual(len(f.calls),1); self.assertEqual(f.load('ocr_evidence')[0]['status'],'unknown')
        self.assertEqual(f.store['records',record['id']]['status'],'review_required')
        f.provider_hook=lambda:None
        again=f.submit('request_002',qwen_enabled=True); f.run()
        self.assertEqual(len(f.calls),1); self.assertEqual(f.store['records',again['id']]['status'],'review_required')
        f.owner='bob'; other=f.submit('request_001',qwen_enabled=True); f.run()
        self.assertEqual(len(f.calls),2); self.assertEqual(f.store['records',other['id']]['decision'],'REVIEW_REQUIRED')
        self.assertEqual(f.clears,3); self.assertTrue(all(timer.cancelled for timer in f.timers))

    def test_timer_settlement_wins_over_late_success(self):
        f=Fixture(self); record=f.submit(qwen_enabled=True)
        f.provider_hook=lambda:f.timers[-1].callback()
        f.run(); stored=f.store['records',record['id']]
        self.assertEqual(stored['diagnostics']['phase'],'timeout'); self.assertEqual(stored['status'],'review_required')
        self.assertEqual(stored['decision'],'REVIEW_REQUIRED'); self.assertEqual(len(f.calls),1)
        self.assertEqual(f.clears,2); self.assertTrue(f.timers[0].cancelled)
        self.assertTrue(any(e[0]=='cas' and e[1]=='records' for e in f.events))

    def test_completed_record_rejects_late_timer_and_runtime_allowlist_is_dynamic(self):
        f=Fixture(self); record=f.submit(qwen_enabled=True); f.run()
        completed=copy.deepcopy(f.store['records',record['id']]); self.assertEqual(completed['status'],'completed')
        f.timers[0].callback()
        self.assertEqual(f.store['records',record['id']],completed); self.assertEqual(f.clears,2)
        f=Fixture(self); record=f.submit()
        with patch.dict(os.environ, {'VANTALINE_STANDARD_ELEMENTS_MATCH_ACCOUNTS':'alice','VANTALINE_STANDARD_PREPARATION_ACCOUNTS':'alice'}): f.run()
        self.assertEqual(f.store['records',record['id']]['decision'],'MATCH')

    def test_settings_resolution_order_alias_and_missing_recorder_fail_closed(self):
        f=Fixture(self)
        with patch.dict(os.environ, {'VANTALINE_QWEN_OCR_ACCOUNTS':'alice'}):
            resolved=qwen.settings(f.model_ports(),'alice')
            self.assertIs(resolved,f.config); self.assertEqual([e[1] for e in f.events],['document','ocr'])
            self.assertEqual(resolved['ocr_settings']['model'],qwen.ocr.MODEL)
            f.config['provider']='invalid'; f.events.clear()
            with self.assertRaisesRegex(ValueError,'qwen_credentials'): qwen.settings(f.model_ports(),'alice')
            self.assertEqual([e[1] for e in f.events],['document','ocr'])
        for invoke in [lambda:qwen.llm({'profile_id':'bound'}, {}, 1), lambda:qwen.ocr.recognize({'profile_id':'bound'},b'',(1,1),1)]:
            with self.assertRaisesRegex(RuntimeError,'recorder is not configured'): invoke()

    def test_existing_cleanup_sequences_remain_distinct(self):
        f=Fixture(self); original=f.save
        def final_save_fails(kind,value,**kwargs):
            if kind=='records' and value.get('status')=='completed': raise RuntimeError('final save failed')
            return original(kind,value,**kwargs)
        f.namespace['_text_v2_save']=final_save_fails; f.submit()
        slot=Mock(); slot.acquire.return_value=True
        with patch.object(comparison,'_slots',slot), self.assertRaisesRegex(RuntimeError,'final save failed'): f.run()
        self.assertEqual(f.clears,0); slot.release.assert_not_called()
        f=Fixture(self); original=f.update
        def final_cas_fails(kind,value):
            if kind=='records' and value.get('status')=='completed': raise RuntimeError('final CAS failed')
            return original(kind,value)
        f.namespace['_text_v2_update_attempt']=final_cas_fails; f.submit(qwen_enabled=True)
        slot=Mock(); slot.acquire.return_value=True
        with patch.object(qwen,'_slots',slot), self.assertRaisesRegex(RuntimeError,'final CAS failed'): f.run()
        self.assertEqual(f.clears,1); self.assertTrue(f.timers[0].cancelled); slot.release.assert_called_once()
        f=Fixture(self); f.namespace['clear_thread_runtime_repository_selection']=Mock(side_effect=RuntimeError('clear failed')); f.submit(qwen_enabled=True)
        slot=Mock(); slot.acquire.return_value=True
        with patch.object(qwen,'_slots',slot), self.assertRaisesRegex(RuntimeError,'clear failed'): f.run()
        self.assertTrue(f.timers[0].cancelled); slot.release.assert_not_called()

    def test_ocr_mapping_and_both_rereads_share_captured_usage(self):
        f=Fixture(self); f.template['elements'][0]['text']='Battery Pack'
        observe=f.observations
        f.observations=lambda:[{**observe()[0],'text':'Batterv Pack'}]
        recognize=f.recognize
        def provider(*args,**kwargs):
            rows,diagnostic=recognize(*args,**kwargs)
            if kwargs.get('region_text'): rows[0]['text']='Battery Pack'
            return rows,diagnostic
        f.recognize=provider
        def mapping(*args,**kwargs):
            self.assertIs(kwargs['record_usage'],f.usage)
            stored=f.load('records')[0]
            self.assertEqual(stored['diagnostics']['phase'],'mapping_unmatched')
            self.assertEqual(stored['diagnostics']['model_audits'][-1]['name'],'mapping')
            return {'mappings':[]},{}
        f.mapping=Mock(side_effect=mapping)
        record=f.submit(qwen_enabled=True,reread_enabled=True)
        newer=Mock(); f.namespace['record_model_call']=newer
        f.run(); stored=f.store['records',record['id']]
        self.assertEqual(len(f.calls),3); f.mapping.assert_called_once(); newer.assert_not_called()
        self.assertTrue(all(c['record_usage'] is f.usage for c in f.calls))
        self.assertEqual([r['mode'] for r in stored['diagnostics']['rereads']],['advanced_recognition','text_recognition'])
        self.assertTrue(stored['diagnostics']['element_presence_satisfied'])
        self.assertEqual(stored['diagnostics']['external_calls'],4); self.assertEqual(stored['decision'],'REVIEW_REQUIRED')


if __name__=='__main__': unittest.main(verbosity=2)
