"""Synthetic detection-result contracts; no model execution or device I/O."""
import copy
from dataclasses import replace
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np


class Tensor:
    def __init__(self, values): self.values = np.asarray(values)
    def cpu(self): return self
    def numpy(self): return self.values


class Boxes:
    def __init__(self, classes=(0,), confidence=(.89123,), xyxy=((10.111, 20.222, 80.333, 90.444),)):
        self.cls, self.conf, self.xyxy = Tensor(classes), Tensor(confidence), Tensor(xyxy)
    def __len__(self): return len(self.cls.values)


def detection(cls=0, confidence=.9, box=(0, 0, 100, 100), **extra):
    x1, y1, x2, y2 = box
    return {'class_id': cls, 'confidence': confidence, 'polygon': [[x1,y1],[x2,y1],[x2,y2],[x1,y2]], 'label': 'part', **extra}


def specialized():
    return {'is_specialized': True, 'model_to_business_class': {0: 8}, 'model_class_names': {0: 'model-nut'},
            'model_to_accessory_id': {'0': 'acc-nut'}, 'rule_class_labels': {8: 'Nut'}, 'confidence_threshold': .01}


class DetectionContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='detection-contracts-')
        root = Path(cls.temporary.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server
    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    def test_root_aliases_and_independent_label_instances(self):
        from local_inspection_service.detection import geometry, postprocessing, drawing
        from local_inspection_service.detection.results import DetectionLabels, DetectionResults
        from local_inspection_service.detection.rules import CountRules
        api = self.api
        for module, names in ((geometry, ('polygon_overlap_ratio','polygon_area','polygon_bbox','bbox_gap','bbox_overlap_ratio')),
                              (postprocessing, ('filter_detections','dedupe_detections','postprocess_detections')),
                              (drawing, ('draw_detections',))):
            for name in names: self.assertIs(getattr(api, name), getattr(module, name))
        self.assertIs(api.parse_detections.__self__, api._detection_results)
        self.assertIs(api.apply_rule.__self__, api._detection_rules)
        one = DetectionResults(DetectionLabels(lambda:{0:'one'}, lambda:{0:'One'}, lambda:{}, lambda:{}), lambda values,shape,spec:values)
        two = DetectionResults(DetectionLabels(lambda:{0:'two'}, lambda:{0:'Two'}, lambda:{}, lambda:{}), lambda values,shape,spec:values)
        self.assertEqual(one.names(0,{}), ('one','One')); self.assertEqual(two.names(0,{}), ('two','Two'))
        never = Mock(side_effect=AssertionError('unselected labels read'))
        selected = DetectionResults(DetectionLabels(never, never, never, never), lambda values,shape,spec:values)
        self.assertEqual(selected.names(8, specialized()), ('Nut','Nut')); never.assert_not_called()
        manual = Mock(return_value={'manual':'Manual'})
        policy = CountRules(lambda:{0:'One'}, manual)
        policy.apply([], {'confidence_threshold':.5, 'required_classes':[], 'min_counts':{}, 'ocr':{'enabled':False,'manual_types':[]}}, {})
        # dict.get evaluates its default keys expression even when manual_types is supplied.
        manual.assert_called_once()

    def test_dedupe_exact_overlap_area_and_absorption_boundaries(self):
        api=self.api
        for x,expected in [(87,1),(88,2)]:
            large=detection(cls=2,confidence=.9);small=detection(cls=2,confidence=.8,box=(x,0,x+20,10))
            self.assertEqual(len(api.dedupe_detections([large,small])),expected)
        large=detection(cls=1,confidence=.54,box=(0,0,500,500));adjacent=detection(cls=1,confidence=.53,box=(542,0,1042,500))
        self.assertEqual(api.dedupe_detections([large,adjacent]),[large,adjacent])
        for width,expected in [(22,1),(23,2)]:
            large=detection(cls=1,confidence=.9);fragment=detection(cls=1,confidence=.8,box=(100,0,100+width,100))
            self.assertEqual(len(api.dedupe_detections([large,fragment])),expected)

    def test_complete_parser_records_and_short_obb_preprocessing(self):
        api=self.api;spec=specialized()
        expected={'class_id':8,'accessory_id':'acc-nut','yolo_accessory_id':'acc-nut','resolved_accessory_id':'acc-nut',
                  'resolution_source':'yolo','class_name':'Nut','label':'Nut','model_class_id':0,'model_class_name':'model-nut',
                  'confidence':.8912,'polygon':[[10.11,20.22],[80.33,20.22],[80.33,90.44],[10.11,90.44]]}
        result=types.SimpleNamespace(orig_shape=(1000,1000,3),boxes=Boxes(),masks=None,obb=None)
        with patch.object(api,'postprocess_detections',side_effect=lambda values,shape,selected:values) as post:
            self.assertEqual(api.parse_detections(result,spec),[expected]);post.assert_called_once()
            self.assertIs(post.call_args.args[2],spec)
        class OBB:
            xyxyxyxy=Tensor([[[10.111,20.222],[80.333,90.444]]]);cls=Tensor([0]);conf=Tensor([.89123])
            def __len__(self):return 1
        result.boxes=None;result.obb=OBB()
        with patch.object(api,'postprocess_detections',side_effect=lambda values,shape,selected:values) as post:
            self.assertEqual(api.parse_detections(result,spec),[{**expected,'polygon':[[10.11,20.22],[80.33,90.44]]}]);post.assert_called_once()
        result.boxes=Boxes();result.masks=types.SimpleNamespace(xy=[np.array([[10,20],[80,90]])])
        with patch.object(api,'postprocess_detections',side_effect=lambda values,shape,selected:values) as post:
            self.assertEqual(api.parse_detections(result,spec),[]);self.assertEqual(post.call_args.args[0],[])

    def test_normal_drawing_fill_edge_text_and_blend(self):
        import cv2
        image=np.zeros((300,400,3),np.uint8);det=detection(box=(70,100,230,230),manual_label='Manual')
        with patch.object(cv2,'fillPoly',wraps=cv2.fillPoly) as fill,patch.object(cv2,'polylines',wraps=cv2.polylines) as edge,patch.object(cv2,'putText',wraps=cv2.putText) as text,patch.object(cv2,'addWeighted',wraps=cv2.addWeighted) as blend:
            rendered=self.api.draw_detections(image,[det],{'passed':True})
        fill.assert_called_once();edge.assert_called_once();blend.assert_called_once();self.assertEqual(text.call_count,2)
        self.assertEqual(text.call_args_list[0].args[1],'Manual 0.90');self.assertEqual(text.call_args_list[1].args[1],'TRUE: exact parts match')
        self.assertEqual(blend.call_args.args[1],.16);self.assertEqual(blend.call_args.args[3:],(.84,0))
        self.assertEqual(edge.call_args.kwargs,{'isClosed':True,'color':(38,82,255),'thickness':3,'lineType':cv2.LINE_AA})
        self.assertEqual(rendered[150,150].tolist(),[6,13,41]);self.assertEqual(rendered[150,70].tolist(),[38,82,255])
        self.assertEqual(rendered[200,250].tolist(),[0,0,0]);self.assertFalse(image.any())

    def test_new_label_provider_failures_are_not_retried(self):
        # New dependency-factory behavior is checked separately from old mapping operations.
        from local_inspection_service.detection.results import DetectionLabels,DetectionResults
        from local_inspection_service.detection.rules import CountRules
        for boundary in ['class_names','class_labels','generic_names','generic_labels','rule_class_labels','manual_labels']:
            with self.subTest(boundary=boundary):
                error=RuntimeError(boundary)
                success={'manual':'Manual'} if boundary=='manual_labels' else {0:'Zero',1:'Manual'}
                target=Mock(side_effect=[error,success])
                if boundary.startswith('rule_') or boundary=='manual_labels':
                    policy=CountRules(target if boundary.startswith('rule_') else lambda:{0:'Zero'},target if boundary=='manual_labels' else lambda:{'manual':'Manual'})
                    invoke=lambda:policy.apply([],{'confidence_threshold':.5,'required_classes':[],'min_counts':{},'ocr':{'enabled':False}}, {})
                else:
                    labels=DetectionLabels(lambda:{0:'Zero'},lambda:{0:'Zero'},lambda:{1:'Manual'},lambda:{1:'Manual'})
                    service=DetectionResults(replace(labels,**{boundary:target}),lambda values,shape,spec:values)
                    invoke=lambda:service.names(1 if boundary.startswith('generic') else 0,{'uses_ocr':boundary.startswith('generic')})
                with self.assertRaises(RuntimeError) as caught:invoke()
                self.assertIs(caught.exception,error);target.assert_called_once()

    def test_original_mapping_and_postprocess_first_errors_are_not_retried(self):
        api=self.api
        for boundary in ['class_get','label_get','rule_items','manual_keys','post_boxes','post_obb']:
            with self.subTest(boundary=boundary):
                error=RuntimeError(boundary);calls=[]
                def first_error():
                    calls.append(1)
                    if len(calls)==1:raise error
                class Mapping(dict):
                    def get(self,*args):first_error();return super().get(*args)
                    def items(self):first_error();return super().items()
                    def keys(self):first_error();return super().keys()
                with ExitStack() as stack:
                    if boundary in ('class_get','label_get'):
                        stack.enter_context(patch.object(api,'CLASS_NAMES' if boundary=='class_get' else 'CLASS_LABELS',Mapping({0:'Zero'})))
                        invoke=lambda:api.detection_names_for_business_class(0,{})
                    elif boundary in ('rule_items','manual_keys'):
                        stack.enter_context(patch.object(api,'CLASS_LABELS' if boundary=='rule_items' else 'MANUAL_TYPE_LABELS',Mapping({0:'Zero'} if boundary=='rule_items' else {'manual':'Manual'})))
                        invoke=lambda:api.apply_rule([],{'confidence_threshold':.5,'required_classes':[],'min_counts':{},'ocr':{'enabled':False}}, {})
                    else:
                        result=types.SimpleNamespace(orig_shape=(1000,1000),boxes=Boxes(),masks=None,obb=None)
                        if boundary=='post_obb':
                            class OBB:
                                xyxyxyxy=Tensor([[[0,0],[100,0],[100,100],[0,100]]]);cls=Tensor([0]);conf=Tensor([.9])
                                def __len__(self):return 1
                            result.boxes=None;result.obb=OBB()
                        def post(values,shape,spec):first_error();return values
                        stack.enter_context(patch.object(api,'postprocess_detections',post));invoke=lambda:api.parse_detections(result,specialized())
                    with self.assertRaises(RuntimeError) as caught:invoke()
                    self.assertIs(caught.exception,error);self.assertEqual(calls,[1])

    def test_geometry_degenerate_overlap_and_distance(self):
        a = detection(box=(0,0,10,10))['polygon']; contained = detection(box=(2,2,8,8))['polygon']
        self.assertEqual(self.api.polygon_area(a), 100)
        self.assertEqual(self.api.polygon_area(list(reversed(a))), 100)
        self.assertEqual(self.api.polygon_overlap_ratio(a, contained), 1)
        self.assertEqual(self.api.polygon_overlap_ratio(a, [[0,0],[0,0],[0,0]]), 0)
        self.assertEqual(self.api.polygon_bbox(contained), (2.,2.,8.,8.))
        self.assertEqual(self.api.bbox_gap((0,0,1,1), (4,5,8,9)), 5)
        self.assertEqual(self.api.bbox_overlap_ratio((0,0,10,10), (2,2,8,8)), 1)
        self.assertEqual(self.api.bbox_overlap_ratio((0,0,0,0), (2,2,8,8)), 0)
        with self.assertRaises((IndexError, ValueError)): self.api.polygon_bbox([])

    def test_filter_thresholds_mutation_and_specialized_fallback(self):
        api = self.api
        accepted = detection(confidence=.85, box=(0,0,15,100)); rejected = detection(confidence=.8499, box=(0,0,15,100))
        result = api.filter_detections([accepted, rejected], (1000,1000))
        self.assertEqual(result, [accepted]); self.assertIs(result[0], accepted)
        self.assertEqual(rejected['area_px'], 1500.0)
        manual = detection(cls=1, confidence=.30, box=(0,0,60,100))
        self.assertEqual(api.filter_detections([manual], (1000,1000)), [manual])
        self.assertEqual(api.filter_detections([detection(cls=1, confidence=.2999, box=(0,0,60,100))], (1000,1000)), [])
        at = detection(confidence=.25, box=(0,0,10,50)); below = detection(confidence=.25, box=(0,0,10,49.9))
        self.assertEqual(api.filter_detections([at,below], (1000,1000), {'is_specialized': True, 'confidence_threshold':'invalid'}), [at])
        self.assertEqual(api.filter_detections([detection(confidence=.001)], (1000,1000), {'is_specialized': True, 'confidence_threshold': -10})[0]['confidence'], .001)
        self.assertEqual(api.filter_detections([detection(confidence=.9899)], (1000,1000), {'is_specialized': True, 'confidence_threshold': 5}), [])

    def test_dedupe_stable_order_class_separation_and_manual_boundaries(self):
        api = self.api
        first = detection(confidence=.9); same = detection(confidence=.9); other_class = detection(cls=2, confidence=.9)
        result = api.dedupe_detections([first, same, other_class])
        self.assertEqual(result, [first,other_class]); self.assertIs(result[0], first)
        manual = detection(cls=1, confidence=.54)
        adjacent = detection(cls=1, confidence=.54, box=(142,0,242,100))
        self.assertEqual(api.dedupe_detections([manual, adjacent]), [manual])
        adjacent['polygon'] = detection(box=(142.01,0,242.01,100))['polygon']
        self.assertEqual(len(api.dedupe_detections([manual, adjacent])), 2)
        manual['confidence'] = .55; adjacent['polygon'] = detection(box=(142,0,242,100))['polygon']
        self.assertEqual(len(api.dedupe_detections([manual, adjacent])), 2)
        large = detection(cls=1, confidence=.9, box=(0,0,100,100)); fragment = detection(cls=1, confidence=.8, box=(100,0,110,20))
        self.assertEqual(api.dedupe_detections([large,fragment]), [large])
        touching = detection(confidence=.8, box=(15,0,115,100))
        self.assertEqual(api.dedupe_detections([first,touching]), [first])
        touching['polygon'] = detection(box=(15.1,0,115.1,100))['polygon']
        self.assertEqual(len(api.dedupe_detections([first,touching])), 2)

    def test_parser_box_mask_obb_precedence_and_rounding(self):
        api = self.api; spec = specialized()
        result = types.SimpleNamespace(orig_shape=(1000,1000,3), boxes=Boxes(), masks=None, obb=None)
        records = api.parse_detections(result, spec)
        self.assertEqual(len(records), 1); record = records[0]
        self.assertEqual(record['polygon'][0], [10.11,20.22]); self.assertEqual(record['confidence'], .8912)
        self.assertEqual(record['model_class_name'], 'model-nut'); self.assertEqual(record['class_id'], 8)
        self.assertEqual(record['accessory_id'], 'acc-nut'); self.assertEqual(record['resolved_accessory_id'], 'acc-nut')
        self.assertEqual(record['class_name'], 'Nut'); self.assertEqual(record['resolution_source'], 'yolo')
        result.masks = types.SimpleNamespace(xy=[np.array([[10,10],[100,10],[100,100]])])
        self.assertEqual(len(api.parse_detections(result, spec)[0]['polygon']), 3)
        result.masks = types.SimpleNamespace(xy=[])
        class OBB:
            xyxyxyxy = Tensor([[[10,10],[100,10],[100,100],[10,100]]])
            cls = Tensor([0]); conf = Tensor([.95123])
            def __len__(self): return 1
        result.obb = OBB()
        self.assertEqual(api.parse_detections(result, spec), [])
        result.boxes = None
        self.assertEqual(api.parse_detections(result, spec)[0]['confidence'], .9512)
        spec['model_to_business_class'] = {}; self.assertEqual(api.parse_detections(result, spec), [])
        result.obb = None; self.assertEqual(api.parse_detections(result, spec), [])

    def test_parser_callback_identity_zip_and_round_before_filter(self):
        api = self.api; spec = specialized(); marker = object()
        result = types.SimpleNamespace(orig_shape=(1000,1000,3), boxes=Boxes(classes=(0,0), confidence=(.24996,.9)),
                                       masks=types.SimpleNamespace(xy=[np.array([[0.004,0.004],[10.004,0.004],[10.004,50.004],[0.004,50.004]])]), obb=None)
        spec['confidence_threshold'] = .25
        with patch.object(api, 'postprocess_detections', return_value=marker) as callback:
            self.assertIs(api.parse_detections(result, spec), marker)
            callback.assert_called_once()
            items, shape, selected = callback.call_args.args
            self.assertEqual(shape, (1000,1000)); self.assertIs(selected, spec)
            self.assertEqual(len(items), 1); self.assertEqual(items[0]['confidence'], .25)
            self.assertEqual(items[0]['polygon'][0], [0.,0.])
        self.assertEqual(len(api.parse_detections(result, spec)), 1)
        class Overflow:
            def __float__(self): raise OverflowError('conversion')
        with self.assertRaises(OverflowError): api.filter_detections([], (100,100), {'confidence_threshold':Overflow()})
        with patch.object(api, 'postprocess_detections') as callback:
            result.boxes = None
            self.assertEqual(api.parse_detections(result, spec), [])
            callback.assert_not_called()

    def test_rule_exact_counts_resolved_accessory_and_legacy_error(self):
        api = self.api; config = {'confidence_threshold': .5, 'required_classes':[0], 'min_counts': {'0':1}, 'ocr':{'enabled':False}}
        one = detection(confidence=.5)
        self.assertTrue(api.apply_rule([one], config, {})['passed'])
        duplicate = api.apply_rule([one, one], config, {})
        self.assertFalse(duplicate['passed']); self.assertEqual(duplicate['extra'][0]['issue'], 'extra')
        self.assertIs(duplicate['missing'][0], duplicate['extra'][0])
        spec = {'is_specialized':True, 'required_accessory_counts': {'selected':1}, 'accessory_labels': {'selected':'Chosen'}}
        item = detection(accessory_id='wrong', resolved_accessory_id='selected')
        value = api.apply_rule([item], config, spec)
        self.assertTrue(value['passed']); self.assertEqual(value['counts'], {'Chosen':1}); self.assertEqual(value['source'], 'task')
        spec['required_accessory_counts'] = {'selected':0}
        self.assertTrue(api.apply_rule([detection(accessory_id='unrequested')], config, spec)['passed'])
        with self.assertRaises(KeyError): api.apply_rule([], {}, {'confidence_threshold':.5})
        with self.assertRaises(ValueError): api.apply_rule([], {**config,'confidence_threshold':'bad'}, {})

    def test_manual_counts_and_label_providers_remain_dynamic(self):
        api = self.api
        config = {'confidence_threshold':.8, 'required_classes':[], 'min_counts':{},
                  'ocr': {'enabled':True, 'require_manual_types':True, 'manual_types':['manual']}}
        with patch.object(api,'CLASS_LABELS',{0:'changed'}), patch.object(api,'CLASS_NAMES',{0:'class-changed'}), \
             patch.object(api,'MANUAL_TYPE_LABELS',{'manual':'Manual changed'}), \
             patch.object(api,'GENERIC_DETECTION_CLASS_NAMES',{1:'generic'}), patch.object(api,'GENERIC_DETECTION_LABELS',{1:'Generic label'}):
            self.assertEqual(api.detection_names_for_business_class(0,{}), ('class-changed','changed'))
            self.assertEqual(api.detection_names_for_business_class(1,{'uses_ocr':True}), ('generic','Generic label'))
            # Manual disposition counting predates the confidence filter and uses_ocr flag.
            value = api.apply_rule([detection(cls=1, confidence=.1, manual_type='manual')], config, {})
            self.assertTrue(value['passed']); self.assertFalse(value['ocr_enabled'])
            self.assertEqual(value['manual_type_counts'], {'Manual changed':1})
            self.assertEqual(value['manual_type_present'][0]['label'], 'Manual changed')
            value = api.apply_rule([detection(cls=1, manual_type='manual'), detection(cls=1, ocr={'manual_type':'manual'})], config, {})
            self.assertFalse(value['passed']); self.assertEqual(value['manual_type_missing'][0]['issue'], 'extra')

    def test_drawing_does_not_mutate_input_and_preserves_banner(self):
        api = self.api; image = np.zeros((100,160,3),np.uint8); original = image.copy()
        passed = api.draw_detections(image, [], {'passed':True})
        failed = api.draw_detections(image, [], {'passed':False})
        np.testing.assert_array_equal(image, original)
        self.assertIsNot(passed, image); self.assertEqual(passed[1,1].tolist(), [42,150,75]); self.assertEqual(failed[1,1].tolist(), [48,60,220])
        missing_label = detection(manual_label='manual'); missing_label.pop('label')
        with self.assertRaises(KeyError) as caught: api.draw_detections(image, [missing_label], {'passed':True})
        self.assertEqual(caught.exception.args, ('label',))


if __name__ == '__main__': unittest.main()
