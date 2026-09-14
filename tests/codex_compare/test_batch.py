"""Batch scope, real PostgreSQL drafts, import-only path and one harness per batch."""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import pytest
from PIL import Image
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_postgres import storage
from test_label_contracts import card as complete_card
from local_inspection_service.codex_compare import batch_contracts as b, api, worker
from local_inspection_service.codex_compare.contracts import digest, validate_report
from local_inspection_service.codex_compare.media import MediaStore
from local_inspection_service.storage.agent_operations import OperationConflict, OperationDenied


def png(color='white'):
    out=io.BytesIO();Image.new('RGB',(120,80),color).save(out,'PNG');return out.getvalue()


def model(count=2):
    t={'report_version':b.VERSION,'inputs':{'references':{'a':{'media':{'image':'hash'}}}},'references':{},'labels':{},'summary':None,'finalized':False}
    b.apply(t,'reference',{'id':'R1','asset_id':'a','name':'标准','region':[0,0,1,1]})
    for n in range(count):
        lid='L'+str(n);t['labels'][lid]=b.new_label(lid,{'image':'actual'},'实拍')
        b.apply(t,'match',{'label_id':lid,'value':{'status':'matched','reference_id':'R1','candidate_ids':['R1'],'reason':'结构相符'}})
    return t


def test_batch_coverage_counts_and_local_ids():
    t=model()
    for e in t['labels'].values():
        e.update({k:v for k,v in complete_card().items() if k in ('elements','checks','issues','summary','artifacts','decodes')})
    t['summary']=dict(decision='MATCH',message='一致',checked_scope='全部',unchecked_scope='')
    validate_report(t)
    assert b.public_batch({**t,'id':'batch','created_at':1,'status':'running','sequence':2})['counts']['match']==2
    b.apply(t,'checklist',{'label_id':'L1','value':{'checks':[{'id':'new','dimension':'print','element_ids':[],'expected':'局部'}]}})
    assert 'new' not in t['labels']['L0']['checks']
    with pytest.raises(ValueError):validate_report(t)
    with pytest.raises(ValueError):b.apply(t,'element',{'label_id':'other','value':{}})
    with pytest.raises(ValueError):b.apply(t,'reference',{'id':'R1','asset_id':'a','name':'标准','region':[0,0,.5,1]})
    with pytest.raises(ValueError):b.apply(t,'match',{'label_id':'L0','value':{'status':'needs_confirmation','reason':'改变','reference_id':None}})
    assert 'checks' not in b.public_label(t,'L0') and 'checks' in b.public_label(t,'L0',True)


def test_unmatched_is_never_ignored_or_passed():
    t=model(1);t['labels']['L0']['match']['status']='pending'
    t['summary']=dict(decision='MATCH',message='一致',checked_scope='全部',unchecked_scope='')
    with pytest.raises(ValueError):validate_report(t)
    b.apply(t,'match',{'label_id':'L0','value':{'status':'needs_confirmation','reason':'候选过于相似','reference_id':None,'candidate_ids':['R1']}})
    with pytest.raises(ValueError):validate_report(t)
    t['summary'].update(decision='REVIEW_REQUIRED',unchecked_scope='L0 对应关系')
    validate_report(t)
    assert b.label_status(t,t['labels']['L0'])=='uncertain'
    with pytest.raises(ValueError):b.apply(t,'checklist',{'label_id':'L0','value':{'checks':[]}})


@pytest.mark.skipif(not os.environ.get('CODEX_TEST_DATABASE_URL'),reason='Disposable PG required')
def test_api_import_draft_freeze_and_owner(storage,tmp_path,monkeypatch):
    monkeypatch.setenv('VANTALINE_CODEX_COMPARE_ACCOUNTS','a');monkeypatch.setenv('VANTALINE_CODEX_COMPARE_MODEL','fixed')
    records={'standards':{},'assets':{}};who={'id':'a'};calls=[]
    data=png()
    def owned(kind,key,owner):
        entry=records[kind].get(key)
        return copy.deepcopy(entry) if entry and entry['owner_user_id']==owner else None
    def save(kind,entry,insert_only=False):records[kind][entry['id']]=copy.deepcopy(entry);return True
    def write(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    def extract(_):
        calls.append('extract')
        return [{'ordinal':1,'sha256':digest(data),'mime_type':'image/png'},{'ordinal':2,'sha256':digest(data),'mime_type':'image/png'}],[data,data]
    app=FastAPI()
    ns={'app':app,'DATA_DIR':tmp_path,'require_permission':lambda *_:None,'_text_v2_owner':lambda:(who['id'],'admin'),
        'runtime_postgres_repository_or_none':lambda:storage().repository,'_text_v2_owned':owned,'_text_v2_load':lambda kind:list(records[kind].values()),
        '_text_v2_save':save,'_text_v2_write':write,'_text_v2_media_path':lambda owner,std,name:tmp_path/owner/std/name,
        '_text_v2_asset_bytes':lambda a,o:Path(a['media_path']).read_bytes(),'extract_docx_candidates':extract,'extract_doc_images':extract}
    api.register(ns);c=TestClient(app);root=api.PREFIX+'/batches'
    response=c.post(root,json={'request_id':'create-batch'});assert response.status_code==200,response.text
    bid=response.json()['id'];url=root+'/'+bid
    assert storage().claim({'a'},'m','v') is None
    response=c.post(url+'/document',data={'request_id':'import-doc'},files={'file':('order.docx',b'fixture')})
    assert response.status_code==200,response.text
    task=response.json();assert len(task['inputs']['references'])==1
    assert next(iter(task['inputs']['references'].values()))['sources'][1]['ordinal']==2
    assert len(records['standards'])==1 and next(iter(records['standards'].values()))['status']=='draft'
    assert calls==['extract']
    assert c.post(url+'/document',data={'request_id':'import-doc'},files={'file':('order.docx',b'fixture')}).status_code==200
    assert calls==['extract']
    upload=lambda key,allow=False:c.post(url+'/photos',data={'request_id':key,'allow_duplicate':str(allow)},files={'file':('actual.png',data)})
    first=upload('photo-one');assert first.status_code==200,first.text
    assert len(upload('photo-one').json()['labels'])==1
    assert upload('photo-two').status_code==409
    assert len(upload('photo-two',True).json()['labels'])==2
    assert len(c.get(url).json()['labels'])==2
    lid=first.json()['labels'][0]['id'];sha=first.json()['labels'][0]['actual']['image'];mediaurl=api.PREFIX+'/tasks/'+bid+'/media/'+sha
    who['id']='b'
    assert c.get(url).status_code==404 and c.get(mediaurl).status_code==404
    assert c.post(url+'/labels/'+lid+'/remove',json={'request_id':'remove-123'}).status_code==403
    who['id']='a'
    r=c.post(url+'/submit',json={'request_id':'submit-one'});assert r.status_code==200,r.text
    assert c.post(url+'/submit',json={'request_id':'submit-one'}).json()['status']=='queued'
    assert upload('photo-new').status_code==409
    assert c.post(url+'/labels/'+lid+'/remove',json={'request_id':'remove-123'}).status_code==409
    task,token=storage().claim({'a'},'m','v');args=('a',bid,task['attempt_id'],token)
    assert storage().claim({'a'},'m','v') is None
    assert c.post(api.PREFIX+'/tasks/'+bid+'/cancel').status_code==200
    with pytest.raises(OperationDenied):storage().write_report(*args,'late-write','progress',{'message':'late'})
    storage().settle('a',bid,task['attempt_id'],'cancelled')
    aid=next(iter(task['inputs']['references']))
    rerun=c.post(url+'/retry',json={'request_id':'rerun-one','label_ids':[lid],'matches':{lid:{'asset_id':aid,'region':[0,0,1,1]}}})
    assert rerun.status_code==200,rerun.text
    assert rerun.json()['parent_id']==bid and len(rerun.json()['labels'])==1
    assert rerun.json()['labels'][0]['match']['status']=='matched'
    assert c.post(url+'/retry',json={'request_id':'rerun-one','label_ids':[lid],'matches':{lid:{'asset_id':aid,'region':[0,0,1,1]}}}).json()['id']==rerun.json()['id']
    assert c.get(url+'/labels/'+lid).json()['match']['status']=='pending'
    for standard in records['standards'].values():standard['status']='deleted'
    assert c.get(mediaurl).content==data


@pytest.mark.skipif(not os.environ.get('CODEX_TEST_DATABASE_URL'),reason='Disposable PG required')
@pytest.mark.parametrize('count',[1,5,10])
def test_batch_one_harness_cli_roundtrip(storage,tmp_path,monkeypatch,count):
    media=MediaStore(tmp_path/'media');evidence=media.image('a',png())
    inputs={'references':{'a':{'id':'a','name':'标准','sources':[],'media':evidence}},'actuals':{f'L{i}':{'name':f'实拍{i}','media':evidence} for i in range(count)}}
    repo=storage();draft=repo.create('a','batch-session',inputs,report_version=b.VERSION)
    repo.edit_draft('a',draft['id'],'queue-batch','queued',{},lambda t:t.update(status='queued'))
    task,token=repo.claim({'a'},'fixture','fixture')
    auth=tmp_path/'auth';auth.mkdir();(auth/'auth.json').write_text('{}')
    fake=tmp_path/'harness.py'
    fake.write_text('''import json,os,sys,subprocess
from pathlib import Path
sock,token,cli,work=sys.argv[1:]
prompt=sys.stdin.read()
assert '$vantaline-label-inspection' in prompt and 'label-batch-v3' in prompt
os.environ.update(VANTALINE_TASK_SOCKET=sock,VANTALINE_TASK_TOKEN=token)
print(json.dumps({'type':'thread.started','thread_id':'one-batch-session'}),flush=True)
def call(*args):
 r=subprocess.run([sys.executable,cli,*args],capture_output=True,text=True)
 assert r.returncode==0,r.stdout
 return json.loads(r.stdout)
def write(value,*args):
 p=Path(work)/'payload.json';p.write_text(json.dumps(value));return call(*args,'--file',str(p))
task=call('batch','show')
assert task['report_version']=='label-batch-v3'
write({'id':'R','asset_id':'a','name':'标准','region':[0,0,1,1]},'reference','upsert')
for e in task['labels']:
 lid=e['id']
 if lid=='L0':
  write({'status':'matched','reference_id':'R','candidate_ids':['R'],'reason':'对应测试'},'label','match','set','--label',lid)
  write({'id':'E1','category':'outline','name':'边框','description':'空白图测试边框不可确认','reference':None,'actual':None},'element','upsert','--label',lid)
  dims='text typography color graphics completeness orientation shape layout codes print'.split()
  plan=[{'id':'G'+d,'dimension':d,'element_ids':[],'expected':'核对 '+d} for d in dims]
  plan += [{'id':'E'+d,'dimension':d,'element_ids':['E1'],'expected':'核对边框 '+d} for d in ['shape','layout','completeness']]
  write({'checks':plan},'checklist','set','--label',lid)
  for c in plan:write({**c,'status':'uncertain','observed':'空白','explanation':'空白测试图片无法判断'},'check','upsert','--label',lid)
  write({'decision':'REVIEW_REQUIRED','message':'需要实拍','checked_scope':'全部维度已观察','unchecked_scope':'空白图'},'card','summary','set','--label',lid)
  call('card','finalize','--label',lid)
  assert len(call('card','show','--label',lid)['checks'])==13
  continue
 write({'status':'needs_confirmation','reference_id':None,'candidate_ids':['R'],'reason':'空白测试图片无法确认'},'label','match','set','--label',lid)
 assert call('card','show','--label',lid)['match']['status']=='needs_confirmation'
write({'decision':'REVIEW_REQUIRED','message':'需要人工指定','checked_scope':'全部实拍均已评估对应关系','unchecked_scope':'空白图无法匹配'},'batch','summary','set')
call('batch','finalize')
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':10}}),flush=True)
''')
    launches=[]
    def command(directory,auth_dir,runtime,t,model,socket_path,proxy_url=''):
        launches.append(directory)
        assert (directory/'input'/'batch.json').is_file()
        return [sys.executable,str(fake),str(socket_path),t,str(Path(worker.__file__).with_name('cli.py')),str(directory/'work')]
    monkeypatch.setattr(worker,'sandbox_command',command);monkeypatch.setattr(worker,'with_repo',lambda fn:fn(storage()))
    worker.execute(task,token,{'work_root':str(tmp_path/'work'),'auth_home':str(auth),'model':'fixture','binary':'unused'},media)
    result=repo.get('a',task['id'])
    assert result['status']=='completed' and len(launches)==1
    assert result['session_id']=='one-batch-session' and len(result['labels'])==count
    assert result['skill_sha256']==digest((worker.SKILL/'SKILL.md').read_bytes())
    assert len(result['labels']['L0']['checks'])==13
    assert all(e['match']['status']=='needs_confirmation' for lid,e in result['labels'].items() if lid!='L0')


def test_scoped_source_evidence_cannot_cross_labels(tmp_path):
    import base64
    media=MediaStore(tmp_path/'media')
    t=model()
    t['inputs']['references']['a']['media']=media.image('owner',png())
    for lid,color in [('L0','red'),('L1','blue')]:
        t['labels'][lid]['actual']=media.image('owner',png(color))
        cropped=worker.artifact(media,'owner',b.require_matched(t,lid),{'source':'actual','box':[0,0,1,1],'data':base64.b64encode(png()).decode()})
        b.apply(t,'artifact',{'label_id':lid,'value':cropped})
        with Image.open(io.BytesIO(media.read('owner',cropped['image']))) as image:
            assert image.getpixel((30,30))==({'red':(255,0,0),'blue':(0,0,255)}[color])
    with pytest.raises(ValueError):b.require_matched(t,'../L0')
    with pytest.raises(ValueError):b.apply(t,'match',{'label_id':'L0','value':{'status':'needs_confirmation','reason':'不能覆盖证据对应关系','reference_id':None}})


def test_batch_metrics_keep_unresolved_denominator():
    from scripts.evaluate_label_batches import evaluate_batches
    t=model(2)
    t['labels']['L0'].update({k:v for k,v in complete_card().items() if k in ('elements','checks','issues','summary','artifacts','decodes')})
    b.matching(t,'L1',{'status':'needs_confirmation','reference_id':None,'reason':'相似','candidate_ids':['R1']})
    expected={lid:{'asset_id':'a','dimensions':{'color':'match'}} for lid in t['labels']}
    result=evaluate_batches([{'kind':'synthetic','report':t,'expected':expected}])['synthetic']
    assert result['matching_accuracy_all_actuals']==.5 and result['matching_confirmation_rate']==.5
    assert result['fully_checked_fraction']==.5 and result['dimensions']['color']['uninspected']==1
