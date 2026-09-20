"""Draft original crop-component contracts; tiny synthetic arrays only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock,patch
import numpy as np
sys.path.insert(0,str(Path.cwd()))
class CropComponentContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='crop-components-')))
        (cls.root/'local_inspection_service/static').mkdir(parents=True)
        for name in ('DATABASE_URL','VANTALINE_POSTGRES_DSN','PGDSN'):os.environ.pop(name,None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(cls.root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false',YOLO_AUTOINSTALL='false')
        for name in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):
            cls.lifetime.enter_context(patch(name,side_effect=AssertionError('External operation forbidden')))
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.lifetime.close()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
    def replace(self,name,**kwargs):return self.stack.enter_context(patch.object(self.api,name,**kwargs))
    def test_cutouts_require_alpha_channel(self):
        self.assertEqual(self.api.alpha_component_cutouts(np.zeros((4,4),np.uint8)),[])
        self.assertEqual(self.api.alpha_component_cutouts(np.zeros((4,4,3),np.uint8)),[])
    def test_cutouts_exact_minimum_area_and_width(self):
        image=np.zeros((60,100,4),np.uint8);image[5:35,5:13,3]=255;image[5:45,40:47,3]=255
        result=self.api.alpha_component_cutouts(image);self.assertEqual(len(result),1);self.assertEqual(int((result[0][1]>12).sum()),240)
        image[5,5,3]=0;self.assertEqual(self.api.alpha_component_cutouts(image),[])
    def test_cutouts_sorted_cap_and_independent_copies(self):
        image=np.zeros((45,650,4),np.uint8)
        for i in range(13):image[10:26,10+45*i:27+46*i,:]=255
        result=self.api.alpha_component_cutouts(image)
        self.assertEqual(len(result),12);self.assertEqual([int((m>12).sum()) for a,m in result],[16*(17+i) for i in range(12,0,-1)])
        self.assertFalse(np.shares_memory(result[0][0],image));self.assertFalse(np.shares_memory(result[0][1],image))
        result[0][1][:]=0;self.assertEqual(int((image[:,:,3]>12).sum()),sum(16*(17+i) for i in range(13)))
    def test_cutout_threshold_is_strict(self):
        image=np.zeros((30,40,4),np.uint8);image[5:20,5:25,3]=12
        self.assertEqual(self.api.alpha_component_cutouts(image),[])
        image[5:20,5:25,3]=13;self.assertEqual(len(self.api.alpha_component_cutouts(image)),1)
    def test_focus_empty_and_no_foreground(self):
        self.assertIsNone(self.api.filter_cutout_to_focus_cell(np.zeros((0,0,3),np.uint8),np.zeros((0,0),np.uint8),(0,0,5,5)))
        self.assertIsNone(self.api.filter_cutout_to_focus_cell(np.zeros((30,30,3),np.uint8),np.zeros((30,30),np.uint8),(0,0,20,20)))
    def test_focus_rejects_distant_component(self):
        asset=np.zeros((100,100,3),np.uint8);mask=np.zeros((100,100),np.uint8);mask[70:90,70:90]=255
        self.assertIsNone(self.api.filter_cutout_to_focus_cell(asset,mask,(0,0,20,20)))
    def test_focus_exact240_padding_and_copies(self):
        asset=np.ones((40,40,3),np.uint8);mask=np.zeros((40,40),np.uint8);mask[5:17,5:25]=255
        result=self.api.filter_cutout_to_focus_cell(asset,mask,(0,0,30,30));self.assertIsNotNone(result)
        self.assertEqual(result[2],(1,1,29,21));self.assertEqual(result[0].shape,(20,28,3));self.assertEqual(int((result[1]>8).sum()),240)
        self.assertFalse(np.shares_memory(result[0],asset));self.assertFalse(np.shares_memory(result[1],mask))
        mask[5,5]=0;self.assertIsNone(self.api.filter_cutout_to_focus_cell(asset,mask,(0,0,30,30)))
    def test_usable_none_does_not_trim(self):
        trim=self.replace('trim_masked_asset',side_effect=AssertionError('unused'))
        self.assertIsNone(self.api.usable_object_cutout(None,(20,20,3)));trim.assert_not_called()
    def test_usable_trims_pad_two_and_preserves_result_identity(self):
        asset=np.ones((5,6,3),np.uint8);mask=np.full((5,6),255,np.uint8);trim=self.replace('trim_masked_asset',return_value=(asset,mask))
        source=(np.zeros((8,8,3),np.uint8),np.zeros((8,8),np.uint8));result=self.api.usable_object_cutout(source,(20,20,3))
        self.assertIs(result[0],asset);self.assertIs(result[1],mask);self.assertIs(trim.call_args.args[0],source[0]);self.assertIs(trim.call_args.args[1],source[1]);self.assertEqual(trim.call_args.kwargs,{'pad':2})
    def test_usable_rejects_broad_full_mask_but_accepts_exact_fill(self):
        asset=np.ones((10,10,3),np.uint8);mask=np.full((10,10),255,np.uint8);self.replace('trim_masked_asset',return_value=(asset,mask))
        self.assertIsNone(self.api.usable_object_cutout((asset,mask),(10,10,3)))
        mask.flat[72:]=0;result=self.api.usable_object_cutout((asset,mask),(10,10,3));self.assertIsNotNone(result);self.assertIs(result[1],mask)
    def test_cleanup_empty_and_no_component_identity(self):
        alpha=np.zeros((0,0),np.uint8);result,meta=self.api.cleanup_crop_alpha_components(np.zeros((0,0,3),np.uint8),alpha)
        self.assertIs(result,alpha);self.assertEqual(meta['mask_strategy'],'crop_local_component_cleanup_empty');self.assertEqual(meta['foreground_component_bbox_xyxy'],[0,0,0,0])
        alpha=np.full((10,10),28,np.uint8);result,meta=self.api.cleanup_crop_alpha_components(np.zeros((10,10,3),np.uint8),alpha)
        self.assertIs(result,alpha);self.assertEqual(meta['mask_strategy'],'crop_local_component_cleanup_no_components');self.assertEqual(meta['foreground_component_bbox_xyxy'],[0,0,10,10])
    def test_cleanup_anchor_keeps_support_and_removes_distant(self):
        asset=np.zeros((100,100,3),np.uint8);alpha=np.zeros((100,100),np.uint8)
        alpha[10:30,10:30]=255;alpha[70:80,70:80]=200;alpha[70:80,82:86]=180
        clean,meta=self.api.cleanup_crop_alpha_components(asset,alpha,(75.125,75.875))
        self.assertEqual(meta,{'mask_strategy':'crop_local_alpha_center_anchored_components','foreground_component_bbox_xyxy':[70,70,86,80],'foreground_component_area_px':140,'foreground_component_anchor_xy':[75.12,75.88],'removed_stray_component_count':1,'removed_stray_component_area_px':400,'candidate_component_count':3,'kept_component_count':2})
        self.assertEqual(int((clean>0).sum()),140);self.assertEqual(int(clean[75,75]),200);self.assertEqual(int(clean[75,83]),180);self.assertEqual(int(alpha[15,15]),255)
    def test_cleanup_default_anchor_and_minimum_override(self):
        asset=np.zeros((100,100,3),np.uint8);alpha=np.zeros((100,100),np.uint8);alpha[40:60,40:60]=255;alpha[5:25,5:25]=255
        clean,meta=self.api.cleanup_crop_alpha_components(asset,alpha);self.assertEqual(meta['foreground_component_anchor_xy'],[50.0,50.0]);self.assertEqual(meta['foreground_component_bbox_xyxy'],[40,40,60,60])
        result,meta=self.api.cleanup_crop_alpha_components(asset,alpha,min_area=401);self.assertIs(result,alpha);self.assertEqual(meta['mask_strategy'],'crop_local_component_cleanup_no_components')
    def test_summary_empty_strict_threshold_and_exact_minimum(self):
        self.assertEqual(self.api.alpha_component_summary(np.zeros((0,0),np.uint8)),(0,0))
        alpha=np.zeros((40,40),np.uint8);alpha[3:8,3:10]=29;alpha[20:25,20:28]=28
        self.assertEqual(self.api.alpha_component_summary(alpha),(1,35));self.assertEqual(self.api.alpha_component_summary(alpha,threshold=29),(0,0));self.assertEqual(self.api.alpha_component_summary(alpha,threshold=27),(2,75))
        alpha[3,3]=0;self.assertEqual(self.api.alpha_component_summary(alpha),(0,0))

    def test_trimmer_selected_before_cutout_argument_effects(self):
        asset=np.ones((4,5,3),np.uint8);mask=np.full((4,5),255,np.uint8)
        original=self.replace('trim_masked_asset',return_value=(asset,mask));newer=Mock(return_value=(asset*2,mask))
        api=self.api
        class ChangingCutout(tuple):
            def __getitem__(self,index):
                if index==0:api.trim_masked_asset=newer
                return super().__getitem__(index)
        result=self.api.usable_object_cutout(ChangingCutout((asset,mask)),(20,20,3))
        self.assertIs(result[0],asset);original.assert_called_once();newer.assert_not_called()
    def test_focus_bounds_selected_after_component_analysis(self):
        asset=np.ones((40,40,3),np.uint8);mask=np.zeros((40,40),np.uint8);mask[5:17,5:25]=255
        old=self.replace('alpha_bbox',return_value=[0,0,40,40]);newer=Mock(return_value=[5,5,25,17]);components=self.api.cv2.connectedComponentsWithStats
        def analyze(*args,**kwargs):
            result=components(*args,**kwargs);self.api.alpha_bbox=newer;return result
        with patch.object(self.api.cv2,'connectedComponentsWithStats',side_effect=analyze):result=self.api.filter_cutout_to_focus_cell(asset,mask,(0,0,30,30))
        self.assertIsNotNone(result);self.assertEqual(result[2],(1,1,29,21));old.assert_not_called();newer.assert_called_once()
    def test_cleanup_bounds_selected_after_mask_intersection(self):
        asset=np.zeros((40,40,3),np.uint8);alpha=np.zeros((40,40),np.uint8);alpha[10:20,10:20]=255
        old=self.replace('alpha_bbox',return_value=[0,0,40,40]);newer=Mock(return_value=[10,10,20,20]);intersection=self.api.cv2.bitwise_and
        def intersect(*args,**kwargs):
            result=intersection(*args,**kwargs);self.api.alpha_bbox=newer;return result
        with patch.object(self.api.cv2,'bitwise_and',side_effect=intersect):clean,meta=self.api.cleanup_crop_alpha_components(asset,alpha)
        self.assertEqual(meta['foreground_component_bbox_xyxy'],[10,10,20,20]);old.assert_not_called();newer.assert_called_once()

    def test_constructor_reads_no_geometry_capability(self):
        from local_inspection_service.accessories.crop_component_ports import CropGeometry
        from local_inspection_service.accessories.crop_selection import CropSelection
        forbidden=Mock(side_effect=AssertionError('eager capability read'))
        instance=CropSelection(CropGeometry(bounds=forbidden,trim=forbidden));self.assertIsInstance(instance,CropSelection);forbidden.assert_not_called()
    def test_independent_selection_and_pure_components_ignore_root_callbacks(self):
        from local_inspection_service.accessories.crop_component_ports import CropGeometry
        from local_inspection_service.accessories.crop_selection import CropSelection
        from local_inspection_service.accessories import crop_analysis
        first_asset=np.ones((5,6,3),np.uint8);first_mask=np.full((5,6),255,np.uint8)
        second_asset=np.ones((7,8,3),np.uint8);second_mask=np.full((7,8),255,np.uint8)
        first_bounds=Mock(return_value=[5,5,25,17]);second_bounds=Mock(return_value=[10,10,20,20])
        first_trim=Mock(return_value=(first_asset,first_mask));second_trim=Mock(return_value=(second_asset,second_mask))
        first=CropSelection(CropGeometry(bounds=lambda:first_bounds,trim=lambda:first_trim))
        second=CropSelection(CropGeometry(bounds=lambda:second_bounds,trim=lambda:second_trim))
        asset=np.ones((40,40,3),np.uint8);mask=np.zeros((40,40),np.uint8);mask[5:17,5:25]=255
        with ExitStack() as blocked:
            poisons=[blocked.enter_context(patch.object(self.api,name,side_effect=AssertionError('root callback forbidden'))) for name in ('alpha_bbox','trim_masked_asset','alpha_component_cutouts','alpha_component_summary')]
            for service,expected_crop,expected_bounds,expected_asset in [(first,(1,1,29,21),[5,5,25,17],first_asset),(second,(6,6,24,24),[10,10,20,20],second_asset),(first,(1,1,29,21),[5,5,25,17],first_asset)]:
                self.assertEqual(service.filter_cutout_to_focus_cell(asset,mask,(0,0,30,30))[2],expected_crop)
                self.assertEqual(service.cleanup_crop_alpha_components(asset,mask)[1]['foreground_component_bbox_xyxy'],expected_bounds)
                self.assertIs(service.usable_object_cutout((asset,mask),(40,40,3))[0],expected_asset)
            self.assertEqual(crop_analysis.alpha_component_summary(mask),(1,240))
            rgba=np.dstack((asset,mask));self.assertEqual(len(crop_analysis.alpha_component_cutouts(rgba)),1)
        for poison in poisons:poison.assert_not_called()
        self.assertEqual(first_bounds.call_count,4);self.assertEqual(second_bounds.call_count,2);self.assertEqual(first_trim.call_count,2);self.assertEqual(second_trim.call_count,1)
        self.assertIs(crop_analysis.cv2,self.api.cv2);self.assertIs(crop_analysis.np,self.api.np)

if __name__=='__main__':unittest.main()
