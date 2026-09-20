"""Draft shared cutout lifecycle contracts; synthetic model substitutes only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from itertools import chain,repeat
from contextlib import ExitStack
from unittest.mock import Mock,patch
import numpy as np
sys.path.insert(0,str(Path.cwd()))
class CutoutRuntimeContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='cutout-runtime-')))
        (cls.root/'local_inspection_service/static').mkdir(parents=True)
        for name in ('DATABASE_URL','VANTALINE_POSTGRES_DSN','PGDSN'):os.environ.pop(name,None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(cls.root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false',YOLO_AUTOINSTALL='false')
        for name in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):
            cls.lifetime.enter_context(patch(name,side_effect=AssertionError('External operation forbidden')))
        from types import SimpleNamespace
        cls.import_factory=Mock(side_effect=AssertionError('Eager model load forbidden'));cls.import_remove=Mock(side_effect=AssertionError('Eager inference forbidden'))
        cls.lifetime.enter_context(patch.dict(sys.modules,{'rembg':SimpleNamespace(new_session=cls.import_factory,remove=cls.import_remove)}))
        from local_inspection_service import server
        cls.import_factory.assert_not_called();cls.import_remove.assert_not_called()
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.lifetime.close()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
    def replace(self,name,**kwargs):return self.stack.enter_context(patch.object(self.api,name,**kwargs))
    def fake_rembg(self, **kwargs):
        from types import SimpleNamespace
        module=SimpleNamespace(**kwargs)
        self.stack.enter_context(patch.dict(sys.modules,{'rembg':module}))
        return module
    def fresh_session(self):
        from local_inspection_service.accessories.cutout_runtime import RembgSessionRuntime
        owner=RembgSessionRuntime();self.replace('_rembg_runtime',new=owner)
        self._read_cache=lambda:owner._session
        self._write_cache=lambda value:setattr(owner,'_session',value)
        self._replace_lock=lambda value:setattr(owner,'lock',value)
        return owner.lock
    def cached_session(self):return self._read_cache()
    def cache_session(self,value):self._write_cache(value)
    def replace_runtime_lock(self,value):self._replace_lock(value)
    def test_success_is_lazy_cached_and_single_factory_call(self):
        lock=self.fresh_session();value=object();factory=Mock(return_value=value);self.fake_rembg(new_session=factory)
        self.assertIsNone(self.cached_session());factory.assert_not_called()
        self.assertIs(self.api.rembg_session(),value);self.assertIs(self.api.rembg_session(),value)
        factory.assert_called_once_with('u2net');self.assertIs(self.cached_session(),value)
    def test_failure_is_not_cached_and_future_acquisition_can_succeed(self):
        lock=self.fresh_session();value=object();failure=RuntimeError('synthetic load failure');factory=Mock(side_effect=[failure,value]);self.fake_rembg(new_session=factory)
        self.assertIsNone(self.api.rembg_session());self.assertIsNone(self.cached_session());self.assertEqual(factory.call_count,1)
        self.assertIs(self.api.rembg_session(),value);self.assertEqual(factory.call_count,2)
        self.assertIs(self.api.rembg_session(),value);self.assertEqual(factory.call_count,2)
    def test_existing_cache_does_not_import_model_package(self):
        self.fresh_session();value=object();self.cache_session(value)
        self.stack.enter_context(patch.dict(sys.modules,{'rembg':None}))
        self.assertIs(self.api.rembg_session(),value)
    def test_two_consumers_no_session_return_none_without_inference(self):
        self.fresh_session();session=self.replace('rembg_session',return_value=None);remove=Mock(side_effect=AssertionError('inference forbidden'));self.fake_rembg(remove=remove)
        image=np.zeros((32,32,3),np.uint8)
        self.assertIsNone(self.api.ai_background_cutout_with_bbox(image));self.assertIsNone(self.api.precise_green_plate_cutout(image));self.assertEqual(session.call_count,2);remove.assert_not_called()
    def test_session_callback_error_escapes_both_consumer_try_blocks(self):
        self.fresh_session();failure=RuntimeError('synthetic session callback');session=self.replace('rembg_session',side_effect=failure);remove=Mock();self.fake_rembg(remove=remove)
        for callback in (self.api.ai_background_cutout_with_bbox,self.api.precise_green_plate_cutout):
            with self.assertRaises(RuntimeError) as seen:callback(np.zeros((32,32,3),np.uint8))
            self.assertIs(seen.exception,failure)
        self.assertEqual(session.call_count,2);remove.assert_not_called()
    def test_invalid_precise_input_does_not_acquire_session(self):
        session=self.replace('rembg_session')
        self.assertIsNone(self.api.precise_green_plate_cutout(None));self.assertIsNone(self.api.precise_green_plate_cutout(np.zeros((8,8),np.uint8)));session.assert_not_called()
    def test_inference_failure_returns_none_and_releases_shared_lock(self):
        import threading
        lock=self.fresh_session();value=object();self.replace('rembg_session',return_value=value);failure=RuntimeError('synthetic inference failure');remove=Mock(side_effect=failure);self.fake_rembg(remove=remove)
        for callback in (self.api.ai_background_cutout_with_bbox,self.api.precise_green_plate_cutout):
            self.assertIsNone(callback(np.zeros((32,32,3),np.uint8)))
            acquired=[]
            def probe():
                ok=lock.acquire(timeout=1);acquired.append(ok)
                if ok:lock.release()
            worker=threading.Thread(target=probe);worker.start();worker.join(timeout=2)
            self.assertFalse(worker.is_alive());self.assertEqual(acquired,[True])
        self.assertEqual(remove.call_count,2)
        for call in remove.call_args_list:self.assertIs(call.kwargs['session'],value)
        self.assertEqual(remove.call_args_list[0].kwargs,{'session':value,'alpha_matting':True,'alpha_matting_foreground_threshold':240,'alpha_matting_background_threshold':12,'alpha_matting_erode_size':8})
        self.assertEqual(remove.call_args_list[1].kwargs,{'session':value,'alpha_matting':True,'alpha_matting_foreground_threshold':240,'alpha_matting_background_threshold':10,'alpha_matting_erode_size':0})
    def assert_lock_held_and_reentrant(self,lock):
        import threading
        results=[]
        def probe():
            held=lock.acquire(False);results.append(held)
            if held:lock.release()
        worker=threading.Thread(target=probe);worker.start();worker.join(timeout=2)
        self.assertFalse(worker.is_alive());self.assertEqual(results,[False])
        reentrant=lock.acquire(False)
        self.assertTrue(reentrant)
        if reentrant:lock.release()
    def test_factory_and_inference_hold_same_reentrant_lock(self):
        from PIL import Image
        lock=self.fresh_session();value=object();events=[]
        def factory(name):
            self.assertEqual(name,'u2net');self.assert_lock_held_and_reentrant(lock);events.append('factory');return value
        def remove(image,**kwargs):
            self.assertIs(kwargs['session'],value);self.assert_lock_held_and_reentrant(lock);events.append('remove');return Image.fromarray(np.full((32,32,4),255,np.uint8))
        self.fake_rembg(new_session=factory,remove=remove)
        self.replace('bright_green_conveyor_mask',return_value=np.zeros((32,32),bool));self.replace('suppress_green_spill',side_effect=lambda image:image)
        for callback in (self.api.ai_background_cutout_with_bbox,self.api.precise_green_plate_cutout):
            result=callback(np.zeros((32,32,3),np.uint8));self.assertIsNotNone(result);self.assertEqual(result[2],(0,0,32,32));np.testing.assert_array_equal(result[1],np.full((32,32),255,np.uint8))
        self.assertEqual(events,['factory','remove','remove']);self.assertIs(self.cached_session(),value)
    def test_concurrent_cold_acquisition_creates_one_shared_session(self):
        import threading
        lock=self.fresh_session();entered=threading.Event();release=threading.Event();second_attempted=threading.Event();value=object();results=[];failures=[];calls=[]
        def factory(name):
            calls.append(name);entered.set()
            if not release.wait(3):raise AssertionError('factory release timeout')
            return value
        self.fake_rembg(new_session=factory)
        entries=[]
        class ObservedLock:
            def __enter__(inner):
                entries.append(threading.get_ident())
                if len(entries)==2:second_attempted.set()
                return lock.__enter__()
            def __exit__(inner,*args):return lock.__exit__(*args)
        self.replace_runtime_lock(ObservedLock())
        def acquire(second=False):
            try:results.append(self.api.rembg_session())
            except BaseException as error:failures.append(error)
        first=threading.Thread(target=acquire);second=threading.Thread(target=acquire,args=(True,))
        first.start()
        try:
            self.assertTrue(entered.wait(2));second.start();self.assertTrue(second_attempted.wait(2))
        finally:
            release.set();first.join(timeout=3)
            if second.ident is not None:second.join(timeout=3)
        self.assertFalse(first.is_alive());self.assertFalse(second.is_alive());self.assertEqual(failures,[]);self.assertEqual(calls,['u2net']);self.assertEqual(len(results),2);self.assertTrue(all(result is value for result in results))
    def test_distinct_postprocessing_exception_boundaries(self):
        from PIL import Image
        self.fresh_session();value=object();self.replace('rembg_session',return_value=value);failure=RuntimeError('synthetic postprocess')
        rgba=Image.fromarray(np.full((32,32,4),255,np.uint8));self.fake_rembg(remove=Mock(return_value=rgba))
        original=self.api.cv2.cvtColor;conversions=[]
        def convert(image,code):
            conversions.append(code)
            if len(conversions)==2:raise failure
            return original(image,code)
        self.stack.enter_context(patch.object(self.api.cv2,'cvtColor',side_effect=convert))
        self.assertIsNone(self.api.ai_background_cutout_with_bbox(np.zeros((32,32,3),np.uint8)))
        self.replace('bright_green_conveyor_mask',side_effect=failure)
        with self.assertRaises(RuntimeError) as seen:self.api.precise_green_plate_cutout(np.zeros((32,32,3),np.uint8))
        self.assertIs(seen.exception,failure)
    def assert_lock_available_from_other_thread(self,lock):
        import threading
        acquired=[]
        def probe():
            ok=lock.acquire(False);acquired.append(ok)
            if ok:lock.release()
        worker=threading.Thread(target=probe);worker.start();worker.join(timeout=2)
        self.assertFalse(worker.is_alive());self.assertEqual(acquired,[True])
    def test_base_exception_escapes_factory_and_consumers_with_lock_release(self):
        class Halt(BaseException):pass
        failure=Halt('synthetic cancellation');lock=self.fresh_session();factory=Mock(side_effect=failure);remove=Mock(side_effect=failure);self.fake_rembg(new_session=factory,remove=remove)
        with self.assertRaises(Halt) as seen:self.api.rembg_session()
        self.assertIs(seen.exception,failure);self.assert_lock_available_from_other_thread(lock)
        self.assertIsNone(self.cached_session());factory.assert_called_once_with('u2net')
        self.replace('rembg_session',return_value=object())
        for callback in (self.api.ai_background_cutout_with_bbox,self.api.precise_green_plate_cutout):
            with self.assertRaises(Halt) as seen:callback(np.zeros((32,32,3),np.uint8))
            self.assertIs(seen.exception,failure);self.assert_lock_available_from_other_thread(lock)
        self.assertEqual(remove.call_count,2)
    def test_bounded_alpha12_is_empty_and13_is_foreground(self):
        from PIL import Image
        self.fresh_session();self.replace('rembg_session',return_value=object());rgba=np.full((32,32,4),255,np.uint8);rgba[:,:,3]=12
        remove=Mock(side_effect=lambda *args,**kwargs:Image.fromarray(rgba.copy()));self.fake_rembg(remove=remove)
        self.assertIsNone(self.api.ai_background_cutout_with_bbox(np.zeros((32,32,3),np.uint8)))
        rgba[:,:,3]=13;result=self.api.ai_background_cutout_with_bbox(np.zeros((32,32,3),np.uint8))
        self.assertIsNotNone(result);self.assertEqual(result[2],(0,0,32,32));np.testing.assert_array_equal(result[1],np.full((32,32),13,np.uint8));self.assertEqual(remove.call_count,2)
    def test_runtime_constructor_is_lazy_and_owns_reentrant_lock(self):
        from local_inspection_service.accessories.cutout_runtime import RembgSessionRuntime
        factory=Mock(side_effect=AssertionError('eager runtime model load'));remove=Mock(side_effect=AssertionError('eager runtime inference'));self.fake_rembg(new_session=factory,remove=remove)
        owner=RembgSessionRuntime();self.assertIsNone(owner._session);factory.assert_not_called();remove.assert_not_called()
        with owner.lock:self.assert_lock_held_and_reentrant(owner.lock)
        self.assert_lock_available_from_other_thread(owner.lock)
        from local_inspection_service.accessories.background_cutouts import BackgroundCutoutProcessor
        from local_inspection_service.accessories.cutout_ports import CutoutRuntimeOperations,CutoutGreenOperations
        getter=Mock(side_effect=AssertionError('eager cutout dependency'))
        processor=BackgroundCutoutProcessor(CutoutRuntimeOperations(session=getter,lock=getter),CutoutGreenOperations(mask=getter,spill=getter));self.assertIsInstance(processor,BackgroundCutoutProcessor);getter.assert_not_called()
    def test_runtime_instances_have_distinct_cache_and_default_locks(self):
        from local_inspection_service.accessories.cutout_runtime import RembgSessionRuntime
        first_value=object();second_value=object();factory=Mock(side_effect=[first_value,second_value]);self.fake_rembg(new_session=factory)
        first=RembgSessionRuntime();second=RembgSessionRuntime();self.assertIsNot(first.lock,second.lock);self.assertIsNone(first._session);self.assertIsNone(second._session)
        root_session=self.replace('rembg_session',side_effect=AssertionError('root session forbidden'))
        self.assertIs(first.rembg_session(),first_value);self.assertIs(second.rembg_session(),second_value);self.assertIs(first.rembg_session(),first_value)
        self.assertEqual(factory.call_count,2);root_session.assert_not_called()
    def test_independent_cutout_processors_first_second_first(self):
        from PIL import Image
        from local_inspection_service.accessories.cutout_runtime import RembgSessionRuntime
        from local_inspection_service.accessories.background_cutouts import BackgroundCutoutProcessor
        from local_inspection_service.accessories.cutout_ports import CutoutRuntimeOperations,CutoutGreenOperations
        first_value=object();second_value=object();factory=Mock(side_effect=[first_value,second_value])
        def remove(image,**kwargs):
            value=10 if kwargs['session'] is first_value else 20
            rgba=np.full((32,32,4),value,np.uint8);rgba[:,:,3]=255;return Image.fromarray(rgba)
        self.fake_rembg(new_session=factory,remove=remove)
        masks=[];spills=[]
        def build(delta):
            owner=RembgSessionRuntime();mask=Mock(return_value=np.zeros((32,32),bool));spill=Mock(side_effect=lambda image:image+delta);masks.append(mask);spills.append(spill)
            return BackgroundCutoutProcessor(CutoutRuntimeOperations(session=lambda:owner.rembg_session,lock=lambda:owner.lock),CutoutGreenOperations(mask=lambda:mask,spill=lambda:spill))
        first=build(1);second=build(2)
        poisons=[self.replace(name,side_effect=AssertionError('root cutout forbidden')) for name in ('rembg_session','ai_background_cutout_with_bbox','precise_green_plate_cutout','bright_green_conveyor_mask','suppress_green_spill')]
        outputs=[]
        for processor in (first,second,first):
            bounded=processor.ai_background_cutout_with_bbox(np.zeros((32,32,3),np.uint8));precise=processor.precise_green_plate_cutout(np.zeros((32,32,3),np.uint8))
            self.assertIsNotNone(bounded);self.assertIsNotNone(precise);self.assertEqual(bounded[2],(0,0,32,32));self.assertEqual(precise[2],(0,0,32,32));outputs.append((int(bounded[0][0,0,0]),int(precise[0][0,0,0])))
        self.assertEqual(outputs,[(10,1),(20,2),(10,1)]);self.assertEqual(factory.call_count,2);self.assertEqual([m.call_count for m in masks],[2,1]);self.assertEqual([s.call_count for s in spills],[2,1])
        for poison in poisons:poison.assert_not_called()

if __name__=='__main__':unittest.main()
