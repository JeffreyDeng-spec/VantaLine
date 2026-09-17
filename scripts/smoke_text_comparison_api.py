"""Synthetic paid-call, evidence and review boundaries; no provider or PLC calls."""
import asyncio
import copy
from contextlib import ExitStack
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi import FastAPI, HTTPException
from local_inspection_service.text_inspection.comparison_submission import ComparisonSubmission
from local_inspection_service.text_inspection.inspection_api import register
from local_inspection_service.text_inspection.inspection_reviews import InspectionReviews
from local_inspection_service.text_inspection.inspection_ports import (
    InspectionAccess, InspectionRecords, SubmissionPolicy, SubmissionImages,
    SubmissionModels, SubmissionDiagnostics,
)
from local_inspection_service.text_inspection.comparison_ports import ComparisonMedia
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
        self.records=InspectionRecords(self.owned,self.save,lambda row:copy.deepcopy(row))
        self.service=ComparisonSubmission(self.access,self.records,self.load,
            ComparisonMedia(lambda owner,standard,name:self.directory/name,self.write,self.digest),
            SubmissionImages(self.prepare,lambda data,mime:(data,mime,'PNG'),self.asset_bytes,self.annotate,self.data_url),
            SubmissionModels(lambda purpose:self.setting(purpose),self.call,lambda:'unchanged-prompt',lambda value,provider:self.normalize(value,provider),self.validate),
            SubmissionPolicy(lambda:30,lambda:'business-prompt-v1',lambda:self.external,lambda:self.match,lambda owner:self.qwen),
            SubmissionDiagnostics(lambda data,**kwargs:{'sha256':self.digest(data)},diagnostic_event,
                                  lambda provider,settings:copy.deepcopy(provider),diagnostic_value,self.log),
            self.prepared,self.extraction,lambda standard,asset:{'display':'fixture'})
        self.reviews=InspectionReviews(self.access,self.records,self.read_verified,self.audit,lambda value,limit:str(value or '')[:limit])
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


class SubmissionContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='comparison-');self.addCleanup(self.temp.cleanup)
        self.f=Fixture(self.temp.name)
    def fresh(self):
        folder=Path(self.temp.name)/str(len(list(Path(self.temp.name).iterdir())));folder.mkdir();return Fixture(folder)
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
