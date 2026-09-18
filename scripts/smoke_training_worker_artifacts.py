"""Synthetic legacy worker artifact import contracts; no models are loaded."""
from contextlib import ExitStack
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, call, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def _capture_worker_artifact_window(ns,site,mode,directory=None):
 events=[];field='output_write_dir_for_owner' if site=='owner' else 'safe_name'
 def called(label):
  def callback(*args):events.append(label);return output if site=='owner' else 'saved.pt'
  return callback
 a,b,c=called('A'),called('B'),called('C')
 def prior():events.append('prior');ns[field]=a if mode=='ordinary' else b if mode=='prior' else None
 def argument():events.append('argument');ns[field]=c
 with tempfile.TemporaryDirectory(prefix='worker-artifact-capture-',dir=directory) as tmp:
  root=Path(tmp);output=root/'runs';run=output/'job';weights=run/'weights';payload=b'fixture-model';digest=hashlib.sha256(payload).hexdigest()
  task={'job_id':'job','owner_user_id':'owner'};model={'artifact_b64':base64.b64encode(payload).decode(),'artifact_filename':'input.pt','artifact_sha256':digest}
  ns.update(time=types.SimpleNamespace(time=lambda:11),output_write_dir_for_owner=lambda *args:output,safe_name=lambda value:'saved.pt');ns[field]=a
  realsha=hashlib.sha256;realmkdir=Path.mkdir;prior_done=[]
  def sha(data):
   actual=realsha(data)
   class Hash:
    def hexdigest(self):
     if site=='owner':prior()
     return actual.hexdigest()
   return Hash()
  def mkdir(path,*args,**kw):
   value=realmkdir(path,*args,**kw)
   if site=='safe' and path==weights and not prior_done:prior_done.append(1);prior()
   return value
  if site=='owner':
   class Task(dict):
    def get(self,key,default=None):
     if key=='owner_user_id':argument()
     return super().get(key,default)
   task=Task(task)
  else:
   class Model(dict):
    def get(self,key,default=None):
     if key=='artifact_filename':argument()
     return super().get(key,default)
   model=Model(model)
  caught=None
  with patch.object(hashlib,'sha256',side_effect=sha),patch.object(Path,'mkdir',autospec=True,side_effect=mkdir):
   try:ns['import_worker_training_artifacts'](task,{'models':[model]})
   except BaseException as error:caught=error
  if mode=='missing':
   assert type(caught)is TypeError,(caught,events)
   assert weights.exists()==(site=='safe')
   if weights.exists():assert list(weights.iterdir())==[]
  else:
   assert caught is None,(caught,events)
   assert (weights/'saved.pt').read_bytes()==payload
   assert (weights/'best.pt').read_bytes()==payload
  assert events==['prior','argument']+([] if mode=='missing' else ['A' if mode=='ordinary' else 'B']),events
 return events


class ArtifactFixture:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.output=self.root/'runs';self.events=[]
        self.payload=b'synthetic model bytes\x00\xff';self.digest=hashlib.sha256(self.payload).hexdigest()
        self.task={'job_id':' job ','task_id':'fallback','owner_user_id':'owner','label':'Task title','pipeline_task_id':4,'pipeline_task_name':'Pipe','remote_training_job_id':{'raw':'alias'}}
        self.model={'artifact_b64':base64.b64encode(self.payload).decode(),'artifact_sha256':' '+self.digest.upper()+' ','artifact_filename':'source.pt','label':'Artifact title'}
        self.artifacts={'models':[self.model]};self.owner=Mock(side_effect=lambda *args:self.event('owner') or self.output)
        self.safe=Mock(side_effect=lambda value:self.event('safe') or 'saved.pt');self.clock_values=iter([123.9,456.9,789.9,900.9]);self.clock=Mock(side_effect=lambda:self.event('clock') or next(self.clock_values))
    def event(self,name):self.events.append(name)
    def bind(self,api,stack):
        stack.enter_context(patch.object(api,'output_write_dir_for_owner',self.owner));stack.enter_context(patch.object(api,'safe_name',self.safe));stack.enter_context(patch('time.time',self.clock))
    @property
    def run(self):return self.output/'job'


class TrainingWorkerArtifactContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ);cls.environment.start();cls.runtime=tempfile.TemporaryDirectory(prefix='worker-artifact-root-')
        root=Path(cls.runtime.name);(root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.runtime.cleanup();cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close);self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='worker-artifact-')));self.sequence=0;self.f=self.fixture()
        for target in ['requests.request','requests.get','requests.post','subprocess.Popen','os.kill']:
            self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected external operation')))
    def fixture(self):
        self.sequence+=1;f=ArtifactFixture(self.root/str(self.sequence));f.bind(self.api,self.stack);return f
    def run_import(self):return self.api.import_worker_training_artifacts(self.f.task,self.f.artifacts)
    def test_real_files_exact_metadata_and_two_clock_order(self):
        f=self.f;result=self.run_import();f.owner.assert_called_once_with('training_runs','owner');f.safe.assert_called_once_with('source.pt')
        self.assertEqual(f.events,['owner','safe','clock','clock']);self.assertEqual((f.run/'weights/saved.pt').read_bytes(),f.payload);self.assertEqual((f.run/'weights/best.pt').read_bytes(),f.payload)
        metadata={'display_name':'Task title','note':'Imported from Windows Worker transfer result.','pipeline_task_id':'4','pipeline_task_name':'Pipe','worker_job_id':{'raw':'alias'},'worker_artifact_sha256':f.digest,'updated_at':123}
        self.assertEqual((f.run/'library_metadata.json').read_text(encoding='utf-8'),json.dumps(metadata,indent=2))
        self.assertEqual(result,{'worker_artifacts_imported_at':456,'worker_artifact_import_error':'','training_run_dir':str(f.run),'imported_model_path':str(f.run/'weights/best.pt'),'worker_artifact_sha256':f.digest})
        self.assertEqual(f.model['artifact_sha256'],' '+f.digest.upper()+' ');self.assertEqual(f.task['remote_training_job_id'],{'raw':'alias'})
    def test_early_returns_are_truthy_and_ordered_before_any_io(self):
        f=self.f
        for task in [{'worker_artifacts_imported_at':1},{'worker_artifacts_imported_at':'0'},{'job_id':'   ','task_id':'fallback'},{'job_id':0},{'task_id':''},{}]:
            f.task=task;f.artifacts=None;self.assertEqual(self.run_import(),{})
        f.task={'job_id':'job'}
        for models in [[],[None,1,{}, {'artifact_b64':''},{'artifact_b64':'  '},{'artifact_b64':0}]]:
            f.artifacts={'models':models};self.assertEqual(self.run_import(),{})
        f.owner.assert_not_called();f.safe.assert_not_called();f.clock.assert_not_called();self.assertFalse(f.output.exists())
    def test_models_container_errors_propagate_and_only_first_eligible_is_used(self):
        f=self.f;f.artifacts={'models':None}
        with self.assertRaises(TypeError):self.run_import()
        bad={'artifact_b64':'not base64'};f.artifacts={'models':[None,{},bad,f.model]}
        self.assertEqual(self.run_import(),{'worker_artifact_import_error':'Worker model artifact payload is not valid base64'});f.owner.assert_not_called()
        f.artifacts={'models':[dict(f.model,artifact_sha256='wrong'),f.model]}
        self.assertEqual(self.run_import(),{'worker_artifact_import_error':'Worker model artifact checksum mismatch'});f.owner.assert_not_called()
    def test_strict_base64_optional_checksum_and_payload_edges(self):
        for encoded in [' '+base64.b64encode(b'x').decode(),base64.b64encode(b'x').decode()+'\n','%%%%','你好']:
            self.f=self.fixture();f=self.f;f.model['artifact_b64']=encoded
            self.assertEqual(self.run_import(),{'worker_artifact_import_error':'Worker model artifact payload is not valid base64'});f.owner.assert_not_called()
        for expected in ['',None,0]:
            self.f=self.fixture();f=self.f;f.model['artifact_sha256']=expected;f.task['worker_artifacts_imported_at']=0
            self.assertEqual(self.run_import()['worker_artifact_sha256'],f.digest)
        f=self.f
        with patch('base64.b64decode',side_effect=TypeError('provider error')) as decode:
            with self.assertRaises(TypeError):self.run_import()
            decode.assert_called_once_with(f.model['artifact_b64'],validate=True)
    def test_filename_suffix_defaults_and_copy_only_for_non_best_name(self):
        for filename,expected,copy_count in [('best.pt','best.pt',0),('custom.pt','custom.pt',1),('CUSTOM.PT','best.pt',0),('model.bin','best.pt',0),('','best.pt',0)]:
            self.f=self.fixture();f=self.f;f.safe.side_effect=None;f.safe.return_value=filename
            with patch('shutil.copyfile',wraps=shutil.copyfile) as copy:
                result=self.run_import();self.assertEqual(copy.call_count,copy_count)
            self.assertEqual((f.run/'weights'/expected).read_bytes(),f.payload);self.assertEqual(Path(result['imported_model_path']).name,'best.pt')
            self.assertEqual(set(p.name for p in (f.run/'weights').iterdir()),{expected,'best.pt'})
        self.f=self.fixture();f=self.f;f.model['artifact_filename']=0;f.task={'job_id':0,'task_id':' job ','owner_user_id':0,'label':''};f.model['label']=''
        self.run_import();f.safe.assert_called_once_with('best.pt');f.owner.assert_called_once_with('training_runs','')
        metadata=json.loads((f.run/'library_metadata.json').read_text());self.assertEqual(metadata['display_name'],'job');self.assertEqual(metadata['pipeline_task_id'],'');self.assertIsNone(metadata['worker_job_id'])
    def test_display_label_priority_keeps_non_string_values(self):
        for task_label,model_label,expected in [('',{'raw':'model'},{'raw':'model'}),({'raw':'task'},'model',{'raw':'task'}),(0,0,'job')]:
            self.f=self.fixture();f=self.f;f.task['label']=task_label;f.model['label']=model_label;self.run_import()
            self.assertEqual(json.loads((f.run/'library_metadata.json').read_text())['display_name'],expected)
    def test_owner_mkdir_and_safe_failures_preserve_creation_order_without_retry(self):
        for stage in ['owner','mkdir','safe']:
            self.f=self.fixture();f=self.f;error=OSError(stage)
            with ExitStack() as stack:
                hits=[]
                def first(callback):
                    def invoke(*args,**kwargs):
                        hits.append(stage)
                        if len(hits)==1:raise error
                        return callback(*args,**kwargs)
                    return invoke
                if stage=='mkdir':target=stack.enter_context(patch.object(Path,'mkdir',autospec=True,side_effect=first(Path.mkdir)))
                else:target=getattr(f,stage);target.side_effect=first(target.side_effect)
                with self.assertRaises(OSError) as caught:self.run_import()
            self.assertIs(caught.exception,error);target.assert_called_once();f.clock.assert_not_called()
            if stage=='safe':self.assertTrue((f.run/'weights').is_dir());self.assertEqual(list((f.run/'weights').iterdir()),[])
            else:f.safe.assert_not_called();self.assertFalse(f.output.exists())
    def test_write_bytes_partial_failure_is_not_retried_or_rolled_back(self):
        f=self.f;original=Path.write_bytes;error=OSError('partial write');calls=[]
        def write(path,data):
            calls.append((path,data))
            if len(calls)==1:original(path,data[:4]);raise error
            return original(path,data)
        with patch.object(Path,'write_bytes',autospec=True,side_effect=write),patch('shutil.copyfile',wraps=shutil.copyfile) as copy:
            with self.assertRaises(OSError) as caught:self.run_import()
            self.assertIs(caught.exception,error);copy.assert_not_called()
        self.assertEqual(calls,[(f.run/'weights/saved.pt',f.payload)]);self.assertEqual((f.run/'weights/saved.pt').read_bytes(),f.payload[:4]);self.assertFalse((f.run/'weights/best.pt').exists());f.clock.assert_not_called()
    def test_copy_partial_failure_keeps_written_model_and_partial_best(self):
        f=self.f;error=OSError('partial copy');original=shutil.copyfile;calls=[]
        def copy(source,target):
            calls.append((source,target))
            if len(calls)==1:Path(target).write_bytes(Path(source).read_bytes()[:3]);raise error
            return original(source,target)
        with patch('shutil.copyfile',side_effect=copy):
            with self.assertRaises(OSError) as caught:self.run_import()
        self.assertIs(caught.exception,error);self.assertEqual(calls,[(f.run/'weights/saved.pt',f.run/'weights/best.pt')]);self.assertEqual((f.run/'weights/saved.pt').read_bytes(),f.payload)
        self.assertEqual((f.run/'weights/best.pt').read_bytes(),f.payload[:3]);f.clock.assert_not_called();self.assertFalse((f.run/'library_metadata.json').exists())
    def test_metadata_and_second_clock_failures_preserve_prior_files(self):
        for stage in ['clock1','json','write_text','clock2']:
            self.f=self.fixture();f=self.f;error=OSError(stage);calls=[];original=Path.write_text
            with ExitStack() as stack:
                if stage in ['clock1','clock2']:
                    ticks=[]
                    def clock():
                        ticks.append(1)
                        if len(ticks)==(1 if stage=='clock1' else 2):raise error
                        return 123.9 if len(ticks)==1 else 999
                    f.clock.side_effect=clock
                elif stage=='json':target=stack.enter_context(patch('json.dumps',side_effect=[error,'second success']))
                else:
                    def write(path,data,*args,**kwargs):
                        calls.append((path,data,args,kwargs))
                        if len(calls)==1:original(path,data[:7],*args,**kwargs);raise error
                        return original(path,data,*args,**kwargs)
                    target=stack.enter_context(patch.object(Path,'write_text',autospec=True,side_effect=write))
                with self.assertRaises(OSError) as caught:self.run_import()
                if stage in ['json','write_text']:target.assert_called_once()
            self.assertIs(caught.exception,error);self.assertEqual((f.run/'weights/saved.pt').read_bytes(),f.payload);self.assertEqual((f.run/'weights/best.pt').read_bytes(),f.payload)
            metadata_path=f.run/'library_metadata.json'
            if stage in ['clock1','json']:self.assertFalse(metadata_path.exists())
            elif stage=='write_text':self.assertEqual(metadata_path.read_text(),calls[0][1][:7]);self.assertEqual(calls[0][3],{'encoding':'utf-8'})
            else:self.assertEqual(json.loads(metadata_path.read_text())['updated_at'],123)
            self.assertEqual(f.clock.call_count,2 if stage=='clock2' else 1)


    def test_existing_files_are_overwritten_without_mutating_inputs_or_trimming_owner(self):
        f=self.f;f.task['owner_user_id']=' owner ';before_task=copy.deepcopy(f.task);before_artifacts=copy.deepcopy(f.artifacts)
        weights=f.run/'weights';weights.mkdir(parents=True);(weights/'saved.pt').write_bytes(b'old model');(weights/'best.pt').write_bytes(b'old best');(f.run/'library_metadata.json').write_text('old metadata')
        model=f.model;models=f.artifacts['models'];remote=f.task['remote_training_job_id'];result=self.run_import()
        f.owner.assert_called_once_with('training_runs',' owner ');self.assertEqual((weights/'saved.pt').read_bytes(),f.payload);self.assertEqual((weights/'best.pt').read_bytes(),f.payload)
        self.assertEqual(json.loads((f.run/'library_metadata.json').read_text())['updated_at'],123);self.assertEqual(result['imported_model_path'],str(weights/'best.pt'))
        self.assertEqual(f.task,before_task);self.assertEqual(f.artifacts,before_artifacts);self.assertIs(f.model,model);self.assertIs(f.artifacts['models'],models);self.assertIs(f.task['remote_training_job_id'],remote)
    def test_unserializable_metadata_keeps_written_weights_and_previous_metadata(self):
        for field in ['label','remote_training_job_id','artifact_label']:
            self.f=self.fixture();f=self.f;f.run.mkdir(parents=True);metadata_path=f.run/'library_metadata.json';metadata_path.write_text('prior metadata')
            if field=='artifact_label':f.task['label']='';f.model['label']={'not-json'}
            else:f.task[field]={'not-json'}
            with self.assertRaises(TypeError):self.run_import()
            self.assertEqual((f.run/'weights/saved.pt').read_bytes(),f.payload);self.assertEqual((f.run/'weights/best.pt').read_bytes(),f.payload)
            self.assertEqual(metadata_path.read_text(),'prior metadata');f.clock.assert_called_once();f.owner.assert_called_once();f.safe.assert_called_once()


    def test_independent_importers_interleave_real_files_and_separate_owner_naming_clocks(self):
        from local_inspection_service.training.worker_artifacts import WorkerArtifactImport
        instances=[]
        for index,owner in enumerate(['alice','bob']):
            f=ArtifactFixture(self.root/owner);f.task['owner_user_id']=owner;f.payload=owner.encode();f.digest=hashlib.sha256(f.payload).hexdigest()
            f.model['artifact_b64']=base64.b64encode(f.payload).decode();f.model['artifact_sha256']=f.digest
            f.safe.side_effect=lambda value,owner=owner:owner+'.pt' if owner=='alice' else 'BEST.PT'
            f.clock_values=iter([123.9+index,456.9+index,789.9+index,900.9+index]);service=WorkerArtifactImport(lambda f=f:f.owner,lambda f=f:f.safe,f.clock)
            f.owner.assert_not_called();f.safe.assert_not_called();f.clock.assert_not_called();self.assertFalse(f.output.exists());self.assertEqual(f.events,[])
            instances.append((owner,f,service))
        for name in ['output_write_dir_for_owner','safe_name','import_worker_training_artifacts']:
            self.stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('unexpected root dependency')))
        self.stack.enter_context(patch('time.time',side_effect=AssertionError('unexpected global clock')))
        counts=[0,0]
        for index in [1,0,1,0]:
            owner,f,service=instances[index];before_task=copy.deepcopy(f.task);before_artifacts=copy.deepcopy(f.artifacts)
            result=service.import_worker_training_artifacts(f.task,f.artifacts);stamp=[456,900][counts[index]]+index;metadata_stamp=[123,789][counts[index]]+index;counts[index]+=1
            self.assertEqual(result['worker_artifacts_imported_at'],stamp);self.assertEqual(result['training_run_dir'],str(f.run));self.assertEqual(result['imported_model_path'],str(f.run/'weights/best.pt'))
            self.assertEqual((f.run/'weights/best.pt').read_bytes(),owner.encode());self.assertEqual(json.loads((f.run/'library_metadata.json').read_text())['updated_at'],metadata_stamp)
            self.assertEqual(set(path.name for path in (f.run/'weights').iterdir()),{'alice.pt','best.pt'} if owner=='alice' else {'best.pt'})
            self.assertEqual(f.owner.call_args,call('training_runs',owner));self.assertEqual(f.task,before_task);self.assertEqual(f.artifacts,before_artifacts)
        for owner,f,service in instances:
            self.assertEqual(f.owner.call_count,2);self.assertEqual(f.safe.call_count,2);self.assertEqual(f.clock.call_count,4)


    def test_missing_getters_fail_before_owner_or_filename_arguments_without_retry(self):
        from local_inspection_service.training.worker_artifacts import WorkerArtifactImport
        for site in ['owner','safe']:
            with self.subTest(site=site):
                self.f=self.fixture();f=self.f;hits=[];reads=[];error=OSError(site)
                def getter():
                    hits.append(site)
                    if len(hits)==1:raise error
                    return f.owner if site=='owner' else f.safe
                class Value:
                    def __str__(value):reads.append(site);return 'owner' if site=='owner' else 'source.pt'
                if site=='owner':f.task['owner_user_id']=Value()
                else:f.model['artifact_filename']=Value()
                service=WorkerArtifactImport(getter if site=='owner' else lambda:f.owner,getter if site=='safe' else lambda:f.safe,f.clock)
                with self.assertRaises(OSError) as caught:service.import_worker_training_artifacts(f.task,f.artifacts)
                self.assertIs(caught.exception,error);self.assertEqual(hits,[site]);self.assertEqual(reads,[]);f.safe.assert_not_called();f.clock.assert_not_called()
                self.assertEqual(f.owner.call_count,0 if site=='owner' else 1)
                self.assertEqual((f.run/'weights').exists(),site=='safe')
                self.assertFalse((f.run/'weights/best.pt').exists())

    def test_invalid_base64_returns_original_error_after_one_decode_attempt(self):
        f=self.f;original=base64.b64decode;hits=[]
        def decode(*args,**kwargs):
            hits.append(1)
            if len(hits)==1:raise ValueError('first decode')
            return original(*args,**kwargs)
        with patch.object(base64,'b64decode',side_effect=decode):
            self.assertEqual(self.run_import(),{'worker_artifact_import_error':'Worker model artifact payload is not valid base64'})
        self.assertEqual(hits,[1]);f.owner.assert_not_called();f.safe.assert_not_called();f.clock.assert_not_called();self.assertFalse(f.output.exists())


    def test_owner_and_filename_capture_preserve_prior_and_argument_order(self):
        for site in ('owner','safe'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(site=site,mode=mode),patch.dict(self.api.__dict__):
                    _capture_worker_artifact_window(self.api.__dict__,site,mode,self.root)

    def test_hash_failures_are_not_retried_or_followed_by_filesystem_writes(self):
        for site in ['sha256','hexdigest']:
            with self.subTest(site=site):
                self.f=self.fixture();f=self.f;error=OSError(site);hits=[];original=hashlib.sha256
                def first(callback):
                    def invoke(*args,**kwargs):
                        hits.append(site)
                        if len(hits)==1:raise error
                        return callback(*args,**kwargs)
                    return invoke
                if site=='sha256':callback=first(original)
                else:
                    def callback(data):return types.SimpleNamespace(hexdigest=first(original(data).hexdigest))
                with patch.object(hashlib,'sha256',side_effect=callback):
                    with self.assertRaises(OSError) as caught:self.run_import()
                self.assertIs(caught.exception,error);self.assertEqual(hits,[site]);f.owner.assert_not_called();f.safe.assert_not_called();f.clock.assert_not_called();self.assertFalse(f.output.exists())


if __name__=='__main__':unittest.main()
