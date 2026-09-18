"""Synthetic training persistence contracts; no training or remote model calls."""
from contextlib import ExitStack
from contextvars import ContextVar
import asyncio
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import uuid
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
PG_CHECK='--postgres' in sys.argv
if PG_CHECK: sys.argv.remove('--postgres')


def task(job='job',**values): return {'job_id':job,'action':'train_model','updated_at':10,**values}


class Guard:
    def __init__(self,events): self.lock=threading.RLock(); self.events=events
    def __enter__(self): self.events.append('enter'); self.lock.acquire(); return self
    def __exit__(self,*exc): self.events.append('exit'); self.lock.release()
    def available_to_other_thread(self):
        result=[]
        def probe():
            acquired=self.lock.acquire(blocking=False); result.append(acquired)
            if acquired: self.lock.release()
        thread=threading.Thread(target=probe); thread.start(); thread.join(timeout=5)
        if thread.is_alive(): raise AssertionError('lock probe did not finish')
        return result[0]


class Resolver:
    def __init__(self,fixture):
        self.fixture=fixture; self.version=1; self.context=ContextVar('training_snapshot',default=None)
    def current_snapshot(self): self.fixture.events.append('scope'); return self.context.get()
    def snapshot_for_record(self,record):
        self.fixture.events.append(('freeze',self.fixture.guard.available_to_other_thread()))
        return {'pipeline':{'version':self.version,'secret_ref':'fixture-ref','prompt_version':'historical-fixture'}}


class Fixture:
    def __init__(self,root):
        self.root=Path(root); self.directory=self.root/'tasks'; self.directory.mkdir()
        self.events=[]; self.guard=Guard(self.events); self.resolver=Resolver(self)
        self.repo=None; self.choices=[]; self.cached=['existing']
        self.enrich=Mock(side_effect=lambda record,*args: {**record,'enriched':True})
    def repository(self):
        self.events.append(('repository',self.guard.available_to_other_thread()))
        result=self.choices.pop(0) if self.choices else self.repo
        if isinstance(result,Exception): raise result
        return result
    def invalidate(self,key):
        self.events.append(('invalidate',key,self.guard.available_to_other_thread())); self.cached.clear()
    def provider(self): self.events.append('resolver'); return self.resolver
    def seed(self,name,value,stamp=100):
        path=self.directory/(name+'.json'); path.write_text(json.dumps(value),encoding='utf-8'); os.utime(path,(stamp,stamp)); return path
    def bind(self,api,stack):
        for name,value in {'TRAINING_TASKS_DIR':self.directory,'runtime_postgres_repository_or_none':self.repository,
            'store_read_cache_invalidate':self.invalidate,'_training_task_lock':self.guard,
            'resolve_model_profiles':self.provider,'enrich_record_audit_fields':self.enrich}.items():
            stack.enter_context(patch.object(api,name,value))


class TrainingStoreContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ); cls.environment.start()
        cls.runtime=tempfile.TemporaryDirectory(prefix='training-store-root-')
        root=Path(cls.runtime.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        root=self.stack.enter_context(tempfile.TemporaryDirectory(prefix='training-store-'))
        self.f=Fixture(root); self.f.bind(self.api,self.stack)

    def test_identity_path_and_sort_contracts(self):
        api=self.api; f=self.f
        for value,expected in [('.. _中 A/..','A'),('...___','training_task'),(None,'None'),(0,'0'),('A.B-1','A.B-1')]:
            self.assertEqual(api.training_task_path(value),f.directory/(expected+'.json'))
        record={'id':' raw ','job_id':0,'task_id':12,'remote_training_job_id':' remote '}
        self.assertEqual(api.training_task_identity_values(record,{'id':' row ','job_id':' job '}),{'raw','12','remote','row','job'})
        self.assertTrue(api.training_task_matches_identifier(record,' raw ')); self.assertFalse(api.training_task_matches_identifier(record,''))
        self.assertTrue(api.training_task_matches_identifier(record,'row',{'id':'row'}))
        self.assertEqual(api.training_task_sort_key({'updated_at':0,'created_at':'12','job_id':' job '}),(12.0,' job '))
        self.assertEqual(api.training_task_sort_key({'updated_at':'bad','created_at':15,'task_id':'t'}),(0.0,'t'))
        self.assertEqual(api.training_task_sort_key({'completed_at':7,'started_at':8,'id':3}),(7.0,'3'))
        with self.assertRaises(OverflowError): api.training_task_sort_key({'updated_at':10**1000})

    def test_save_freezes_before_invalidation_and_lock_and_retains_old_bindings(self):
        api=self.api; f=self.f; value=task(label='中文')
        api.save_training_task(value)
        self.assertEqual(f.events,['resolver','scope',('freeze',True),('invalidate','training_task_pairs',True),'enter',('repository',False),'exit'])
        expected=copy.deepcopy(value); self.assertEqual(f.cached,[])
        path=api.training_task_path('job'); self.assertEqual(path.read_text(encoding='utf-8'),json.dumps(value,indent=2))
        f.resolver.version=99; value['status']='completed'; f.events.clear(); api.save_training_task(value)
        self.assertEqual(value['model_profiles'],expected['model_profiles']); self.assertNotIn('resolver',f.events)
        for snapshot in ({},None):
            old=task('old',model_profiles=snapshot)
            with patch.object(api,'resolve_model_profiles',side_effect=AssertionError('old snapshot rewritten')):
                api.save_training_task(old)
            self.assertIs(old['model_profiles'],snapshot)
        self.assertTrue(f.guard.available_to_other_thread())

    def test_write_stage_lock_coverage_invalidation_failure_and_partial_file(self):
        api=self.api; f=self.f; value=task()
        with patch.object(api,'store_read_cache_invalidate',side_effect=RuntimeError('invalidate')):
            with self.assertRaisesRegex(RuntimeError,'invalidate'): api.save_training_task(value)
        self.assertIn('model_profiles',value); self.assertNotIn('enter',f.events)
        self.assertFalse(any(isinstance(event,tuple) and event[0]=='repository' for event in f.events))
        encoder=api.training_task_row; encoded=[]; stages=[]; f.repo=Mock()
        def encode(record,**kwargs):
            stages.append('encode')
            encoded.append((f.guard.available_to_other_thread(),kwargs)); return encoder(record,**kwargs)
        def upsert(table,row):
            stages.append('upsert')
            self.assertFalse(f.guard.available_to_other_thread()); raise RuntimeError('locked-upsert')
        f.repo.upsert_row.side_effect=upsert
        with patch.object(api,'training_task_row',side_effect=encode):
            # No outer lock: the save operation itself must protect both stages.
            with self.assertRaisesRegex(RuntimeError,'locked-upsert'):api.save_training_task(task(' job ',task_id='task'))
            self.assertEqual(encoded,[(False,{'fallback_id':' job '})])
            self.assertEqual(stages,['encode','upsert']); self.assertTrue(f.guard.available_to_other_thread())
            encoded.clear(); stages.clear()
            with f.guard:
                with self.assertRaisesRegex(RuntimeError,'locked-upsert'):api.save_training_task(task(' job ',task_id='task'))
                self.assertFalse(f.guard.available_to_other_thread())
        self.assertEqual(encoded,[(False,{'fallback_id':' job '})]); self.assertTrue(f.guard.available_to_other_thread())
        self.assertEqual(stages,['encode','upsert'])
        with patch.object(api,'training_task_row',side_effect=ValueError('encode')):
            with self.assertRaisesRegex(ValueError,'encode'):api.save_training_task(value)
        self.assertTrue(f.guard.available_to_other_thread())
        f.repo=None; original_write=Path.write_text; path=f.seed('job',{'old':True})
        def partial_write(target,data,**kwargs):
            self.assertFalse(f.guard.available_to_other_thread())
            original_write(target,'partial',**kwargs); raise OSError('partial-write')
        with patch.object(Path,'write_text',partial_write):
            with self.assertRaisesRegex(OSError,'partial-write'):api.save_training_task(value)
        self.assertEqual(path.read_text(),'partial'); self.assertTrue(f.guard.available_to_other_thread())

    def test_missing_resolver_and_save_failures_preserve_order_and_release_lock(self):
        api=self.api; f=self.f; value=task()
        with patch.object(api,'resolve_model_profiles',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'Model profile resolver is not configured'): api.save_training_task(value)
        self.assertEqual(f.events,[]); self.assertEqual(f.cached,['existing']); self.assertNotIn('model_profiles',value)
        self.assertFalse(api.training_task_path('job').exists())
        f.repo=RuntimeError('factory')
        with self.assertRaisesRegex(RuntimeError,'factory'): api.save_training_task(value)
        self.assertIn('model_profiles',value); self.assertEqual(f.cached,[])
        self.assertEqual(f.events[-3:],['enter',('repository',False),'exit']); self.assertTrue(f.guard.available_to_other_thread())
        f.repo=None; f.events.clear()
        with self.assertRaises(KeyError): api.save_training_task({'model_profiles':{}})
        self.assertEqual(f.events,[('invalidate','training_task_pairs',True),'enter',('repository',False),'exit'])
        missing=f.root/'missing'
        with patch.object(api,'TRAINING_TASKS_DIR',missing):
            with self.assertRaises(FileNotFoundError): api.save_training_task(task('missing',model_profiles={}))
        self.assertFalse(missing.exists()); self.assertTrue(f.guard.available_to_other_thread())
        path=f.seed('job',{'old':True})
        with self.assertRaises(TypeError): api.save_training_task(task(bad=object()))
        self.assertEqual(json.loads(path.read_text()),{'old':True})
        with patch.object(Path,'write_text',side_effect=PermissionError('write')):
            with self.assertRaisesRegex(PermissionError,'write'): api.save_training_task(task())
        self.assertTrue(f.guard.available_to_other_thread())

    def test_json_read_shapes_decode_and_filesystem_failures(self):
        api=self.api; f=self.f
        for value in ({'id':'a'},[],[1],None,0,'string'):
            path=f.seed('value',value); self.assertEqual(api.load_training_task(path),value)
        path.write_text('{bad'); self.assertIsNone(api.load_training_task(path))
        self.assertIsNone(api.load_training_task(f.root/'missing.json'))
        with patch.object(Path,'read_text',side_effect=PermissionError('read')): self.assertIsNone(api.load_training_task(path))
        path.write_bytes(b'\xff')
        with self.assertRaises(UnicodeDecodeError): api.load_training_task(path)
        path=f.seed('value',[1])
        with self.assertRaises(TypeError): api.load_training_task_records()
        with self.assertRaises(AttributeError): api.find_training_task('value')
        f.repo=RuntimeError('factory')
        with self.assertRaisesRegex(RuntimeError,'factory'): api.load_training_task(path)

    def test_json_list_mtime_order_path_audit_and_reselect_each_read(self):
        api=self.api; f=self.f
        old=f.seed('old',task('old',updated_at=999),100); new=f.seed('new',task('new',updated_at=1),200)
        f.seed('empty',{},300); bad=f.directory/'bad.json'; bad.write_text('{bad')
        values=api.load_training_task_records()
        self.assertEqual([v['job_id'] for v in values],['new','old'])
        self.assertEqual(f.enrich.call_args_list, [((task('new',updated_at=1),new),),((task('old',updated_at=999),old),)])
        self.assertEqual(sum(e[0]=='repository' for e in f.events if isinstance(e,tuple)),5)
        self.assertNotIn('enter',f.events)
        # Store selection stays late for nested reads, even within one JSON list.
        repository=Mock(); repository.fetch_all.return_value=[{'raw_json':task('new')}]
        f.choices=[None,repository,repository,repository,repository]; f.events.clear()
        values=api.load_training_task_records(); self.assertEqual([v['job_id'] for v in values],['new'])
        self.assertEqual(repository.fetch_all.call_count,4)

    def test_postgres_reads_sorting_aliases_first_match_and_errors(self):
        api=self.api; f=self.f; f.repo=Mock()
        records=[task('a',task_id='alias',remote_training_job_id='remote',updated_at=10),task('z',updated_at=10),task('new',updated_at=11)]
        f.repo.fetch_all.return_value=[{'id':'row-id','job_id':'row-job','raw_json':records[0]},*({'raw_json':v} for v in records[1:])]
        result=api.load_training_task_records(); self.assertEqual([v['job_id'] for v in result],['new','z','a'])
        self.assertTrue(all(len(call.args)==1 for call in f.enrich.call_args_list))
        for identity in ('a','alias','remote','row-id','row-job'):
            self.assertEqual(api.load_training_task(Path(identity+'.json')),records[0])
        self.assertIsNone(api.load_training_task(Path('missing.json')))
        f.repo.fetch_all.return_value=[{'raw_json':task('first',task_id='same')},{'raw_json':task('second',task_id='same')}]
        self.assertEqual(api.load_training_task(Path('same.json'))['job_id'],'first')
        f.seed('same',{'job_id':'json-fallback'})
        f.repo.fetch_all.side_effect=RuntimeError('fetch')
        for action in (api.load_training_task_records,lambda:api.load_training_task(f.directory/'same.json')):
            with self.assertRaisesRegex(RuntimeError,'fetch'): action()
        self.assertNotIn('enter',f.events)

    def test_postgres_save_row_identity_invalid_noop_and_failure(self):
        api=self.api; f=self.f; f.repo=Mock(); value=task('job',id='id',task_id='task',model_profiles={})
        api.save_training_task(value); table,row=f.repo.upsert_row.call_args.args
        self.assertEqual(table,'training_tasks'); self.assertEqual(row['id'],'task'); self.assertEqual(row['job_id'],'job')
        self.assertEqual(row['raw_json'],value); self.assertFalse(api.training_task_path('job').exists())
        f.repo.upsert_row.reset_mock(); api.save_training_task({'model_profiles':{}}); f.repo.upsert_row.assert_not_called()
        f.repo.upsert_row.side_effect=RuntimeError('upsert')
        with self.assertRaisesRegex(RuntimeError,'upsert'): api.save_training_task(value)
        self.assertTrue(f.guard.available_to_other_thread()); self.assertFalse(api.training_task_path('job').exists())

    def test_find_direct_versus_fallback_identity_and_enrichment(self):
        api=self.api; f=self.f
        self.assertIsNone(api.find_training_task('  ')); self.assertEqual(f.events,[])
        f.seed('job',task()); result=api.find_training_task(' job ')
        self.assertEqual(result,task()); f.enrich.assert_not_called()
        # Raw id is intentionally not accepted by the direct branch; the list path adds audit.
        f.seed('raw',{'id':'raw'}); self.assertEqual(api.find_training_task('raw'),{'id':'raw','enriched':True})
        f.enrich.reset_mock(); f.seed('spaced',task(' spaced '))
        self.assertTrue(api.find_training_task('spaced')['enriched']); self.assertTrue(f.enrich.called)
        f.seed('elsewhere',task('canonical',remote_training_job_id='remote'),500)
        self.assertEqual(api.find_training_task('remote')['job_id'],'canonical')
        self.assertIsNone(api.find_training_task('absent'))

    def test_scoped_snapshot_copy_and_two_async_thread_saves(self):
        api=self.api; f=self.f; snapshot={'pipeline':{'version':7,'secret_ref':'fixture-ref'}}
        token=f.resolver.context.set(snapshot)
        try:
            value=task('scoped'); api.save_training_task(value)
            self.assertEqual(value['model_profiles'],snapshot); self.assertIsNot(value['model_profiles'],snapshot)
            snapshot['pipeline']['version']=9; self.assertEqual(value['model_profiles']['pipeline']['version'],7)
        finally: f.resolver.context.reset(token)
        token=f.resolver.context.set({}); f.events.clear()
        try:
            empty=task('empty-scope'); api.save_training_task(empty)
            self.assertEqual(empty['model_profiles'],{})
            self.assertFalse(any(isinstance(event,tuple) and event[0]=='freeze' for event in f.events))
        finally: f.resolver.context.reset(token)
        async def work(owner,version):
            token=f.resolver.context.set({'pipeline':{'version':version}})
            try:
                await asyncio.sleep(0)
                value=task(owner,owner_user_id=owner)
                await asyncio.to_thread(api.save_training_task,value)
                self.assertEqual(f.resolver.context.get()['pipeline']['version'],version)
                return value
            finally:f.resolver.context.reset(token)
        async def check(): return await asyncio.gather(work('alice',11),work('bob',22))
        result=asyncio.run(check())
        self.assertEqual([v['model_profiles']['pipeline']['version'] for v in result],[11,22])
        self.assertIsNone(f.resolver.context.get())
        for value in result:self.assertEqual(json.loads(api.training_task_path(value['job_id']).read_text()),value)

    def test_independent_services_late_directory_resolver_and_root_aliases(self):
        from local_inspection_service.training import task_identity
        from local_inspection_service.training.record_store import TrainingRecordStore,TrainingRows
        from local_inspection_service.storage.runtime_records import training_task_row,row_raw_json_list,file_stem_identifier
        self.assertIs(self.api.training_task_identity_values,task_identity.training_task_identity_values)
        self.assertIs(self.api.training_task_matches_identifier,task_identity.training_task_matches_identifier)
        self.assertIs(self.api.training_task_sort_key,task_identity.training_task_sort_key)
        other_root=self.f.root/'other'; other_root.mkdir(); other=Fixture(other_root)
        def compose(f):
            return TrainingRecordStore(f.repository,lambda:f.directory,lambda:f.guard,lambda:f.provider,f.invalidate,
                TrainingRows(lambda:training_task_row,lambda:row_raw_json_list,file_stem_identifier),f.enrich)
        first=compose(self.f); second=compose(other)
        self.assertEqual(self.f.events,[]); self.assertEqual(other.events,[])
        first.save_training_task(task('first')); other.resolver.version=200; second.save_training_task(task('second'))
        self.assertEqual(first.find_training_task('first')['model_profiles']['pipeline']['version'],1)
        self.assertEqual(second.find_training_task('second')['model_profiles']['pipeline']['version'],200)
        self.assertIsNone(first.find_training_task('second')); self.assertIsNot(self.f.guard,other.guard)
        moved=self.f.root/'moved'; moved.mkdir()
        with patch.object(self.api,'TRAINING_TASKS_DIR',moved),patch.object(self.api,'resolve_model_profiles',return_value=other.resolver):
            self.api.save_training_task(task('late'))
            value=self.api.load_training_task(self.api.training_task_path('late'))
            self.assertEqual(value['model_profiles']['pipeline']['version'],200)
        self.assertTrue((moved/'late.json').exists()); self.assertFalse((self.f.directory/'late.json').exists())

    def test_callback_capture_before_nested_operations(self):
        api=self.api;f=self.f
        for window in ('decode','encode','resolver'):
            for mode in ('normal','prior','missing'):
                with self.subTest(window=window,mode=mode),ExitStack() as stack:
                    events=[];f.events.clear();f.repo=Mock();f.repo.fetch_all.return_value=[]
                    target={'decode':'row_raw_json_list','encode':'training_task_row','resolver':'resolve_model_profiles'}[window]
                    original=getattr(api,target)
                    def callback(label):
                        def call(*args,**kwargs):
                            events.append(label)
                            if window=='decode':return []
                            if window=='encode':return None
                            return original()
                        return call
                    a,b,c=(callback(label) for label in ('A','B','C'))
                    stack.enter_context(patch.object(api,target,a if mode!='missing' else None))
                    def argument():events.append('argument');setattr(api,target,c)
                    if mode=='prior':
                        base_repository=f.repository
                        def repository():
                            result=base_repository();events.append('prior');setattr(api,target,b);return result
                        # Resolver is captured before all persistence work; prior replacement belongs to the caller.
                        if window=='resolver':events.append('prior');setattr(api,target,b)
                        else:stack.enter_context(patch.object(api,'runtime_postgres_repository_or_none',repository))
                    if window=='decode':
                        def fetch(table):argument();return []
                        f.repo.fetch_all.side_effect=fetch;action=api.load_training_task_records
                    elif window=='encode':
                        class Record(dict):
                            def get(self,key,*args):
                                if key=='job_id':argument()
                                return super().get(key,*args)
                        value=Record(job_id='job',model_profiles={});action=lambda:api.save_training_task(value)
                    else:
                        class Record(dict):
                            def __contains__(self,key):
                                if key=='model_profiles':argument()
                                return super().__contains__(key)
                        value=Record(job_id='job');action=lambda:api.save_training_task(value)
                    if mode=='missing':
                        with self.assertRaises(TypeError):action()
                    else:action()
                    expected=(['prior'] if mode=='prior' else [])+['argument']+([] if mode=='missing' else ['B' if mode=='prior' else 'A'])
                    self.assertEqual(events,expected)

    def test_directory_is_resolved_after_task_id_conversion(self):
        api=self.api;f=self.f;destination=f.root/'converted';events=[]
        class Identifier:
            def __str__(self):
                events.append('str');api.TRAINING_TASKS_DIR=destination;return '../task'
        with patch.object(api,'TRAINING_TASKS_DIR',f.directory):
            self.assertEqual(api.training_task_path(Identifier()),destination/'task.json')
        self.assertEqual(events,['str'])

    def test_first_callback_failures_are_not_retried(self):
        api=self.api
        cases=[('repository','list'),('repository','read'),('repository','save'),('invalidate','save'),
               ('resolver','save'),('scope','save'),('snapshot','save'),('encode','save'),
               ('decode','list'),('decode','read'),('identifier','read'),('enrich','list'),
               ('fetch','list'),('fetch','read'),('upsert','save'),('enrich','json_list')]
        for target,operation in cases:
            with self.subTest(target=target,operation=operation),ExitStack() as stack:
                root=stack.enter_context(tempfile.TemporaryDirectory(prefix='training-first-failure-'))
                f=Fixture(root);f.bind(api,stack);value=task();path=f.seed('job',value)
                f.repo=None if operation=='json_list' else Mock()
                if f.repo is not None:f.repo.fetch_all.return_value=[{'raw_json':value}]
                mapping={'repository':(api,'runtime_postgres_repository_or_none',f.repo),
                         'invalidate':(api,'store_read_cache_invalidate',None),
                         'resolver':(api,'resolve_model_profiles',f.resolver),
                         'scope':(f.resolver,'current_snapshot',None),
                         'snapshot':(f.resolver,'snapshot_for_record',{}),
                         'encode':(api,'training_task_row',None),
                         'decode':(api,'row_raw_json_list',[value]),
                         'identifier':(api,'file_stem_identifier','job'),
                         'enrich':(api,'enrich_record_audit_fields',value),
                         'fetch':(f.repo,'fetch_all',[{'raw_json':value}]),
                         'upsert':(f.repo,'upsert_row',None)}
                owner,name,second=mapping[target];error=RuntimeError('first-'+target)
                callback=Mock(side_effect=[error,second]);stack.enter_context(patch.object(owner,name,callback))
                action={'list':api.load_training_task_records,'json_list':api.load_training_task_records,
                        'read':lambda:api.load_training_task(path),'save':lambda:api.save_training_task(value)}[operation]
                with self.assertRaises(RuntimeError) as caught:action()
                self.assertIs(caught.exception,error);self.assertEqual(callback.call_count,1)
                self.assertTrue(f.guard.available_to_other_thread())
                if target in ('resolver','scope','snapshot'):self.assertEqual(f.cached,['existing']);self.assertNotIn('enter',f.events)

    def test_file_first_failures_keep_original_swallow_or_raise(self):
        api=self.api;f=self.f;path=f.seed('job',task())
        for error in (PermissionError('read'),OSError('read'),UnicodeDecodeError('utf-8',b'\xff',0,1,'bad')):
            with self.subTest(error=type(error).__name__):
                callback=Mock(side_effect=[error,json.dumps(task())])
                with patch.object(Path,'read_text',callback):
                    if isinstance(error,UnicodeDecodeError):
                        with self.assertRaises(UnicodeDecodeError) as caught:api.load_training_task(path)
                        self.assertIs(caught.exception,error)
                    else:self.assertIsNone(api.load_training_task(path))
                self.assertEqual(callback.call_count,1)
        error=OSError('write');callback=Mock(side_effect=[error,1])
        with patch.object(Path,'write_text',callback):
            with self.assertRaises(OSError) as caught:api.save_training_task(task())
        self.assertIs(caught.exception,error);self.assertEqual(callback.call_count,1);self.assertTrue(f.guard.available_to_other_thread())
        for name,valid in [('glob',[path]),('stat',path.stat())]:
            error=OSError(name);callback=Mock(side_effect=[error,valid]);original=getattr(Path,name)
            def fail(target,*args,**kwargs):
                if target==(f.directory if name=='glob' else path):return callback(*args,**kwargs)
                return original(target,*args,**kwargs)
            with self.subTest(name=name),patch.object(Path,name,fail):
                with self.assertRaises(OSError) as caught:api.load_training_task_records()
                self.assertIs(caught.exception,error);self.assertEqual(callback.call_count,1)

    def test_new_getters_fail_once_before_dependent_effects(self):
        from dataclasses import replace
        service=self.api._training_records;f=self.f;f.repo=Mock();f.repo.fetch_all.return_value=[]
        for case in ('decode','decode_read','encode','resolver','guard','directory','directory_list'):
            name=case.split('_')[0]
            with self.subTest(case=case),ExitStack() as stack:
                f.events.clear();value=task();error=RuntimeError('getter-'+case)
                f.repo=Mock();f.repo.fetch_all.return_value=[{'raw_json':value}]
                owner=service.rows if name in ('decode','encode') else service
                original=getattr(owner,name);callback=Mock(side_effect=[error,original()])
                if name in ('decode','encode'):stack.enter_context(patch.object(service,'rows',replace(service.rows,**{name:callback})))
                else:stack.enter_context(patch.object(service,name,callback))
                if case=='decode_read':action=lambda:service.load_training_task(Path('job.json'))
                elif case=='directory_list':f.repo=None;action=service.load_training_task_records
                elif name=='decode':action=service.load_training_task_records
                elif name=='directory':action=lambda:service.training_task_path('job')
                else:action=lambda:service.save_training_task(value)
                with self.assertRaises(RuntimeError) as caught:action()
                self.assertIs(caught.exception,error);self.assertEqual(callback.call_count,1)
                self.assertTrue(f.guard.available_to_other_thread())
                if name=='resolver':self.assertEqual(f.events,[]);self.assertNotIn('model_profiles',value)

    def test_json_serialization_first_failure_is_not_retried(self):
        error=TypeError('serialize');value=task();path=self.f.seed('job',{'old':True});previous=path.read_text();callback=Mock(side_effect=[error,json.dumps(value)])
        with patch.object(json,'dumps',callback):
            with self.assertRaises(TypeError) as caught:self.api.save_training_task(value)
        self.assertIs(caught.exception,error);self.assertEqual(callback.call_count,1)
        self.assertTrue(self.f.guard.available_to_other_thread());self.assertEqual(path.read_text(),previous)
        self.assertIn('model_profiles',value);self.assertEqual(self.f.cached,[])

    def test_internal_read_failures_are_not_retried(self):
        service=self.api._training_records;f=self.f;f.seed('job',task())
        for name,operation,valid in [('load_training_task','list',task()),('load_training_task','find',task()),
                                     ('load_training_task_records','fallback',[]),('training_task_path','find',f.directory/'job.json')]:
            with self.subTest(name=name,operation=operation),ExitStack() as stack:
                error=RuntimeError(name);callback=Mock(side_effect=[error,valid]);stack.enter_context(patch.object(service,name,callback))
                if operation=='fallback':stack.enter_context(patch.object(service,'load_training_task',return_value=None))
                action=service.load_training_task_records if operation=='list' else lambda:service.find_training_task('job')
                with self.assertRaises(RuntimeError) as caught:action()
                self.assertIs(caught.exception,error);self.assertEqual(callback.call_count,1)

    def test_single_read_decoder_is_selected_after_fetch_and_for_each_row(self):
        api=self.api;f=self.f;f.repo=Mock();value=task()
        for missing in (False,True):
            with self.subTest(missing=missing),ExitStack() as stack:
                events=[]
                def c(rows):events.append('C');return [value]
                def b(rows):events.append('B');api.row_raw_json_list=c;return []
                def a(rows):events.append('A');return [value]
                def fetch(table):events.append('fetch');api.row_raw_json_list=None if missing else b;return [{},{}]
                stack.enter_context(patch.object(api,'row_raw_json_list',a));f.repo.fetch_all.side_effect=fetch
                if missing:
                    with self.assertRaises(TypeError):api.load_training_task(Path('job.json'))
                    self.assertEqual(events,['fetch'])
                else:
                    self.assertIs(api.load_training_task(Path('job.json')),value);self.assertEqual(events,['fetch','B','C'])
        f.repo.fetch_all.side_effect=None;f.repo.fetch_all.return_value=[]
        with patch.object(api,'row_raw_json_list',side_effect=AssertionError('empty rows decoded')) as decoder:
            self.assertIsNone(api.load_training_task(Path('job.json')));decoder.assert_not_called()

    def test_nested_repository_first_failures_are_not_retried(self):
        api=self.api;f=self.f;f.seed('job',task())
        for operation in ('list','find_direct','find_fallback'):
            with self.subTest(operation=operation):
                f.events.clear();error=RuntimeError('nested-'+operation)
                f.choices=[error,None] if operation=='find_direct' else [None,error,None]
                action=api.load_training_task_records if operation=='list' else lambda:api.find_training_task('absent')
                with self.assertRaises(RuntimeError) as caught:action()
                self.assertIs(caught.exception,error)
                selections=[event for event in f.events if isinstance(event,tuple) and event[0]=='repository']
                self.assertEqual(len(selections),1 if operation=='find_direct' else 2)
                self.assertEqual(f.choices,[None])

    @unittest.skipUnless(PG_CHECK,'use --postgres with an isolated test DSN')
    def test_real_postgres_upsert_alias_update_and_snapshot_persistence(self):
        import psycopg
        from psycopg import sql
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        schema='training_store_'+uuid.uuid4().hex; dsn=os.environ['VANTALINE_POSTGRES_DSN']
        with psycopg.connect(dsn,autocommit=True) as control:
            control.execute(postgres_ddl(schema))
            try:
                with psycopg.connect(dsn) as connection:
                    self.f.repo=PostgresRuntimeRepository(connection,'test',schema); api=self.api
                    value=task('job',task_id='canonical',remote_training_job_id='remote',owner_user_id='alice')
                    api.save_training_task(value)
                    for identity in ('job','canonical','remote'):
                        self.assertEqual(api.find_training_task(identity)['model_profiles'],value['model_profiles'])
                    self.f.resolver.version=200; updated=api.update_training_task('remote',status='running',progress=42)
                    self.assertEqual(updated['model_profiles'],value['model_profiles'])
                    self.assertEqual(api.find_training_task('job')['progress'],42)
                    self.assertEqual(self.f.repo.count_rows(['training_tasks'])['training_tasks'],1)
                    api.save_training_task({'model_profiles':{}})
                    self.assertEqual(self.f.repo.count_rows(['training_tasks'])['training_tasks'],1)
                    self.assertEqual(list(self.f.directory.iterdir()),[])
            finally: control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__=='__main__': unittest.main()
