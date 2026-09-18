"""Native HTTP and failure-order contracts for the standard workflow services."""
import asyncio
import copy
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch, AsyncMock
from types import SimpleNamespace
from dataclasses import replace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.text_inspection import standard_ports as ports, standard_imports as imports, standard_edits as edits, standard_api as api
import httpx
from fastapi import FastAPI, HTTPException
from local_inspection_service.text_inspection.standard_api import register
from local_inspection_service.text_inspection.standard_imports import StandardImports
from local_inspection_service.text_inspection.standard_library import StandardLibrary
from local_inspection_service.text_inspection.standard_edits import StandardEdits
from local_inspection_service.text_inspection.standard_ports import (
    StandardAccess, StandardRecords, StandardWrites, StandardMedia, StandardRevisions,
    StandardParsers, StandardClassification, StandardPreparation,
)
from local_inspection_service.text_inspection.revisions import TextRevisions, RevisionRecords, expected_revision, confirmed_snapshot
from local_inspection_service.document_images import DocImageError, DocImageUnavailable
from local_inspection_service.text_inspection_v2 import UnsafeDocument


class Upload:
    def __init__(self, data=b'fixture', filename='fixture.docx'):
        self.data, self.filename, self.reads = data, filename, []
    async def read(self, size=-1):
        self.reads.append(size)
        return self.data if size < 0 else self.data[:size]


def capture_trial(case, window=False):
 events=[];std={'id':'standard','owner_user_id':'alice','standard_type':'label','status':'draft','revision_number':0};asset={'id':'asset','standard_id':'standard','owner_user_id':'alice','status':'candidate'}
 ns={}
 def text_a(v,limit):events.append('textA');return str(v)
 def text_b(v,limit):events.append('textB');return str(v)
 def public_a(v):events.append('publicA');return dict(v)
 def public_b(v):events.append('publicB');return dict(v)
 def public_c(v):events.append('publicC');return dict(v)
 def owned(kind,identity,owner):return std if kind=='standards' else asset
 ns.update(require_permission=lambda *a,**k:None,_text_v2_owner=lambda:('alice','Alice'),bounded_text=text_a,sha256_bytes=lambda b:'hash',_text_v2_load=lambda kind:[asset] if kind=='assets' else [],
 _text_v2_save=lambda *a,**k:True,_text_v2_owned=owned,_text_v2_public=public_a,
 _text_v2_media_path=lambda *a:Path('/synthetic')/a[-1],_text_v2_write=lambda *a:events.append('writeA'),
 _text_v2_prepare_image=lambda b:(b,'image/png','.png','PNG'),_text_v2_expected_revision=lambda v:events.append('expectedA'),
 _text_v2_confirmed_snapshot=lambda v:[],_text_v2_apply_revision=lambda *a,**k:events.append('applyA'),
 runtime_postgres_repository_or_none=lambda:None,_incoming_text_store_lock=threading.RLock(),
 extract_doc_images=lambda b:(events.append('docA') or [],[]),extract_docx_candidates=lambda b:([],[]),inspect_pdf=lambda b:{},
 DocImageUnavailable=imports.DocImageUnavailable,DocImageError=imports.DocImageError,UnsafeDocument=imports.UnsafeDocument,
 document_import_jobs=SimpleNamespace(start=lambda *a:None,mark_unavailable=lambda *a:events.append('markA'),refresh=lambda *a:None),
 standard_preparation_jobs=SimpleNamespace(start=lambda *a:None))
 class Upload:
  filename='fixture.docx'
  async def read(self,*a):return b'synthetic'
 upload=Upload()
 name,material,version='name','material','version';body={'action':'review','expected_revision':None};prep_enabled=False
 target='import_text_inspection_standard'
 if case=='import_text':
  class Name(str):
   def strip(self):events.append('strip');ns['bounded_text']=text_b;return 'name'
  name=Name('name')
 elif case=='doc_queued':
  upload.filename='fixture.doc'
  if window:
   class Name(str):
    def strip(self):ns['extract_doc_images']=lambda b:(events.append('docB') or [],[]);return 'name'
   name=Name('name')
 elif case=='asset_write':
  class Blobs(list):
   def __getitem__(self,index):events.append('blob-index');ns['_text_v2_write']=lambda *a:events.append('writeC' if window else 'writeB');return super().__getitem__(index)
  ns['extract_docx_candidates']=lambda b:([{'mime_type':'image/png'}],Blobs([b'image']))
  if window:
   def source_write(*a):
    events.append('writeA');ns['_text_v2_write']=lambda *a:events.append('writeB')
   ns['_text_v2_write']=source_write
 elif case=='unavailable':
  class Message:
   def __str__(self):events.append('reason');ns['document_import_jobs'].mark_unavailable=lambda *a:events.append('markC' if window else 'markB');return 'reason'
  def start(*a):
   if window:ns['document_import_jobs'].mark_unavailable=lambda *a:events.append('markB')
   raise HTTPException(503,Message())
  ns['document_import_jobs'].start=start
 elif case=='add_text':
  target='add_text_inspection_standard_asset'
  class NamedUpload(Upload):
   @property
   def filename(self):events.append('filename');ns['bounded_text']=text_b;return 'image.png'
  upload=NamedUpload()
 elif case=='expected':
  target='patch_text_inspection_asset'
  class Body(dict):
   def get(self,key,default=None):
    if key=='expected_revision':events.append('expected-arg');ns['_text_v2_expected_revision']=lambda value:events.append('expectedC' if window else 'expectedB')
    return super().get(key,default)
  body=Body(body)
 elif case=='public_db':
  target='confirm_text_inspection_standard'
  def confirm(*a,**k):events.append('db');ns['_text_v2_public']=public_c if window else public_b;return std
  def repository():
   if window:ns['_text_v2_public']=public_b
   return SimpleNamespace(confirm_text_inspection_standard=confirm)
  ns['runtime_postgres_repository_or_none']=repository
 elif case=='public_owned':
  target='confirm_text_inspection_standard';prep_enabled=True;calls=[]
  def owned2(*a):
   calls.append(1)
   if len(calls)==2:events.append('owned-second');ns['_text_v2_public']=public_c if window else public_b
   return std
  ns['_text_v2_owned']=owned2
  if window:ns['standard_preparation_jobs'].start=lambda *a:ns.update(_text_v2_public=public_b)
 elif case=='apply_confirm':
  target='confirm_text_inspection_standard'
  class Standard(dict):
   def __getitem__(self,key):
    if key=='confirmed_at':events.append('confirmed-time');ns['_text_v2_apply_revision']=lambda *a,**k:events.append('applyC' if window else 'applyB')
    return super().__getitem__(key)
  std=Standard(std)
  if window:
   class Asset(dict):
    def get(self,key,default=None):
     if key=='ordinal':ns['_text_v2_apply_revision']=lambda *a,**k:events.append('applyB')
     return super().get(key,default)
   asset=Asset(asset)
 elif case=='request_json':
  target='patch_text_inspection_asset'
 async def json_a():
  events.append('jsonA')
  if window and case=='expected':ns['_text_v2_expected_revision']=lambda value:events.append('expectedB')
  return body
 async def json_b():events.append('jsonB');return body
 request=SimpleNamespace(json=json_a)
 if case=='request_json':
  ns['require_permission']=lambda *a,**k:setattr(request,'json',json_b)
 async def queued(fn,*args):
  events.append('queued');ns['extract_doc_images']=lambda b:(events.append('docC' if window else 'docB') or [],[])
  return fn(*args)
 access=ports.StandardAccess(lambda *a,**k:ns['require_permission'](*a,**k),lambda:ns['_text_v2_owner']())
 records=ports.StandardRecords(lambda k:ns['_text_v2_load'](k),lambda *a,**k:ns['_text_v2_save'](*a,**k),lambda *a:ns['_text_v2_owned'](*a),lambda:ns['_text_v2_public'])
 media=ports.StandardMedia(lambda *a:ns['_text_v2_media_path'](*a),lambda:ns['_text_v2_write'],lambda b:ns['sha256_bytes'](b))
 imp=imports.StandardImports(access,records,media,ports.StandardParsers(lambda:ns['extract_doc_images'],lambda b:ns['extract_docx_candidates'](b),lambda b:ns['inspect_pdf'](b)),ports.StandardClassification(lambda *a:ns['document_import_jobs'].start(*a),lambda:ns['document_import_jobs'].mark_unavailable),lambda:ns['bounded_text'])
 edit=edits.StandardEdits(access,records,ports.StandardWrites(lambda:ns['runtime_postgres_repository_or_none'](),lambda:ns['_incoming_text_store_lock']),media,
 ports.StandardRevisions(lambda:ns['_text_v2_expected_revision'],lambda a:ns['_text_v2_confirmed_snapshot'](a),lambda:ns['_text_v2_apply_revision']),
 ports.StandardPreparation(lambda *a:ns['standard_preparation_jobs'].start(*a),lambda owner:prep_enabled),lambda b:ns['_text_v2_prepare_image'](b),lambda:ns['bounded_text'])
 fn=getattr(imp if target=='import_text_inspection_standard' else edit,target)
 if case=='request_json':fn=api.register(FastAPI(),imp,None,edit).patch_text_inspection_asset
 with patch.object(asyncio,'to_thread',side_effect=queued):
  if target=='import_text_inspection_standard':asyncio.run(fn(upload,name,material,version))
  elif target=='add_text_inspection_standard_asset':asyncio.run(fn('standard',upload,''))
  elif target=='patch_text_inspection_asset':
   arg=request if case=='request_json' else request.json
   asyncio.run(fn('standard','asset',arg))
  else:fn('standard')
 return events

class Fixture:
    def __init__(self, directory, owner='alice'):
        self.directory=Path(directory);self.events=[];self.owner=ContextVar('standard_owner',default=(owner,owner))
        self.store={'standards':[], 'assets':[], 'revisions':[], 'feedback':[]}
        self.repo=None;self.repo_error=None;self.fail={};self.files=[];self.preparation_enabled=False
        self.parser_result=([dict(ordinal=1,status='candidate',mime_type='image/png')],[b'image'])
        self.parser_error=None;self.start_error=None;self.unavailable_error=None;self.media_calls=0
        self.access=StandardAccess(self.require,lambda:self.owner.get())
        self.records=StandardRecords(self.load,self.save,self.owned,lambda:self.public)
        self.media=StandardMedia(self.path,lambda:self.write,lambda data:hashlib.sha256(data).hexdigest())
        self.revision_service=TextRevisions(RevisionRecords(self.load,self.save),confirmed_snapshot)
        self.imports=StandardImports(self.access,self.records,self.media,
            StandardParsers(lambda:lambda data:self.parse('doc',data),lambda data:self.parse('docx',data),lambda data:self.parse('pdf',data)),
            StandardClassification(self.start,lambda:self.unavailable),lambda:lambda value,limit:value[:limit])
        self.library=StandardLibrary(self.access,self.records,self.refresh,self.asset_bytes)
        self.edits=StandardEdits(self.access,self.records,StandardWrites(self.repository,self.guard),self.media,
            StandardRevisions(lambda:expected_revision,confirmed_snapshot,lambda:self.revision_service.apply),
            StandardPreparation(self.prepare,lambda owner:self.preparation_enabled),
            lambda data:(data,'image/png','.png','PNG'),lambda:lambda value,limit:value[:limit])
        self.app=FastAPI();self.routes=register(self.app,self.imports,self.library,self.edits)
        @self.app.middleware('http')
        async def identity(request,call_next):
            who=request.headers.get('x-owner',owner);token=self.owner.set((who,who))
            try:return await call_next(request)
            finally:self.owner.reset(token)
    def require(self, permission, *, detail):
        self.events.append(('permission',self.owner.get()[0]))
        if self.owner.get()[0]=='denied':raise HTTPException(403,detail)
    def load(self,kind):self.events.append(('load',kind));return copy.deepcopy(self.store[kind])
    def owned(self,kind,identifier,owner):
        self.events.append(('owned',kind,identifier,owner))
        return next((copy.deepcopy(row) for row in self.store[kind] if row['id']==identifier and row['owner_user_id']==owner),None)
    def save(self,kind,value,*,insert_only=False):
        self.events.append(('save',kind,copy.deepcopy(value),insert_only))
        failure=self.fail.get(kind)
        if isinstance(failure,Exception):raise failure
        if failure is False:return False
        self.store[kind]=[copy.deepcopy(value)]+[row for row in self.store[kind] if row['id']!=value['id']]
        return True
    def public(self,value):self.events.append(('public',value['id']));return copy.deepcopy(value)
    def path(self,owner,standard,name):return self.directory / owner / standard / name
    def write(self,path,data):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);self.files.append(path);self.events.append(('write',path))
    def parse(self,kind,data):
        self.events.append(('parse',kind,self.owner.get()[0],threading.get_ident()))
        if self.parser_error:raise self.parser_error
        return self.parser_result
    def start(self,standard,owner):
        self.events.append(('start',standard,owner))
        if self.start_error:raise self.start_error
    def unavailable(self,*args):
        self.events.append(('unavailable',*args))
        if self.unavailable_error:raise self.unavailable_error
    def refresh(self,*args):self.events.append(('refresh',*args))
    def prepare(self,*args):self.events.append(('prepare',*args))
    def asset_bytes(self,asset,owner):
        self.media_calls+=1;self.events.append(('media',owner));asset['media_path']='generated';return b'content'
    def repository(self):
        self.events.append(('repository',))
        if self.repo_error:raise self.repo_error
        return self.repo
    @contextmanager
    def guard(self):
        self.events.append(('enter',))
        try:yield
        finally:self.events.append(('exit',))
    def seed(self,**kwargs):
        self.store['standards']=[dict(id='std',owner_user_id=self.owner.get()[0],standard_type='label',status='draft',revision_number=0,**kwargs)]
        self.store['assets']=[dict(id='asset',standard_id='std',owner_user_id=self.owner.get()[0],ordinal=1,status='candidate',classification_source='human',asset_kind='label_candidate',sha256='hash')]
    def import_file(self,upload,**kwargs):
        return asyncio.run(self.imports.import_text_inspection_standard(upload,kwargs.get('name','name'),kwargs.get('material','part'),kwargs.get('version','1')))
    def add(self,upload=None,expected=''):
        return asyncio.run(self.edits.add_text_inspection_standard_asset('std',upload or Upload(b'image','new.png'),expected))
    def patch(self,action='review',expected=0,read=None):
        async def body():return {'action':action,'expected_revision':expected}
        return asyncio.run(self.edits.patch_text_inspection_asset('std','asset',read or body))


class StandardContracts(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='standards-');self.addCleanup(self.temporary.cleanup)
        self.f=Fixture(self.temporary.name)
    def test_import_provider_first_errors_are_not_retried(self):
        for mode in ('doc','docx','start','unavailable'):
            with self.subTest(mode=mode):
                f=Fixture(Path(self.temporary.name)/mode);error=RuntimeError('unknown '+mode+' outcome')
                failed=Mock(side_effect=[error,f.parser_result if mode in {'doc','docx'} else None])
                if mode=='doc':f.imports.parsers=replace(f.imports.parsers,doc=lambda:failed)
                elif mode=='docx':f.imports.parsers=replace(f.imports.parsers,docx=failed)
                elif mode=='start':f.imports.classification=replace(f.imports.classification,start=failed)
                else:
                    f.start_error=HTTPException(503,'unavailable')
                    f.imports.classification=replace(f.imports.classification,mark_unavailable=lambda:failed)
                with self.assertRaises(RuntimeError) as caught:f.import_file(Upload(filename='file.doc' if mode=='doc' else 'file.docx'))
                self.assertIs(caught.exception,error);failed.assert_called_once()
                parsed=mode in {'doc','docx'}
                self.assertEqual(len(f.files),0 if parsed else 2)
                self.assertTrue(all(path.exists() for path in f.files))
                self.assertEqual(len(f.store['standards']),0 if parsed else 1)
                self.assertEqual(len(f.store['assets']),0 if parsed else 1)
                self.assertFalse(any(e[0] in {'public','owned'} for e in f.events))
                if parsed:self.assertFalse(any(e[0] in {'write','save','start','unavailable'} for e in f.events))
                if mode=='unavailable':self.assertEqual(sum(e[0]=='start' for e in f.events),1)

    def test_import_first_write_error_retains_prior_evidence(self):
        for kind in ('standards','assets'):
            with self.subTest(kind=kind):
                f=Fixture(Path(self.temporary.name)/kind);error=RuntimeError('unknown '+kind+' outcome')
                failed=Mock(side_effect=[error,True]);attempts=[]
                def save(table,value,*,insert_only=False):
                    attempts.append((table,insert_only))
                    return failed() if table==kind else f.save(table,value,insert_only=insert_only)
                f.imports.records=replace(f.imports.records,save=save)
                with self.assertRaises(RuntimeError) as caught:f.import_file(Upload())
                self.assertIs(caught.exception,error);failed.assert_called_once_with()
                self.assertEqual(attempts,[('standards',True)]+([('assets',True)] if kind=='assets' else []))
                self.assertEqual(len(f.files),1 if kind=='standards' else 2)
                self.assertTrue(all(path.exists() for path in f.files))
                self.assertEqual(len(f.store['standards']),0 if kind=='standards' else 1)
                self.assertEqual(f.store['assets'],[])
                self.assertFalse(any(e[0] in {'start','unavailable','public'} for e in f.events))

    def test_postgres_first_error_keeps_cause_and_cleanup_order(self):
        for mode in ('add','patch','confirm'):
            with self.subTest(mode=mode):
                f=Fixture(Path(self.temporary.name)/mode);f.seed();before=copy.deepcopy(f.store)
                error=RuntimeError('unknown database '+mode+' outcome');f.repo=Mock()
                name={'add':'add_text_inspection_standard_asset','patch':'patch_text_inspection_asset','confirm':'confirm_text_inspection_standard'}[mode]
                result=f.store['standards'][0] if mode=='confirm' else (f.store['assets'][0],f.store['standards'][0])
                failed=getattr(f.repo,name);failed.side_effect=[error,result]
                unlink=Path.unlink
                with patch.object(Path,'unlink',autospec=True,side_effect=unlink) as removed:
                    with self.assertRaises(HTTPException) as caught:
                        if mode=='add':f.add()
                        elif mode=='patch':f.patch()
                        else:f.edits.confirm_text_inspection_standard('std')
                self.assertEqual(caught.exception.status_code,409);self.assertIs(caught.exception.__cause__,error)
                failed.assert_called_once();self.assertEqual(f.store,before)
                self.assertFalse(any(e[0] in {'save','public','enter','exit'} for e in f.events))
                if mode=='add':removed.assert_called_once_with(f.files[0],missing_ok=True);self.assertFalse(f.files[0].exists())
                else:removed.assert_not_called();self.assertEqual(f.files,[])

    def test_json_edit_first_error_keeps_prior_writes_and_releases_lock(self):
        for mode in ('body','feedback','patch-standard','confirm-standard'):
            with self.subTest(mode=mode):
                f=Fixture(Path(self.temporary.name)/mode);f.seed();before=copy.deepcopy(f.store)
                error=RuntimeError('unknown '+mode+' outcome');attempts=[]
                if mode=='body':
                    failed=AsyncMock(side_effect=[error,{'action':'review','expected_revision':0}])
                    with self.assertRaises(RuntimeError) as caught:f.patch(read=failed)
                    failed.assert_awaited_once_with();self.assertIs(caught.exception,error)
                    self.assertEqual(f.store,before)
                    self.assertFalse(any(e[0] in {'repository','enter','exit','save','public'} for e in f.events))
                    continue
                failed=Mock(side_effect=[error,True]);table='feedback' if mode=='feedback' else 'standards'
                def save(kind,value,*,insert_only=False):
                    attempts.append((kind,copy.deepcopy(value),insert_only))
                    return failed() if kind==table else f.save(kind,value,insert_only=insert_only)
                f.edits.records=replace(f.edits.records,save=save)
                with self.assertRaises(RuntimeError) as caught:
                    if mode=='confirm-standard':f.edits.confirm_text_inspection_standard('std')
                    else:f.patch()
                self.assertIs(caught.exception,error);failed.assert_called_once_with()
                self.assertEqual(sum(e[0]=='enter' for e in f.events),1);self.assertEqual(sum(e[0]=='exit' for e in f.events),1)
                self.assertFalse(any(e[0]=='public' for e in f.events));self.assertEqual(f.store['feedback'],[])
                if mode=='confirm-standard':
                    self.assertEqual([e[0] for e in attempts],['standards'])
                    self.assertEqual(len(f.store['revisions']),1)
                    self.assertEqual(attempts[0][1]['current_revision_id'],f.store['revisions'][0]['id'])
                    self.assertEqual(f.store['standards'],before['standards'])
                else:
                    self.assertEqual([e[0] for e in attempts],['assets','standards']+(['feedback'] if mode=='feedback' else []))
                    self.assertEqual(f.store['assets'][0]['status'],'needs_confirmation')
                    self.assertEqual(f.store['revisions'],[])
                    if mode=='patch-standard':self.assertEqual(f.store['standards'],before['standards'])
                    else:self.assertEqual(f.store['standards'][0]['asset_count'],0)

    def test_dependency_capture_matches_original_event_sequences(self):
        expected={
            'import_text':['strip','textA','textB','textB','writeA','publicA'],
            'doc_queued':['textA','textA','textA','queued','docA','writeA','publicA'],
            'asset_write':['textA','textA','textA','writeA','blob-index','writeA','publicA'],
            'unavailable':['textA','textA','textA','writeA','reason','markA','publicA'],
            'add_text':['expectedA','filename','textA','writeA','publicA','publicA'],
            'expected':['jsonA','expected-arg','expectedA','publicA','publicA'],
            'public_db':['db','publicA'], 'public_owned':['owned-second','publicA'],
            'apply_confirm':['confirmed-time','applyA','publicA'],
            'request_json':['jsonB','expectedA','publicA','publicA'],
        }
        for case,events in expected.items():
            with self.subTest(case=case):self.assertEqual(capture_trial(case),events)

    def test_capture_window_rejects_entry_caching_and_late_lookup(self):
        # Prior business work switches A to B; evaluating the call's arguments
        # switches B to C. The current call must use B, never cached A or late C.
        expected={
            'doc_queued':['textA','textA','textA','queued','docB','writeA','publicA'],
            'asset_write':['textA','textA','textA','writeA','blob-index','writeB','publicA'],
            'unavailable':['textA','textA','textA','writeA','reason','markB','publicA'],
            'expected':['jsonA','expected-arg','expectedB','publicA','publicA'],
            'public_db':['db','publicB'], 'public_owned':['owned-second','publicB'],
            'apply_confirm':['confirmed-time','applyB','publicA'],
        }
        for case,events in expected.items():
            with self.subTest(case=case):self.assertEqual(capture_trial(case,window=True),events)

    def test_import_admission_duplicate_and_parser_thread_identity(self):
        f=self.f;u=Upload();
        with self.assertRaises(HTTPException) as error:f.import_file(u,name=' ')
        self.assertEqual(error.exception.status_code,400);self.assertEqual(u.reads,[])
        f.owner.set(('denied','denied'));u=Upload()
        with self.assertRaises(HTTPException) as error:f.import_file(u)
        self.assertEqual(error.exception.status_code,403);self.assertEqual(u.reads,[])
        f.owner.set(('alice','alice'))
        f.store['standards']=[dict(id='duplicate',owner_user_id='alice',source_sha256=f.media.digest(b'fixture'),material_code='part',version_label='1',status='draft')]
        self.assertTrue(f.import_file(Upload(filename='unsupported.bin'))['duplicate'])
        u=Upload(filename='file.pdf')
        with self.assertRaises(HTTPException) as error:f.import_file(u)
        self.assertEqual(error.exception.status_code,410);self.assertEqual(u.reads,[100*1024*1024+1])
        f.store['standards'][0]['status']='deleted'
        with self.assertRaises(HTTPException) as error:f.import_file(Upload())
        self.assertEqual(error.exception.status_code,409)
        f.store['standards']=[];main_thread=threading.get_ident();f.owner.set(('thread-owner','thread-owner'));f.import_file(Upload(filename='file.doc'))
        parse=next(e for e in f.events if e[0]=='parse');self.assertEqual(parse[1:3],('doc','thread-owner'));self.assertNotEqual(parse[3],main_thread)
        f.store['standards']=[];f.events=[];f.owner.set(('alice','alice'));f.import_file(Upload())
        self.assertEqual(next(e for e in f.events if e[0]=='parse')[3],main_thread)
        for exception,status in [(DocImageUnavailable('missing'),503),(DocImageError('broken'),400),(UnsafeDocument('unsafe'),400)]:
            f.store['standards']=[];f.parser_error=exception
            with self.assertRaises(HTTPException) as error:f.import_file(Upload())
            self.assertEqual(error.exception.status_code,status)
    def test_import_partial_writes_and_classification_failure_boundaries(self):
        for failure_at in (1,3):
            part=Fixture(Path(self.temporary.name)/str(failure_at))
            part.parser_result=([dict(ordinal=i,status='candidate',mime_type='image/png') for i in (1,2)],[b'first',b'second'])
            writes=[]
            def failing_write(path,data):
                writes.append(path)
                if len(writes)==failure_at:raise OSError('write failed')
                part.write(path,data)
            part.imports.media=StandardMedia(part.path,lambda:failing_write,part.media.digest)
            with self.assertRaisesRegex(OSError,'write failed'):part.import_file(Upload())
            self.assertEqual(len(writes),failure_at)
            self.assertEqual(len(part.store['standards']),0 if failure_at==1 else 1)
            self.assertEqual(len(part.store['assets']),0 if failure_at==1 else 1)
            self.assertTrue(all(path.exists() for path in part.files))
            self.assertEqual(len(part.files),failure_at-1)
            self.assertFalse(any(e[0]=='start' for e in part.events))
            if failure_at==1:self.assertFalse(any(e[0]=='save' for e in part.events))
        f=self.f;f.fail['standards']=False
        with self.assertRaises(HTTPException) as error:f.import_file(Upload())
        self.assertEqual(error.exception.status_code,409);self.assertEqual(len(f.files),1);self.assertTrue(f.files[0].exists())
        f.fail={'assets':False};f.start_error=HTTPException(503,'offline');result=f.import_file(Upload())
        self.assertEqual(result['assets'],[]);self.assertEqual(len(f.store['standards']),1)
        self.assertTrue(any(e[0]=='unavailable' and e[-1]=='offline' for e in f.events))
        self.assertTrue(all(e[3] is True for e in f.events if e[0]=='save'))
        f.store['standards']=[];f.start_error=RuntimeError('startup')
        with self.assertRaisesRegex(RuntimeError,'startup'):f.import_file(Upload())
        self.assertEqual(len(f.store['standards']),1)
        f.store['standards']=[];f.start_error=HTTPException(503,'offline');f.unavailable_error=RuntimeError('mark')
        with self.assertRaisesRegex(RuntimeError,'mark'):f.import_file(Upload())
        self.assertEqual(len(f.store['standards']),1)
    def test_library_refresh_media_double_read_and_native_headers(self):
        f=self.f;f.seed(classification={'state':'processing'})
        result=f.library.get_text_inspection_standard('std');self.assertEqual(result['id'],'std')
        self.assertEqual(sum(e[0]=='refresh' for e in f.events),1)
        response=f.routes.get_text_inspection_asset_content('asset')
        self.assertEqual(f.media_calls,2);self.assertEqual(response.body,b'content')
        self.assertEqual(response.headers['cache-control'],'private, no-store');self.assertEqual(response.headers['x-content-type-options'],'nosniff')
        self.assertEqual(response.media_type,'application/octet-stream')
        f.owner.set(('bob','bob'))
        with self.assertRaises(HTTPException) as error:f.library.get_text_inspection_asset_content('asset')
        self.assertEqual(error.exception.status_code,404);self.assertEqual(f.media_calls,2)
        f.owner.set(('alice','alice'));f.store['standards'][0]['status']='deleted'
        self.assertEqual(f.library.list_text_inspection_standards()['items'],[])
        self.assertEqual(f.library.get_text_inspection_standard('std')['status'],'deleted')
    def test_add_factory_failure_cleanup_and_partial_record_evidence(self):
        f=self.f;f.seed();u=Upload()
        with self.assertRaises(HTTPException):f.add(u,'bad')
        self.assertEqual(u.reads,[])
        f.repo_error=RuntimeError('factory')
        with self.assertRaisesRegex(RuntimeError,'factory'):f.add()
        self.assertTrue(f.files[-1].exists());self.assertEqual(len(f.store['assets']),1)
        prior_file=f.files[-1]
        f.repo_error=None;f.repo=Mock();f.repo.add_text_inspection_standard_asset.side_effect=HTTPException(418,'repo')
        with self.assertRaises(HTTPException) as error:f.add(expected='7')
        self.assertEqual(error.exception.status_code,418);self.assertFalse(f.files[-1].exists());self.assertTrue(prior_file.exists())
        f.repo.add_text_inspection_standard_asset.assert_called_once()
        self.assertEqual(f.repo.add_text_inspection_standard_asset.call_args.kwargs['expected_revision'],7)
        f.repo=None;f.fail['standards']=RuntimeError('save')
        with self.assertRaises(HTTPException) as error:f.add()
        self.assertEqual(error.exception.status_code,409);self.assertFalse(f.files[-1].exists());self.assertTrue(prior_file.exists())
        self.assertEqual(len(f.store['assets']),2)
        relevant=[e[0] if e[0]!='save' else e[1] for e in f.events if e[0] in {'enter','exit','save'}]
        self.assertEqual(relevant[-4:],['enter','assets','standards','exit'])
        self.assertIs(next(e for e in reversed(f.events) if e[0]=='save' and e[1]=='assets')[3],True)
    def test_patch_body_order_noop_feedback_and_error_conversion(self):
        f=self.f;f.seed();calls=[]
        async def invalid():calls.append('read');raise ValueError('invalid JSON')
        f.owner.set(('other','other'))
        with self.assertRaises(HTTPException) as error:f.patch(read=invalid)
        self.assertEqual(error.exception.status_code,404);self.assertEqual(calls,[])
        f.owner.set(('alice','alice'));f.store['standards'][0]['standard_type']='manual'
        with self.assertRaises(HTTPException) as error:f.patch(read=invalid)
        self.assertEqual(error.exception.status_code,410);self.assertEqual(calls,[])
        f.store['standards'][0]['standard_type']='label'
        with self.assertRaisesRegex(ValueError,'invalid JSON'):f.patch(read=invalid)
        f.events=[];f.patch('confirm')
        saves=[e for e in f.events if e[0]=='save'];self.assertEqual([e[1] for e in saves],['feedback']);self.assertIs(saves[0][3],True)
        self.assertLess(next(i for i,e in enumerate(f.events) if e[0]=='exit'),next(i for i,e in enumerate(f.events) if e[0]=='save'))
        f.fail['feedback']=RuntimeError('feedback')
        with self.assertRaisesRegex(RuntimeError,'feedback'):f.patch('review')
        self.assertEqual(f.store['assets'][0]['status'],'needs_confirmation')
        f.fail={};f.repo=Mock();f.repo.patch_text_inspection_asset.side_effect=HTTPException(418,'repo')
        with self.assertRaises(HTTPException) as error:f.patch()
        self.assertEqual(error.exception.status_code,409)
    def test_confirmation_preparation_shortcut_and_projection_failure(self):
        f=self.f;f.seed();f.store['standards'][0]['status']='confirmed';f.preparation_enabled=True
        f.repo_error=AssertionError('repository should not run');f.edits.confirm_text_inspection_standard('std')
        self.assertTrue(any(e[0]=='prepare' for e in f.events));self.assertFalse(any(e[0]=='repository' for e in f.events))
        f.preparation_enabled=False;f.repo_error=None;f.repo=Mock();f.repo.confirm_text_inspection_standard.return_value=f.store['standards'][0]
        def broken(value):raise RuntimeError('projection')
        records=StandardRecords(f.load,f.save,f.owned,lambda:broken);f.edits.records=records
        with self.assertRaises(HTTPException) as error:f.edits.confirm_text_inspection_standard('std')
        self.assertEqual(error.exception.status_code,409)
        f.repo=None
        with self.assertRaisesRegex(RuntimeError,'projection'):f.edits.confirm_text_inspection_standard('std')
        f.edits.records=f.records;f.store['standards'][0]['status']='draft';f.store['assets'][0]['status']='needs_confirmation'
        with self.assertRaises(HTTPException) as error:f.edits.confirm_text_inspection_standard('std')
        self.assertEqual(error.exception.status_code,409)
        f.store['assets'][0]['status']='candidate';result=f.edits.confirm_text_inspection_standard('std')
        self.assertEqual(result['revision_number'],1);self.assertEqual(result['confirmed_asset_ids'],['asset'])
    def test_two_apps_interleaved_sync_async_owner_and_route_contract(self):
        a=self.f;b=Fixture(Path(self.temporary.name)/'second','bob');a.seed();b.seed()
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=a.app),base_url='http://a') as ca, httpx.AsyncClient(transport=httpx.ASGITransport(app=b.app),base_url='http://b') as cb:
                responses=await asyncio.gather(ca.get('/api/text-inspection/standards'),cb.get('/api/text-inspection/standards'),
                    ca.post('/api/text-inspection/standards/std/assets',files={'file':('a.png',b'a','image/png')}),
                    cb.post('/api/text-inspection/standards/std/assets',files={'file':('b.png',b'b','image/png')}),
                    ca.get('/api/text-inspection/standards/std',headers={'x-owner':'bob'}),cb.get('/api/text-inspection/assets/asset/content',headers={'x-owner':'alice'}))
                return responses
        responses=asyncio.run(run());self.assertEqual([r.status_code for r in responses],[200,200,200,200,404,404])
        self.assertEqual(responses[0].json()['items'][0]['owner_user_id'],'alice');self.assertEqual(responses[1].json()['items'][0]['owner_user_id'],'bob')
        self.assertEqual(responses[2].json()['asset']['owner_user_id'],'alice');self.assertEqual(responses[3].json()['asset']['owner_user_id'],'bob')
        for f in (a,b):
            routes=[r for r in f.app.routes if r.path.startswith('/api/text-inspection/')]
            self.assertEqual(len(routes),7)
            for route in routes:self.assertIs(route.endpoint,getattr(f.routes,route.name))
            schema=f.app.openapi();self.assertEqual(schema['paths']['/api/text-inspection/standards/{standard_id}/assets']['post']['requestBody']['required'],True)


if __name__=='__main__':unittest.main(verbosity=2)
