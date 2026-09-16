"""Document-job admission, durable attempts and explicit dependency contracts."""
import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
import io
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from local_inspection_service import document_import_jobs as compatibility
from local_inspection_service.text_inspection import document_api, document_jobs
from local_inspection_service.text_inspection.document_ports import DocumentAccess, DocumentRecords, DocumentModels

PREFIX = '/api/text-inspection/standards/'


class Fixture:
    def __init__(self):
        self.events=[]; self.lock=threading.RLock(); self.locked=False; self.pg=False
        self.standard={'id':'order','owner_user_id':'alice','standard_type':'label','status':'draft'}
        self.assets=[{'id':'a','standard_id':'order','owner_user_id':'alice','sha256':'same','ordinal':1,'status':'candidate'}]
        self.enabled=True; self.tasks=[]; self.calls=[]; self.usage=[]; self.clear_count=0
        self.config=dict(provider='qwen',model='synthetic',api_key='fixture-secret',base_url='https://fixture.invalid',profile_id='fixture-profile',profile_version=7)
        self.repo=SimpleNamespace(mutate_text_document=self.transaction)
        self.records=DocumentRecords(self.repository,self.guard,self.owned,self.load,self.save,copy.deepcopy)
        self.models=DocumentModels(lambda:self.enabled,self.settings,self.transport,lambda *args:self.usage.append(args))
        self.jobs=document_jobs.DocumentJobs(self.records,self.models,self.media,self.clear)
        image=Image.new('RGB',(100,60),'white'); out=io.BytesIO();image.save(out,'PNG');self.blob=out.getvalue()
    def repository(self): self.events.append(('repository',));return self.repo if self.pg else None
    @contextmanager
    def guard(self):
        with self.lock:
            self.events.append(('enter',)); self.locked=True
            try: yield
            finally:self.locked=False;self.events.append(('exit',))
    def owned(self,kind,key,owner):
        self.events.append(('owned',kind,key,owner))
        return copy.deepcopy(self.standard) if key=='order' and self.standard['owner_user_id']==owner else None
    def load(self,kind): self.events.append(('load',kind));return copy.deepcopy(self.assets)
    def save(self,kind,value):
        assert self.locked
        self.events.append(('save',kind,value['id']))
        if kind=='standards': self.standard=copy.deepcopy(value)
        else:self.assets=[copy.deepcopy(value) if row['id']==value['id'] else row for row in self.assets]
        return True
    def transaction(self,identity,owner,change):
        self.events.append(('transaction',identity,owner))
        with self.lock:
            standard,assets=copy.deepcopy((self.standard,self.assets))
            result=change(standard,assets);self.standard,self.assets=standard,assets;return result
    def settings(self,purpose):self.events.append(('settings',purpose));return self.config
    def media(self,asset,owner):
        stored=next(row for row in self.assets if row['id']==asset['id'])
        assert stored['classification_attempt']['state']=='attempting'
        self.events.append(('media',asset['id'],owner));return self.blob
    def transport(self,request,settings,*,timeout):
        assert settings['single_attempt'] is True and timeout==60
        self.calls.append((request,settings))
        body={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'category':'label_design','reason':'synthetic artwork'})}}], 'usage':{'total_tokens':1}}
        return io.BytesIO(json.dumps(body).encode())
    def clear(self):self.clear_count+=1
    def start(self,fail_thread=False):
        fixture=self
        class Thread:
            def __init__(self,**kwargs):self.kwargs=kwargs
            def start(self):
                if fail_thread:raise RuntimeError('fixture thread failure')
                fixture.tasks.append(self.kwargs)
        with patch.dict('os.environ',{'VANTALINE_DOCUMENT_CLASSIFICATION_ACCOUNTS':'alice'}), patch.object(document_jobs.threading,'Thread',Thread):
            self.jobs.start('order','alice')
    def run(self):
        task=self.tasks.pop(0);task['target'](*task['args'])


class DocumentContracts(unittest.TestCase):
    def slots_free(self,f):
        self.assertTrue(f.jobs.slots.acquire(False));self.assertTrue(f.jobs.slots.acquire(False))
        self.assertFalse(f.jobs.slots.acquire(False));f.jobs.slots.release();f.jobs.slots.release()
    def app(self,name,owner):
        f=Fixture();f.standard['owner_user_id']=owner
        app=FastAPI();identity=ContextVar(name,default='unset');f.allowed=True
        @app.middleware('http')
        async def bind(request,call_next):
            token=identity.set(request.headers.get('x-owner','alice'))
            try:return await call_next(request)
            finally:identity.reset(token)
        def permission(key,*,detail):
            f.events.append(('permission',key,detail))
            if not f.allowed:raise HTTPException(403,detail)
        def who():f.events.append(('owner',identity.get()));return identity.get(),name
        f.jobs.start=Mock()
        returned=document_api.register(app,DocumentAccess(permission,who),f.records,f.jobs)
        self.assertIs(returned,f.jobs);self.assertEqual(f.events,[])
        f.client=TestClient(app,raise_server_exceptions=False);self.addCleanup(f.client.close)
        return f
    def test_native_asgi_two_app_account_isolation_and_guard_order(self):
        first,second=self.app('first','alice'),self.app('second','bob')
        def send(f,owner):return f.client.post(PREFIX+'order/classify',headers={'x-owner':owner})
        with ThreadPoolExecutor(max_workers=2) as pool:
            one=pool.submit(send,first,'alice');two=pool.submit(send,second,'bob')
            self.assertEqual(one.result().status_code,200);self.assertEqual(two.result().status_code,200)
        first.jobs.start.assert_called_once_with('order','alice');second.jobs.start.assert_called_once_with('order','bob')
        self.assertEqual(first.events[:2],[('permission','inspection','没有文字检验权限'),('owner','alice')])
        for suffix,method in [('/classify','post'),('','delete')]:
            self.assertEqual(getattr(first.client,method)(PREFIX+'order'+suffix,headers={'x-owner':'bob'}).status_code,404)
        first.allowed=False;first.events.clear()
        response=first.client.post(PREFIX+'order/classify')
        self.assertEqual((response.status_code,response.json()),(403,{'detail':'没有文字检验权限'}))
        self.assertEqual(first.events,[('permission','inspection','没有文字检验权限')])
    def test_json_change_only_persistence_and_pg_transaction_adapter(self):
        f=Fixture();f.jobs.mutate('order','alice',lambda s,a:'no-change')
        self.assertFalse(any(e[0]=='save' for e in f.events))
        def change(s,a):s['name']='new';a[0]['status']='excluded';return 'result'
        self.assertEqual(f.jobs.mutate('order','alice',change),'result')
        self.assertEqual([e for e in f.events if e[0]=='save'],[('save','standards','order'),('save','assets','a')])
        self.assertFalse(f.locked)
        f.pg=True;f.events.clear();f.jobs.mutate('order','alice',change)
        self.assertEqual(f.events,[('repository',),('transaction','order','alice')])
        def fail(s,a):s['name']='not-committed';raise RuntimeError('rollback')
        with self.assertRaises(RuntimeError):f.jobs.mutate('order','alice',fail)
        self.assertEqual(f.standard['name'],'new')
        f.pg=False
        with self.assertRaises(RuntimeError):f.jobs.mutate('order','alice',fail)
        self.assertFalse(f.locked);self.assertEqual(f.standard['name'],'new')
    def test_start_limits_duplicate_claim_and_thread_failure_never_replays(self):
        f=Fixture()
        with self.assertRaises(RuntimeError):f.start(fail_thread=True)
        self.slots_free(f);self.assertEqual(f.standard['classification']['state'],'processing')
        f.start();self.assertEqual(f.tasks,[]);self.slots_free(f)
        f=Fixture();f.jobs.slots.acquire();f.jobs.slots.acquire()
        try:
            with self.assertRaises(HTTPException) as caught:f.start()
            self.assertEqual(caught.exception.status_code,429)
            self.assertEqual(f.events,[('settings','document')]);self.assertNotIn('classification',f.standard)
        finally:f.jobs.slots.release();f.jobs.slots.release()
        f=Fixture();f.enabled=False
        with self.assertRaises(HTTPException) as caught:f.start()
        self.assertEqual(caught.exception.status_code,409);self.assertEqual(f.events,[]);self.slots_free(f)
        f=Fixture();f.config['base_url']='http://fixture.invalid'
        with self.assertRaises(HTTPException):f.start()
        self.slots_free(f)
    def test_run_persists_attempt_before_media_deduplicates_and_cleans_up(self):
        f=Fixture();base=f.assets[0]
        f.assets=[dict(base,id='later',ordinal=3,sha256='other'),dict(base,id='a',ordinal=1),dict(base,id='duplicate',ordinal=2),dict(base,id='human',ordinal=4,classification_source='human'),dict(base,id='unknown',ordinal=5,classification_attempt={'id':'prior','state':'attempting'})]
        f.start();self.assertEqual(len(f.tasks),1);f.run()
        self.assertEqual(len(f.calls),2);self.assertEqual(len(f.usage),2)
        self.assertTrue(all(args[0] is f.config for args in f.usage))
        self.assertEqual([e[1] for e in f.events if e[0]=='media'],['a','later'])
        duplicate=next(a for a in f.assets if a['id']=='duplicate')
        self.assertEqual(duplicate['classification_attempt']['diagnostics']['reused_source_sha256'],'same')
        self.assertEqual(next(a for a in f.assets if a['id']=='unknown')['classification_attempt']['id'],'prior')
        self.assertEqual(f.standard['classification']['done'],5);self.assertEqual(f.standard['classification']['state'],'completed')
        self.assertEqual(f.clear_count,1);self.slots_free(f)
    def test_human_and_cancelled_jobs_fence_late_results_and_failures_do_not_retry(self):
        for mutation in ['human','delete','transport','media']:
            with self.subTest(mutation=mutation):
                f=Fixture();original=f.models.transport
                def transport(*args,**kwargs):
                    if mutation=='human':f.assets[0].update(status='excluded',classification_source='human')
                    if mutation=='delete':f.jobs.delete('order','alice')
                    if mutation=='transport':raise TimeoutError('synthetic unknown outcome')
                    return original(*args,**kwargs)
                models=DocumentModels(lambda:f.enabled,f.settings,transport,lambda *args:f.usage.append(args))
                f.jobs.models=models
                if mutation=='media':f.jobs.asset_bytes=Mock(side_effect=ValueError('unreadable'))
                f.start();f.run();self.assertEqual(f.clear_count,1);self.slots_free(f)
                self.assertEqual(f.assets[0]['classification_attempt']['state'],'finished')
                if mutation=='human':self.assertEqual((f.assets[0]['status'],f.assets[0]['classification_source']),('excluded','human'))
                if mutation=='delete':self.assertEqual((f.standard['status'],f.standard['classification']['state']),('deleted','cancelled'))
                if mutation=='media':self.assertEqual(len(f.usage),0);f.jobs.asset_bytes.assert_called_once()
                if mutation in {'transport','media'}:
                    self.assertEqual(f.assets[0]['status'],'needs_confirmation');previous=len(f.usage);f.start();self.assertEqual(f.tasks,[]);self.assertEqual(len(f.usage),previous)
    def test_failure_cache_claim_errors_and_worker_cleanup_order(self):
        f=Fixture();f.assets.append(dict(f.assets[0],id='duplicate',ordinal=2))
        failed=Mock(side_effect=TimeoutError('unknown'))
        f.jobs.models=DocumentModels(lambda:True,f.settings,failed,lambda *args:f.usage.append(args))
        f.start();f.run();failed.assert_called_once();self.assertEqual(len(f.usage),1)
        self.assertEqual(f.assets[1]['classification_attempt']['diagnostics']['reused_source_sha256'],'same')
        self.assertEqual(f.assets[0]['status'],'needs_confirmation');self.slots_free(f)
        f=Fixture();f.jobs.mutate=Mock(side_effect=RuntimeError('claim failed'))
        with self.assertRaises(RuntimeError):f.start()
        f.jobs.mutate.assert_called_once();self.slots_free(f)
        first,second=Fixture(),Fixture()
        first.jobs.slots.acquire();first.jobs.slots.acquire()
        self.slots_free(second);first.jobs.slots.release();first.jobs.slots.release()
        for point in ['load','claim','finish','clear']:
            with self.subTest(point=point):
                f=Fixture();f.start();order=[]
                release=f.jobs.slots.release
                f.jobs.slots.release=Mock(side_effect=lambda:(order.append('release'),release())[-1])
                original_load=f.records.load; original_mutate=f.jobs.mutate
                load=Mock(side_effect=RuntimeError('load failed')) if point=='load' else original_load
                f.jobs.records=DocumentRecords(f.records.repository,f.records.guard,f.records.owned,load,f.records.save,f.records.public)
                def mutate(identity,owner,change):
                    if point in {'claim','finish'} and change.__name__==point:raise RuntimeError('synthetic '+point)
                    return original_mutate(identity,owner,change)
                f.jobs.mutate=mutate
                def clear():
                    order.append('clear')
                    if point=='clear':raise RuntimeError('cleanup failed')
                f.jobs.clear_repository=clear
                with patch('builtins.print'):
                    if point=='clear':
                        with self.assertRaises(RuntimeError):f.run()
                    else:f.run()
                self.assertEqual(order,['clear'] if point=='clear' else ['clear','release'])
                if point in {'load','claim'}:self.assertEqual(f.calls,[])
                if point=='finish':self.assertEqual(len(f.calls),1);self.assertEqual(f.assets[0]['classification_attempt']['state'],'attempting')
                if point=='load':load.assert_called_once()
                if point=='clear':release()  # Preserve the old cleanup-failure behavior; only release the fixture.
                self.slots_free(f)
        f=Fixture();original=f.models.transport
        def replaced_attempt(*args,**kwargs):
            f.assets[0]['classification_attempt']={'id':'newer','state':'attempting'}
            f.standard['classification']['id']='newer-job'
            return original(*args,**kwargs)
        f.jobs.models=DocumentModels(lambda:True,f.settings,replaced_attempt,lambda *args:None)
        f.start();f.run()
        self.assertEqual(f.assets[0]['classification_attempt'],{'id':'newer','state':'attempting'})
        self.assertEqual(f.standard['classification']['id'],'newer-job')

    def test_stale_threshold_tombstones_and_compatibility_exports(self):
        self.assertIs(compatibility.DocumentJobs,document_jobs.DocumentJobs);self.assertIs(compatibility.register,document_api.register)
        f=Fixture();f.standard['classification']={'id':'claim','state':'processing','heartbeat':100}
        with patch.object(document_jobs.time,'time',return_value=250):f.jobs.refresh('order','alice')
        self.assertEqual(f.standard['classification']['state'],'processing')
        with patch.object(document_jobs.time,'time',return_value=250.001):f.jobs.refresh('order','alice')
        self.assertEqual(f.standard['classification']['state'],'interrupted')
        first=f.jobs.delete('order','alice');second=f.jobs.delete('order','alice');self.assertEqual(first,second)
        self.assertEqual(first['status_before_delete'],'draft');self.assertEqual(f.assets[0]['status'],'candidate')


if __name__=='__main__':unittest.main(verbosity=2)
