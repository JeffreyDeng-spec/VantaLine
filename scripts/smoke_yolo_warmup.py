"""YOLO warmup contracts using synthetic catalogs, predictions and recorded threads."""
from contextlib import ExitStack
import copy
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch, call
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


class WarmupContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='warmup-root-')
        root=Path(cls.temp.name);(root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ,{'VANTALINE_YOLO_PREWARM':'1','VANTALINE_YOLO_PREWARM_LIMIT':'6',
            'VANTALINE_YOLO_PREWARM_MODELS':'','VANTALINE_YOLO_PREWARM_DELAY_SECONDS':'0'}))
        self.state=self.api._yolo_warmup_state;old=copy.deepcopy(self.state)
        self.state.clear();self.state.update(enabled=True,status='idle',model_ids=[],completed_model_ids=[],failed_model_ids=[],started_at=0,completed_at=0,error='')
        def restore():self.state.clear();self.state.update(old)
        self.addCleanup(restore)
    def test_environment_values_and_explicit_candidates_short_circuit(self):
        api=self.api
        with patch.dict(os.environ,{}):
            os.environ.pop('VANTALINE_YOLO_PREWARM',None);os.environ.pop('VANTALINE_YOLO_PREWARM_LIMIT',None)
            self.assertTrue(api.yolo_warmup_enabled());self.assertEqual(api.yolo_warmup_limit(),6)
        for value,expected in [('0',False),(' FALSE ',False),('no',False),('off',False),('',True),('yes',True),('2',True)]:
            with patch.dict(os.environ,{'VANTALINE_YOLO_PREWARM':value}):self.assertEqual(api.yolo_warmup_enabled(),expected)
        for value,expected in [('-1',1),('0',1),('13',12),('bad',6),('',6),('3',3)]:
            with patch.dict(os.environ,{'VANTALINE_YOLO_PREWARM_LIMIT':value}):self.assertEqual(api.yolo_warmup_limit(),expected)
        with patch.dict(os.environ,{'VANTALINE_YOLO_PREWARM_MODELS':' a, a, , b,c ','VANTALINE_YOLO_PREWARM_LIMIT':'3'}),\
             patch.object(api,'load_pipeline_tasks',side_effect=AssertionError('pipeline')) as pipeline,\
             patch.object(api,'list_trained_model_specs',side_effect=AssertionError('trained')) as trained:
            self.assertEqual(api.yolo_warmup_configured_model_ids({}),['a','a','b']);pipeline.assert_not_called();trained.assert_not_called()
    def test_candidate_order_limits_duplicates_and_empty_id_path_consumption(self):
        api=self.api;config={'active_model_id':' active '}
        tasks=[None,{'stage':'other'},dict(stage='library',detection_method='ai',id='ignored'),
               dict(stage='library',detection_method='yolo',id='old',updated_at=1),
               dict(stage='library',detection_method='yolo_ocr',id='active',updated_at=3),
               dict(stage='library',detection_method='yolo',id='new',updated_at=2)]
        specs=[dict(id='duplicate',path='same',updated_at=2),dict(id='',path='same',updated_at=3),
               dict(id='train',artifact_path='other',updated_at=1),dict(id='ai',is_ai_detection=True)]
        with patch.object(api,'load_pipeline_tasks',return_value=tasks),\
             patch.object(api,'normalize_pipeline_detection_method',side_effect=lambda value:value),\
             patch.object(api,'pipeline_task_model_status',return_value='available'),\
             patch.object(api,'pipeline_task_model_id',side_effect=lambda item:item['id']) as model_id,\
             patch.object(api,'list_trained_model_specs',return_value=specs) as trained,\
             patch.object(api,'resolve_service_path',side_effect=lambda value:Path(value)) as resolve:
            self.assertEqual(api.yolo_warmup_configured_model_ids(config),['active','new','old','train'])
            self.assertEqual([v.args[0]['id'] for v in model_id.call_args_list],['active','new','old'])
            self.assertEqual(resolve.call_args_list,[call('same'),call('same'),call('other')]);trained.assert_called_once_with(config)
            model_id.reset_mock();trained.reset_mock();resolve.reset_mock()
            with patch.dict(os.environ,{'VANTALINE_YOLO_PREWARM_LIMIT':'1'}):
                self.assertEqual(api.yolo_warmup_configured_model_ids(config),['active'])
            model_id.assert_called_once();trained.assert_called_once_with(config);resolve.assert_called_once_with('same')
    def test_prediction_dummy_clamps_and_exception_boundaries(self):
        api=self.api;predictor=Mock();config={'image_size':2,'confidence_threshold':.6}
        with patch.object(api,'selected_model_spec',return_value={'id':'actual','confidence_threshold':2}) as select,\
             patch.object(api,'model',return_value=predictor) as load,patch.object(api,'yolo_inference_device',return_value='cpu') as device:
            api.warm_yolo_model_once('requested',config);select.assert_called_once_with('requested',config);load.assert_called_once_with('actual',config)
            predictor.predict.assert_called_once();device.assert_called_once_with()
            image=predictor.predict.call_args.args[0];self.assertEqual(image.shape,(96,96,3));self.assertEqual(image.dtype,np.uint8);self.assertFalse(image.any())
            self.assertEqual(predictor.predict.call_args.kwargs,{'imgsz':320,'device':'cpu','conf':.99,'verbose':False})
            for image_size,confidence,size_result,conf_result in [('bad',None,640,.25),(9999,-1,1280,.001),(0,.5,640,.5)]:
                predictor.reset_mock();select.reset_mock();load.reset_mock();device.reset_mock()
                select.return_value={'id':7,'confidence_threshold':confidence};api.warm_yolo_model_once('requested',{'image_size':image_size})
                predictor.predict.assert_called_once();select.assert_called_once_with('requested',{'image_size':image_size})
                load.assert_called_once_with('7',{'image_size':image_size});device.assert_called_once_with()
                self.assertEqual(predictor.predict.call_args.kwargs['imgsz'],size_result);self.assertEqual(predictor.predict.call_args.kwargs['conf'],conf_result)
                self.assertEqual(load.call_args.args[0],'7')
            for field in ('is_ai_detection','is_label_sheet_match'):
                predictor.reset_mock();select.reset_mock();load.reset_mock();device.reset_mock()
                select.return_value={field:True};api.warm_yolo_model_once('requested',{})
                select.assert_called_once_with('requested',{});load.assert_not_called();device.assert_not_called();predictor.predict.assert_not_called()
            predictor.reset_mock();select.reset_mock();load.reset_mock();device.reset_mock()
            select.return_value={'id':'actual'};predictor.predict.side_effect=RuntimeError('predict')
            with self.assertRaisesRegex(RuntimeError,'predict'):api.warm_yolo_model_once('requested',{})
            predictor.predict.assert_called_once();select.assert_called_once_with('requested',{})
            load.assert_called_once_with('actual',{});device.assert_called_once_with()
    def test_snapshot_is_shallow_and_public_loaded_error_does_not_mutate_state(self):
        api=self.api;ids=['one'];self.state['model_ids']=ids
        value=api.yolo_warmup_status();self.assertIsNot(value,self.state);self.assertIs(value['model_ids'],ids)
        value['status']='other';value['model_ids'].append('two');self.assertEqual(self.state['status'],'idle');self.assertEqual(ids,['one','two'])
        with patch.object(api,'yolo_loaded_model_ids',return_value=['ready']) as loaded:
            result=api.public_yolo_warmup_status({'a':1});loaded.assert_called_once_with({'a':1})
            self.assertEqual(result['loaded_model_ids'],['ready']);self.assertNotIn('loaded_model_ids',self.state)
        before=copy.deepcopy(self.state)
        with patch.object(api,'yolo_loaded_model_ids',side_effect=RuntimeError('loaded')):
            with self.assertRaisesRegex(RuntimeError,'loaded'):api.public_yolo_warmup_status({})
        self.assertEqual(self.state,before)
    def test_disabled_worker_and_start_preserve_previous_detail(self):
        api=self.api;self.state.update(reason='old',model_ids=['old'],completed_model_ids=['old'],started_at=1,completed_at=2,error='old')
        expected={**self.state,'enabled':False,'status':'disabled','error':''}
        with patch.dict(os.environ,{'VANTALINE_YOLO_PREWARM':'off'}),patch.object(api.time,'sleep') as sleep,\
             patch.object(api,'load_config') as config,patch.object(api.threading,'Thread') as thread:
            api.yolo_warmup_worker();self.assertEqual(self.state,expected)
            api.start_yolo_warmup();self.assertEqual(self.state,expected)
            sleep.assert_not_called();config.assert_not_called();thread.assert_not_called()
    def test_worker_progress_aliases_failure_summary_and_callbacks_outside_lock(self):
        api=self.api;ids=['ok','bad1','bad2','bad3','bad4'];observed=[];snapshots=[];unlocked=[]
        def warm(model_id,config):
            observed.append((model_id,config));snapshots.append(api.yolo_warmup_status())
            def probe():
                locked=api._yolo_warmup_lock.acquire(blocking=False);unlocked.append(locked)
                if locked:api._yolo_warmup_lock.release()
            thread=threading.Thread(target=probe);thread.start();thread.join(2);self.assertFalse(thread.is_alive())
            if model_id!='ok':raise RuntimeError('failure '+model_id)
        with patch.object(api.time,'sleep') as sleep,patch.object(api.time,'time',side_effect=[100.9,200.9]),\
             patch.object(api,'load_config',return_value={'config':True}),patch.object(api,'yolo_warmup_configured_model_ids') as configured,\
             patch.object(api,'warm_yolo_model_once',side_effect=warm),patch.object(api,'bounded_text',side_effect=lambda text,limit:text[:limit]) as bounded:
            api.yolo_warmup_worker('manual',ids);sleep.assert_called_once_with(0);configured.assert_not_called()
        self.assertEqual([v[0] for v in observed],ids);self.assertTrue(all(unlocked));self.assertEqual(len(unlocked),5)
        self.assertIs(self.state['model_ids'],ids);self.assertEqual(self.state['started_at'],100);self.assertEqual(self.state['completed_at'],200)
        self.assertEqual(self.state['status'],'completed_with_errors');self.assertEqual(len(self.state['failed_model_ids']),4)
        self.assertEqual(self.state['error'],'bad1: failure bad1; bad2: failure bad2; bad3: failure bad3')
        self.assertEqual(bounded.call_args_list,[call('failure '+value,180) for value in ids[1:]])
        self.assertIs(snapshots[1]['completed_model_ids'],self.state['completed_model_ids'])
        self.assertIs(snapshots[1]['failed_model_ids'],self.state['failed_model_ids'])
        self.assertEqual(snapshots[1]['failed_model_ids'],self.state['failed_model_ids'])
    def test_worker_pre_running_errors_empty_ids_and_formatter_failure(self):
        api=self.api;initial=copy.deepcopy(self.state)
        with patch.object(api.time,'sleep') as sleep,patch.object(api,'load_config',side_effect=RuntimeError('config')):
            with self.assertRaisesRegex(RuntimeError,'config'):api.yolo_warmup_worker()
        self.assertEqual(self.state,initial)
        with patch.object(api.time,'sleep'),patch.object(api,'load_config',return_value={}),\
             patch.object(api,'yolo_warmup_configured_model_ids',side_effect=ValueError('candidates')):
            with self.assertRaisesRegex(ValueError,'candidates'):api.yolo_warmup_worker(model_ids=[])
        self.assertEqual(self.state,initial)
        with patch.dict(os.environ,{'VANTALINE_YOLO_PREWARM_DELAY_SECONDS':'bad'}),patch.object(api.time,'sleep') as sleep,\
             patch.object(api.time,'time',side_effect=[10,20]),patch.object(api,'load_config',return_value={}),\
             patch.object(api,'yolo_warmup_configured_model_ids',return_value=[]) as configured,patch.object(api,'warm_yolo_model_once') as warm:
            api.yolo_warmup_worker(model_ids=[]);configured.assert_called_once_with({});warm.assert_not_called();sleep.assert_called_once_with(1.5)
        self.assertEqual(self.state['status'],'completed')
        with patch.dict(os.environ,{}),patch.object(api.time,'sleep') as sleep,patch.object(api,'load_config',return_value={}),patch.object(api,'yolo_warmup_configured_model_ids',return_value=[]):
            os.environ.pop('VANTALINE_YOLO_PREWARM_DELAY_SECONDS',None)
            api.yolo_warmup_worker();sleep.assert_called_once_with(1.5)
        with patch.object(api.time,'sleep'),patch.object(api,'load_config',return_value={}),\
             patch.object(api,'warm_yolo_model_once',side_effect=RuntimeError('warm')),patch.object(api,'bounded_text',side_effect=ValueError('formatter')):
            with self.assertRaisesRegex(ValueError,'formatter'):api.yolo_warmup_worker(model_ids=['one'])
        self.assertEqual(self.state['status'],'running');self.assertEqual(self.state['completed_at'],0);self.assertEqual(self.state['failed_model_ids'],[])
    def test_start_captures_current_worker_and_each_call_creates_daemon(self):
        api=self.api;worker=Mock();ids=['one'];first=Mock();second=Mock()
        with patch.object(api,'yolo_warmup_worker',worker),patch.object(api.threading,'Thread',side_effect=[first,second]) as thread:
            api.start_yolo_warmup('manual',ids);api.start_yolo_warmup('manual',ids)
            self.assertEqual(thread.call_args_list,[call(target=worker,args=('manual',ids),name='yolo-warmup-manual',daemon=True)]*2)
            self.assertIs(thread.call_args.kwargs['args'][1],ids);first.start.assert_called_once_with();second.start.assert_called_once_with();worker.assert_not_called()
        before=copy.deepcopy(self.state)
        replacement=Mock()
        def enabled():
            api.yolo_warmup_worker=replacement
            return True
        with patch.object(api,'yolo_warmup_worker',Mock()),patch.object(api,'yolo_warmup_enabled',side_effect=enabled),patch.object(api.threading,'Thread') as thread:
            api.start_yolo_warmup('late',ids)
            self.assertIs(thread.call_args.kwargs['target'],replacement)
        with patch.object(api.threading,'Thread') as thread:
            thread.return_value.start.side_effect=RuntimeError('start')
            with self.assertRaisesRegex(RuntimeError,'start'):api.start_yolo_warmup()
        self.assertEqual(self.state,before)


    def test_runtime_instances_are_lazy_independent_and_snapshot_waits_for_lock(self):
        from local_inspection_service.runtime.yolo_warmup import YoloWarmup, WarmupOperations
        providers=[Mock() for _ in range(6)];operations=WarmupOperations(*providers)
        first=YoloWarmup(operations);second=YoloWarmup(operations)
        for provider in providers:provider.assert_not_called()
        self.assertIs(self.api._yolo_warmup_lock,self.api._yolo_warmup_runtime.lock)
        self.assertIs(self.api._yolo_warmup_state,self.api._yolo_warmup_runtime.state)
        self.assertIsNot(first.lock,second.lock);self.assertIsNot(first.state,second.state)
        for key in ('model_ids','completed_model_ids','failed_model_ids'):self.assertIsNot(first.state[key],second.state[key])
        first.state['model_ids'].append('first');self.assertEqual(second.state['model_ids'],[])
        started=threading.Event();finished=threading.Event();values=[]
        def snapshot():
            started.set();values.append(first.yolo_warmup_status());finished.set()
        with first.lock:
            thread=threading.Thread(target=snapshot);thread.start();self.assertTrue(started.wait(2))
            self.assertFalse(finished.wait(.05));self.assertEqual(second.yolo_warmup_status()['status'],'idle')
        self.assertTrue(finished.wait(2));thread.join(2);self.assertFalse(thread.is_alive())
        self.assertIs(values[0]['model_ids'],first.state['model_ids'])

    def test_runtime_state_updates_hold_lock_and_unhandled_baseexception_remains_running(self):
        from local_inspection_service.runtime import yolo_warmup as runtime
        observed=[]
        instance=runtime.YoloWarmup(runtime.WarmupOperations(lambda:True,lambda:{},lambda config:['one'],
            lambda model_id,config:None,lambda config:[],lambda text,limit:text))
        def probe():
            results=[]
            def acquire():
                locked=instance.lock.acquire(blocking=False);results.append(locked)
                if locked:instance.lock.release()
            thread=threading.Thread(target=acquire);thread.start();thread.join(2)
            self.assertFalse(thread.is_alive());self.assertEqual(results,[False]);observed.append('locked')
        class CheckedState(dict):
            def update(self,*args,**kwargs):probe();return super().update(*args,**kwargs)
            def __setitem__(self,key,value):probe();return super().__setitem__(key,value)
        instance.state=CheckedState(instance.state)
        with patch.object(runtime.time,'sleep'):instance.yolo_warmup_worker('fixture')
        self.assertGreaterEqual(len(observed),4);self.assertEqual(instance.state['status'],'completed')
        with patch.object(self.api.time,'sleep'),patch.object(self.api,'load_config',return_value={}),             patch.object(self.api,'warm_yolo_model_once',side_effect=KeyboardInterrupt('stop')):
            with self.assertRaises(KeyboardInterrupt):self.api.yolo_warmup_worker(model_ids=['one'])
        self.assertEqual(self.state['status'],'running');self.assertEqual(self.state['completed_at'],0)


if __name__=='__main__':unittest.main()
