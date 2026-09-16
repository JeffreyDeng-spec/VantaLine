"""Native ASGI identity, PostgreSQL adapter and immutable history-media contracts."""
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
import io
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from local_inspection_service import comparison_history as compatibility
from local_inspection_service.text_inspection import history
from local_inspection_service.text_inspection.history_ports import HistoryAccess, HistoryRecords, HistoryMedia

PREFIX='/api/text-inspection/history'


class HistoryContracts(unittest.TestCase):
    def image(self,fmt='PNG',orientation=1):
        out=io.BytesIO();image=Image.new('RGB',(300,100),'purple')
        exif=image.getexif();exif[274]=orientation
        image.save(out,fmt,exif=exif)
        return out.getvalue()

    def fixture(self,name):
        app=FastAPI();identity=ContextVar('history-'+name,default='alice')
        state=SimpleNamespace(permission=True,events=[],queries=[],reads=[],data={},records={},pg=True)
        @app.middleware('http')
        async def bind(request,call_next):
            token=identity.set(request.headers.get('x-owner','alice'))
            try:return await call_next(request)
            finally:identity.reset(token)
        def permission(key,*,detail):
            state.events.append(('permission',key,detail))
            if not state.permission:raise HTTPException(403,detail)
        def owner():state.events.append(('owner',identity.get()));return identity.get(),'fixture'
        class Repo:
            def list_text_comparison_history(self,*args):
                state.queries.append((args,identity.get(),threading.get_ident()))
                return [{'id':name,'created_at':10,'status':'completed','decision':'MATCH',
                         'display':{},'has_source':True,'error_type':'hidden'}]
        repo=Repo()
        def repository():state.events.append(('repository',));return repo if state.pg else None
        def load(kind):raise AssertionError('PG history must not load JSON')
        def owned(kind,key,uid):
            state.events.append(('owned',kind,key,uid))
            entry=state.records.get((kind,key))
            return copy.deepcopy(entry) if entry and entry.get('owner_user_id')==uid else None
        def read(path,uid,sid,**kwargs):state.reads.append((path,uid,sid,kwargs));return state.data[path]
        def media_path(uid,sid,name):return Path(uid)/sid/name
        history.register(app,HistoryAccess(permission,owner),HistoryRecords(repository,load,owned,copy.deepcopy),HistoryMedia(media_path,read))
        self.assertEqual(state.events,[])
        state.app=app;state.client=TestClient(app,raise_server_exceptions=False);self.addCleanup(state.client.close)
        state.records['records','record']={'id':'record','owner_user_id':'alice','standard_id':'standard',
            'standard_revision_id':'old-revision','standard_asset_id':'asset','reference_sha256':'old-hash',
            'created_at':10,'status':'completed','source_path':'source.png','source_sha256':'source-hash',
            'diagnostics':{'provider':{'fixture':True},'private':'saved-evidence'}}
        state.data['source.png']=self.image()
        return state

    def test_pg_exact_arguments_and_native_concurrent_app_identity(self):
        first,second=self.fixture('first'),self.fixture('second')
        cursor=history.cursor_encode({'id':'older','created_at':12})
        def listing(state,owner):return state.client.get(PREFIX,headers={'x-owner':owner},params={'q':'  fixture  ','result':'MATCH','cursor':cursor,'limit':2})
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(listing,first,'alice');b=pool.submit(listing,second,'bob')
            self.assertEqual(a.result().json()['items'][0]['id'],'first')
            self.assertEqual(b.result().json()['items'][0]['id'],'second')
        for state,owner in [(first,'alice'),(second,'bob')]:
            self.assertEqual(len(state.queries),1)
            args,bound,_=state.queries[0]
            self.assertEqual(args,(owner,'fixture','MATCH',[12,'older'],3))
            self.assertEqual(bound,owner)
        self.assertEqual(len(first.app.routes),len(second.app.routes))

    def test_permission_filter_cursor_order_and_cross_owner_no_media_read(self):
        state=self.fixture('guard');state.permission=False
        response=state.client.get(PREFIX,params={'result':'invalid','cursor':'invalid'})
        self.assertEqual((response.status_code,response.json()),(403,{'detail':'没有文字检验权限'}))
        self.assertEqual(state.events,[('permission','inspection','没有文字检验权限')])
        state.permission=True;state.events.clear()
        response=state.client.get(PREFIX,params={'result':'invalid','cursor':'invalid'})
        self.assertEqual((response.status_code,response.json()),(400,{'detail':'无效结果筛选'}))
        self.assertEqual([event[0] for event in state.events],['permission','owner'])
        self.assertEqual(state.queries,[])
        for suffix in ['', '/diagnostics','/media/source']:
            self.assertEqual(state.client.get(PREFIX+'/record'+suffix,headers={'x-owner':'bob'}).status_code,404)
        self.assertEqual(state.reads,[])
        response=state.client.get(PREFIX+'/record/diagnostics')
        self.assertEqual(response.json()['private'],'saved-evidence')

    def test_reference_overlay_priority_and_fixed_revision_hash_checks(self):
        state=self.fixture('reference');record=state.records['records','record']
        record.update(reference_overlay_path='overlay.png',reference_overlay_sha256='overlay-hash')
        state.data['overlay.png']=self.image()
        response=state.client.get(PREFIX+'/record/media/reference')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(state.reads,[('overlay.png','alice','standard',{'expected_sha256':'overlay-hash'})])
        self.assertFalse(any(event[0]=='owned' and event[1]=='revisions' for event in state.events))
        record.pop('reference_overlay_path');state.reads.clear()
        revision={'id':'old-revision','standard_id':'standard','owner_user_id':'alice',
                  'confirmed_assets':[{'id':'asset','sha256':'snapshot-hash','preparation':{'id':'p1','sha256':'wrong'}}]}
        state.records['revisions','old-revision']=revision
        self.assertEqual(state.client.get(PREFIX+'/record/media/reference').status_code,409)
        self.assertEqual(state.reads,[])
        preparation=revision['confirmed_assets'][0]['preparation'];preparation['sha256']='old-hash'
        path=str(Path('alice')/'standard'/'preparation_p1_clean.png');state.data[path]=self.image()
        self.assertEqual(state.client.get(PREFIX+'/record/media/reference').status_code,200)
        self.assertEqual(state.reads[-1],(path,'alice','standard',{'expected_sha256':'old-hash'}))
        revision['confirmed_assets'][0].pop('preparation');state.reads.clear()
        state.records['assets','asset']={'id':'asset','owner_user_id':'alice','standard_id':'standard','sha256':'new-hash','media_path':'source.png'}
        self.assertEqual(state.client.get(PREFIX+'/record/media/reference').status_code,404)
        self.assertEqual(state.reads,[])

    def test_source_bytes_exif_and_saved_preview_precedence(self):
        state=self.fixture('media');record=state.records['records','record']
        for fmt,orientation in [('PNG',1),('JPEG',1),('JPEG',6)]:
            data=self.image(fmt,orientation);state.data['source.png']=data
            response=state.client.get(PREFIX+'/record/media/source')
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.headers['cache-control'],'private, no-store')
            self.assertEqual(response.headers['x-content-type-options'],'nosniff')
            if orientation==1:self.assertEqual(response.content,data)
            else:
                self.assertTrue(response.content.startswith(b'\x89PNG'))
                with Image.open(io.BytesIO(response.content)) as rotated:self.assertEqual(rotated.size,(100,300))
        record.update(source_preview_path='saved-preview.jpg',source_preview_sha256='preview-hash')
        state.data['saved-preview.jpg']=self.image('JPEG')
        self.assertEqual(state.client.get(PREFIX+'/record/media/preview').content,state.data['saved-preview.jpg'])
        response=state.client.get(PREFIX+'/record/media/thumbnail')
        with Image.open(io.BytesIO(response.content)) as thumb:self.assertLessEqual(max(thumb.size),240)
        self.assertEqual(state.reads[-1],('saved-preview.jpg','alice','standard',{'expected_sha256':'preview-hash'}))
        before=len(state.reads)
        self.assertEqual(state.client.get(PREFIX+'/record/media/unknown').status_code,404)
        self.assertEqual(len(state.reads),before)

    def test_compatibility_cursor_and_state_boundaries(self):
        for name in ['display_snapshot','project','state','cursor_encode','cursor_decode','register']:
            self.assertIs(getattr(compatibility,name),getattr(history,name))
        def cursor(pair):return base64.urlsafe_b64encode(json.dumps(pair).encode()).decode()
        self.assertEqual(history.cursor_decode(cursor([1,'x'*128])),[1,'x'*128])
        for pair in [[True,'id'],[1.0,'id'],[1,'x'*129],[1,2]]:
            with self.assertRaises(HTTPException):history.cursor_decode(cursor(pair))
        with patch.object(history.time,'time',return_value=130):
            self.assertEqual(history.state({'status':'attempting','created_at':10},now=0),'processing')
            self.assertEqual(history.state({'status':'attempting','created_at':9},now=0),'timeout')


if __name__=='__main__':unittest.main()
