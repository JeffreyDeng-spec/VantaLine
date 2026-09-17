"""Synthetic OCR detection contracts; every prediction uses a local test double."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np


def result(kind='unknown', score=0, text='text', confidence=0.0, rotation=0):
    return {'texts':[text], 'mean_text_score':.9, 'rotation':rotation,
            'classification':{'manual_type':kind,'manual_label':kind,'confidence':confidence,'scores':{kind:score},'matches':[]}}


class OCRContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='detection-ocr-')
        root = Path(cls.temporary.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server
    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    def test_engine_factory_failure_retry_instance_scope_and_bootstrap(self):
        from local_inspection_service.runtime import paddle
        model=object();prepare=Mock(side_effect=[RuntimeError('prepare'),None,None])
        factory=Mock(side_effect=[RuntimeError('factory'),model]);engine=paddle.DetectionOCREngine(prepare,factory)
        for message in ('prepare','factory'):
            with self.assertRaisesRegex(RuntimeError,message):engine.get()
            self.assertIsNone(engine.instance)
        self.assertIs(engine.get(),model);self.assertIs(engine.get(),model)
        self.assertEqual(prepare.call_count,3);self.assertEqual(factory.call_count,2)
        self.assertIsNot(paddle.DetectionOCREngine(lambda:None,lambda:object()).get(),model)
        module=types.ModuleType('paddleocr');module.PaddleOCR=Mock(return_value=model)
        with patch.dict(sys.modules,{'paddleocr':module}):self.assertIs(paddle.create_detection_ocr(),model)
        module.PaddleOCR.assert_called_once_with(lang='en',text_detection_model_name='PP-OCRv6_small_det',
            text_recognition_model_name='PP-OCRv6_small_rec',use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=True)
        with patch.dict(paddle.os.environ,{'FLAGS_use_mkldnn':'existing'},clear=True),patch.object(paddle.Path,'exists',return_value=True), \
             patch.object(paddle.ctypes,'RTLD_GLOBAL',77,create=True),patch.object(paddle.ctypes,'CDLL',side_effect=OSError('library')) as load:
            paddle.prepare_runtime()
            self.assertEqual(paddle.os.environ['FLAGS_use_mkldnn'],'existing')
            self.assertEqual(paddle.os.environ['FLAGS_use_onednn'],'false');self.assertEqual(paddle.os.environ['FLAGS_enable_pir_api'],'0')
            self.assertEqual(load.call_args.kwargs,{'mode':77});self.assertTrue(load.call_args.args[0].replace('\\','/').endswith('/torch/lib/libgomp.so.1'))
            load.side_effect=ValueError('invalid loader')
            with self.assertRaisesRegex(ValueError,'invalid loader'):paddle.prepare_runtime()

    def test_root_composition_aliases_and_late_shared_bootstrap(self):
        from local_inspection_service.runtime import paddle
        from local_inspection_service.detection import ocr_images,ocr_matching,ocr_scoring
        api=self.api
        self.assertIs(api.prepare_paddle_runtime,paddle.prepare_runtime)
        self.assertIs(api.normalize_ocr_text,ocr_matching.normalize_ocr_text)
        self.assertIs(api.crop_detection_region,ocr_images.crop_detection_region)
        self.assertIs(api.better_ocr_result,ocr_scoring.better_ocr_result)
        self.assertIs(api.attach_ocr_results.__self__,api._ocr_attachment)
        self.assertIs(api.score_ocr_variants.__self__,api._ocr_scoring)
        with patch.object(api,'prepare_paddle_runtime') as prepare:
            api._detection_ocr_engine.prepare();api._incoming_ocr_engine.prepare_runtime()
        self.assertEqual(prepare.call_count,2)

    def test_batch_build_failure_replays_single_images_and_preserves_order(self):
        from local_inspection_service.detection.ocr_scoring import OCRScoring
        image=np.full((2,3,3),(10,20,30),np.uint8);events=[];model=Mock()
        model.predict.side_effect=[
            [{'rec_texts':['discarded'],'rec_scores':[1]},{'rec_texts':['bad'],'rec_scores':['invalid']}],
            [{'rec_texts':['single one'],'rec_scores':[.8]}],[{'rec_texts':['single two'],'rec_scores':[.9]}]]
        def engine():events.append('engine');return model
        actual_color=cv2.cvtColor
        def color(*args):events.append('color');return actual_color(*args)
        scoring=OCRScoring(engine,lambda texts:{'manual_type':'unknown'})
        with patch.object(cv2,'cvtColor',side_effect=color):values=scoring.variants([image,image],[0,180])
        self.assertEqual(events,['color','color','engine','engine','color','engine','color'])
        self.assertEqual([value['texts'] for value in values],[['single one'],['single two']])
        model.predict.assert_called();self.assertEqual(model.predict.call_count,3)
        model.predict.reset_mock();model.predict.side_effect=[RuntimeError('batch'),[{'rec_scores':['still bad']}]]
        with self.assertRaises(ValueError):scoring.variants([image,image],[0,180])
        self.assertEqual(model.predict.call_count,2)

    def test_normalization_keywords_profiles_and_original_aliases(self):
        api=self.api
        self.assertEqual(api.normalize_ocr_text(' ÄÖÜ ß ÉÈÊ ÁÀÍÓÇĞ ABC 中文 0/O '), 'aou ss eee aaiocg abc 0/o')
        with patch.object(api,'OCR_ACCESSORY_PROFILE_STOPWORDS',{'manual'}):
            terms=api.ocr_keyword_terms({'one':['manual','foo manual'], 'two':'foo'},weight=2)
            self.assertEqual(terms,[{'text':'foo manual','weight':2},{'text':'foo','weight':2},{'text':'foo','weight':2},{'text':'foo','weight':2}])
            item={'name':'foo','ai_profile':{'distinguishing_text':['foo'],'tags':['foo','zulu']}}
            with patch.object(api,'accessory_uid',return_value='generated'):
                profiles=api.build_ocr_accessory_profiles([{},item],{})
            self.assertEqual(profiles['generated']['keywords'],[{'text':'foo','weight':3.0},{'text':'zulu','weight':1.0}])
            self.assertEqual(profiles['generated']['label'],'foo');self.assertNotIn('id',item)

    def test_matching_threshold_rounding_ties_and_reason_priority(self):
        api=self.api
        spec={'ocr_accessory_profiles':{'one':{'label':'One','keywords':[{'text':'alpha','weight':3.6}]},
                                        'two':{'label':'Two','keywords':[{'text':'alpha','weight':2.7}]}}}
        accepted=api.match_ocr_text_accessory(['ALPHA'],.65,spec)
        self.assertTrue(accepted['accepted']);self.assertEqual(accepted['margin'],.15);self.assertEqual(accepted['confidence'],.6)
        self.assertEqual(api.match_ocr_text_accessory(['ALPHA'],.64999,spec)['reason'],'low_text_score')
        spec['ocr_accessory_profiles']['two']['keywords'][0]['weight']=3.6
        tied=api.match_ocr_text_accessory(['alpha'],1,spec)
        self.assertFalse(tied['accepted']);self.assertEqual(tied['reason'],'low_match_margin');self.assertEqual(tied['accessory_id'],'one')
        with patch.object(api,'OCR_ACCESSORY_MATCH_MIN_MARGIN',0):self.assertTrue(api.match_ocr_text_accessory(['alpha'],1,spec)['accepted'])
        self.assertEqual(api.match_ocr_text_accessory([],1,spec)['reason'],'no_ocr_text_or_profiles')
        self.assertEqual(api.match_ocr_text_accessory(['unrelated'],1,spec)['reason'],'low_match_confidence')

    def test_manual_classification_weight_gap_and_empty_policy(self):
        api=self.api
        with patch.object(api,'MANUAL_TYPE_KEYWORDS',{'alpha':[('foo',6)],'beta':[('foo',4)]}),patch.object(api,'MANUAL_TYPE_LABELS',{'alpha':'Alpha'}):
            value=api.classify_manual_text(['FOO']);self.assertEqual(value['manual_type'],'alpha');self.assertEqual(value['confidence'],.6);self.assertEqual(value['manual_label'],'Alpha')
            api.MANUAL_TYPE_KEYWORDS['beta']=[('foo',5)]
            self.assertEqual(api.classify_manual_text(['foo'])['manual_type'],'unknown')
            self.assertEqual(api.classify_manual_text(['bar'])['matches'],[])
        with patch.object(api,'MANUAL_TYPE_KEYWORDS',{}):
            with self.assertRaises(ValueError):api.classify_manual_text(['foo'])

    def test_crop_rotation_resize_and_original_image(self):
        api=self.api;image=np.arange(6*10*3,dtype=np.uint8).reshape(6,10,3);original=image.copy()
        self.assertIs(api.rotate_quarter_turn(image,360),image)
        np.testing.assert_array_equal(api.rotate_quarter_turn(image,-90),cv2.rotate(image,cv2.ROTATE_90_COUNTERCLOCKWISE))
        with self.assertRaises(ValueError):api.rotate_quarter_turn(image,45)
        self.assertIs(api.resize_for_ocr(image,0),image);self.assertIs(api.resize_for_ocr(image,10),image)
        self.assertEqual(api.resize_for_ocr(image,5).shape,(3,5,3))
        self.assertIsNone(api.crop_detection_region(image,[[0,0],[1,1]]))
        self.assertIsNone(api.crop_detection_region(image,[[100,100],[110,100],[100,110]]))
        # Explicit rectangular evidence with asymmetric BGR values: the padded
        # top/left border is white, and the original long-edge rule turns it 270°.
        masked=np.full((5,9,3),255,np.uint8);masked[1:5,1:9]=image[1:5,1:9]
        expected=np.rot90(masked,k=1)
        unscaled,details=api.crop_detection_region(image,[[1,1],[8,1],[8,4],[1,4]],padding=1,max_long_side=0)
        np.testing.assert_array_equal(unscaled,expected)
        self.assertEqual(details,{'long_edge_angle':180.0,'predicted_rotation':270,'fallback_rotations':[90]})
        crop,orientation=api.crop_detection_region(image,[[1,1],[8,1],[8,4],[1,4]],padding=1,max_long_side=5)
        np.testing.assert_array_equal(crop,cv2.resize(expected,(3,5),interpolation=cv2.INTER_AREA))
        self.assertLessEqual(max(crop.shape[:2]),5);self.assertIn(orientation['predicted_rotation'],(0,90,180,270))
        self.assertEqual(orientation['fallback_rotations'],[(orientation['predicted_rotation']+180)%360]);np.testing.assert_array_equal(image,original)

    def test_scoring_rgb_batch_fallback_zip_and_exception_boundaries(self):
        api=self.api;image=np.full((3,4,3),(10,20,30),np.uint8);model=Mock()
        model.predict.return_value=[{'rec_texts':['',' a ',None],'rec_scores':[.2,.8]}]
        with patch.object(api,'ocr_engine',return_value=model):
            value=api.score_ocr_variant(image,-90)
        self.assertEqual(value['texts'],[' a ','None']);self.assertEqual(value['mean_text_score'],.5);self.assertEqual(value['rotation'],270)
        self.assertEqual(model.predict.call_args.args[0][0,0].tolist(),[30,20,10])
        model.predict.side_effect=[RuntimeError('batch'),[{'rec_texts':['one'],'rec_scores':[1]}],[{'rec_texts':['two'],'rec_scores':[.5]}]]
        model.predict.reset_mock()
        with patch.object(api,'ocr_engine',return_value=model):values=api.score_ocr_variants([image,image],[0,180])
        self.assertEqual([r['texts'] for r in values],[['one'],['two']]);self.assertEqual(model.predict.call_count,3)
        model.predict.side_effect=None;model.predict.return_value=[{'rec_texts':['one']}]
        with patch.object(api,'ocr_engine',return_value=model):self.assertEqual(len(api.score_ocr_variants([image,image],[0,180])),1)
        model.predict.return_value=[];model.predict.reset_mock()
        with patch.object(api,'ocr_engine',return_value=model):self.assertEqual(api.score_ocr_variants([image],[0]),[])
        self.assertEqual(model.predict.call_count,1)
        model.predict.return_value=[{'rec_texts':['text'],'rec_scores':['invalid']}]
        with patch.object(api,'ocr_engine',return_value=model):
            with self.assertRaises(ValueError):api.score_ocr_variant(image,0)
        model.predict.side_effect=RuntimeError('local inference failed')
        with patch.object(api,'ocr_engine',return_value=model):self.assertEqual(api.score_ocr_variant(image,0)['texts'],[])
        with patch.object(api,'ocr_engine',side_effect=AssertionError('must not initialize')):
            self.assertEqual(api.score_ocr_variants([],[]),[])

    def test_crop_fallback_updates_winner_alias_and_rotates_original(self):
        api=self.api;image=np.arange(3*4*3,dtype=np.uint8).reshape(3,4,3);orientation={'predicted_rotation':0,'fallback_rotations':[180,0]}
        model=Mock()
        # Each single prediction returns a one-result collection.
        model.predict.side_effect=[[{'rec_texts':['foo'],'rec_scores':[.9]}],[{'rec_texts':['none'],'rec_scores':[.1]}],[{'rec_texts':['none'],'rec_scores':[.1]}]]
        with patch.object(api,'MANUAL_TYPE_KEYWORDS',{'alpha':[('foo',6)],'beta':[]}),patch.object(api,'ocr_engine',return_value=model):
            best=api.run_ocr_on_crop(image,orientation,2)
        self.assertEqual(best['texts'],['foo']);self.assertTrue(best['fallback_used']);self.assertIs(best['orientation'],orientation)
        self.assertEqual(model.predict.call_count,3)
        expected=cv2.cvtColor(cv2.rotate(image,cv2.ROTATE_180),cv2.COLOR_BGR2RGB)
        np.testing.assert_array_equal(model.predict.call_args_list[1].args[0],expected);np.testing.assert_array_equal(model.predict.call_args_list[2].args[0],expected)
        current=result('alpha',6);candidate=copy.deepcopy(current)
        self.assertIs(api.better_ocr_result(current,candidate),current)
        candidate['texts'].append('more');self.assertIs(api.better_ocr_result(current,candidate),candidate)

    def test_attachment_batch_losing_fallback_and_partial_zip(self):
        api=self.api;image=np.zeros((20,30,3),np.uint8);orientation={'predicted_rotation':0,'long_edge_angle':0,'fallback_rotations':[180]}
        detections=[{'class_id':1,'model_class_id':1,'polygon':[[0,0],[1,0],[1,1]]} for _ in range(2)]
        first=result('unknown',6,text='first');fallback=result('unknown',0,text='second',rotation=180)
        with patch.object(api,'crop_detection_region',return_value=(image,orientation)),patch.object(api,'score_ocr_variants',side_effect=[[first],[fallback]]) as score:
            returned=api.attach_ocr_results(image,detections,{},None)
        self.assertIs(returned,detections);self.assertEqual(score.call_count,2)
        self.assertFalse(detections[0]['ocr']['fallback_used']);self.assertNotIn('ocr',detections[1])
        self.assertTrue(fallback['fallback_used']);self.assertEqual(detections[0]['class_id'],99)
        with patch.object(api,'crop_detection_region',side_effect=AssertionError('disabled OCR')):
            self.assertIs(api.attach_ocr_results(image,detections,{'ocr':{'enabled':False}}),detections)
            self.assertIs(api.attach_ocr_results(image,detections,{}, {'is_specialized':True,'ocr_model_class_ids':[]}),detections)

    def test_attachment_specialized_resolution_and_missing_crop(self):
        api=self.api;image=np.zeros((20,30,3),np.uint8);orientation={'predicted_rotation':0,'long_edge_angle':0,'fallback_rotations':[180]}
        spec={'is_specialized':True,'ocr_model_class_ids':[4], 'ocr_accessory_profiles':{'resolved':{'label':'Resolved','keywords':[{'text':'alpha','weight':6}]}}}
        original={'class_id':4,'model_class_id':4,'accessory_id':'yolo','polygon':[[0,0],[1,0],[1,1]]}
        for text,source in [('alpha','ocr'),('none','yolo_fallback_low_match_confidence')]:
            det=copy.deepcopy(original);ocr=result('manual',6,text=text,confidence=1)
            with patch.object(api,'crop_detection_region',return_value=(image,orientation)),patch.object(api,'score_ocr_variants',return_value=[ocr]):
                value=api.attach_ocr_results(image,[det],{},spec)
            self.assertIs(value[0],det);self.assertEqual(det['class_id'],4);self.assertEqual(det['resolution_source'],source)
            self.assertEqual(det['yolo_accessory_id'],'yolo');self.assertEqual(det['resolved_accessory_id'],'resolved' if source=='ocr' else 'yolo')
        det=copy.deepcopy(original)
        with patch.object(api,'crop_detection_region',return_value=None),patch.object(api,'score_ocr_variants') as score:
            api.attach_ocr_results(image,[det],{},spec)
        score.assert_not_called();self.assertEqual(det['class_id'],4);self.assertEqual(det['ocr']['texts'],[])

    def test_final_projection_retains_original_mutation_and_unknown_error(self):
        api=self.api;orientation={'predicted_rotation':90,'long_edge_angle':12};det={'class_id':1,'manual_type':'old','manual_label':'Old'}
        api.finalize_ocr_detection(det,result(),orientation,0)
        self.assertEqual(det['class_id'],99);self.assertEqual(det['manual_type'],'old');self.assertEqual(det['ocr']['texts'],[])
        with patch.object(api,'MANUAL_TYPE_CLASS_IDS',{'known':7}),patch.object(api,'CLASS_NAMES',{7:'name'}),patch.object(api,'CLASS_LABELS',{7:'Label'}):
            api.finalize_ocr_detection(det,result('known',6),orientation,16)
        self.assertEqual(det['class_id'],7);self.assertEqual(det['class_name'],'name');self.assertEqual(det['manual_type'],'known')
        with self.assertRaises(KeyError):api.finalize_ocr_detection(det,result('not-configured',6),orientation,16)


if __name__ == '__main__': unittest.main()
