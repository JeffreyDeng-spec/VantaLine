"""Legacy JSON/SQL persistence contracts with optional isolated PostgreSQL."""
import copy
from contextlib import contextmanager
from dataclasses import replace
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
            IncomingRows(self.serialize_reference,self.serialize_inspection,self.serialize_audit,lambda:row_raw_json_list),self.read,self.write,
            load_references=lambda:self.store.load_incoming_text_references(),
            load_inspections=lambda:self.store.load_incoming_text_inspections())
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
    @staticmethod
    def fail_once(callback,error):
        attempts=[]
        def invoke(*args,**kwargs):
            attempts.append((args,kwargs))
            if len(attempts)==1:raise error
            return callback(*args,**kwargs)
        return Mock(side_effect=invoke)

    def lock_available(self,lock):
        acquired=[]
        def probe():
            got=lock.acquire(blocking=False);acquired.append(got)
            if got:lock.release()
        thread=threading.Thread(target=probe);thread.start();thread.join(timeout=3)
        self.assertFalse(thread.is_alive());self.assertEqual(len(acquired),1)
        return acquired[0]

    def test_read_first_errors_are_not_retried_or_redirected(self):
        for kind in ('references','inspections'):
            for mode in ('factory','fetch-all','fetch-one','decode-list','decode-one','json'):
                with self.subTest(kind=kind,mode=mode):
                    f=Fixture(self.temp.name);repo=Mock();f.repo=repo
                    repo.fetch_all.return_value=[{'raw_json':{'id':'wanted'}}]
                    repo.fetch_by_primary_key.return_value={'raw_json':{'id':'wanted'}}
                    error=RuntimeError(mode)
                    if mode=='factory':
                        failed=self.fail_once(f.store.repository,error);f.store.repository=failed
                    elif mode.startswith('fetch'):
                        name='fetch_all' if mode=='fetch-all' else 'fetch_by_primary_key'
                        failed=self.fail_once(getattr(repo,name),error);setattr(repo,name,failed)
                    elif mode.startswith('decode'):
                        failed=self.fail_once(f.store.rows.decode(),error);f.store.rows=replace(f.store.rows,decode=lambda:failed)
                    else:
                        f.repo=None;failed=self.fail_once(f.store.read_json,error);f.store.read_json=failed
                    single=mode in ('fetch-one','decode-one')
                    fn=getattr(f.store,'load_incoming_text_'+(kind[:-1] if single else kind))
                    with self.assertRaises(RuntimeError) as caught:fn('wanted') if single else fn()
                    self.assertIs(caught.exception,error);self.assertEqual(failed.call_count,1)
                    self.assertFalse(any(e[0] in {'write','row'} for e in f.events))
                    self.assertTrue(all(not rows for rows in f.data.values()))
                    if mode!='json':self.assertFalse(any(e[0]=='read' for e in f.events))
                    if mode=='factory':repo.fetch_all.assert_not_called()
                    if mode=='json':self.assertEqual([e[0] for e in f.events],['repository','enter','exit'])
                    self.assertTrue(self.lock_available(f.lock))

    def test_write_first_errors_preserve_data_and_stop_dispatch(self):
        for kind in ('reference','inspection','audit'):
            modes=('row','insert','json') if kind=='audit' else ('row','insert','upsert','json')
            for mode in modes:
                with self.subTest(kind=kind,mode=mode):
                    f=Fixture(self.temp.name);repo=Mock();f.repo=repo
                    value=reference() if kind=='reference' else inspection() if kind=='inspection' else {'id':'audit'}
                    error=RuntimeError(kind+'-'+mode)
                    if mode=='row':
                        failed=self.fail_once(getattr(f.store.rows,kind),error)
                        f.store.rows=replace(f.store.rows,**{kind:failed})
                    elif mode in ('insert','upsert'):
                        name='insert_row_once' if mode=='insert' else 'upsert_row'
                        failed=self.fail_once(getattr(repo,name),error);setattr(repo,name,failed)
                    else:
                        f.repo=None;failed=self.fail_once(f.store.write_json,error);f.store.write_json=failed
                    before=copy.deepcopy(f.data)
                    with self.assertRaises(RuntimeError) as caught:
                        if kind=='audit':f.store.append_incoming_text_audit(value)
                        else:getattr(f.store,'save_incoming_text_'+kind)(value,insert_only=mode=='insert')
                    self.assertIs(caught.exception,error);self.assertEqual(failed.call_count,1)
                    self.assertEqual(f.data,before);self.assertTrue(self.lock_available(f.lock))
                    if mode=='row':
                        repo.insert_row_once.assert_not_called();repo.upsert_row.assert_not_called()
                        if kind!='audit':self.assertFalse(any(e[0]=='repository' for e in f.events))
                    if mode=='json':self.assertEqual(f.events[-1],('exit',))
                    else:self.assertFalse(any(e[0] in {'read','write','enter'} for e in f.events))

    def test_file_read_and_partial_temp_write_first_errors_are_not_retried(self):
        path=Path(self.temp.name)/'first.json';path.write_text('[{"id":"old"}]',encoding='utf-8')
        original_read=Path.read_text;error=PermissionError('first read')
        failed=self.fail_once(original_read,error)
        with patch.object(Path,'read_text',autospec=True,side_effect=failed):
            self.assertEqual(json_records.read_json_list(path),[])
        self.assertEqual(failed.call_count,1)
        original_write=Path.write_text;error=OSError('partial write');attempts=[]
        def write(target,text,*args,**kwargs):
            attempts.append(target)
            if len(attempts)==1:
                original_write(target,'partial',encoding='utf-8');raise error
            return original_write(target,text,*args,**kwargs)
        with patch.object(Path,'write_text',autospec=True,side_effect=write),patch.object(json_records.os,'replace',wraps=json_records.os.replace) as move:
            with self.assertRaises(OSError) as caught:json_records.write_json_list(path,[{'id':'new'}])
            self.assertIs(caught.exception,error);move.assert_not_called()
        self.assertEqual(len(attempts),1);self.assertEqual(path.read_text(encoding='utf-8'),'[{"id":"old"}]')
        leftovers=list(path.parent.glob('first.json.*.tmp'));self.assertEqual(leftovers,attempts)
        self.assertEqual(leftovers[0].read_text(encoding='utf-8'),'partial')

    def test_uniqueness_and_input_copy_stay_inside_one_shared_guard(self):
        for kind in ('reference','inspection'):
            for existing in (False,True):
                with self.subTest(kind=kind,existing=existing):
                    f=Fixture(self.temp.name);armed=[False];stages=[]
                    def locked(stage):
                        if armed[0]:
                            stages.append(stage);self.assertFalse(self.lock_available(f.lock),stage)
                    class Prior(dict):
                        def get(self,*args):locked('comparison');return super().get(*args)
                    class Incoming(dict):
                        def __iter__(self):return super().__iter__()
                        def keys(self):locked('keys');return super().keys()
                        def __getitem__(self,key):locked('item');return super().__getitem__(key)
                    make=reference if kind=='reference' else inspection
                    previous=make('ref' if kind=='reference' else 'inspection') if existing else make('other')
                    if not existing:previous.update(version_label='other',capture_id='other')
                    f.data[f.paths[kind+'s']]=[Prior(previous)]
                    original=f.store.read_json
                    def read(path):
                        value=original(path);armed[0]=True;return value
                    f.store.read_json=read
                    self.assertTrue(getattr(f.store,'save_incoming_text_'+kind)(Incoming(make(nested=[]))))
                    self.assertTrue({'comparison','keys','item'}<=set(stages))
                    self.assertEqual(sum(e[0]=='enter' for e in f.events),1)
                    self.assertEqual(sum(e[0]=='exit' for e in f.events),1)
                    self.assertTrue(self.lock_available(f.lock))

    def test_decoder_capture_window_and_single_lookup_short_circuit(self):
        for kind in ('references','inspections'):
            for mode in ('list','list-none','single','single-none','empty'):
                with self.subTest(kind=kind,mode=mode):
                    f=Fixture(self.temp.name);events=[];callbacks={}
                    def decoder(label):
                        def decode(rows):events.append(label);return [{'id':'wanted','source':label}]
                        return decode
                    callbacks['decode']=decoder('A');repo=Mock()
                    def repository():
                        events.append('repository');callbacks['decode']=None if mode.endswith('none') else decoder('B');return repo
                    def fetch_all(table):
                        events.append('fetch-all');callbacks['decode']=decoder('C');return [{'raw_json':{'id':'wanted'}}]
                    def fetch_one(*args):
                        events.append('fetch-one');callbacks['decode']=decoder('C');return None if mode=='empty' else {'raw_json':{'id':'wanted'}}
                    getter=Mock(side_effect=lambda:callbacks['decode'])
                    f.store.repository=repository;f.store.rows=replace(f.store.rows,decode=getter)
                    repo.fetch_all=fetch_all;repo.fetch_by_primary_key=fetch_one
                    if mode.startswith('list'):
                        fn=getattr(f.store,'load_incoming_text_'+kind)
                        if mode=='list-none':
                            with self.assertRaises(TypeError):fn()
                            self.assertEqual(events,['repository','fetch-all'])
                        else:
                            self.assertEqual(fn(),[{'id':'wanted','source':'B'}]);self.assertEqual(events,['repository','fetch-all','B'])
                        self.assertEqual(getter.call_count,1)
                    else:
                        result=getattr(f.store,'load_incoming_text_'+kind[:-1])('wanted')
                        if mode=='empty':
                            self.assertIsNone(result);self.assertEqual(events,['repository','fetch-one']);getter.assert_not_called()
                        else:
                            self.assertEqual(result,{'id':'wanted','source':'C'});self.assertEqual(events,['repository','fetch-one','C'])
                            self.assertEqual(getter.call_count,1)
                    self.assertFalse(any(e[0] in {'read','write','enter'} for e in f.events))

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
    @unittest.skipUnless(ROOT_CHECK,'use --root for application composition')
    def test_root_single_lookup_observes_replaced_public_list_loader(self):
        runtime=Path(self.temp.name)/'runtime';(runtime/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(runtime),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        original=server.row_raw_json_list
        self.assertIs(server._incoming_text_store.rows.decode(),original)
        replacement=Mock()
        with patch.object(server,'row_raw_json_list',replacement):self.assertIs(server._incoming_text_store.rows.decode(),replacement)
        self.assertIs(server._incoming_text_store.rows.decode(),original)
        for kind in ('references','inspections'):
            for missing in (False,True):
                with self.subTest(kind=kind,missing=missing):
                    name='load_incoming_text_'+kind;initial=Mock(return_value=[])
                    replacement=None if missing else Mock(return_value=[{'id':'wanted'}])
                    def repository():setattr(server,name,replacement);return None
                    with patch.object(server,name,initial),patch.object(server,'runtime_postgres_repository_or_none',side_effect=repository) as factory:
                        fn=getattr(server,'load_incoming_text_'+kind[:-1])
                        if missing:
                            with self.assertRaises(TypeError):fn('wanted')
                        else:
                            self.assertEqual(fn('wanted'),{'id':'wanted'});replacement.assert_called_once_with()
                        factory.assert_called_once_with();initial.assert_not_called()

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
