"""Synthetic geometry, drawing and output contracts without inference or device access."""
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


def capture_annotation_backend_refresh(ns):
 import numpy as np
 events=[];image=np.zeros((120,200,3),dtype=np.uint8);result=object()
 with patch.dict(ns):
  class Backend:
   def __init__(self,name):self.name=name
   @property
   def LINE_AA(self):events.append((self.name,'LINE_AA'));return 101 if self.name=='A' else 202
   @property
   def FONT_HERSHEY_SIMPLEX(self):events.append((self.name,'FONT'));return 11 if self.name=='A' else 22
   def rectangle(self,*args):events.append((self.name,'rectangle'));return args[0]
   def getTextSize(self,*args):events.append((self.name,'size'));return ((20,8),3)
   def putText(self,*args):
    events.append((self.name,'put'))
    if self.name=='A':ns['cv2']=second
    return args[0]
   def addWeighted(self,*args):events.append((self.name,'blend'));return result
  first,second=Backend('A'),Backend('B');ns['cv2']=first;ns['bounded_text']=lambda value,limit:'Label';ns['ai_box_2d_to_pixels']=lambda *args:(1,2,30,40)
  caught=None;actual=None
  try:actual=ns['draw_ai_detection_boxes'](image,[{'box_2d':[],'label':'X'},{'box_2d':[],'label':'Y'}],{})
  except BaseException as exc:caught=exc
  assert caught is None,(caught,events)
  expected=[]
  for mark in ('A','B'):expected.extend((mark,operation) for operation in ('rectangle','LINE_AA','rectangle','FONT','size','rectangle','FONT','LINE_AA','put'))
  expected.append(('B','blend'));assert events==expected,(events,expected);assert actual is result
 return events


class AnnotationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ); cls.environment.start(); cls.runtime=tempfile.TemporaryDirectory(prefix='annotation-contract-')
        root=Path(cls.runtime.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        for target in ['requests.sessions.Session.request','subprocess.Popen','os.kill']:
            self.stack.enter_context(patch(target,side_effect=AssertionError('external operation')))
        for name in ['normalize_ai_box_2d','ai_box_2d_to_pixels','draw_ai_detection_boxes','write_ai_original_output','bounded_text','cv2']:
            self.stack.enter_context(patch.object(self.api,name,getattr(self.api,name)))
        self.output=Path(self.runtime.name)/self.id().split('.')[-1]; self.output.mkdir(exist_ok=True)
        self.directory=self.stack.enter_context(patch.object(self.api,'output_write_dir',return_value=self.output))
        self.url=self.stack.enter_context(patch.object(self.api,'output_url',side_effect=lambda path:'/fixture/'+path.name))
    def backend(self):
        return SimpleNamespace(IMWRITE_JPEG_QUALITY=11,LINE_AA=12,FONT_HERSHEY_SIMPLEX=13,
            imwrite=Mock(return_value=False),rectangle=Mock(side_effect=lambda image,*args:image),
            getTextSize=Mock(return_value=((20,8),3)),putText=Mock(side_effect=lambda image,*args:image),
            addWeighted=Mock(return_value=np.full((2,2,3),77,dtype=np.uint8)))

    def test_normalize_geometry_strict_types_clamp_and_rounding_order(self):
        normalize=self.api.normalize_ai_box_2d
        for value in [None,{},'0,0,1,1',[],[0,0,1], [0,0,1,1,2], [False,0,1,1],[0,0,float('nan'),1],
                      [0,0,float('inf'),1],[0,0,'1',1],[1,0,1,1],[2,0,1,1],[0,2,1,1],[-5,-5,-1,2]]:
            with self.subTest(value=value): self.assertIsNone(normalize(value))
        class Integer(int): pass
        class Float(float): pass
        for value in [Integer(1),Float(1),np.int64(1),np.float64(1)]: self.assertIsNone(normalize([0,0,value,2]))
        self.assertEqual(normalize((-10,-2,1001,1002)),[0.0,0.0,1000.0,1000.0])
        self.assertEqual(normalize([1.234,2.346,3.456,4.567]),[1.23,2.35,3.46,4.57])
        tiny=[0,0,0.001,0.001]
        self.assertEqual(normalize(tiny),[0.0,0.0,0.0,0.0]); self.assertEqual(tiny,[0,0,0.001,0.001])
        self.assertIsNone(self.api.ai_box_2d_to_pixels(tiny,(100,200,3)))

    def test_pixel_projection_floors_ceils_and_normalizes_before_shape(self):
        convert=self.api.ai_box_2d_to_pixels
        self.assertEqual(convert([0,0,1000,1000],(120,200,3)),(0,0,199,119))
        self.assertEqual(convert([100,200,400,600],(120,200,3)),(39,11,120,48))
        self.assertEqual(convert([-1,-1,1001,1001],(2,2)),(0,0,1,1))
        for shape in [(0,20),(20,1),(-1,20)]: self.assertIsNone(convert([0,0,1000,1000],shape))
        class Shape:
            def __getitem__(inner,key): raise AssertionError('shape read too early')
        self.assertIsNone(convert(None,Shape()))
        error=OSError('normalize failed'); normalizer=Mock(side_effect=[error,[0,0,1000,1000]])
        self.api.normalize_ai_box_2d=normalizer
        with self.assertRaises(OSError) as caught: convert([0,0,1,1],Shape())
        self.assertIs(caught.exception,error); normalizer.assert_called_once_with([0,0,1,1])

    def test_empty_draw_has_no_copy_or_rule_read(self):
        image=SimpleNamespace(shape=(120,200,3),copy=Mock(side_effect=AssertionError('copy')))
        rule=Mock(); rule.get.side_effect=AssertionError('rule read')
        self.api.cv2=self.backend()
        for detections in [[],[None,False,'bad'],[{'box_2d':[3,0,1,1]}]]:
            self.assertIsNone(self.api.draw_ai_detection_boxes(image,detections,rule))
        image.copy.assert_not_called(); rule.get.assert_not_called(); self.api.cv2.rectangle.assert_not_called()

    def test_complete_draw_calls_order_copies_and_return_alias(self):
        backend=self.backend(); self.api.cv2=backend; events=[]
        copies=[np.full((120,200,3),11,dtype=np.uint8),np.full((120,200,3),22,dtype=np.uint8)]
        image=SimpleNamespace(shape=(120,200,3),copy=Mock(side_effect=lambda:events.append('copy') or copies[len(events)-1]))
        text=Mock(return_value='Label'); self.api.bounded_text=text
        row={'box_2d':[100,200,400,600],'label':'long label','present':False,'confidence':True}
        result=self.api.draw_ai_detection_boxes(image,[None,row],{'passed':'false'})
        self.assertIs(result,backend.addWeighted.return_value); self.assertEqual(events,['copy','copy']); self.assertEqual(image.copy.call_count,2)
        self.assertIsNot(copies[0],copies[1]); text.assert_called_once_with('long label',24)
        rectangles=backend.rectangle.call_args_list
        self.assertEqual(len(rectangles),3)
        self.assertIs(rectangles[0].args[0],copies[1]); self.assertEqual(rectangles[0].args[1:],((39,11),(120,48),(32,196,92),-1))
        self.assertIs(rectangles[1].args[0],copies[0]); self.assertEqual(rectangles[1].args[1:],((39,11),(120,48),(32,196,92),2,12))
        self.assertIs(rectangles[2].args[0],copies[0]); self.assertEqual(rectangles[2].args[1:],((39,0),(69,17),(32,196,92),-1))
        backend.getTextSize.assert_called_once_with('Label 1.00',13,0.45,1)
        self.assertIs(backend.putText.call_args.args[0],copies[0])
        self.assertEqual(backend.putText.call_args.args[1:],('Label 1.00',(44,11),13,0.45,(255,255,255),1,12))
        self.assertIs(backend.addWeighted.call_args.args[0],copies[1]); self.assertIs(backend.addWeighted.call_args.args[2],copies[0])
        self.assertEqual((backend.addWeighted.call_args.args[1],*backend.addWeighted.call_args.args[3:]),(0.1,0.9,0))

    def test_draw_confidence_font_limits_and_original_image_unchanged(self):
        image=np.full((120,200,3),30,dtype=np.uint8); original=image.copy()
        real=self.api.cv2
        drawn=self.api.draw_ai_detection_boxes(image,[{'box_2d':[100,200,700,800],'label':'Marker','confidence':0.8}],{'passed':False})
        self.assertIsInstance(drawn,np.ndarray); self.assertFalse(np.array_equal(drawn,image)); np.testing.assert_array_equal(image,original)
        self.assertFalse(np.shares_memory(drawn,image)); self.assertEqual(drawn.shape,image.shape)
        for confidence,expected in [(True,'X 1.00'),(float('inf'),'X inf'),(float('nan'),'X'),('bad','X'),(-1,'X'),(0.125,'X 0.12')]:
            backend=self.backend(); self.api.cv2=backend
            self.api.draw_ai_detection_boxes(image,[{'box_2d':[0,0,1000,1000],'label':'X','confidence':confidence}],{})
            self.assertEqual(backend.getTextSize.call_args.args[0],expected)
            self.assertEqual(backend.rectangle.call_args_list[0].args[3],(40,180,255))
        for shape,font,thickness in [((40,60,3),0.45,2),((400,500,3),0.625,2),((800,900,3),0.7,4)]:
            backend=self.backend(); self.api.cv2=backend
            self.api.draw_ai_detection_boxes(np.zeros(shape,dtype=np.uint8),[{'box_2d':[0,0,1000,1000],'label':'L'*30}],{})
            self.assertEqual(backend.getTextSize.call_args.args,('L'*24,13,font,max(1,thickness-1)))
            self.assertEqual(backend.rectangle.call_args_list[1].args[-2],thickness)
        self.api.cv2=real

    def test_real_synthetic_outputs_and_none_only_fallback(self):
        image=np.full((80,100,3),18,dtype=np.uint8)
        result=self.api.write_ai_annotated_output(image,'empty',[],{})
        self.assertEqual(result,'/fixture/empty_ai_original.jpg'); self.assertFalse((self.output/'empty_ai_annotated.jpg').exists())
        saved=self.api.cv2.imread(str(self.output/'empty_ai_original.jpg')); self.assertIsNotNone(saved)
        self.assertLessEqual(int(self.api.cv2.absdiff(saved,image).max()),3)
        self.assertEqual(self.api.write_ai_annotated_output(image,'box',[{'box_2d':[100,100,800,800],'label':'X'}],{}),'/fixture/box_ai_annotated.jpg')
        saved=self.api.cv2.imread(str(self.output/'box_ai_annotated.jpg')); self.assertIsNotNone(saved); self.assertFalse(np.array_equal(saved,image))
        backend=self.backend(); self.api.cv2=backend
        self.api.draw_ai_detection_boxes=Mock(return_value=False); self.api.write_ai_original_output=Mock(side_effect=AssertionError('not None'))
        self.assertEqual(self.api.write_ai_annotated_output(image,'false',[],{}),'/fixture/false_ai_annotated.jpg')
        self.assertIs(backend.imwrite.call_args.args[1],False)
        self.assertEqual(backend.imwrite.call_args.args[2],[11,92])
        self.assertEqual(self.url.call_args.args[0],self.output/'false_ai_annotated.jpg')

    def test_write_failures_stop_without_retry_or_later_side_effect(self):
        for annotated in [False,True]:
            stages=['draw','directory','path','quality','write','url'] if annotated else ['directory','path','quality','write','url']
            for stage in stages:
                with self.subTest(annotated=annotated,stage=stage):
                    events=[]; counts={}; error=OSError(stage); image=np.zeros((2,2,3),dtype=np.uint8)
                    def visit(name,value):
                        events.append(name); counts[name]=counts.get(name,0)+1
                        if name==stage and counts[name]==1: raise error
                        return value
                    class Out:
                        def __str__(inner): return visit('path','synthetic.jpg')
                    out=Out()
                    class Directory:
                        def __truediv__(inner,name): return out
                    class Quality:
                        def __int__(inner): return visit('quality',11)
                    backend=self.backend(); backend.IMWRITE_JPEG_QUALITY=Quality(); backend.imwrite.side_effect=lambda *a:visit('write',False)
                    with patch.object(self.api,'cv2',backend), patch.object(self.api,'draw_ai_detection_boxes',side_effect=lambda *a:visit('draw',image)), \
                         patch.object(self.api,'output_write_dir',side_effect=lambda *a:visit('directory',Directory())), \
                         patch.object(self.api,'output_url',side_effect=lambda *a:visit('url','url')):
                        with self.assertRaises(OSError) as caught:
                            if annotated: self.api.write_ai_annotated_output(image,'id',[],{})
                            else: self.api.write_ai_original_output(image,'id')
                    self.assertIs(caught.exception,error); self.assertEqual(events,stages[:stages.index(stage)+1])
                    self.assertEqual(counts[stage],1)

    def test_write_callee_before_path_but_quality_after_path(self):
        for annotated in [False,True]:
            with self.subTest(annotated=annotated):
                first=self.backend(); second=self.backend(); second.IMWRITE_JPEG_QUALITY=22; image=np.zeros((2,2,3),dtype=np.uint8)
                events=[]
                class Out:
                    def __str__(inner): events.append('path'); self.api.cv2=second; return 'synthetic.jpg'
                out=Out()
                class Directory:
                    def __truediv__(inner,name): events.append(name); return out
                self.directory.return_value=Directory(); self.url.side_effect=lambda path:events.append(('url',path)) or 'url'
                self.api.cv2=first; self.api.draw_ai_detection_boxes=Mock(return_value=image)
                result=self.api.write_ai_annotated_output(image,'id',[],{}) if annotated else self.api.write_ai_original_output(image,'id')
                self.assertEqual(result,'url'); first.imwrite.assert_called_once(); second.imwrite.assert_not_called()
                self.assertEqual(first.imwrite.call_args.args[0],'synthetic.jpg'); self.assertIs(first.imwrite.call_args.args[1],image)
                self.assertEqual(first.imwrite.call_args.args[2],[22,92]); self.assertIs(events[-1][1],out)

    def test_draw_callbacks_capture_before_fields_and_rebind_next_box(self):
        image=np.zeros((120,200,3),dtype=np.uint8); backend=self.backend(); self.api.cv2=backend; events=[]
        def pixels(name):
            def convert(*args): events.append(name); return (1,2,30,40)
            return convert
        old,new=pixels('old-pixels'),pixels('new-pixels')
        class Detection(dict):
            def get(inner,key,default=None):
                if key=='box_2d': self.api.ai_box_2d_to_pixels=new
                if key=='label': self.api.bounded_text=new_text
                return super().get(key,default)
        def old_text(*args): events.append('old-text'); return 'Old'
        def new_text(*args): events.append('new-text'); return 'New'
        self.api.ai_box_2d_to_pixels=old; self.api.bounded_text=old_text
        self.api.draw_ai_detection_boxes(image,[Detection(box_2d=[],label='X'),{'box_2d':[],'label':'Y'}],{})
        self.assertEqual(events,['old-pixels','new-pixels','old-text','new-text'])
        self.assertEqual([c.args[0] for c in backend.getTextSize.call_args_list],['Old','New'])


    def test_drawing_callees_and_later_constants_can_come_from_different_backends(self):
        events=[]; image=np.zeros((120,200,3),dtype=np.uint8); result=object(); instances={}
        class Backend:
            def __init__(inner,name): inner.name=name
            @property
            def LINE_AA(inner):
                events.append((inner.name,'LINE_AA')); self.api.cv2=instances['C' if inner.name=='B' else 'F']
                return 102 if inner.name=='B' else 105
            @property
            def FONT_HERSHEY_SIMPLEX(inner):
                events.append((inner.name,'FONT')); self.api.cv2=instances['D' if inner.name=='C' else 'E']
                return 203 if inner.name=='C' else 204
            def rectangle(inner,*args):
                events.append((inner.name,'rectangle',args[1:]))
                if inner.name=='A': self.api.cv2=instances['B']
            def getTextSize(inner,*args): events.append((inner.name,'getTextSize',args)); return ((20,8),3)
            def putText(inner,*args): events.append((inner.name,'putText',args[1:]))
            def addWeighted(inner,*args): events.append((inner.name,'addWeighted')); return result
        instances.update({name:Backend(name) for name in 'ABCDEF'}); self.api.cv2=instances['A']
        actual=self.api.draw_ai_detection_boxes(image,[{'box_2d':[100,200,400,600],'label':'X'}],{})
        self.assertIs(actual,result)
        self.assertEqual([(event[0],event[1]) for event in events],[('A','rectangle'),('B','LINE_AA'),('B','rectangle'),
            ('C','FONT'),('C','getTextSize'),('D','rectangle'),('D','FONT'),('E','LINE_AA'),('D','putText'),('F','addWeighted')])
        self.assertEqual(events[2][2][-1],102); self.assertEqual(events[4][2],('X',203,0.45,1))
        self.assertEqual(events[8][2][2],204); self.assertEqual(events[8][2][-1],105)

    def test_noncallable_targets_still_evaluate_pixel_text_and_write_arguments(self):
        events=[]; pixels=Mock(return_value=(1,2,30,40)); backend=self.backend(); self.api.cv2=backend
        class Detection(dict):
            def get(inner,key,default=None):
                if key=='box_2d': events.append('box'); self.api.ai_box_2d_to_pixels=pixels
                return super().get(key,default)
        class Image:
            @property
            def shape(inner): events.append('shape'); return (120,200,3)
        self.api.ai_box_2d_to_pixels=None
        with self.assertRaises(TypeError): self.api.draw_ai_detection_boxes(Image(),[Detection(box_2d=[])],{})
        self.assertEqual(events,['box','shape']); pixels.assert_not_called(); backend.rectangle.assert_not_called()
        events.clear(); self.api.ai_box_2d_to_pixels=pixels; formatter=Mock(return_value='text'); rectangles=0
        def rectangle(*args):
            nonlocal rectangles
            rectangles+=1
            if rectangles==2: self.api.bounded_text=None
        backend.rectangle.side_effect=rectangle
        class Label(dict):
            def get(inner,key,default=None):
                events.append(key)
                if key=='label': self.api.bounded_text=formatter
                return super().get(key,default)
        with self.assertRaises(TypeError): self.api.draw_ai_detection_boxes(np.zeros((120,200,3),dtype=np.uint8),[Label(box_2d=[],label='X')],{})
        self.assertEqual(events,['box_2d','label']); formatter.assert_not_called(); backend.getTextSize.assert_not_called()
        for annotated in [False,True]:
            with self.subTest(annotated=annotated):
                events.clear(); backend=self.backend(); writer=backend.imwrite; backend.imwrite=None; self.api.cv2=backend
                class Out:
                    name = 'output.jpg'
                    def __str__(inner): events.append('path'); backend.imwrite=writer; return 'output.jpg'
                class Directory:
                    def __truediv__(inner,name): return Out()
                class Quality:
                    def __int__(inner): events.append('quality'); return 11
                backend.IMWRITE_JPEG_QUALITY=Quality(); self.directory.return_value=Directory(); self.url.reset_mock()
                self.api.draw_ai_detection_boxes=Mock(return_value=False)
                with self.assertRaises(TypeError):
                    if annotated: self.api.write_ai_annotated_output(None,'id',[],{})
                    else: self.api.write_ai_original_output(None,'id')
                self.assertEqual(events,['path','quality']); writer.assert_not_called(); self.url.assert_not_called()

    def test_write_error_keeps_partial_file_and_skips_url(self):
        for annotated in [False,True]:
            with self.subTest(annotated=annotated):
                backend=self.backend(); self.api.cv2=backend; error=OSError('write interrupted'); image=np.zeros((2,2,3),dtype=np.uint8)
                def write(path,*args): Path(path).write_bytes(b'synthetic-partial'); raise error
                backend.imwrite.side_effect=write; self.url.reset_mock(); self.api.draw_ai_detection_boxes=Mock(return_value=image)
                with self.assertRaises(OSError) as caught:
                    if annotated: self.api.write_ai_annotated_output(image,'partial-annotated',[],{})
                    else: self.api.write_ai_original_output(image,'partial-original')
                self.assertIs(caught.exception,error); backend.imwrite.assert_called_once(); self.url.assert_not_called()
                path=Path(backend.imwrite.call_args.args[0]); self.assertTrue(path.is_relative_to(self.output)); self.assertEqual(path.read_bytes(),b'synthetic-partial')


    def test_every_draw_stage_stops_on_first_error_without_retry(self):
        stages=['pixels','copy1','copy2','rectangle1','rectangle2','text','size','rectangle3','put','blend']
        for stage in stages:
            with self.subTest(stage=stage):
                events=[]; counts={}; error=OSError(stage); array=np.zeros((120,200,3),dtype=np.uint8)
                def visit(name,value):
                    counts[name]=counts.get(name,0)+1; events.append(name)
                    if name==stage and counts[name]==1: raise error
                    return value
                copies=0; rectangles=0
                def copy_image():
                    nonlocal copies
                    copies+=1; return visit('copy'+str(copies),array.copy())
                def rectangle(*args):
                    nonlocal rectangles
                    rectangles+=1; return visit('rectangle'+str(rectangles),args[0])
                backend=self.backend(); backend.rectangle.side_effect=rectangle
                backend.getTextSize.side_effect=lambda *a:visit('size',((20,8),3))
                backend.putText.side_effect=lambda *a:visit('put',a[0])
                backend.addWeighted.side_effect=lambda *a:visit('blend',array)
                image=SimpleNamespace(shape=(120,200,3),copy=Mock(side_effect=copy_image))
                with patch.object(self.api,'cv2',backend), \
                     patch.object(self.api,'ai_box_2d_to_pixels',side_effect=lambda *a:visit('pixels',(1,2,30,40))), \
                     patch.object(self.api,'bounded_text',side_effect=lambda *a:visit('text','Label')):
                    with self.assertRaises(OSError) as caught:
                        self.api.draw_ai_detection_boxes(image,[{'box_2d':[],'label':'Label'}],{})
                self.assertIs(caught.exception,error); self.assertEqual(events,stages[:stages.index(stage)+1])
                self.assertEqual(counts[stage],1)


    def test_writer_capture_after_directory_join_and_draw_before_path(self):
        for annotated,stage in [(False,'directory'),(False,'join'),(True,'draw'),(True,'directory'),(True,'join')]:
            with self.subTest(annotated=annotated,stage=stage):
                before,captured,later=self.backend(),self.backend(),self.backend()
                before.IMWRITE_JPEG_QUALITY=10; captured.IMWRITE_JPEG_QUALITY=20; later.IMWRITE_JPEG_QUALITY=30
                image=np.zeros((2,2,3),dtype=np.uint8); active=True
                def reach(name):
                    if active and name==stage: self.api.cv2=captured
                class Out:
                    def __str__(inner): self.api.cv2=later; return 'synthetic.jpg'
                class Directory:
                    def __truediv__(inner,name): reach('join'); return Out()
                def directory(name): reach('directory'); return Directory()
                def draw(*args): reach('draw'); return image
                self.api.cv2=before
                with patch.object(self.api,'output_write_dir',side_effect=directory), patch.object(self.api,'output_url',return_value='url'), \
                     patch.object(self.api,'draw_ai_detection_boxes',side_effect=draw):
                    for repetition in [1,2]:
                        result=self.api.write_ai_annotated_output(image,'id',[],{}) if annotated else self.api.write_ai_original_output(image,'id')
                        self.assertEqual(result,'url'); active=False
                before.imwrite.assert_not_called(); captured.imwrite.assert_called_once(); later.imwrite.assert_called_once()
                for writer in [captured.imwrite,later.imwrite]:
                    self.assertEqual(writer.call_args.args[0],'synthetic.jpg'); self.assertIs(writer.call_args.args[1],image)
                    self.assertEqual(writer.call_args.args[2],[30,92])


    def test_independent_services_interleave_owned_paths_backends_and_callbacks(self):
        from local_inspection_service.detection.annotation import DetectionAnnotation, normalize_ai_box_2d
        services=[]; image=np.full((120,200,3),30,dtype=np.uint8)
        for owner in ['alice','bob']:
            holder={}; backend=self.backend(); output=self.output/owner
            normalize=Mock(side_effect=normalize_ai_box_2d); text=Mock(return_value=owner)
            pixels=Mock(side_effect=lambda holder=holder:holder['service'].ai_box_2d_to_pixels)
            texts=Mock(return_value=text); images=Mock(return_value=backend)
            directory=Mock(return_value=output); url=Mock(side_effect=lambda path,owner=owner:owner+'/'+path.name)
            draw=Mock(side_effect=lambda *args,holder=holder:holder['service'].draw_ai_detection_boxes(*args))
            original=Mock(side_effect=lambda *args,holder=holder:holder['service'].write_ai_original_output(*args))
            service=DetectionAnnotation(normalize,pixels,texts,images,directory,url,draw,original); holder['service']=service
            for port in [normalize,pixels,texts,images,directory,url,draw,original,text]: port.assert_not_called()
            services.append((owner,service,backend,output,normalize,pixels,texts,images,directory,url,draw,original,text))
        with ExitStack() as stack:
            for name in ['normalize_ai_box_2d','ai_box_2d_to_pixels','bounded_text','output_write_dir','output_url','draw_ai_detection_boxes','write_ai_original_output']:
                stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('root callback')))
            stack.enter_context(patch.object(self.api,'cv2',object()))
            for repetition in [1,2]:
                for owner,service,backend,output,normalize,pixels,texts,images,directory,url,draw,original,text in services:
                    self.assertEqual(service.ai_box_2d_to_pixels([0,0,1000,1000],image.shape),(0,0,199,119))
                    self.assertEqual(service.write_ai_original_output(image,'original'),owner+'/original_ai_original.jpg')
                    self.assertEqual(service.write_ai_annotated_output(image,'box',[{'box_2d':[0,0,1000,1000],'label':'X'}],{}),owner+'/box_ai_annotated.jpg')
                    self.assertEqual(service.write_ai_annotated_output(image,'empty',[],{}),owner+'/empty_ai_original.jpg')
                    self.assertEqual(normalize.call_count,2*repetition); self.assertEqual(pixels.call_count,repetition)
                    self.assertEqual(texts.call_count,repetition); self.assertEqual(text.call_args_list,[call('X',24)]*repetition)
                    self.assertEqual(images.call_count,16*repetition); self.assertEqual(draw.call_count,2*repetition); self.assertEqual(original.call_count,repetition)
                    self.assertEqual(directory.call_args_list,[call('ai_detection')]*(3*repetition))
                    expected=[output/'original_ai_original.jpg',output/'box_ai_annotated.jpg',output/'empty_ai_original.jpg']*repetition
                    self.assertEqual(url.call_args_list,[call(path) for path in expected])
                    writes=backend.imwrite.call_args_list; self.assertEqual([entry.args[0] for entry in writes],[str(path) for path in expected])
                    for index,entry in enumerate(writes):
                        self.assertIs(entry.args[1],backend.addWeighted.return_value if index%3==1 else image)
                        self.assertEqual(entry.args[2],[11,92])

    def test_independent_provider_failures_precede_their_argument_reads(self):
        from local_inspection_service.detection.annotation import DetectionAnnotation, normalize_ai_box_2d
        for position in [1,2]:
            with self.subTest(images_lookup=position):
                events=[]; backend=self.backend(); error=OSError('image provider'); count=0
                class Out:
                    def __str__(inner): events.append('path'); return 'synthetic.jpg'
                class Directory:
                    def __truediv__(inner,name): events.append('join'); return Out()
                class Quality:
                    def __int__(inner): events.append('quality'); return 11
                backend.IMWRITE_JPEG_QUALITY=Quality()
                def lookup():
                    nonlocal count
                    count+=1; events.append('images')
                    if count==position: raise error
                    return backend
                images=Mock(side_effect=lookup); directory=Mock(side_effect=lambda kind:events.append('directory') or Directory()); url=Mock(return_value='url')
                service=DetectionAnnotation(normalize_ai_box_2d,Mock(),Mock(),images,directory,url,Mock(),Mock())
                for port in [images,directory,url]: port.assert_not_called()
                with self.assertRaises(OSError) as caught: service.write_ai_original_output(None,'id')
                self.assertIs(caught.exception,error); self.assertEqual(count,position)
                self.assertEqual(events,['directory','join','images'] if position==1 else ['directory','join','images','path','images'])
                backend.imwrite.assert_not_called(); url.assert_not_called()
        for target in ['pixels','text']:
            with self.subTest(target=target):
                events=[]; backend=self.backend(); error=OSError(target)
                class Detection(dict):
                    def get(inner,key,default=None): events.append(key); return super().get(key,default)
                pixels=Mock(return_value=lambda *args:(1,2,30,40)); texts=Mock(return_value=lambda *args:'text')
                if target=='pixels': pixels.side_effect=error
                else: texts.side_effect=error
                service=DetectionAnnotation(normalize_ai_box_2d,pixels,texts,lambda:backend,Mock(),Mock(),Mock(),Mock())
                pixels.assert_not_called(); texts.assert_not_called()
                with self.assertRaises(OSError) as caught: service.draw_ai_detection_boxes(np.zeros((120,200,3),dtype=np.uint8),[Detection(box_2d=[],label='X')],{})
                self.assertIs(caught.exception,error); self.assertEqual(events,[] if target=='pixels' else ['box_2d'])
                self.assertEqual(pixels.call_count,1); self.assertEqual(texts.call_count,int(target=='text'))
                self.assertEqual(backend.rectangle.call_count,0 if target=='pixels' else 2); backend.getTextSize.assert_not_called()


    def test_confidence_errors_only_catch_type_and_value_failures(self):
        for stage in ['get','bool','float']:
            for error_type in [OSError,OverflowError,TypeError,ValueError]:
                with self.subTest(stage=stage,error=error_type):
                    events=[]; counts={}; error=error_type('confidence'); backend=self.backend(); self.api.cv2=backend
                    def visit(name,value):
                        events.append(name); counts[name]=counts.get(name,0)+1
                        if name==stage and counts[name]==1: raise error
                        return value
                    class Confidence:
                        def __bool__(inner): return visit('bool',True)
                        def __float__(inner): return visit('float',0.7)
                    class Detection(dict):
                        def get(inner,key,default=None):
                            if key=='confidence': return visit('get',Confidence())
                            return super().get(key,default)
                    formatter=Mock(return_value='Label')
                    with patch.object(self.api,'bounded_text',formatter):
                        def draw(): return self.api.draw_ai_detection_boxes(np.zeros((120,200,3),dtype=np.uint8),[Detection(box_2d=[0,0,1000,1000],label='X')],{})
                        handled=error_type in [TypeError,ValueError]
                        if handled:
                            self.assertIs(draw(),backend.addWeighted.return_value)
                        else:
                            with self.assertRaises(error_type) as caught: draw()
                            self.assertIs(caught.exception,error)
                    self.assertEqual(events,['get','bool','float'][:['get','bool','float'].index(stage)+1]); self.assertEqual(counts[stage],1)
                    formatter.assert_called_once_with('X',24)
                    self.assertEqual(backend.rectangle.call_count,3 if handled else 2)
                    self.assertEqual(backend.getTextSize.call_count,int(handled)); self.assertEqual(backend.putText.call_count,int(handled))
                    self.assertEqual(backend.addWeighted.call_count,int(handled))
                    if handled: self.assertEqual(backend.getTextSize.call_args.args[0],'Label')


    def test_each_image_provider_failure_is_not_retried(self):
        from local_inspection_service.detection.annotation import DetectionAnnotation, normalize_ai_box_2d
        for operation,total in [('draw',10),('annotated',2)]:
            for position in range(1,total+1):
                with self.subTest(operation=operation,position=position):
                    calls=[]; error=RuntimeError('images lookup'); backend=self.backend(); image=np.zeros((120,200,3),dtype=np.uint8)
                    def images():
                        calls.append('images')
                        if len(calls)==position: raise error
                        return backend
                    url=Mock(return_value='url')
                    service=DetectionAnnotation(normalize_ai_box_2d,lambda:lambda *args:(1,2,30,40),lambda:lambda *args:'Label',images,lambda kind:self.output,url,lambda *args:image,Mock())
                    with self.assertRaises(BaseException) as caught:
                        if operation=='draw': service.draw_ai_detection_boxes(image,[{'box_2d':[],'label':'X'}],{})
                        else: service.write_ai_annotated_output(image,'id',[],{})
                    self.assertIs(caught.exception,error); self.assertEqual(len(calls),position); url.assert_not_called(); backend.imwrite.assert_not_called()

    def test_draw_mapping_errors_fail_once_without_retry(self):
        for owner,key in [('det','box_2d'),('rule','passed'),('det','label'),('det','accessory_id')]:
            with self.subTest(owner=owner,key=key):
                calls=[]; error=RuntimeError('draw mapping'); backend=self.backend(); self.api.cv2=backend
                class Values(dict):
                    def get(inner,name,default=None):
                        if name==key:
                            calls.append(name)
                            if len(calls)==1: raise error
                        return super().get(name,default)
                det={'box_2d':[0,0,1000,1000],'accessory_id':'a'}; rule={'passed':True}
                if owner=='det': det=Values(det)
                else: rule=Values(rule)
                with self.assertRaises(BaseException) as caught:
                    self.api.draw_ai_detection_boxes(np.zeros((120,200,3),dtype=np.uint8),[det],rule)
                self.assertIs(caught.exception,error); self.assertEqual(calls,[key]); backend.addWeighted.assert_not_called()

    def test_original_output_fallback_failure_is_not_retried(self):
        error=RuntimeError('original fallback'); calls=[]
        def original(*args):
            calls.append(args)
            if len(calls)==1: raise error
            return 'recovered'
        image=np.zeros((5,7,3),dtype=np.uint8)
        with patch.object(self.api,'draw_ai_detection_boxes',return_value=None),patch.object(self.api,'write_ai_original_output',side_effect=original),patch.object(self.api,'output_write_dir') as directory:
            with self.assertRaises(BaseException) as caught: self.api.write_ai_annotated_output(image,'id',[],{})
        self.assertIs(caught.exception,error); self.assertEqual(len(calls),1); self.assertIs(calls[0][0],image); self.assertEqual(calls[0][1],'id'); directory.assert_not_called()


    def test_backend_refresh_is_visible_to_every_next_box_operation(self):
        capture_annotation_backend_refresh(self.api.__dict__)


if __name__=='__main__': unittest.main()
