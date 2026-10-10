"""Provider fixtures and real PostgreSQL cache fences; no paid calls or quality claim."""
import concurrent.futures
import copy
import json
import time
import pytest
from test_real_photo_feedback import classes, database, image
from local_inspection_service.training.real_photo_cache import (
    annotate_cached, cache_key, create_prefix, schedule_cache, usable)
from local_inspection_service.training.real_photo_contracts import MODEL
from local_inspection_service.training.real_photo_workflow import apply_result, schedule

SETTINGS={'provider':'doubao','model':MODEL,'configured':True}


def cached():
    return {'key':'fixture','response_id':'resp_prefix','expires_at':int(time.time())+3600,'references':[]}


def answer(objects=None):
    return {'model':MODEL,'status':'completed','id':'resp_new_photo','output':[
        {'type':'message','role':'assistant','status':'completed','content':[
            {'type':'output_text','text':json.dumps({'objects':objects or []})}]}],
        'usage':{'input_tokens':1000,'output_tokens':30,'input_tokens_details':{'cached_tokens':800}}}


def test_prefix_and_two_photos_upload_references_once_and_never_chain_answers():
    calls=[]
    def provider(body,settings):
        calls.append(body)
        if body.get('caching',{}).get('prefix'):
            return 200,json.dumps({'model':MODEL,'status':'completed','id':'resp_prefix',
                                  'expire_at':body['expire_at'],'usage':{'input_tokens':800,'output_tokens':0}})
        return 200,json.dumps(answer([{'class_id':'a','bbox':[0,0,500,1000]}]))
    prefix=create_prefix(classes(),SETTINGS,lambda c:image(),provider)
    cache={**prefix,'key':'fixture'}
    first=annotate_cached(image(),classes(),cache,SETTINGS,lambda c:image(),provider)
    second=annotate_cached(image(),classes(),cache,SETTINGS,lambda c:image(),provider)
    assert first['status']==second['status']=='completed'
    assert first['objects'][0]['bbox']==[0,0,40,60]
    assert len(calls)==3
    assert len([p for p in calls[0]['input'][0]['content'] if p['type']=='input_image'])==2
    for call in calls[1:]:
        assert call['previous_response_id']=='resp_prefix'
        assert len([p for p in call['input'][0]['content'] if p['type']=='input_image'])==1
        assert 'reference_path' not in json.dumps(call) and 'visible part' not in json.dumps(call)
        assert call['max_output_tokens']==4096 and call['temperature']==0
        assert call['expire_at']==prefix['expires_at']  # No sliding or default three-day storage.
    assert first['receipt']['uploaded_image_count']==1
    assert first['receipt']['usage']['input_tokens_details']['cached_tokens']==800


@pytest.mark.parametrize('mode',['unknown','truncated','refusal','broken','model','http','extra','reasoning'])
def test_strict_responses_failure_has_no_replay(mode):
    calls=[];value=answer()
    if mode=='unknown':value=answer([{'class_id':'not-task','bbox':[0,0,10,10]}])
    if mode=='truncated':value['status']='incomplete'
    if mode=='refusal':value['output'][0]['content']=[{'type':'refusal','refusal':'no'}]
    if mode=='broken':value['output'][0]['content'][0]['text']='{'
    if mode=='model':value['model']='other'
    if mode=='extra':value['output'][0]['content'][0]['text']='{"objects":[],"extra":1}'
    if mode=='reasoning':value['output'].insert(0,{'type':'reasoning'})
    def provider(body,settings):calls.append(body);return (503 if mode=='http' else 200),json.dumps(value)
    result=annotate_cached(image(),classes(),cached(),SETTINGS,lambda c:image(),provider)
    assert len(calls)==1 and result['status']=='failed' and not result['objects']
    assert result['receipt']['usage']['output_tokens']==30


def test_changed_reference_and_known_expiration_never_send_paid_request():
    calls=[]
    for cache,reader in (({**cached(),'expires_at':time.time()+60},lambda c:image()),(cached(),lambda c:b'changed')):
        with pytest.raises(ValueError):annotate_cached(image(),classes(),cache,SETTINGS,reader,lambda *a:calls.append(a))
    assert not calls


def test_safe_nested_connection_timeout_diagnostics():
    from requests.exceptions import ConnectionError
    from urllib3.exceptions import ReadTimeoutError
    calls=[]
    def provider(*args):calls.append(1);raise ConnectionError(ReadTimeoutError(None,'PRIVATE_URL','SECRET'))
    result=annotate_cached(image(),classes(),cached(),SETTINGS,lambda c:image(),provider)
    assert calls==[1] and result['receipt']['failure_types']==['ConnectionError','ReadTimeoutError']
    assert 'SECRET' not in json.dumps(result) and 'PRIVATE_URL' not in json.dumps(result)


def initialized(database):
    repo=database();repo.enable('a','task',classes(),{'bbox_annotation':{'id':'fixed','version':1}})
    job,token=repo.claim({'a'},{'initialize'},'gpt-6-astra','fixture')
    repo.finish(job['id'],token,{'review_trigger':20,'approved_real_target':20,'reason':'first cohort'},
                lambda s,j,c:apply_result(repo,s,j,c))
    repo.capture('a','task',{'sample_id':'one','image_sha256':'one','source_path':'original','geometry':{'width':80,'height':60}})
    return repo


def publish(repo,job,token):
    result={**cached(),'status':'completed'}
    repo.receipt(job['id'],job['attempt_id'],{'external_call_started':True,'usage':{'input_tokens':800,'output_tokens':0}})
    repo.finish(job['id'],token,result,lambda s,j,c:apply_result(repo,s,j,c))


def test_postgres_single_prefix_claim_reuse_and_billing(database):
    repo=initialized(database)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _:schedule(database(),'a','task'),range(8)))
    assert len([j for j in repo.jobs('a','task') if j['kind']=='reference_cache'])==1
    assert repo.claim({'a'},{'annotate'},'model','fixture') is None
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        claims=list(pool.map(lambda _:database().claim({'a'},{'reference_cache'},'model','fixture'),range(4)))
    assert sum(x is not None for x in claims)==1
    job,token=next(x for x in claims if x);publish(repo,job,token)
    annotation,token=repo.claim({'a'},{'annotate'},'model','fixture')
    assert annotation['reference_cache']['response_id']=='resp_prefix'
    result={'status':'completed','objects':[],'receipt':{'usage':answer()['usage']}}
    repo.receipt(annotation['id'],annotation['attempt_id'],{'external_call_started':True,'usage':answer()['usage']})
    repo.finish(annotation['id'],token,result,lambda s,j,c:apply_result(repo,s,j,c))
    assert repo.get('a','task')['reference_cache']['response_id']=='resp_prefix'
    stats=repo.statistics('a','task')
    assert stats['doubao']['usage']['cached_tokens']==800
    assert stats['doubao_reference_cache']['attempts']==1
    assert stats['doubao']['estimated_cost'] is None
    schedule(repo,'a','task');assert len(repo.jobs('a','task'))==3


def test_postgres_expiration_only_refreshes_with_pending_work_and_key_isolation(database):
    repo=initialized(database);schedule(repo,'a','task')
    job,token=repo.claim({'a'},{'reference_cache'},'model','fixture');publish(repo,job,token)
    state=repo.get('a','task');assert usable(state)
    for changes in ({'owner_user_id':'b'},{'task_id':'other'},{'profiles':{}},{'classes':list(reversed(classes()))}):
        assert cache_key({**state,**changes})!=cache_key(state)
    repo.mutate('a','task',lambda s,c:s['reference_cache'].update(expires_at=time.time()+60))
    assert repo.claim({'a'},{'annotate'},'model','fixture') is None
    schedule(repo,'a','task')
    assert len([j for j in repo.jobs('a','task') if j['kind']=='reference_cache'])==2
    assert repo.get('a','task')['reference_cache']['generation']==2


@pytest.mark.parametrize('uncertain',[False,True])
def test_postgres_failed_uncertain_prefix_does_not_replay_and_revokes_late_result(database,uncertain):
    repo=initialized(database);schedule(repo,'a','task')
    job,token=repo.claim({'a'},{'reference_cache'},'model','fixture')
    if uncertain:
        with repo.tx() as c:
            changed=repo.read_job(c,job['id']);changed['heartbeat']=0;repo.save_job(c,changed)
        assert repo.claim({'a'},{'reference_cache','annotate'},'model','fixture') is None
        with pytest.raises(ValueError):publish(repo,job,token)
    else:
        repo.finish(job['id'],token,{'status':'failed','receipt':{}},lambda s,j,c:apply_result(repo,s,j,c))
    for _ in range(3):schedule(repo,'a','task')
    assert len([j for j in repo.jobs('a','task') if j['kind']=='reference_cache'])==1
    assert repo.claim({'a'},{'annotate','reference_cache'},'model','fixture') is None
    assert repo.get('a','task')['pause_reason']
    repo.mutate('a','task',lambda s,c:(s.pop('pause_reason'),s['reference_cache'].update(status='retry_authorized')))
    schedule(repo,'a','task');assert len([j for j in repo.jobs('a','task') if j['kind']=='reference_cache'])==2


def test_postgres_cancelled_prefix_does_not_block_explicit_reenable(database):
    repo=initialized(database);schedule(repo,'a','task')
    before=repo.get('a','task')
    repo.enable('a','task',before['classes'],before['profiles'],False)
    assert repo.get('a','task')['reference_cache']['status']=='cancelled'
    repo.enable('a','task',before['classes'],before['profiles'],True)
    # Existing cancelled original isn't silently replayed after re-enable.
    schedule(repo,'a','task');assert len([j for j in repo.jobs('a','task') if j['kind']=='reference_cache'])==1


def test_pooled_transport_explicit_proxy_single_post_and_safe_failure(monkeypatch):
    from local_inspection_service.training import real_photo_transport as client
    from requests.exceptions import ConnectionError
    calls=[];evidence={};closed=[]
    monkeypatch.setattr(client,'_last_finished',None)
    monkeypatch.setattr(client._session,'close',lambda:closed.append(True))
    def post(endpoint,**kwargs):calls.append((endpoint,kwargs));raise ConnectionError('PRIVATE_KEY URL')
    monkeypatch.setattr(client._session,'post',post)
    config={**SETTINGS,'base_url':'https://ark.cn-beijing.volces.com/api/v3/chat/completions',
            'api_key':'PRIVATE_KEY','proxy_url_raw':'http://127.0.0.1:8123','timeout_seconds':120}
    with pytest.raises(ConnectionError):client.invoke({'model':MODEL},config,evidence)
    assert len(calls)==1 and calls[0][0].endswith('/api/v3/responses')
    assert calls[0][1]['proxies']['https']==config['proxy_url_raw']
    assert calls[0][1]['timeout']==(30,120)
    assert closed==[True] and evidence['pool_failure_reset']
    assert not client._session.trust_env and client._session.adapters['https://'].max_retries.total==0
    assert evidence['automatic_retries']==0 and evidence['transport_stage']=='send_wait_headers'
    assert 'PRIVATE_KEY' not in json.dumps(evidence)


def test_transport_reuses_recent_pool_but_retires_idle_connection_before_next_post(monkeypatch):
    from local_inspection_service.training import real_photo_transport as client
    from unittest.mock import Mock
    session=Mock();events=[]
    class Response:
        status_code=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,*args):yield b'{"status":"completed"}'
    def post(*args,**kwargs):events.append('post');return Response()
    session.post.side_effect=post;session.close.side_effect=lambda:events.append('close')
    monkeypatch.setattr(client,'_session',session)
    monkeypatch.setattr(client,'_last_finished',None)
    ticks=iter([100,100,101,101,110,110,111,111,145,145,146,146])
    monkeypatch.setattr(client.time,'monotonic',lambda:next(ticks))
    config={**SETTINGS,'base_url':'https://fixture.invalid/api/v3','api_key':'PRIVATE',
            'timeout_seconds':120}
    receipts=[]
    for _ in range(3):
        evidence={};assert client.invoke({},config,evidence)[0]==200;receipts.append(evidence)
    assert events==['post','post','close','post']
    assert [r['pool_idle_reset'] for r in receipts]==[False,False,True]
    assert all(r['transport_stage']=='complete' and r['automatic_retries']==0 for r in receipts)
    assert session.cookies.clear.call_count==3


def test_socket_write_uses_connect_budget_not_later_response_read_budget():
    # Exercise the production urllib3 implementation, not an assumed requests
    # timeout meaning: both reused headers and body inherit this socket budget.
    from urllib3.connection import HTTPConnection
    class Socket:
        def __init__(self):self.timeout=None;self.writes=[]
        def settimeout(self,value):self.timeout=value
        def sendall(self,data):self.writes.append((self.timeout,data))
    connection=HTTPConnection('fixture.invalid',timeout=30)
    connection.sock=Socket()
    connection.request('POST','/api/v3/responses',body=b'image-body',headers={'Content-Length':'10'})
    assert connection.sock.writes[-1]==(30,b'image-body')
    assert all(timeout==30 for timeout,_ in connection.sock.writes)
