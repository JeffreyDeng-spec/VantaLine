"""Synthetic geometry and queue tests. Real-model acceptance is a separate commissioning gate."""
import concurrent.futures
import copy
import io
import json
import os
import time
import uuid
import pytest
from PIL import Image
from local_inspection_service.training.real_photo_annotation import canonical, annotate
from local_inspection_service.training.real_photo_contracts import MODEL, objects, review_report, review_key, dataset_gate


def image():
    out=io.BytesIO();im=Image.new('RGB',(80,60),'green')
    exif=Image.Exif();exif[274]=6;im.save(out,'JPEG',exif=exif)
    return out.getvalue()


def classes():
    from local_inspection_service.training.real_photo_contracts import digest
    return [{'class_id':'a','name':'part','definition':'visible part',
             'reference_path':'fixture.jpg','reference_sha256':digest(image())},
            {'class_id':'missing','name':'rare part','definition':'rare','reference_path':'fixture.jpg','reference_sha256':digest(image())}]


def test_first_frame_preserves_pixels_and_explicit_orientation():
    clean,meta=canonical(image())
    with Image.open(io.BytesIO(clean)) as normalized, Image.open(io.BytesIO(image())) as original:
        assert normalized.size==original.size==(80,60)
        assert normalized.tobytes()==original.convert('RGB').tobytes()
        assert not normalized.getexif()
    assert meta['source_orientation']==6 and meta['coordinate_transform']==[1,0,0,0,1,0]


@pytest.mark.parametrize('box',[[0,0,1001,100],[10,0,1,100],[False,0,100,100],[float('nan'),0,100,100]])
def test_reject_ambiguous_or_invalid_geometry(box):
    with pytest.raises(ValueError):objects([{'class_id':'a','bbox':box}],{'a'},80,60,normalized=True)


@pytest.mark.parametrize('mode',['valid','unknown','truncated','broken','model','http','empty'])
def test_blind_request_and_failed_usage_retention(mode):
    calls=[]
    def invoke(body,settings):
        calls.append(body)
        raw={'objects':[] if mode=='empty' else [{'class_id':'unknown' if mode=='unknown' else 'a','bbox':[0,0,500,1000]}]}
        return 500 if mode=='http' else 200,json.dumps({'model':'other' if mode=='model' else MODEL,
            'choices':[{'finish_reason':'length' if mode=='truncated' else 'stop',
                        'message':{'content':'{' if mode=='broken' else json.dumps(raw)}}],
            'usage':{'prompt_tokens':100,'completion_tokens':2048}})
    result=annotate(image(),classes(),{'provider':'doubao','model':MODEL,'configured':True},lambda c:image(),invoke)
    assert len(calls)==1 and calls[0]['max_tokens']==4096
    assert result['receipt']['usage']['completion_tokens']==2048
    assert result['status']==('completed' if mode in {'valid','empty'} else 'failed')
    if mode=='valid':assert result['objects'][0]['bbox']==[0,0,40,60]


def state_fixture():
    cs=classes();samples=[]
    for i in range(20):
        s={'sample_id':str(i),'image_sha256':str(i),'source_group':str(i%3),'geometry':{'width':80,'height':60},
           'annotation':{'status':'completed','version':1,'objects':[{'class_id':'a','bbox':[0,0,10,10]}]}}
        s['review']={'key':review_key(s,cs),'decision':'accept_positive'};samples.append(s)
    return {'classes':cs,'samples':samples}


def test_group_split_and_missing_class_does_not_block():
    state=state_fixture();selected,splits,unsupported=dataset_gate(state,20)
    assert len(selected)==20 and set(splits.values())=={'train','val','test'} and unsupported==['missing']
    assert dataset_gate({**state,'split_assignments':splits},20)[1]==splits
    state['samples'][0]['annotation']['version']=2
    with pytest.raises(ValueError):dataset_gate(state,20)


def test_duplicate_source_cannot_cross_groups_and_no_source_group():
    state=state_fixture();state['samples'][0]['source_group']=''
    with pytest.raises(ValueError):dataset_gate(state,20)
    state=state_fixture();state['samples'][1]['image_sha256']=state['samples'][0]['image_sha256']
    state['samples'][1]['review']['key']=review_key(state['samples'][1],state['classes'])
    with pytest.raises(ValueError):dataset_gate(state,20)


def test_agent_cannot_change_boxes_or_turn_positive_into_negative():
    s=state_fixture()['samples'][0];s['review_key']=s['review']['key']
    job={'kind':'review','inputs':{'samples':[s]}}
    row={'sample_id':s['sample_id'],'review_key':s['review_key'],'decision':'accept_negative','reason':'none'}
    with pytest.raises(ValueError):review_report(job,{'decisions':[row]})
    row.update(decision='accept_positive',bbox=[0,0,1,1])
    with pytest.raises(ValueError):review_report(job,{'decisions':[row]})


@pytest.fixture
def database():
    dsn=os.getenv('REAL_PHOTO_TEST_DATABASE_URL')
    if not dsn:pytest.skip('explicit disposable PostgreSQL required')
    import psycopg
    from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
    from local_inspection_service.storage.real_photo_feedback import RealPhotoRepository, DDL
    name='real_photo_test_'+uuid.uuid4().hex
    with psycopg.connect(dsn) as c:
        c.execute(f'CREATE SCHEMA {name}')
        c.execute(DDL.format(schema=name))
    connections=[]
    def create():
        c=psycopg.connect(dsn);connections.append(c)
        return RealPhotoRepository(PostgresRuntimeRepository(c,'test',name))
    yield create
    for c in connections:c.close()
    with psycopg.connect(dsn) as c:c.execute(f'DROP SCHEMA {name} CASCADE')


def test_postgres_concurrent_enable_claim_owner_and_no_uncertain_replay(database):
    def enable(_):return database().enable('a','task',classes(),{})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(enable,range(8)))
    repo=database();assert len(repo.jobs('a','task'))==1 and repo.get('b','task') is None
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        claims=list(pool.map(lambda _:database().claim({'a'},{'initialize'},'model','cli'),range(4)))
    assert sum(x is not None for x in claims)==1
    job,token=next(x for x in claims if x)
    with repo.tx() as c:
        old=repo.read_job(c,job['id']);old['heartbeat']=0;repo.save_job(c,old)
    assert repo.claim({'a'},{'initialize'},'model','cli') is None
    assert repo.jobs('a','task')[0]['status']=='interrupted'
    with pytest.raises(ValueError):repo.finish(job['id'],token,{},lambda *a:None)
    assert repo.repository.connection.info.transaction_status.name=='IDLE'


def test_postgres_cancel_stale_token_and_atomic_round(database):
    repo=database();repo.enable('a','task',classes(),{})
    job,token=repo.claim({'a'},{'initialize'},'model','cli')
    result={'review_trigger':20,'approved_real_target':20,'reason':'few real photos first'}
    repo.finish(job['id'],token,result,lambda s,j,c:s.update(review_trigger=j['result']['review_trigger']))
    assert repo.get('a','task')['review_trigger']==20
    with pytest.raises(ValueError):repo.finish(job['id'],token,result,lambda *a:None)
    repo.enable('a','task',classes(),{},False)
    assert not repo.get('a','task')['enabled']


def test_api_owner_isolation_failed_multi_capture_and_private_original(database,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from local_inspection_service.training.real_photo_api import compose,FeedbackPorts,FeedbackService
    raw=image();reader=lambda path:raw
    owner={'id':'a'};task={'id':'task','owner_user_id':'a','accessory_ids':['a']}
    profiles=SimpleNamespace(snapshot=lambda:{'bbox_annotation':{'id':'fixed','version':1}},
                             resolve=lambda *a:{'configured':True,'provider':'doubao','model':MODEL})
    ports=FeedbackPorts(repository=lambda:database().repository,user=lambda:owner,tasks=lambda:[task],
                        authorize=lambda *a,**kw:None,config=lambda user:{'accessories':[{'id':'a','name':'part'}]},
                        references=lambda item:['ref'],read=reader,profiles=lambda:profiles,legacy_state=lambda task:{})
    app=FastAPI();service=compose(app,FeedbackService(ports));client=TestClient(app)
    monkeypatch.setenv('VANTALINE_REAL_PHOTO_ACCOUNTS','a')
    assert client.patch('/api/ai/tasks/task/real-photo',json={'enabled':True}).status_code==200
    result={'passed':False,'model':{'task_id':'task','is_ai_detection':True},'detections':[{},{}]}
    assert service.capture({'source_image':{'path':'real','url':'overlay'}},result,'one',None)
    assert service.capture({'source_image':{'path':'real'}},result,'two',None)
    status=client.get('/api/ai/tasks/task/real-photo').json()
    assert status['candidate_count']==1 and status['pending_annotation_count']==1
    identifier=status['samples'][0]['sample_id'];sample=client.get(f'/api/ai/tasks/task/real-photo/samples/{identifier}/image')
    assert sample.status_code==200 and sample.headers['cache-control']=='private, no-store'
    owner.update(id='b',role='admin')
    assert client.get('/api/ai/tasks/task/real-photo').status_code==403
    monkeypatch.delenv('VANTALINE_REAL_PHOTO_ACCOUNTS')
    assert service.capture({},result,'three',None) is False
