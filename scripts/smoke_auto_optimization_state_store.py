"""Synthetic persistence/cache contract, using temporary files and repository substitutes."""
import ast
import copy
from contextvars import ContextVar
from dataclasses import fields
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from typing import Any
import unittest
import uuid
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from local_inspection_service.model_profiles.snapshots import freeze_record
from auto_application_test_methods import auto_method,auto_port
from auto_optimization_test_ports import test_capability, assert_capability_owner
BASELINE=os.environ.get('VANTALINE_AUTO_STATE_BASELINE_SOURCE')
PG_CHECK='--postgres' in sys.argv
if PG_CHECK:sys.argv.remove('--postgres')
NAMES={'auto_optimize_task_path','load_auto_optimize_state','save_auto_optimize_state','list_auto_optimize_states'}


def create(bindings):
    if BASELINE:
        nodes=[node for node in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(node,ast.FunctionDef) and node.name in NAMES]
        assert len(nodes)==4
        namespace=dict(bindings,Any=Any,Path=Path,json=json,time=time,freeze_model_record=freeze_record)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),namespace)
        return SimpleNamespace(**{name:namespace[name] for name in NAMES}),lambda name,value:namespace.__setitem__(name,value)
    from local_inspection_service.training.auto_optimization_state_store import AutoOptimizationStateStore
    from local_inspection_service.training.auto_optimization_state_ports import AutoOptimizationStateStorage,AutoOptimizationStatePolicy,AutoOptimizationStateCache
    def ports(kind):return kind(**{field.name:test_capability(bindings, field.name) for field in fields(kind)})
    service=AutoOptimizationStateStore(ports(AutoOptimizationStateStorage),ports(AutoOptimizationStatePolicy),ports(AutoOptimizationStateCache))
    bindings['auto_optimize_task_path']=service.auto_optimize_task_path
    return service,lambda name,value:bindings.__setitem__(name,value)


class LocalFiles:
    def exists(self,path):return path.exists()
    def read_text(self,path,*,encoding):return path.read_text(encoding=encoding)
    def write_text(self,path,value,*,encoding):return path.write_text(value,encoding=encoding)
    def glob(self,path,pattern):return path.glob(pattern)


class StateStoreContract(unittest.TestCase):
    def fixture(self,*,postgres=True):
        tmp=tempfile.TemporaryDirectory(prefix='auto-state-contract-');self.addCleanup(tmp.cleanup)
        directory=Path(tmp.name)/'state';events=[];records={};cached={};request_cache=ContextVar('request-state',default=None)
        def fetch(table,key):events.append(('fetch',table,key));return records.get(key['task_id'])
        def fetch_all(table):events.append(('fetch.all',table));return list(records.values())
        def upsert(table,row):events.append(('upsert',table,row));records[row['task_id']]=row
        repo=SimpleNamespace(fetch_by_primary_key=fetch,fetch_all=fetch_all,upsert_row=upsert)
        def repository():events.append('repository');return repo if postgres else None
        def defaults():events.append('defaults');return {'enabled':False,'default':1}
        def decode(rows):events.append('decode');return [row['raw_json'] for row in rows]
        def encode(state,*,fallback_id):events.append('encode');return {'task_id':fallback_id,'raw_json':state}
        def invalidate(key):events.append(('invalidate',key));cached.pop(key,None)
        def get(key):events.append(('cache.get',key));return (key in cached,cached.get(key))
        def put(key,value):events.append(('cache.put',key));cached[key]=value
        snapshot={'training_vision':{'id':'synthetic','version':7}}
        def resolver():events.append('resolver');return SimpleNamespace(current_snapshot=lambda:snapshot)
        bindings={'AUTO_OPTIMIZE_DIR':directory,'AI_DETECTION_MODEL_ID':'default-task','_business_files':LocalFiles(),
            'runtime_postgres_repository_or_none':repository,'_read_path_cache':request_cache,
            'sanitize_ai_detection_task_id':lambda value:str(value or '').strip(),
            'safe_record_id':lambda value:value.replace('/','_'),
            'row_raw_json_list':decode,'auto_optimize_state_row':encode,'default_auto_optimize_settings':defaults,
            'resolve_model_profiles':resolver,'store_read_cache_get':get,'store_read_cache_put':put,'store_read_cache_invalidate':invalidate}
        service,replace=create(bindings)
        return SimpleNamespace(service=service,replace=replace,bindings=bindings,directory=directory,records=records,events=events,
            repository=repo,cached=cached,request_cache=request_cache,snapshot=snapshot)

    def test_path_sanitization_and_fallback(self):
        f=self.fixture();self.assertEqual(f.service.auto_optimize_task_path(' a/b '),f.directory/'a_b.json')
        self.assertEqual(f.service.auto_optimize_task_path(''),f.directory/'default-task.json')
        self.assertEqual(f.events,[]);self.assertFalse(f.directory.exists())

    def test_load_defaults_and_request_cache_same_object(self):
        f=self.fixture();state={'task_id':'stored','settings':{'enabled':True},'samples':['keep'],'created_at':1}
        f.records['a']={'raw_json':state};token=f.request_cache.set({});self.addCleanup(f.request_cache.reset,token)
        with patch.object(time,'time',side_effect=[100,101]) as clock:
            first=f.service.load_auto_optimize_state('a');self.assertEqual(clock.call_count,2)
        self.assertIs(first,state);self.assertEqual(first['created_at'],1);self.assertEqual(first['updated_at'],101)
        self.assertEqual(first['settings'],{'default':1,'enabled':True});self.assertEqual(first['task_id'],'stored')
        self.assertIs(first['samples'],state['samples']);before=list(f.events)
        self.assertIs(f.service.load_auto_optimize_state('a'),first);self.assertEqual(f.events,before)
        self.assertFalse(f.directory.exists())

    def test_load_json_missing_bad_shape_and_error_boundary(self):
        f=self.fixture(postgres=False);f.directory.mkdir()
        for text in (None,'{bad','[]','null'):
            path=f.directory/'a.json'
            if text is None:
                if path.exists():path.unlink()
            else:path.write_text(text,encoding='utf-8')
            result=f.service.load_auto_optimize_state('a');self.assertEqual(result['task_id'],'a');self.assertEqual(result['samples'],[])
        f.replace('_business_files',SimpleNamespace(exists=lambda p:True,read_text=lambda *a,**k:(_ for _ in ()).throw(ValueError('unexpected'))))
        with self.assertRaisesRegex(ValueError,'unexpected'):f.service.load_auto_optimize_state('a')

    def test_save_pg_order_same_object_and_existing_snapshot(self):
        f=self.fixture();state={'task_id':' a ','model_profiles':{'old':True}}
        with patch.object(time,'time',return_value=123):result=f.service.save_auto_optimize_state(state)
        self.assertIs(result,state);self.assertTrue(f.directory.is_dir());self.assertEqual(state['updated_at'],123)
        self.assertEqual(state['task_id'],'a');self.assertEqual(state['model_profiles'],{'old':True})
        self.assertEqual(f.events[:3],[('invalidate','auto_optimize_states'),'repository','encode'])
        self.assertEqual(f.events[3][0],'upsert');self.assertNotIn('resolver',f.events)
        self.assertIs(f.records['a']['raw_json'],state)

    def test_save_new_snapshot_deepcopy_and_missing_resolver_before_effects(self):
        f=self.fixture();state={}
        f.service.save_auto_optimize_state(state);self.assertEqual(state['model_profiles'],f.snapshot)
        self.assertIsNot(state['model_profiles'],f.snapshot);self.assertIsNot(state['model_profiles']['training_vision'],f.snapshot['training_vision'])
        self.assertEqual(f.events[0],'resolver')
        f=self.fixture();f.replace('resolve_model_profiles',lambda:None);state={}
        with self.assertRaisesRegex(RuntimeError,'resolver is not configured'):f.service.save_auto_optimize_state(state)
        self.assertEqual(state,{});self.assertFalse(f.directory.exists());self.assertEqual(f.events,[])

    def test_save_json_replaces_temp_and_returns_same_state(self):
        f=self.fixture(postgres=False);state={'task_id':'a','text':'测试'}
        result=f.service.save_auto_optimize_state(state);self.assertIs(result,state)
        self.assertEqual(json.loads((f.directory/'a.json').read_text(encoding='utf-8')),state)
        self.assertFalse((f.directory/'a.json.tmp').exists())
        self.assertEqual(list(f.directory.iterdir()),[f.directory/'a.json'])

    def test_encode_rejection_and_upsert_failure_keep_prior_mutations(self):
        for reject in (True,False):
            f=self.fixture();sentinel=RuntimeError('upsert failure');state={'task_id':'a'}
            if reject:f.replace('auto_optimize_state_row',lambda *args,**kwargs:None)
            else:f.repository.upsert_row=lambda *args:(_ for _ in ()).throw(sentinel)
            if reject:self.assertIs(f.service.save_auto_optimize_state(state),state)
            else:
                with self.assertRaises(RuntimeError) as raised:f.service.save_auto_optimize_state(state)
                self.assertIs(raised.exception,sentinel)
            self.assertIn('model_profiles',state);self.assertIn('updated_at',state);self.assertTrue(f.directory.exists())
            self.assertIn(('invalidate','auto_optimize_states'),f.events);self.assertEqual(f.records,{})

    def test_list_cache_copies_container_and_preserves_nested_state(self):
        f=self.fixture();raw={};f.records.update(a={'task_id':'a','raw_json':raw},bad={'task_id':'b','raw_json':[]})
        first=f.service.list_auto_optimize_states();self.assertEqual(first,[{'task_id':'a'}]);self.assertIs(first[0],raw)
        before=list(f.events);second=f.service.list_auto_optimize_states();self.assertIsNot(second,first);self.assertIs(second[0],first[0])
        self.assertEqual(f.events[len(before):],[('cache.get','auto_optimize_states')]);first.clear()
        self.assertEqual(f.service.list_auto_optimize_states(),[{'task_id':'a'}])
        self.assertNotIn('defaults',f.events)

    def test_list_json_skips_bad_data_and_fills_only_missing_ids(self):
        f=self.fixture(postgres=False);f.directory.mkdir()
        for name,text in [('a','{}'),('b','{"task_id":"custom"}'),('c','{bad'),('d','[]')]:
            (f.directory/(name+'.json')).write_text(text,encoding='utf-8')
        result=f.service.list_auto_optimize_states();self.assertEqual(sorted(item['task_id'] for item in result),['a','custom'])
        self.assertNotIn('defaults',f.events)

    def test_request_caches_and_repositories_are_resolved_per_call(self):
        a=self.fixture();b=self.fixture();a.request_cache.set({});b.request_cache.set({})
        one=a.service.load_auto_optimize_state('same');two=b.service.load_auto_optimize_state('same')
        self.assertIsNot(one,two);self.assertIs(a.service.load_auto_optimize_state('same'),one)
        replacement=SimpleNamespace(fetch_by_primary_key=lambda *args:{'raw_json':{'from':'second repository'}})
        a.replace('runtime_postgres_repository_or_none',lambda:replacement);a.request_cache.set({})
        self.assertEqual(a.service.load_auto_optimize_state('same')['from'],'second repository')
        self.assertIs(b.service.load_auto_optimize_state('same'),two)

    def test_existing_empty_or_none_snapshot_is_not_rebound(self):
        for snapshot in ({},None):
            f=self.fixture();f.replace('resolve_model_profiles',lambda:(_ for _ in ()).throw(AssertionError('rebound')))
            state={'task_id':'a','model_profiles':snapshot};f.service.save_auto_optimize_state(state)
            self.assertIs(state['model_profiles'],snapshot)

    def test_failed_json_write_retains_existing_target_and_prior_state_effects(self):
        f=self.fixture(postgres=False);f.directory.mkdir();path=f.directory/'a.json';path.write_text('{"old":true}',encoding='utf-8')
        sentinel=OSError('write failure')
        class FailedFiles(LocalFiles):
            def write_text(self,path,value,*,encoding):raise sentinel
        f.replace('_business_files',FailedFiles());state={'task_id':'a'}
        with self.assertRaises(OSError) as raised:f.service.save_auto_optimize_state(state)
        self.assertIs(raised.exception,sentinel);self.assertEqual(json.loads(path.read_text()),{'old':True})
        self.assertIn('model_profiles',state);self.assertIn('updated_at',state)
        self.assertIn(('invalidate','auto_optimize_states'),f.events)

    @unittest.skipIf(BASELINE,'candidate-only actual composition')
    def test_actual_root_getters_wrappers_and_request_scope_cache(self):
        from contextlib import ExitStack
        from unittest.mock import Mock
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service=server._auto_optimization_state_store
        for port in (service.storage,service.policy,service.cache):
            for field in fields(port):assert_capability_owner(self, port, field.name, server)
        f=self.fixture(postgres=False)
        with ExitStack() as stack:
            from dataclasses import replace
            stack.enter_context(auto_port(service,'storage',replace(f.service.storage,
                auto_optimize_task_path=lambda:service.auto_optimize_task_path)))
            stack.enter_context(auto_port(service,'policy',f.service.policy))
            stack.enter_context(auto_port(service,'cache',replace(f.service.cache,
                _read_path_cache=lambda:server._read_path_cache)))
            state={'task_id':'a','value':1};self.assertIs(server.save_auto_optimize_state(state),state)
            with server.read_path_cache_scope():
                first=server.load_auto_optimize_state('a')
                changed=dict(state,value=2);(f.directory/'a.json').write_text(json.dumps(changed),encoding='utf-8')
                with server.read_path_cache_scope():self.assertIs(server.load_auto_optimize_state('a'),first)
                self.assertEqual(first['value'],1)
            self.assertEqual(server.load_auto_optimize_state('a')['value'],2)
            self.assertEqual(server.list_auto_optimize_states()[0]['value'],2)
        self.assertIsNone(server._read_path_cache.get())
        for name,args in [('auto_optimize_task_path',('a',)),('load_auto_optimize_state',('a',)),('save_auto_optimize_state',({},)),('list_auto_optimize_states',())]:
            result=object();operation=Mock(return_value=result)
            with auto_method(self,server._auto_optimization_state_store,name,operation):
                self.assertIs(getattr(server,name)(*args),result);operation.assert_called_once_with(*args)

    @unittest.skipUnless(PG_CHECK,'use --postgres with isolated test DSN')
    def test_real_postgres_upsert_read_list_and_snapshot_retention(self):
        import psycopg
        from psycopg import sql
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        from local_inspection_service.storage.runtime_records import auto_optimize_state_row,row_raw_json_list
        schema='auto_state_'+uuid.uuid4().hex;dsn=os.environ['VANTALINE_POSTGRES_DSN']
        with psycopg.connect(dsn,autocommit=True) as control:
            control.execute(postgres_ddl(schema))
            try:
                with psycopg.connect(dsn) as connection:
                    f=self.fixture();repository=PostgresRuntimeRepository(connection,'synthetic-test',schema)
                    f.replace('runtime_postgres_repository_or_none',lambda:repository)
                    f.replace('auto_optimize_state_row',auto_optimize_state_row);f.replace('row_raw_json_list',row_raw_json_list)
                    value={'task_id':'alpha','owner_user_id':'alpha','value':1};f.service.save_auto_optimize_state(value)
                    frozen=copy.deepcopy(value['model_profiles']);f.snapshot['training_vision']['version']=99
                    f.service.save_auto_optimize_state({'task_id':'beta','owner_user_id':'beta','value':2})
                    loaded=f.service.load_auto_optimize_state('alpha');self.assertEqual(loaded['model_profiles'],frozen)
                    loaded['value']=3;f.service.save_auto_optimize_state(loaded)
                    listed={item['task_id']:item for item in f.service.list_auto_optimize_states()}
                    self.assertEqual(listed['alpha']['value'],3);self.assertEqual(listed['alpha']['model_profiles'],frozen)
                    self.assertEqual(listed['beta']['model_profiles']['training_vision']['version'],99)
                    self.assertEqual(repository.count_rows(['auto_optimize_states'])['auto_optimize_states'],2)
                    self.assertEqual(list(f.directory.iterdir()),[])
                    # A new connection sees the committed save and no cached connection is stored in the service.
                    with psycopg.connect(dsn) as second:
                        f.replace('runtime_postgres_repository_or_none',lambda:PostgresRuntimeRepository(second,'synthetic-test',schema))
                        self.assertEqual(f.service.load_auto_optimize_state('alpha')['value'],3)
            finally:control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

    @unittest.skipIf(BASELINE,'candidate-only import')
    def test_lightweight_import(self):
        code="import sys; import local_inspection_service.training.auto_optimization_state_store; assert not any(x in sys.modules for x in ('local_inspection_service.server','fastapi','psycopg'))"
        subprocess.run([sys.executable,'-c',code],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()
