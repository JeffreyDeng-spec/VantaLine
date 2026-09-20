"""Material-alpha contracts; tiny synthetic arrays and isolated legacy helper only."""
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
class MaterialAlphaContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='material-alpha-')))
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
    def alpha_fixture(self, total=100, glass=89, anchors=11, value=150):
        hsv=np.zeros((1,total,3),np.uint8);hsv[:,:,1]=80;hsv[:,:,2]=130;hsv[0,:glass,1]=0;hsv[0,:glass,2]=value;hsv[0,glass:glass+anchors,1]=100
        asset=np.zeros((1,total,3),np.uint8);mask=np.full((1,total),255,np.uint8);edges=np.zeros((1,total),np.uint8)
        self.stack.enter_context(patch.object(self.api.cv2,'cvtColor',side_effect=lambda a,code:hsv if code==self.api.cv2.COLOR_BGR2HSV else np.zeros((1,total),np.uint8)))
        self.stack.enter_context(patch.object(self.api.cv2,'Canny',return_value=edges));self.stack.enter_context(patch.object(self.api.cv2,'dilate',side_effect=lambda a,k,iterations:a))
        blur=self.stack.enter_context(patch.object(self.api.cv2,'GaussianBlur',side_effect=lambda a,k,s:a.copy()))
        return asset,mask,hsv,edges,blur
    def test_transparent_empty_returns_same_mask_and_default_stats(self):
        mask=np.zeros((0,0),np.uint8)
        with patch.object(self.api.cv2,'cvtColor') as convert:
            adjusted,stats=self.api.transparent_object_alpha(np.zeros((0,0,3),np.uint8),mask)
        self.assertIs(adjusted,mask);self.assertFalse(stats['transparent_alpha_applied']);self.assertEqual(stats['opaque_anchor_fraction'],0.0);convert.assert_not_called()
    def test_transparent_glass_weak_alpha_preserves_anchors(self):
        asset,mask,hsv,edges,blur=self.alpha_fixture();adjusted,stats=self.api.transparent_object_alpha(asset,mask)
        np.testing.assert_array_equal(adjusted[0,:89],np.full(89,92,np.uint8));np.testing.assert_array_equal(adjusted[0,89:],np.full(11,255,np.uint8));np.testing.assert_array_equal(mask,np.full_like(mask,255));self.assertTrue(stats['transparent_alpha_applied']);self.assertEqual(stats['glass_fraction'],0.89);self.assertEqual(stats['opaque_anchor_fraction'],0.11);blur.assert_called_once()
    def test_transparent_highlights_are_raised_to126(self):
        asset,mask,hsv,edges,blur=self.alpha_fixture(value=200);adjusted,stats=self.api.transparent_object_alpha(asset,mask)
        np.testing.assert_array_equal(adjusted[0,:89],np.full(89,126,np.uint8));self.assertTrue(stats['transparent_alpha_applied'])
    def test_transparent_glass_count_boundary80(self):
        asset,mask,hsv,edges,blur=self.alpha_fixture(total=90,glass=80,anchors=10);adjusted,stats=self.api.transparent_object_alpha(asset,mask)
        self.assertFalse(stats['transparent_alpha_applied']);np.testing.assert_array_equal(adjusted,mask)
        hsv[0,80,1]=0;hsv[0,80,2]=150;adjusted,stats=self.api.transparent_object_alpha(asset,mask)
        self.assertTrue(stats['transparent_alpha_applied']);self.assertEqual(int(adjusted[0,80]),92)
    def test_transparent_glass_fraction_strict12_percent(self):
        asset,mask,hsv,edges,blur=self.alpha_fixture(total=1000,glass=120,anchors=10);adjusted,stats=self.api.transparent_object_alpha(asset,mask)
        self.assertEqual(stats['glass_fraction'],0.12);self.assertFalse(stats['transparent_alpha_applied'])
        hsv[0,130,1]=0;hsv[0,130,2]=150;adjusted,stats=self.api.transparent_object_alpha(asset,mask)
        self.assertTrue(stats['transparent_alpha_applied']);self.assertEqual(stats['glass_fraction'],0.121)
    def test_transparent_without_anchors_or_edges_is_not_applied(self):
        asset,mask,hsv,edges,blur=self.alpha_fixture(total=100,glass=100,anchors=0);adjusted,stats=self.api.transparent_object_alpha(asset,mask)
        self.assertFalse(stats['transparent_alpha_applied']);np.testing.assert_array_equal(adjusted,mask);self.assertIsNot(adjusted,mask)
    def test_solid_empty_and_threshold20_return_original(self):
        for mask in (np.zeros((0,0),np.uint8),np.full((5,5),20,np.uint8)):
            adjusted,stats=self.api.solid_object_alpha(mask);self.assertIs(adjusted,mask);self.assertTrue(stats['solid_alpha_applied']);self.assertEqual(stats['opaque_anchor_fraction'],1.0)
    def test_solid21_becomes255_without_mutating_input(self):
        mask=np.full((5,5),21,np.uint8);adjusted,stats=self.api.solid_object_alpha(mask)
        np.testing.assert_array_equal(adjusted,np.full((5,5),255,np.uint8));np.testing.assert_array_equal(mask,np.full((5,5),21,np.uint8));self.assertIsNot(adjusted,mask);self.assertTrue(stats['solid_alpha_applied'])
    def test_material_policy_transparent_preserves_aliases(self):
        asset=np.zeros((2,2,3),np.uint8);mask=np.ones((2,2),np.uint8);adjusted=np.full_like(mask,92);stats={'existing':[]};metadata={'policy':'x'}
        policy=self.replace('object_alpha_material_policy',return_value='transparent');transparent=self.replace('transparent_object_alpha',return_value=(adjusted,stats));solid=self.replace('solid_object_alpha')
        result,info=self.api.material_aware_object_alpha(asset,mask,metadata)
        self.assertIs(result,adjusted);self.assertIs(info,stats);self.assertEqual(info['object_alpha_material_policy'],'transparent');policy.assert_called_once_with(None,metadata);transparent.assert_called_once_with(asset,mask);solid.assert_not_called()
    def test_material_other_policy_uses_opaque(self):
        asset=np.zeros((2,2,3),np.uint8);mask=np.ones((2,2),np.uint8);stats={}
        self.replace('object_alpha_material_policy',return_value='unknown');solid=self.replace('solid_object_alpha',return_value=(mask,stats));transparent=self.replace('transparent_object_alpha')
        adjusted,info=self.api.material_aware_object_alpha(asset,mask)
        self.assertIs(adjusted,mask);self.assertIs(info,stats);self.assertEqual(info['object_alpha_material_policy'],'opaque');solid.assert_called_once_with(mask);transparent.assert_not_called()
    def test_material_callback_refresh_after_policy(self):
        asset=np.zeros((2,2,3),np.uint8);mask=np.ones((2,2),np.uint8);old=self.replace('transparent_object_alpha',return_value=(mask,{'selected':'old'}));new=Mock(return_value=(mask,{'selected':'new'}))
        def policy(*args):self.api.transparent_object_alpha=new;return 'transparent'
        self.replace('object_alpha_material_policy',side_effect=policy);adjusted,stats=self.api.material_aware_object_alpha(asset,mask)
        self.assertEqual(stats['selected'],'new');old.assert_not_called();new.assert_called_once_with(asset,mask)
    def test_material_callback_exception_is_exact(self):
        asset=np.zeros((2,2,3),np.uint8);mask=np.ones((2,2),np.uint8);failure=RuntimeError('synthetic alpha')
        self.replace('object_alpha_material_policy',return_value='transparent');callback=self.replace('transparent_object_alpha',side_effect=failure)
        with self.assertRaises(RuntimeError) as seen:self.api.material_aware_object_alpha(asset,mask)
        self.assertIs(seen.exception,failure);callback.assert_called_once_with(asset,mask)
    def test_solid_morphology_order_blur_and_core_restoration(self):
        mask=np.full((5,5),21,np.uint8);opened=np.zeros((5,5),np.uint8);opened[2,2]=255;closed=np.zeros((5,5),np.uint8);closed[1:4,1:4]=255;events=[]
        def morph(src,operation,kernel,iterations):
            events.append(operation)
            if len(events)==1:np.testing.assert_array_equal(src,np.full((5,5),255,np.uint8));return opened
            self.assertIs(src,opened);return closed
        def blur(src,kernel,sigma):self.assertIs(src,closed);events.append('blur');return np.full((5,5),7,np.uint8)
        with patch.object(self.api.cv2,'morphologyEx',side_effect=morph) as morphology,patch.object(self.api.cv2,'GaussianBlur',side_effect=blur) as gaussian:
            adjusted,stats=self.api.solid_object_alpha(mask)
        self.assertEqual(events,[self.api.cv2.MORPH_OPEN,self.api.cv2.MORPH_CLOSE,'blur']);self.assertEqual(morphology.call_count,2);gaussian.assert_called_once();expected=np.full((5,5),7,np.uint8);expected[1:4,1:4]=255;np.testing.assert_array_equal(adjusted,expected)
    def test_transparent_edge_only_evidence_without_anchors(self):
        asset,mask,hsv,edges,blur=self.alpha_fixture(total=100,glass=100,anchors=0);edges[0,:2]=255
        adjusted,stats=self.api.transparent_object_alpha(asset,mask);self.assertFalse(stats['transparent_alpha_applied']);self.assertEqual(stats['edge_fraction'],0.02)
        edges[0,2]=255;adjusted,stats=self.api.transparent_object_alpha(asset,mask)
        self.assertTrue(stats['transparent_alpha_applied']);self.assertEqual(stats['opaque_anchor_fraction'],0.0);self.assertEqual(stats['edge_fraction'],0.03);np.testing.assert_array_equal(adjusted[0,:3],np.full(3,255,np.uint8));self.assertEqual(int(adjusted[0,3]),92)
    def test_policy_error_stops_dispatch_without_retry(self):
        asset=np.zeros((2,2,3),np.uint8);mask=np.ones((2,2),np.uint8);failure=RuntimeError('policy first error')
        policy=self.replace('object_alpha_material_policy',side_effect=chain([failure],repeat('transparent')));transparent=self.replace('transparent_object_alpha',return_value=(mask,{}));solid=self.replace('solid_object_alpha',return_value=(mask,{}))
        with self.assertRaises(RuntimeError) as seen:self.api.material_aware_object_alpha(asset,mask)
        self.assertIs(seen.exception,failure);policy.assert_called_once_with(None,None);transparent.assert_not_called();solid.assert_not_called()
    def test_policy_and_solid_refresh_between_calls(self):
        asset=np.zeros((2,2,3),np.uint8);mask=np.ones((2,2),np.uint8);old_policy=self.replace('object_alpha_material_policy',return_value='opaque');old_solid=self.replace('solid_object_alpha',return_value=(mask,{'selected':'old'}));new_policy=Mock(return_value='unknown');new_solid=Mock(return_value=(mask,{'selected':'new'}));selected=[]
        selected.append(self.api.material_aware_object_alpha(asset,mask)[1]['selected']);self.api.object_alpha_material_policy=new_policy;self.api.solid_object_alpha=new_solid
        selected.append(self.api.material_aware_object_alpha(asset,mask)[1]['selected']);self.api.object_alpha_material_policy=old_policy;self.api.solid_object_alpha=old_solid;selected.append(self.api.material_aware_object_alpha(asset,mask)[1]['selected'])
        self.assertEqual(selected,['old','new','old']);self.assertEqual(old_policy.call_count,2);self.assertEqual(old_solid.call_count,2);new_policy.assert_called_once_with(None,None);new_solid.assert_called_once_with(mask)
    def test_existing_synthetic_alpha_helper(self):
        import runpy
        path=Path('local_inspection_service/scripts/smoke_object_overlap_alpha_pose_scale.py')
        with patch.dict(sys.modules,{'server':self.api}),patch.object(sys,'path',list(sys.path)):
            namespace=runpy.run_path(str(path),run_name='material_alpha_legacy_contract')
            result=namespace['material_alpha_smoke']()
        self.assertEqual(result,{'solid_policy':'opaque','solid_mean_alpha':255.0,'solid_opaque_fraction':1.0,'glass_policy':'transparent','glass_transparent_alpha_applied':False,'glass_center_alpha':210})
    def test_alpha_constructor_reads_no_dependencies(self):
        from local_inspection_service.accessories.material_alpha import MaterialAlphaProcessor
        from local_inspection_service.accessories.material_alpha_ports import MaterialAlphaOperations
        forbidden=Mock(side_effect=AssertionError('eager alpha dependencies'))
        processor=MaterialAlphaProcessor(MaterialAlphaOperations(policy=forbidden,transparent=forbidden,solid=forbidden))
        self.assertIsInstance(processor,MaterialAlphaProcessor);forbidden.assert_not_called()
    def test_independent_alpha_first_second_first(self):
        from local_inspection_service.accessories.material_alpha import MaterialAlphaProcessor
        from local_inspection_service.accessories.material_alpha_ports import MaterialAlphaOperations
        from local_inspection_service.accessories.alpha_masks import transparent_object_alpha,solid_object_alpha
        transparent_policy=Mock(return_value='transparent');solid_policy=Mock(return_value='opaque')
        first=MaterialAlphaProcessor(MaterialAlphaOperations(policy=lambda:transparent_policy,transparent=lambda:transparent_object_alpha,solid=lambda:solid_object_alpha))
        second=MaterialAlphaProcessor(MaterialAlphaOperations(policy=lambda:solid_policy,transparent=lambda:transparent_object_alpha,solid=lambda:solid_object_alpha))
        poisons=[self.replace(name,side_effect=AssertionError('root forbidden')) for name in ('object_alpha_material_policy','transparent_object_alpha','solid_object_alpha','material_aware_object_alpha')]
        asset=np.full((8,8,3),42,np.uint8);mask=np.full((8,8),210,np.uint8);policies=[];centers=[]
        for processor in (first,second,first):
            adjusted,stats=processor.material_aware_object_alpha(asset,mask);policies.append(stats['object_alpha_material_policy']);centers.append(int(adjusted[4,4]));self.assertEqual(adjusted.shape,mask.shape)
        self.assertEqual(policies,['transparent','opaque','transparent']);self.assertEqual(centers,[210,255,210]);self.assertEqual(transparent_policy.call_count,2);solid_policy.assert_called_once_with(None,None)
        for poison in poisons:poison.assert_not_called()

if __name__=='__main__':unittest.main()
