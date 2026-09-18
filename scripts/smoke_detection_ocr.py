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

    def _attachment_capture_trace(self, mode, missing=False, prior=False):
        api=self.api;events=[];image=np.zeros((5,7,3),np.uint8)
        key={'crop':'crop_detection_region','default':'score_ocr_variants','fallback':'score_ocr_variants','match':'match_ocr_text_accessory'}[mode]
        count=[0]
        def first(*args,**kwargs):
            events.append('B' if prior else 'A');count[0]+=1
            if mode=='crop':return None
            if mode in ('default','fallback'):
                if mode=='default' or count[0]>1:return []
                if missing:setattr(api,key,None)
                return [result('unknown',6)]
            return {'accepted':False,'reason':'fixture'}
        def replacement(*args,**kwargs):
            events.append('C' if prior else 'B')
            return None if mode=='crop' else ([] if mode in ('default','fallback') else {'accepted':False,'reason':'fixture'})
        def swap():events.append('arg');setattr(api,key,replacement)
        class Integer:
            def __int__(self):swap();return 0
        class Floating:
            def __float__(self):swap();return .9
        class Detection(dict):
            def __getitem__(self,name):
                if mode=='crop' and name=='polygon':swap()
                return super().__getitem__(name)
        orientation={'predicted_rotation':Integer() if mode=='default' else 0,
                     'fallback_rotations':[Integer() if mode=='fallback' else 180],'long_edge_angle':0}
        value=result('known',6,confidence=1)
        if mode=='match':value['mean_text_score']=Floating()
        callbacks={'crop_detection_region':lambda *a,**k:(image,orientation),
                   'score_ocr_variants':lambda *a:[value],
                   'match_ocr_text_accessory':lambda *a:{'accepted':False,'reason':'fixture'},
                   'finalize_ocr_detection':lambda *a:None}
        callbacks[key]=None if missing and mode!='fallback' else first
        def advance():events.append('prior');setattr(api,key,first)
        class ClassId:
            def __int__(self):advance();return 1
        if prior:
            callbacks[key]=Mock(side_effect=AssertionError('callback captured before preceding work'))
            if mode=='default':
                def crop(*args,**kwargs):advance();return image,orientation
                callbacks['crop_detection_region']=crop
            elif mode=='match':
                def score(*args):advance();return [value]
                callbacks['score_ocr_variants']=score
        det=Detection(class_id=ClassId() if prior and mode=='crop' else (4 if mode=='match' else 1),polygon=[[0,0],[1,0],[1,1]],accessory_id='old')
        with patch.dict(api.__dict__,callbacks):
            invoke=lambda:api.attach_ocr_results(image,[det],{}, {'is_specialized':True,'ocr_model_class_ids':[4]} if mode=='match' else {})
            if missing:
                with self.assertRaises(TypeError):invoke()
            else:invoke()
        expected=(['prior'] if prior else (['A'] if mode=='fallback' else []))+['arg']+([] if missing else ['B' if prior else 'A'])
        self.assertEqual(events,expected)

    def test_attachment_callback_capture_before_argument_effects(self):
        for mode in ('crop','default','fallback','match'):
            with self.subTest(mode=mode):self._attachment_capture_trace(mode)

    def test_attachment_callback_capture_after_preceding_work(self):
        for mode in ('crop','default','match'):
            with self.subTest(mode=mode):self._attachment_capture_trace(mode,prior=True)

    def test_attachment_missing_callback_preserves_arguments_and_typeerror(self):
        for mode in ('crop','default','fallback','match'):
            with self.subTest(mode=mode):self._attachment_capture_trace(mode,missing=True)

    def test_attachment_first_failures_preserve_partial_state_without_retry(self):
        api=self.api;image=np.zeros((5,7,3),np.uint8)
        for mode in ('crop','default','fallback','match','finalize'):
            with self.subTest(mode=mode):
                error=RuntimeError(mode);orientation={'predicted_rotation':0,'fallback_rotations':[180],'long_edge_angle':0}
                value=result('unknown' if mode=='fallback' else 'known',6,confidence=1)
                crop=Mock(return_value=(image,orientation));score=Mock(return_value=[value])
                match=Mock(return_value={'accepted':False,'reason':'fixture'});finalize=Mock(return_value=None)
                target={'crop':crop,'default':score,'fallback':score,'match':match,'finalize':finalize}[mode]
                success={'crop':(image,orientation),'default':[],'fallback':[],'match':{'accepted':False,'reason':'fixture'},'finalize':None}[mode]
                target.side_effect=([ [value] ] if mode=='fallback' else [])+[error,success]
                det={'class_id':4 if mode=='match' else 1,'polygon':[[0,0],[1,0],[1,1]],'accessory_id':'original'}
                before=copy.deepcopy(det)
                with patch.multiple(api,crop_detection_region=crop,score_ocr_variants=score,match_ocr_text_accessory=match,finalize_ocr_detection=finalize):
                    with self.assertRaises(RuntimeError) as caught:
                        api.attach_ocr_results(image,[det],{}, {'is_specialized':True,'ocr_model_class_ids':[4]} if mode=='match' else {})
                self.assertIs(caught.exception,error);self.assertEqual(target.call_count,2 if mode=='fallback' else 1)
                self.assertEqual(det,before)
                if mode=='crop':score.assert_not_called()
                if mode in ('crop','default','fallback'):match.assert_not_called();finalize.assert_not_called()
                if mode=='match':finalize.assert_not_called()

    def test_original_uid_and_mapping_failures_are_not_retried(self):
        api=self.api
        for mode in ('uid','stopwords','keywords','labels'):
            with self.subTest(mode=mode):
                error=RuntimeError(mode);calls=[]
                def fail_once():
                    calls.append(1)
                    if len(calls)==1:raise error
                class Words(set):
                    def __contains__(self,key):fail_once();return super().__contains__(key)
                class Mapping(dict):
                    def items(self):fail_once();return super().items()
                    def get(self,*args):fail_once();return super().get(*args)
                if mode=='uid':
                    callback=Mock(side_effect=[error,'synthetic']);context=patch.object(api,'accessory_uid',callback)
                    invoke=lambda:api.build_ocr_accessory_profiles([{'name':'alpha'}],{})
                elif mode=='stopwords':
                    context=patch.object(api,'OCR_ACCESSORY_PROFILE_STOPWORDS',Words());invoke=lambda:api.ocr_keyword_terms('alpha')
                elif mode=='keywords':
                    context=patch.object(api,'MANUAL_TYPE_KEYWORDS',Mapping({'alpha':[('alpha',6)]}));invoke=lambda:api.classify_manual_text(['alpha'])
                else:
                    context=patch.object(api,'MANUAL_TYPE_LABELS',Mapping());invoke=lambda:api.classify_manual_text(['unknown'])
                with context:
                    with self.assertRaises(RuntimeError) as caught:invoke()
                self.assertIs(caught.exception,error)
                if mode=='uid':callback.assert_called_once()
                else:self.assertEqual(calls,[1])

    def test_new_policy_provider_failures_are_not_retried(self):
        from dataclasses import replace
        from local_inspection_service.detection.ocr_matching import OCRMatching,MatchThresholds
        from local_inspection_service.detection.manual_text import ManualClassifier
        for mode in ('stopwords','text_score','confidence','margin','keywords','labels'):
            with self.subTest(mode=mode):
                error=RuntimeError(mode)
                success={'stopwords':set(),'text_score':.65,'confidence':.6,'margin':.15,'keywords':{'alpha':[('alpha',6)]},'labels':{'alpha':'Alpha'}}[mode]
                target=Mock(return_value=success)
                def fail_once(*args,**kwargs):
                    if target.call_count==1:raise error
                    return success
                target.side_effect=fail_once
                if mode in ('keywords','labels'):
                    policy=ManualClassifier(target if mode=='keywords' else lambda:{'alpha':[('alpha',6)]},target if mode=='labels' else lambda:{'alpha':'Alpha'})
                    invoke=lambda:policy.classify(['alpha'])
                else:
                    thresholds=MatchThresholds(lambda:.65,lambda:.6,lambda:.15)
                    if mode!='stopwords':thresholds=replace(thresholds,**{mode:target})
                    policy=OCRMatching(target if mode=='stopwords' else lambda:set(),lambda item:'id',thresholds)
                    invoke=(lambda:policy.keywords('alpha')) if mode=='stopwords' else lambda:policy.match(['alpha'],1,{'ocr_accessory_profiles':{'id':{'keywords':[{'text':'alpha','weight':6}]}}})
                with self.assertRaises(RuntimeError) as caught:invoke()
                self.assertIs(caught.exception,error);target.assert_called_once()

    def test_single_scoring_first_failure_and_baseexception_boundaries(self):
        api=self.api;image=np.zeros((3,4,3),np.uint8)
        for mode in ('engine','predict','classify','engine_base','predict_base','classify_base'):
            with self.subTest(mode=mode):
                class Stop(BaseException):pass
                error=Stop(mode) if mode.endswith('_base') else RuntimeError(mode)
                model=Mock();model.predict.return_value=[{'rec_texts':['success'],'rec_scores':[.9]}]
                engine=Mock(return_value=model);classify=Mock(return_value={'manual_type':'unknown'})
                target=engine if mode.startswith('engine') else model.predict if mode.startswith('predict') else classify
                success=model if mode.startswith('engine') else [{'rec_texts':['success'],'rec_scores':[.9]}] if mode.startswith('predict') else {'manual_type':'unknown'}
                target.side_effect=[error,success]
                with patch.object(api,'ocr_engine',engine),patch.object(api,'classify_manual_text',classify):
                    if mode.endswith('_base') or mode=='classify':
                        with self.assertRaises(type(error)) as caught:api.score_ocr_variant(image,0)
                        self.assertIs(caught.exception,error)
                    else:
                        value=api.score_ocr_variant(image,0);self.assertEqual(value['texts'],[]);self.assertEqual(value['mean_text_score'],0)
                target.assert_called_once()
                if mode.startswith('engine'):model.predict.assert_not_called()
                if mode.endswith('_base') and not mode.startswith('classify'):classify.assert_not_called()

    def test_batch_classification_failure_retains_single_image_fallback(self):
        api=self.api;image=np.zeros((3,4,3),np.uint8);model=Mock();error=RuntimeError('classification')
        model.predict.side_effect=[[{'rec_texts':['discarded']}],[{'rec_texts':['one']}],[{'rec_texts':['two']}]]
        classify=Mock(side_effect=[error,{'manual_type':'unknown'},{'manual_type':'unknown'}])
        with patch.object(api,'ocr_engine',return_value=model),patch.object(api,'classify_manual_text',classify):
            values=api.score_ocr_variants([image,image],[0,180])
        self.assertEqual([value['texts'] for value in values],[['one'],['two']])
        self.assertEqual(model.predict.call_count,3);self.assertEqual(classify.call_count,3)
        self.assertEqual([call.args[0] for call in classify.call_args_list],[['discarded'],['one'],['two']])


    def test_engine_factory_failure_retry_instance_scope_and_bootstrap(self):
        from local_inspection_service.runtime import paddle
        model=object();prepare=Mock(side_effect=[RuntimeError('prepare'),None,None])
        factory=Mock(side_effect=[RuntimeError('factory'),model]);engine=paddle.DetectionOCREngine(prepare,factory)
        for message in ('prepare','factory'):
            with self.assertRaisesRegex(RuntimeError,message):engine.get()
            self.assertIsNone(engine.instance)
        self.assertIs(engine.get(),model);self.assertIs(engine.get(),model)
        self.assertEqual(prepare.call_count,3);self.assertEqual(factory.call_count,2)
        class FalsyModel:
            def __bool__(self):return False
        false_model=FalsyModel();false_factory=Mock(return_value=false_model);false_prepare=Mock()
        cached=paddle.DetectionOCREngine(false_prepare,false_factory)
        self.assertIs(cached.get(),false_model);self.assertIs(cached.get(),false_model)
        false_factory.assert_called_once();false_prepare.assert_called_once()

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
        polygon=[[1,1],[8,1],[8,4],[1,4]]
        # OpenCV may start equivalent rectangle vertices at either long edge.
        # Verify the real geometry, then test both edge orders explicitly so a
        # platform-specific tie does not masquerade as a changed crop algorithm.
        rectangle=cv2.minAreaRect(np.asarray(polygon,np.float32))
        actual_points=cv2.boxPoints(rectangle)
        self.assertEqual(sorted(map(tuple,actual_points.tolist())),sorted(map(tuple,polygon)))
        with patch.object(cv2,'boxPoints',return_value=np.asarray([[8,1],[1,1],[1,4],[8,4]],np.float32)) as vertices:
            unscaled,details=api.crop_detection_region(image,polygon,padding=1,max_long_side=0)
            np.testing.assert_array_equal(unscaled,expected)
            self.assertEqual(details,{'long_edge_angle':180.0,'predicted_rotation':270,'fallback_rotations':[90]})
            crop,orientation=api.crop_detection_region(image,polygon,padding=1,max_long_side=5)
            np.testing.assert_array_equal(crop,cv2.resize(expected,(3,5),interpolation=cv2.INTER_AREA))
            self.assertLessEqual(max(crop.shape[:2]),5);self.assertIn(orientation['predicted_rotation'],(0,90,180,270))
            self.assertEqual(orientation['fallback_rotations'],[(orientation['predicted_rotation']+180)%360]);np.testing.assert_array_equal(image,original)
            self.assertEqual([call.args for call in vertices.call_args_list],[(rectangle,),(rectangle,)])
        with patch.object(cv2,'boxPoints',return_value=np.asarray(polygon,np.float32)) as vertices:
            opposite,opposite_details=api.crop_detection_region(image,polygon,padding=1,max_long_side=0)
            np.testing.assert_array_equal(opposite,np.rot90(masked,k=3))
            self.assertEqual(opposite_details,{'long_edge_angle':0.0,'predicted_rotation':90,'fallback_rotations':[270]})
            bounded,bounded_details=api.crop_detection_region(image,polygon,padding=1,max_long_side=5)
            np.testing.assert_array_equal(bounded,cv2.resize(np.rot90(masked,k=3),(3,5),interpolation=cv2.INTER_AREA))
            self.assertEqual(bounded_details,opposite_details);np.testing.assert_array_equal(image,original)
            self.assertEqual([call.args for call in vertices.call_args_list],[(rectangle,),(rectangle,)])

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
