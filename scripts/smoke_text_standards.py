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
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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


class Fixture:
    def __init__(self, directory, owner='alice'):
        self.directory=Path(directory);self.events=[];self.owner=ContextVar('standard_owner',default=(owner,owner))
        self.store={'standards':[], 'assets':[], 'revisions':[], 'feedback':[]}
        self.repo=None;self.repo_error=None;self.fail={};self.files=[];self.preparation_enabled=False
        self.parser_result=([dict(ordinal=1,status='candidate',mime_type='image/png')],[b'image'])
        self.parser_error=None;self.start_error=None;self.unavailable_error=None;self.media_calls=0
        self.access=StandardAccess(self.require,lambda:self.owner.get())
        self.records=StandardRecords(self.load,self.save,self.owned,self.public)
        self.media=StandardMedia(self.path,self.write,lambda data:hashlib.sha256(data).hexdigest())
        self.revision_service=TextRevisions(RevisionRecords(self.load,self.save),confirmed_snapshot)
        self.imports=StandardImports(self.access,self.records,self.media,
            StandardParsers(lambda data:self.parse('doc',data),lambda data:self.parse('docx',data),lambda data:self.parse('pdf',data)),
            StandardClassification(self.start,self.unavailable),lambda value,limit:value[:limit])
        self.library=StandardLibrary(self.access,self.records,self.refresh,self.asset_bytes)
        self.edits=StandardEdits(self.access,self.records,StandardWrites(self.repository,self.guard),self.media,
            StandardRevisions(expected_revision,confirmed_snapshot,self.revision_service.apply),
            StandardPreparation(self.prepare,lambda owner:self.preparation_enabled),
            lambda data:(data,'image/png','.png','PNG'),lambda value,limit:value[:limit])
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
            part.imports.media=StandardMedia(part.path,failing_write,part.media.digest)
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
        records=StandardRecords(f.load,f.save,f.owned,broken);f.edits.records=records
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
