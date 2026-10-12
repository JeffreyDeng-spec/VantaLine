"""Synthetic administrator photo evidence and actual admission projection; no jobs."""
import copy
import json
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from local_inspection_service.auth.dataset_photos import DatasetPhotos, register_dataset_photos
from local_inspection_service.training.real_photo_api import FeedbackService
from local_inspection_service.training.real_photo_contracts import review_key

@pytest.fixture
def fixture(monkeypatch):
    classes=[{'class_id':'a','name':'part','definition':'part','reference_path':'fixture','reference_sha256':'hash'}]
    state={'owner_user_id':'a','task_id':'task','classes':classes,'samples':[],'datasets':[],'enabled':False}
    records=[]
    for i in range(105):
        s={'sample_id':f's{i:03}', 'record_id':f'r{i:03}', 'image_sha256':str(i),'source_group':'batch', 'created_at':i,
           'geometry':{'width':80,'height':60},'annotation':{'status':'completed','version':1,'objects':[{'class_id':'a','bbox':[0,0,10,10]}], 'receipt':{'secret':'PRIVATE'}}}
        decision=['accept_positive','accept_negative','exclude','uncertain'][i%4]
        if decision=='accept_negative':s['annotation']['objects']=[]
        s['review']={'key':review_key(s,classes),'decision':decision,'reason':'safe reason','private':'PRIVATE'}
        state['samples'].append(s)
        records.append({'record_id':s['record_id'],'task_id':'task','created_at':i,'image_path':'private/original','owner_user_id':'a','raw_json':json.dumps({'task':{'name':'任务'},'secret':'PRIVATE'})})
    state['datasets']=[{'id':'d1','task_id':'task','owner_user_id':'a','sample_count':2,'samples':[{'source_sample_id':'s000','image':'private/image','split':'train','annotation_version':1},{'source_sample_id':'orphan','image':'private/image','split':'test'}]},
                       {'id':'d2','task_id':'task','sample_count':1,'samples':[{'source_sample_id':'s000','image':'private/image','split':'val'}]}]
    actor={'id':'admin','role':'admin'}; tasks=[{'id':'task','owner_user_id':'a'},{'id':'legacy','owner_user_id':'a'}]
    legacy={'owner_user_id':'a','samples':[{'sample_id':'old','record_id':'legacy-photo','label_status':'trainable'}], 'datasets':[{'id':'old-d','task_id':'legacy','samples':[{'source_sample_id':'old','source_record_id':'legacy-photo','image':'private/derived','split':'train','sample_type':'synthetic'}]}]}
    reads=[]
    class Repo:
        def _qualified_table(self,t):return t
        def _cursor(self):return Cursor()
        def _row_to_dict(self,c,r):return r
        def _end_read_transaction(self):pass
    class Cursor:
        def execute(self,sql,params):
            assert sql.startswith('SELECT') and 'owner_user_id=%s' in sql
            self.result=[r for r in records if r['owner_user_id']==params[0] and (len(params)==1 or r['record_id']==params[1])]
            self.result=sorted(self.result,key=lambda r:(r['created_at'],r['record_id']),reverse=True)
        def fetchall(self):return self.result
        def close(self):pass
    @contextmanager
    def repo(self):yield SimpleNamespace(states=lambda owners:[copy.deepcopy(state)],get=lambda owner,task:copy.deepcopy(state) if owner=='a' else None)
    monkeypatch.setattr(FeedbackService,'repo',repo)
    monkeypatch.setattr(FeedbackService,'class_metadata',lambda *a:[{k:v for k,v in c.items() if k!='reference_sha256'} for c in classes])
    monkeypatch.setattr(FeedbackService,'sync_definitions',lambda *a:pytest.fail('read cannot enqueue work'))
    def read(path):
        reads.append(path)
        from PIL import Image
        import io
        if path=='missing':raise OSError()
        stream=io.BytesIO();Image.new('RGB',(80,60),'blue').save(stream,format='PNG');return stream.getvalue()
    ports=SimpleNamespace(tasks=lambda:tasks,user=lambda:actor,authorize=lambda *a,**kw:None,legacy_state=lambda t:legacy if t=='legacy' else {},read=read)
    def target(owner):
        if actor['role']!='admin':raise HTTPException(403,'Admin required')
        if owner not in ('a','b'):raise HTTPException(404,'missing')
        return actor,{'id':owner}
    workbench=SimpleNamespace(target=target,feedback=lambda user:FeedbackService(ports,managed_owner=user),repository=lambda:Repo(),
        ports=SimpleNamespace(resources=lambda **kw:{'datasets':[{'id':'history','owner_user_id':'a','sample_count':20},{'id':'foreign','owner_user_id':'b','samples':[]}]}))
    app=FastAPI();register_dataset_photos(app,workbench)
    return TestClient(app),state,records,actor,workbench,reads,legacy

BASE='/api/auth/users/a/data'
def test_pages_anchor_classification_and_nonmutation(fixture):
    client,state,records,actor,_,reads,_=fixture
    before=copy.deepcopy(state)
    first=client.get(BASE+'/detection-photos').json()
    assert first['total']==105 and len(first['items'])==24 and first['counts']['included']==1
    assert sum(first['counts'][s] for s in ('eligible','excluded','uncertain','processing','annotation_failed','disabled','not_collected','unknown'))==105
    records.append({**records[-1],'record_id':'new','created_at':200})
    ids=[r['record_id'] for r in first['items']];cursor=first['next_cursor']
    while cursor:
        value=client.get(BASE+'/detection-photos',params={'cursor':cursor}).json()
        ids += [r['record_id'] for r in value['items']];cursor=value['next_cursor']
    assert len(ids)==len(set(ids))==105 and 'new' not in ids
    refreshed=client.get(BASE+'/detection-photos',params={'cursor':first['refresh_cursor']}).json()
    assert refreshed['items'][0]['record_id']=='r104' and refreshed['record_total']==106
    assert client.get(BASE+'/detection-photos').json()['items'][0]['record_id']=='new'
    assert state==before and not reads and actor['id']=='admin'
    assert 'PRIVATE' not in json.dumps(first) and 'private/' not in json.dumps(first)

def test_current_review_and_historical_membership(fixture):
    client,state,_,_,_,_,_=fixture
    state['samples'][0]['usage_enabled']=False
    state['samples'][2]['annotation']['version']=2
    state['samples'][4]['annotation']['status']='failed'
    state['samples'][8]['source_group_confirmed']=False
    for rid,status in [('r000','disabled'),('r002','processing'),('r004','annotation_failed'),('r008','processing'),('r003','uncertain'),('r001','eligible')]:
        value=client.get(BASE+'/detection-photos/'+rid).json();assert value['status']==status
    value=client.get(BASE+'/detection-photos/r000').json()
    assert {m['dataset_id'] for m in value['memberships']}=={'d1','d2'}
    assert client.get(BASE+'/detection-photos',params={'status':'included'}).json()['total']==1
    assert client.get(BASE+'/detection-photos/r001').json()['samples'][0]['sample_type']=='negative'
    stale=client.get(BASE+'/detection-photos/r002').json();assert stale['samples'][0]['reason']!='safe reason'

def test_dataset_orphans_legacy_and_missing_metadata(fixture):
    client,_,records,_,_,_,_=fixture
    records.extend([{'record_id':'legacy-photo','task_id':'legacy','created_at':1,'image_path':'','owner_user_id':'a','raw_json':None},
                    {'record_id':'uncollected','task_id':'other','created_at':1,'image_path':'','owner_user_id':'a','raw_json':42},
                    {'record_id':'ambiguous-duplicate','task_id':'task','created_at':1,'image_path':'','owner_user_id':'a','raw_json':{}}])
    legacy=client.get(BASE+'/detection-photos/legacy-photo').json()
    assert legacy['status']=='unknown' and legacy['memberships'][0]['dataset_id']=='old-d'
    assert client.get(BASE+'/detection-photos/uncollected').json()['status']=='not_collected'
    assert client.get(BASE+'/detection-photos/ambiguous-duplicate').json()['status']=='unknown'
    members=client.get(BASE+'/datasets/d1/members').json()
    assert members['total']==2 and any(m['sample_id']=='orphan' for m in members['items'])
    history=client.get(BASE+'/datasets/history/members').json();assert history['reason'] and not history['dataset']['members_available']
    assert client.get(BASE+'/datasets/old-d/members').json()['items'][0]['sample_type']=='synthetic'

def test_isolation_invalid_scopes_media_and_no_classification_on_images(fixture,monkeypatch):
    client,_,records,actor,_,reads,_=fixture
    cursor=client.get(BASE+'/detection-photos').json()['next_cursor']
    for params in ({'cursor':cursor,'status':'excluded'},{'cursor':'garbage'},{'status':'bad'},{'limit':101}):
        assert client.get(BASE+'/detection-photos',params=params).status_code==422
    assert client.get('/api/auth/users/b/data/detection-photos/r000').status_code==404
    assert client.get(BASE+'/datasets/foreign/members').status_code==404
    assert client.get('/api/auth/users/b/data/detection-photos',params={'cursor':cursor}).status_code==422
    assert client.get(BASE+'/datasets/d1/members',params={'cursor':cursor}).status_code==422
    monkeypatch.setattr(FeedbackService,'sample_page',lambda *a,**k:pytest.fail('thumbnail cannot scan or classify samples'))
    assert client.get(BASE+'/detection-photos/r000/image').status_code==200
    assert client.get(BASE+'/datasets/d1/members/0/image').status_code==200
    assert client.get(BASE+'/datasets/d1/members/-1/image').status_code==404
    records[0]['image_path']='missing';assert client.get(BASE+'/detection-photos/r000/image').status_code==404
    records[0]['image_path']='';records[0]['raw_json']={'image_url':'https://outside.invalid/private'}
    assert client.get(BASE+'/detection-photos/r000/image').status_code==404
    records[0]['raw_json']={'image_url':'/outputs/fixture.png'}
    assert client.get(BASE+'/detection-photos/r000/image',follow_redirects=False).headers['location']=='/outputs/fixture.png'
    actor['role']='user'
    assert client.get(BASE+'/detection-photos').status_code==403
    assert client.get(BASE+'/detection-photos/r000/image').status_code==403
    assert client.get(BASE+'/datasets/d1/members/0/image').status_code==403

def test_empty_owner_and_manifest_owner_refusal(fixture):
    client,_,_,_,_,_,_=fixture
    assert client.get('/api/auth/users/b/data/detection-photos').json()['total']==0
    assert client.get('/api/auth/users/missing/data/detection-photos').status_code==404

def test_dataset_complete_pagination(fixture):
    client,state,_,_,_,_,_=fixture
    state['datasets'][0]['samples']=[{'source_sample_id':f's{i:03}','image':'private/image','split':'train'} for i in range(105)]
    first=client.get(BASE+'/datasets/d1/members').json();assert first['total']==105
    ids=[m['id'] for m in first['items']];cursor=first['next_cursor']
    while cursor:
        result=client.get(BASE+'/datasets/d1/members',params={'cursor':cursor}).json();ids += [m['id'] for m in result['items']];cursor=result['next_cursor']
    assert len(set(ids))==len(ids)==105
