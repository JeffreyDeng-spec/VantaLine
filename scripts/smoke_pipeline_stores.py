"""Offline pipeline task/state persistence, transaction and shared-guard contracts."""
from contextlib import ExitStack
from contextvars import ContextVar
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
if PG_CHECK:sys.argv.remove('--postgres')


def available(lock):
    results=[]
    def probe():
        acquired=lock.acquire(blocking=False);results.append(acquired)
        if acquired:lock.release()
    thread=threading.Thread(target=probe);thread.start();thread.join(timeout=5)
    if thread.is_alive():raise AssertionError('lock probe stalled')
    return results[0]


class Resolver:
    def __init__(self,fixture):self.fixture=fixture;self.version=1;self.scope=ContextVar('pipeline-snapshot',default=None)
    def current_snapshot(self):self.fixture.events.append('scope');return self.scope.get()
    def snapshot_for_record(self,record):self.fixture.events.append('snapshot');return {'pipeline':{'version':self.version,'secret_ref':'fixture-ref'}}


class Fixture:
    def __init__(self,root):
        self.root=Path(root);self.data=self.root/'data';self.tasks=self.data/'tasks.json';self.state=self.data/'state.json'
        self.events=[];self.repo=None;self.choices=[];self.guard=threading.RLock();self.resolver=Resolver(self)
    def repository(self):
        self.events.append(('repository',self.data.exists(),available(self.guard)))
        result=self.choices.pop(0) if self.choices else self.repo
        if isinstance(result,Exception):raise result
        return result
    def provider(self):self.events.append('resolver');return self.resolver
    def seed(self,path,value):self.data.mkdir(exist_ok=True);path.write_text(json.dumps(value),encoding='utf-8')
    def bind(self,api,stack):
        values={'DATA_DIR':self.data,'PIPELINE_TASKS_PATH':self.tasks,'PIPELINE_STATE_PATH':self.state,
                '_pipeline_state_lock':self.guard,'runtime_postgres_repository_or_none':self.repository,
                'resolve_model_profiles':self.provider}
        for name,value in values.items():stack.enter_context(patch.object(api,name,value))


class PipelineStoreContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ);cls.environment.start()
        cls.runtime=tempfile.TemporaryDirectory(prefix='pipeline-root-');root=Path(cls.runtime.name)
        (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.runtime.cleanup();cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.f=Fixture(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='pipeline-store-')));self.f.bind(self.api,self.stack)

    def test_json_reads_preserve_types_and_exception_boundaries(self):
        api=self.api;f=self.f;empty={'accessory_ids':[],'pending_candidate_ids':[]}
        self.assertEqual(api.load_pipeline_tasks(),[]);self.assertEqual(api.load_pipeline_state(),empty)
        for value in ({},None,1,'text'):
            f.seed(f.tasks,value);self.assertEqual(api.load_pipeline_tasks(),[])
        f.seed(f.tasks,[1,None,{'id':'one'}]);self.assertEqual(api.load_pipeline_tasks(),[1,None,{'id':'one'}])
        with self.assertRaises(AttributeError):api.load_pipeline_task('one')
        for path in (f.tasks,f.state):
            path.write_text('{bad');path.write_bytes(b'\xff')
        for read in (api.load_pipeline_tasks,api.load_pipeline_state):
            with self.assertRaises(UnicodeDecodeError):read()
        with patch.object(Path,'exists',side_effect=OSError('exists')):
            for read in (api.load_pipeline_tasks,api.load_pipeline_state):
                with self.assertRaisesRegex(OSError,'exists'):read()
        with patch.object(Path,'read_text',side_effect=PermissionError('read')):
            self.assertEqual(api.load_pipeline_tasks(),[]);self.assertEqual(api.load_pipeline_state(),empty)
        for path in (f.tasks,f.state):path.write_text('{bad')
        self.assertEqual(api.load_pipeline_tasks(),[]);self.assertEqual(api.load_pipeline_state(),empty)

    def test_task_bulk_json_format_temp_and_error_residue(self):
        api=self.api;f=self.f;values=[{'id':'one','label':'中文'},None,{}]
        api.save_pipeline_tasks(values)
        self.assertEqual(f.tasks.read_text(encoding='utf-8'),json.dumps(values,indent=2,ensure_ascii=False))
        self.assertNotIn('resolver',f.events);self.assertEqual(f.events,[('repository',True,True)])
        tmp=f.tasks.with_name('tasks.json.tmp');self.assertFalse(tmp.exists())
        with patch.object(os,'replace',side_effect=PermissionError('replace')):
            with self.assertRaisesRegex(PermissionError,'replace'):api.save_pipeline_tasks([{'id':'new'}])
        self.assertEqual(json.loads(f.tasks.read_text()),values);self.assertEqual(json.loads(tmp.read_text()),[{'id':'new'}])
        with self.assertRaises(TypeError):api.save_pipeline_tasks([object()])
        self.assertEqual(json.loads(tmp.read_text()),[{'id':'new'}])
        f.repo=RuntimeError('factory')
        with self.assertRaisesRegex(RuntimeError,'factory'):api.save_pipeline_tasks([])

    def test_single_task_freeze_validation_replacement_and_shallow_result(self):
        api=self.api;f=self.f
        self.assertIsNone(api.save_pipeline_task([]));self.assertEqual(f.events,[])
        with patch.object(api,'resolve_model_profiles',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'Model profile resolver is not configured'):api.save_pipeline_task({'id':'new'})
        self.assertEqual(f.events,[]);self.assertFalse(f.data.exists())
        invalid={};self.assertIsNone(api.save_pipeline_task(invalid));self.assertIn('model_profiles',invalid)
        self.assertEqual(f.events,['resolver','scope','snapshot']);self.assertFalse(f.data.exists())
        f.seed(f.tasks,[{'id':'a','old':1},{'id':'b'},{'id':'a','old':2}]);f.events.clear()
        value={'id':'a','nested':{'x':1}};result=api.save_pipeline_task(value)
        self.assertIsNot(result,value);self.assertIs(result['nested'],value['nested'])
        self.assertIs(result['model_profiles'],value['model_profiles'])
        self.assertEqual(json.loads(f.tasks.read_text()),[value,{'id':'b'},{'id':'a','old':2}])
        self.assertEqual(f.events,['resolver','scope','snapshot',('repository',True,True),('repository',True,True),('repository',True,True)])
        f.resolver.version=99;api.save_pipeline_task(value);self.assertEqual(value['model_profiles']['pipeline']['version'],1)
        added={'id':'c','model_profiles':{}};api.save_pipeline_task(added);self.assertEqual(json.loads(f.tasks.read_text())[0],added)
        for snapshot in ({},None):
            with patch.object(api,'resolve_model_profiles',side_effect=AssertionError('old binding replaced')):
                self.assertIs(api.save_pipeline_task({'id':'old','model_profiles':snapshot})['model_profiles'],snapshot)
        padded={'id':' padded ','model_profiles':{}};api.save_pipeline_task(padded)
        self.assertEqual(padded['id'],' padded ');self.assertIsNone(api.load_pipeline_task('padded'))
        alias_only={'task_id':'alias','model_profiles':{}};api.save_pipeline_task(alias_only)
        self.assertNotIn('id',alias_only);self.assertIsNone(api.load_pipeline_task('alias'))

    def test_write_paths_create_data_directory_not_arbitrary_destination_parent(self):
        api=self.api;f=self.f;other=f.root/'uncreated'/'records.json'
        with patch.object(api,'PIPELINE_TASKS_PATH',other):
            with self.assertRaises(FileNotFoundError):api.save_pipeline_tasks([])
        self.assertTrue(f.data.exists());self.assertFalse(other.parent.exists())
        with patch.object(api,'PIPELINE_STATE_PATH',other):
            with self.assertRaises(FileNotFoundError):api.save_pipeline_state({})
        self.assertFalse(other.parent.exists())

    def test_task_single_load_delete_raw_id_and_nested_repository_selection(self):
        api=self.api;f=self.f
        self.assertIsNone(api.load_pipeline_task(' '));self.assertFalse(api.delete_pipeline_task_row(0));self.assertEqual(f.events,[])
        f.seed(f.tasks,[{'id':' a '},{'id':'a'},{'id':'a'},{'id':'b'}])
        self.assertEqual(api.load_pipeline_task(' a '),{'id':'a'})
        self.assertTrue(api.delete_pipeline_task_row(' a '));self.assertEqual(json.loads(f.tasks.read_text()),[{'id':' a '},{'id':'b'}])
        self.assertFalse(api.delete_pipeline_task_row('missing'))
        repo=Mock();repo.fetch_all.return_value=[{'raw_json':{'id':'pg'}}]
        f.choices=[None,repo];self.assertEqual(api.load_pipeline_task('pg'),{'id':'pg'})
        f.choices=[None,repo,repo];api.save_pipeline_task({'id':'new','model_profiles':{}})
        table,rows=repo.replace_all.call_args.args;self.assertEqual(table,'pipeline_tasks')
        self.assertEqual([row['id'] for row in rows],['new','pg']);self.assertEqual(json.loads(f.tasks.read_text()),[{'id':' a '},{'id':'b'}])

    def test_postgres_task_dispatch_invalid_bulk_and_no_json_fallback(self):
        api=self.api;f=self.f;f.repo=Mock();f.repo.fetch_all.return_value=[{'raw_json':{'id':'one'}}]
        self.assertEqual(api.load_pipeline_tasks(),[{'id':'one'}]);f.repo.fetch_all.assert_called_once_with('pipeline_tasks')
        f.repo.fetch_by_primary_key.return_value={'raw_json':{'id':'one'}}
        self.assertEqual(api.load_pipeline_task(' one '),{'id':'one'});f.repo.fetch_by_primary_key.assert_called_once_with('pipeline_tasks',{'id':'one'})
        f.repo.fetch_by_primary_key.return_value={}
        self.assertIsNone(api.load_pipeline_task('one'));self.assertTrue(api.delete_pipeline_task_row('one'))
        f.repo.delete_by_primary_key.assert_called_once_with('pipeline_tasks',{'id':'one'})
        f.repo.fetch_by_primary_key.return_value=None;self.assertFalse(api.delete_pipeline_task_row('one'))
        api.save_pipeline_tasks([{},None,{'id':'one'},3]);self.assertEqual(len(f.repo.replace_all.call_args.args[1]),1)
        api.save_pipeline_tasks([{},None]);f.repo.replace_all.assert_called_with('pipeline_tasks',[])
        value={'id':'one','nested':[]};result=api.save_pipeline_task(value)
        self.assertIs(result['nested'],value['nested']);self.assertEqual(f.repo.upsert_row.call_args.args[1]['raw_json'],value)
        f.seed(f.tasks,[{'id':'json'}]);f.repo.fetch_all.side_effect=RuntimeError('database')
        with self.assertRaisesRegex(RuntimeError,'database'):api.load_pipeline_tasks()
        f.repo.upsert_row.side_effect=ValueError('upsert')
        with self.assertRaisesRegex(ValueError,'upsert'):api.save_pipeline_task({'id':'two'})
        self.assertEqual(json.loads(f.tasks.read_text()),[{'id':'json'}])

    def test_state_normalization_and_full_save_order(self):
        api=self.api;f=self.f
        raw={'accessory_ids':[' a ',0,None,False,'a',2,True], 'pending_candidate_ids':'aba','extra':['ignored']}
        before=copy.deepcopy(raw);expected={'accessory_ids':['a','2','True'],'pending_candidate_ids':['a','b']}
        self.assertEqual(api.normalize_pipeline_state(raw),expected);self.assertEqual(raw,before)
        for value in (None,[],4):self.assertEqual(api.normalize_pipeline_state(value),{'accessory_ids':[],'pending_candidate_ids':[]})
        with self.assertRaises(TypeError):api.save_pipeline_state({'accessory_ids':1})
        self.assertTrue(f.data.exists());self.assertEqual(f.events,[])
        api.save_pipeline_state(raw);self.assertEqual(f.state.read_text(),json.dumps(expected,indent=2,ensure_ascii=False))
        tmp=f.state.with_name('state.json.tmp')
        with patch.object(os,'replace',side_effect=OSError('replace')):
            with self.assertRaisesRegex(OSError,'replace'):api.save_pipeline_state({})
        self.assertEqual(json.loads(f.state.read_text()),expected);self.assertEqual(json.loads(tmp.read_text()),{'accessory_ids':[],'pending_candidate_ids':[]})
        f.repo=Mock()
        with patch('time.time',return_value=17.9):api.save_pipeline_state(raw)
        self.assertEqual(f.repo.replace_all.call_args.args,('pipeline_state',[
            {'state_key':'accessory_ids','state_value_json':['a','2','True'],'updated_at':17},
            {'state_key':'pending_candidate_ids','state_value_json':['a','b'],'updated_at':17}]))

    def test_state_partial_keys_filter_and_json_reselection(self):
        api=self.api;f=self.f;value={'accessory_ids':['x']}
        api.save_pipeline_state_keys(value,set());api.save_pipeline_state_keys(value,{'unknown'})
        self.assertEqual(f.events,[]);self.assertFalse(f.data.exists())
        with self.assertRaises(TypeError):api.save_pipeline_state_keys({'accessory_ids':1},set())
        api.save_pipeline_state_keys(value,{'accessory_ids'})
        self.assertEqual(f.events,[('repository',False,True),('repository',True,True)])
        self.assertEqual(json.loads(f.state.read_text()),{'accessory_ids':['x'],'pending_candidate_ids':[]})
        repo=Mock();f.choices=[None,repo];api.save_pipeline_state_keys({'pending_candidate_ids':['c']},{'pending_candidate_ids'})
        self.assertEqual(repo.replace_all.call_args.args[0],'pipeline_state')
        repo.upsert_row.assert_not_called()

    def test_state_postgres_partial_commit_rollback_and_pretry_errors(self):
        api=self.api;f=self.f;f.repo=Mock();events=[]
        def direct_upsert(*args,**kwargs):
            self.assertTrue(available(f.guard));events.append(('upsert',args,kwargs))
        f.repo.upsert_row.side_effect=direct_upsert
        f.repo.connection.commit.side_effect=lambda:events.append('commit')
        f.repo.connection.rollback.side_effect=lambda:events.append('rollback')
        value={'accessory_ids':['a'],'pending_candidate_ids':['c']}
        with patch('time.time',return_value=23):api.save_pipeline_state_keys(value,{'accessory_ids','unknown'})
        self.assertEqual(events,[('upsert',('pipeline_state',{'state_key':'accessory_ids','state_value_json':['a'],'updated_at':23}),{'commit':False}),'commit'])
        for failure in ('upsert','commit'):
            events.clear();f.repo.upsert_row.side_effect=lambda *a,**kw:events.append('upsert')
            f.repo.connection.commit.side_effect=lambda:events.append('commit')
            if failure=='upsert':f.repo.upsert_row.side_effect=ValueError('upsert')
            else:f.repo.connection.commit.side_effect=ValueError('commit')
            with self.assertRaisesRegex(ValueError,failure):api.save_pipeline_state_keys(value,{'accessory_ids'})
            self.assertEqual(events[-1],'rollback')
        f.repo.connection.rollback.side_effect=RuntimeError('rollback')
        with self.assertRaisesRegex(RuntimeError,'rollback'):api.save_pipeline_state_keys(value,{'accessory_ids'})
        f.repo.connection.rollback=None
        with self.assertRaisesRegex(ValueError,'commit'):api.save_pipeline_state_keys(value,{'accessory_ids'})
        f.repo.connection.rollback=Mock();f.repo.upsert_row.side_effect=KeyboardInterrupt('cancel')
        with self.assertRaises(KeyboardInterrupt):api.save_pipeline_state_keys(value,{'accessory_ids'})
        f.repo.connection.rollback.assert_not_called()
        f.repo.upsert_row.reset_mock();f.repo.connection.commit.reset_mock()
        with patch.object(api,'pipeline_state_rows',side_effect=ValueError('encode')):
            with self.assertRaisesRegex(ValueError,'encode'):api.save_pipeline_state_keys(value,{'accessory_ids'})
        f.repo.upsert_row.assert_not_called();f.repo.connection.commit.assert_not_called();f.repo.connection.rollback.assert_not_called()
        f.repo.connection.commit.side_effect=None
        with patch.object(api,'pipeline_state_rows',return_value=[]):api.save_pipeline_state_keys(value,{'accessory_ids'})
        f.repo.connection.commit.assert_called_once();f.repo.upsert_row.assert_not_called()

    def test_update_shared_guard_copy_changed_fields_and_exception_release(self):
        api=self.api;f=self.f;initial={'accessory_ids':['a'],'pending_candidate_ids':['c']};f.seed(f.state,initial);calls=[]
        def mutate(value):
            calls.append('mutate')
            self.assertFalse(available(f.guard));value['accessory_ids'].append('b');value['pending_candidate_ids'].append('c')
        result=api.update_pipeline_state(mutate)
        self.assertEqual(len(calls),1)
        self.assertEqual(result,{'accessory_ids':['a','b'],'pending_candidate_ids':['c']})
        self.assertEqual(f.events,[('repository',True,False)]*3);self.assertTrue(available(f.guard))
        f.events.clear();api.update_pipeline_state(lambda value:None)
        self.assertEqual(f.events,[('repository',True,False)])
        failures=[]
        def failure(value):failures.append('called');value['accessory_ids'].append('discard');raise RuntimeError('mutator')
        with self.assertRaisesRegex(RuntimeError,'mutator'):api.update_pipeline_state(failure)
        self.assertEqual(len(failures),1)
        self.assertTrue(available(f.guard));self.assertEqual(json.loads(f.state.read_text()),result)
        with patch.object(json,'dumps',side_effect=ValueError('deep-copy')):
            with self.assertRaisesRegex(ValueError,'deep-copy'):api.update_pipeline_state(lambda value:None)
        self.assertTrue(available(f.guard))
        with self.assertRaises(TypeError):api.update_pipeline_state(lambda value:value.update(accessory_ids=1))
        self.assertTrue(available(f.guard));self.assertEqual(json.loads(f.state.read_text()),result)
        ignored_return=Mock(return_value={'accessory_ids':['ignored-return']})
        self.assertEqual(api.update_pipeline_state(ignored_return),result);ignored_return.assert_called_once()
        f.repo=Mock();f.repo.fetch_all.return_value=[{'state_key':key,'state_value_json':value} for key,value in initial.items()]
        def upsert(table,row,*,commit):
            self.assertFalse(available(f.guard));self.assertFalse(commit);self.assertEqual(row['state_key'],'accessory_ids')
        f.repo.upsert_row.side_effect=upsert
        f.repo.connection.commit.side_effect=lambda:self.assertFalse(available(f.guard))
        encoder=api.pipeline_state_rows
        def locked_encode(value,**kwargs):
            self.assertFalse(available(f.guard));return encoder(value,**kwargs)
        with patch.object(api,'pipeline_state_rows',side_effect=locked_encode):
            api.update_pipeline_state(lambda value:value['accessory_ids'].append('b'))
        f.repo.upsert_row.assert_called_once();f.repo.connection.commit.assert_called_once();self.assertTrue(available(f.guard))

    def test_state_add_remove_order_deduplication_and_concurrent_updates(self):
        api=self.api;f=self.f
        self.assertEqual(api.add_pipeline_accessory_id(' a ')['accessory_ids'],['a'])
        self.assertEqual(api.add_pipeline_accessory_id('b')['accessory_ids'],['b','a'])
        self.assertEqual(api.add_pipeline_accessory_id('a')['accessory_ids'],['b','a'])
        self.assertEqual(api.add_pipeline_pending_candidate_id(' c ')['pending_candidate_ids'],['c'])
        self.assertEqual(api.remove_pipeline_accessory_id(' b ')['accessory_ids'],['a'])
        self.assertEqual(api.remove_pipeline_pending_candidate_id('c')['pending_candidate_ids'],[])
        errors=[]
        def add(name):
            try:api.add_pipeline_accessory_id(name)
            except BaseException as error:errors.append(error)
        threads=[threading.Thread(target=add,args=(name,)) for name in ('x','y')]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads));self.assertEqual(errors,[])
        self.assertEqual(set(api.load_pipeline_state()['accessory_ids']),{'a','x','y'})

    def test_independent_store_instances_lazy_paths_and_root_state_alias(self):
        from local_inspection_service.pipeline import state_policy
        from local_inspection_service.pipeline.task_store import PipelineTaskStore,PipelineTaskPaths,PipelineTaskRows
        from local_inspection_service.pipeline.state_store import PipelineStateStore,PipelineStatePaths,PipelineStateRows
        from local_inspection_service.storage.runtime_records import pipeline_task_row,row_raw_json_list,pipeline_state_rows,pipeline_state_from_rows
        self.assertIs(self.api.normalize_pipeline_state,state_policy.normalize_pipeline_state)
        other_root=self.f.root/'other';other_root.mkdir();other=Fixture(other_root)
        def compose(f):
            tasks=PipelineTaskStore(f.repository,PipelineTaskPaths(lambda:f.data,lambda:f.tasks),
                PipelineTaskRows(pipeline_task_row,lambda:row_raw_json_list),lambda:f.provider)
            state=PipelineStateStore(f.repository,PipelineStatePaths(lambda:f.data,lambda:f.state),
                PipelineStateRows(lambda:pipeline_state_rows,lambda:pipeline_state_from_rows),lambda:f.guard)
            self.assertEqual(f.events,[]);self.assertFalse(f.data.exists())
            return tasks,state
        first_tasks,first_state=compose(self.f);second_tasks,second_state=compose(other)
        first_tasks.save_pipeline_task({'id':'first'});other.resolver.version=200;second_tasks.save_pipeline_task({'id':'second'})
        self.assertEqual(first_tasks.load_pipeline_task('first')['model_profiles']['pipeline']['version'],1)
        self.assertEqual(second_tasks.load_pipeline_task('second')['model_profiles']['pipeline']['version'],200)
        self.assertIsNone(first_tasks.load_pipeline_task('second'))
        first_state.add_pipeline_accessory_id('first');second_state.add_pipeline_pending_candidate_id('second')
        self.assertEqual(first_state.load_pipeline_state(),{'accessory_ids':['first'],'pending_candidate_ids':[]})
        self.assertEqual(second_state.load_pipeline_state(),{'accessory_ids':[],'pending_candidate_ids':['second']})
        moved=self.f.root/'moved.json'
        with patch.object(self.api,'PIPELINE_STATE_PATH',moved):self.api.add_pipeline_accessory_id('late')
        self.assertEqual(json.loads(moved.read_text()),{'accessory_ids':['late'],'pending_candidate_ids':[]})
        self.assertEqual(first_state.load_pipeline_state()['accessory_ids'],['first'])

    def test_callbacks_capture_before_fetch_clock_and_snapshot_membership(self):
        api=self.api;f=self.f
        windows=('task_decode','state_decode','state_encode_full','state_encode_keys','resolver')
        for window in windows:
            for mode in ('normal','prior','missing'):
                with self.subTest(window=window,mode=mode),ExitStack() as stack:
                    events=[];f.repo=Mock();f.repo.fetch_all.return_value=[]
                    target=('row_raw_json_list' if window=='task_decode' else 'pipeline_state_from_rows' if window=='state_decode' else 'pipeline_state_rows' if window.startswith('state_encode') else 'resolve_model_profiles')
                    original=getattr(api,target)
                    def callback(label):
                        def call(*args,**kwargs):
                            events.append(label)
                            return original() if window=='resolver' else {} if window=='state_decode' else []
                        return call
                    a,b,c=(callback(label) for label in ('A','B','C'))
                    stack.enter_context(patch.object(api,target,a if mode!='missing' else None))
                    if mode=='prior':
                        if window=='resolver':events.append('prior');setattr(api,target,b)
                        else:
                            base_repository=f.repository
                            def repository():result=base_repository();events.append('prior');setattr(api,target,b);return result
                            stack.enter_context(patch.object(api,'runtime_postgres_repository_or_none',repository))
                    def argument():events.append('argument');setattr(api,target,c);return 10
                    if window.endswith('decode'):
                        def fetch(table):argument();return []
                        f.repo.fetch_all.side_effect=fetch
                        action=api.load_pipeline_tasks if window=='task_decode' else api.load_pipeline_state
                    elif window.startswith('state_encode'):
                        stack.enter_context(patch('time.time',side_effect=argument))
                        action=(lambda:api.save_pipeline_state({})) if window.endswith('full') else (lambda:api.save_pipeline_state_keys({'accessory_ids':['a']},{'accessory_ids'}))
                    else:
                        class Record(dict):
                            def __contains__(self,key):
                                if key=='model_profiles':argument()
                                return super().__contains__(key)
                        action=lambda:api.save_pipeline_task(Record(id='job'))
                    if mode=='missing':
                        with self.assertRaises(TypeError):action()
                    else:action()
                    self.assertEqual(events,(['prior'] if mode=='prior' else [])+['argument']+([] if mode=='missing' else ['B' if mode=='prior' else 'A']))

    def test_repository_callback_and_transaction_first_failures(self):
        api=self.api
        operations=('task_list','task_bulk','task_read','task_single','task_delete','state_read','state_full','state_keys')
        cases=[('repository',name) for name in operations]+[
            ('task_decode','task_list'),('task_decode','task_read'),('state_decode','state_read'),
            ('task_encode','task_bulk'),('task_encode','task_single'),('state_encode','state_full'),('state_encode','state_keys'),
            ('resolver','task_single'),('scope','task_single'),('snapshot','task_single'),
            ('fetch_all','task_list'),('fetch_all','state_read'),('fetch_one','task_read'),('fetch_one','task_delete'),
            ('replace','task_bulk'),('replace','state_full'),('upsert','task_single'),('upsert','state_keys'),
            ('delete','task_delete'),('commit','state_keys'),('rollback','state_keys'),('clock','state_full'),('clock','state_keys')]
        for target,operation in cases:
            with self.subTest(target=target,operation=operation),ExitStack() as stack:
                f=Fixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='pipeline-first-error-')));f.bind(api,stack)
                f.repo=Mock();record={'id':'one'};rows=[{'raw_json':record}];state={'accessory_ids':['a'],'pending_candidate_ids':[]}
                f.repo.fetch_all.return_value=[];f.repo.fetch_by_primary_key.return_value=rows[0]
                actions={'task_list':api.load_pipeline_tasks,'task_bulk':lambda:api.save_pipeline_tasks([record]),
                         'task_read':lambda:api.load_pipeline_task('one'),'task_single':lambda:api.save_pipeline_task(record),
                         'task_delete':lambda:api.delete_pipeline_task_row('one'),'state_read':api.load_pipeline_state,
                         'state_full':lambda:api.save_pipeline_state(state),'state_keys':lambda:api.save_pipeline_state_keys(state,{'accessory_ids'})}
                mapping={'repository':(api,'runtime_postgres_repository_or_none',f.repo),
                         'task_decode':(api,'row_raw_json_list',[record]),'state_decode':(api,'pipeline_state_from_rows',state),
                         'task_encode':(api,'pipeline_task_row',None),'state_encode':(api,'pipeline_state_rows',[]),
                         'resolver':(api,'resolve_model_profiles',f.resolver),'scope':(f.resolver,'current_snapshot',None),
                         'snapshot':(f.resolver,'snapshot_for_record',{}),'fetch_all':(f.repo,'fetch_all',[]),
                         'fetch_one':(f.repo,'fetch_by_primary_key',rows[0]),'replace':(f.repo,'replace_all',None),
                         'upsert':(f.repo,'upsert_row',None),'delete':(f.repo,'delete_by_primary_key',None),
                         'commit':(f.repo.connection,'commit',None),'rollback':(f.repo.connection,'rollback',None)}
                error=RuntimeError('first-'+target);callback=Mock(side_effect=[error,10 if target=='clock' else mapping[target][2]])
                if target=='clock':stack.enter_context(patch('time.time',callback))
                else:owner,name,_=mapping[target];stack.enter_context(patch.object(owner,name,callback))
                if target=='rollback':f.repo.upsert_row.side_effect=RuntimeError('original-write')
                with self.assertRaises(RuntimeError) as caught:actions[operation]()
                self.assertIs(caught.exception,error);self.assertEqual(callback.call_count,1)
                self.assertEqual(f.repo.connection.rollback.call_count,1 if operation=='state_keys' and target in ('upsert','commit','rollback') else 0)
                self.assertTrue(available(f.guard))

    def test_json_first_failures_are_not_retried(self):
        api=self.api
        for domain in ('task','state'):
            for target in ('exists','read','mkdir','write','replace','serialize'):
                with self.subTest(domain=domain,target=target),ExitStack() as stack:
                    f=Fixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='pipeline-file-error-')));f.bind(api,stack)
                    path=f.tasks if domain=='task' else f.state;value=[{'id':'one'}] if domain=='task' else {'accessory_ids':['a']}
                    f.seed(path,value);tmp=path.with_name(path.name+'.tmp');previous=path.read_text()
                    read=api.load_pipeline_tasks if domain=='task' else api.load_pipeline_state
                    save=(lambda:api.save_pipeline_tasks(value)) if domain=='task' else (lambda:api.save_pipeline_state(value))
                    error=OSError('first-'+target);valid={'exists':True,'read':json.dumps(value),'mkdir':None,'write':10,'replace':None,'serialize':json.dumps(value)}[target]
                    callback=Mock(side_effect=[error,valid])
                    if target in ('exists','read','mkdir','write'):
                        method={'exists':'exists','read':'read_text','mkdir':'mkdir','write':'write_text'}[target];original=getattr(Path,method)
                        subject=f.data if target=='mkdir' else tmp if target=='write' else path
                        if target=='write':
                            def write_failure(*args,**kwargs):
                                if callback.call_count==1:raise error
                                return original(subject,*args,**kwargs)
                            callback.side_effect=write_failure
                        def invoke(actual,*args,**kwargs):return callback(*args,**kwargs) if actual==subject else original(actual,*args,**kwargs)
                        stack.enter_context(patch.object(Path,method,invoke))
                    elif target=='replace':stack.enter_context(patch.object(os,'replace',callback))
                    else:stack.enter_context(patch.object(json,'dumps',callback))
                    if target=='read':
                        expected=[] if domain=='task' else {'accessory_ids':[],'pending_candidate_ids':[]}
                        self.assertEqual(read(),expected)
                    else:
                        with self.assertRaises(OSError) as caught:(read if target=='exists' else save)()
                        self.assertIs(caught.exception,error)
                    self.assertEqual(callback.call_count,1)
                    # Use the original reader while the read_text fault is still installed.
                    if target!='read':self.assertEqual(path.read_text(),previous)

    def test_new_getter_first_failures_do_not_retry(self):
        from dataclasses import replace
        api=self.api;f=self.f
        for case in ('task_decode_list','task_decode_read','state_decode','state_encode_full','state_encode_keys','resolver','guard','task_path_read','state_path_read','task_data','state_data'):
            with self.subTest(case=case),ExitStack() as stack:
                f.repo=Mock();f.repo.fetch_all.return_value=[];f.repo.fetch_by_primary_key.return_value={'raw_json':{'id':'one'}}
                tasks=api._pipeline_task_store;states=api._pipeline_state_store
                if case.startswith('task_decode'):service=tasks;part='rows';name='decode';action=tasks.load_pipeline_tasks if case.endswith('list') else lambda:tasks.load_pipeline_task('one')
                elif case=='state_decode':service=states;part='rows';name='decode';action=states.load_pipeline_state
                elif case.startswith('state_encode'):service=states;part='rows';name='encode';action=(lambda:states.save_pipeline_state({})) if case.endswith('full') else lambda:states.save_pipeline_state_keys({'accessory_ids':['a']},{'accessory_ids'})
                elif case=='resolver':service=tasks;part=None;name='resolver';action=lambda:tasks.save_pipeline_task({'id':'one'})
                elif case=='guard':service=states;part=None;name='guard';action=lambda:states.update_pipeline_state(lambda state:None)
                else:
                    service=tasks if case.startswith('task_') else states;part='paths';name='data' if case.endswith('data') else 'tasks' if service is tasks else 'state';f.repo=None
                    action=(lambda:tasks.save_pipeline_tasks([])) if case=='task_data' else (lambda:states.save_pipeline_state({})) if case=='state_data' else tasks.load_pipeline_tasks if service is tasks else states.load_pipeline_state
                owner=getattr(service,part) if part else service;original=getattr(owner,name);error=RuntimeError(case);callback=Mock(side_effect=[error,original()])
                if part:stack.enter_context(patch.object(service,part,replace(owner,**{name:callback})))
                else:stack.enter_context(patch.object(service,name,callback))
                with self.assertRaises(RuntimeError) as caught:action()
                self.assertIs(caught.exception,error);self.assertEqual(callback.call_count,1);self.assertTrue(available(f.guard))

    def test_update_holds_guard_during_copy_and_normalization(self):
        api=self.api;f=self.f;f.seed(f.state,{'accessory_ids':['a']});events=[];original=json.dumps
        def dumps(*args,**kwargs):events.append(('copy',available(f.guard)));return original(*args,**kwargs)
        class Identifier:
            def __str__(self):events.append(('normalize',available(f.guard)));return 'b'
        with patch.object(json,'dumps',side_effect=dumps):
            result=api.update_pipeline_state(lambda state:state['accessory_ids'].append(Identifier()))
        self.assertEqual(result,{'accessory_ids':['a','b'],'pending_candidate_ids':[]})
        self.assertTrue(events);self.assertTrue(any(name=='copy' for name,_ in events));self.assertTrue(any(name=='normalize' for name,_ in events))
        self.assertTrue(all(not free for _,free in events));self.assertTrue(available(f.guard))

    def test_internal_store_first_failures_are_not_retried(self):
        tasks=self.api._pipeline_task_store;states=self.api._pipeline_state_store;f=self.f
        cases=[('task','load_pipeline_tasks','read',[{'id':'one'}]),('task','load_pipeline_tasks','save_existing',[{'id':'one'}]),
               ('task','save_pipeline_tasks','save_existing',None),('task','save_pipeline_tasks','save_new',None),
               ('task','load_pipeline_tasks','delete',[{'id':'one'}]),('task','save_pipeline_tasks','delete',None),
               ('state','save_pipeline_state','keys',None),('state','load_pipeline_state','update',{'accessory_ids':[],'pending_candidate_ids':[]}),
               ('state','save_pipeline_state_keys','update',None)]
        for domain,name,operation,valid in cases:
            with self.subTest(domain=domain,name=name,operation=operation),ExitStack() as stack:
                f.seed(f.tasks,[{'id':'one'},{'id':'keep'}]);f.seed(f.state,{'accessory_ids':['a'],'pending_candidate_ids':[]})
                before_tasks=f.tasks.read_text();before_state=f.state.read_text();mutations=[]
                value={'id':'two' if operation=='save_new' else 'one','model_profiles':{}}
                def mutate(state):mutations.append('called');state['accessory_ids'].append('b')
                actions={'read':lambda:tasks.load_pipeline_task('one'),'save_existing':lambda:tasks.save_pipeline_task(value),
                         'save_new':lambda:tasks.save_pipeline_task(value),'delete':lambda:tasks.delete_pipeline_task_row('one'),
                         'keys':lambda:states.save_pipeline_state_keys({'accessory_ids':['b']},{'accessory_ids'}),
                         'update':lambda:states.update_pipeline_state(mutate)}
                error=RuntimeError(name);callback=Mock(side_effect=[error,valid]);stack.enter_context(patch.object(tasks if domain=='task' else states,name,callback))
                with self.assertRaises(RuntimeError) as caught:actions[operation]()
                self.assertIs(caught.exception,error);self.assertEqual(callback.call_count,1);self.assertTrue(available(f.guard))
                self.assertEqual(f.tasks.read_text(),before_tasks);self.assertEqual(f.state.read_text(),before_state)
                if operation=='update':self.assertEqual(mutations,[] if name=='load_pipeline_state' else ['called'])
                if name=='save_pipeline_tasks':
                    expected=[value,{'id':'keep'}] if operation=='save_existing' else [value,{'id':'one'},{'id':'keep'}] if operation=='save_new' else [{'id':'keep'}]
                    self.assertEqual(callback.call_args.args[0],expected)

    def test_copy_and_row_filter_first_failures_remain_outside_transactions(self):
        api=self.api;f=self.f;initial={'accessory_ids':['a'],'pending_candidate_ids':[]};f.seed(f.state,initial)
        error=RuntimeError('copy');callback=Mock(side_effect=[error,json.dumps(initial)]);mutator=Mock()
        with patch.object(json,'dumps',callback):
            with self.assertRaises(RuntimeError) as caught:api.update_pipeline_state(mutator)
        self.assertIs(caught.exception,error);self.assertEqual(callback.call_count,1);mutator.assert_not_called();self.assertTrue(available(f.guard))
        self.assertEqual(json.loads(f.state.read_text()),initial)
        f.repo=Mock();error=RuntimeError('row-filter');calls=[]
        class Row(dict):
            def get(self,key,*args):
                if key=='state_key':
                    calls.append(key)
                    if len(calls)==1:raise error
                return super().get(key,*args)
        row=Row(state_key='accessory_ids',state_value_json=['b'],updated_at=10)
        with patch.object(api,'pipeline_state_rows',return_value=[row]):
            with self.assertRaises(RuntimeError) as caught:api.save_pipeline_state_keys({'accessory_ids':['b']},{'accessory_ids'})
        self.assertIs(caught.exception,error);self.assertEqual(calls,['state_key'])
        f.repo.upsert_row.assert_not_called();f.repo.connection.commit.assert_not_called();f.repo.connection.rollback.assert_not_called()

    def test_single_task_decoder_is_selected_after_fetch_and_row_truth(self):
        api=self.api;f=self.f;f.repo=Mock();value={'id':'one'}
        for mode in ('normal','missing','falsey','empty_id'):
            with self.subTest(mode=mode),ExitStack() as stack:
                events=[]
                def decoder(label):
                    def call(rows):events.append(label);return [value]
                    return call
                a,b,c=(decoder(label) for label in ('A','B','C'))
                class Row(dict):
                    def __bool__(self):events.append('truth');api.row_raw_json_list=None if mode=='missing' else c;return mode!='falsey'
                def fetch(*args):events.append('fetch');api.row_raw_json_list=b;return Row(raw_json=value)
                f.repo.fetch_by_primary_key.side_effect=fetch;stack.enter_context(patch.object(api,'row_raw_json_list',a))
                if mode=='missing':
                    with self.assertRaises(TypeError):api.load_pipeline_task('one')
                    self.assertEqual(events,['fetch','truth'])
                elif mode in ('falsey','empty_id'):
                    self.assertIsNone(api.load_pipeline_task('' if mode=='empty_id' else 'one'))
                    self.assertEqual(events,[] if mode=='empty_id' else ['fetch','truth'])
                else:self.assertIs(api.load_pipeline_task('one'),value);self.assertEqual(events,['fetch','truth','C'])

    @unittest.skipUnless(PG_CHECK,'use --postgres with an isolated test DSN')
    def test_real_postgres_tasks_partial_state_and_rollback(self):
        from types import SimpleNamespace
        import psycopg
        from psycopg import sql
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        schema='pipeline_store_'+uuid.uuid4().hex;dsn=os.environ['VANTALINE_POSTGRES_DSN']
        with psycopg.connect(dsn,autocommit=True) as control:
            control.execute(postgres_ddl(schema))
            try:
                with psycopg.connect(dsn) as connection:
                    repo=PostgresRuntimeRepository(connection,'test',schema);self.f.repo=repo;api=self.api
                    value={'id':'one','name':'One'};api.save_pipeline_task(value)
                    self.f.resolver.version=99;value['name']='Changed';api.save_pipeline_task(value)
                    self.assertEqual(api.load_pipeline_task('one')['model_profiles']['pipeline']['version'],1)
                    self.assertTrue(api.delete_pipeline_task_row('one'));self.assertFalse(api.delete_pipeline_task_row('one'))
                    api.save_pipeline_tasks([{'id':'new'},None,{}]);self.assertEqual(api.load_pipeline_tasks(),[{'id':'new'}])
                    state={'accessory_ids':['a'],'pending_candidate_ids':['c']};api.save_pipeline_state(state)
                    api.save_pipeline_state_keys({'accessory_ids':['b'],'pending_candidate_ids':['discard']},{'accessory_ids'})
                    expected={'accessory_ids':['b'],'pending_candidate_ids':['c']};self.assertEqual(api.load_pipeline_state(),expected)
                    original=repo.upsert_row;calls=[]
                    def second_write_fails(table,row,*,commit=True):
                        calls.append(row['state_key'])
                        if len(calls)==2:raise RuntimeError('second-state-write')
                        original(table,row,commit=commit)
                    self.f.repo=SimpleNamespace(connection=connection,upsert_row=second_write_fails)
                    try:
                        with self.assertRaisesRegex(RuntimeError,'second-state-write'):
                            api.save_pipeline_state_keys({'accessory_ids':['bad'],'pending_candidate_ids':['bad']},{'accessory_ids','pending_candidate_ids'})
                    finally:self.f.repo=repo
                    self.assertEqual(calls,['accessory_ids','pending_candidate_ids']);self.assertEqual(api.load_pipeline_state(),expected)
                    self.assertFalse(self.f.tasks.exists());self.assertFalse(self.f.state.exists())
            finally:control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__=='__main__':unittest.main()
