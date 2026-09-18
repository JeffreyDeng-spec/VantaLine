"""Text record storage contracts; optional PostgreSQL uses a disposable schema."""
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
from unittest.mock import Mock
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.text_inspection.record_store import TEXT_INSPECTION_TABLES, TextRecordDependencies, TextRecordStore, record_row
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.runtime_records import row_raw_json_list

POSTGRES='--postgres' in sys.argv
ROOT='--root' in sys.argv
sys.argv=[a for a in sys.argv if a not in {'--postgres','--root'}]


class Fixture:
    def __init__(self):
        self.repository=None; self.events=[]; self.values={}; self.lock=threading.RLock(); self.depth=0
        self.store=TextRecordStore(TextRecordDependencies(self.repo,self.guard,lambda:Path('/fixture'),
            lambda:TEXT_INSPECTION_TABLES,lambda:self.read,lambda:self.write,lambda:row_raw_json_list))
    def repo(self): self.events.append(('repository',self.depth)); return self.repository
    @contextmanager
    def guard(self):
        with self.lock:
            self.depth+=1; self.events.append(('enter',self.depth))
            try: yield
            finally: self.events.append(('exit',self.depth)); self.depth-=1
    def read(self,path): self.events.append(('read',path,self.depth)); return copy.deepcopy(self.values.get(path,[]))
    def write(self,path,values): self.events.append(('write',path,self.depth)); self.values[path]=copy.deepcopy(values)


def sample(identity='first',owner='alice',comparison='request'):
    return dict(id=identity,owner_user_id=owner,standard_id='standard',comparison_id=comparison,status='attempting',
        auto_decision='REVIEW_REQUIRED',final_decision='',source_sha256='a'*64,created_at=1,updated_at=1,nested={'text':'合成'})


class StoreContracts(unittest.TestCase):
    def test_all_table_encodings_default_fields_and_no_payload_loss(self):
        self.assertEqual(len(TEXT_INSPECTION_TABLES),9)
        for kind in TEXT_INSPECTION_TABLES:
            value=sample(); row=record_row(kind,value)
            self.assertEqual(row['id'],value['id'])
            if kind in {'extractions','ocr_evidence'}: self.assertIs(row['raw_json'],value)
            else:
                self.assertIsInstance(row['raw_json'],str); self.assertEqual(json.loads(row['raw_json']),value)
                self.assertIn('合成',row['raw_json'])
            self.assertNotIn('nested',row.keys()-{'raw_json'})
            with self.assertRaises(TypeError): record_row(kind,{'id':'bad','unserializable':object()})
        self.assertEqual(record_row('assets',{'id':'asset'})['ordinal'],'')
        self.assertIsNone(record_row('assets',{'id':'asset','ordinal':None})['ordinal'])
        with self.assertRaises(KeyError): record_row('missing',{})

    def test_json_business_duplicates_order_and_copy_isolation(self):
        for kind,keys in {'standards':{'material_code':'M','version_label':'1','standard_type':'label'},
            'assets':{'standard_id':'standard','ordinal':1},'revisions':{'standard_id':'standard','revision_number':1},
            'records':{'comparison_id':'request'},'pages':{'session_id':'session','capture_id':'capture'}}.items():
            with self.subTest(kind=kind):
                f=Fixture(); first={**sample(),**keys}
                self.assertTrue(f.store.save(kind,first,insert_only=True))
                self.assertFalse(f.store.save(kind,{**first,'id':'second'},insert_only=True))
                self.assertFalse(f.store.save(kind,first,insert_only=True))
                first['nested']['text']='caller changed'
                self.assertEqual(f.store.load(kind)[0]['nested']['text'],'合成')
        f=Fixture(); first=sample(); second=sample('second',comparison='different')
        f.store.save('records',first); f.store.save('records',second)
        f.store.save('records',{**first,'status':'completed'})
        self.assertEqual([r['id'] for r in f.store.load('records')],['second','first'])
        self.assertEqual(f.store.load('records')[1]['status'],'completed')
        self.assertTrue(f.store.save('ocr_evidence',sample('ocr-other'),insert_only=True))
        self.assertIsNone(f.store.owned('records','first','bob'))
        self.assertTrue(f.store.save('records',sample('same-business-key')))
        self.assertEqual(len(f.store.load('records')),3)
        for kind in {'ocr_evidence','extractions','sessions','feedback'}:
            f=Fixture(); self.assertTrue(f.store.save(kind,{'id':1,'owner_user_id':1},insert_only=True))
            self.assertFalse(f.store.save(kind,{'id':'1','owner_user_id':1},insert_only=True))
            self.assertIsNotNone(f.store.owned(kind,'1','1')); self.assertIsNone(f.store.owned(kind,1,'1'))
            self.assertTrue(f.store.save(kind,{'id':'1','owner_user_id':1})); self.assertEqual(len(f.store.load(kind)),1)
        f=Fixture(); self.assertTrue(f.store.save('records',{'id':'missing'},insert_only=True))
        self.assertFalse(f.store.save('records',{'id':'explicit-none','owner_user_id':None,'comparison_id':None},insert_only=True))

    def test_json_compare_and_set_reentrant_lock_and_failure_release(self):
        f=Fixture(); original=sample(); f.store.save('records',original)
        f.events.clear()
        self.assertFalse(f.store.update_attempt('records',{**original,'owner_user_id':'bob','status':'completed'}))
        self.assertFalse(any(e[0]=='write' for e in f.events))
        f.events.clear(); self.assertTrue(f.store.update_attempt('records',{**original,'status':'review_required'}))
        self.assertIn(('enter',2),f.events); self.assertTrue(all(e[2]>0 for e in f.events if e[0] in {'read','write'}))
        self.assertEqual(len([e for e in f.events if e[0]=='repository']),4)
        self.assertFalse(f.store.update_attempt('records',{**original,'status':'completed'}))
        self.assertTrue(f.store.update_attempt('records',{**original,'status':'completed'},'review_required'))
        f.events.clear()
        with self.assertRaisesRegex(ValueError,'unsupported_attempt_kind'):f.store.update_attempt('assets',original)
        self.assertEqual(f.events,[])
        def fail(*args): raise RuntimeError('write failed')
        f.store.dependencies=replace(f.store.dependencies,json_writer=lambda:fail)
        with self.assertRaisesRegex(RuntimeError,'write failed'): f.store.save('records',original)
        self.assertEqual(f.depth,0)
        f.events.clear()
        with self.assertRaisesRegex(RuntimeError,'write failed'):
            f.store.update_attempt('records',{**original,'status':'review_required'},'completed')
        self.assertIn(('enter',2),f.events); self.assertEqual(f.depth,0)
        acquired=[]
        def other_thread():
            success=f.lock.acquire(False); acquired.append(success)
            if success:f.lock.release()
        thread=threading.Thread(target=other_thread); thread.start(); thread.join(timeout=2)
        self.assertFalse(thread.is_alive()); self.assertEqual(acquired,[True])

    def test_postgres_dispatch_owner_scope_and_no_json_fallback(self):
        f=Fixture(); repository=Mock(spec=PostgresRuntimeRepository); f.repository=repository; value=sample()
        repository.fetch_one_by_columns.return_value={'raw_json':json.dumps(value)}
        self.assertEqual(f.store.owned('records','first','alice'),value)
        repository.fetch_one_by_columns.assert_called_once_with('text_inspection_records',{'id':'first','owner_user_id':'alice'})
        repository.fetch_all.assert_not_called()
        repository.fetch_one_by_columns.return_value=None
        self.assertIsNone(f.store.owned('ocr_evidence','missing','bob'))
        repository.fetch_all.return_value=[{'raw_json':json.dumps(value)}]
        self.assertEqual(f.store.owned('standards','first','alice'),value)
        repository.fetch_all.assert_called_once_with('text_inspection_standards')
        repository.insert_row_once.return_value=0
        self.assertFalse(f.store.save('records',value,insert_only=True)); repository.upsert_row.assert_not_called()
        self.assertTrue(f.store.save('records',value)); repository.upsert_row.assert_called_once_with('text_inspection_records',record_row('records',value))
        repository.update_text_attempt.return_value=False
        self.assertIs(f.store.update_attempt('records',value,'queued'),False)
        repository.update_text_attempt.assert_called_once_with('text_inspection_records',record_row('records',value),'queued')
        repository.upsert_row.side_effect=RuntimeError('database failed')
        with self.assertRaisesRegex(RuntimeError,'database failed'): f.store.save('records',value)
        self.assertTrue(all(e[0]=='repository' for e in f.events)); self.assertEqual(f.values,{})
        f.store.dependencies=replace(f.store.dependencies,runtime_repository=Mock(side_effect=RuntimeError('factory failed')))
        with self.assertRaisesRegex(RuntimeError,'factory failed'): f.store.load('records')
        self.assertEqual(f.values,{})

    @unittest.skipUnless(ROOT,'requires full application runtime')
    def test_application_uses_shared_lock_and_late_repository_factory(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'local_inspection_service/static').mkdir(parents=True)
            os.environ.update(LOCAL_INSPECTION_ROOT=folder,VANTALINE_DATA_STORE='json',VANTALINE_LABEL_INSPECTION_ENABLED='false',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0')
            from local_inspection_service import server
            from unittest.mock import patch
            self.assertIs(server._text_records.dependencies.guard(),server._incoming_text_store_lock)
            self.assertIs(server.TEXT_INSPECTION_TABLES,TEXT_INSPECTION_TABLES)
            self.assertIs(server._text_v2_row,record_row)
            with patch.object(server,'runtime_postgres_repository_or_none',return_value=None) as factory:
                self.assertTrue(server._text_v2_save('records',sample()))
                self.assertEqual(server._text_v2_owned('records','first','alice'),sample())
                self.assertGreaterEqual(factory.call_count,3)
            repository=Mock(spec=PostgresRuntimeRepository); repository.fetch_all.return_value=[]
            with patch.object(server,'runtime_postgres_repository_or_none',return_value=repository), patch.object(server,'TEXT_INSPECTION_TABLES',{**TEXT_INSPECTION_TABLES,'records':'alternate_records'}):
                self.assertEqual(server._text_v2_load('records'),[])
                repository.fetch_all.assert_called_once_with('alternate_records')
            with patch.object(server,'TEXT_INSPECTION_JSON_DIR',root/'other-json'):
                self.assertEqual(server._text_v2_json_path('records'),root/'other-json'/'records.json')
            for mode in ('read','write','missing-reader','missing-writer'):
                events=[]
                reader_a=lambda path:events.append('readA') or []
                reader_b=lambda path:events.append('readB') or []
                writer_a=lambda path,values:events.append('writeA')
                writer_b=lambda path,values:events.append('writeB')
                class Kind(str):
                    def __format__(self,spec):
                        events.append('path')
                        if mode in {'read','missing-reader'}:server._incoming_text_json_list=reader_b
                        elif events.count('path')==2:server._save_incoming_text_json_list=writer_b
                        return str(self)
                with patch.object(server,'runtime_postgres_repository_or_none',return_value=None),patch.object(server,'_incoming_text_json_list',None if mode=='missing-reader' else reader_a),patch.object(server,'_save_incoming_text_json_list',None if mode=='missing-writer' else writer_a):
                    def invoke():
                        if mode in {'read','missing-reader'}:return server._text_v2_load(Kind('records'))
                        return server._text_v2_save(Kind('records'),sample())
                    if mode.startswith('missing'):
                        with self.assertRaises(TypeError):invoke()
                    else:invoke()
                expected={'read':['path','readA'],'write':['path','readA','path','writeA'],
                    'missing-reader':['path'],'missing-writer':['path','readA','path']}[mode]
                self.assertEqual(events,expected,mode)
            for mode in ('load','owned','missing','missing-decoder'):
                events=[]
                rows_a=lambda rows:events.append('rowsA') or rows
                rows_b=lambda rows:events.append('rowsB') or rows
                def fetch(*args):
                    events.append('fetch');server.row_raw_json_list=rows_b
                    return [] if mode in {'load','missing-decoder'} else None if mode=='missing' else {'id':'r'}
                repository=Mock(spec=PostgresRuntimeRepository)
                repository.fetch_all.side_effect=fetch;repository.fetch_one_by_columns.side_effect=fetch
                with patch.object(server,'runtime_postgres_repository_or_none',return_value=repository),patch.object(server,'row_raw_json_list',None if mode=='missing-decoder' else rows_a):
                    if mode=='missing-decoder':
                        with self.assertRaises(TypeError):server._text_v2_load('records')
                    elif mode=='load':server._text_v2_load('records')
                    else:server._text_v2_owned('records','r','alice')
                expected=['fetch','rowsA'] if mode=='load' else ['fetch','rowsB'] if mode=='owned' else ['fetch']
                self.assertEqual(events,expected,mode)

            # Capture after preceding work, but before evaluating call arguments.
            for mode in ('reader','writer','decoder'):
                events=[]
                def callback(name):
                    return lambda *args:events.append(name) or []
                callbacks={name:callback(name) for name in ('A','B','C')}
                attribute={'reader':'_incoming_text_json_list','writer':'_save_incoming_text_json_list',
                           'decoder':'row_raw_json_list'}[mode]
                repository=Mock(spec=PostgresRuntimeRepository)
                def factory():
                    events.append('factory')
                    if mode!='writer' and events.count('factory')==1:
                        setattr(server,attribute,callbacks['B'])
                    return repository if mode=='decoder' else None
                def read(path):
                    events.append('read')
                    if events.count('read')==1:setattr(server,attribute,callbacks['B'])
                    return []
                def fetch(*args):
                    events.append('fetch');setattr(server,attribute,callbacks['C'])
                    return []
                class Kind(str):
                    def __format__(self,spec):
                        events.append('path')
                        if mode=='reader' or events.count('path')%2==0:
                            setattr(server,attribute,callbacks['C'])
                        return str(self)
                repository.fetch_all.side_effect=fetch
                with patch.object(server,'runtime_postgres_repository_or_none',side_effect=factory),patch.object(server,attribute,callbacks['A']):
                    if mode=='writer':
                        with patch.object(server,'_incoming_text_json_list',side_effect=read):
                            for _ in range(2):server._text_v2_save(Kind('records'),sample())
                    else:
                        for _ in range(2):server._text_v2_load(Kind('records'))
                expected={'reader':['factory','path','B','factory','path','C'],
                          'writer':['factory','path','read','path','B','factory','path','read','path','C'],
                          'decoder':['factory','fetch','B','factory','fetch','C']}[mode]
                self.assertEqual(events,expected,mode)

    def test_first_io_failure_is_preserved_without_retry_or_fallback(self):
        modes=('factory','json-read','json-write','json-cas-write','fetch_all',
               'fetch_one_by_columns','insert_row_once','upsert_row','update_text_attempt')
        for mode in modes:
            with self.subTest(mode=mode):
                f=Fixture();value=sample();error=RuntimeError('unknown '+mode+' outcome')
                if mode=='json-cas-write':f.store.save('records',value)
                before=copy.deepcopy(f.values);f.events.clear()
                fallback=[] if mode in {'json-read','fetch_all'} else True if mode in {'insert_row_once','update_text_attempt'} else None
                failure=Mock(side_effect=[error,fallback])
                if mode=='factory':
                    f.store.dependencies=replace(f.store.dependencies,runtime_repository=failure)
                    invoke=lambda:f.store.load('records')
                elif mode=='json-read':
                    f.store.dependencies=replace(f.store.dependencies,json_reader=lambda:failure)
                    invoke=lambda:f.store.load('records')
                elif mode in {'json-write','json-cas-write'}:
                    f.store.dependencies=replace(f.store.dependencies,json_writer=lambda:failure)
                    invoke=(lambda:f.store.save('records',value)) if mode=='json-write' else (lambda:f.store.update_attempt('records',{**value,'status':'completed'}))
                else:
                    repository=Mock(spec=PostgresRuntimeRepository);f.repository=repository
                    setattr(repository,mode,failure)
                    if mode=='fetch_all':invoke=lambda:f.store.load('records')
                    elif mode=='fetch_one_by_columns':invoke=lambda:f.store.owned('records','first','alice')
                    elif mode=='insert_row_once':invoke=lambda:f.store.save('records',value,insert_only=True)
                    elif mode=='upsert_row':invoke=lambda:f.store.save('records',value)
                    else:invoke=lambda:f.store.update_attempt('records',value)
                with self.assertRaises(RuntimeError) as caught:invoke()
                self.assertIs(caught.exception,error);failure.assert_called_once()
                self.assertEqual(f.values,before);self.assertEqual(f.depth,0)
                self.assertFalse(any(e[0]=='write' for e in f.events))
                if mode=='factory':self.assertEqual(f.events,[])
                elif mode in {'json-read','json-write','json-cas-write'}:
                    self.assertEqual(failure.call_args.args[0],Path('/fixture/records.json'))
                    if mode=='json-cas-write':self.assertIn(('enter',2),f.events)
                else:
                    self.assertTrue(all(e[0]=='repository' for e in f.events))
                    self.assertEqual(len(repository.method_calls),1);self.assertEqual(repository.method_calls[0][0],mode)

    def test_lock_covers_copy_and_compare_until_write(self):
        f=Fixture();probes=[]
        def locked():
            acquired=[]
            def contender():
                success=f.lock.acquire(False);acquired.append(success)
                if success:f.lock.release()
            thread=threading.Thread(target=contender);thread.start();thread.join(timeout=2)
            self.assertFalse(thread.is_alive());self.assertEqual(acquired,[False]);probes.append(True)
        class Input(dict):
            def __deepcopy__(self,memo):locked();return copy.deepcopy(dict(self),memo)
        self.assertTrue(f.store.save('records',Input(sample())))
        self.assertEqual(len(probes),1)
        class Previous(dict):
            def get(self,key,default=None):
                if key=='status':locked()
                return super().get(key,default)
        f.values[Path('/fixture/records.json')]=[Previous(sample())]
        self.assertTrue(f.store.update_attempt('records',{**sample(),'status':'completed'}))
        self.assertEqual(len(probes),2);self.assertEqual(f.depth,0)
        self.assertIn(('enter',2),f.events)

    @unittest.skipUnless(POSTGRES,'requires isolated PostgreSQL')
    def test_real_postgres_duplicate_claim_and_late_update(self):
        import psycopg
        from psycopg import sql
        from local_inspection_service.storage.postgres_schema import postgres_ddl
        dsn=os.environ['VANTALINE_POSTGRES_DSN']; schema='text_records_'+uuid.uuid4().hex
        local=threading.local()
        def forbidden(*args):raise AssertionError('PostgreSQL fell back to JSON')
        store=TextRecordStore(TextRecordDependencies(lambda:local.repo,forbidden,lambda:Path('/unused'),lambda:TEXT_INSPECTION_TABLES,forbidden,forbidden,lambda:row_raw_json_list))
        with psycopg.connect(dsn,autocommit=True) as control:
            control.execute(postgres_ddl(schema))
            try:
                def race(fn):
                    barrier=threading.Barrier(2); results=[]; errors=[]
                    def worker(index):
                        try:
                            with psycopg.connect(dsn) as connection:
                                local.repo=PostgresRuntimeRepository(connection,'test',schema)
                                barrier.wait(timeout=10); results.append(fn(index))
                        except BaseException as exc:errors.append(exc)
                    threads=[threading.Thread(target=worker,args=(i,)) for i in range(2)]
                    for thread in threads:thread.start()
                    for thread in threads:thread.join(timeout=20)
                    self.assertFalse(any(t.is_alive() for t in threads)); self.assertEqual(errors,[]); self.assertEqual(sorted(results),[False,True])
                race(lambda i:store.save('records',sample('claim-'+str(i)),insert_only=True))
                with psycopg.connect(dsn) as connection:
                    local.repo=PostgresRuntimeRepository(connection,'test',schema); winner=store.load('records')[0]
                    self.assertEqual(len(store.load('records')),1)
                    self.assertIsNone(store.owned('records',winner['id'],'bob'))
                    self.assertFalse(store.update_attempt('records',{**winner,'owner_user_id':'bob','status':'completed'}))
                    self.assertEqual(store.owned('records',winner['id'],'alice')['status'],'attempting')
                race(lambda i:store.update_attempt('records',{**winner,'status':'review_required' if i else 'completed'}))
                with psycopg.connect(dsn) as connection:
                    local.repo=PostgresRuntimeRepository(connection,'test',schema)
                    self.assertFalse(store.update_attempt('records',{**winner,'status':'completed'}))
                    self.assertEqual(store.owned('records',winner['id'],'alice')['status'] in {'completed','review_required'},True)
            finally:control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__=='__main__':unittest.main(verbosity=2)
