"""Configuration read recovery and protected writes against original and extracted code."""
import ast
import copy
from contextvars import ContextVar
from dataclasses import fields
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
import uuid

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_APP_CONFIG_STORE_BASELINE_SOURCE')
NAMES=('_read_config_file','load_config','save_config')


def create(b):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
        assert len(nodes)==3
        b.update(Any=Any,copy=copy,json=json,os=os,time=time,uuid=uuid)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),b)
        return SimpleNamespace(**{n:b[n] for n in NAMES})
    from local_inspection_service.config.app_store import AppConfigStore
    from local_inspection_service.config.app_store_ports import AppConfigFiles,AppConfigRows,AppConfigPolicy
    def ports(cls):return cls(**{f.name:lambda name=f.name:b[name] for f in fields(cls)})
    service=AppConfigStore(ports(AppConfigFiles),ports(AppConfigRows),ports(AppConfigPolicy))
    b.update({n:getattr(service,n) for n in NAMES})
    return service


class StoreContract(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory(prefix='vantaline-config-contract-');self.addCleanup(tmp.cleanup)
        root=Path(tmp.name);events=[]
        files=SimpleNamespace(read_text=lambda p,**kw:p.read_text(**kw),write_text=lambda p,s,**kw:p.write_text(s,**kw),unlink=lambda p:p.unlink())
        b=dict(_business_files=files,CONFIG_PATH=root/'config.json',CONFIG_BACKUP_PATH=root/'backup.json',DATA_DIR=root,
            _config_io_lock=threading.RLock(),ensure_dirs=lambda:events.append('ensure'),
            runtime_postgres_repository_or_none=lambda:None,config_from_rows=lambda a,b:{'pg':a,'accessories':b},
            app_config_rows=lambda c,**kw:events.append(('rows',kw)) or [c],accessory_rows=lambda c:c.get('accessories',[]),
            DEFAULT_CONFIG={'nested':{'default':1},'accessories':[]},PLC_PROTECTED_CONFIG_KEYS=('plc','lease'),
            _plc_namespace_write_authorized=ContextVar('plc-write',default=False),public_path_sanitized=lambda c:c)
        return create(b),b,events

    def test_missing_file_and_partial_reads_retry(self):
        s,b,_=self.fixture();self.assertEqual(s._read_config_file(),{})
        b['_business_files'].read_text=Mock(side_effect=['',OSError('transient'),'{bad','{"ok":1}'])
        with patch.object(time,'sleep') as sleep:self.assertEqual(s._read_config_file(),{'ok':1})
        self.assertEqual(sleep.call_count,3)
        b['_business_files'].read_text=Mock(return_value=' ')
        with patch.object(time,'sleep') as sleep:self.assertIsNone(s._read_config_file())
        self.assertEqual(sleep.call_count,6)

    def test_json_backup_merge_and_default_isolation(self):
        s,b,events=self.fixture();b['CONFIG_PATH'].write_text('{bad');b['CONFIG_BACKUP_PATH'].write_text('{"nested":{"saved":2},"accessories":[{"id":"kept"}]}')
        with patch.object(time,'sleep'):result=s.load_config()
        self.assertEqual(result,{'nested':{'default':1,'saved':2},'accessories':[{'id':'kept'}]})
        result['nested']['default']=99;self.assertEqual(b['DEFAULT_CONFIG']['nested']['default'],1)
        self.assertEqual(events,['ensure'])

    def test_missing_primary_does_not_restore_old_backup(self):
        s,b,_=self.fixture();b['CONFIG_BACKUP_PATH'].write_text('{"accessories":[{"id":"old"}]}')
        self.assertEqual(s.load_config()['accessories'],[])
        b['CONFIG_PATH'].write_text('{bad');b['CONFIG_BACKUP_PATH'].write_text('{bad')
        with patch.object(time,'sleep'):self.assertEqual(s.load_config()['accessories'],[])

    def test_falsey_postgres_stays_authoritative(self):
        s,b,events=self.fixture()
        class Repo:
            def __bool__(self):return False
            def fetch_all(self,table):events.append(('fetch',table));return [{'table':table}]
        b['runtime_postgres_repository_or_none']=lambda:Repo()
        b['_business_files'].read_text=Mock(side_effect=AssertionError('No JSON fallback'))
        result=s.load_config();self.assertEqual(result['accessories'],[{'table':'accessories'}])
        self.assertEqual(events,['ensure',('fetch','app_config'),('fetch','accessories')])
        b['config_from_rows']=Mock(side_effect=OSError('db failed'))
        with self.assertRaises(OSError):s.load_config()

    def test_json_protected_fields_and_caller_unchanged(self):
        s,b,_=self.fixture();b['CONFIG_PATH'].write_text('{"plc":{"owner":"real"}}')
        config={'plc':{'owner':'other'},'lease':'forbidden','accessories':[{'id':'a'}]};before=copy.deepcopy(config)
        s.save_config(config)
        saved=json.loads(b['CONFIG_PATH'].read_text());self.assertEqual(saved,{'plc':{'owner':'real'},'accessories':[{'id':'a'}]})
        self.assertEqual(json.loads(b['CONFIG_BACKUP_PATH'].read_text()),saved);self.assertEqual(config,before)
        self.assertEqual(list(b['DATA_DIR'].glob('*.tmp.*')),[])

    def test_authorized_namespace_is_context_local(self):
        s,b,_=self.fixture();b['CONFIG_PATH'].write_text('{"plc":{"owner":"old"}}')
        token=b['_plc_namespace_write_authorized'].set(True)
        try:s.save_config({'plc':{'owner':'new'}})
        finally:b['_plc_namespace_write_authorized'].reset(token)
        s.save_config({'plc':{'owner':'unprivileged'}})
        self.assertEqual(json.loads(b['CONFIG_PATH'].read_text())['plc']['owner'],'new')

    def test_unreadable_primary_drops_untrusted_protected_proposal(self):
        s,b,_=self.fixture();b['_read_config_file']=lambda:None
        s.save_config({'plc':{'owner':'untrusted'},'lease':'untrusted','kept':1})
        self.assertEqual(json.loads(b['CONFIG_PATH'].read_text()),{'kept':1})

    def test_primary_replace_failure_cleans_temporary_and_propagates(self):
        s,b,_=self.fixture();b['CONFIG_PATH'].write_text('{"old":1}')
        failure=OSError('replace failed')
        with patch.object(os,'replace',side_effect=failure):
            with self.assertRaises(OSError) as error:s.save_config({'new':2})
        self.assertIs(error.exception,failure);self.assertEqual(json.loads(b['CONFIG_PATH'].read_text()),{'old':1})
        self.assertEqual(list(b['DATA_DIR'].glob('*.tmp.*')),[]);self.assertFalse(b['CONFIG_BACKUP_PATH'].exists())

    def test_backup_failure_is_best_effort_after_primary(self):
        s,b,_=self.fixture();replace=os.replace
        def fail_backup(src,dst):
            if dst==b['CONFIG_BACKUP_PATH']:raise OSError('backup unavailable')
            replace(src,dst)
        with patch.object(os,'replace',side_effect=fail_backup):s.save_config({'saved':1})
        self.assertEqual(json.loads(b['CONFIG_PATH'].read_text()),{'saved':1})
        self.assertEqual(len(list(b['DATA_DIR'].glob('backup.json.tmp.*'))),1)

    def test_postgres_replace_keeps_keys_and_accessories_together(self):
        s,b,events=self.fixture();repo=SimpleNamespace(replace_app_config_preserving_keys=Mock())
        b['runtime_postgres_repository_or_none']=lambda:repo
        config={'accessories':[{'id':'a'}],'plc':'ignored by repository fence'}
        with patch.object(time,'time',return_value=44.9):s.save_config(config)
        repo.replace_app_config_preserving_keys.assert_called_once_with([config],('plc','lease'),additional_tables={'accessories':[{'id':'a'}]})
        self.assertEqual(events,[('rows',{'updated_at':44})]);self.assertFalse(b['CONFIG_PATH'].exists())
        failure=RuntimeError('write failure');repo.replace_app_config_preserving_keys.side_effect=failure
        with self.assertRaises(RuntimeError) as error:s.save_config(config)
        self.assertIs(error.exception,failure)

    @unittest.skipUnless(os.environ.get('VANTALINE_POSTGRES_DSN'), 'isolated PostgreSQL DSN required')
    def test_real_postgres_protected_commit_and_mid_write_rollback(self):
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        from local_inspection_service.storage.runtime_selector import default_postgres_connector
        from local_inspection_service.storage.runtime_records import app_config_rows, accessory_rows, config_from_rows
        s,b,_=self.fixture();schema='app_config_contract_'+uuid.uuid4().hex[:12]
        connection=default_postgres_connector(os.environ['VANTALINE_POSTGRES_DSN'])
        observer=default_postgres_connector(os.environ['VANTALINE_POSTGRES_DSN'])
        try:
            with connection.cursor() as cursor:cursor.execute(postgres_ddl(schema))
            connection.commit()
            repository=PostgresRuntimeRepository(connection,'<redacted>',schema_name=schema)
            external=PostgresRuntimeRepository(observer,'<redacted>',schema_name=schema)
            repository.upsert_row('app_config',app_config_rows({'plc':{'owner':'old'}},updated_at=1)[0])
            b.update(runtime_postgres_repository_or_none=lambda:repository,app_config_rows=app_config_rows,
                     accessory_rows=accessory_rows,config_from_rows=config_from_rows)
            s.save_config({'plc':{'owner':'untrusted'},'value':{'state':'committed'},'accessories':[{'id':'kept'}]})
            def observed():
                value=config_from_rows(external.fetch_all('app_config'),external.fetch_all('accessories'))
                observer.rollback()
                return value
            before=observed()
            self.assertEqual(before['plc'],{'owner':'old'});self.assertEqual(before['value'],{'state':'committed'})
            self.assertEqual(before['accessories'][0]['id'],'kept')
            original=repository._upsert_sql_params;failure=RuntimeError('after config SQL and accessory DELETE')
            def fail_after_sql(instance,table,row):
                if table=='accessories':raise failure
                return original(table,row)
            with patch.object(PostgresRuntimeRepository,'_upsert_sql_params',new=fail_after_sql):
                with self.assertRaises(RuntimeError) as error:
                    s.save_config({'value':{'state':'must rollback'},'accessories':[{'id':'new'}]})
            self.assertIs(error.exception,failure);self.assertEqual(observed(),before)
            self.assertEqual(s.load_config()['value'],{'state':'committed'});connection.rollback()
            self.assertFalse(b['CONFIG_PATH'].exists())
        finally:
            observer.close();connection.rollback()
            with connection.cursor() as cursor:cursor.execute('DROP SCHEMA IF EXISTS "'+schema+'" CASCADE')
            connection.commit();connection.close()

    @unittest.skipIf(BASELINE,'Original entry has no extracted assembly')
    def test_actual_composition_getters_and_instance_isolation(self):
        from local_inspection_service.config.app_store import AppConfigStore
        from local_inspection_service.config.app_store_ports import AppConfigFiles,AppConfigRows,AppConfigPolicy
        tree=ast.parse((ROOT/'local_inspection_service/server.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_app_config_store' for t in n.targets))
        symbols=dict(AppConfigStore=AppConfigStore,AppConfigFiles=AppConfigFiles,AppConfigRows=AppConfigRows,AppConfigPolicy=AppConfigPolicy)
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<assembly>','exec'),symbols)
        store=symbols['_app_config_store']
        for group in ('files','rows','policy'):
            ports=getattr(store,group)
            for field in fields(ports):
                marker=object();symbols[field.name]=marker;self.assertIs(getattr(ports,field.name)(),marker)
        a,b,_=self.fixture();c,d,_=self.fixture()
        self.assertIsNot(a.policy._plc_namespace_write_authorized(),c.policy._plc_namespace_write_authorized())
        a.save_config({'a':1});c.save_config({'b':1})
        self.assertEqual(a.load_config()['a'],1);self.assertNotIn('a',c.load_config())


if __name__=='__main__':unittest.main(verbosity=2)
