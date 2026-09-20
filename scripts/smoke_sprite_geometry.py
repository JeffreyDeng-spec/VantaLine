"""Draft original sprite-geometry contracts; tiny synthetic arrays only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock,patch
import numpy as np
sys.path.insert(0,str(Path.cwd()))
class SpriteGeometryContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='sprite-geometry-')))
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
    def test_angle_wrap_and_vertical_boundary(self):
        self.assertEqual([self.api.normalize_angle_180(x) for x in (0,90,-90,180,270,-180)],[0.0,90.0,90.0,0.0,90.0,0.0])
        self.assertAlmostEqual(self.api.normalize_angle_180(-89.998),-89.998)
    def test_bbox_empty_strict_threshold_and_exclusive_end(self):
        mask=np.zeros((6,8),np.uint8);self.assertEqual(self.api.alpha_bbox(mask),[0,0,0,0]);mask[1:4,2:6]=8
        self.assertEqual(self.api.alpha_bbox(mask),[0,0,0,0]);self.assertEqual(self.api.alpha_bbox(mask,7),[2,1,6,4])
    def test_edge_statistics_count_corners_twice(self):
        mask=np.array([[1,2],[3,4]],np.uint8)
        self.assertEqual(self.api.alpha_edge_max(mask),4);self.assertEqual(self.api.alpha_edge_stats(mask),{'max':4,'nonzero_px':8,'mean':2.5})
        empty=np.zeros((0,0),np.uint8);self.assertEqual(self.api.alpha_edge_max(empty),0);self.assertEqual(self.api.alpha_edge_stats(empty),{'max':0,'nonzero_px':0,'mean':0.0})
    def test_component_threshold_exact24_and_strict12(self):
        mask=np.zeros((30,40),np.uint8);mask[2:6,2:8]=13;mask[20:24,20:26]=12
        self.assertEqual(self.api.alpha_component_count(mask),1);mask[2,2]=0;self.assertEqual(self.api.alpha_component_count(mask),0)
        self.assertEqual(self.api.alpha_component_count(np.zeros((0,0),np.uint8)),0)
    def test_margin_shapes_values_and_empty_aliases(self):
        asset=np.ones((2,3,3),np.uint8);mask=np.full((2,3),50,np.uint8);a,m=self.api.add_sprite_safety_margin(asset,mask,2)
        self.assertEqual(a.shape,(6,7,3));self.assertEqual(m.shape,(6,7));self.assertEqual(int(m.sum()),300);self.assertEqual(int(m[0].sum()),0)
        empty=np.zeros((0,0),np.uint8);a,m=self.api.add_sprite_safety_margin(asset,empty);self.assertIs(a,asset);self.assertIs(m,empty)
    def test_trim_threshold_padding_and_copies(self):
        asset=np.ones((20,30,3),np.uint8);mask=np.zeros((20,30),np.uint8);mask[7:10,8:12]=8
        a,m=self.api.trim_masked_asset(asset,mask);self.assertIs(a,asset);self.assertIs(m,mask)
        mask[7:10,8:12]=9;a,m=self.api.trim_masked_asset(asset,mask,pad=2)
        self.assertEqual(a.shape,(7,8,3));self.assertEqual(m.shape,(7,8));self.assertFalse(np.shares_memory(a,asset));self.assertFalse(np.shares_memory(m,mask))
    def test_major_axis_small_horizontal_vertical(self):
        mask=np.zeros((20,40),np.uint8);mask[3,2:25]=255;self.assertEqual(self.api.masked_major_axis_angle(mask),(0.0,1.0))
        mask[3,25]=255;angle,ratio=self.api.masked_major_axis_angle(mask);self.assertEqual(angle,0.0);self.assertGreater(ratio,1.0)
        vertical=mask.T.copy();angle,ratio=self.api.masked_major_axis_angle(vertical);self.assertEqual(angle,90.0);self.assertGreater(ratio,1.0)
    def test_rotate_tiny_angle_pads_then_trims(self):
        asset=np.ones((4,6,3),np.uint8);mask=np.ones((4,6),np.uint8);padded=np.ones((24,26,3),np.uint8);pmask=np.ones((24,26),np.uint8)
        margin=self.replace('add_sprite_safety_margin',return_value=(padded,pmask));trim=self.replace('trim_masked_asset',return_value=(asset,mask))
        result=self.api.rotate_masked_asset(asset,mask,0.049);self.assertIs(result[0],asset);self.assertEqual(margin.call_args.args[2],10);self.assertIs(trim.call_args.args[0],padded);self.assertEqual(trim.call_args.kwargs,{'pad':10})
    def test_rotate_exact_threshold_runs_affine(self):
        asset=np.ones((4,6,3),np.uint8);mask=np.full((4,6),255,np.uint8)
        warp=self.stack.enter_context(patch.object(self.api.cv2,'warpAffine',wraps=self.api.cv2.warpAffine))
        self.api.rotate_masked_asset(asset,mask,0.05);self.assertEqual(warp.call_count,2);self.assertTrue(all(c.kwargs['flags']==self.api.cv2.INTER_LINEAR for c in warp.call_args_list))
    def test_upright_ratio_boundary_and_metadata(self):
        asset=np.ones((10,20,3),np.uint8);mask=np.ones((10,20),np.uint8)
        trim=self.replace('trim_masked_asset',return_value=(asset,mask));axis=self.replace('masked_major_axis_angle',return_value=(20.12345,1.18));self.replace('add_sprite_safety_margin',return_value=(asset,mask));rotate=self.replace('rotate_masked_asset',return_value=(asset,mask))
        a,m,meta=self.api.normalize_sprite_upright(asset,mask);self.assertIs(a,asset);self.assertIs(m,mask);self.assertEqual(trim.call_args.kwargs,{'pad':8});self.assertAlmostEqual(rotate.call_args.args[2],-69.87655)
        self.assertEqual(meta['rotation_degrees'],-69.877);self.assertEqual(meta['source_restore_rotation_degrees'],69.877);self.assertEqual(meta['pre_normalized_asset_size_px'],[20,10]);self.assertEqual(meta['pre_rotation_safety_margin_px'],18)
        axis.return_value=(20.12345,1.1799);self.api.normalize_sprite_upright(asset,mask);self.assertEqual(rotate.call_args.args[2],0.0)
    def test_visible_size_clamps_reversed_bounds(self):
        bounds=self.replace('alpha_bbox',return_value=[9,8,4,2]);self.assertEqual(self.api.visible_mask_size_px(np.zeros((1,1),np.uint8)),[0,0]);bounds.assert_called_once()
    def test_resize_empty_preserves_alias_and_reads_visible(self):
        asset=np.zeros((0,0,3),np.uint8);mask=np.zeros((0,0),np.uint8);visible=self.replace('visible_mask_size_px',return_value=[0,0])
        a,m,meta=self.api.resize_masked_asset_to_visible_footprint(asset,mask,(0,-2),True)
        self.assertIs(a,asset);self.assertIs(m,mask);visible.assert_called_once();self.assertEqual(meta['render_box_px'],[1,1]);self.assertIsNone(meta['render_scale_x']);self.assertFalse(meta['non_uniform_scaling_applied'])
    def test_resize_anisotropic_and_preserved_aspect(self):
        asset=np.ones((10,20,3),np.uint8);mask=np.zeros((10,20),np.uint8);mask[3:7,5:15]=255
        a,m,meta=self.api.resize_masked_asset_to_visible_footprint(asset,mask,(20,12))
        self.assertEqual(a.shape,(30,40,3));self.assertEqual(m.shape,(30,40));self.assertEqual(meta['source_visible_footprint_px'],[10,4]);self.assertEqual(meta['render_scale_x'],2.0);self.assertEqual(meta['render_scale_y'],3.0);self.assertTrue(meta['non_uniform_scaling_applied'])
        a,m,meta=self.api.resize_masked_asset_to_visible_footprint(asset,mask,(20,12),True)
        self.assertEqual(a.shape,(20,40,3));self.assertEqual(meta['render_scale_y'],2.0);self.assertFalse(meta['non_uniform_scaling_applied'])

    def test_resize_interpolation_downscale_and_same_size(self):
        asset=np.ones((20,30,3),np.uint8);mask=np.full((20,30),255,np.uint8)
        resize=self.stack.enter_context(patch.object(self.api.cv2,'resize',wraps=self.api.cv2.resize))
        self.api.resize_masked_asset_to_visible_footprint(asset,mask,(15,10))
        self.assertEqual([c.kwargs['interpolation'] for c in resize.call_args_list],[self.api.cv2.INTER_AREA,self.api.cv2.INTER_LINEAR])
        resize.reset_mock();self.api.resize_masked_asset_to_visible_footprint(asset,mask,(30,20))
        self.assertEqual([c.kwargs['interpolation'] for c in resize.call_args_list],[self.api.cv2.INTER_CUBIC,self.api.cv2.INTER_LINEAR])
    def test_component_area_scales_above_minimum(self):
        mask=np.zeros((500,1000),np.uint8);mask[2:7,2:10]=255
        self.assertEqual(self.api.alpha_component_count(mask),1)
        mask[2,2]=0;self.assertEqual(self.api.alpha_component_count(mask),0)

    def test_upright_rotate_selected_after_margin_callback(self):
        asset=np.ones((10,20,3),np.uint8);mask=np.ones((10,20),np.uint8)
        old=self.replace('rotate_masked_asset',return_value=(asset,mask));new=Mock(return_value=(asset,mask))
        self.replace('trim_masked_asset',return_value=(asset,mask));self.replace('masked_major_axis_angle',return_value=(0.0,2.0))
        def margin(*args):
            self.api.rotate_masked_asset=new
            return asset,mask
        self.replace('add_sprite_safety_margin',side_effect=margin)
        self.api.normalize_sprite_upright(asset,mask)
        old.assert_not_called();new.assert_called_once();self.assertEqual(new.call_args.args[2],90.0)
    def test_resize_refreshes_visible_callback_after_image_resize(self):
        asset=np.ones((10,20,3),np.uint8);mask=np.ones((10,20),np.uint8)
        old=self.replace('visible_mask_size_px',return_value=[20,10]);new=Mock(return_value=[7,8]);original=self.api.cv2.resize
        def resize(*args,**kwargs):
            self.api.visible_mask_size_px=new
            return original(*args,**kwargs)
        self.stack.enter_context(patch.object(self.api.cv2,'resize',side_effect=resize))
        _,_,meta=self.api.resize_masked_asset_to_visible_footprint(asset,mask,(20,10))
        old.assert_called_once();new.assert_called_once();self.assertEqual(meta['source_visible_footprint_px'],[20,10]);self.assertEqual(meta['render_visible_footprint_px'],[7,8])
    def test_rotation_refreshes_trim_after_padding(self):
        asset=np.ones((4,6,3),np.uint8);mask=np.ones((4,6),np.uint8)
        old=self.replace('trim_masked_asset',return_value=(asset,mask));new=Mock(return_value=(asset,mask))
        def margin(*args):
            self.api.trim_masked_asset=new
            return asset,mask
        self.replace('add_sprite_safety_margin',side_effect=margin)
        self.api.rotate_masked_asset(asset,mask,0.0)
        old.assert_not_called();new.assert_called_once();self.assertEqual(new.call_args.kwargs,{'pad':10})

    def geometry_dependencies(self, *, second=False):
        from local_inspection_service.accessories.sprite_geometry_ports import SpriteTransformOperations,SpriteFootprintOperations
        from local_inspection_service.accessories.sprite_geometry import SpriteGeometry
        callbacks={
            'normalize':Mock(return_value=20.0 if second else 10.0),
            'axis':Mock(return_value=(25.0 if second else 15.0,2.0)),
            'rotate':Mock(side_effect=lambda a,m,angle:(a,m)),
            'trim':Mock(side_effect=lambda a,m,pad=4:(a,m)),
            'margin':Mock(side_effect=lambda a,m,margin=10:(a,m)),
            'bounds':Mock(return_value=[1,2,8,11] if second else [0,0,4,3]),
            'visible':Mock(return_value=[6,5] if second else [4,3]),
        }
        getters={k:(lambda callback=callback:callback) for k,callback in callbacks.items()}
        instance=SpriteGeometry(SpriteTransformOperations(**{k:getters[k] for k in ('normalize','axis','rotate','trim','margin')}),SpriteFootprintOperations(**{k:getters[k] for k in ('bounds','visible')}))
        return instance,callbacks
    def test_geometry_constructor_does_not_read_capabilities(self):
        from local_inspection_service.accessories.sprite_geometry_ports import SpriteTransformOperations,SpriteFootprintOperations
        from local_inspection_service.accessories.sprite_geometry import SpriteGeometry
        forbidden=Mock(side_effect=AssertionError('eager capability read'))
        service=SpriteGeometry(SpriteTransformOperations(**{k:forbidden for k in ('normalize','axis','rotate','trim','margin')}),SpriteFootprintOperations(bounds=forbidden,visible=forbidden))
        self.assertIsInstance(service,SpriteGeometry);forbidden.assert_not_called()
    def test_independent_geometry_first_second_first(self):
        first,first_calls=self.geometry_dependencies();second,second_calls=self.geometry_dependencies(second=True)
        names=('normalize_angle_180','masked_major_axis_angle','rotate_masked_asset','trim_masked_asset','add_sprite_safety_margin','alpha_bbox','visible_mask_size_px')
        poisons=[];metas=[];bounds=[]
        with ExitStack() as stack:
            for name in names:poisons.append(stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('root helper forbidden'))))
            for service,width,height in ((first,4,3),(second,6,5),(first,4,3)):
                asset=np.ones((height,width,3),np.uint8);mask=np.ones((height,width),np.uint8)
                a,m,meta=service.normalize_sprite_upright(asset,mask);self.assertIs(a,asset);self.assertIs(m,mask);metas.append(meta)
                bounds.append(service.visible_mask_size_px(mask))
                _,_,resize=service.resize_masked_asset_to_visible_footprint(asset,mask,(width,height))
                self.assertEqual(resize['source_visible_footprint_px'],[width,height]);self.assertEqual(resize['render_scale_x'],1.0)
        for poison in poisons:poison.assert_not_called()
        self.assertEqual([m['rotation_degrees'] for m in metas],[10.0,20.0,10.0]);self.assertEqual(bounds,[[4,3],[7,9],[4,3]])
        for name in ('normalize','axis','rotate','trim','margin','bounds'):
            self.assertEqual(first_calls[name].call_count,2);self.assertEqual(second_calls[name].call_count,1)
        self.assertEqual(first_calls['visible'].call_count,4);self.assertEqual(second_calls['visible'].call_count,2)

if __name__=='__main__':unittest.main()
