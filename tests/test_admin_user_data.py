"""Real PostgreSQL admin reads, purpose changes and immutable sample protections."""
import copy
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
import time
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_real_photo_feedback import database, classes, state_fixture, image
from local_inspection_service.auth.data_workbench import UserDataWorkbench, WorkbenchPorts, register
from local_inspection_service.training.real_photo_api import FeedbackService, FeedbackPorts
from local_inspection_service.training.real_photo_contracts import approved, review_key


def setup(database):
    repo=database()
    c=repo.repository._cursor()
    c.execute(f'''CREATE TABLE {repo.repository._qualified_table('agent_operation_audit')} (
        id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, created_at BIGINT NOT NULL, raw_json JSONB NOT NULL)''')
    repo.repository.connection.commit();c.close()
    state=state_fixture()
    repo.enable('a','task',classes(),{})
    values=[]
    for i in range(101):
        s=copy.deepcopy(state['samples'][i%20]);s['sample_id']=f's{i:03}';s['source_group']='group'+str(i%3)
        s['review']['key']=review_key(s,classes());values.append(s)
    repo.mutate('a','task',lambda s,c:s.update(samples=values,enabled=False))
    actor={'id':'admin','username':'admin','role':'admin'}
    users=[{'id':'a','username':'a','active':True,'role':'user'},{'id':'b','username':'b','active':False,'role':'user'}]
    tasks=[{'id':'task','owner_user_id':'a','selected_accessory_ids':['a','missing']}]
    config={'accessories':[{'id':c['class_id'],'name':c['name'],'ai_profile':c['definition']} for c in classes()]}
    def admin():
        if actor['role']!='admin':raise HTTPException(403,'forbidden')
        return actor
    feedback=FeedbackService(FeedbackPorts(repository=lambda:database().repository,user=lambda:actor,tasks=lambda:tasks,
        authorize=lambda task,user,**kw:None,config=lambda user:config,references=lambda item:['fixture.jpg'],
        read=lambda path:image(),profiles=lambda:None,legacy_state=lambda t:{}))
    service=UserDataWorkbench(WorkbenchPorts(admin=admin,auth_load=lambda:{'users':users},auth_save_user=lambda u:True,
        repository=lambda:database().repository,config=lambda:config,accessory_save=lambda *a:None,
        pipelines=lambda:[],pipeline_save=lambda t:None,pipeline_update=lambda *a:None,pipeline_pause=lambda t:None,
        training_records=lambda:[],resources=lambda **kw:{'datasets':[],'models':[]},feedback=lambda:feedback))
    app=FastAPI();register(app,service)
    return repo,actor,users,service,TestClient(app)


def test_admin_readonly_pages_and_actor_owner(database,monkeypatch):
    monkeypatch.setenv('VANTALINE_REAL_PHOTO_ACCOUNTS','a,b')
    repo,actor,users,service,client=setup(database)
    before=repo.get('a','task');jobs=repo.jobs('a','task')
    first=client.get('/api/auth/users/a/data/tasks/task/samples').json()
    assert first['total']==101 and len(first['samples'])==24
    seen=[s['sample_id'] for s in first['samples']]
    cursor=first['next_cursor']
    extra=copy.deepcopy(before['samples'][0]);extra['sample_id']='later'
    repo.mutate('a','task',lambda s,c:s['samples'].append(extra))
    while cursor:
        page=client.get('/api/auth/users/a/data/tasks/task/samples',params={'cursor':cursor}).json()
        seen.extend(s['sample_id'] for s in page['samples']);cursor=page['next_cursor']
    assert len(seen)==101==len(set(seen)) and 'later' not in seen
    result=client.get('/api/auth/users/a/data')
    assert result.status_code==200
    assert result.json()['actor']['id']=='admin' and result.json()['user']['id']=='a'
    assert len(repo.jobs('a','task'))==len(jobs)
    assert repo.get('a','task')['epoch']==before['epoch']
    assert client.get('/api/auth/users/b/data/tasks/task/samples').status_code==403
    actor['role']='user'
    assert client.get('/api/auth/users/a/data').status_code==403
    assert client.get('/api/auth/users/a/data/tasks/task/samples').status_code==403
    actor['role']='admin'
    assert actor['id']=='admin'


def test_usage_preserves_review_and_freeze(database,monkeypatch):
    monkeypatch.setenv('VANTALINE_REAL_PHOTO_ACCOUNTS','a,b')
    repo,actor,users,service,client=setup(database)
    original=repo.get('a','task')['samples'][0]
    req={'action':'image_usage','kind':'sample','resource_id':'s000','task_id':'task','enabled':False,'reason':'hold sample'}
    assert client.post('/api/auth/users/a/data/operations',json=req).status_code==200
    current=repo.get('a','task');changed=current['samples'][0]
    assert changed['review']==original['review'] and not changed['usage_enabled']
    assert len(approved(current))==100
    assert changed['usage_history'][0]['actor_user_id']=='admin'
    events=client.get('/api/auth/users/a/data').json()['audit']
    assert any(e['result']=='requested' for e in events) and any(e['result']=='succeeded' for e in events)
    assert all(e['actor_user_id']=='admin' and e['owner_user_id']=='a' for e in events)
    req['enabled']=True
    assert client.post('/api/auth/users/a/data/operations',json=req).status_code==200
    repo.mutate('a','task',lambda s,c:s.update(split_assignments={'group0':'train'}))
    req['enabled']=False
    assert client.post('/api/auth/users/a/data/operations',json=req).status_code==409
    assert repo.get('a','task')['samples'][0]['usage_enabled']
    assert client.post('/api/auth/users/b/data/operations',json=req).status_code==403


def test_legacy_readonly_pagination_and_mode_selection(database,monkeypatch):
    monkeypatch.setenv('VANTALINE_REAL_PHOTO_ACCOUNTS','a')
    repo,actor,users,service,client=setup(database)
    legacy={'owner_user_id':'a','task_id':'task','settings':{'enabled':False,'auto_promote':True},
            'samples':[{'sample_id':f'old{i:03}','owner_user_id':'a','label_status':'completed'} for i in range(101)]}
    calls=[]
    feedback=service.ports.feedback()
    feedback.ports=replace(feedback.ports,legacy_state=lambda identifier:copy.deepcopy(legacy))
    def update(identifier,request):
        calls.append((identifier,request.model_dump(exclude_unset=True)))
        legacy['settings'].update(request.model_dump(exclude_unset=True))
        return {'settings':legacy['settings']}
    service.ports=replace(service.ports,legacy_update=update,
        pipelines=lambda:[{'id':'pipe_ai_task','owner_user_id':'a','name':'linked','auto_advance':True}])
    data=client.get('/api/auth/users/a/data').json()
    assert data['tasks'][0]['control_kind']=='real_photo'
    assert data['tasks'][0]['params_locked'] and not data['tasks'][0]['control_enabled']
    assert data['legacy_feedback']==[] and not calls
    req={'kind':'legacy','action':'resume','resource_id':'task','reason':'avoid fallback'}
    assert client.post('/api/auth/users/a/data/operations',json=req).status_code==409
    assert not calls
    with repo.tx() as c:c.execute(f'DELETE FROM {repo.table("states")} WHERE owner_user_id=%s AND task_id=%s',('a','task'))
    data=client.get('/api/auth/users/a/data').json()
    assert data['tasks'][0]['control_kind']=='legacy' and data['legacy_feedback'][0]['sample_count']==101
    first=client.get('/api/auth/users/a/data/tasks/task/legacy-samples').json()
    assert first['total']==101 and len(first['samples'])==24
    legacy['samples'].insert(0,{'sample_id':'new','owner_user_id':'a','label_status':'pending'})
    seen=[s['sample_id'] for s in first['samples']];cursor=first['next_cursor']
    while cursor:
        page=client.get('/api/auth/users/a/data/tasks/task/legacy-samples',params={'cursor':cursor}).json()
        assert page['total']==101
        seen.extend(s['sample_id'] for s in page['samples']);cursor=page['next_cursor']
    assert len(seen)==len(set(seen))==101 and 'new' not in seen and not calls
    assert client.post('/api/auth/users/a/data/operations',json=req).status_code==200
    assert legacy['settings']['enabled'] and legacy['settings']['auto_promote']
    req.update(action='params',epochs=100)
    assert client.post('/api/auth/users/a/data/operations',json=req).status_code==409
    req['action']='pause'
    assert client.post('/api/auth/users/a/data/operations',json=req).status_code==200
    req['action']='params'
    assert client.post('/api/auth/users/a/data/operations',json=req).status_code==200
    assert legacy['settings']['training_epochs']==100 and legacy['settings']['auto_promote']
