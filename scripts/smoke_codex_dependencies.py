"""Codex API composition, dynamic configuration and pure-contract compatibility."""
import asyncio
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
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from local_inspection_service.codex_compare import api, batch_api, contracts, validation
from local_inspection_service.codex_compare.dependencies import ComparisonAccess, StandardLibrary, ComparisonMedia, DocumentImports
from local_inspection_service.schemas import codex_compare as schemas


class CodexDependencyContracts(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='codex-ports-')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        env=patch.dict(os.environ,{'VANTALINE_CODEX_COMPARE_ACCOUNTS':'alice,bob','VANTALINE_CODEX_COMPARE_MODEL':'fixture-model'})
        env.start();self.addCleanup(env.stop)
        image=io.BytesIO();Image.new('RGB',(60,80),'white').save(image,'PNG');self.data=image.getvalue()

    def fixture(self,name):
        app=FastAPI();identity=ContextVar('codex-'+name,default='alice')
        state=SimpleNamespace(permission=True,available=True,events=[],opens=[],requests=[],saved=[],tasks={},references=[])
        @app.middleware('http')
        async def bind(request,call_next):
            token=identity.set(request.headers.get('x-owner','alice'))
            state.requests.append((identity.get(),threading.get_ident()))
            try:return await call_next(request)
            finally:identity.reset(token)
        class Repository:
            def create(self,owner,request_id,inputs,**kwargs):
                state.saved.append((owner,request_id,inputs,kwargs,identity.get(),threading.get_ident()))
                task={'id':'task-'+name,'status':'queued','inputs':inputs,'summary':{},'items':{},'checks':{},
                      'elements':{},'issues':{},'decodes':{},'artifacts':{},'reviews':[],**kwargs}
                state.tasks[task['id']]=(owner,task)
                return task
            def get(self,owner,identifier):
                entry=state.tasks.get(identifier)
                return entry[1] if entry and entry[0]==owner else None
            def cancel(self,owner,identifier):
                task=self.get(owner,identifier);task['status']='cancelled';return task
        repo=Repository()
        def repository():
            state.events.append('repository');state.opens.append((identity.get(),threading.get_ident()))
            return repo if state.available else None
        def permission(value):
            state.events.append('permission')
            if not state.permission:raise HTTPException(403,'fixture permission denied')
        def owned(kind,identifier,owner):
            state.events.append('owned')
            if kind=='assets':return {'id':'asset','standard_id':'standard','sha256':'outdated-current-value'}
            return {'id':'standard','name':'Fixture','standard_type':'label','status':'confirmed',
                    'current_revision_id':'revision','confirmed_assets':[{'id':'asset','sha256':contracts.digest(self.data)}]}
        def asset_bytes(asset,owner):
            state.references.append((asset,owner));return self.data
        def unused(*args,**kwargs):raise AssertionError('unexpected document write or extraction')
        api.register(app,ComparisonAccess(permission,lambda:(identity.get(),'fixture-'+name)),repository,
                     StandardLibrary(owned,unused,unused),
                     ComparisonMedia(lambda:self.root/name,asset_bytes,unused,unused),DocumentImports(unused,unused))
        self.assertEqual(state.events,[])
        state.client=TestClient(app,raise_server_exceptions=False)
        self.addCleanup(state.client.close);state.app=app
        return state

    def create(self,state,owner):
        return state.client.post(api.PREFIX+'/tasks',headers={'x-owner':owner},
            data={'standard_asset_id':'asset','request_id':'request-'+owner,'expected_revision':'revision'},
            files={'captured_file':('actual.png',self.data,'image/png')})

    def test_two_apps_concurrent_identity_repositories_and_frozen_source(self):
        with patch.object(api,'CodexComparisonsRepository',side_effect=lambda raw:raw):
            first,second=self.fixture('first'),self.fixture('second')
            with ThreadPoolExecutor(max_workers=2) as pool:
                a=pool.submit(self.create,first,'alice');b=pool.submit(self.create,second,'bob')
                self.assertEqual(a.result().status_code,200)
                self.assertEqual(b.result().status_code,200)
            for state,owner in [(first,'alice'),(second,'bob')]:
                self.assertEqual(len(state.opens),1)
                self.assertEqual(state.opens[0][0],owner)
                self.assertNotEqual(state.opens[0][1],state.requests[0][1])
                self.assertEqual(state.saved[0][0],owner)
                self.assertEqual(state.saved[0][4:],(owner,state.opens[0][1]))
                self.assertEqual(state.references[0][0]['sha256'],contracts.digest(self.data))
                self.assertEqual(state.references[0][1],owner)
            self.assertEqual(len(first.app.routes),len(second.app.routes))
        self.assertNotIn('local_inspection_service.server',sys.modules)

    def test_capabilities_without_database_and_dynamic_owner_model_flags(self):
        with patch.object(api,'CodexComparisonsRepository',side_effect=lambda raw:raw):
            state=self.fixture('flags');state.available=False
            response=state.client.get(api.PREFIX+'/capabilities')
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.json()['enabled'])
            self.assertEqual(state.opens,[])
            self.assertEqual(state.client.get(api.PREFIX+'/tasks').status_code,503)
            state.available=True
            created=self.create(state,'alice');self.assertEqual(created.status_code,200,created.text)
            path=api.PREFIX+'/tasks/'+created.json()['id']
            os.environ['VANTALINE_CODEX_COMPARE_ACCOUNTS']='bob'
            self.assertFalse(state.client.get(api.PREFIX+'/capabilities').json()['enabled'])
            self.assertEqual(state.client.get(path).status_code,200)
            self.assertEqual(state.client.post(path+'/cancel').status_code,200)
            self.assertEqual(state.client.post(path+'/retry',json={'request_id':'retry-001'}).status_code,403)
            os.environ['VANTALINE_CODEX_COMPARE_ACCOUNTS']='alice'
            os.environ['VANTALINE_CODEX_COMPARE_MODEL']=''
            self.assertFalse(state.client.get(api.PREFIX+'/capabilities').json()['enabled'])
            self.assertEqual(self.create(state,'alice').status_code,503)
            state.permission=False
            self.assertEqual(state.client.get(api.PREFIX+'/capabilities').status_code,403)

    def test_upload_read_vs_permission_order_is_endpoint_specific(self):
        with patch.object(api,'CodexComparisonsRepository',side_effect=lambda raw:raw):
            state=self.fixture('ordering');state.permission=False
            class Upload:
                filename='fixture.docx'
                async def read(self,limit):state.events.append('read');return b'fixture'
            def endpoint(path):return next(route.endpoint for route in state.app.routes if getattr(route,'path','')==api.PREFIX+path and 'POST' in getattr(route,'methods',set()))
            state.events.clear()
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(endpoint('/tasks')(captured_file=Upload(),standard_asset_id='asset',request_id='request-1',expected_revision='revision'))
            self.assertEqual(caught.exception.status_code,403)
            self.assertEqual(state.events,['read','permission'])
            for suffix in ['document','photos']:
                state.events.clear()
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(endpoint('/batches/{bid}/'+suffix)(bid='fixture',file=Upload(),request_id='request-1'))
                self.assertEqual(caught.exception.status_code,403)
                self.assertEqual(state.events,['permission'])

    def test_validation_and_request_exports_preserve_exact_values(self):
        for name in ['text','box','summary','DECISIONS']:
            self.assertIs(getattr(contracts,name),getattr(validation,name))
        for name in ['Retry','Review']:self.assertIs(getattr(api,name),getattr(schemas,name))
        for name in ['Retry','Review','SelectOrder','Rename','Rerun']:self.assertIs(getattr(batch_api,name),getattr(schemas,name))
        value=[0,0,1,1];self.assertIs(contracts.box(value),value)
        for value in [[False,0,1,1],[0,0,float('nan'),1],[0,0,float('inf'),1],[0,0,1.01,1]]:
            with self.assertRaises(ValueError):contracts.box(value)
        self.assertEqual(contracts.text(' keep spaces '),' keep spaces ')
        summary={'decision':'MATCH','message':' keep ','checked_scope':' all ','unchecked_scope':''}
        self.assertEqual(contracts.summary(summary),summary)
        with self.assertRaises(ValueError):contracts.summary({**summary,'extra':True})
        self.assertEqual(schemas.Rerun(request_id='request-1',label_ids=['label']).matches,{})
        self.assertIsNot(schemas.Rerun(request_id='request-1',label_ids=['label']).matches,
                         schemas.Rerun(request_id='request-2',label_ids=['label']).matches)


if __name__=='__main__':unittest.main()
