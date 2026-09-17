"""Legacy JSON/SQL persistence contracts with optional isolated PostgreSQL."""
import copy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime import json_records
from local_inspection_service.text_inspection.incoming_store import IncomingTextStore, IncomingPaths, IncomingRows
from local_inspection_service.storage.runtime_records import incoming_text_reference_row, incoming_text_inspection_row, audit_event_row, row_raw_json_list
ROOT_CHECK='--root' in sys.argv;PG_CHECK='--postgres' in sys.argv
for flag in ['--root','--postgres']:
    if flag in sys.argv:sys.argv.remove(flag)


def reference(identifier='ref',**kwargs):return dict(id=identifier,owner_user_id='alice',task_id='task',version_label='v1',**kwargs)
def inspection(identifier='inspection',**kwargs):return dict(id=identifier,owner_user_id='alice',task_id='task',capture_id='capture',**kwargs)


class Fixture:
    def __init__(self,directory):
        self.directory=Path(directory);self.paths={kind:self.directory/(kind+'.json') for kind in ('references','inspections','audit')}
        self.data={path:[] for path in self.paths.values()};self.events=[];self.repo=None;self.choices=[];self.write_error=None;self.lock=threading.RLock()
        self.store=IncomingTextStore(self.repository,self.guard,IncomingPaths(*(lambda kind=kind:self.paths[kind] for kind in ('references','inspections','audit'))),
            IncomingRows(self.serialize_reference,self.serialize_inspection,self.serialize_audit,row_raw_json_list),self.read,self.write)
    def repository(self):
        self.events.append(('repository',));value=self.choices.pop(0) if self.choices else self.repo
        if isinstance(value,Exception):raise value
        return value
    @contextmanager
    def guard(self):
        with self.lock:
            self.events.append(('enter',))
            try:yield
            finally:self.events.append(('exit',))
    def serialize_reference(self,row):self.events.append(('row','reference'));return incoming_text_reference_row(row)
    def serialize_inspection(self,row):self.events.append(('row','inspection'));return incoming_text_inspection_row(row)
    def serialize_audit(self,row):self.events.append(('row','audit'));return audit_event_row(row)
    def read(self,path):self.events.append(('read',path));return list(self.data[path])
    def write(self,path,values):
        self.events.append(('write',path))
        if self.write_error:raise self.write_error
        self.data[path]=values


class IncomingStoreContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='incoming-store-');self.addCleanup(self.temp.cleanup);self.f=Fixture(self.temp.name)
    def test_json_reference_and_inspection_have_distinct_business_keys(self):
        f=self.f;s=f.store;original=reference(nested=[])
        self.assertTrue(s.save_incoming_text_reference(original,insert_only=True))
        stored=f.data[f.paths['references']][0];self.assertIsNot(stored,original);self.assertIs(stored['nested'],original['nested'])
        self.assertFalse(s.save_incoming_text_reference(reference('other')))
        self.assertFalse(s.save_incoming_text_reference(reference('other'),insert_only=True))
        other=reference('other');other['version_label']='v2';self.assertTrue(s.save_incoming_text_reference(other))
        changed=reference();changed['version_label']='v2';self.assertTrue(s.save_incoming_text_reference(changed))
        self.assertEqual([row['version_label'] for row in f.data[f.paths['references']]],['v2','v2'])
        self.assertFalse(s.save_incoming_text_reference(changed,insert_only=True))
        self.assertTrue(s.save_incoming_text_inspection(inspection(),insert_only=True))
        self.assertFalse(s.save_incoming_text_inspection(inspection('other'),insert_only=True))
        self.assertTrue(s.save_incoming_text_inspection(inspection('other')))
        self.assertEqual(len(f.data[f.paths['inspections']]),2)
        # The real row serializer cleans whitespace, but JSON still persists the input.
        raw={'id':' spaced ','owner_user_id':None,'task_id':7,'version_label':None}
        self.assertTrue(s.save_incoming_text_reference(raw));self.assertEqual(f.data[f.paths['references']][0],raw)
        duplicate={**raw,'id':'another','task_id':'7'};self.assertFalse(s.save_incoming_text_reference(duplicate))
        missing={'id':'missing','owner_user_id':None,'task_id':7};self.assertFalse(s.save_incoming_text_reference(missing))
        self.assertEqual(s.load_incoming_text_reference(' spaced '),raw)
    def test_lazy_factory_selection_single_lookup_and_no_json_fallback(self):
        f=self.f;s=f.store;f.data[f.paths['references']]=[{'id':7,'value':'numeric'}]
        self.assertEqual(s.load_incoming_text_reference('7'),{'id':7,'value':'numeric'})
        self.assertEqual(sum(e[0]=='repository' for e in f.events),2)
        self.assertIsNone(s.load_incoming_text_reference(7))
        repo=Mock();repo.fetch_all.return_value=[{'raw_json':reference()}];f.events=[];f.choices=[None,repo]
        self.assertEqual(s.load_incoming_text_reference('ref'),reference());repo.fetch_all.assert_called_once_with('incoming_text_reference_versions')
        self.assertFalse(any(e[0]=='read' for e in f.events))
        repo.reset_mock();repo.fetch_by_primary_key.return_value={'raw_json':inspection()};f.repo=repo;f.events=[]
        self.assertEqual(s.load_incoming_text_inspection('inspection'),inspection())
        repo.fetch_by_primary_key.assert_called_once_with('incoming_text_inspections',{'id':'inspection'});repo.fetch_all.assert_not_called()
        self.assertEqual(sum(e[0]=='repository' for e in f.events),1)
        repo.fetch_by_primary_key.side_effect=RuntimeError('database')
        with self.assertRaisesRegex(RuntimeError,'database'):s.load_incoming_text_inspection('inspection')
        self.assertFalse(any(e[0]=='read' for e in f.events))
        for fn in [s.save_incoming_text_reference,s.save_incoming_text_inspection]:
            f.events=[]
            with self.assertRaisesRegex(RuntimeError,'invalid incoming text'):fn({})
            self.assertEqual(len(f.events),1);self.assertEqual(f.events[0][0],'row')
        f.repo=RuntimeError('factory');f.events=[]
        with self.assertRaisesRegex(RuntimeError,'factory'):s.save_incoming_text_reference(reference())
        self.assertEqual(f.events,[('row','reference'),('repository',)])
    def test_postgres_save_dispatch_and_audit_selection_order(self):
        f=self.f;s=f.store;repo=Mock();f.repo=repo;repo.insert_row_once.return_value=False
        for fn,value,table in [(s.save_incoming_text_reference,reference(),'incoming_text_reference_versions'),(s.save_incoming_text_inspection,inspection(),'incoming_text_inspections')]:
            f.events=[];self.assertFalse(fn(value,insert_only=True));self.assertEqual([e[0] for e in f.events],['row','repository'])
            self.assertEqual(repo.insert_row_once.call_args.args[0],table)
            self.assertTrue(fn(value));self.assertEqual(repo.upsert_row.call_args.args[0],table)
        f.events=[];repo.reset_mock();self.assertIsNone(s.append_incoming_text_audit({}))
        self.assertEqual(f.events,[('repository',),('row','audit')]);repo.insert_row_once.assert_not_called()
        self.assertIsNone(s.append_incoming_text_audit({'id':'audit','payload':{'safe':'fixture'}}));repo.insert_row_once.assert_called_once()
        self.assertEqual(repo.insert_row_once.call_args.args[0],'audit_events')
        f.repo=None;f.events=[];s.append_incoming_text_audit({'payload':{'first':True}});s.append_incoming_text_audit({'id':None,'payload':{'second':True}})
        self.assertFalse(any(e[0]=='row' for e in f.events));self.assertEqual(len(f.data[f.paths['audit']]),1)
        self.assertEqual(f.data[f.paths['audit']][0],{'payload':{'first':True}})
    def test_file_adapter_read_errors_unicode_and_replace_failure_residue(self):
        path=Path(self.temp.name)/'nested'/'records.json';self.assertEqual(json_records.read_json_list(path),[])
        json_records.write_json_list(path,[{'text':'中文'},3,{'second':True}]);self.assertEqual(json_records.read_json_list(path),[{'text':'中文'},{'second':True}])
        self.assertIn('中文',path.read_text(encoding='utf-8'));self.assertIn('\n  {',path.read_text(encoding='utf-8'))
        for value in ['{invalid','{}','null','123']:
            path.write_text(value,encoding='utf-8');self.assertEqual(json_records.read_json_list(path),[])
        path.write_bytes(b'\xff')
        with self.assertRaises(UnicodeDecodeError):json_records.read_json_list(path)
        with patch.object(Path,'read_text',side_effect=PermissionError('read')):self.assertEqual(json_records.read_json_list(path),[])
        with patch.object(Path,'exists',side_effect=OSError('exists')):
            with self.assertRaisesRegex(OSError,'exists'):json_records.read_json_list(path)
        path.write_text('old',encoding='utf-8')
        with patch.object(json_records.os,'replace',side_effect=PermissionError('replace')) as replace:
            with self.assertRaisesRegex(PermissionError,'replace'):json_records.write_json_list(path,[{'new':'中文'}])
            replace.assert_called_once()
        self.assertEqual(path.read_text(encoding='utf-8'),'old');leftovers=list(path.parent.glob('records.json.*.tmp'));self.assertEqual(len(leftovers),1)
        self.assertEqual(len(leftovers[0].name.split('.')[2]),32);self.assertEqual(json.loads(leftovers[0].read_text(encoding='utf-8')),[{'new':'中文'}])
        fresh=Path(self.temp.name)/'new-dir'/'bad.json'
        with self.assertRaises(TypeError):json_records.write_json_list(fresh,[{'bad':object()}])
        self.assertTrue(fresh.parent.exists());self.assertEqual(list(fresh.parent.iterdir()),[])
    def test_shared_lock_released_on_error_and_paths_remain_dynamic(self):
        f=self.f;f.write_error=OSError('write')
        with self.assertRaisesRegex(OSError,'write'):f.store.save_incoming_text_reference(reference())
        acquired=[]
        def other_thread():
            locked=f.lock.acquire(blocking=False);acquired.append(locked)
            if locked:f.lock.release()
        thread=threading.Thread(target=other_thread);thread.start();thread.join(timeout=3)
        self.assertFalse(thread.is_alive());self.assertEqual(acquired,[True]);self.assertEqual(f.events[-1],('exit',))
        f.write_error=None;changed=Path(self.temp.name)/'changed.json';f.paths['references']=changed;f.data[changed]=[]
        self.assertTrue(f.store.save_incoming_text_reference(reference()));self.assertEqual(f.data[changed],[reference()])
    @unittest.skipUnless(ROOT_CHECK,'use --root for application composition')
    def test_root_aliases_shared_lock_and_late_factory_serializer_paths(self):
        runtime=Path(self.temp.name)/'runtime';(runtime/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(runtime),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        self.assertIs(server._incoming_text_json_list,json_records.read_json_list);self.assertIs(server._save_incoming_text_json_list,json_records.write_json_list)
        self.assertIs(server._incoming_text_store.guard(),server._text_records.dependencies.guard())
        target=Path(self.temp.name)/'late.json'
        with patch.object(server,'INCOMING_TEXT_REFERENCES_PATH',target),patch.object(server,'incoming_text_reference_row',return_value=None) as serializer,patch.object(server,'runtime_postgres_repository_or_none') as factory:
            self.assertEqual(server._incoming_text_store.paths.references(),target)
            with self.assertRaisesRegex(RuntimeError,'invalid incoming text'):server.save_incoming_text_reference(reference())
            serializer.assert_called_once();factory.assert_not_called()
        with patch.object(server,'runtime_postgres_repository_or_none',side_effect=RuntimeError('late')):
            with self.assertRaisesRegex(RuntimeError,'late'):server.load_incoming_text_inspection('inspection')
    @unittest.skipUnless(PG_CHECK,'use --postgres with an isolated test DSN')
    def test_real_postgres_unique_keys_readback_and_audit_insert(self):
        import psycopg
        from psycopg import sql
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
        dsn=os.environ['VANTALINE_POSTGRES_DSN'];schema='incoming_store_test_'+uuid.uuid4().hex
        with psycopg.connect(dsn,autocommit=True) as control:
            control.execute(postgres_ddl(schema))
            try:
                with psycopg.connect(dsn) as connection:
                    self.f.repo=PostgresRuntimeRepository(connection,'test',schema);s=self.f.store
                    self.assertTrue(s.save_incoming_text_reference(reference(),insert_only=True))
                    self.assertFalse(s.save_incoming_text_reference(reference('other'),insert_only=True))
                    self.assertEqual(s.load_incoming_text_reference('ref'),reference())
                    self.assertTrue(s.save_incoming_text_inspection(inspection(),insert_only=True))
                    self.assertFalse(s.save_incoming_text_inspection(inspection('other'),insert_only=True))
                    self.assertEqual(s.load_incoming_text_inspection('inspection'),inspection())
                    s.append_incoming_text_audit({'id':'audit','event_type':'fixture','payload':{'safe':True}})
                    s.append_incoming_text_audit({'id':'audit','event_type':'changed'})
                    row=self.f.repo.fetch_by_primary_key('audit_events',{'id':'audit'});self.assertEqual(row['event_type'],'fixture')
                    self.assertFalse(any(e[0] in {'read','write','enter'} for e in self.f.events))
            finally:control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__=='__main__':unittest.main(verbosity=2)
