"""Synthetic legacy workflow regressions, including original partial-failure boundaries."""
import asyncio
import copy
from contextvars import ContextVar
from dataclasses import replace
from contextlib import ExitStack
import hashlib
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import httpx
import numpy as np
from fastapi import FastAPI, HTTPException
from local_inspection_service.text_inspection import incoming_access, incoming_catalog, incoming_execution, incoming_retention
from local_inspection_service.text_inspection.incoming_api import register_catalog, register_inspections
from local_inspection_service.text_inspection.incoming_catalog import IncomingCatalog
from local_inspection_service.text_inspection.incoming_execution import IncomingExecution
from local_inspection_service.text_inspection.incoming_reviews import IncomingReviews
from local_inspection_service.text_inspection.incoming_retention import IncomingCapacity, IncomingRetention
from local_inspection_service.text_inspection.incoming_ports import (
    IncomingAccess, IncomingReferences, IncomingInspections, IncomingTasks, IncomingMedia,
    IncomingWrites, IncomingJSON, IncomingOCR, IncomingImaging, IncomingPaths,
)
from local_inspection_service.schemas.text_inspection import IncomingTextRulesRequest, IncomingTextReviewRequest

RULE = {'field_id': 'model', 'name': '型号', 'region_normalized': {'x': 0.1, 'y': 0.1, 'width': 0.8, 'height': 0.8},
        'expected_text': 'MODEL', 'match_mode': 'exact', 'importance': 'critical', 'case_sensitive': True}


def pixels():
    return np.full((320, 320, 3), 170, np.uint8)


def picture():
    ok, encoded = cv2.imencode('.png', pixels())
    assert ok
    return encoded.tobytes()


class Upload:
    filename = 'standard.png'
    def __init__(self, data=None):
        self.data = picture() if data is None else data
        self.reads = []
    async def read(self, size=-1):
        self.reads.append(size)
        await asyncio.sleep(0)
        return self.data


class Fixture:
    def __init__(self, case):
        temporary = tempfile.TemporaryDirectory(prefix='incoming-workflows-')
        case.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.context = ContextVar('incoming-fixture-user', default='alice')
        self.lock, self.events, self.lock_probes = threading.RLock(), [], []
        self.state = {'references': [], 'inspections': [], 'audit': []}
        self.task_records = [{'id': 'task', 'task_kind': 'incoming_material_text', 'owner_user_id': 'alice'}]
        self.repository = None
        self.fail_write_number, self.write_number = 0, 0
        self.permission = Mock()
        self.task_access = incoming_access.IncomingTaskAccess(self.load_task, self.user, lambda:self.allowed)
        self.require_task = Mock(side_effect=self.task_access.require)
        self.record_access = Mock()
        self.save_task = Mock()
        self.capacity = Mock()
        self.quality = Mock(return_value={'accepted': True})
        self.rectify = Mock(side_effect=lambda image, size: (image.copy(), {'accepted': True}))
        self.observe = Mock(return_value=[])
        self.corroborate = Mock(return_value={})
        self.field = Mock(return_value=None)
        self.similarity = Mock(return_value=None)
        self.annotate = Mock(side_effect=lambda image, fields: image.copy())
        self.save_reference = Mock(side_effect=lambda record, **kw: self.save('references', record, **kw))
        self.save_inspection = Mock(side_effect=lambda record, **kw: self.save('inspections', record, **kw))
        self.audit = Mock()
        self.access = IncomingAccess(lambda *a, **kw: self.permission(*a, **kw), self.user,
            lambda:self.require_task, lambda:self.record_access,
            lambda value: str(value.get('owner_user_id') or ''), self.allowed)
        self.references = IncomingReferences(lambda: copy.deepcopy(self.state['references']),
            lambda identity: self.find('references', identity), lambda *a, **kw: self.save_reference(*a, **kw))
        self.inspections = IncomingInspections(lambda: copy.deepcopy(self.state['inspections']),
            lambda identity: self.find('inspections', identity), lambda *a, **kw: self.save_inspection(*a, **kw),
            lambda *a: self.reviews.duplicate(*a))
        self.tasks = IncomingTasks(lambda: copy.deepcopy(self.task_records), lambda task: self.save_task(task),
            lambda:lambda task, config: copy.deepcopy(task), lambda: {'user': self.context.get()})
        self.media = IncomingMedia(lambda:self.output, lambda: self.root, lambda path, root: path.resolve().is_relative_to(root.resolve()),
            lambda:lambda data, name: (cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR), '.png'))
        self.writes = IncomingWrites(lambda: self.repository, lambda: self.lock)
        self.paths = IncomingPaths(lambda: self.root/'references.json', lambda: self.root/'inspections.json', lambda: self.root/'audit.json')
        self.json = IncomingJSON(self.paths, lambda path: copy.deepcopy(self.state[path.stem]), self.write)
        public = lambda record: incoming_access.public_record(record, lambda value: value)
        self.catalog = IncomingCatalog(self.access, self.references, self.tasks, self.media, self.writes, self.json, public, lambda: False)
        self.reviews = IncomingReviews(self.access, self.inspections, self.tasks, self.media, self.writes, self.json,
            lambda:lambda rows: [row['raw_json'] for row in rows], public)
        self.execution = IncomingExecution(self.access, self.references, self.inspections, self.media,
            IncomingOCR(lambda image: self.observe(image), lambda *a: self.corroborate(*a), lambda:self.field),
            IncomingImaging(lambda image: self.quality(image), lambda:self.rectify, lambda:self.similarity, lambda:self.annotate),
            lambda:self.capacity, lambda: False, public)
        self.retention = IncomingRetention(self.inspections, self.media, self.writes, self.json, lambda:self.audit, lambda: 'system')
    def user(self):
        return {'id': self.context.get()}
    def allowed(self, task, user):
        return incoming_access.task_access_allowed(task, user, lambda value: value['id'] == 'admin', lambda value: value['owner_user_id'])
    def load_task(self, identity):
        return next((copy.deepcopy(t) for t in self.task_records if t['id'] == identity), None)
    def find(self, kind, identity):
        return next((copy.deepcopy(r) for r in self.state[kind] if r['id'] == identity), None)
    def save(self, kind, record, *, insert_only=False):
        self.events.append(('save', kind, insert_only, copy.deepcopy(record)))
        if insert_only and self.find(kind, record['id']):
            return False
        self.state[kind] = [copy.deepcopy(record)] + [r for r in self.state[kind] if r['id'] != record['id']]
        return True
    def write(self, path, records):
        def probe():
            acquired = self.lock.acquire(blocking=False)
            self.lock_probes.append(acquired)
            if acquired: self.lock.release()
        thread = threading.Thread(target=probe); thread.start(); thread.join(2)
        if thread.is_alive(): raise AssertionError('lock probe stalled')
        self.write_number += 1
        self.events.append(('write', path.stem))
        if self.write_number == self.fail_write_number: raise OSError('write failed')
        self.state[path.stem] = copy.deepcopy(records)
    def output(self, name, owner):
        directory = self.root/owner/name
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    def active_reference(self):
        path = self.root/'canonical.png'; path.write_bytes(picture())
        record = {'id': 'itref_one', 'task_id': 'task', 'owner_user_id': 'alice', 'status': 'active',
                  'version_label': 'v1', 'source_sha256': 'original', 'canonical_path': str(path), 'rules': [copy.deepcopy(RULE)], 'created_at': 1}
        self.state['references'] = [record]
        return record
    def inspection(self, **extra):
        record = {'id': 'itinsp_one', 'task_id': 'task', 'owner_user_id': 'alice', 'capture_id': 'capture-0001',
                  'auto_decision': 'REVIEW_REQUIRED', 'final_decision': '', 'created_at': 1, **extra}
        self.state['inspections'] = [record]
        return record


class Workflows(unittest.TestCase):
    def first_failure(self, error, success):
        attempts=[]
        def call(*args,**kwargs):
            attempts.append(1)
            if len(attempts)==1:raise error
            return success(*args,**kwargs)
        return Mock(side_effect=call)

    def test_catalog_first_failures_preserve_partial_state_without_retry(self):
        for boundary in ['create','activate_pg','activate_read','activate_write','publish','clone']:
            with self.subTest(boundary=boundary):
                f=Fixture(self);error=RuntimeError(boundary)
                if boundary=='create':
                    target=self.first_failure(error,lambda record,**kw:f.save('references',record,**kw));f.save_reference.side_effect=target
                    invoke=lambda:asyncio.run(f.catalog.create_incoming_text_reference('task',Upload(),'v1'))
                else:
                    reference=f.active_reference();reference['status']='draft'
                    if boundary=='clone':
                        target=self.first_failure(error,lambda record,**kw:f.save('references',record,**kw));f.save_reference.side_effect=target
                        invoke=lambda:f.catalog.clone_incoming_text_reference('itref_one','v2')
                    else:
                        invoke=lambda:f.catalog.update_incoming_text_reference_rules('itref_one',IncomingTextRulesRequest(rules=[RULE],activate=True))
                        if boundary=='activate_pg':
                            f.repository=Mock();target=self.first_failure(error,lambda *args:None);f.repository.activate_incoming_text_reference=target
                        elif boundary=='publish':
                            target=self.first_failure(error,lambda task:None);f.save_task.side_effect=target
                        else:
                            if boundary=='activate_read':
                                target=self.first_failure(error,f.json.read);f.catalog.json=replace(f.json,read=target)
                            else:
                                target=self.first_failure(error,f.json.write);f.catalog.json=replace(f.json,write=target)
                with self.assertRaises(RuntimeError) as caught:invoke()
                self.assertIs(caught.exception,error);target.assert_called_once()
                if boundary=='create':self.assertEqual(f.state['references'],[]);self.assertEqual(len(list(f.root.rglob('itref_*'))),2)
                elif boundary=='publish':self.assertEqual(f.find('references','itref_one')['status'],'active')
                else:self.assertEqual(f.find('references','itref_one')['status'],'draft')
                if boundary!='publish':f.save_task.assert_not_called()

    def test_execution_first_failures_keep_claim_and_completion_boundaries(self):
        for boundary in ['claim','final','quality','observe','corroborate','field','annotate','imwrite']:
            with self.subTest(boundary=boundary):
                f=Fixture(self);f.active_reference();error=RuntimeError(boundary)
                with ExitStack() as stack:
                    if boundary in ('claim','final'):
                        save=f.save_inspection.side_effect;target=self.first_failure(error,save)
                        f.save_inspection.side_effect=lambda record,**kw:target(record,**kw) if bool(kw.get('insert_only'))==(boundary=='claim') else save(record,**kw)
                    elif boundary=='imwrite':
                        target=self.first_failure(error,incoming_execution.cv2.imwrite);stack.enter_context(patch.object(incoming_execution.cv2,'imwrite',target))
                    else:
                        success={'quality':lambda image:{'accepted':True},'observe':lambda image:[],
                                 'corroborate':lambda *args:{},'field':lambda *args:None,'annotate':lambda image,fields:image.copy()}[boundary]
                        target=self.first_failure(error,success);getattr(f,boundary).side_effect=target
                    invoke=lambda:asyncio.run(f.execution.inspect_incoming_text('task',Upload(),'capture-0001'))
                    if boundary in ('claim','final','quality'):
                        with self.assertRaises(RuntimeError) as caught:invoke()
                        self.assertIs(caught.exception,error)
                    else:
                        result=invoke();self.assertEqual(result['status'],'completed_with_error');self.assertEqual(result['error_code'],'RuntimeError')
                        self.assertEqual(result['auto_decision'],'REVIEW_REQUIRED');self.assertEqual(result['final_decision'],'')
                    target.assert_called_once()
                if boundary=='claim':self.assertEqual(f.state['inspections'],[]);f.quality.assert_not_called()
                elif boundary in ('final','quality'):self.assertEqual(f.state['inspections'][0]['status'],'processing')
                else:self.assertEqual(f.state['inspections'][0]['status'],'completed_with_error')
                if boundary in ('claim','quality'):f.observe.assert_not_called()
                if boundary=='observe':f.corroborate.assert_not_called()
                if boundary in ('observe','corroborate'):f.field.assert_not_called()
                if boundary in ('observe','corroborate','field'):f.annotate.assert_not_called()
                self.assertEqual(len(list(f.root.rglob('itinsp_*_source*'))),1)

    def test_review_read_and_list_decode_first_errors_are_not_retried(self):
        for boundary in ['review_read','list_decode']:
            with self.subTest(boundary=boundary):
                f=Fixture(self);f.inspection();error=RuntimeError(boundary)
                if boundary=='review_read':
                    target=self.first_failure(error,f.json.read);f.reviews.json=replace(f.json,read=target)
                    invoke=lambda:f.reviews.review_incoming_text_inspection('itinsp_one',IncomingTextReviewRequest(decision='RELEASED',reason='checked'))
                else:
                    f.repository=Mock();f.repository.list_incoming_text_inspections.return_value={'items':[{'raw_json':{'id':'one'}}],'total':1,'summary':{}}
                    target=self.first_failure(error,lambda rows:[row['raw_json'] for row in rows]);f.reviews.decode_rows=lambda:target
                    invoke=lambda:f.reviews.list_incoming_text_inspections()
                with self.assertRaises(RuntimeError) as caught:invoke()
                self.assertIs(caught.exception,error);target.assert_called_once();self.assertEqual(f.events,[])
                self.assertEqual(f.state['inspections'][0]['final_decision'],'');self.assertEqual(f.state['audit'],[])

    def test_retention_first_failures_preserve_evidence_and_audit_order(self):
        for boundary in ['audit','unlink','mark','read','write']:
            with self.subTest(boundary=boundary):
                f=Fixture(self);path=f.root/'source.png';path.write_bytes(b'evidence');f.inspection(source_path=str(path),created_at=1)
                error=OSError(boundary) if boundary=='unlink' else RuntimeError(boundary)
                with ExitStack() as stack:
                    stack.enter_context(patch.dict(incoming_retention.os.environ,{'VANTALINE_INCOMING_TEXT_IMAGE_RETENTION_DAYS':'1'}))
                    stack.enter_context(patch.object(incoming_retention.time,'time',return_value=100000))
                    if boundary=='audit':target=self.first_failure(error,lambda event:None);f.audit.side_effect=target
                    elif boundary=='unlink':
                        target=self.first_failure(error,Path.unlink)
                        def unlink(candidate,*args,**kwargs):return target(candidate,*args,**kwargs)
                        stack.enter_context(patch.object(Path,'unlink',unlink))
                    elif boundary=='mark':
                        f.repository=Mock();f.repository.incoming_text_retention_candidates.return_value=copy.deepcopy(f.state['inspections'])
                        target=self.first_failure(error,lambda *args,**kwargs:True);f.repository.mark_incoming_text_evidence_purged=target
                    elif boundary=='read':target=self.first_failure(error,f.json.read);f.retention.json=replace(f.json,read=target)
                    else:target=self.first_failure(error,f.json.write);f.retention.json=replace(f.json,write=target)
                    if boundary=='unlink':self.assertEqual(f.retention.purge(),{'records':0,'files':0})
                    else:
                        with self.assertRaises(RuntimeError) as caught:f.retention.purge()
                        self.assertIs(caught.exception,error)
                    target.assert_called_once()
                self.assertEqual(path.exists(),boundary=='unlink')
                if boundary=='audit':self.assertEqual(f.state['inspections'][0]['evidence_purged_at'],100000)
                else:self.assertNotIn('evidence_purged_at',f.state['inspections'][0]);f.audit.assert_not_called()

    def test_json_comparisons_and_mutations_share_the_write_lock(self):
        for domain in ['activate','review','retention']:
            with self.subTest(domain=domain):
                f=Fixture(self);probes=[];armed=[False]
                def probe(label):
                    if not armed[0]:return
                    def other_thread():
                        acquired=f.lock.acquire(blocking=False);probes.append((label,acquired))
                        if acquired:f.lock.release()
                    thread=threading.Thread(target=other_thread);thread.start();thread.join(2);self.assertFalse(thread.is_alive())
                class Record(dict):
                    def get(self,key,*args):probe('get');return super().get(key,*args)
                    def __setitem__(self,key,value):probe('set');return super().__setitem__(key,value)
                    def update(self,*args,**kwargs):probe('update');return super().update(*args,**kwargs)
                def read(path):
                    armed[0]=True;probe('read')
                    return [Record(value) for value in copy.deepcopy(f.state[path.stem])]
                def write(path,values):
                    probe('write');armed[0]=False;f.write(path,values)
                io=replace(f.json,read=read,write=write)
                if domain=='activate':
                    ref=f.active_reference();ref['status']='draft';f.state['references'].append({**ref,'id':'itref_old','status':'active'})
                    f.catalog.json=io;f.catalog.update_incoming_text_reference_rules('itref_one',IncomingTextRulesRequest(rules=[RULE],activate=True))
                    self.assertIn(('set',False),probes)
                elif domain=='review':
                    f.inspection();f.reviews.json=io
                    f.reviews.review_incoming_text_inspection('itinsp_one',IncomingTextReviewRequest(decision='RELEASED',reason='checked'))
                    self.assertIn(('update',False),probes)
                else:
                    f.inspection(created_at=1);f.retention.json=io
                    with patch.dict(incoming_retention.os.environ,{'VANTALINE_INCOMING_TEXT_IMAGE_RETENTION_DAYS':'1'}),patch.object(incoming_retention.time,'time',return_value=100000):f.retention.purge()
                    self.assertIn(('set',False),probes)
                self.assertIn(('get',False),probes);self.assertIn(('write',False),probes)
                self.assertEqual(probes.count(('read',False)),2 if domain=='review' else 1)
                self.assertTrue(all(not acquired for _,acquired in probes));self.assertTrue(all(not acquired for acquired in f.lock_probes))
                released=[]
                def after():
                    acquired=f.lock.acquire(blocking=False);released.append(acquired)
                    if acquired:f.lock.release()
                thread=threading.Thread(target=after);thread.start();thread.join(2);self.assertFalse(thread.is_alive());self.assertEqual(released,[True])

    def capture_trial(self, mode, missing=False):
        f=Fixture(self);events=[];cell=[];patches=[]
        class Stop(BaseException):pass
        def marker(label):
            def call(*args,**kwargs):events.append(label);raise Stop()
            return call
        a,b,c=marker('A'),None if missing else marker('B'),marker('C');cell.append(a)
        def prior(value):events.append('prior');cell[0]=b;return value
        def argument(value):events.append('argument');cell[0]=c;return value
        def getter():events.append('capture');return cell[0]
        class Mapping(dict):
            def get(self,key,default=None):
                value=super().get(key,default)
                return argument(value) if key==self.trigger else value
        class ItemMapping(dict):
            def __getitem__(self,key):
                value=super().__getitem__(key)
                return argument(value) if key==self.trigger else value
        def mapping(value,key,item=False):
            result=(ItemMapping if item else Mapping)(value);result.trigger=key;return result
        def execution():
            f.active_reference();return lambda:asyncio.run(f.execution.inspect_incoming_text('task',Upload(),'capture-0001'))
        if mode=='allowed':
            f.task_access.load=lambda identity:prior(f.load_task(identity));f.task_access.user=lambda:argument({'id':'alice'});f.task_access.allowed=getter
            invoke=lambda:f.task_access.require('task')
        elif mode in ('record','task'):
            ref=f.active_reference()
            if mode=='task':ref=mapping(ref,'task_id')
            f.catalog.references=replace(f.references,load=lambda identity:prior(ref))
            f.catalog.access=replace(f.access,**({'record':getter,'user':lambda:argument({'id':'alice'})} if mode=='record' else {'task':getter}))
            invoke=lambda:f.catalog.get_incoming_text_reference_asset('itref_one','canonical')
        elif mode=='public':
            f.catalog.references=replace(f.references,all=lambda:prior([]))
            f.catalog.tasks=replace(f.tasks,public=getter,config=lambda:argument({}))
            invoke=lambda:f.catalog.get_incoming_text_task('task')
        elif mode=='decode':
            class File(Upload):
                async def read(self,size=-1):return prior(await super().read(size))
                @property
                def filename(self):return argument('sample.png')
            f.catalog.media=replace(f.media,decode=getter)
            invoke=lambda:asyncio.run(f.catalog.create_incoming_text_reference('task',File(),'v1'))
        elif mode=='rows':
            f.repository=Mock();f.repository.list_incoming_text_inspections.side_effect=lambda **kwargs:prior(mapping({'items':[]},'items'))
            f.reviews.decode_rows=getter;invoke=lambda:f.reviews.list_incoming_text_inspections()
        elif mode=='field':
            invoke=execution();f.corroborate.side_effect=lambda *args:prior(mapping({},'model'))
            f.execution.ocr=replace(f.execution.ocr,field=getter)
        elif mode=='annotate':
            invoke=execution();result=mapping({'fields':[]},'fields',True)
            patches=[patch.object(incoming_execution,'decide_inspection',return_value=result),patch.object(incoming_execution,'apply_commissioning_gate',side_effect=lambda value,**kwargs:prior(value))]
            f.execution.imaging=replace(f.execution.imaging,annotate=getter)
        elif mode=='rectify':
            invoke=execution()
            class Shape:
                def __getitem__(self,key):return argument(320)
            patches=[patch.object(incoming_execution.cv2,'imread',side_effect=lambda *args:prior(types.SimpleNamespace(shape=Shape())))]
            f.execution.imaging=replace(f.execution.imaging,rectify=getter)
        elif mode=='similarity':
            invoke=execution();rule=mapping(dict(RULE),'region_normalized',True)
            patches=[patch.object(incoming_execution,'normalize_field_rules',return_value=[rule])]
            f.field.side_effect=lambda *args:prior(None);f.execution.imaging=replace(f.execution.imaging,similarity=getter)
        elif mode=='capacity':
            invoke=execution();counts=[0]
            class Blob(bytes):
                def __len__(self):
                    counts[0]+=1
                    if counts[0]==3:argument(None)
                    return super().__len__()
            f.execution.inspections=replace(f.inspections,duplicate=lambda *args:prior(None));f.execution.capacity=getter
            invoke=lambda:asyncio.run(f.execution.inspect_incoming_text('task',Upload(Blob(picture())),'capture-0001'))
        elif mode=='output':
            class TaskId(str):
                def __format__(self,spec):return argument('task')
            decode=f.media.decode();f.catalog.media=replace(f.media,decode=lambda:lambda *args:prior(decode(*args)),output=getter)
            invoke=lambda:asyncio.run(f.catalog.create_incoming_text_reference(TaskId('task'),Upload(),'v1'))
        elif mode=='audit':
            f.inspection(created_at=1);counts=[0]
            def clock():
                counts[0]+=1
                if counts[0]==3:argument(None)
                return 10_000_000
            def write(*args):f.json.write(*args);prior(None)
            f.retention.json=replace(f.json,write=write);f.retention.audit=getter
            patches=[patch.object(incoming_retention.time,'time',side_effect=clock)]
            invoke=f.retention.purge
        else:raise AssertionError(mode)
        with ExitStack() as stack:
            for context in patches:stack.enter_context(context)
            try:
                result=invoke()
                if missing:self.assertEqual(result.get('error_code'),'TypeError');events.append('TypeError')
                else:self.fail('capture callback not invoked')
            except Stop:
                if missing:self.fail('missing callback unexpectedly invoked another callback')
            except TypeError:
                if not missing:raise
                events.append('TypeError')
        expected=['prior','capture']+['argument']*(2 if mode=='rectify' else 1)+['TypeError' if missing else 'B']
        self.assertEqual(events,expected)

    def test_thirteen_callbacks_capture_after_preceding_work_before_arguments(self):
        for mode in ['allowed','record','task','public','decode','rows','field','annotate','audit','rectify','similarity','capacity','output']:
            with self.subTest(mode=mode):self.capture_trial(mode)

    def test_missing_callbacks_keep_argument_effects_and_original_failure_projection(self):
        for mode in ['allowed','record','task','public','decode','rows','field','annotate','audit','rectify','similarity','capacity','output']:
            with self.subTest(mode=mode):self.capture_trial(mode,missing=True)

    def test_owner_projection_and_media_permission_order(self):
        f = Fixture(self)
        self.assertEqual(f.task_access.require('task', write=True)['id'], 'task')
        token = f.context.set('other')
        f.task_records[0]['shared_with_user_ids'] = ['other']
        with self.assertRaises(HTTPException) as caught: f.task_access.require('task')
        self.assertEqual(caught.exception.status_code, 404)
        f.context.reset(token)
        value = {'id': 'itinsp_a b/part', 'source_path': 'private', 'nested': {'keep': True}}
        result = incoming_access.public_record(value, lambda record: {**record, 'sanitized': True})
        self.assertEqual(result['source_url'], '/api/incoming-text/inspections/itinsp_a%20b/part/evidence/source')
        result['nested']['keep'] = False; self.assertTrue(value['nested']['keep']); self.assertNotIn('source_path', result)
        reference = f.active_reference(); path = Path(reference['canonical_path'])
        order = []
        f.record_access.side_effect = lambda *a, **kw: order.append('record')
        f.require_task.side_effect = lambda *a, **kw: order.append('task') or f.task_records[0]
        self.assertEqual(f.catalog.get_incoming_text_reference_asset('itref_one', 'canonical'), path)
        self.assertEqual(order, ['record', 'task'])
        f.inspection(source_path=str(path)); order.clear()
        self.assertEqual(f.reviews.get_incoming_text_inspection_evidence('itinsp_one', 'source'), path)
        self.assertEqual(order, ['task'])
        with self.assertRaises(HTTPException): f.reviews.get_incoming_text_inspection_evidence('itinsp_one', 'unknown')
        f.state['inspections'][0]['source_path'] = str(Path(__file__).resolve())
        with self.assertRaises(HTTPException): f.reviews.get_incoming_text_inspection_evidence('itinsp_one', 'source')

    def test_catalog_upload_failure_boundaries_and_clone_shared_media(self):
        f = Fixture(self); upload = Upload()
        with self.assertRaises(HTTPException): asyncio.run(f.catalog.create_incoming_text_reference('task', upload, ' '))
        self.assertEqual(upload.reads, [])
        with patch.object(incoming_catalog.cv2, 'imwrite', return_value=False):
            with self.assertRaises(HTTPException) as caught: asyncio.run(f.catalog.create_incoming_text_reference('task', upload, 'v1'))
        self.assertEqual(caught.exception.status_code, 500); self.assertEqual(list(f.root.rglob('itref_*')), [])
        f.save_reference.side_effect = None; f.save_reference.return_value = False
        with self.assertRaises(HTTPException) as caught: asyncio.run(f.catalog.create_incoming_text_reference('task', Upload(), 'v1'))
        self.assertEqual(caught.exception.status_code, 409); self.assertEqual(list(f.root.rglob('itref_*')), [])
        f.save_reference.side_effect = RuntimeError('store unavailable')
        with self.assertRaisesRegex(RuntimeError, 'store unavailable'): asyncio.run(f.catalog.create_incoming_text_reference('task', Upload(), 'v1'))
        self.assertEqual(len(list(f.root.rglob('itref_*'))), 2)
        f.save_reference.side_effect = lambda record, **kw: f.save('references', record, **kw)
        original = f.active_reference(); original['activated_by_user_id'] = 'previous'; original['nested'] = {'value': 1}
        before = set(f.root.rglob('*'))
        clone = f.catalog.clone_incoming_text_reference('itref_one', ' v2 ')
        stored = f.find('references', clone['id'])
        self.assertEqual(stored['canonical_path'], original['canonical_path']); self.assertEqual(stored['activated_by_user_id'], 'previous')
        self.assertEqual(stored['activated_at'], 0); self.assertEqual(stored['status'], 'draft'); self.assertEqual(before, set(f.root.rglob('*')))
        stored['nested']['value'] = 2; self.assertEqual(original['nested']['value'], 1)

    def test_activation_order_partial_publication_and_catalog_status(self):
        for postgres in (False, True):
            f = Fixture(self); first = f.active_reference(); other = copy.deepcopy(first); other.update(id='itref_new', version_label='v2', status='draft')
            f.state['references'].append(other)
            request = IncomingTextRulesRequest(rules=[RULE], activate=True)
            if postgres:
                f.repository = Mock()
                f.save_reference.side_effect = lambda record, **kw: f.events.append(('draft', record['status'])) or False
                f.repository.activate_incoming_text_reference.side_effect = lambda *a: f.events.append(('activate', a[0], a[3]['status']))
            f.save_task.side_effect = RuntimeError('task publication')
            with self.assertRaisesRegex(RuntimeError, 'task publication'): f.catalog.update_incoming_text_reference_rules('itref_new', request)
            self.assertEqual(f.require_task.call_count, 2); self.assertEqual(f.save_task.call_args.args[0]['active_reference_id'], 'itref_new')
            if postgres:
                self.assertEqual(f.events[:2], [('draft', 'draft'), ('activate', 'itref_new', 'active')]); f.repository.activate_incoming_text_reference.assert_called_once()
            else:
                self.assertEqual(f.find('references', 'itref_one')['status'], 'archived'); self.assertEqual(f.find('references', 'itref_new')['status'], 'active')
                self.assertEqual(f.lock_probes, [False])
        f = Fixture(self)
        self.assertEqual(f.catalog.get_incoming_text_task('task')['task']['status'], 'setup_required')
        f.active_reference(); self.assertEqual(f.catalog.get_incoming_text_task('task')['task']['status'], 'ready')
        f.state['references'].append({**f.state['references'][0], 'id': 'itref_two', 'created_at': 2})
        value = f.catalog.get_incoming_text_task('task'); self.assertFalse(value['configuration_valid']); self.assertIsNone(value['active_reference'])
        self.assertEqual(value['task']['status'], 'configuration_error'); self.assertEqual(value['references'][0]['id'], 'itref_two')

    def test_duplicate_and_insert_loser_precede_processing(self):
        f = Fixture(self); data = picture(); digest = hashlib.sha256(data).hexdigest()
        f.inspection(source_sha256=digest)
        result = asyncio.run(f.execution.inspect_incoming_text('task', Upload(data), 'capture-0001'))
        self.assertEqual(result['id'], 'itinsp_one'); f.capacity.assert_not_called(); f.quality.assert_not_called()
        with self.assertRaises(HTTPException) as caught: asyncio.run(f.execution.inspect_incoming_text('task', Upload(b'changed'), 'capture-0001'))
        self.assertEqual(caught.exception.status_code, 409); f.capacity.assert_not_called()
        f = Fixture(self); f.active_reference(); winner = {'id': 'itinsp_winner', 'source_sha256': digest}
        duplicates = Mock(side_effect=[None, winner])
        f.execution.inspections = replace(f.inspections, duplicate=duplicates)
        f.save_inspection.side_effect = None; f.save_inspection.return_value = False
        result = asyncio.run(f.execution.inspect_incoming_text('task', Upload(data), 'capture-0001'))
        self.assertEqual(result['id'], 'itinsp_winner'); self.assertEqual(len(list(f.root.rglob('itinsp_*'))), 0)
        f.quality.assert_not_called(); self.assertEqual(duplicates.call_count, 2)

    def test_quality_engine_and_final_write_failures_keep_distinct_states(self):
        f = Fixture(self); f.active_reference(); f.quality.side_effect = RuntimeError('quality outside catch')
        with self.assertRaisesRegex(RuntimeError, 'quality outside catch'): asyncio.run(f.execution.inspect_incoming_text('task', Upload(), 'capture-0001'))
        self.assertEqual(f.state['inspections'][0]['status'], 'processing'); self.assertEqual(f.save_inspection.call_count, 1)
        first_id = f.state['inspections'][0]['id']; f.quality.reset_mock()
        repeated = asyncio.run(f.execution.inspect_incoming_text('task', Upload(), 'capture-0001'))
        self.assertEqual(repeated['id'], first_id); f.quality.assert_not_called()
        f = Fixture(self); f.active_reference(); f.observe.side_effect = RuntimeError('OCR failure')
        value = asyncio.run(f.execution.inspect_incoming_text('task', Upload(), 'capture-0001'))
        self.assertEqual(value['status'], 'completed_with_error'); self.assertEqual(value['auto_decision'], 'REVIEW_REQUIRED')
        self.assertEqual(value['error_code'], 'RuntimeError'); self.assertEqual(value['final_decision'], '')
        self.assertEqual(f.events[0][2], True); self.assertEqual(f.events[0][3]['status'], 'processing'); self.assertFalse(f.events[-1][2])
        f = Fixture(self); f.active_reference(); loop_thread = threading.get_ident(); seen_threads = []
        f.quality.side_effect = lambda image: seen_threads.append(threading.get_ident()) or {'accepted': True}
        original_save = f.save_inspection.side_effect
        f.save_inspection.side_effect = lambda record, **kw: original_save(record, **kw) if kw.get('insert_only') else False
        value = asyncio.run(f.execution.inspect_incoming_text('task', Upload(), 'capture-0001'))
        self.assertEqual(value['status'], 'completed'); self.assertEqual(f.state['inspections'][0]['status'], 'processing')
        self.assertEqual(seen_threads, [loop_thread])
        f = Fixture(self); f.active_reference(); original_save = f.save_inspection.side_effect
        def save(record, **kw):
            if kw.get('insert_only'): return original_save(record, **kw)
            raise OSError('final save')
        f.save_inspection.side_effect = save
        with self.assertRaisesRegex(OSError, 'final save'): asyncio.run(f.execution.inspect_incoming_text('task', Upload(), 'capture-0001'))
        self.assertEqual(f.state['inspections'][0]['status'], 'processing'); self.assertEqual(f.observe.call_count, 1)

    def test_review_json_partial_audit_and_locked_conflict_pg_errors(self):
        request = IncomingTextReviewRequest(decision=' released ', reason=' checked ')
        f = Fixture(self); f.inspection(); f.fail_write_number = 2
        with self.assertRaisesRegex(OSError, 'write failed'): f.reviews.review_incoming_text_inspection('itinsp_one', request)
        self.assertEqual(f.state['inspections'][0]['final_decision'], 'RELEASED'); self.assertEqual(f.state['audit'], [])
        self.assertEqual(f.events, [('write', 'inspections'), ('write', 'audit')]); self.assertEqual(f.lock_probes, [False, False])
        released = []
        def probe_release():
            acquired = f.lock.acquire(blocking=False)
            released.append(acquired)
            if acquired: f.lock.release()
        thread = threading.Thread(target=probe_release); thread.start(); thread.join(2)
        self.assertFalse(thread.is_alive()); self.assertEqual(released, [True])
        f.reviews.review_incoming_text_inspection('itinsp_one', request); self.assertEqual(f.write_number, 2)
        f = Fixture(self); f.inspection(); stale = f.find('inspections', 'itinsp_one')
        f.state['inspections'][0]['final_decision'] = 'REJECTED'
        f.reviews.inspections = replace(f.inspections, load=lambda identity: stale)
        with self.assertRaises(HTTPException) as caught: f.reviews.review_incoming_text_inspection('itinsp_one', request)
        self.assertEqual(caught.exception.status_code, 409); self.assertEqual(f.events, [])
        f = Fixture(self); f.inspection(); f.repository = Mock()
        f.repository.review_incoming_text_inspection.side_effect = OSError('database failure')
        with self.assertRaises(HTTPException) as caught: f.reviews.review_incoming_text_inspection('itinsp_one', request)
        self.assertEqual(caught.exception.status_code, 409); self.assertEqual(caught.exception.detail, 'database failure')
        f.repository.review_incoming_text_inspection.assert_called_once(); self.assertEqual(f.events, [])

    def test_list_owner_filter_sql_empty_set_and_duplicate_lookup(self):
        f = Fixture(self); f.inspection(material_code='SKU', created_at=1)
        f.state['inspections'] += [{**f.state['inspections'][0], 'id': 'itinsp_later', 'created_at': 2, 'final_decision': 'RELEASED'},
                                  {**f.state['inspections'][0], 'id': 'hidden', 'task_id': 'hidden'}]
        result = f.reviews.list_incoming_text_inspections(decision=' review_required ', limit=0)
        self.assertEqual(result['total'], 2); self.assertEqual([r['id'] for r in result['items']], ['itinsp_later'])
        self.assertEqual(result['summary'], {'RELEASED': 1, 'REVIEW_REQUIRED': 1})
        self.assertEqual(f.reviews.list_incoming_text_inspections(material_code='different')['total'], 0)
        self.assertEqual(f.reviews.duplicate('alice', 'task', 'capture-0001')['id'], 'itinsp_one')
        self.assertIsNone(f.reviews.duplicate('other', 'task', 'capture-0001'))
        f.repository = Mock(); f.repository.list_incoming_text_inspections.return_value = {'items': [], 'total': 0, 'summary': {}}
        token = f.context.set('other')
        try: f.reviews.list_incoming_text_inspections(task_id='hidden', limit=999)
        finally: f.context.reset(token)
        f.repository.list_incoming_text_inspections.assert_called_once_with(task_ids=[], task_id='hidden', material_code='', decision='', limit=500)
        f.repository.fetch_one_by_columns.return_value = {'raw_json': {'id': 'winner'}}
        self.assertEqual(f.reviews.duplicate('alice', 'task', 'capture-0001'), {'id': 'winner'})
        f.repository.fetch_one_by_columns.assert_called_once_with('incoming_text_inspections', {'owner_user_id': 'alice', 'task_id': 'task', 'capture_id': 'capture-0001'})

    def test_retention_partial_unlink_cutoff_mark_and_audit_failures(self):
        f = Fixture(self); one = f.root/'source.png'; two = f.root/'corrected.png'; one.write_bytes(b'evidence'); two.write_bytes(b'evidence')
        f.inspection(source_path=str(one), corrected_path=str(two), created_at=99)
        real_unlink = Path.unlink
        def unlink(path, *a, **kw):
            if path == two: raise OSError('busy')
            return real_unlink(path, *a, **kw)
        with patch.dict(incoming_retention.os.environ, {'VANTALINE_INCOMING_TEXT_IMAGE_RETENTION_DAYS': '1'}), patch.object(incoming_retention.time, 'time', return_value=86500), patch.object(Path, 'unlink', unlink):
            self.assertEqual(f.retention.purge(), {'records': 0, 'files': 1})
        self.assertFalse(one.exists()); self.assertTrue(two.exists()); self.assertNotIn('evidence_purged_at', f.state['inspections'][0]); f.audit.assert_not_called()
        f.state['inspections'] += [{'id': 'boundary', 'created_at': 100}, {'id': 'already', 'created_at': 1, 'evidence_purged_at': 3}]
        f.audit.side_effect = RuntimeError('audit unavailable')
        with patch.dict(incoming_retention.os.environ, {'VANTALINE_INCOMING_TEXT_IMAGE_RETENTION_DAYS': '1'}), patch.object(incoming_retention.time, 'time', return_value=86500):
            with self.assertRaisesRegex(RuntimeError, 'audit unavailable'): f.retention.purge()
        self.assertFalse(two.exists()); self.assertEqual(f.find('inspections', 'itinsp_one')['evidence_purged_at'], 86500)
        self.assertNotIn('evidence_purged_at', f.find('inspections', 'boundary')); self.assertEqual(f.lock_probes, [False])
        f = Fixture(self); f.inspection(source_path=str(Path(__file__).resolve()), created_at=1)
        f.repository = Mock(); f.repository.incoming_text_retention_candidates.return_value = copy.deepcopy(f.state['inspections'])
        f.repository.mark_incoming_text_evidence_purged.return_value = False
        with patch.dict(incoming_retention.os.environ, {'VANTALINE_INCOMING_TEXT_IMAGE_RETENTION_DAYS': '0'}), patch.object(incoming_retention.time, 'time', return_value=100000):
            self.assertEqual(f.retention.purge(), {'records': 0, 'files': 0})
        f.repository.incoming_text_retention_candidates.assert_called_once_with(before_created_at=13600)
        f.repository.mark_incoming_text_evidence_purged.assert_called_once_with('itinsp_one', purged_at=100000, retention_days=1)
        f.audit.assert_not_called(); self.assertTrue(Path(__file__).exists())

    def test_capacity_threshold_and_error_mapping(self):
        f = Fixture(self); minimum = [100]; capacity = IncomingCapacity(lambda: f.root, lambda: minimum[0])
        with patch.object(incoming_retention.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=130)):
            capacity.require(10)
            with self.assertRaises(HTTPException) as caught: capacity.require(11)
            self.assertEqual(caught.exception.status_code, 507)
            capacity.require(-1)
            minimum[0] = 131
            with self.assertRaises(HTTPException): capacity.require(0)
        with patch.object(incoming_retention.shutil, 'disk_usage', side_effect=OSError('disk')):
            with self.assertRaises(HTTPException) as caught: capacity.require(1)
        self.assertEqual(caught.exception.status_code, 507); self.assertIsInstance(caught.exception.__cause__, OSError)

    def test_two_applications_keep_native_http_thread_identity(self):
        fixtures = [Fixture(self), Fixture(self)]
        applications = []
        for fixture, owner in zip(fixtures, ('alice', 'bob')):
            fixture.task_records[0]['owner_user_id'] = owner
            app = FastAPI()
            register_catalog(app, fixture.catalog); register_inspections(app, fixture.execution, fixture.reviews)
            self.assertEqual(len([r for r in app.routes if r.path.startswith('/api/incoming-text')]), 9)
            applications.append(app)
        # Both compositions exist before either application's first request.
        async def exercise(app, fixture, owner):
            token = fixture.context.set(owner)
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fixture') as client:
                    first = await client.get('/api/incoming-text/tasks/task')
                    self.assertEqual(first.status_code, 200); self.assertEqual(first.json()['task']['owner_user_id'], owner)
                    uploaded = await client.post('/api/incoming-text/tasks/task/references', data={'version_label': 'v1'}, files={'file': ('sample.png', picture(), 'image/png')})
                    self.assertEqual(uploaded.status_code, 200); self.assertEqual(uploaded.json()['created_by_user_id'], owner)
                    self.assertEqual(uploaded.json()['owner_user_id'], owner)
                    invalid = await client.post('/api/incoming-text/tasks/task/inspect', data={'capture_id': 'invalid'}, files={'file': ('sample.png', picture())})
                    self.assertEqual(invalid.status_code, 400)
                    schema = await client.put('/api/incoming-text/references/id/rules', json={'rules': 'wrong'})
                    self.assertEqual(schema.status_code, 422)
            finally: fixture.context.reset(token)
        async def run(): await asyncio.gather(exercise(applications[0], fixtures[0], 'alice'), exercise(applications[1], fixtures[1], 'bob'))
        asyncio.run(run())
        self.assertEqual(fixtures[0].context.get(), 'alice'); self.assertEqual(fixtures[1].context.get(), 'alice')
        self.assertNotEqual(fixtures[0].state['references'][0]['owner_user_id'], fixtures[1].state['references'][0]['owner_user_id'])


if __name__ == '__main__':
    unittest.main()
