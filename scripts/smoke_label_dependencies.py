"""Isolated label ports, identity, binding and actual registrar lifecycle contracts."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from local_inspection_service.label_inspection import api, model, worker, pdf_import
from local_inspection_service.label_inspection.dependencies import (
    LabelAccess, RepositoryLifecycle, LabelImports, require_models,
)


class Models:
    def __init__(self,name,enabled=True):
        self.name,self.enabled=name,enabled
        self.calls=[]
        self.reference={'id':name,'version':7,'secret_ref':'fixture-secret-version'}
        self.legacy={'id':name,'version':1}
    def snapshot(self):
        self.calls.append(('snapshot',))
        return {'label':self.reference}
    def snapshot_for_record(self,record):
        self.calls.append(('snapshot_for_record',record))
        return {'label':self.legacy}
    def resolve(self,*args):
        self.calls.append(('resolve',args))
        return {'configured':self.enabled,'model':self.name,'api_key':'fixture-key-'+self.name,'provider':'doubao'}
    def record_call(self,*args):self.calls.append(('record_call',args))


def fake_threads():
    events,threads=[],[]
    class Event:
        def __init__(self):
            self.stopped=False
            self.waits=[]
            events.append(self)
        def is_set(self):return self.stopped
        def set(self):self.stopped=True
        def clear(self):self.stopped=False
        def wait(self,seconds):
            self.waits.append(seconds)
            self.set()
    class Thread:
        def __init__(self,*,target,name,daemon):
            self.target,self.name,self.daemon=target,name,daemon
        def start(self):threads.append(self)
    return SimpleNamespace(Event=Event,Thread=Thread,events=events,threads=threads)


class LabelDependencyContracts(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='label-ports-')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.environment=patch.dict(os.environ,{'VANTALINE_LABEL_INSPECTION_ENABLED':'true'})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def fixture(self,name,enabled=True):
        app=FastAPI()
        identity=ContextVar('identity-'+name,default='unset')
        models=Models(name,enabled)
        state=SimpleNamespace(models=models,prior=None,opens=[],submissions=[],permissions=[])
        @app.middleware('http')
        async def bind(request,call_next):
            token=identity.set(request.headers.get('x-owner','owner-'+name))
            try:return await call_next(request)
            finally:identity.reset(token)
        class Repository:
            def get(self,owner,identifier,kind):
                return {'id':identifier,'source':{'type':'word'}}
            def request_run(self,owner,request_id):return state.prior
            def submit(self,*args,**kwargs):
                state.submissions.append((args,kwargs,identity.get(),threading.get_ident()))
                return {'id':'fixture-run','kind':'run','status':'queued'}
        repo=Repository()
        def open_repository():
            state.opens.append((identity.get(),threading.get_ident()))
            return repo
        def unused(*args,**kwargs):raise AssertionError('unused fixture dependency')
        access=LabelAccess(lambda permission:state.permissions.append((permission,identity.get())),unused,lambda:(identity.get(),'fixture'))
        lifecycle=RepositoryLifecycle(open_repository,unused)
        imports=LabelImports(lambda:self.root/name,unused,unused,unused,unused)
        api.register(app,access,lifecycle,imports,lambda:state.models,lambda:model.settings(lambda:state.models))
        state.client=TestClient(app,raise_server_exceptions=False)
        self.addCleanup(state.client.close)
        state.app=app
        return state

    def submit(self,state,request_id='fixture-request',owner='fixture-owner'):
        image=io.BytesIO()
        Image.new('RGB',(30,40),'red').save(image,'PNG')
        return state.client.post(api.PREFIX+'/tasks/task/runs',headers={'x-owner':owner},
            data={'request_id':request_id,'revision':'1','asset_id':'asset'},files={'file':('actual.png',image.getvalue(),'image/png')})

    def test_two_apps_settings_identity_and_async_thread_repositories(self):
        with patch.object(api,'LabelRepository',side_effect=lambda raw:raw):
            first,second=self.fixture('first'),self.fixture('second',False)
            for state,enabled in [(first,True),(second,False),(first,True)]:
                response=state.client.get(api.PREFIX+'/capabilities')
                self.assertEqual((response.status_code,response.json()),(200,{'enabled':enabled}))
            self.assertEqual(self.submit(second).status_code,503)
            self.assertEqual(second.submissions,[])
            second.models.enabled=True
            first.opens.clear();second.opens.clear()
            with ThreadPoolExecutor(max_workers=2) as pool:
                a=pool.submit(self.submit,first,'request-first','alice')
                b=pool.submit(self.submit,second,'request-second','bob')
                self.assertEqual(a.result().status_code,200)
                self.assertEqual(b.result().status_code,200)
            for state,owner,name in [(first,'alice','first'),(second,'bob','second')]:
                self.assertEqual([value[0] for value in state.opens],[owner,owner])
                self.assertNotEqual(state.opens[0][1],state.opens[1][1])
                args,kwargs,bound_owner,thread=state.submissions[-1]
                self.assertEqual((args[0],bound_owner,args[6]),(owner,owner,name))
                self.assertEqual(kwargs['profile_snapshot'],state.models.reference)
                self.assertEqual(thread,state.opens[1][1])
            self.assertEqual(len(first.app.routes),len(second.app.routes))
        self.assertNotIn('local_inspection_service.server',sys.modules)

    def test_prior_none_binding_and_late_provider_replacement(self):
        with patch.object(api,'LabelRepository',side_effect=lambda raw:raw):
            state=self.fixture('initial')
            replacement=Models('replacement')
            state.models=replacement
            for reference in [None,{}, {'id':'old-model','version':2,'secret_ref':'old-secret'}]:
                state.prior={'id':'prior','profile_snapshot':reference}
                replacement.calls.clear()
                response=self.submit(state)
                self.assertEqual(response.status_code,200,response.text)
                self.assertFalse(any(call[0]=='snapshot' for call in replacement.calls))
                self.assertEqual(replacement.calls[-1],('resolve',('label',reference)))
                self.assertIs(state.submissions[-1][1]['profile_snapshot'],reference)
            state.models=None
            self.assertEqual(self.submit(state).status_code,500)
            self.assertEqual(len(state.submissions),3)

    def test_settings_resolves_omitted_reference_even_when_disabled(self):
        models=Models('settings')
        os.environ['VANTALINE_LABEL_INSPECTION_ENABLED']='false'
        result=model.settings(lambda:models)
        self.assertFalse(result['enabled'])
        self.assertEqual(result['key'],'fixture-key-settings')
        self.assertEqual(models.calls,[('resolve',('label',))])
        with self.assertRaisesRegex(RuntimeError,'Label model profile resolver is not configured'):
            model.settings(lambda:None)

    def test_registration_order_no_eager_dependencies_and_independent_stops(self):
        fake=fake_threads()
        with patch.object(worker,'threading',fake),patch.object(pdf_import,'threading',fake):
            first,second=self.fixture('one'),self.fixture('two')
            self.assertEqual(fake.threads,[])
            self.assertEqual(first.opens+second.opens,[])
            self.assertEqual(first.models.calls+second.models.calls,[])
            for state in [first,second]:
                for callback in state.app.router.on_startup:callback()
            self.assertEqual([thread.name for thread in fake.threads],
                ['pdf-import','label-inspection-0','label-inspection-1']*2)
            self.assertTrue(all(thread.daemon for thread in fake.threads))
            for callback in first.app.router.on_shutdown:callback()
            self.assertEqual([event.stopped for event in fake.events],[True,True,False,False])
            for callback in second.app.router.on_shutdown:callback()
            self.assertTrue(all(event.stopped for event in fake.events))

    def worker_iteration(self,reference,*,error=None,enabled=True,legacy=True,missing=False):
        fake=fake_threads();events=[];app=FastAPI()
        run={'id':'run','owner_user_id':'alice','profile_snapshot':reference}
        initial=Models('initial')
        state=SimpleNamespace(models=initial)
        def fail(stage):
            if error==stage:raise RuntimeError('synthetic '+stage+' failure')
        def claim():
            events.append('claim');fail('claim')
            return None if error=='idle' else run
        repo=SimpleNamespace(claim=claim)
        def repository():
            events.append('repository');fail('repository');return repo
        def provider():
            events.append('models');fail('models');return state.models
        def clear():
            events.append('clear');fake.events[0].set()
        def process(*args,**kwargs):
            events.append('process');fail('process')
        with patch.object(worker,'threading',fake),patch.object(worker,'LabelRepository',side_effect=lambda raw:raw), \
             patch.object(worker,'process',side_effect=process) as invoked, \
             patch.dict(os.environ,{'VANTALINE_LABEL_INSPECTION_ENABLED':str(enabled).lower()}):
            worker.register(app,RepositoryLifecycle(repository,clear),lambda:self.root,provider)
            self.assertEqual(events,[])
            replacement=Models('replacement')
            if not legacy:replacement.legacy=None
            if error=='resolve':
                def resolve(*args):raise RuntimeError('synthetic missing version')
                replacement.resolve=resolve
            if error=='snapshot_for_record':
                def snapshot(record):raise RuntimeError('synthetic legacy snapshot failure')
                replacement.snapshot_for_record=snapshot
            state.models=None if missing else replacement
            for callback in app.router.on_startup:callback()
            self.assertEqual(len(fake.threads),2)
            fake.threads[0].target()
            self.assertTrue(fake.events[0].is_set())
            self.assertEqual(events[-1],'clear')
            self.assertEqual(initial.calls,[])
            return run,replacement,events,invoked,fake.events[0].waits

    def test_worker_bindings_and_late_resolver_forwarding(self):
        reference={'id':'bound','version':3,'secret_ref':'old-secret'}
        for bound,legacy in [(reference,True),({},True),(None,True),(None,False)]:
            with self.subTest(bound=bound,legacy=legacy):
                run,models,events,invoked,waits=self.worker_iteration(bound,legacy=legacy)
                invoked.assert_called_once()
                args,kwargs=invoked.call_args
                self.assertIs(args[2],run)
                selected=bound or models.legacy
                if selected:
                    self.assertEqual(args[3],'fixture-key-replacement')
                    self.assertEqual(kwargs['resolved']['model'],'replacement')
                    self.assertIn(('resolve',('label',selected)),models.calls)
                else:
                    self.assertEqual(args[3],'')
                    self.assertIsNone(kwargs['resolved'])
                    self.assertFalse(any(call[0]=='resolve' for call in models.calls))
                self.assertIs(kwargs['record_call'].__self__,models)
                self.assertEqual(any(call[0]=='snapshot_for_record' for call in models.calls),not bool(bound))
                self.assertEqual(events.count('claim'),1)
                self.assertEqual(events[-2:],['process','clear'])
                self.assertEqual(waits,[])

    def test_worker_cleanup_on_disabled_idle_and_each_failure(self):
        bound={'id':'old','version':2}
        for error in ['repository','claim','models','process','idle']:
            with self.subTest(error=error):
                _,_,events,invoked,waits=self.worker_iteration(bound,error=error)
                self.assertEqual(events.count('clear'),1)
                self.assertLessEqual(events.count('claim'),1)
                self.assertEqual(invoked.call_count,int(error=='process'))
                self.assertEqual(waits,[1] if error in {'repository','claim','idle'} else [])
        for error,reference in [('resolve',bound),('snapshot_for_record',None),('snapshot_for_record',{})]:
            with self.subTest(error=error,reference=reference):
                _,_,events,invoked,waits=self.worker_iteration(reference,error=error)
                invoked.assert_not_called()
                self.assertEqual(events.count('claim'),1)
                self.assertEqual(events.count('clear'),1)
                self.assertEqual(waits,[])
        _,_,events,invoked,waits=self.worker_iteration(bound,enabled=False)
        self.assertEqual((events,waits),(['clear'],[1]))
        invoked.assert_not_called()
        for reference in [bound,None]:
            _,_,events,invoked,waits=self.worker_iteration(reference,missing=True)
            invoked.assert_not_called()
            self.assertEqual(events.count('claim'),1)
            self.assertEqual(events.count('clear'),1)
            self.assertEqual(waits,[])

    def test_pdf_loop_token_cleanup_and_two_second_wait(self):
        for error in [None,'repository','claim','process','idle']:
            with self.subTest(error=error):
                fake=fake_threads();events=[];tokens=[];app=FastAPI();task={'id':'pdf-task'}
                def fail(stage):
                    if error==stage:raise RuntimeError('synthetic '+stage+' failure')
                def claim(token):
                    events.append('claim');tokens.append(token);fail('claim')
                    return None if error=='idle' else task
                repo=SimpleNamespace(claim_pdf=claim)
                def repository():
                    events.append('repository');fail('repository');return repo
                def clear():events.append('clear');fake.events[0].set()
                def process(*args):events.append('process');fail('process')
                with patch.object(pdf_import,'threading',fake),patch.object(pdf_import,'LabelRepository',side_effect=lambda raw:raw), \
                     patch.object(pdf_import,'process',side_effect=process) as invoked, \
                     patch.dict(os.environ,{'VANTALINE_LABEL_INSPECTION_ENABLED':'false'}):
                    pdf_import.register(app,RepositoryLifecycle(repository,clear),lambda:self.root)
                    self.assertEqual(events,[])
                    for callback in app.router.on_startup:callback()
                    self.assertEqual([thread.name for thread in fake.threads],['pdf-import'])
                    fake.threads[0].target()
                    self.assertEqual(events[-1],'clear')
                    self.assertEqual(events.count('clear'),1)
                    self.assertEqual(invoked.call_count,int(error in {None,'process'}))
                    if invoked.call_count:
                        self.assertIs(invoked.call_args.args[2],task)
                        self.assertEqual(invoked.call_args.args[3],tokens[0])
                    self.assertEqual(fake.events[0].waits,[] if error is None else [2])


if __name__=='__main__':unittest.main()
