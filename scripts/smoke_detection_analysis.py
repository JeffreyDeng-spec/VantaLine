"""Offline ordinary detection routing/inference contracts; no model or PLC I/O."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def capture_ordinary(api, Fixture, root, stage, mode):
    from contextlib import ExitStack
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    with ExitStack() as stack:
        stack.enter_context(patch.dict(api.__dict__))
        f=Fixture(root);f.bind(api,stack);entry=api.analyze_bgr;events=[]
        early=Mock(side_effect=AssertionError('entry callback A used'));late=Mock(side_effect=AssertionError('late callback C used'))
        def swap(name,value):setattr(api,name,value)
        if stage=='sanitize':
            b=Mock(side_effect=lambda value:events.append('B') or '')
            api.sanitize_ai_detection_task_id=b if mode=='ordinary' else early
            class Spec(dict):
                def get(self,key,default=None):
                    if key=='is_ai_detection' and mode!='ordinary':
                        events.append('prior');swap('sanitize_ai_detection_task_id',None if mode=='missing' else b)
                    if key=='task_id':events.append('arg');swap('sanitize_ai_detection_task_id',late)
                    return super().get(key,default)
            f.spec=Spec(id='ai',is_ai_detection=True,task_id='task')
            expected=([] if mode=='ordinary' else ['prior'])+['arg']+([] if mode=='missing' else ['B'])
        elif stage=='formatter':
            b=Mock(side_effect=lambda *args:events.append('B') or 'safe B');api.bounded_text=b if mode=='ordinary' else early
            f.spec={'id':'ai','is_ai_detection':True,'task_id':'task'};f.sanitize.side_effect=lambda value:'task'
            f.state={'settings':{'enabled':True,'serving_mode':'promoted_yolo'},'active_model_id':'student'}
            class Failure(Exception):
                def __str__(self):events.append('arg');swap('bounded_text',late);return 'student'
            stack.enter_context(patch.object(api,'analyze_bgr',Mock(side_effect=Failure())))
            def ai(*args,**kwargs):
                if mode!='ordinary':events.append('prior');swap('bounded_text',None if mode=='missing' else b)
                return f.ai_result
            f.ai.side_effect=ai;expected=([] if mode=='ordinary' else ['prior'])+['arg']+([] if mode=='missing' else ['B'])
        elif stage=='resize':
            b=Mock(side_effect=lambda *args:events.append('B') or f.preview);api.resize_bgr_max_side=b if mode=='ordinary' else early
            def directory(kind):
                if mode!='ordinary':events.append('prior');swap('resize_bgr_max_side',None if mode=='missing' else b)
                return Path(root)
            f.directory.side_effect=directory;expected=([] if mode=='ordinary' else ['prior'])+([] if mode=='missing' else ['B'])
        elif stage=='writer':
            b=Mock(side_effect=lambda *args:events.append('B') or False)
            api.cv2=SimpleNamespace(imwrite=b if mode=='ordinary' else early,IMWRITE_JPEG_QUALITY=11)
            class Out:
                name='synthetic.jpg'
                def __str__(self):events.append('arg');swap('cv2',SimpleNamespace(imwrite=late,IMWRITE_JPEG_QUALITY=33));return 'synthetic.jpg'
            class Directory:
                def __truediv__(self,name):return Out()
            f.directory.side_effect=lambda kind:Directory()
            def resize(*args):
                if mode!='ordinary':events.append('prior');swap('cv2',SimpleNamespace(imwrite=None if mode=='missing' else b,IMWRITE_JPEG_QUALITY=22))
                return f.preview
            f.resize.side_effect=resize;expected=([] if mode=='ordinary' else ['prior'])+['arg']+([] if mode=='missing' else ['B'])
        else:raise AssertionError(stage)
        captured=None
        try:entry(f.image,'req','id')
        except BaseException as exc:captured=exc
        assert (type(captured) is TypeError) if mode=='missing' else captured is None,(stage,mode,captured)
        assert events==expected,(stage,mode,events,expected)
        early.assert_not_called();late.assert_not_called()
        assert b.call_count==int(mode!='missing')
        return events

def capture_independent_resize(Fixture, root, mode):
    from local_inspection_service.detection.analysis import DetectionAnalysis
    from local_inspection_service.detection.analysis_ports import AnalysisInput,AnalysisRouting,AnalysisInference,AnalysisOutput
    from unittest.mock import Mock
    from pathlib import Path
    f=Fixture(root);events=[];early=Mock(side_effect=AssertionError('entry A'));late=Mock(side_effect=AssertionError('late C'))
    b=Mock(side_effect=lambda *args:events.append('B') or f.preview);slot=[b if mode=='ordinary' else early]
    def directory(kind):
        if mode!='ordinary':events.append('prior');slot[0]=None if mode=='missing' else b
        return Path(root)
    def maximum():events.append('arg');slot[0]=late;return 640
    service=DetectionAnalysis(AnalysisInput(f.load,lambda:f.scope,f.selected,lambda:f.sanitize,f.state_load),AnalysisRouting(Mock(),f.ai,f.retired,lambda:f.text),AnalysisInference(lambda:f.model,f.device,f.parse,f.ocr,f.apply,f.draw),AnalysisOutput(directory,lambda:slot[0],maximum,lambda:f.backend,lambda:87,f.url))
    captured=None
    try:service.analyze_bgr(f.image,'req','id')
    except BaseException as exc:captured=exc
    assert (type(captured) is TypeError) if mode=='missing' else captured is None,(mode,captured)
    expected=([] if mode=='ordinary' else ['prior'])+['arg']+([] if mode=='missing' else ['B'])
    assert events==expected,(events,expected)
    early.assert_not_called();late.assert_not_called();assert b.call_count==int(mode!='missing')
    return events


class AnalysisFixture:
    def __init__(self,root):
        self.root=Path(root); self.events=[]
        self.config={'image_size':64,'confidence_threshold':0.3}; self.scoped={'image_size':96,'confidence_threshold':0.2}
        self.spec={'id':'detector','label':'Detector','uses_ocr':True}; self.state={}
        self.image=np.full((5,7,3),10,dtype=np.uint8); self.annotated=np.full((5,7,3),20,dtype=np.uint8); self.preview=np.full((3,4,3),30,dtype=np.uint8)
        self.raw=object(); self.detections=[{'source':'parsed'}]; self.ocr_detections=[{'source':'ocr'}]; self.rule={'passed':True,'counts':{}}
        self.ai_result={'request_id':'req','passed':True}; self.promoted_result={'request_id':'req','passed':True}
        def port(name,result): return Mock(side_effect=lambda *args,**kwargs:self.record(name,*args,**kwargs) or result())
        self.load=port('load',lambda:self.config); self.scope=port('scope',lambda:self.scoped); self.selected=port('selected',lambda:self.spec)
        self.sanitize=port('sanitize',lambda:''); self.state_load=port('state',lambda:self.state)
        self.ai=port('ai',lambda:self.ai_result); self.retired=port('retired',lambda:None)
        self.predict=port('predict',lambda:[self.raw]); self.loaded=SimpleNamespace(predict=self.predict); self.model=port('model',lambda:self.loaded)
        self.device=port('device',lambda:'cpu'); self.parse=port('parse',lambda:self.detections); self.ocr=port('ocr',lambda:self.ocr_detections)
        self.apply=port('rule',lambda:self.rule); self.draw=port('draw',lambda:self.annotated); self.directory=port('directory',lambda:self.root)
        self.resize=port('resize',lambda:self.preview); self.write=port('write',lambda:False); self.url=port('url',lambda:'/out/req_annotated.jpg')
        self.text=port('text',lambda:'safe failure'); self.backend=SimpleNamespace(imwrite=self.write,IMWRITE_JPEG_QUALITY=321)
    def record(self,name,*args,**kwargs): self.events.append((name,args,kwargs))
    def bind(self,api,stack):
        for name,value in {'load_config':self.load,'scope_config_for_user':self.scope,'selected_model_spec':self.selected,
            'sanitize_ai_detection_task_id':self.sanitize,'load_auto_optimize_state':self.state_load,'analyze_bgr_ai_detection':self.ai,
            'removed_phase1_feature':self.retired,'model':self.model,'yolo_inference_device':self.device,'parse_detections':self.parse,
            'attach_ocr_results':self.ocr,'apply_rule':self.apply,'draw_detections':self.draw,'output_write_dir':self.directory,
            'resize_bgr_max_side':self.resize,'output_url':self.url,'bounded_text':self.text,'cv2':self.backend,
            'INSPECTION_PREVIEW_MAX_SIDE':640,'INSPECTION_PREVIEW_JPEG_QUALITY':87}.items():stack.enter_context(patch.object(api,name,value))


class DetectionAnalysisContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ); cls.environment.start(); cls.runtime=tempfile.TemporaryDirectory(prefix='analysis-contract-')
        root=Path(cls.runtime.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        for target in ['requests.sessions.Session.request','subprocess.Popen','os.kill']:
            self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected external operation')))
        self.stack.enter_context(patch.object(self.api,'analyze_bgr',self.api.analyze_bgr))
        self.f=AnalysisFixture(Path(self.runtime.name)/self.id().split('.')[-1]); self.f.bind(self.api,self.stack)
        self._original_analysis_entry=self.api.analyze_bgr
    def analyze(self): return self.api.analyze_bgr(self.f.image,'req','selected-id',image_path=Path('synthetic-source.png'))

    def test_complete_yolo_path_orders_inference_ocr_rule_and_output(self):
        f=self.f; result=self.analyze()
        self.assertEqual([event[0] for event in f.events],['load','scope','selected','model','device','predict','parse','ocr','rule','draw','directory','resize','write','url'])
        self.assertEqual(result,{'request_id':'req','passed':True,'model':{'id':'detector','label':'Detector','uses_ocr':True},
            'rule':f.rule,'detections':f.ocr_detections,'annotated_url':'/out/req_annotated.jpg'})
        self.assertIs(result['rule'],f.rule); self.assertIs(result['detections'],f.ocr_detections)
        f.load.assert_called_once_with(); f.scope.assert_called_once_with(f.config); f.selected.assert_called_once_with('selected-id',f.scoped)
        f.model.assert_called_once_with('detector',f.scoped); self.assertIs(f.predict.call_args.args[0],f.image)
        self.assertEqual(f.predict.call_args.kwargs,{'imgsz':96,'device':'cpu','conf':0.2,'verbose':False})
        f.parse.assert_called_once_with(f.raw,f.spec); self.assertIs(f.ocr.call_args.args[0],f.image)
        self.assertEqual(f.ocr.call_args.args[1:],(f.detections,f.scoped,f.spec)); f.apply.assert_called_once_with(f.ocr_detections,f.scoped,f.spec)
        self.assertIs(f.draw.call_args.args[0],f.image); self.assertEqual(f.draw.call_args.args[1:],(f.ocr_detections,f.rule))
        f.directory.assert_called_once_with('inspection'); self.assertIs(f.resize.call_args.args[0],f.annotated); self.assertEqual(f.resize.call_args.args[1],640)
        self.assertEqual(f.write.call_args.args[0],str(f.root/'req_annotated.jpg')); self.assertIs(f.write.call_args.args[1],f.preview)
        self.assertEqual(f.write.call_args.args[2],[321,87]); f.url.assert_called_once_with(f.root/'req_annotated.jpg')
        f.ai.assert_not_called()

    def test_confidence_threshold_defaults_clamp_and_narrow_error_boundary(self):
        for value,expected in [(2,0.99),(-1,0.001),(True,0.99),(False,0.001),('0.4',0.4),(None,0.25),('bad',0.25),(float('nan'),0.99),(float('inf'),0.99)]:
            with self.subTest(value=value):
                self.f.spec['confidence_threshold']=value; self.analyze(); self.assertEqual(self.f.predict.call_args.kwargs['conf'],expected)
        self.f.spec.pop('confidence_threshold'); self.f.scoped.pop('confidence_threshold'); self.analyze(); self.assertEqual(self.f.predict.call_args.kwargs['conf'],0.25)
        class Overflow:
            def __float__(inner): raise OverflowError('threshold overflow')
        self.f.spec['confidence_threshold']=Overflow(); self.f.model.reset_mock()
        with self.assertRaises(OverflowError): self.analyze()
        self.f.model.assert_not_called()
        events=[]
        class Config(dict):
            def get(inner,key,default=None):
                if key=='confidence_threshold': events.append('config')
                return super().get(key,default)
        class Spec(dict):
            def get(inner,key,default=None):
                if key=='confidence_threshold': events.append('spec')
                return super().get(key,default)
        self.f.scoped=Config(image_size=64,confidence_threshold=0.1); self.f.spec=Spec(id='model',label='label',confidence_threshold=0.4)
        self.analyze(); self.assertEqual(events,['config','spec'])

    def test_no_ocr_and_retired_label_branches_keep_boundaries(self):
        f=self.f; f.spec['uses_ocr']=False; result=self.analyze()
        f.ocr.assert_not_called(); self.assertIs(result['detections'],f.detections); self.assertFalse(result['model']['uses_ocr'])
        f.spec['is_label_sheet_match']=True; error=RuntimeError('retired'); f.retired.side_effect=error; f.model.reset_mock()
        with self.assertRaises(RuntimeError) as caught: self.analyze()
        self.assertIs(caught.exception,error); f.retired.assert_called_once_with('Label Sheet'); f.model.assert_not_called()

    def test_ai_routing_without_active_promotion_returns_same_result(self):
        for task,state in [('',{}),('task',{}),('task',{'settings':{'enabled':False,'serving_mode':'promoted_yolo'},'active_model_id':'student'}),
                           ('task',{'settings':{'enabled':True,'serving_mode':'api_primary'},'active_model_id':'student'}),
                           ('task',{'settings':{'enabled':True,'serving_mode':'promoted_yolo'},'active_model_id':'   '})]:
            with self.subTest(task=task,state=state):
                f=self.f; f.events.clear(); f.spec={'id':'ai','is_ai_detection':True,'task_id':'','run_id':'run'}; f.state=state
                f.sanitize.side_effect=lambda value:f.record('sanitize',value) or task; f.state_load.reset_mock(); f.ai.reset_mock()
                result=self.analyze(); self.assertIs(result,f.ai_result)
                self.assertEqual([e[0] for e in f.events],['load','scope','selected','sanitize']+(['state'] if task else [])+['ai'])
                f.sanitize.assert_called_with('run'); self.assertEqual(f.state_load.call_count,int(bool(task)))
                self.assertIs(f.ai.call_args.args[0],f.image); self.assertEqual(f.ai.call_args.args[1:],('req',f.spec,f.scoped))
                self.assertEqual(f.ai.call_args.kwargs,{'image_path':Path('synthetic-source.png')}); f.model.assert_not_called()

    def test_promoted_recursion_returns_alias_and_falls_back_only_after_failure(self):
        f=self.f; f.spec={'id':'ai','is_ai_detection':True,'task_id':'task'}; f.sanitize.return_value='task'; f.sanitize.side_effect=None
        f.state={'settings':{'enabled':True,'serving_mode':'promoted_yolo'},'active_model_id':' student '}
        entry=self.api.analyze_bgr; recurse=Mock(return_value=f.promoted_result)
        self.api.analyze_bgr=recurse
        result=entry(f.image,'req','ai',image_path=Path('source.png'))
        self.assertIs(result,f.promoted_result); self.assertEqual(result['ai_auto_optimize'],{'serving_mode':'promoted_yolo','ai_task_id':'task','active_model_id':'student','fallback_used':False})
        self.assertIs(recurse.call_args.args[0],f.image); self.assertEqual(recurse.call_args.args[1:],('req','student')); self.assertEqual(recurse.call_args.kwargs,{'image_path':Path('source.png')})
        f.ai.assert_not_called()
        error=OSError('student unavailable'); recurse.reset_mock(); recurse.side_effect=error
        result=entry(f.image,'req','ai',image_path=Path('source.png'))
        self.assertIs(result,f.ai_result); self.assertEqual(result['ai_auto_optimize'],{'serving_mode':'api_primary','ai_task_id':'task','active_model_id':'student','fallback_used':True,'fallback_reason':'safe failure'})
        recurse.assert_called_once(); f.ai.assert_called_once(); f.text.assert_called_once_with('student unavailable',180)
        failure=OSError('teacher failed'); f.ai.side_effect=failure; f.text.reset_mock()
        with self.assertRaises(OSError) as caught: entry(f.image,'req','ai')
        self.assertIs(caught.exception,failure); f.text.assert_not_called()

    def test_each_ordinary_pipeline_failure_stops_without_retry(self):
        stages=['load','scope','selected','model','device','predict','parse','ocr','rule','draw','directory','resize','write','url']
        for stage in stages:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=AnalysisFixture(self.f.root); f.bind(self.api,stack); error=OSError(stage); calls=0
                port=getattr(f,{'rule':'apply'}.get(stage,stage)); original=port.side_effect
                def fail(*args,**kwargs):
                    nonlocal calls
                    calls+=1
                    if calls==1: f.record(stage,*args,**kwargs); raise error
                    return original(*args,**kwargs)
                port.side_effect=fail
                with self.assertRaises(OSError) as caught: self.api.analyze_bgr(f.image,'req')
                self.assertIs(caught.exception,error); self.assertEqual(calls,1); self.assertEqual([e[0] for e in f.events],stages[:stages.index(stage)+1])


    def test_scope_model_and_predict_capture_before_nested_arguments(self):
        f=self.f; initial=f.scope; later=Mock(return_value=f.scoped)
        f.load.side_effect=lambda:setattr(self.api,'scope_config_for_user',later) or f.config
        self.analyze(); initial.assert_called_once_with(f.config); later.assert_not_called()
        self.analyze(); later.assert_called_once_with(f.config)
        before=f.model; captured=Mock(return_value=f.loaded); after=Mock(return_value=f.loaded)
        class Identity:
            def __str__(inner): self.api.model=after; return 'converted-id'
        identity=Identity(); f.spec={'id':identity,'label':'label'}
        def select(*args): self.api.model=captured; return f.spec
        f.selected.side_effect=select; before.reset_mock(); result=self.analyze()
        before.assert_not_called(); captured.assert_called_once_with('converted-id',f.scoped); after.assert_not_called()
        self.assertIs(result['model']['id'],identity)
        f.selected.side_effect=lambda *args:f.spec; f.spec={'id':'normal','label':'normal'}; self.api.model=f.model
        first,second,third=Mock(return_value=[f.raw]),Mock(return_value=[f.raw]),Mock(return_value=[f.raw])
        f.loaded.predict=first
        class ImageSize:
            def __int__(inner): f.loaded.predict=second; return 128
        f.scoped['image_size']=ImageSize()
        f.device.side_effect=lambda:setattr(f.loaded,'predict',third) or 'cpu'
        self.analyze(); first.assert_called_once(); second.assert_not_called(); third.assert_not_called()
        self.assertEqual(first.call_args.kwargs,{'imgsz':128,'device':'cpu','conf':0.2,'verbose':False})

    def test_noncallable_scope_model_and_predict_evaluate_original_arguments(self):
        for stage in ['scope','model','predict']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=AnalysisFixture(self.f.root); f.bind(self.api,stack); events=[]
                if stage=='scope':
                    self.api.scope_config_for_user=None
                    f.load.side_effect=lambda:events.append('load') or setattr(self.api,'scope_config_for_user',f.scope) or f.config
                elif stage=='model':
                    class Identity:
                        def __str__(inner): events.append('id'); self.api.model=f.model; return 'id'
                    f.spec={'id':Identity(),'label':'label'}
                    f.selected.side_effect=lambda *args:setattr(self.api,'model',None) or f.spec
                else:
                    f.loaded.predict=None
                    class ImageSize:
                        def __int__(inner): events.append('size'); f.loaded.predict=f.predict; return 64
                    f.scoped['image_size']=ImageSize(); f.device.side_effect=lambda:events.append('device') or 'cpu'
                with self.assertRaises(TypeError): self.api.analyze_bgr(f.image,'req')
                self.assertEqual(events,{'scope':['load'],'model':['id'],'predict':['size','device']}[stage])
                if stage=='scope': f.scope.assert_not_called(); f.selected.assert_not_called()
                if stage=='model': f.model.assert_not_called()
                f.predict.assert_not_called(); f.write.assert_not_called()

    def test_promoted_metadata_assignment_failure_is_in_fallback_try_boundary(self):
        f=self.f; entry=self.api.analyze_bgr; error=OSError('assignment'); writes=[]
        class Promoted(dict):
            def __setitem__(inner,key,value):
                writes.append(key)
                if len(writes)==1: raise error
                return super().__setitem__(key,value)
        promoted=Promoted(); recurse=Mock(return_value=promoted); self.api.analyze_bgr=recurse
        f.spec={'id':'ai','is_ai_detection':True}; f.sanitize.side_effect=None; f.sanitize.return_value='task'
        f.state={'settings':{'enabled':True,'serving_mode':'promoted_yolo'},'active_model_id':'student'}
        result=entry(f.image,'req','ai'); self.assertIs(result,f.ai_result); self.assertEqual(writes,['ai_auto_optimize'])
        self.assertEqual(promoted,{}); recurse.assert_called_once(); f.ai.assert_called_once(); f.text.assert_called_once_with('assignment',180)
        self.assertTrue(result['ai_auto_optimize']['fallback_used'])
        reason_error=OSError('reason formatter'); recurse.reset_mock(); recurse.side_effect=error; f.ai.reset_mock(); f.text.side_effect=reason_error
        old={'existing':'metadata'}; f.ai_result['ai_auto_optimize']=old
        with self.assertRaises(OSError) as caught: entry(f.image,'req','ai')
        self.assertIs(caught.exception,reason_error); self.assertIs(f.ai_result['ai_auto_optimize'],old)
        recurse.assert_called_once(); f.ai.assert_called_once()

    def test_output_writer_is_captured_after_resize_before_path_and_late_quality(self):
        f=self.f; events=[]; before=f.write; writer=Mock(return_value=False); after=Mock(return_value=False)
        class Out:
            def __str__(inner): events.append('path'); self.api.cv2=SimpleNamespace(imwrite=after,IMWRITE_JPEG_QUALITY=99); self.api.INSPECTION_PREVIEW_JPEG_QUALITY=73; return 'output.jpg'
        out=Out()
        class Directory:
            def __truediv__(inner,name): return out
        f.directory.side_effect=lambda kind:Directory()
        def resize(image,side): self.api.cv2=SimpleNamespace(imwrite=writer,IMWRITE_JPEG_QUALITY=88); return f.preview
        f.resize.side_effect=resize; self.analyze()
        before.assert_not_called(); writer.assert_called_once(); after.assert_not_called()
        self.assertEqual(events,['path']); self.assertEqual(writer.call_args.args[0],'output.jpg'); self.assertIs(writer.call_args.args[1],f.preview)
        self.assertEqual(writer.call_args.args[2],[99,73]); f.url.assert_called_once_with(out)


    def test_promoted_base_exception_propagates_without_teacher_call(self):
        class Cancelled(BaseException): pass
        f=self.f; entry=self.api.analyze_bgr; signal=Cancelled('synthetic cancellation'); recurse=Mock(side_effect=[signal,f.promoted_result])
        self.api.analyze_bgr=recurse; f.spec={'id':'ai','is_ai_detection':True}; f.sanitize.side_effect=None; f.sanitize.return_value='task'
        f.state={'settings':{'enabled':True,'serving_mode':'promoted_yolo'},'active_model_id':'student'}
        with self.assertRaises(Cancelled) as caught: entry(f.image,'req','ai')
        self.assertIs(caught.exception,signal); recurse.assert_called_once(); f.ai.assert_not_called(); f.text.assert_not_called()


    def test_independent_plc_guard_rejects_business_calls_and_pin_bypass(self):
        import ast
        from local_inspection_service.scripts.smoke_plc_frontend_contract import require_detection_analysis_boundary
        root=Path(__file__).resolve().parents[1]/'local_inspection_service'; source=(root/'server.py').read_text(encoding='utf-8')
        implementations={name:(root/'detection'/name).read_text(encoding='utf-8') for name in ['analysis.py','ai_analysis.py']}
        require_detection_analysis_boundary(source,implementations)
        for filename,method in [('analysis.py','analyze_bgr'),('ai_analysis.py','analyze_bgr_ai_detection')]:
            tree=ast.parse(implementations[filename]); node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==method)
            node.body.insert(0,ast.parse('dispatch_plc_for_detection()').body[0]); ast.fix_missing_locations(tree)
            with self.assertRaisesRegex(AssertionError,'PLC dispatch'): require_detection_analysis_boundary(source,{**implementations,filename:ast.unparse(tree)})
        for mutation in ['forward','decorator','delegate','ordinary-constructor','ai-constructor','ordinary-import','ai-import']:
            tree=ast.parse(source)
            if mutation.endswith('-constructor'):
                receiver='_detection_analysis' if mutation.startswith('ordinary') else '_ai_detection_analysis'
                binding=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==receiver for t in n.targets))
                binding.value.func.id='UninspectedAnalysis'
            elif mutation.endswith('-import'):
                module='detection.analysis' if mutation.startswith('ordinary') else 'detection.ai_analysis'
                imported=next(n for n in tree.body if isinstance(n,ast.ImportFrom) and n.module==module)
                imported.module='uninspected.analysis'
            elif mutation=='delegate':
                route=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='AnalysisRouting')
                route.args[1].body.func=ast.parse('_ai_detection_analysis.analyze_bgr_ai_detection',mode='eval').body
            else:
                node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='analyze_bgr_ai_detection')
                if mutation=='forward': node.body[0].value.func.value.id='_uninspected'
                else: node.decorator_list=[]
            ast.fix_missing_locations(tree)
            with self.assertRaises(AssertionError): require_detection_analysis_boundary(ast.unparse(tree),implementations)


    def test_independent_ordinary_services_interleave_without_root_state(self):
        from local_inspection_service.detection.analysis import DetectionAnalysis
        from local_inspection_service.detection.analysis_ports import AnalysisInput,AnalysisRouting,AnalysisInference,AnalysisOutput
        services=[]
        for owner in ['alice','bob']:
            f=AnalysisFixture(self.f.root/owner); f.spec['id']=owner; f.spec['label']=owner; f.rule['owner']=owner
            f.ocr_detections=[{'owner':owner}]; f.url.side_effect=lambda path,owner=owner:owner+'/'+path.name
            scope=Mock(return_value=f.scope); task=Mock(return_value=f.sanitize); model=Mock(return_value=f.model)
            resize=Mock(return_value=f.resize); images=Mock(return_value=f.backend); text=Mock(return_value=f.text)
            service=DetectionAnalysis(AnalysisInput(f.load,scope,f.selected,task,f.state_load),AnalysisRouting(Mock(),f.ai,f.retired,text),
                AnalysisInference(model,f.device,f.parse,f.ocr,f.apply,f.draw),AnalysisOutput(f.directory,resize,lambda:640,images,lambda:87,f.url))
            self.assertEqual(f.events,[])
            for provider in [scope,task,model,resize,images,text]: provider.assert_not_called()
            services.append((owner,f,service,scope,model,resize,images))
        with ExitStack() as stack:
            for name in ['load_config','scope_config_for_user','selected_model_spec','model','yolo_inference_device','parse_detections',
                         'attach_ocr_results','apply_rule','draw_detections','output_write_dir','resize_bgr_max_side','output_url','analyze_bgr_ai_detection']:
                stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('root callback')))
            stack.enter_context(patch.object(self.api,'cv2',object()))
            for repetition in [1,2]:
                for owner,f,service,scope,model,resize,images in services:
                    result=service.analyze_bgr(f.image,'req','selected-id')
                    self.assertEqual(result['model']['id'],owner); self.assertEqual(result['annotated_url'],owner+'/req_annotated.jpg')
                    self.assertIs(result['detections'],f.ocr_detections); self.assertIs(result['rule'],f.rule)
                    self.assertEqual(f.write.call_args.args[0],str(f.root/'req_annotated.jpg')); self.assertIs(f.write.call_args.args[1],f.preview)
                    self.assertEqual(f.scope.call_args_list,[call(f.config)]*repetition); self.assertEqual(scope.call_count,repetition)
                    self.assertEqual(model.call_count,repetition); self.assertEqual(resize.call_count,repetition); self.assertEqual(images.call_count,2*repetition)

    def test_independent_scope_provider_failure_precedes_configuration_read(self):
        from local_inspection_service.detection.analysis import DetectionAnalysis
        from local_inspection_service.detection.analysis_ports import AnalysisInput,AnalysisRouting,AnalysisInference,AnalysisOutput
        f=self.f; error=OSError('scope provider'); scope=Mock(side_effect=error)
        service=DetectionAnalysis(AnalysisInput(f.load,scope,f.selected,lambda:f.sanitize,f.state_load),AnalysisRouting(Mock(),f.ai,f.retired,lambda:f.text),
            AnalysisInference(lambda:f.model,f.device,f.parse,f.ocr,f.apply,f.draw),AnalysisOutput(f.directory,lambda:f.resize,lambda:640,lambda:f.backend,lambda:87,f.url))
        scope.assert_not_called()
        with self.assertRaises(OSError) as caught: service.analyze_bgr(f.image,'req')
        self.assertIs(caught.exception,error); scope.assert_called_once_with(); f.load.assert_not_called(); self.assertEqual(f.events,[])


    def test_fallback_formatter_capture_precedes_exception_text_and_never_retries(self):
        entry=self.api.analyze_bgr
        for mode in ['success','none','error']:
            with self.subTest(mode=mode), ExitStack() as stack:
                f=AnalysisFixture(self.f.root); f.bind(self.api,stack); events=[]
                f.spec={'id':'ai','is_ai_detection':True}; f.sanitize.side_effect=None; f.sanitize.return_value='task'
                f.state={'settings':{'enabled':True,'serving_mode':'promoted_yolo'},'active_model_id':'student'}
                later=Mock(return_value='late'); failure=OSError('formatter failed')
                first=Mock(return_value='first',side_effect=[failure,'retry'] if mode=='error' else None)
                class PromotedError(Exception):
                    def __str__(inner):
                        events.append('str'); self.api.bounded_text=later; return 'student failed'
                promoted=PromotedError(); recurse=Mock(side_effect=[promoted,f.promoted_result])
                stack.enter_context(patch.object(self.api,'analyze_bgr',recurse))
                self.api.bounded_text=None if mode=='none' else first
                f.ai.side_effect=lambda *args,**kwargs:events.append('teacher') or f.ai_result
                previous={'previous':True}; f.ai_result['ai_auto_optimize']=previous
                if mode=='success':
                    result=entry(f.image,'req','ai'); self.assertIs(result,f.ai_result)
                    self.assertEqual(result['ai_auto_optimize']['fallback_reason'],'first')
                else:
                    with self.assertRaises(TypeError if mode=='none' else OSError) as caught: entry(f.image,'req','ai')
                    if mode=='error': self.assertIs(caught.exception,failure)
                    self.assertIs(f.ai_result['ai_auto_optimize'],previous)
                self.assertEqual(events,['teacher','str']); recurse.assert_called_once(); f.ai.assert_called_once(); later.assert_not_called()
                if mode=='none': first.assert_not_called()
                else: first.assert_called_once_with('student failed',180)


    def test_mapping_reads_stop_at_the_first_failure_without_retry(self):
        windows=[('spec','get','is_ai_detection',1),('spec','get','is_label_sheet_match',1),
                 ('spec','get','uses_ocr',1),('spec','get','uses_ocr',2),('spec','get','confidence_threshold',1),
                 ('spec','item','id',1),('spec','item','id',2),('spec','item','label',1),
                 ('config','get','confidence_threshold',1),('config','item','image_size',1),('rule','item','passed',1),
                 ('spec','get','task_id',1),('spec','get','run_id',1),('state','get','settings',1),
                 ('state','get','settings',2),('state','get','active_model_id',1),
                 ('settings','get','enabled',1),('settings','get','serving_mode',1)]
        for owner,operation,key,occurrence in windows:
            with self.subTest(owner=owner,key=key,occurrence=occurrence),ExitStack() as stack:
                f=AnalysisFixture(self.f.root);f.bind(self.api,stack);error=RuntimeError('mapping read');reads=[];count=0
                def visit(where,op,field):
                    nonlocal count
                    reads.append((where,op,field))
                    if (where,op,field)==(owner,operation,key):
                        count+=1
                        if count==occurrence:raise error
                class ReadMap(dict):
                    def __init__(inner,where,values):super().__init__(values);inner.where=where
                    def get(inner,field,default=None):visit(inner.where,'get',field);return super().get(field,default)
                    def __getitem__(inner,field):visit(inner.where,'item',field);return super().__getitem__(field)
                if owner in ('state','settings') or key in ('task_id','run_id'):
                    f.spec.update(is_ai_detection=True,run_id='task');f.sanitize.side_effect=lambda value:'task'
                    f.state={'settings':ReadMap('settings',{'enabled':True,'serving_mode':'promoted_yolo'}),'active_model_id':'student'}
                    stack.enter_context(patch.object(self.api,'analyze_bgr',Mock(return_value=f.promoted_result)))
                f.spec=ReadMap('spec',f.spec);f.scoped=ReadMap('config',f.scoped);f.rule=ReadMap('rule',f.rule);f.state=ReadMap('state',f.state)
                # Keep the actual entry before substituting promoted recursion.
                with self.assertRaises(RuntimeError) as caught:self._mapping_entry(f)
                self.assertIs(caught.exception,error);self.assertEqual(count,occurrence);self.assertEqual(reads[-1],(owner,operation,key));f.url.assert_not_called()

    def _mapping_entry(self,f):
        return self._original_analysis_entry(f.image,'req')

    def test_ai_routing_callback_failures_do_not_retry(self):
        entry=self.api.analyze_bgr
        for stage in ('sanitize','state','direct','fallback'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=AnalysisFixture(self.f.root);f.bind(self.api,stack);f.spec['is_ai_detection']=True
                f.sanitize.side_effect=lambda value:'task';f.state={'settings':{'enabled':True,'serving_mode':'promoted_yolo'},'active_model_id':'student'}
                if stage=='direct':f.state={}
                if stage=='fallback':stack.enter_context(patch.object(self.api,'analyze_bgr',Mock(side_effect=OSError('student'))))
                port=f.sanitize if stage=='sanitize' else f.state_load if stage=='state' else f.ai
                original=port.side_effect;error=OSError(stage);calls=0
                def once(*args,**kwargs):
                    nonlocal calls
                    calls+=1
                    if calls==1:raise error
                    return original(*args,**kwargs)
                port.side_effect=once
                with self.assertRaises(OSError) as caught:entry(f.image,'req')
                self.assertIs(caught.exception,error);self.assertEqual(calls,1);f.text.assert_not_called();f.url.assert_not_called()

    def test_independent_policy_and_provider_failures_do_not_retry(self):
        from local_inspection_service.detection.analysis import DetectionAnalysis
        from local_inspection_service.detection.analysis_ports import AnalysisInput,AnalysisRouting,AnalysisInference,AnalysisOutput
        for stage,occurrence in [('scope',1),('task',1),('model',1),('resize',1),('max_side',1),('images',1),('images',2),('quality',1),('text',1)]:
            with self.subTest(stage=stage,occurrence=occurrence):
                f=AnalysisFixture(self.f.root);error=OSError(stage);counts={}
                def provider(name,value):
                    def read():
                        counts[name]=counts.get(name,0)+1
                        if name==stage and counts[name]==occurrence:raise error
                        return value
                    return read
                if stage in ('task','text'):f.spec['is_ai_detection']=True
                f.sanitize.side_effect=lambda value:'task';f.state={'settings':{'enabled':True,'serving_mode':'promoted_yolo'},'active_model_id':'student'}
                service=DetectionAnalysis(AnalysisInput(f.load,provider('scope',f.scope),f.selected,provider('task',f.sanitize),f.state_load),
                    AnalysisRouting(Mock(side_effect=OSError('student')),f.ai,f.retired,provider('text',f.text)),
                    AnalysisInference(provider('model',f.model),f.device,f.parse,f.ocr,f.apply,f.draw),
                    AnalysisOutput(f.directory,provider('resize',f.resize),provider('max_side',640),provider('images',f.backend),provider('quality',87),f.url))
                with self.assertRaises(OSError) as caught:service.analyze_bgr(f.image,'req')
                self.assertIs(caught.exception,error);self.assertEqual(counts[stage],occurrence);f.url.assert_not_called()


    def test_original_callback_capture_at_each_effect_boundary(self):
        for stage in ('sanitize','formatter','resize','writer'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(stage=stage,mode=mode):capture_ordinary(self.api,AnalysisFixture,self.f.root,stage,mode)

    def test_independent_resize_capture_before_maximum_provider(self):
        for mode in ('ordinary','prior','missing'):
            with self.subTest(mode=mode):capture_independent_resize(AnalysisFixture,self.f.root,mode)


if __name__=='__main__': unittest.main()
