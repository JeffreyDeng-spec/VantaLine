"""Protected config mutation contracts on original and owned persistence methods."""
import ast
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any, Callable
import unittest
from unittest.mock import Mock, patch
import uuid

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import smoke_app_config_store as existing
BASELINE=os.environ.get('VANTALINE_PROTECTED_CONFIG_BASELINE_SOURCE')
NAMES=('save_app_config','mutate_app_config_atomically')


def bind(store,b):
    if not BASELINE:return SimpleNamespace(**{name:getattr(store,name) for name in NAMES})
    nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
    assert len(nodes)==2
    b.update(Any=Any,Callable=Callable,copy=copy,time=time,load_config=store.load_config,save_config=store.save_config)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),b)
    return SimpleNamespace(**{name:b[name] for name in NAMES})


class ProtectedConfigContracts(unittest.TestCase):
    def fixture(self):
        store,b,events=existing.StoreContract.fixture(self)
        return bind(store,b),store,b,events

    def assert_lock_released(self,lock):
        def acquire():
            acquired=lock.acquire(timeout=2)
            if acquired:lock.release()
            return acquired
        with ThreadPoolExecutor(1) as pool:self.assertTrue(pool.submit(acquire).result(timeout=3))

    def test_save_app_config_pg_keeps_namespace_without_accessory_replacement(self):
        api,store,b,events=self.fixture();repo=SimpleNamespace(replace_app_config_preserving_keys=Mock())
        b['runtime_postgres_repository_or_none']=lambda:repo
        payload={'value':1,'accessories':[{'id':'do-not-replace'}]}
        with patch.object(time,'time',return_value=19.9):api.save_app_config(payload)
        repo.replace_app_config_preserving_keys.assert_called_once_with([payload],('plc','lease'))
        self.assertEqual(events,[('rows',{'updated_at':19})]);self.assertFalse(b['CONFIG_PATH'].exists())
        error=RuntimeError('persist failure');repo.replace_app_config_preserving_keys.side_effect=error
        with self.assertRaises(RuntimeError) as raised:api.save_app_config(payload)
        self.assertIs(raised.exception,error);self.assert_lock_released(b['_config_io_lock'])

    def test_json_save_and_protected_mutation_preserve_data_and_reentrant_guard(self):
        api,store,b,_=self.fixture();b['CONFIG_PATH'].write_text(json.dumps({'plc':{'count':1},'outside':{'kept':2}}))
        api.save_app_config({'plc':{'count':99},'outside':{'kept':3}})
        self.assertEqual(json.loads(b['CONFIG_PATH'].read_text())['plc'],{'count':1})
        checks=[]
        def mutate(config):
            self.assertTrue(b['_config_io_lock'].acquire(blocking=False));b['_config_io_lock'].release()
            with ThreadPoolExecutor(1) as pool:checks.append(pool.submit(b['_config_io_lock'].acquire,False).result(timeout=3))
            config['plc']['count']+=1
        result=api.mutate_app_config_atomically(mutate)
        self.assertEqual(checks,[False]);self.assertEqual(result['plc'],{'count':2})
        self.assertEqual(result['outside'],{'kept':3});self.assertFalse(b['_plc_namespace_write_authorized'].get())
        self.assertEqual(json.loads(b['CONFIG_PATH'].read_text()),result);self.assert_lock_released(b['_config_io_lock'])

    def test_unprotected_mutation_rejected_before_save(self):
        for action in (lambda c:c.__setitem__('outside',{'kept':9}),lambda c:c['outside'].__setitem__('kept',9),lambda c:c.__setitem__('new',1)):
            api,store,b,_=self.fixture();original={'plc':{'count':1},'outside':{'kept':2}};b['CONFIG_PATH'].write_text(json.dumps(original))
            with self.assertRaisesRegex(ValueError,'changed unprotected'):api.mutate_app_config_atomically(action)
            self.assertEqual(json.loads(b['CONFIG_PATH'].read_text()),original)
            self.assertFalse(b['_plc_namespace_write_authorized'].get());self.assert_lock_released(b['_config_io_lock'])

    def test_failed_save_resets_prior_authorization_and_releases_lock(self):
        for prior in (False,True):
            api,store,b,_=self.fixture();b['CONFIG_PATH'].write_text('{"plc":{"count":1}}')
            error=OSError('synthetic write');observed=[]
            def fail(*args,**kwargs):observed.append(b['_plc_namespace_write_authorized'].get());raise error
            b['_business_files'].write_text=fail
            token=b['_plc_namespace_write_authorized'].set(prior)
            try:
                with self.assertRaises(OSError) as raised:api.mutate_app_config_atomically(lambda c:c['plc'].__setitem__('count',2))
                self.assertIs(raised.exception,error);self.assertEqual(observed,[True])
                self.assertIs(b['_plc_namespace_write_authorized'].get(),prior)
            finally:b['_plc_namespace_write_authorized'].reset(token)
            self.assertEqual(json.loads(b['CONFIG_PATH'].read_text())['plc']['count'],1)
            self.assert_lock_released(b['_config_io_lock'])

    def test_pg_falsey_authority_validation_and_postcommit_read_failure(self):
        api,store,b,events=self.fixture();committed=[]
        class Repo:
            def __bool__(self):return False
            def mutate_app_config_namespace(self,keys,mutator,*,updated_at):
                self_test.assertEqual(keys,('plc','lease'));self_test.assertEqual(updated_at,41)
                value={'plc':{'count':1}};mutator(value);committed.append(copy.deepcopy(value));return value
        self_test=self;repo=Repo();b['runtime_postgres_repository_or_none']=Mock(return_value=repo)
        error=RuntimeError('after commit');b['ensure_dirs']=Mock(side_effect=error)
        with patch.object(time,'time',return_value=41.9):
            with self.assertRaises(RuntimeError) as raised:api.mutate_app_config_atomically(lambda c:c['plc'].__setitem__('count',2))
            self.assertIs(raised.exception,error);self.assertEqual(committed,[{'plc':{'count':2}}])
            self.assertEqual(b['runtime_postgres_repository_or_none'].call_count,1)
            with self.assertRaisesRegex(ValueError,'unprotected keys'):
                api.mutate_app_config_atomically(lambda c:c.__setitem__('outside',1))
        self.assertEqual(len(committed),1);self.assertFalse(b['CONFIG_PATH'].exists());self.assert_lock_released(b['_config_io_lock'])

    def test_successful_pg_reload_reselects_repository_while_same_guard_is_held(self):
        api,store,b,events=self.fixture();trace=[]
        def guarded(label):
            with ThreadPoolExecutor(1) as pool:
                self.assertFalse(pool.submit(b['_config_io_lock'].acquire,False).result(timeout=3))
            trace.append(label)
        def mutate(keys,callback,*,updated_at):
            guarded('mutate');state={'plc':{'count':1}};callback(state)
            self.assertEqual(state['plc']['count'],2)
            return state
        first=SimpleNamespace(mutate_app_config_namespace=mutate)
        def fetch(table):guarded(table);return []
        second=SimpleNamespace(fetch_all=fetch)
        selected=iter([first,second])
        def select():guarded('select');return next(selected)
        b['runtime_postgres_repository_or_none']=Mock(side_effect=select)
        b['ensure_dirs']=lambda:guarded('ensure')
        b['config_from_rows']=lambda *args:{'committed':True}
        result=api.mutate_app_config_atomically(lambda c:c['plc'].__setitem__('count',2))
        self.assertTrue(result['committed'])
        self.assertEqual(trace,['select','mutate','ensure','select','app_config','accessories'])
        self.assertEqual(b['runtime_postgres_repository_or_none'].call_count,2)
        self.assert_lock_released(b['_config_io_lock'])

    def test_mutator_and_factory_fail_once_before_authorization(self):
        api,store,b,events=self.fixture();error=RuntimeError('mutator failed')
        mutator=Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as raised:api.mutate_app_config_atomically(mutator)
        self.assertIs(raised.exception,error);mutator.assert_called_once();self.assertFalse(b['_plc_namespace_write_authorized'].get())
        b['runtime_postgres_repository_or_none']=Mock(side_effect=error);mutator.reset_mock()
        with self.assertRaises(RuntimeError) as raised:api.mutate_app_config_atomically(mutator)
        self.assertIs(raised.exception,error);mutator.assert_not_called();b['runtime_postgres_repository_or_none'].assert_called_once()
        self.assert_lock_released(b['_config_io_lock'])

    @unittest.skipUnless(os.environ.get('VANTALINE_POSTGRES_DSN'),'isolated PostgreSQL DSN required')
    def test_real_pg_two_independent_guards_serialize_and_failed_write_rolls_back(self):
        import psycopg
        from psycopg import sql
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        from local_inspection_service.storage.runtime_records import app_config_rows,accessory_rows,config_from_rows
        from local_inspection_service.runtime.connections import ThreadRepositoryFactory
        schema='protected_config_'+uuid.uuid4().hex
        dsn=os.environ['VANTALINE_POSTGRES_DSN'];connections=[]
        def connect():
            connection=psycopg.connect(dsn);connections.append(connection)
            return SimpleNamespace(repository=PostgresRuntimeRepository(connection,'fixture',schema),store='postgres')
        factory=ThreadRepositoryFactory(connect,lambda:schema)
        fixtures=[self.fixture(),self.fixture()]
        for api,store,b,events in fixtures:
            b.update(runtime_postgres_repository_or_none=lambda:factory.selection().repository,
                app_config_rows=app_config_rows,accessory_rows=accessory_rows,config_from_rows=config_from_rows)
        self.assertIsNot(fixtures[0][2]['_config_io_lock'],fixtures[1][2]['_config_io_lock'])
        with psycopg.connect(dsn,autocommit=True) as control:
            control.execute(postgres_ddl(schema))
            try:
                with factory.thread_scope():
                    fixtures[0][0].mutate_app_config_atomically(lambda c:c.update(plc={'count':0},lease={'kept':True}))
                barrier=threading.Barrier(2)
                def increment(fixture):
                    with factory.thread_scope():
                        barrier.wait(timeout=5)
                        for _ in range(16):fixture[0].mutate_app_config_atomically(lambda c:c['plc'].__setitem__('count',c['plc']['count']+1))
                with ThreadPoolExecutor(2) as pool:
                    futures=[pool.submit(increment,f) for f in fixtures]
                    for future in futures:future.result(timeout=20)
                with factory.thread_scope():
                    api,store,b,_=fixtures[0];self.assertEqual(store.load_config()['plc']['count'],32)
                    before=store.load_config();error=RuntimeError('after first protected SQL')
                    original=PostgresRuntimeRepository._upsert_sql_params
                    def fail_on_second(repo,table,row):
                        if table=='app_config' and row.get('config_key')=='lease':raise error
                        return original(repo,table,row)
                    with patch.object(PostgresRuntimeRepository,'_upsert_sql_params',fail_on_second):
                        with self.assertRaises(RuntimeError) as raised:api.mutate_app_config_atomically(lambda c:c['plc'].__setitem__('count',1000))
                    self.assertIs(raised.exception,error);self.assertEqual(store.load_config(),before)
                    with self.assertRaisesRegex(ValueError,'unprotected keys'):api.mutate_app_config_atomically(lambda c:c.__setitem__('outside',1))
                    self.assertEqual(store.load_config(),before)
                self.assertTrue(all(c.closed for c in connections));self.assertTrue(all(not f[2]['CONFIG_PATH'].exists() for f in fixtures))
            finally:
                factory.clear();control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

    @unittest.skipIf(BASELINE,'new direct owner exports')
    def test_root_exports_and_source_contract(self):
        tree=ast.parse((ROOT/'local_inspection_service/server.py').read_text())
        for name in NAMES:
            node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
            self.assertEqual(ast.unparse(node.value),'_app_configuration.'+name)
        from local_inspection_service.scripts import smoke_postgres_endpoint_source_contract
        smoke_postgres_endpoint_source_contract.main()


if __name__=='__main__':unittest.main(verbosity=2)
