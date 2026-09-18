"""Training user-state and completion propagation contracts with isolated storage ports."""
from contextlib import ExitStack
from itertools import chain, repeat
import asyncio
import copy
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def available(lock):
    values=[]
    def probe():
        acquired=lock.acquire(blocking=False);values.append(acquired)
        if acquired:lock.release()
    thread=threading.Thread(target=probe);thread.start();thread.join(timeout=5)
    if thread.is_alive():raise AssertionError('lock probe stalled')
    return values[0]


class Fixture:
    def __init__(self):
        self.defaults={'status':'idle','selected_accessory_ids':[],'nested':{'values':[]}}
        self.config={};self.task=None;self.pipeline=None;self.auto={'candidate_models':[]};self.events=[]
        self.pipeline_guard=threading.Lock();self.auto_guard=threading.RLock()
        self.find=Mock(side_effect=lambda job:self.event('find',job) or self.task)
        self.config_load=Mock(side_effect=lambda:self.event('config-load') or self.config)
        self.config_save=Mock(side_effect=lambda value:self.event('config-save',value))
        self.pipeline_load=Mock(side_effect=lambda key:self.event('pipeline-load',key) or self.pipeline)
        self.pipeline_save=Mock(side_effect=lambda value:self.event('pipeline-save',value))
        self.link=Mock(side_effect=lambda value:self.event('link',value))
        self.auto_load=Mock(side_effect=lambda key:self.event('auto-load',key) or self.auto)
        self.auto_save=Mock(side_effect=lambda value:self.event('auto-save',value))
        self.stop=Mock(side_effect=lambda *args,**kwargs:self.event('stop-capture',args,kwargs))
        self.models=Mock(side_effect=lambda:self.event('models') or [])
    def event(self,name,*args):self.events.append((name,available(self.pipeline_guard),available(self.auto_guard),args))
    def bind(self,api,stack):
        for name,value in {'DEFAULT_CONFIG':{'training':self.defaults},'find_training_task':self.find,'load_config':self.config_load,'save_config':self.config_save,
                '_pipeline_tasks_lock':self.pipeline_guard,'load_pipeline_task':self.pipeline_load,'save_pipeline_task':self.pipeline_save,
                'link_pipeline_trained_model':self.link,'_auto_optimize_lock':self.auto_guard,'load_auto_optimize_state':self.auto_load,
                'save_auto_optimize_state':self.auto_save,'auto_optimize_stop_capture_for_model_locked':self.stop,'list_trained_model_specs':self.models}.items():
            stack.enter_context(patch.object(api,name,value))


class TrainingStateContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ);cls.environment.start()
        cls.runtime=tempfile.TemporaryDirectory(prefix='training-state-root-');root=Path(cls.runtime.name)
        (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.runtime.cleanup();cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close);self.f=Fixture();self.f.bind(self.api,self.stack)
        token=self.api._request_user.set(None);self.addCleanup(self.api._request_user.reset,token)
        self.alice={'id':'alice','username':'Alice','role':'user'};self.admin={'id':'admin','role':'admin'}
        self.stack.enter_context(patch('requests.request',side_effect=AssertionError('unexpected network')))
        self.stack.enter_context(patch('os.kill',side_effect=AssertionError('unexpected process signal')))

    def test_default_json_clone_private_reset_and_owner_normalization(self):
        api=self.api;f=self.f;f.defaults['roundtrip']={1:(2,3)}
        first=api.default_training_state();second=api.default_training_state()
        self.assertEqual(first['roundtrip'],{'1':[2,3]});first['nested']['values'].append('x')
        self.assertEqual(second['nested']['values'],[]);self.assertEqual(f.defaults['nested']['values'],[])
        value={'private':True};self.assertIs(api.clear_training_private_state(value,'reason'),value)
        self.assertEqual(value,{'private':True,'preview_urls':[],'previews':[],'preview_cache_key':None,'preview_sprite_versions':{},
            'last_preview_id':'','approved_preview_id':'','active_training_task_id':'','preview_stale_reason':'reason'})
        for raw,wanted in [(' alice ','alice'),('',api.LEGACY_OWNER_ID),(None,api.LEGACY_OWNER_ID),(0,api.LEGACY_OWNER_ID),(4,'4')]:
            self.assertEqual(api.normalize_training_owner_key(raw),wanted)
        f.defaults['bad']=object()
        with self.assertRaises(TypeError):api.default_training_state()

    def test_store_replaces_container_preserves_records_collision_and_legacy(self):
        api=self.api;one={'status':'one'};two={'status':'two'};legacy={'owner_user_id':'alice','status':'legacy'}
        raw={' alice ':one,'alice':two,'invalid':None,' ':one};config={'training_by_user_id':raw,'training':legacy}
        result=api.training_state_store(config)
        self.assertIs(config['training_by_user_id'],result);self.assertIsNot(result,raw)
        self.assertEqual(list(result),['alice',api.LEGACY_OWNER_ID]);self.assertIs(result['alice'],two);self.assertIs(result[api.LEGACY_OWNER_ID],one)
        config={'training_by_user_id':[],'training':legacy};self.assertIs(api.training_state_store(config)['alice'],legacy)
        config={'training':{}};self.assertEqual(api.training_state_store(config),{});self.assertIn('training_by_user_id',config)

    def test_sanitize_visibility_in_place_and_user_views_shallow_copy(self):
        api=self.api;private={'owner_user_id':'bob','selected_accessory_ids':None}
        result=api.sanitize_training_state_for_user(private,self.alice,set());self.assertEqual(result,self.f.defaults)
        self.assertEqual(private,{'owner_user_id':'bob','selected_accessory_ids':None})
        value={'owner_user_id':'alice','selected_accessory_ids':['a','b',1,''],'previews':['private'],'nested':{'v':[]}}
        self.assertIs(api.sanitize_training_state_for_user(value,self.alice,{'a','1'}),value)
        self.assertEqual(value['selected_accessory_ids'],['a','1']);self.assertEqual(value['previews'],[])
        self.assertEqual(value['preview_stale_reason'],'training_selection_not_visible')
        original={'owner_user_id':'alice','selected_accessory_ids':['a','b'],'previews':['keep'],'nested':{'v':[]}}
        config={'training_by_user_id':{'alice':original}}
        result=api.training_state_for_user(config,self.alice,{'a'})
        self.assertEqual(result['selected_accessory_ids'],['a']);self.assertEqual(original['selected_accessory_ids'],['a','b']);self.assertEqual(original['previews'],['keep'])
        self.assertIs(result['nested'],original['nested'])
        with self.assertRaises(TypeError):api.sanitize_training_state_for_user({'owner_user_id':'alice','selected_accessory_ids':None},self.alice,set())

    def test_admin_aggregate_target_and_failed_read_store_side_effect(self):
        api=self.api;one={'owner_user_id':'alice','status':'one'};two={'owner_user_id':'bob','status':'two'}
        config={'training_by_user_id':{'alice':one,'bob':two}}
        result=api.training_state_for_user(config,self.admin,set())
        self.assertEqual([s['status'] for s in result['training_states']],['one','two']);self.assertEqual(result['status'],'idle')
        self.assertIsNot(result['training_states'][0],one)
        self.assertEqual(api.training_state_for_user(config,self.admin,set(),'bob')['status'],'two')
        self.assertNotIn('training_states',api.training_state_for_user(config,self.admin,set(),' '))
        raw={' alice ':one};config={'training_by_user_id':raw}
        with patch.object(api,'record_visible_to_user',side_effect=RuntimeError('visibility')):
            with self.assertRaisesRegex(RuntimeError,'visibility'):api.training_state_for_user(config,self.alice,set())
        self.assertIsNot(config['training_by_user_id'],raw);self.assertIs(config['training_by_user_id']['alice'],one)

    def test_set_state_context_owner_overrides_explicit_user_and_async_threads(self):
        api=self.api;config={};state={'owner_user_id':'forged','owner_username':'forged','status':'running','nested':{'v':[]}}
        token=api._request_user.set({'id':'bob','username':'Bob'})
        try:api.set_training_state_for_user(config,self.alice,state)
        finally:api._request_user.reset(token)
        result=config['training_by_user_id']['bob'];self.assertEqual((result['owner_user_id'],result['owner_username']),('bob','Bob'))
        self.assertIs(result['nested'],state['nested']);self.assertNotIn('training',config);self.assertEqual(state['owner_user_id'],'forged')
        api.set_training_state_for_user(config,self.admin,{'owner_user_id':'chosen'})
        self.assertIs(config['training'],config['training_by_user_id']['chosen'])
        barrier=threading.Barrier(2)
        def operation(user):
            barrier.wait(timeout=10);local={};api.set_training_state_for_user(local,user,{'owner_user_id':'wrong'});return local
        async def worker(name):
            user={'id':name,'username':name,'role':'user'};token=api._request_user.set(user)
            try:
                result=await asyncio.to_thread(operation,user);self.assertIs(api._request_user.get(),user);return result
            finally:api._request_user.reset(token)
        async def check():return await asyncio.gather(worker('alice'),worker('bob'))
        results=asyncio.run(check());self.assertEqual([list(item['training_by_user_id']) for item in results],[['alice'],['bob']]);self.assertIsNone(api._request_user.get())

    def test_sync_user_state_preserves_presence_defaults_owner_and_save_order(self):
        api=self.api;f=self.f;api.sync_training_state_from_task('missing');f.config_load.assert_not_called()
        old={'owner_user_id':'alice','sample_count':9,'epochs':7,'image_size':640,'selected_accessory_ids':['old'],'dataset_id':'old','nested':{'v':[]}}
        f.config={'training_by_user_id':{'alice':old},'training':old}
        f.task={'job_id':' job ','owner_user_id':' alice ','owner_username':' Alice ','status':'completed','progress':0,'note':None,'epochs':0,
            'sample_count':0,'selected_accessory_ids':[],'source_dataset_id':'new','mode':'yolo_ocr'};f.events.clear()
        with patch('time.time',return_value=10.9):api.sync_training_state_from_task('requested')
        value=f.config['training_by_user_id']['alice'];self.assertIsNot(value,old);self.assertIs(value['nested'],old['nested'])
        self.assertIs(f.config['training'],value)
        self.assertEqual({key:value[key] for key in ('owner_user_id','owner_username','status','progress','note','epochs','sample_count','selected_accessory_ids','dataset_id','mode','active_training_task_id','updated_at')},
            {'owner_user_id':' alice ','owner_username':' Alice ','status':'completed','progress':0,'note':None,'epochs':7,'sample_count':9,
             'selected_accessory_ids':['old'],'dataset_id':'new','mode':'yolo_ocr','active_training_task_id':' job ','updated_at':10})
        self.assertEqual([v[0] for v in f.events],['find','config-load','config-save']);f.config_save.assert_called_once_with(f.config)
        f.config={'training':{'owner_user_id':'bob','active_training_task_id':'requested'}}
        api.sync_training_state_from_task('requested');self.assertIs(f.config['training'],f.config['training_by_user_id']['alice'])
        f.config={'training':{'owner_user_id':'bob'}};api.sync_training_state_from_task('requested');self.assertEqual(f.config['training']['owner_user_id'],'bob')
        f.task={'job_id':'job','created_by_user_id':'fallback','created_by_username':'Fallback'};f.config={};api.sync_training_state_from_task('job')
        self.assertEqual(f.config['training_by_user_id']['fallback']['owner_username'],'Fallback');self.assertNotIn('training',f.config)

    def test_model_identity_first_match_variant_and_catalog_error(self):
        api=self.api;f=self.f
        for task,expected in [({},'yolo'),({'model_variant':' yolo_ocr '},'yolo_ocr'),({'model_variant':'YOLO_OCR','mode':'yolo_ocr'},'yolo'),
                ({'mode':'yolo','train_mode':'yolo_ocr'},'yolo')]:self.assertEqual(api.training_task_model_variant(task),expected)
        f.models.side_effect=None;f.models.return_value=[{'run_id':'job','id':' custom '},{'run_id':'job','id':'second'}]
        self.assertEqual(api.training_task_model_id({},'job'),'custom');f.models.assert_called_once_with()
        f.models.return_value=[{'run_id':'job','id':' '},{'run_id':'job','id':'second'}]
        self.assertEqual(api.training_task_model_id({'mode':'yolo_ocr'},'job'),'trained_job__yolo_ocr')
        self.assertEqual(api.training_task_model_id({},' job '),'trained_ job __yolo')
        f.models.side_effect=RuntimeError('catalog')
        with self.assertRaisesRegex(RuntimeError,'catalog'):api.training_task_model_id({},'job')
        for identifier,task,expected in [(' pipe_ai_A B ',None,'a_b'),('other',{'ai_task_id':'C D'},'c_d'),('pipe_ai_X',{'ai_task_id':'!!!'},'x'),('other',None,'')]:
            self.assertEqual(api.auto_optimize_task_id_from_pipeline_task(identifier,task),expected)

    def test_pipeline_terminal_branches_exact_fields_and_lock_order(self):
        api=self.api;f=self.f
        case=self;modifications=[]
        def guarded_change(operation):
            case.assertFalse(available(f.pipeline_guard),'pipeline mutation must hold the shared guard')
            case.assertTrue(available(f.auto_guard),'pipeline mutation must not hold the candidate guard')
            modifications.append(operation)
        class GuardedPipeline(dict):
            def update(self,*args,**kwargs):guarded_change('update');super().update(*args,**kwargs)
            def __setitem__(self,key,value):guarded_change(('set',key));super().__setitem__(key,value)
        for task in ({},{'job_id':'job','pipeline_task_id':'pipe','status':'running'}):api.sync_pipeline_training_state_from_task(task)
        f.models.assert_not_called();f.pipeline_load.assert_not_called()
        for status,expected in [('completed','completed'),('failed','failed'),('stopped','stopped'),('cancelled','stopped'),('canceled','stopped')]:
            f.pipeline=GuardedPipeline(id='pipe',detection_method='yolo');f.events.clear();f.link.reset_mock();f.pipeline_save.reset_mock();modifications.clear()
            task={'job_id':' job ','pipeline_task_id':' pipe ','status':' '+status+' ','error':'e'*250,'note':'n'*210}
            with patch('time.time',return_value=22.9):api.sync_pipeline_training_state_from_task(task)
            self.assertEqual(f.pipeline['status'],expected);self.assertEqual(f.pipeline['progress'],100);self.assertEqual(f.pipeline['training_task_id'],'job')
            self.assertEqual(f.pipeline['updated_at'],22);self.assertEqual(f.pipeline['job_note'],'n'*200)
            if status=='completed':
                self.assertEqual({key:f.pipeline[key] for key in ('stage','model_run_id','ai_model_id','model_status','model_exists','linked_view','last_error')},
                    {'stage':'library','model_run_id':'job','ai_model_id':'trained_job__yolo','model_status':'available','model_exists':True,'linked_view':'inspect','last_error':''})
                f.link.assert_called_once_with(f.pipeline)
            else:
                self.assertEqual(f.pipeline['stage'],'training');self.assertEqual(f.pipeline['last_error'],'e'*240);f.link.assert_not_called()
            f.pipeline_save.assert_called_once_with(f.pipeline)
            self.assertEqual(modifications,['update',('set','updated_at')])
            self.assertEqual(f.events[0][:3],('models',True,True))
            self.assertTrue(all(not event[1] and event[2] for event in f.events[1:]));self.assertTrue(available(f.pipeline_guard))
        f.pipeline=GuardedPipeline(id='pipe',detection_method='ai');f.events.clear();modifications.clear()
        api.sync_pipeline_training_state_from_task({'job_id':'job','pipeline_task_id':'pipe','status':'completed'})
        self.assertEqual(f.pipeline['job_note'],'YOLO 接管模型已训练完成，自动优化采集已停止。');self.assertNotIn('training_task_id',f.pipeline)
        self.assertEqual(modifications,['update'])
        f.pipeline={'id':'pipe','detection_method':'ai'};f.pipeline_save.reset_mock()
        api.sync_pipeline_training_state_from_task({'job_id':'job','pipeline_task_id':'pipe','status':'failed'});f.pipeline_save.assert_not_called()

    def test_candidate_upsert_identity_order_defaults_and_lock(self):
        api=self.api;f=self.f;case=self;modifications=[];timestamps=iter([30.9])
        def guarded_change(operation):
            case.assertFalse(available(f.auto_guard),'candidate mutation must hold the shared guard')
            case.assertTrue(available(f.pipeline_guard),'candidate mutation must not hold the pipeline guard')
            modifications.append(operation)
        class GuardedCandidate(dict):
            def update(self,*args,**kwargs):guarded_change('candidate-update');super().update(*args,**kwargs)
        class GuardedState(dict):
            def __setitem__(self,key,value):guarded_change(('state-set',key));super().__setitem__(key,value)
        def clock():guarded_change('clock');return next(timestamps)
        first=GuardedCandidate(job_id='job',created_at=1,old=True);duplicate={'job_id':'job','other':True};other={'job_id':'other'}
        f.auto=GuardedState(candidate_models=['bad',other,first,duplicate,first],task_name='existing',selected_accessory_ids=['existing'])
        task={'job_id':' job ','status':'completed','progress':0,'source_dataset_id':'source','dataset_id':'ignored','note':'x'*250,
            'epochs':0,'total_epochs':8,'image_size':640,'pipeline_task_name':'ignored','selected_accessory_ids':['ignored']}
        with patch('time.time',side_effect=clock):api.sync_auto_optimize_training_candidate_from_task(task,ai_task_id=' AI ',model_id='model')
        self.assertEqual(f.auto['candidate_models'],[first,other,duplicate]);self.assertIs(f.auto['candidate_models'][0],first)
        self.assertEqual(first,{'job_id':'job','created_at':1,'old':True,'status':'completed','progress':100,'dataset_id':'source','model_id':'model',
            'note':'x'*240,'updated_at':30,'training_parameters':{'training_epochs':8,'training_image_size':640}})
        self.assertEqual(f.auto['task_name'],'existing');self.assertEqual(f.auto['selected_accessory_ids'],['existing'])
        f.stop.assert_called_once_with(f.auto,'model',reason='completed_model_ready');f.auto_save.assert_called_once_with(f.auto)
        self.assertEqual([e[0] for e in f.events],['auto-load','stop-capture','auto-save']);self.assertTrue(all(e[1] and not e[2] for e in f.events))
        self.assertEqual(modifications,['clock','candidate-update',('state-set','candidate_models')])
        f.auto=GuardedState(candidate_models=[]);f.stop.reset_mock();selected=['a'];task={'job_id':'new','status':'failed','created_at':0,'pipeline_task_name':'name','selected_accessory_ids':selected}
        modifications.clear();timestamps=iter([41.9,42.9])
        with patch('time.time',side_effect=clock):api.sync_auto_optimize_training_candidate_from_task(task,ai_task_id='ai',model_id='new-model')
        new=f.auto['candidate_models'][0];self.assertEqual((new['updated_at'],new['created_at']),(41,42));self.assertIs(f.auto['selected_accessory_ids'],selected)
        self.assertEqual(f.auto['task_name'],'name');f.stop.assert_not_called();self.assertTrue(available(f.auto_guard))
        self.assertEqual(modifications,['clock','clock',('state-set','candidate_models'),('state-set','task_name'),('state-set','selected_accessory_ids')])

    def test_completion_chain_save_order_non_nested_locks_and_missing_pipeline(self):
        api=self.api;f=self.f;f.task={'job_id':'job','owner_user_id':'alice','pipeline_task_id':'pipe_ai_AI','status':'completed'}
        f.pipeline={'id':'pipe_ai_AI','detection_method':'yolo','ai_task_id':'AI'}
        api.sync_training_state_from_task('job')
        self.assertEqual([e[0] for e in f.events],['find','config-load','config-save','models','pipeline-load','link','pipeline-save','auto-load','stop-capture','auto-save'])
        for e in f.events:
            if e[0] in {'pipeline-load','link','pipeline-save'}:self.assertEqual(e[1:3],(False,True))
            elif e[0] in {'auto-load','stop-capture','auto-save'}:self.assertEqual(e[1:3],(True,False))
            else:self.assertEqual(e[1:3],(True,True))
        f.pipeline=None;f.events.clear();f.link.reset_mock();f.pipeline_save.reset_mock();f.auto_save.reset_mock()
        api.sync_pipeline_training_state_from_task(f.task)
        f.link.assert_not_called();f.pipeline_save.assert_not_called();f.auto_save.assert_called_once()
        self.assertEqual([e[0] for e in f.events],['models','pipeline-load','auto-load','stop-capture','auto-save'])

    def test_false_returns_nonterminal_sync_and_variant_precedence(self):
        api=self.api;f=self.f
        f.task={'job_id':'canonical','owner_user_id':'alice','status':'running','train_mode':'yolo','mode':'yolo_ocr','model_variant':'yolo_ocr'}
        f.config_save.side_effect=None;f.config_save.return_value=False
        with patch.object(api,'sync_pipeline_training_state_from_task') as sync:
            api.sync_training_state_from_task('requested')
            f.config_save.assert_called_once_with(f.config);sync.assert_called_once_with(f.task)
        self.assertEqual(f.config['training_by_user_id']['alice']['mode'],'yolo')
        self.assertEqual(api.training_task_model_variant(f.task),'yolo_ocr')
        f.task.update(status='completed',pipeline_task_id='pipe_ai_ai');f.pipeline={'id':'pipe_ai_ai','params':{'route':'yolo'}}
        f.link.side_effect=None;f.link.return_value={'replacement':'ignored'}
        f.pipeline_save.side_effect=None;f.pipeline_save.return_value=False
        f.stop.side_effect=None;f.stop.return_value=False;f.auto_save.side_effect=None;f.auto_save.return_value=False
        api.sync_pipeline_training_state_from_task(f.task)
        f.link.assert_called_once_with(f.pipeline);f.pipeline_save.assert_called_once_with(f.pipeline)
        self.assertNotIn('replacement',f.pipeline);f.auto_load.assert_called_once_with('ai')
        f.stop.assert_called_once_with(f.auto,'trained_canonical__yolo_ocr',reason='completed_model_ready')
        f.auto_save.assert_called_once_with(f.auto)

    def test_failure_boundaries_partial_updates_and_lock_release(self):
        api=self.api;f=self.f;f.task={'job_id':'job','owner_user_id':'alice','pipeline_task_id':'pipe_ai_ai','status':'completed'}
        f.config_save.side_effect=RuntimeError('config-save')
        with self.assertRaisesRegex(RuntimeError,'config-save'):api.sync_training_state_from_task('job')
        self.assertIn('alice',f.config['training_by_user_id']);f.models.assert_not_called();f.pipeline_load.assert_not_called()
        f.config_save.side_effect=lambda value:f.event('config-save',value)
        f.pipeline={'id':'pipe_ai_ai','ai_task_id':'ai','detection_method':'yolo'};f.link.side_effect=RuntimeError('link')
        with self.assertRaisesRegex(RuntimeError,'link'):api.sync_training_state_from_task('job')
        self.assertEqual(f.pipeline['status'],'completed');self.assertNotIn('updated_at',f.pipeline);f.pipeline_save.assert_not_called();f.auto_load.assert_not_called()
        self.assertTrue(available(f.pipeline_guard));f.link.side_effect=lambda value:f.event('link',value)
        f.pipeline_save.side_effect=RuntimeError('pipeline-save')
        with self.assertRaisesRegex(RuntimeError,'pipeline-save'):api.sync_pipeline_training_state_from_task(f.task)
        self.assertIn('updated_at',f.pipeline);f.auto_load.assert_not_called();self.assertTrue(available(f.pipeline_guard))
        f.pipeline_save.side_effect=lambda value:f.event('pipeline-save',value);f.stop.side_effect=RuntimeError('stop-capture')
        with self.assertRaisesRegex(RuntimeError,'stop-capture'):api.sync_pipeline_training_state_from_task(f.task)
        self.assertEqual(f.auto['candidate_models'][0]['status'],'completed');f.auto_save.assert_not_called()
        self.assertTrue(available(f.pipeline_guard));self.assertTrue(available(f.auto_guard))
        f.stop.side_effect=None;f.auto_save.side_effect=RuntimeError('auto-save')
        with self.assertRaisesRegex(RuntimeError,'auto-save'):api.sync_auto_optimize_training_candidate_from_task(f.task,ai_task_id='ai',model_id='model')
        self.assertTrue(available(f.auto_guard))
        for task,key in [({},'ai'),({'job_id':'job','status':'running'},'ai'),({'job_id':'job','status':'completed'},'!!!')]:
            f.auto_load.reset_mock();api.sync_auto_optimize_training_candidate_from_task(task,ai_task_id=key,model_id='unused');f.auto_load.assert_not_called()

    def test_independent_services_lazy_composition_and_identity(self):
        from local_inspection_service.training.user_state import TrainingUserState,TrainingStateAccess,TrainingStateStorage
        from local_inspection_service.training.task_models import TrainingTaskModels
        from local_inspection_service.pipeline.training_sync import PipelineTrainingSync,PipelineTrainingRecords,PipelineTrainingModels
        from local_inspection_service.detection.training_candidate_sync import TrainingCandidateSync,CandidateTrainingRecords
        from local_inspection_service.runtime.identity import RequestIdentity
        from local_inspection_service.records.ownership import RecordOwnership
        ownership=RecordOwnership('legacy_admin','system');api=self.api
        def compose(f):
            identity=RequestIdentity()
            def current_owner():
                user=identity.get();return {'owner_user_id':user['id'],'owner_username':user.get('username','')} if user else {}
            models=TrainingTaskModels(f.models)
            candidate=TrainingCandidateSync(lambda:f.auto_guard,CandidateTrainingRecords(f.auto_load,f.auto_save),api.sanitize_ai_detection_task_id,f.stop)
            pipeline=PipelineTrainingSync(lambda:f.pipeline_guard,PipelineTrainingRecords(f.pipeline_load,f.pipeline_save),
                PipelineTrainingModels(models.training_task_model_id,f.link),lambda:api.normalize_pipeline_detection_method,
                lambda:api.sanitize_ai_detection_task_id,candidate.sync_auto_optimize_training_candidate_from_task)
            service=TrainingUserState(lambda:f.defaults,lambda:'legacy_admin',TrainingStateAccess(ownership.record_owner_id,
                ownership.record_visible_to_user,api.user_is_admin,current_owner),TrainingStateStorage(f.find,f.config_load,f.config_save),
                pipeline.sync_pipeline_training_state_from_task)
            self.assertEqual(f.events,[]);self.assertIsNone(identity.get());return service,identity
        other=Fixture();first,first_identity=compose(self.f);second,second_identity=compose(other)
        for f,service,identity,name in [(self.f,first,first_identity,'alice'),(other,second,second_identity,'bob')]:
            with identity.bind({'id':name,'username':name}):
                config={};service.set_training_state_for_user(config,{'id':'explicit','role':'user'},{})
                self.assertEqual(list(config['training_by_user_id']),[name])
            self.assertIsNone(identity.get())
            f.task={'job_id':name,'owner_user_id':name,'pipeline_task_id':'pipe_ai_'+name,'status':'completed'}
            f.pipeline={'id':'pipe_ai_'+name,'detection_method':'yolo'}
            service.sync_training_state_from_task(name)
            self.assertEqual(f.auto['candidate_models'][0]['model_id'],'trained_'+name+'__yolo')
        self.assertEqual(list(self.f.config['training_by_user_id']),['alice']);self.assertEqual(list(other.config['training_by_user_id']),['bob'])


    def test_pipeline_callback_capture_windows(self):
        api=self.api
        for window in ('direct','prefix','method'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(window=window,mode=mode),ExitStack() as stack:
                    events=[];name='normalize_pipeline_detection_method' if window=='method' else 'sanitize_ai_detection_task_id'
                    def callback(label):
                        def call(value):events.append(label);return 'unknown' if window=='method' else label
                        return call
                    stack.enter_context(patch.object(api,name,callback('A')))
                    def before():
                        events.append('before')
                        if mode!='ordinary':setattr(api,name,callback('B') if mode=='prior' else None)
                    def argument():events.append('argument');setattr(api,name,callback('C'))
                    class Pipeline(dict):
                        def __bool__(self):
                            if window=='direct':before()
                            return True
                        def get(self,key,default=None):
                            if window=='direct' and key=='ai_task_id':argument();return 'ai'
                            if window=='method' and key=='ai_task_id':before();return ''
                            return super().get(key,default)
                    class DetectionMethod:
                        def __str__(self):argument();return 'yolo'
                    class Prefix(str):
                        def strip(self):return self
                        def startswith(self,prefix):before();return super().startswith(prefix)
                        def __getitem__(self,key):argument();return super().__getitem__(key)
                    class Identifier:
                        def __str__(self):return Prefix('pipe_ai_one')
                    if window=='direct':invoke=lambda:api.auto_optimize_task_id_from_pipeline_task('pipe_ai_one',Pipeline(ai_task_id='ai'))
                    elif window=='prefix':invoke=lambda:api.auto_optimize_task_id_from_pipeline_task(Identifier())
                    else:
                        self.f.pipeline=Pipeline(detection_method=DetectionMethod())
                        stack.enter_context(patch.object(api,'training_task_model_id',return_value='model'))
                        invoke=lambda:api.sync_pipeline_training_state_from_task({'job_id':'job','pipeline_task_id':'ordinary','status':'completed'})
                    if mode=='missing':
                        with self.assertRaises(BaseException) as error:invoke()
                        self.assertIs(type(error.exception),TypeError)
                    else:
                        result=invoke()
                        if window!='method':self.assertEqual(result,'A' if mode=='ordinary' else 'B')
                    self.assertEqual(events,['before','argument']+([] if mode=='missing' else ['A' if mode=='ordinary' else 'B']))
                    self.assertTrue(available(self.f.pipeline_guard));self.assertTrue(available(self.f.auto_guard))


    def test_completion_first_failures_preserve_order_and_partial_state(self):
        api=self.api
        stages=['find','config-load','config-save','model','pipeline-load','pipeline-id','method','link','pipeline-save','candidate-id','auto-load','stop-capture','auto-save']
        for stage in stages:
            with self.subTest(stage=stage),ExitStack() as stack:
                f=Fixture();f.bind(api,stack);failure=OSError('first-only');calls=[]
                f.task={'job_id':'job','owner_user_id':'alice','pipeline_task_id':'pipe_ai_ai','status':'completed'}
                f.pipeline={'id':'pipe_ai_ai','ai_task_id':'ai','detection_method':'yolo'}
                mapping={'find':f.find,'config-load':f.config_load,'config-save':f.config_save,'model':f.models,'pipeline-load':f.pipeline_load,
                    'link':f.link,'pipeline-save':f.pipeline_save,'auto-load':f.auto_load,'stop-capture':f.stop,'auto-save':f.auto_save}
                if stage in ('pipeline-id','candidate-id'):
                    original=api.sanitize_ai_detection_task_id
                    def bad(*args,**kwargs):
                        calls.append((available(f.pipeline_guard),available(f.auto_guard)))
                        if len(calls)==(1 if stage=='pipeline-id' else 2):raise failure
                        return original(*args,**kwargs)
                    probe=stack.enter_context(patch.object(api,'sanitize_ai_detection_task_id',side_effect=bad))
                elif stage=='method':
                    original=api.normalize_pipeline_detection_method
                    def bad(*args,**kwargs):
                        calls.append((available(f.pipeline_guard),available(f.auto_guard)))
                        if len(calls)==1:raise failure
                        return original(*args,**kwargs)
                    probe=stack.enter_context(patch.object(api,'normalize_pipeline_detection_method',side_effect=bad))
                else:
                    probe=mapping[stage];original=probe.side_effect
                    def bad(*args,**kwargs):
                        calls.append((available(f.pipeline_guard),available(f.auto_guard)))
                        if len(calls)==1:raise failure
                        return original(*args,**kwargs)
                    probe.side_effect=bad
                with self.assertRaises(BaseException) as error:api.sync_training_state_from_task('job')
                self.assertIs(error.exception,failure);self.assertEqual(probe.call_count,2 if stage=='candidate-id' else 1)
                expected_lock=(False,True) if stage in ('pipeline-load','pipeline-id','method','link','pipeline-save') else ((True,False) if stage in ('auto-load','stop-capture','auto-save') else (True,True))
                self.assertEqual(calls[-1],expected_lock);self.assertTrue(available(f.pipeline_guard));self.assertTrue(available(f.auto_guard))
                for later in stages[stages.index(stage)+1:]:
                    if later in mapping:self.assertEqual(mapping[later].call_count,0,later)
                if stage in ('link','pipeline-save'):self.assertEqual(f.pipeline['status'],'completed')
                if stage in ('stop-capture','auto-save'):self.assertEqual(f.auto['candidate_models'][0]['job_id'],'job')
                if stage=='config-save':self.assertEqual(f.config['training_by_user_id']['alice']['status'],'completed')

    def test_access_first_failures_stop_without_retry(self):
        api=self.api
        for name in ('record_owner_id','record_visible_to_user','user_is_admin','current_owner_fields'):
            with self.subTest(name=name),ExitStack() as stack:
                failure=OSError('first-only');original=getattr(api,name);count=[]
                def bad(*args,**kwargs):
                    count.append(True)
                    if len(count)==1:raise failure
                    return original(*args,**kwargs)
                probe=stack.enter_context(patch.object(api,name,side_effect=bad));config={'training':{'owner_user_id':'alice'}}
                with self.assertRaises(BaseException) as error:
                    if name=='record_owner_id':api.training_state_store(config)
                    elif name=='record_visible_to_user':api.sanitize_training_state_for_user({'owner_user_id':'alice'},self.alice,set())
                    elif name=='user_is_admin':api.training_state_for_user(config,self.alice,set())
                    else:api.set_training_state_for_user(config,self.alice,{})
                self.assertIs(error.exception,failure);self.assertEqual(probe.call_count,1)
                self.f.config_save.assert_not_called();self.assertTrue(available(self.f.pipeline_guard));self.assertTrue(available(self.f.auto_guard))

    def test_internal_state_first_failures_keep_original_exception(self):
        api=self.api;service=api._training_user_state;pipeline=api._pipeline_training_sync
        cases=[(service,'default_training_state',lambda:api.sanitize_training_state_for_user(None,self.alice,set())),
            (service,'normalize_training_owner_key',lambda:api.training_state_store({'training_by_user_id':{'alice':{}}})),
            (service,'training_state_store',lambda:api.training_state_for_user({},self.alice,set())),
            (service,'sanitize_training_state_for_user',lambda:api.training_state_for_user({},self.alice,set())),
            (pipeline,'auto_optimize_task_id_from_pipeline_task',lambda:api.sync_pipeline_training_state_from_task({'job_id':'job','pipeline_task_id':'pipe_ai_ai','status':'completed'}))]
        for target,name,invoke in cases:
            with self.subTest(name=name):
                failure=OSError('first-only');original=getattr(target,name);calls=[]
                def bad(*args,**kwargs):
                    calls.append(True)
                    if len(calls)==1:raise failure
                    return original(*args,**kwargs)
                with patch.object(target,name,side_effect=bad) as probe:
                    with self.assertRaises(BaseException) as error:invoke()
                    self.assertIs(error.exception,failure);self.assertEqual(probe.call_count,1)
                self.assertTrue(available(self.f.pipeline_guard));self.assertTrue(available(self.f.auto_guard))

    def test_new_state_getter_failures(self):
        api=self.api
        for stage in ('direct','prefix','method','defaults','legacy','pipeline-guard','candidate-guard'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=Fixture();f.bind(api,stack);failure=OSError('first-only');events=[]
                class Pipeline(dict):
                    def get(self,key,default=None):events.append(key);return super().get(key,default)
                class Method:
                    def __str__(self):events.append('str');return 'yolo'
                if stage in ('direct','prefix'):
                    target=api._pipeline_training_sync;field='clean_id';valid=api.sanitize_ai_detection_task_id
                    invoke=lambda:api.auto_optimize_task_id_from_pipeline_task('pipe_ai_ai',Pipeline(ai_task_id='ai') if stage=='direct' else None)
                elif stage=='method':
                    f.pipeline=Pipeline(detection_method=Method());target=api._pipeline_training_sync;field='normalize_method';valid=api.normalize_pipeline_detection_method
                    invoke=lambda:api.sync_pipeline_training_state_from_task({'job_id':'job','pipeline_task_id':'ordinary','status':'completed'})
                elif stage in ('defaults','legacy'):
                    target=api._training_user_state;field='defaults' if stage=='defaults' else 'legacy_owner';valid={} if stage=='defaults' else 'legacy'
                    invoke=api.default_training_state if stage=='defaults' else lambda:api.normalize_training_owner_key('')
                else:
                    target=api._pipeline_training_sync if stage=='pipeline-guard' else api._training_candidate_sync;field='guard';valid=f.pipeline_guard if stage=='pipeline-guard' else f.auto_guard
                    task={'job_id':'job','pipeline_task_id':'pipe_ai_ai','status':'completed'}
                    invoke=(lambda:api.sync_pipeline_training_state_from_task(task)) if stage=='pipeline-guard' else lambda:api.sync_auto_optimize_training_candidate_from_task(task,ai_task_id='ai',model_id='model')
                probe=stack.enter_context(patch.object(target,field,side_effect=chain([failure],repeat(valid))))
                with self.assertRaises(BaseException) as error:invoke()
                self.assertIs(error.exception,failure);probe.assert_called_once_with()
                if stage in ('direct','prefix'):self.assertEqual(events,[])
                if stage=='method':self.assertNotIn('str',events)
                f.config_save.assert_not_called();f.pipeline_save.assert_not_called();f.auto_save.assert_not_called()
                self.assertTrue(available(f.pipeline_guard));self.assertTrue(available(f.auto_guard))

    def test_full_pipeline_and_candidate_reads_hold_their_own_guard(self):
        api=self.api;f=self.f;events=[]
        class Pipeline(dict):
            def get(self,key,default=None):events.append(('pipeline-get',available(f.pipeline_guard),available(f.auto_guard)));return super().get(key,default)
        class Candidate(dict):
            def get(self,key,default=None):events.append(('candidate-get',available(f.pipeline_guard),available(f.auto_guard)));return super().get(key,default)
        class State(dict):
            def get(self,key,default=None):events.append(('state-get',available(f.pipeline_guard),available(f.auto_guard)));return super().get(key,default)
        f.task={'job_id':'job','owner_user_id':'alice','pipeline_task_id':'pipe_ai_ai','status':'completed'}
        f.pipeline=Pipeline(detection_method='yolo');f.auto=State(candidate_models=[Candidate(job_id='job')])
        api.sync_training_state_from_task('job')
        self.assertTrue(events)
        for name,pipeline_open,auto_open in events:self.assertEqual((pipeline_open,auto_open),(False,True) if name=='pipeline-get' else (True,False))
        self.assertTrue(any(name=='candidate-get' for name,*_ in events));self.assertTrue(any(name=='pipeline-get' for name,*_ in events))
        self.assertTrue(available(f.pipeline_guard));self.assertTrue(available(f.auto_guard))


    def test_user_state_branch_first_failures(self):
        api=self.api;service=api._training_user_state
        def sync_fixture():
            self.f.task={'job_id':'job','owner_user_id':'alice','status':'completed'}
            self.f.config={'training':{'owner_user_id':'alice','status':'old'}}
            return lambda:api.sync_training_state_from_task('job')
        cases=[
            ('default_training_state','sanitize-denied',lambda:api.sanitize_training_state_for_user({'owner_user_id':'bob'},self.alice,set())),
            ('default_training_state','admin-aggregate',lambda:api.training_state_for_user({},self.admin,set())),
            ('default_training_state','set',lambda:api.set_training_state_for_user({},self.alice,{})),
            ('default_training_state','sync',None),
            ('normalize_training_owner_key','legacy',lambda:api.training_state_store({'training':{'owner_user_id':'alice'}})),
            ('normalize_training_owner_key','admin-target',lambda:api.training_state_for_user({},self.admin,set(),'alice')),
            ('normalize_training_owner_key','user',lambda:api.training_state_for_user({},self.alice,set())),
            ('normalize_training_owner_key','set',lambda:api.set_training_state_for_user({},self.alice,{})),
            ('normalize_training_owner_key','sync-owner',None),
            ('normalize_training_owner_key','sync-current-owner',None),
            ('training_state_store','set',lambda:api.set_training_state_for_user({},self.alice,{})),
            ('training_state_store','sync',None),
            ('sanitize_training_state_for_user','admin-aggregate',lambda:api.training_state_for_user({'training_by_user_id':{'alice':{'owner_user_id':'alice'}}},self.admin,set())),
        ]
        for name,branch,invoke in cases:
            with self.subTest(name=name,branch=branch):
                if invoke is None:invoke=sync_fixture()
                failure=OSError('first-only');original=getattr(service,name);calls=[]
                # Sync first normalizes the legacy record in store(), then the task owner,
                # then the legacy current record after publishing its per-owner state.
                fail_at=3 if branch=='sync-current-owner' else (2 if branch=='sync-owner' else 1)
                def bad(*args,**kwargs):
                    calls.append(args)
                    if len(calls)==fail_at:raise failure
                    return original(*args,**kwargs)
                with patch.object(service,name,side_effect=bad) as probe:
                    with self.assertRaises(BaseException) as error:invoke()
                    self.assertIs(error.exception,failure);self.assertEqual(probe.call_count,fail_at)
                self.assertTrue(available(self.f.pipeline_guard));self.assertTrue(available(self.f.auto_guard))
        for name,branch,fail_at in [('user_is_admin','second-admin',2),('record_visible_to_user','admin-filter',1),('record_visible_to_user','admin-sanitize',2),('sync_pipeline_training_state_from_task','sync',1)]:
            with self.subTest(name=name,branch=branch):
                failure=OSError('first-only');original=getattr(api,name);calls=[]
                def bad(*args,**kwargs):
                    calls.append(args)
                    if len(calls)==fail_at:raise failure
                    return original(*args,**kwargs)
                with patch.object(api,name,side_effect=bad) as probe:
                    with self.assertRaises(BaseException) as error:
                        if branch=='sync':sync_fixture()()
                        else:api.training_state_for_user({'training_by_user_id':{'alice':{'owner_user_id':'alice'}}},self.alice if branch=='second-admin' else self.admin,set())
                    self.assertIs(error.exception,failure);self.assertEqual(probe.call_count,fail_at)
                self.assertTrue(available(self.f.pipeline_guard));self.assertTrue(available(self.f.auto_guard))


    def test_remaining_state_failures_and_clock_residues(self):
        api=self.api
        for stage in ('set-admin','sync-legacy','sync-owner','ai-save','user-clock','yolo-clock','ai-clock','candidate-updated','candidate-created'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=Fixture();f.bind(api,stack);failure=OSError('first-only');calls=[]
                f.task={'job_id':'job','owner_user_id':'alice','status':'completed'}
                f.config={'training':{'owner_user_id':'alice','status':'old'}} if stage=='sync-owner' else {}
                f.pipeline={'id':'pipe_ai_ai','ai_task_id':'ai','detection_method':'ai' if stage in ('ai-save','ai-clock') else 'yolo'}
                task={'job_id':'job','pipeline_task_id':'pipe_ai_ai','status':'completed'}
                if stage=='set-admin':
                    original=api.user_is_admin;target=api;field='user_is_admin';fail_at=1
                    invoke=lambda:api.set_training_state_for_user(f.config,self.alice,{})
                elif stage=='sync-legacy':
                    f.task.pop('owner_user_id');target=api._training_user_state;field='legacy_owner';original=getattr(target,field);fail_at=1
                    invoke=lambda:api.sync_training_state_from_task('job')
                elif stage=='sync-owner':
                    target=api;field='record_owner_id';original=getattr(target,field);fail_at=2
                    invoke=lambda:api.sync_training_state_from_task('job')
                elif stage=='ai-save':
                    target=api;field='save_pipeline_task';original=f.pipeline_save;fail_at=1
                    invoke=lambda:api.sync_pipeline_training_state_from_task(task)
                else:
                    target=__import__('time');field='time';original=lambda:42.9;fail_at=2 if stage=='candidate-created' else 1
                    if stage=='user-clock':invoke=lambda:api.sync_training_state_from_task('job')
                    elif stage in ('yolo-clock','ai-clock'):invoke=lambda:api.sync_pipeline_training_state_from_task(task)
                    else:
                        existing={'job_id':'job','old':True};f.auto={'candidate_models':[existing] if stage=='candidate-updated' else []}
                        invoke=lambda:api.sync_auto_optimize_training_candidate_from_task(task,ai_task_id='ai',model_id='model')
                def bad(*args,**kwargs):
                    calls.append((available(f.pipeline_guard),available(f.auto_guard)))
                    if len(calls)==fail_at:raise failure
                    return original(*args,**kwargs)
                probe=stack.enter_context(patch.object(target,field,side_effect=bad))
                with self.assertRaises(BaseException) as error:invoke()
                self.assertIs(error.exception,failure);self.assertEqual(probe.call_count,fail_at)
                expected=(False,True) if stage in ('ai-save','yolo-clock','ai-clock') else ((True,False) if stage.startswith('candidate-') else (True,True))
                self.assertEqual(calls[-1],expected);self.assertTrue(available(f.pipeline_guard));self.assertTrue(available(f.auto_guard))
                f.config_save.assert_not_called();f.auto_save.assert_not_called();f.stop.assert_not_called()
                if stage!='ai-save':f.pipeline_save.assert_not_called()
                if stage=='set-admin':self.assertIn('alice',f.config['training_by_user_id']);self.assertNotIn('training',f.config)
                if stage=='sync-owner':self.assertEqual(f.config['training_by_user_id']['alice']['status'],'completed');self.assertEqual(f.config['training']['status'],'old')
                if stage=='sync-legacy':f.config_load.assert_not_called()
                if stage=='user-clock':self.assertEqual(f.config['training_by_user_id'],{})
                if stage in ('ai-save','yolo-clock'):self.assertEqual(f.pipeline['status'],'completed')
                if stage=='yolo-clock':self.assertNotIn('updated_at',f.pipeline)
                if stage=='ai-clock':self.assertNotIn('status',f.pipeline)
                if stage=='candidate-updated':self.assertEqual(existing,{'job_id':'job','old':True});self.assertIs(f.auto['candidate_models'][0],existing)
                if stage=='candidate-created':self.assertEqual(f.auto['candidate_models'],[])


if __name__=='__main__':unittest.main()
