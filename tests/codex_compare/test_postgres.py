"""Real PostgreSQL, random disposable schema. Never reads production DATABASE_URL."""
import concurrent.futures
import copy
import io
import os
import time
import uuid
from pathlib import Path
import psycopg
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.codex_comparisons import CodexComparisonsRepository
from local_inspection_service.storage.agent_operations import OperationConflict, OperationDenied
from local_inspection_service.codex_compare import api, worker
from local_inspection_service.codex_compare.contracts import digest

DSN = os.environ.get('CODEX_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DSN, reason='CODEX_TEST_DATABASE_URL must point to a disposable PostgreSQL database')


@pytest.fixture
def storage():
    name='codex_test_'+uuid.uuid4().hex
    with psycopg.connect(DSN) as c: c.execute(postgres_ddl(name))
    connections=[]
    def repo():
        c=psycopg.connect(DSN);connections.append(c)
        return CodexComparisonsRepository(PostgresRuntimeRepository(c,'test',name))
    yield repo
    for c in connections: c.close()
    with psycopg.connect(DSN) as c: c.execute(f'DROP SCHEMA "{name}" CASCADE')


def test_concurrent_admission_claim_and_revision(storage):
    def submit(_): return storage().create('a','request-123',{'standard':'frozen'})
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        tasks=list(pool.map(submit,range(16)))
    assert len({t['id'] for t in tasks})==1
    repo=storage();task=tasks[0]
    assert repo.get('b',task['id']) is None
    with pytest.raises(OperationConflict): repo.create('a','request-123',{'standard':'changed'})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        claims=list(pool.map(lambda _:storage().claim({'a'},'fixed','test'),range(8)))
    assert len([c for c in claims if c])==1
    active,token=next(c for c in claims if c)
    args=('a',task['id'],active['attempt_id'],token)
    entry={'id':'x','status':'uncertain','explanation':'blurry'}
    first=repo.write_report(*args,'write-001','item',entry)
    assert repo.write_report(*args,'write-001','item',entry)==first
    with pytest.raises(OperationConflict): repo.write_report(*args,'write-001','item',{**entry,'explanation':'different'})
    repo.write_report(*args,'write-002','item',{**entry,'explanation':'reread still unclear'})
    assert len([x for x in repo.events('a',task['id'],0) if x['kind']=='item'])==2
    repo.write_report(*args,'write-003','summary',{'decision':'REVIEW_REQUIRED','message':'review','checked_scope':'label','unchecked_scope':'small text'})
    repo.write_report(*args,'write-004','finalize',{})
    assert repo.get('a',task['id'])['status']=='running'
    with pytest.raises(OperationConflict): repo.write_report(*args,'write-005','progress',{'message':'late'})
    result=repo.settle('a',task['id'],active['attempt_id'],'completed')
    assert result['status']=='completed'
    with pytest.raises(OperationDenied): repo.write_report(*args,'write-006','item',entry)
    frozen=copy.deepcopy(result['summary'])
    repo.review('a',task['id'],{'decision':'DIFFERENCES','note':'human'},'review-1')
    assert repo.get('a',task['id'])['summary']==frozen
    child=repo.create('a','retry-123',result['inputs'],parent_id=task['id'])
    assert child['id']!=task['id'] and child['parent_id']==task['id']


def test_cancel_timeout_restart(storage):
    repo=storage()
    pending=repo.create('a','request-1',{})
    assert repo.cancel('a',pending['id'])['status']=='cancelled'
    assert repo.claim({'a'},'fixed','test') is None
    pending=repo.create('a','request-2',{})
    task,token=repo.claim({'a'},'fixed','test')
    repo.cancel('a',task['id'])
    with pytest.raises(OperationDenied): repo.write_report('a',task['id'],task['attempt_id'],token,'write-001','progress',{'message':'late'})
    assert repo.settle('a',task['id'],task['attempt_id'],'completed')['status']=='cancelled'
    repo.create('a','request-3',{})
    task,token=repo.claim({'a'},'fixed','test')
    with repo.tx() as c:
        task['heartbeat']=time.time()-40;task['deadline']=time.time()-1;repo.save(c,task)
    with pytest.raises(OperationDenied): repo.write_report('a',task['id'],task['attempt_id'],token,'write-002','finalize',{})
    storage().recover()
    assert repo.get('a',task['id'])['status']=='interrupted'
    assert repo.claim({'a'},'fixed','test') is None
    assert repo.settle('a',task['id'],task['attempt_id'],'completed')['status']=='interrupted'


def test_api_isolation_snapshot_and_media(storage,tmp_path,monkeypatch):
    monkeypatch.setenv('VANTALINE_CODEX_COMPARE_ACCOUNTS','a')
    monkeypatch.setenv('VANTALINE_CODEX_COMPARE_MODEL','fixed-test-model')
    buffer=io.BytesIO();Image.new('RGB',(200,100),'white').save(buffer,'PNG');data=buffer.getvalue()
    current={'owner':'a','permission':True}
    standard={'id':'s','name':'Fixture','standard_type':'label','status':'confirmed','current_revision_id':'rev-1','revision_number':1,'confirmed_assets':[{'id':'asset','sha256':digest(data)}]}
    asset={'id':'asset','standard_id':'s','sha256':digest(data)}
    def owned(kind,identifier,owner):
        if owner!='a': return None
        return copy.deepcopy(standard if kind=='standards' else asset)
    def permission(_):
        if not current['permission']:raise HTTPException(403,'no permission')
    app=FastAPI()
    api.register({'app':app,'require_permission':permission,'_text_v2_owner':lambda:(current['owner'],'test'),
                  'runtime_postgres_repository_or_none':lambda:storage().repository,'DATA_DIR':tmp_path,
                  '_text_v2_owned':owned,'_text_v2_asset_bytes':lambda *_:data})
    client=TestClient(app)
    form={'standard_asset_id':'asset','request_id':'request-123','expected_revision':'rev-1'}
    def create():return client.post(api.PREFIX+'/tasks',data=form,files={'captured_file':('a.png',data,'image/png')})
    response=create();assert response.status_code==200,response.text
    task=response.json();assert create().json()['id']==task['id']
    path=api.PREFIX+'/tasks/'+task['id']
    media=path+'/media/'+task['inputs']['reference']['image']
    assert client.get(media).status_code==200
    assert client.get(path+'/media/'+'f'*64).status_code==404
    assert 'token_hash' not in client.get(path).text and 'media_path' not in client.get(path).text
    current['owner']='b'
    assert client.get(path).status_code==404
    assert client.get(media).status_code==404
    assert client.post(path+'/cancel').status_code==404
    assert create().status_code==403
    current['owner']='a';current['permission']=False
    assert client.get(path).status_code==403
    current['permission']=True
    standard['current_revision_id']='rev-2';standard['status']='deleted'
    assert client.get(media).status_code==200
    assert client.get(path).json()['inputs']['standard_revision_id']=='rev-1'
    assert create().status_code==404
    monkeypatch.setenv('VANTALINE_CODEX_COMPARE_ACCOUNTS','')
    assert client.get(path).status_code==200
    assert client.post(path+'/cancel').json()['status']=='cancelled'
    assert client.post(path+'/retry',json={'request_id':'retry-123'}).status_code==403

@pytest.mark.parametrize('mode,expected',[('complete','completed'),('no_finalize','failed'),('crash','failed'),('timeout','timed_out'),('cancel','cancelled')])
def test_worker_and_cli_lifecycle(storage,tmp_path,monkeypatch,mode,expected):
    import sys
    import threading
    from local_inspection_service.codex_compare.media import MediaStore
    media=MediaStore(tmp_path/'media')
    buffer=io.BytesIO();Image.new('RGB',(100,100),'white').save(buffer,'PNG')
    evidence=media.image('a',buffer.getvalue())
    repo=storage();repo.create('a','worker-request',{'reference':evidence,'actual':evidence})
    task,token=repo.claim({'a'},'fixture','fixture-v1')
    if mode=='timeout':
        with repo.tx() as c:
            task['deadline']=time.time()+1;repo.save(c,task)
    auth=tmp_path/'auth';auth.mkdir();(auth/'auth.json').write_text('{"tokens":{"access_token":"test-sensitive-auth-value"}}')
    cli=Path(worker.__file__).with_name('cli.py')
    fake=tmp_path/'fake_harness.py'
    fake.write_text('''import json,os,subprocess,sys,time
from pathlib import Path
socket_path,token,cli,mode,work=sys.argv[1:]
os.environ['VANTALINE_TASK_SOCKET']=socket_path
os.environ['VANTALINE_TASK_TOKEN']=token
print(json.dumps({'type':'thread.started','thread_id':'session-fixture'}),flush=True)
def call(*args):
    result=subprocess.run([sys.executable,cli,*args],capture_output=True,text=True)
    if result.returncode: raise RuntimeError(result.stdout)
call('report','progress','--message','checking test-sensitive-auth-value')
if mode in ('timeout','cancel'):time.sleep(30)
if mode=='crash':sys.exit(2)
p=Path(work)/'item.json'
p.write_text(json.dumps({'id':'one','status':'uncertain','explanation':'unreadable'}))
call('report','item','upsert','--file',str(p))
p.write_text(json.dumps({'decision':'REVIEW_REQUIRED','message':'review','checked_scope':'label','unchecked_scope':'unreadable'}))
call('report','summary','set','--file',str(p))
if mode!='no_finalize':call('report','finalize')
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':12,'output_tokens':5}}),flush=True)
''')
    def command(directory,auth_dir,runtime,t,model,socket_path):
        # Stub replaces Codex only in this test; production has no escape flag.
        return [sys.executable,str(fake),str(socket_path),t,str(cli),mode,str(directory/'work')]
    monkeypatch.setattr(worker,'sandbox_command',command)
    monkeypatch.setattr(worker,'with_repo',lambda fn:fn(storage()))
    if mode=='cancel':
        timer=threading.Timer(.8,lambda:storage().cancel('a',task['id']));timer.start()
    worker.execute(task,token,{'work_root':str(tmp_path/'work'),'auth_home':str(auth),'model':'fixture','binary':'unused'},media)
    result=repo.get('a',task['id'])
    assert result['status']==expected
    assert result['session_id']=='session-fixture'
    assert 'test-sensitive-auth-value' not in str(repo.events('a',task['id'],0))
    assert list((tmp_path/'work').iterdir())==[]
    if mode=='complete':assert result['usage']['input_tokens']==12


def test_hard_restart_cleans_only_terminal_owned_scratch(storage,tmp_path,monkeypatch):
    repo=storage();repo.create('a','cleanup-request',{})
    task,token=repo.claim({'a'},'fixture','fixture-v1')
    work=tmp_path/'work';work.mkdir()
    own=work/'cc_owned';own.mkdir()
    (own/'owner.json').write_text(__import__('json').dumps({'id':task['id'],'owner':'a','attempt':task['attempt_id'],'socket_directory':'/not-a-task-socket'}))
    unrelated=work/'unrelated';unrelated.mkdir()
    broken=work/'cc_broken';broken.mkdir();(broken/'owner.json').write_text('{')
    monkeypatch.setattr(worker,'with_repo',lambda fn:fn(storage()))
    worker.cleanup_finished({'work_root':str(work)});assert own.exists()
    repo.settle('a',task['id'],task['attempt_id'],'interrupted')
    worker.cleanup_finished({'work_root':str(work)})
    assert not own.exists() and unrelated.exists() and broken.exists()
