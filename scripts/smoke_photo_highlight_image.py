"""Draft original photo-highlight image contracts; synthetic arrays only."""
import os
import base64
import hashlib
import numpy as np
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path.cwd()))

class PhotoHighlightImageContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ)
        cls.environment.start()
        cls.root = tempfile.TemporaryDirectory(prefix='photo-highlight-workflow-')
        (Path(cls.root.name) / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=cls.root.name, VANTALINE_DATA_STORE='json', LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server
    @classmethod
    def tearDownClass(cls):
        cls.root.cleanup()
        cls.environment.stop()
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory(dir=self.root.name)))
        for name in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):
            self.stack.enter_context(patch(name, side_effect=AssertionError('External operation forbidden')))
    def replace(self, name, **kwargs):
        return self.stack.enter_context(patch.object(self.api, name, **kwargs))
    def test_prompt_exact_text_and_name_precedence(self):
        uid=self.replace('accessory_uid',return_value='identifier')
        self.assertEqual(hashlib.sha256(self.api.photo_highlight_mask_prompt({'name':'Synthetic','label':'Other'}).encode()).hexdigest(),'06f8e24b093bf09a644768a51c52069272682840b155398c0d25e7a94e6f944e')
        uid.assert_not_called()
        self.assertIn('Accessory: Label.',self.api.photo_highlight_mask_prompt({'label':'Label'}));uid.assert_not_called()
        self.assertIn('Accessory: identifier.',self.api.photo_highlight_mask_prompt({}));uid.assert_called_once()
    def test_input_invalid_or_encode_failure(self):
        self.assertIsNone(self.api.photo_highlight_input_data_url(None))
        self.assertIsNone(self.api.photo_highlight_input_data_url(np.zeros((2,2),np.uint8)))
        with patch.object(self.api.cv2,'imencode',return_value=(False,None)) as encode:
            self.assertIsNone(self.api.photo_highlight_input_data_url(np.zeros((4,5,3),np.uint8)))
        self.assertEqual(encode.call_args.args[0],'.jpg')
        self.assertEqual(encode.call_args.args[2],[int(self.api.cv2.IMWRITE_JPEG_QUALITY),92])
    def test_input_small_image_copy_and_exact_base64(self):
        image=np.full((4,7,3),17,np.uint8);encoded=np.array([1,2,3],np.uint8)
        with patch.object(self.api.cv2,'imencode',return_value=(True,encoded)):
            result=self.api.photo_highlight_input_data_url(image)
        self.assertIsNot(result[0],image);np.testing.assert_array_equal(result[0],image)
        self.assertEqual(result[1:],('data:image/jpeg;base64,AQID',1.0,1.0))
    def test_input_resize_preserves_actual_axis_ratios(self):
        self.replace('PHOTO_HIGHLIGHT_MASK_MAX_SIDE',new=8)
        image=np.zeros((5,11,3),np.uint8)
        with patch.object(self.api.cv2,'imencode',return_value=(True,np.array([1],np.uint8))):result=self.api.photo_highlight_input_data_url(image)
        self.assertEqual(result[0].shape,(4,8,3));self.assertEqual(result[2],8/11);self.assertEqual(result[3],4/5)
    def test_decode_invalid_and_no_highlight(self):
        mask,metadata=self.api.decode_photo_highlight_mask(None)
        self.assertEqual(mask.shape,(0,0));self.assertEqual(mask.dtype,np.uint8);self.assertEqual(metadata,{'ok':False,'reason':'mask_unreadable'})
        mask,metadata=self.api.decode_photo_highlight_mask(np.zeros((64,64,3),np.uint8))
        self.assertEqual(int(mask.sum()),0);self.assertEqual(metadata,{'ok':False,'reason':'no_highlight_component','component_count':0})
    def test_decode_rectangle_exact_component(self):
        image=np.zeros((128,128,3),np.uint8);image[40:88,40:88,1]=255
        mask,metadata=self.api.decode_photo_highlight_mask(image)
        self.assertEqual(metadata,{'ok':True,'bbox_xyxy_ai':[40,40,88,88],'mask_area_fraction':0.140625,'component_count':1,'main_component_area':2304,'main_component_aspect':1.0})
        self.assertEqual(int((mask>0).sum()),2304);self.assertEqual(mask.dtype,np.uint8)
    def test_decode_excessive_mask_area_rejected(self):
        image=np.zeros((64,64,3),np.uint8);image[:,:,1]=255
        mask,metadata=self.api.decode_photo_highlight_mask(image)
        self.assertFalse(metadata['ok']);self.assertEqual(metadata['reason'],'mask_area_out_of_range');self.assertEqual(metadata['mask_area_fraction'],1.0)
    def test_auto_roi_invalid_and_small(self):
        mask,metadata=self.api.photo_highlight_auto_roi_mask(None,None)
        self.assertIsNone(mask);self.assertEqual(metadata,{'status':'unavailable','reason':'empty_roi'})
        mask,metadata=self.api.photo_highlight_auto_roi_mask(np.zeros((11,20,3),np.uint8),np.ones((11,20),np.uint8))
        self.assertIsNone(mask);self.assertEqual(metadata,{'status':'unavailable','reason':'roi_too_small'})
    def test_auto_roi_uniform_background_has_no_component(self):
        mask,metadata=self.api.photo_highlight_auto_roi_mask(np.full((64,64,3),255,np.uint8),np.zeros((64,64),np.uint8))
        self.assertIsNone(mask);self.assertEqual(metadata,{'status':'unavailable','reason':'no_auto_foreground_component'})
    def test_compare_missing_and_area_boundaries(self):
        self.assertEqual(self.api.photo_highlight_auto_compare(None,None),{'ok':True,'status':'skipped','reason':'auto_mask_unavailable','score':0.0})
        ai=np.zeros((16,16),np.uint8);auto=np.full((16,16),29,np.uint8);ai.flat[:239]=9
        result=self.api.photo_highlight_auto_compare(ai,auto)
        self.assertEqual(result,{'ok':True,'status':'skipped','reason':'insufficient_mask_area','ai_area_px':239,'auto_area_px':256,'score':0.0})
    def test_compare_identical_masks_exact_projection(self):
        ai=np.full((16,16),9,np.uint8);auto=np.full((16,16),29,np.uint8)
        result=self.api.photo_highlight_auto_compare(ai,auto)
        self.assertTrue(result['ok']);self.assertEqual(result['status'],'passed');self.assertEqual(result['score'],1.0)
        self.assertEqual(result['mask_iou'],1.0);self.assertEqual(result['bbox_iou'],1.0);self.assertEqual(result['ai_area_px'],256)
        auto[:]=28
        self.assertEqual(self.api.photo_highlight_auto_compare(ai,auto)['auto_area_px'],0)
    def test_compare_disjoint_masks_fail(self):
        ai=np.zeros((64,64),np.uint8);auto=np.zeros((64,64),np.uint8);ai[4:20,4:20]=255;auto[40:56,40:56]=255
        result=self.api.photo_highlight_auto_compare(ai,auto)
        self.assertFalse(result['ok']);self.assertEqual(result['reason'],'ai_mask_auto_crop_mismatch');self.assertEqual(result['mask_iou'],0.0);self.assertEqual(result['bbox_iou'],0.0)

    def test_compare_exact_minimum_area_is_compared(self):
        ai=np.full((15,16),9,np.uint8);auto=np.full((15,16),29,np.uint8)
        result=self.api.photo_highlight_auto_compare(ai,auto)
        self.assertTrue(result['ok']);self.assertEqual(result['status'],'passed');self.assertEqual(result['ai_area_px'],240)
    def test_auto_roi_contrast_object_produces_available_mask(self):
        roi=np.full((64,64,3),255,np.uint8);roi[20:44,20:44]=0
        ai=np.zeros((64,64),np.uint8);ai[20:44,20:44]=255
        mask,metadata=self.api.photo_highlight_auto_roi_mask(roi,ai)
        self.assertIsNotNone(mask);self.assertEqual(metadata['status'],'available');self.assertEqual(metadata['candidate_component_count'],1)
        self.assertEqual(metadata['kept_component_count'],1);self.assertEqual(mask.dtype,np.uint8);self.assertEqual(mask.shape,(64,64))
        self.assertGreater(int(mask[32,32]),0);self.assertEqual(int(mask[0,0]),0)

    def test_prompt_identifier_selected_after_name_lookup(self):
        later=Mock(return_value='later')
        original=self.replace('accessory_uid',return_value='old');api=self.api
        class Item(dict):
            def get(self,key,default=None):
                if key=='label':api.accessory_uid=later
                return super().get(key,default)
        self.assertIn('Accessory: later.',self.api.photo_highlight_mask_prompt(Item()))
        original.assert_not_called();later.assert_called_once()
    def test_input_selects_encoder_after_resize(self):
        self.replace('PHOTO_HIGHLIGHT_MASK_MAX_SIDE',new=8);later=Mock(return_value=(True,np.array([1],np.uint8)))
        old=self.stack.enter_context(patch.object(self.api.cv2,'imencode',return_value=(False,None)))
        def resize(*args,**kwargs):
            self.api.cv2.imencode=later
            return np.zeros((4,8,3),np.uint8)
        self.stack.enter_context(patch.object(self.api.cv2,'resize',side_effect=resize))
        result=self.api.photo_highlight_input_data_url(np.zeros((5,11,3),np.uint8))
        self.assertIsNotNone(result);old.assert_not_called();later.assert_called_once()
    def test_compare_refreshes_alpha_and_iou_callbacks_in_order(self):
        events=[];bbox=[0,0,16,16];iou=Mock(side_effect=lambda *args:events.append('iou') or 1.0)
        def second(*args,**kwargs):
            events.append('second');self.api.bbox_iou_xyxy=iou
            return bbox
        later=Mock(side_effect=second)
        def first(*args,**kwargs):
            events.append('first');self.api.alpha_bbox=later
            return bbox
        old=self.replace('alpha_bbox',side_effect=first);old_iou=self.replace('bbox_iou_xyxy',return_value=0.0)
        result=self.api.photo_highlight_auto_compare(np.full((16,16),9,np.uint8),np.full((16,16),29,np.uint8))
        self.assertTrue(result['ok']);self.assertEqual(events,['first','second','iou']);self.assertIs(result['auto_bbox_xyxy_roi'],bbox)
        old.assert_called_once();later.assert_called_once();old_iou.assert_not_called();iou.assert_called_once()


    def test_image_service_constructors_do_not_read_capabilities(self):
        from dataclasses import fields
        from local_inspection_service.agent import photo_highlight_image_ports as ports
        from local_inspection_service.agent.photo_highlight_image_input import PhotoHighlightImageInput
        from local_inspection_service.agent.photo_highlight_comparison import PhotoHighlightComparison
        getters=[]
        def group(port_type):
            values={f.name:Mock(return_value=None) for f in fields(port_type)};getters.extend(values.values())
            return port_type(**values)
        PhotoHighlightImageInput(group(ports.PhotoHighlightImagePolicy))
        PhotoHighlightComparison(group(ports.PhotoMaskGeometry))
        for getter in getters:getter.assert_not_called()
    def test_image_services_and_pure_masks_do_not_use_root_business_state(self):
        from local_inspection_service.agent.photo_highlight_image_ports import PhotoHighlightImagePolicy,PhotoMaskGeometry
        from local_inspection_service.agent.photo_highlight_image_input import PhotoHighlightImageInput
        from local_inspection_service.agent.photo_highlight_comparison import PhotoHighlightComparison
        from local_inspection_service.agent import photo_highlight_masks as masks
        def make(name,size,overlap):
            return PhotoHighlightImageInput(PhotoHighlightImagePolicy(identifier=lambda:lambda item:name,max_side=lambda:size)),PhotoHighlightComparison(PhotoMaskGeometry(alpha=lambda:lambda *args,**kwargs:[0,0,16,16],iou=lambda:lambda *args:overlap))
        instances={'first':make('first',8,1.0),'second':make('second',4,0.0)}
        with patch.object(self.api,'accessory_uid',side_effect=AssertionError('root identity')),patch.object(self.api,'alpha_bbox',side_effect=AssertionError('root bbox')),patch.object(self.api,'bbox_iou_xyxy',side_effect=AssertionError('root iou')),patch.object(self.api,'decode_photo_highlight_mask',side_effect=AssertionError('root mask')),patch.object(self.api,'photo_highlight_auto_roi_mask',side_effect=AssertionError('root roi')),patch.object(self.api.cv2,'imencode',return_value=(True,np.array([1],np.uint8))):
            for name in ('first','second','first'):
                inputs,comparison=instances[name]
                self.assertIn('Accessory: '+name+'.',inputs.photo_highlight_mask_prompt({}))
                encoded=inputs.photo_highlight_input_data_url(np.zeros((16,16,3),np.uint8))
                self.assertEqual(encoded[0].shape[:2],(8,8) if name=='first' else (4,4))
                result=comparison.photo_highlight_auto_compare(np.full((16,16),9,np.uint8),np.full((16,16),29,np.uint8))
                self.assertEqual(result['ok'],name=='first')
            mask,metadata=masks.decode_photo_highlight_mask(np.zeros((32,32,3),np.uint8))
            self.assertEqual(metadata['reason'],'no_highlight_component');self.assertEqual(mask.shape,(32,32))
            roi,metadata=masks.photo_highlight_auto_roi_mask(np.full((64,64,3),255,np.uint8),np.zeros((64,64),np.uint8))
            self.assertIsNone(roi);self.assertEqual(metadata['reason'],'no_auto_foreground_component')
            self.assertIs(masks.cv2,self.api.cv2);self.assertIs(masks.np,self.api.np)

if __name__=='__main__':unittest.main()
