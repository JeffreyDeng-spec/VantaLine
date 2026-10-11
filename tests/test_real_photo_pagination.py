"""Read-only HTTP pagination with isolated originals; no paid jobs or real media."""
import copy
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from local_inspection_service.training.real_photo_api import FeedbackService, compose
from local_inspection_service.training.real_photo_contracts import review_key


@pytest.fixture
def fixture(monkeypatch):
    monkeypatch.setenv('VANTALINE_REAL_PHOTO_ACCOUNTS', 'owner')
    classes = [{'class_id':'a', 'name':'part', 'definition':'part', 'reference_path':'fixture', 'reference_sha256':'hash'}]
    state = {'classes':classes, 'samples':[]}
    for i in range(105):
        s = {'sample_id':str(i), 'image_sha256':str(i), 'source_group':'batch', 'geometry':{'width':80,'height':60},
             'annotation':{'status':'completed', 'version':1, 'objects':[{'class_id':'a','bbox':[0,0,10,10]}], 'receipt':{'response':'PRIVATE'}}}
        decision = ['accept_positive','exclude','uncertain'][i % 3]
        s['review'] = {'key':review_key(s,classes), 'decision':decision, 'reason':'isolated reason'}
        state['samples'].append(s)
    user = {'id':'owner'}
    repo = SimpleNamespace(get=lambda owner,task: copy.deepcopy(state) if owner=='owner' else None)
    @contextmanager
    def repository():
        yield repo
    ports = SimpleNamespace(user=lambda:user, tasks=lambda:[{'id':'task','owner_user_id':'owner'}],
                            authorize=lambda *a,**k:None)
    service = FeedbackService(ports)
    service.repo = repository
    service.class_metadata = lambda *args:[{k:v for k,v in c.items() if k!='reference_sha256'} for c in classes]
    service.sync_definitions = lambda *a: pytest.fail('list cannot reconcile definitions or enqueue work')
    app = FastAPI(); compose(app,service)
    return TestClient(app), state, user, service


def test_full_pagination_remains_stable_when_new_original_arrives(fixture):
    client,state,_,_=fixture
    before=copy.deepcopy(state)
    r=client.get('/api/ai/tasks/task/real-photo/samples'); assert r.status_code==200
    first=r.json(); assert len(first['samples'])==24 and first['total']==105
    assert first['samples'][0]['sample_id']=='104'
    assert 'PRIVATE' not in r.text and 'receipt' not in r.text
    assert state==before
    state['samples'].append({**copy.deepcopy(state['samples'][-1]),'sample_id':'new'})
    seen=[s['sample_id'] for s in first['samples']]; cursor=first['next_cursor']
    while cursor:
        page=client.get('/api/ai/tasks/task/real-photo/samples',params={'cursor':cursor}).json()
        assert page['total']==105
        seen += [s['sample_id'] for s in page['samples']]; cursor=page['next_cursor']
    assert seen == [str(i) for i in range(104,-1,-1)]
    assert client.get('/api/ai/tasks/task/real-photo/samples').json()['total']==106


def test_current_filters_and_stale_reviews(fixture):
    client,state,_,_=fixture
    state['samples'][1]['annotation']['version']=2 # exclusion now stale
    state['samples'][0]['source_group_confirmed']=False
    state['samples'][3]['annotation']['status']='failed'
    filtered=client.get('/api/ai/tasks/task/real-photo/samples',params={'category':'agent_filtered'}).json()
    assert filtered['total']==69
    excluded=client.get('/api/ai/tasks/task/real-photo/samples',params={'category':'agent_filtered','decision':'exclude'}).json()
    assert excluded['total']==34 and all(s['current_status']=='exclude' for s in excluded['samples'])
    assert client.get('/api/ai/tasks/task/real-photo/samples',params={'category':'approved'}).json()['total']==33
    for sample_id,status in [('1','pending_review'),('0','unconfirmed_source'),('3','annotation_failed')]:
        result=client.get('/api/ai/tasks/task/real-photo/samples',params={'sample_id':sample_id}).json()['samples'][0]
        assert result['current_status']==status
        if sample_id=='1': assert result['review'] is None


def test_invalid_cursor_scope_and_account_isolation(fixture):
    client,_,user,_=fixture
    cursor=client.get('/api/ai/tasks/task/real-photo/samples').json()['next_cursor']
    for params in [{'cursor':'garbage'}, {'cursor':cursor,'category':'approved'}, {'limit':0}, {'limit':101},
                   {'category':'other'}, {'decision':'exclude'}]:
        assert client.get('/api/ai/tasks/task/real-photo/samples',params=params).status_code==422
    user['id']='other'
    assert client.get('/api/ai/tasks/task/real-photo/samples').status_code==403
    assert client.get('/api/ai/tasks/missing/real-photo/samples').status_code==404


def test_browsing_changed_definitions_invalidates_without_mutation(fixture):
    client,state,_,service=fixture
    service.class_metadata=lambda *a:[]
    before=copy.deepcopy(state)
    assert client.get('/api/ai/tasks/task/real-photo/samples',params={'category':'approved'}).json()['total']==0
    assert client.get('/api/ai/tasks/task/real-photo/samples',params={'category':'agent_filtered'}).json()['total']==0
    assert state==before
