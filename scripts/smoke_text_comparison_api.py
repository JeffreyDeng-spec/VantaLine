"""Synthetic paid-call, evidence and review boundaries; no provider or PLC calls."""
import asyncio
import copy
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import re,time,uuid
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi import FastAPI, HTTPException, File, Form, Request, Response, UploadFile
from local_inspection_service.text_inspection import comparison_submission as submission, inspection_reviews as reviews
from local_inspection_service.text_inspection.comparison_submission import ComparisonSubmission
from local_inspection_service.text_inspection.inspection_api import register
from local_inspection_service.text_inspection.inspection_reviews import InspectionReviews
from local_inspection_service.text_inspection.inspection_ports import (
    InspectionAccess, InspectionRecords, SubmissionPolicy, SubmissionImages,
    SubmissionModels, SubmissionDiagnostics, SubmissionMedia,
)
from local_inspection_service.text_inspection.diagnostics import diagnostic_event, diagnostic_value
ROOT_CHECK='--root' in sys.argv
if ROOT_CHECK:sys.argv.remove('--root')


class Upload:
    filename='capture.png';content_type='image/png'
    def __init__(self,data=b'captured'):self.data=data;self.reads=[]
    async def read(self,size=-1):self.reads.append(size);return self.data


class Fixture:
    def __init__(self,directory):
        self.directory=Path(directory);self.events=[];self.owner='alice';self.rows=[];self.save_count=0
        self.fail_save={};self.insert_loser='';self.external=True;self.match=True;self.qwen=False;self.fail_stage=''
        self.standard=dict(id='std',owner_user_id='alice',status='confirmed',current_revision_id='rev1',revision_number=1,
            confirmed_assets=[dict(id='asset',sha256='snapshot-hash')])
        self.asset=dict(id='asset',owner_user_id='alice',standard_id='std',sha256='current-hash')
        self.settings=dict(provider='provider',model='model',timeout_seconds=1,base_url='https://fixture.invalid',configured=True)
        self.provider=dict(ok=True,parsed={},latency_ms=1);self.calls=[];self.files=[];self.logged=[];self.audits=[]
        self.prepared=Mock(return_value={'prepared':True});self.extraction=Mock(return_value=(b'extracted',{'id':'extract'}))
        self.access=InspectionAccess(self.require,lambda:(self.owner,self.owner))
        self.records=InspectionRecords(lambda:self.owned,self.save,lambda row:copy.deepcopy(row))
        self.service=ComparisonSubmission(self.access,self.records,self.load,
            SubmissionMedia(lambda:lambda owner,standard,name:self.directory/name,self.write,lambda:self.digest),
            SubmissionImages(lambda:self.prepare,lambda data,mime:(data,mime,'PNG'),self.asset_bytes,lambda:self.annotate,self.data_url),
            SubmissionModels(lambda purpose:self.setting(purpose),lambda:self.call,lambda:'unchanged-prompt',lambda:lambda value,provider:self.normalize(value,provider),self.validate),
            SubmissionPolicy(lambda:30,lambda:'business-prompt-v1',lambda:self.external,lambda:self.match,lambda owner:self.qwen),
            SubmissionDiagnostics(lambda data,**kwargs:{'sha256':self.digest(data)},lambda:diagnostic_event,
                                  lambda provider,settings:copy.deepcopy(provider),diagnostic_value,self.log),
            self.prepared,self.extraction,lambda standard,asset:{'display':'fixture'})
        self.reviews=InspectionReviews(self.access,self.records,lambda:self.read_verified,lambda:self.audit,lambda:lambda value,limit:str(value or '')[:limit])
        self.app=FastAPI();self.routes=register(self.app,self.service,self.reviews,self.access)
    @staticmethod
    def digest(data):return hashlib.sha256(data).hexdigest()
    def require(self,permission,**kwargs):
        self.events.append(('permission',self.owner))
        if self.owner=='denied':raise HTTPException(403,'denied')
    def owned(self,kind,identifier,owner):
        values={'standards':[self.standard],'assets':[self.asset],'records':self.rows}[kind]
        return next((copy.deepcopy(row) for row in values if row['id']==identifier and row['owner_user_id']==owner),None)
    def load(self,kind):self.events.append(('load',kind));return copy.deepcopy(self.rows)
    def save(self,kind,row,*,insert_only=False):
        self.save_count+=1;self.events.append(('save',self.save_count,copy.deepcopy(row),insert_only))
        error=self.fail_save.get(self.save_count)
        if isinstance(error,Exception):raise error
        if error is False:return False
        if insert_only and self.insert_loser:
            if self.insert_loser!='missing':
                winner=copy.deepcopy(row);winner['id']='winner'
                if self.insert_loser=='conflict':winner['fingerprint']='conflict'
                self.rows=[winner]
            return False
        self.rows=[copy.deepcopy(row)];return True
    def write(self,path,data):
        self.events.append(('write',path))
        if self.fail_stage=='annotation_write' and 'annotated' in path.name:raise OSError('annotation_write')
        path.write_bytes(data);self.files.append(path)
    def prepare(self,data,**kwargs):self.events.append(('prepare',data,kwargs));return data,'image/png','.png','PNG'
    def asset_bytes(self,asset,owner):self.events.append(('asset_bytes',asset['sha256'],owner));return b'reference'
    def setting(self,purpose):self.events.append(('settings',purpose));return self.settings
    def data_url(self,data,mime):
        if self.fail_stage=='data_url':raise RuntimeError('data_url')
        return 'fixture:'+data.decode()
    def call(self,name,args):
        self.calls.append((name,copy.deepcopy(args)));self.events.append(('call',))
        self.assert_persisted_attempt()
        if self.fail_stage=='provider':raise TimeoutError('provider')
        return self.provider
    def assert_persisted_attempt(self):
        assert self.rows and self.rows[0]['status']=='attempting'
        assert any(e[0]=='save' and e[3] is True for e in self.events)
    def normalize(self,value,provider):return {'decision':'MATCH','differences':[],'message':'match'}
    def validate(self,value):
        if self.fail_stage=='validation':raise ValueError('validation')
        return value
    def annotate(self,data,differences):
        if self.fail_stage=='annotation':raise RuntimeError('annotation')
        return b'annotated'
    def log(self,row):
        self.logged.append(copy.deepcopy(row))
        if self.fail_stage=='logger':raise RuntimeError('logger')
    def read_verified(self,path,owner,standard,**kwargs):self.events.append(('verified',path,owner,standard,kwargs));return b'\x89PNGfixture'
    def audit(self,event):
        self.audits.append(copy.deepcopy(event))
        if self.fail_stage=='audit':raise RuntimeError('audit')
    def compare(self,upload=None,comparison='comparison-01',extraction=''):
        return asyncio.run(self.service.compare_text_inspection_label(upload if upload is not None else (None if extraction else Upload()),'asset',comparison,extraction))


def capture_trial(case, window=False, missing=False):
 with tempfile.TemporaryDirectory(prefix='capture-') as tmp:
  f=Fixture(tmp);events=[]
  f.rows=[dict(id='inspection',owner_user_id='alice',standard_id='std',source_path='source',source_sha256='hash')] if case.startswith('review') or case.startswith('evidence') else []
  def owned(kind,identifier,owner):
   values={'standards':[f.standard],'assets':[f.asset],'records':f.rows}[kind]
   return next((row for row in values if row['id']==identifier and row['owner_user_id']==owner),None)
  ns=dict(Any=Any,Path=Path,HTTPException=HTTPException,File=File,Form=Form,Request=Request,Response=Response,UploadFile=UploadFile,
   json=json,re=re,time=SimpleNamespace(time=lambda:1000.0),uuid=uuid,urlsplit=urlsplit,
   require_permission=f.require,_text_v2_owner=lambda:('alice','alice'),_text_v2_owned=owned,_text_v2_save=f.save,_text_v2_load=f.load,_text_v2_public=lambda row:row,
   _text_v2_media_path=lambda owner,standard,name:Path(tmp)/name,_text_v2_write=f.write,sha256_bytes=f.digest,
   _text_v2_prepare_image=f.prepare,_text_v2_prepare_provider_image=lambda data,mime:(data,mime,'PNG'),_text_v2_asset_bytes=f.asset_bytes,_text_v2_annotate=f.annotate,_text_v2_data_url=f.data_url,
   ai_detection_settings=f.setting,call_ai_mcp_tool=f.call,strict_compare_prompt=lambda:'unchanged-prompt',normalize_vlm_provider_result=f.normalize,validate_vlm_result=f.validate,
   TEXT_INSPECTION_PROVIDER_TIMEOUT_SECONDS=30,TEXT_INSPECTION_PROMPT_VERSION='business-prompt-v1',TEXT_INSPECTION_EXTERNAL_VLM_ENABLED=True,TEXT_INSPECTION_AUTOMATIC_MATCH_VERIFIED=True,
   _qwen_evidence_policy=SimpleNamespace(enabled=lambda owner:False),_text_v2_image_diagnostics=lambda data,**kw:{},_text_v2_diagnostic_event=lambda *a,**k:None,
   _text_v2_provider_diagnostics=lambda p,s:{},_text_v2_diagnostic_value=lambda x:x,_text_v2_write_server_diagnostic=f.log,
   _submit_prepared_text_comparison=f.prepared,resolve_label_extraction=f.extraction,comparison_display_snapshot=lambda s,a:{},
   _text_v2_read_verified=f.read_verified,append_incoming_text_audit=f.audit,bounded_text=lambda value,limit:str(value or '')[:limit],
   )
  target={
   'owned-compare':'_text_v2_owned','prepare':'_text_v2_prepare_image','fingerprint':'sha256_bytes','source-path':'_text_v2_media_path','paid-call':'call_ai_mcp_tool','normalize':'normalize_vlm_provider_result','annotate':'_text_v2_annotate','event-provider':'_text_v2_diagnostic_event','event-failure':'_text_v2_diagnostic_event',
   'review-owned':'_text_v2_owned','review-text':'bounded_text','review-audit':'append_incoming_text_audit','evidence-read':'_text_v2_read_verified','review-json':None}[case]
  if target:
   original=ns[target]
   def callback_a(*a,**k):events.append('A');return original(*a,**k)
   def callback_b(*a,**k):events.append('B');return original(*a,**k)
   def callback_c(*a,**k):events.append('C');return original(*a,**k)
   ns[target]=callback_a
  def before():ns[target]=None if missing else callback_b
  def switch():events.append('argument');ns[target]=callback_c if window else callback_b
  body={'decision':'PASS','reason':' approved '}
  class TriggerDict(dict):
   def __init__(self,*a,hook=None,key=None,method='get',**kw):super().__init__(*a,**kw);self.hook=hook;self.key=key;self.method=method
   def get(self,key,*a):
    if self.method=='get' and key==self.key:self.hook()
    return super().get(key,*a)
   def __getitem__(self,key):
    if self.method=='item' and key==self.key:self.hook()
    return super().__getitem__(key)
  if case=='owned-compare':f.asset=TriggerDict(f.asset,key='standard_id',hook=switch)
  if case=='prepare':
   class Extraction(dict):
    def __bool__(self):switch();return True
   f.extraction.return_value=(b'extracted',Extraction(id='extract'))
  if case=='fingerprint':
   def dumps(*a,**k):switch();return json.dumps(*a,**k)
   ns['json']=SimpleNamespace(dumps=dumps)
  if case=='source-path':
   path_reads=[0]
   def path_arg():
    path_reads[0]+=1
    if path_reads[0]==4:switch()
   f.standard=TriggerDict(f.standard,key='id',method='item',hook=path_arg)
  if case=='paid-call':
   def prompt():switch();return 'unchanged-prompt'
   ns['strict_compare_prompt']=prompt
  if case=='normalize':f.provider=TriggerDict(f.provider,key='parsed',hook=switch)
  if case=='annotate':
   def normalize(*a):return TriggerDict({'decision':'MATCH','differences':[],'message':'match'},key='differences',method='item',hook=switch)
   ns['normalize_vlm_provider_result']=normalize
  if case=='event-provider':f.provider=TriggerDict(f.provider,key='ok',hook=switch)
  if case=='event-failure':
   class Failure(RuntimeError):
    def __str__(self):
     self.reads=getattr(self,'reads',0)+1
     if window and self.reads==1:before()
     if self.reads==2:switch()
     return 'unknown'
   def fail(*a):raise Failure()
   ns['call_ai_mcp_tool']=fail
  if case=='review-owned':f.rows[0]=TriggerDict(f.rows[0],key='standard_id',hook=switch)
  if case=='review-text':body=TriggerDict(body,key='reason',hook=switch)
  if case=='review-audit':
   clock_reads=[0]
   def clock():
    clock_reads[0]+=1
    if clock_reads[0]==3:switch()
    return 1000.0
   ns['time']=SimpleNamespace(time=clock)
  if case=='evidence-read':f.rows[0]=TriggerDict(f.rows[0],key='source_path',hook=switch)
  class RequestFixture:
   @property
   def json(self):
    events.append('json-lookup')
    async def read():
     events.append('json-call')
     if window and case=='review-text':before()
     return body
    return read
  if case=='review-json':
   def permission(*a,**k):events.append('permission');raise HTTPException(403,'denied')
   ns['require_permission']=permission
  req=RequestFixture()
  if window:
   if case in ('owned-compare','review-owned'):
    def first_owned(*a,**k):
     result=callback_a(*a,**k);before();return result
    ns[target]=first_owned
   elif case=='prepare':
    def resolve(*a):before();return f.extraction(*a)
    ns['resolve_label_extraction']=resolve
   elif case=='fingerprint':
    entered=[False]
    def model_policy():
     if not entered[0]:before();entered[0]=True
    f.settings=TriggerDict(f.settings,key='model',hook=model_policy)
   elif case=='source-path':ns['comparison_display_snapshot']=lambda *a:(before() or {})
   elif case in ('paid-call','review-audit'):
    def save(*a,**k):
     result=f.save(*a,**k)
     if case=='review-audit' or f.save_count==2:before()
     return result
    ns['_text_v2_save']=save
   elif case=='normalize':
    def event(*a,**k):
     if a[1:3]==('provider_call','ok'):before()
    ns['_text_v2_diagnostic_event']=event
   elif case=='annotate':
    def validate(value):before();return f.validate(value)
    ns['validate_vlm_result']=validate
   elif case=='event-provider':
    def call(*a):result=f.call(*a);before();return result
    ns['call_ai_mcp_tool']=call
   elif case=='evidence-read':
    owner=ns['_text_v2_owner']
    def current_owner():before();return owner()
    ns['_text_v2_owner']=current_owner
  access=InspectionAccess(lambda *a,**k:ns['require_permission'](*a,**k),lambda:ns['_text_v2_owner']())
  records=InspectionRecords(lambda:ns['_text_v2_owned'],lambda *a,**k:ns['_text_v2_save'](*a,**k),lambda row:ns['_text_v2_public'](row))
  compare=ComparisonSubmission(access,records,lambda kind:ns['_text_v2_load'](kind),
   SubmissionMedia(lambda:ns['_text_v2_media_path'],lambda *a:ns['_text_v2_write'](*a),lambda:ns['sha256_bytes']),
   SubmissionImages(lambda:ns['_text_v2_prepare_image'],lambda *a:ns['_text_v2_prepare_provider_image'](*a),lambda *a:ns['_text_v2_asset_bytes'](*a),lambda:ns['_text_v2_annotate'],lambda *a:ns['_text_v2_data_url'](*a)),
   SubmissionModels(lambda purpose:ns['ai_detection_settings'](purpose),lambda:ns['call_ai_mcp_tool'],lambda:ns['strict_compare_prompt'](),lambda:ns['normalize_vlm_provider_result'],lambda value:ns['validate_vlm_result'](value)),
   SubmissionPolicy(lambda:30,lambda:'business-prompt-v1',lambda:True,lambda:True,lambda owner:False),
   SubmissionDiagnostics(lambda *a,**k:ns['_text_v2_image_diagnostics'](*a,**k),lambda:ns['_text_v2_diagnostic_event'],lambda *a:ns['_text_v2_provider_diagnostics'](*a),lambda value:ns['_text_v2_diagnostic_value'](value),lambda row:ns['_text_v2_write_server_diagnostic'](row)),
   lambda *a:ns['_submit_prepared_text_comparison'](*a),lambda *a:ns['resolve_label_extraction'](*a),lambda *a:ns['comparison_display_snapshot'](*a))
  review=InspectionReviews(access,records,lambda:ns['_text_v2_read_verified'],lambda:ns['append_incoming_text_audit'],lambda:ns['bounded_text'])
  def execute():
   if case.startswith('review'):
    endpoint=register(FastAPI(),compare,review,access).review_text_inspection_v2
    return asyncio.run(endpoint('inspection',req))
   if case.startswith('evidence'):return review.get_text_inspection_v2_evidence('inspection','source')
   return asyncio.run(compare.compare_text_inspection_label(None if case=='prepare' else Upload(),'asset','comparison-01','extract' if case=='prepare' else ''))
  with patch.object(submission,'time',ns['time']),patch.object(submission,'json',ns['json']),patch.object(reviews,'time',ns['time']):
   try:
    result=execute()
    if missing:events.append('settled:'+str(result.get('error_code')))
   except HTTPException:
    if case!='review-json':raise
   except TypeError:
    if not missing:raise
    events.append('error:TypeError')
  return events

class SubmissionContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='comparison-');self.addCleanup(self.temp.cleanup)
        self.f=Fixture(self.temp.name)
    def fresh(self):
        folder=Path(self.temp.name)/str(len(list(Path(self.temp.name).iterdir())));folder.mkdir();return Fixture(folder)
    def test_capture_sequences_match_original_calls_and_http_admission(self):
        expected={
            'owned-compare':['A','argument','A'],
            'prepare':['argument','A','B','argument'],
            'fingerprint':['A','A','A','A','argument','A','B','B'],
            'source-path':['argument','A','B'],
            'paid-call':['argument','A'], 'normalize':['argument','A'], 'annotate':['argument','A'],
            'event-provider':['A','A','argument','A','argument','B','B','B'],
            'event-failure':['A','A','argument','A'],
            'review-owned':['A','argument','A','json-lookup','json-call'],
            'review-text':['json-lookup','json-call','argument','A'],
            'review-audit':['json-lookup','json-call','argument','A'],
            'evidence-read':['argument','A'], 'review-json':['permission'],
        }
        for case,events in expected.items():
            with self.subTest(case=case):self.assertEqual(capture_trial(case),events)

    def test_capture_windows_reject_entry_cache_and_late_resolution(self):
        expected={
            'owned-compare':['A','argument','B'],
            'prepare':['argument','B','C','argument'],
            'fingerprint':['A','A','A','A','argument','B','C','C'],
            'source-path':['argument','B','C'],
            'paid-call':['argument','B'], 'normalize':['argument','B'], 'annotate':['argument','B'],
            'event-provider':['A','A','argument','B','argument','C','C','C'],
            'event-failure':['A','A','argument','B'],
            'review-owned':['A','argument','B','json-lookup','json-call'],
            'review-text':['json-lookup','json-call','argument','B'],
            'review-audit':['json-lookup','json-call','argument','B'],
            'evidence-read':['argument','B'],
        }
        for case,events in expected.items():
            with self.subTest(case=case):self.assertEqual(capture_trial(case,window=True),events)

    def test_missing_callbacks_preserve_argument_effects_and_error_policy(self):
        expected={
            'owned-compare':['A','argument','error:TypeError'],
            'prepare':['argument','error:TypeError'],
            'fingerprint':['A','A','A','A','argument','error:TypeError'],
            'source-path':['argument','error:TypeError'],
            'paid-call':['argument','settled:TypeError'],
            'normalize':['argument','settled:TypeError'], 'annotate':['argument','settled:TypeError'],
            'event-provider':['A','A','argument','C','settled:TypeError'],
            'event-failure':['A','A','argument','error:TypeError'],
            'review-owned':['A','argument','error:TypeError'],
            'review-text':['json-lookup','json-call','argument','error:TypeError'],
            'review-audit':['json-lookup','json-call','argument','error:TypeError'],
            'evidence-read':['argument','error:TypeError'],
        }
        for case,events in expected.items():
            with self.subTest(case=case):self.assertEqual(capture_trial(case,window=True,missing=True),events)

    @staticmethod
    def fail_once(callback, error):
        # Downstream work is valid after the first failure, so a retry cannot hide
        # behind another fixture exception or an exhausted side-effect sequence.
        attempts=[]
        def invoke(*args,**kwargs):
            attempts.append((args,kwargs))
            if len(attempts)==1:raise error
            return callback(*args,**kwargs)
        return Mock(side_effect=invoke)

    def test_input_first_errors_escape_without_retry_or_evidence(self):
        for mode in ('load','owned','prepared','extraction'):
            with self.subTest(mode=mode):
                f=self.fresh();error=RuntimeError(mode)
                if mode=='load':
                    failed=self.fail_once(f.service.load,error);f.service.load=failed
                elif mode=='owned':
                    failed=self.fail_once(f.service.records.owned(),error)
                    f.service.records=replace(f.service.records,owned=lambda:failed)
                elif mode=='prepared':
                    f.standard['confirmed_assets'][0]['preparation']={'id':'prepared'}
                    failed=self.fail_once(f.service.prepared_submit,error);f.service.prepared_submit=failed
                else:
                    failed=self.fail_once(f.service.resolve_extraction,error);f.service.resolve_extraction=failed
                with self.assertRaises(RuntimeError) as caught:f.compare(extraction='extract' if mode=='extraction' else '')
                self.assertIs(caught.exception,error);self.assertEqual(failed.call_count,1)
                self.assertEqual(f.calls,[]);self.assertEqual(f.save_count,0);self.assertEqual(f.files,[])
                self.assertEqual(f.rows,[]);self.assertEqual(f.logged,[])

    def test_postprocessing_and_evidence_first_errors_keep_original_settlement(self):
        for mode in ('normalize','validate','annotate','source-write','annotation-write','input-event','provider-event'):
            with self.subTest(mode=mode):
                f=self.fresh();error=RuntimeError(mode)
                if mode in ('normalize','validate'):
                    failed=self.fail_once((getattr(f.service.models,mode)() if mode=='normalize' else getattr(f.service.models,mode)),error)
                    f.service.models=replace(f.service.models,**{mode:(lambda:failed) if mode=='normalize' else failed})
                elif mode=='annotate':
                    failed=self.fail_once(f.service.images.annotate(),error)
                    f.service.images=replace(f.service.images,annotate=lambda:failed)
                elif mode.endswith('-write'):
                    original=f.service.media.write;failed=self.fail_once(original,error)
                    def write(path,data):
                        selected=('annotated' in path.name) if mode=='annotation-write' else ('source' in path.name)
                        return failed(path,data) if selected else original(path,data)
                    f.service.media=replace(f.service.media,write=write)
                else:
                    original=f.service.diagnostics.event();failed=self.fail_once(original,error)
                    def event(record,stage,status,**kwargs):
                        selected=stage=='input_prepared' if mode=='input-event' else stage=='provider_call' and status=='ok'
                        return failed(record,stage,status,**kwargs) if selected else original(record,stage,status,**kwargs)
                    f.service.diagnostics=replace(f.service.diagnostics,event=lambda:event)
                if mode in ('source-write','input-event'):
                    with self.assertRaises(RuntimeError) as caught:f.compare()
                    self.assertIs(caught.exception,error);self.assertEqual(f.calls,[])
                    self.assertEqual(f.save_count,0);self.assertEqual(f.rows,[]);self.assertEqual(f.files,[])
                    self.assertEqual(f.logged,[])
                else:
                    result=f.compare();self.assertEqual(result['status'],'uncertain')
                    self.assertEqual(result['charge_status'],'uncertain');self.assertEqual(result['error_code'],'RuntimeError')
                    stage='response_validation' if mode in ('normalize','validate') else 'provider_call' if mode=='provider-event' else 'annotation'
                    self.assertEqual(result['diagnostics']['failure'],{'stage':stage,'error_type':'RuntimeError','message':mode})
                    self.assertEqual(len(f.calls),1);self.assertEqual(f.save_count,3)
                    self.assertEqual(len(f.files),1);self.assertEqual(f.files[0].read_bytes(),b'captured')
                    self.assertEqual(f.rows[0]['status'],'uncertain');self.assertEqual(len(f.logged),1)
                    repeat=f.compare();self.assertEqual(repeat['id'],result['id']);self.assertEqual(len(f.calls),1)
                    self.assertEqual(f.save_count,3);self.assertEqual(len(f.logged),1)
                self.assertEqual(failed.call_count,1)

    def test_review_and_verified_read_first_errors_preserve_prior_state(self):
        for mode in ('owned','audit','verified'):
            with self.subTest(mode=mode):
                f=self.fresh();f.rows=[dict(id='inspection',owner_user_id='alice',standard_id='std',source_path='source',source_sha256='hash')]
                before=copy.deepcopy(f.rows);error=RuntimeError(mode);reads=[]
                async def body():reads.append(1);return {'decision':'PASS','reason':'approved'}
                if mode=='owned':
                    failed=self.fail_once(f.reviews.records.owned(),error)
                    f.reviews.records=replace(f.reviews.records,owned=lambda:failed)
                elif mode=='audit':
                    failed=self.fail_once(f.reviews.audit(),error);f.reviews.audit=lambda:failed
                else:
                    failed=self.fail_once(f.reviews.read_verified(),error);f.reviews.read_verified=lambda:failed
                with self.assertRaises(RuntimeError) as caught:
                    if mode=='verified':f.routes.get_text_inspection_v2_evidence('inspection','source')
                    else:asyncio.run(f.reviews.review_text_inspection_v2('inspection',body))
                self.assertIs(caught.exception,error);self.assertEqual(failed.call_count,1)
                self.assertEqual(f.audits,[]);self.assertEqual(f.calls,[])
                if mode=='audit':
                    self.assertEqual(f.save_count,1);self.assertEqual(f.rows[0]['final_decision'],'PASS');self.assertEqual(reads,[1])
                else:
                    self.assertEqual(f.save_count,0);self.assertEqual(f.rows,before);self.assertEqual(reads,[])

    def test_prepared_branch_and_extraction_limits_precede_legacy_work(self):
        f=self.f;f.standard['confirmed_assets'][0]['preparation']={'id':'prepared'};f.qwen=True
        result=f.compare();self.assertEqual(result,{'prepared':True});self.assertEqual(f.calls,[])
        self.assertFalse(any(e[0] in {'prepare','load','settings','write'} for e in f.events))
        self.assertEqual(f.prepared.call_args.args[6],'comparison-01')
        f.standard['confirmed_assets'][0].pop('preparation');f.qwen=False
        upload=Upload();f.compare(upload);self.assertEqual(upload.reads,[10*1024*1024+1])
        self.assertIn(('prepare',b'captured',{'max_bytes':10*1024*1024}),f.events)
        self.assertIn(('asset_bytes','snapshot-hash','alice'),f.events)
        f=self.fresh();f.compare(extraction='extract')
        self.assertIn(('prepare',b'extracted',{'max_bytes':100*1024*1024}),f.events)
        self.assertEqual(f.rows[0]['fingerprint_components']['extraction_id'],'extract')
    def test_exact_fingerprint_payload_and_durable_single_model_call(self):
        f=self.f;result=f.compare();self.assertEqual(result['decision'],'MATCH');self.assertEqual(len(f.calls),1)
        fields=dict(reference_sha256=f.digest(b'reference'),reference_bytes=9,prepared_reference_sha256=f.digest(b'reference'),prepared_reference_bytes=9,
            captured_upload_sha256=f.digest(b'captured'),captured_upload_bytes=8,captured_sha256=f.digest(b'captured'),captured_bytes=8,
            standard_asset_id='asset',provider='provider',standard_revision_id='rev1',standard_revision_number=1,model='model',prompt_version='business-prompt-v1',schema_version='text-compare-result-v1')
        self.assertEqual(result['fingerprint_components'],fields)
        self.assertEqual(result['fingerprint'],f.digest(json.dumps(fields,sort_keys=True,separators=(',',':')).encode()))
        name,args=f.calls[0];self.assertEqual(name,'provider.gemini.generate_json')
        self.assertEqual(args['system_prompt'],'unchanged-prompt');self.assertEqual(args['max_tokens'],1800);self.assertEqual(args['max_attempts'],1)
        self.assertEqual(args['provider_config']['timeout_seconds'],30)
        self.assertEqual(args['user_content'],[{'type':'text','text':'STANDARD_LABEL'},{'type':'image_url','image_url':{'url':'fixture:reference','detail':'high'}},{'type':'text','text':'CAPTURED_LABEL'},{'type':'image_url','image_url':{'url':'fixture:captured','detail':'high'}}])
        events=[e[0] for e in f.events];call=events.index('call');self.assertEqual([e[1] for e in f.events[:call] if e[0]=='save'],[1,2])
        f.events=[];repeat=f.compare();self.assertEqual(repeat['id'],result['id']);self.assertEqual(len(f.calls),1)
        self.assertLess(next(i for i,e in enumerate(f.events) if e[0]=='settings'),next(i for i,e in enumerate(f.events) if e[0]=='load'))
        f.rows[0]['status']='attempting';repeat=f.compare();self.assertEqual(repeat['decision'],'REVIEW_REQUIRED');self.assertIn('message',repeat);self.assertEqual(len(f.calls),1)
        f.rows[0]['fingerprint']='changed'
        with self.assertRaises(HTTPException) as error:f.compare()
        self.assertEqual(error.exception.status_code,409);self.assertEqual(len(f.calls),1)
    def test_insert_loser_and_input_build_failure_keep_attempt_evidence(self):
        for outcome in ['same','conflict','missing']:
            f=self.fresh();f.insert_loser=outcome
            if outcome=='same':
                result=f.compare();self.assertEqual(result['id'],'winner');self.assertEqual(result['status'],'attempting');self.assertNotIn('message',result)
            else:
                with self.assertRaises(HTTPException) as error:f.compare()
                self.assertEqual(error.exception.status_code,409)
            self.assertEqual(f.calls,[]);self.assertEqual(len(f.files),1);self.assertTrue(f.files[0].exists())
        f=self.f;f.fail_stage='data_url'
        with self.assertRaisesRegex(RuntimeError,'data_url'):f.compare()
        self.assertEqual(f.rows[0]['status'],'attempting');self.assertEqual(f.save_count,1);self.assertEqual(f.calls,[])
    def test_provider_validation_annotation_and_write_failures_never_replay(self):
        for stage in ['provider','provider_false','validation','annotation','annotation_write']:
            f=self.fresh();f.fail_stage=stage
            if stage=='provider_false':f.provider={'ok':False,'error':'failed','error_type':'ProviderUnavailable'}
            result=f.compare();self.assertEqual(result['status'],'uncertain',stage);self.assertEqual(result['charge_status'],'uncertain');self.assertEqual(len(f.calls),1)
            self.assertEqual(result['external_media_send_status'],'uncertain');self.assertIsNone(result['external_media_sent'])
            if stage=='provider_false':self.assertEqual(result['error_code'],'ProviderUnavailable')
            f.compare();self.assertEqual(len(f.calls),1)
    def test_second_and_final_save_logger_and_admission_boundaries(self):
        f=self.f;f.fail_save[2]=RuntimeError('second');result=f.compare();self.assertEqual(result['status'],'uncertain');self.assertEqual(f.calls,[])
        f=self.fresh();f.fail_save[2]=False;self.assertEqual(f.compare()['decision'],'MATCH');self.assertEqual(len(f.calls),1)
        f=self.fresh();f.fail_save[3]=RuntimeError('final')
        with self.assertRaisesRegex(RuntimeError,'final'):f.compare()
        self.assertEqual(len(f.calls),1);self.assertEqual(f.rows[0]['status'],'attempting');self.assertEqual(f.logged,[])
        repeat=f.compare();self.assertEqual(repeat['decision'],'REVIEW_REQUIRED')
        self.assertEqual(repeat['status'],'attempting');self.assertEqual(len(f.calls),1);self.assertEqual(f.logged,[])
        f=self.fresh();f.fail_stage='logger'
        with self.assertRaisesRegex(RuntimeError,'logger'):f.compare()
        self.assertEqual(f.rows[0]['status'],'completed');self.assertEqual(len(f.calls),1)
        repeat=f.compare();self.assertEqual(repeat['status'],'completed')
        self.assertEqual(len(f.calls),1);self.assertEqual(len(f.logged),1)
        f=self.fresh();f.external=False;result=f.compare();self.assertEqual(result['external_media_send_status'],'not_sent');self.assertEqual(f.calls,[]);self.assertEqual(f.save_count,2);self.assertEqual(len(f.files),1)
        f=self.fresh();f.match=False;result=f.compare();self.assertEqual(result['decision'],'REVIEW_REQUIRED');self.assertEqual(result['status'],'review_required');self.assertEqual(len(f.calls),1)
    def test_review_read_order_save_audit_partial_failure_and_evidence(self):
        f=self.f;f.rows=[dict(id='inspection',owner_user_id='alice',standard_id='std',source_path='source',source_sha256='hash')];reads=[]
        async def body():reads.append(1);return {'decision':'PASS','reason':' approved '}
        def review():return asyncio.run(f.reviews.review_text_inspection_v2('inspection',body))
        f.owner='other'
        with self.assertRaises(HTTPException) as error:review()
        self.assertEqual(error.exception.status_code,404);self.assertEqual(reads,[])
        f.owner='alice';f.standard['standard_type']='manual'
        with self.assertRaises(HTTPException) as error:review()
        self.assertEqual(error.exception.status_code,410);self.assertEqual(reads,[]);f.standard.pop('standard_type')
        f.fail_save[1]=False;result=review();self.assertEqual(result['review_reason'],'approved');self.assertEqual(len(f.audits),1);self.assertNotIn('final_decision',f.rows[0])
        f.fail_save[2]=RuntimeError('save')
        with self.assertRaisesRegex(RuntimeError,'save'):review()
        self.assertEqual(len(f.audits),1)
        f.fail_stage='audit'
        with self.assertRaisesRegex(RuntimeError,'audit'):review()
        self.assertEqual(f.rows[0]['final_decision'],'PASS')
        response=f.routes.get_text_inspection_v2_evidence('inspection','source')
        self.assertEqual(response.media_type,'image/png');self.assertEqual(response.headers['cache-control'],'private, no-store')
        self.assertEqual(f.events[-1],('verified','source','alice','std',{'expected_sha256':'hash','max_bytes':20*1024*1024}))
        with self.assertRaises(HTTPException) as error:f.routes.get_text_inspection_v2_evidence('inspection','other')
        self.assertEqual(error.exception.status_code,404)
    def test_legacy_http_permission_validation_and_no_body_consumption(self):
        f=self.f
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=f.app),base_url='http://fixture') as client:
                responses=[await client.post('/api/text-inspection/manual/sessions',content=b'invalid-json'),
                    await client.post('/api/text-inspection/manual/sessions/id/pages',files={'captured_file':('x.png',b'x')},data={'capture_id':'id'}),
                    await client.post('/api/text-inspection/manual/sessions/id/complete')]
                self.assertEqual([r.status_code for r in responses],[410,410,410])
                missing=await client.post('/api/text-inspection/manual/sessions/id/pages');self.assertEqual(missing.status_code,422)
                f.owner='denied';denied=await client.post('/api/text-inspection/manual/sessions',content=b'invalid-json');self.assertEqual(denied.status_code,403)
        asyncio.run(run());self.assertEqual(f.calls,[]);self.assertEqual(f.save_count,0)
    @unittest.skipUnless(ROOT_CHECK,'use --root for application composition')
    def test_root_prepared_submission_captures_callbacks_per_call(self):
        os.environ.update(LOCAL_INSPECTION_ROOT=str(Path(self.temp.name)/'runtime'),VANTALINE_DATA_STORE='json',VANTALINE_LABEL_INSPECTION_ENABLED='false',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0')
        (Path(os.environ['LOCAL_INSPECTION_ROOT'])/'local_inspection_service/static').mkdir(parents=True)
        from local_inspection_service import server, standard_preparation_compare
        captures=[]
        names=['_text_v2_load','_text_v2_save','_text_v2_owned','_text_v2_update_attempt','_text_v2_public','_text_v2_media_path','_text_v2_write','sha256_bytes','ai_detection_settings','record_model_call','clear_thread_runtime_repository_selection']
        first={name:Mock(name='first-'+name) for name in names};second={name:Mock(name='second-'+name) for name in names}
        first_jobs=object();second_jobs=object();env_a={'key':'A'};env_b={'key':'B'}
        environment_a=Mock();environment_a.getenv=lambda key,default:env_a.get(key,default)
        environment_b=Mock();environment_b.getenv=lambda key,default:env_b.get(key,default)
        with patch.object(standard_preparation_compare,'submit',side_effect=lambda *args:captures.append(args) or {'captured':True}):
            for callbacks,flag,jobs,environment in [(first,True,first_jobs,environment_a),(second,False,second_jobs,environment_b)]:
                with patch.multiple(server,**callbacks,TEXT_INSPECTION_EXTERNAL_VLM_ENABLED=flag,standard_preparation_jobs=jobs,os=environment):
                    server._submit_prepared_text_comparison('owner','name',{}, {}, {},b'upload','request',None)
        a,b=captures;self.assertIs(a[0].load,first['_text_v2_load']);self.assertIs(b[0].load,second['_text_v2_load'])
        for captured,callbacks,jobs,flag in [(a,first,first_jobs,True),(b,second,second_jobs,False)]:
            for attr,name in [('save','_text_v2_save'),('owned','_text_v2_owned'),('update_attempt','_text_v2_update_attempt'),('public','_text_v2_public')]:self.assertIs(getattr(captured[0],attr),callbacks[name])
            self.assertIs(captured[1].path,callbacks['_text_v2_media_path']);self.assertIs(captured[1].write,callbacks['_text_v2_write']);self.assertIs(captured[1].digest,callbacks['sha256_bytes'])
            self.assertIs(captured[2].settings,callbacks['ai_detection_settings']);self.assertIs(captured[2].record_usage,callbacks['record_model_call']);self.assertIs(captured[2].external_enabled,flag)
            self.assertIs(captured[3],callbacks['clear_thread_runtime_repository_selection']);self.assertIs(captured[5],jobs)
        env_a['key']='later';self.assertEqual(a[4]('key',''),'later');self.assertEqual(b[4]('key',''),'B')


if __name__=='__main__':unittest.main(verbosity=2)
