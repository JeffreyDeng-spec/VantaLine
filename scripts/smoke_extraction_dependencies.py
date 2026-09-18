"""Explicit extraction admission, worker, media and expiration contracts; offline only."""
import asyncio
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from local_inspection_service import label_bbox, label_extraction_api as compatibility
from local_inspection_service.text_inspection import extraction_api as api
from local_inspection_service.text_inspection.extraction_ports import ExtractionAccess, ExtractionRecords, ExtractionMedia, ExtractionModels

PREFIX='/api/text-inspection/extractions'


class ExtractionContracts(unittest.TestCase):
    def fixture(self,name):
        app=FastAPI();identity=ContextVar(name,default='alice');temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        f=SimpleNamespace(root=Path(temp.name),data={},events=[],reads=[],writes=[],workers=[],clears=0,allowed=True,enabled=False,pg=True,reject=None,fail_save=False,lose_insert=False,calls=[])
        f.image_config={'configured':False,'provider':'fixture','model':name,'timeout_seconds':1}
        f.save_errors=[]
        f.document_config={'configured':True,'provider':'qwen','model':name,'api_key':'synthetic','base_url':'https://fixture.invalid'}
        output=io.BytesIO();Image.new('RGB',(300,200),'white').save(output,'PNG');f.image=output.getvalue()
        @app.middleware('http')
        async def bind(request,call_next):
            token=identity.set(request.headers.get('x-owner','alice'))
            try:return await call_next(request)
            finally:identity.reset(token)
        def permission(key,*,detail):
            f.events.append(('permission',identity.get(),key))
            if not f.allowed:raise HTTPException(403,detail)
        def owned(kind,key,uid):
            value=f.data.get((kind,key));return copy.deepcopy(value) if value and value['owner_user_id']==uid else None
        def load(kind):f.events.append(('load',kind,identity.get()));return [copy.deepcopy(v) for (k,_),v in f.data.items() if k==kind]
        class Repo:
            def fetch_by_primary_key(self,table,key):
                f.events.append(('fetch',table,key,identity.get()));value=f.data.get(('extractions',key['id']))
                return {'raw_json':copy.deepcopy(value),'owner_user_id':value['owner_user_id']} if value else None
            def fetch_label_extraction_rows(self,uid,root):
                f.events.append(('rows',uid,root,identity.get()))
                return [copy.deepcopy(v) for (k,_),v in f.data.items() if k=='extractions' and v['owner_user_id']==uid and (root is None or v['root_id']==root)]
        repo=Repo()
        def repository():f.events.append(('repository',identity.get()));return repo if f.pg else None
        def save(kind,value,*,insert_only=False):
            f.events.append(('save',kind,value['id'],insert_only))
            if f.save_errors:
                failure=f.save_errors.pop(0)
                if failure is not None:raise failure
            if f.fail_save:raise RuntimeError('synthetic save failure')
            if value['id']==f.reject:return False
            if insert_only and f.lose_insert:
                f.data[kind,value['id']]=copy.deepcopy(value);return False
            if insert_only and (kind,value['id']) in f.data:return False
            f.data[kind,value['id']]=copy.deepcopy(value);return True
        def path(uid,identifier,name):return f.root/uid/identifier/name
        def write(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);f.writes.append(path)
        def read(path,uid,identifier,**kwargs):
            f.reads.append((path,uid,identifier,kwargs));data=Path(path).read_bytes()
            if kwargs.get('expected_sha256') and digest(data)!=kwargs['expected_sha256']:raise HTTPException(409,'hash mismatch')
            return data
        def digest(data):return hashlib.sha256(data).hexdigest()
        def clear():f.events.append(('clear',));f.clears+=1
        class Provider:
            def generate_image(self,prompt,images,*,model):f.calls.append(('image',model,images));raise TimeoutError('synthetic unknown')
        def provider(settings):f.calls.append(('provider',copy.deepcopy(settings)));return Provider()
        def transport(request,settings,*,timeout):f.calls.append(('bbox',json.loads(request.data),copy.deepcopy(settings),timeout));raise TimeoutError('synthetic unknown')
        ports=ExtractionMedia(path,write,read,digest,lambda data,mime:'data:'+mime+';base64,'+base64.b64encode(data).decode())
        models=ExtractionModels(lambda:f.image_config,lambda purpose:f.document_config,provider,transport,copy.deepcopy,lambda:f.enabled)
        f.resolve=api.register(app,ExtractionAccess(permission,lambda:(identity.get(),name)),ExtractionRecords(repository,owned,load,save),ports,models,clear)
        self.assertEqual(f.events,[]);self.assertIs(compatibility.register,api.register)
        f.client=TestClient(app,raise_server_exceptions=False);self.addCleanup(f.client.close)
        f.endpoint=next(route.endpoint for route in app.routes if route.path==PREFIX and 'POST' in route.methods)
        f.path=path;f.write=write;f.digest=digest;return f
    def create(self,f,uid='alice',request='manual_001'):
        return f.client.post(PREFIX,headers={'x-owner':uid},data={'target':'[0.1,0.1,0.8,0.8]','request_id':request,'method':'manual'},files={'file':('fixture.bin',f.image,'application/octet-stream')})
    def test_native_two_app_identity_pg_arguments_dynamic_settings_and_resolver(self):
        first,second=self.fixture('first'),self.fixture('second')
        with patch.dict('os.environ',{'VANTALINE_LABEL_EXTRACTION_ACCOUNTS':'alice,bob'}):
            with ThreadPoolExecutor(max_workers=2) as pool:
                a=pool.submit(self.create,first,'alice');b=pool.submit(self.create,second,'bob');one,two=a.result().json(),b.result().json()
        self.assertNotEqual(one['id'],two['id']);self.assertEqual(one['diagnostics']['model'],'first');self.assertEqual(two['diagnostics']['model'],'second')
        for f,uid,result in [(first,'alice',one),(second,'bob',two)]:
            queries=[e for e in f.events if e[0]=='rows'];self.assertTrue(queries)
            self.assertTrue(all(e[1]==uid and e[-1]==uid for e in queries))
            fetches=[e for e in f.events if e[0]=='fetch'];self.assertTrue(fetches)
            self.assertTrue(all(e[1:]==('text_label_extractions',{'id':result['id']},uid) for e in fetches))
            self.assertFalse(any(e[0]=='load' and e[1]=='extractions' for e in f.events))
            self.assertNotIn('owner_user_id',result);self.assertNotIn('source_path',result)
            value=f.data['extractions',result['id']];value.update(status='confirmed',standard_asset_id='asset',standard_revision_id='rev',crop_path=value['source_path'],crop_sha256=value['source_sha256'])
            data,public=f.resolve(value['id'],uid,'asset',{'current_revision_id':'rev'})
            self.assertEqual(data,Path(value['source_path']).read_bytes());self.assertEqual(public['status'],'confirmed')
            self.assertEqual(f.reads[-1][3],{'expected_sha256':value['crop_sha256'],'max_bytes':100*1024*1024})
        first.image_config={'configured':True,'provider':'later','model':'later'};first.enabled=True
        with patch.dict('os.environ',{'VANTALINE_LABEL_EXTRACTION_ACCOUNTS':'alice'}):
            response=first.client.get('/api/text-inspection/extraction-capabilities').json();self.assertTrue(response['ai_available']);self.assertEqual(response['model'],'later')
    def test_upload_admission_limit_and_worker_targets_preserve_settings_cleanup(self):
        for method,fail_save in [('ai',False),('ai',True),('vlm_bbox',False),('vlm_bbox',True)]:
            with self.subTest(method=method,fail_save=fail_save):
                f=self.fixture(method);f.enabled=True;f.image_config['configured']=True
                class Upload:
                    async def read(self,limit):f.events.append(('upload',limit));return f.image
                class Thread:
                    def __init__(self,**kwargs):self.kwargs=kwargs
                    def start(self):f.workers.append(self.kwargs)
                with patch.dict('os.environ',{'VANTALINE_LABEL_EXTRACTION_ACCOUNTS':'alice','VANTALINE_LABEL_BBOX_ACCOUNTS':'alice'}),patch.object(api.threading,'Thread',Thread):
                    value=asyncio.run(f.endpoint(Upload(),'[0.1,0.1,0.8,0.8]','worker_001',method))
                    duplicate=asyncio.run(f.endpoint(Upload(),'[0.1,0.1,0.8,0.8]','worker_001',method))
                self.assertEqual(value['id'],duplicate['id']);self.assertEqual(len(f.workers),1)
                self.assertTrue(all(e[1]==10*1024*1024+1 for e in f.events if e[0]=='upload'))
                task=f.workers[0];self.assertEqual(f.data['extractions',value['id']]['status'],'attempting')
                f.image_config={'configured':True,'model':'replacement'};f.document_config={'configured':True,'model':'replacement'}
                f.fail_save=fail_save
                if fail_save:
                    with self.assertRaises(RuntimeError):task['target'](*task['args'])
                    self.assertEqual(f.data['extractions',value['id']]['status'],'attempting')
                else:
                    task['target'](*task['args']);self.assertEqual(f.data['extractions',value['id']]['status'],'uncertain')
                self.assertEqual(f.clears,1)
                self.assertEqual([call[0] for call in f.calls],['provider','image'] if method=='ai' else ['bbox'])
                if method=='ai':
                    self.assertTrue(f.calls[0][1]['single_attempt']);self.assertEqual(f.calls[1][1],method);self.assertEqual(f.calls[1][2][0]['type'],'image_url')
                else:self.assertEqual(f.calls[0][1]['model'],method);self.assertEqual(f.calls[0][3],label_bbox.TIMEOUT)
        f=self.fixture('insert-loser');f.lose_insert=True;f.enabled=True;f.image_config['configured']=True
        class Upload:
            async def read(self,limit):return f.image
        class NoThread:
            def __init__(self,**kwargs):raise AssertionError('losing insert must not start work')
        with patch.dict('os.environ',{'VANTALINE_LABEL_EXTRACTION_ACCOUNTS':'alice'}),patch.object(api.threading,'Thread',NoThread):
            value=asyncio.run(f.endpoint(Upload(),'[0.1,0.1,0.8,0.8]','insert_001','ai'))
        self.assertIn(('extractions',value['id']),f.data);self.assertEqual(f.calls,[]);self.assertEqual(f.clears,0)
        f=self.fixture('denied');f.allowed=False
        with patch.dict('os.environ',{'VANTALINE_LABEL_EXTRACTION_ACCOUNTS':'alice'}):response=self.create(f)
        self.assertEqual(response.status_code,403);self.assertEqual(f.events,[('permission','alice','inspection')]);self.assertEqual(f.writes,[])
    def queue_worker(self,f,method):
        f.enabled=True;f.image_config['configured']=True
        class Upload:
            async def read(self,limit):return f.image
        class Thread:
            def __init__(self,**kwargs):self.kwargs=kwargs
            def start(self):f.workers.append(self.kwargs)
        with patch.dict('os.environ',{'VANTALINE_LABEL_EXTRACTION_ACCOUNTS':'alice','VANTALINE_LABEL_BBOX_ACCOUNTS':'alice'}),patch.object(api.threading,'Thread',Thread):
            value=asyncio.run(f.endpoint(Upload(),'[0.1,0.1,0.8,0.8]','boundary_001',method))
        self.assertEqual(len(f.workers),1)
        return value,f.workers[0]

    def test_first_final_save_failure_is_not_retried_in_either_worker(self):
        for method in ('ai','vlm_bbox'):
            with self.subTest(method=method):
                f=self.fixture('save-once-'+method);value,task=self.queue_worker(f,method)
                durable=copy.deepcopy(f.data)
                failure=RuntimeError('synthetic unknown final save')
                f.save_errors=[failure,None];f.events.clear()
                with self.assertRaises(RuntimeError) as caught:task['target'](*task['args'])
                self.assertIs(caught.exception,failure)
                self.assertEqual(f.events,[('save','extractions',value['id'],False),('clear',)])
                self.assertEqual(f.save_errors,[None]);self.assertEqual(f.clears,1)
                self.assertEqual(f.data,durable)
                self.assertEqual(f.data['extractions',value['id']]['status'],'attempting')
                self.assertEqual([call[0] for call in f.calls],['provider','image'] if method=='ai' else ['bbox'])

    def test_deadline_is_strict_projection_and_late_worker_result_is_retained(self):
        for method in ('ai','vlm_bbox'):
            with self.subTest(method=method):
                f=self.fixture('deadline-'+method);value,task=self.queue_worker(f,method)
                durable=copy.deepcopy(f.data);deadline=value['deadline_at'];f.events.clear()
                url=PREFIX+'/'+value['id']
                for now,status in ((deadline,'attempting'),(deadline+0.001,'uncertain')):
                    with patch.object(api.time,'time',return_value=now):response=f.client.get(url)
                    self.assertEqual(response.status_code,200)
                    self.assertEqual(response.json()['status'],status)
                    if status=='uncertain':self.assertEqual(response.json()['error_code'],'provider_outcome_unknown')
                    else:self.assertNotIn('error_code',response.json())
                    self.assertEqual(f.data,durable)
                self.assertEqual(f.calls,[]);self.assertEqual(f.clears,0)
                self.assertFalse(any(event[0] in {'save','clear'} for event in f.events))
                with patch.object(api.time,'time',return_value=deadline+1),patch('builtins.print'):
                    task['target'](*task['args'])
                    settled=copy.deepcopy(f.data)
                    response=f.client.get(url)
                self.assertEqual(response.status_code,200)
                self.assertEqual((response.json()['status'],response.json()['error_code']),('uncertain','TimeoutError'))
                self.assertEqual(response.json()['finished_at'],deadline+1)
                self.assertEqual(f.data,settled);self.assertEqual(f.clears,1);self.assertEqual(len(f.workers),1)
                self.assertEqual([call[0] for call in f.calls],['provider','image'] if method=='ai' else ['bbox'])

    def test_expiration_protects_history_and_failed_tombstone_and_non_png(self):
        f=self.fixture('expiry')
        for identifier in ['protected','loser','expired']:
            path=f.path('alice',identifier,'source.png');f.write(path,f.image)
            f.data['extractions',identifier]={'id':identifier,'root_id':identifier,'kind':'task','version':0,'owner_user_id':'alice','created_at':int(time.time())-8*86400,'status':'needs_adjustment','source_path':str(path),'source_sha256':f.digest(f.image)}
        f.data['records','history']={'id':'history','owner_user_id':'alice','diagnostics':{'extraction':{'root_id':'protected'}}};f.reject='loser_v1'
        directory=f.path('alice','expired','source.png').parent
        keep=directory/'keep.txt';keep.write_text('synthetic');upper=directory/'keep.PNG';upper.write_bytes(f.image)
        link=directory/'link.png'
        try:link.symlink_to(keep);has_link=True
        except OSError:has_link=False
        self.assertEqual(f.client.get('/api/text-inspection/extraction-capabilities').status_code,200)
        self.assertTrue(f.path('alice','protected','source.png').exists());self.assertTrue(f.path('alice','loser','source.png').exists())
        self.assertFalse(f.path('alice','expired','source.png').exists());self.assertTrue(keep.exists());self.assertTrue(upper.exists())
        if has_link:self.assertTrue(link.is_symlink())
        self.assertEqual(f.data['extractions','expired_v1']['status'],'expired');self.assertNotIn(('extractions','loser_v1'),f.data)
    def test_media_owner_hash_headers_and_losing_revision_only_removes_new_crop(self):
        f=self.fixture('media')
        with patch.dict('os.environ',{'VANTALINE_LABEL_EXTRACTION_ACCOUNTS':'alice'}):result=self.create(f).json()
        source=Path(f.data['extractions',result['id']]['source_path'])
        self.assertEqual(f.client.get(result['media']['source'],headers={'x-owner':'bob'}).status_code,404);self.assertEqual(f.reads,[])
        response=f.client.get(result['media']['source']);self.assertEqual(response.content,source.read_bytes())
        self.assertEqual(response.headers['cache-control'],'private, no-store');self.assertEqual(response.headers['x-content-type-options'],'nosniff')
        self.assertEqual(f.reads[-1][3],{'expected_sha256':f.digest(source.read_bytes()),'max_bytes':100*1024*1024})
        f.reject=result['id']+'_v1';before=set(f.writes);unrelated=source.parent/'winner.png';unrelated.write_bytes(f.image)
        response=f.client.post(PREFIX+'/'+result['id']+'/revise',json={'version':0,'polygon':[[.1,.1],[.9,.1],[.9,.9],[.1,.9]]})
        self.assertEqual(response.status_code,409);new=[path for path in f.writes if path not in before]
        self.assertEqual(len(new),1);self.assertFalse(new[0].exists());self.assertTrue(unrelated.exists());self.assertTrue(source.exists())


if __name__=='__main__':unittest.main(verbosity=2)
