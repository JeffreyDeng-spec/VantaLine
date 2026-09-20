"""Offline original contracts for asset compositing."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock,patch,call
sys.path.insert(0,str(Path.cwd()))
class CompositingContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='compositing-')))
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
    def images(self):
        import numpy as np
        return np.full((40,40,3),100,dtype=np.uint8),np.full((3,5,3),50,dtype=np.uint8),np.full((3,5),255,dtype=np.uint8)
    def test_trim_uniform_and_small_component_return_original(self):
        import numpy as np
        image=np.full((40,40,3),255,dtype=np.uint8);self.assertIs(self.api.trim_rect_asset(image),image);image[18:22,18:22]=0;self.assertIs(self.api.trim_rect_asset(image),image)
    def test_trim_threshold_padding_and_copy(self):
        import numpy as np
        image=np.full((40,40,3),100,dtype=np.uint8);image[10:30,10:30]=92;self.assertIs(self.api.trim_rect_asset(image),image);image[10:30,10:30]=91;result=self.api.trim_rect_asset(image,pad=3);self.assertEqual(result.shape,(26,26,3));self.assertFalse(np.shares_memory(result,image));self.assertTrue(np.array_equal(result,image[7:33,7:33]))
    def test_long_axis_orientation_and_minimum(self):
        self.assertEqual(self.api.long_axis_unified_render_box(40,20,100,60),(100,50));self.assertEqual(self.api.long_axis_unified_render_box(20,40,60,100),(50,100));self.assertEqual(self.api.long_axis_unified_render_box(0,-1,0,-1),(16,16));self.assertEqual(self.api.long_axis_unified_render_box(40,1,64.5,1),(64,16))
    def test_masked_paste_returns_canvas_alias_and_visible_mask(self):
        import numpy as np
        canvas,asset,mask=self.images();result,visible=self.api.paste_masked_asset(canvas,asset,mask,(20,20),(10,6),0,trim_before_paste=False,return_visible_mask=True);self.assertIs(result,canvas);self.assertEqual(visible.shape,(40,40));self.assertEqual(visible.dtype,np.uint8);self.assertEqual(int(np.count_nonzero(visible)),60);self.assertTrue(np.all(canvas[visible>0]==50));self.assertTrue(np.all(canvas[visible==0]==100))
    def test_masked_paste_outside_keeps_canvas_and_zero_mask(self):
        import numpy as np
        canvas,asset,mask=self.images();before=canvas.copy();result,visible=self.api.paste_masked_asset(canvas,asset,mask,(-100,-100),(10,6),0,trim_before_paste=False,return_visible_mask=True);self.assertIs(result,canvas);self.assertFalse(visible.any());self.assertTrue(np.array_equal(canvas,before))
    def test_masked_paste_skip_resize_and_fractional_alpha(self):
        import numpy as np
        canvas,asset,mask=self.images();mask[:]=128;resize=self.stack.enter_context(patch.object(self.api.cv2,'resize',side_effect=AssertionError('resize forbidden')));result,visible=self.api.paste_masked_asset(canvas,asset,mask,(20,20),(100,100),0,trim_before_paste=False,return_visible_mask=True,resize_to_target=False);self.assertIs(result,canvas);self.assertEqual(int(np.count_nonzero(visible)),15);self.assertTrue(np.all(canvas[visible>0]==74));resize.assert_not_called()
    def test_masked_paste_trim_default_and_canvas_only(self):
        canvas,asset,mask=self.images();trim=self.replace('trim_masked_asset',return_value=(asset,mask));self.assertIs(self.api.paste_masked_asset(canvas,asset,mask,(20,20),(5,3),0),canvas);trim.assert_called_once_with(asset,mask)
    def test_physical_paste_metadata_alias_and_no_second_resize(self):
        canvas,asset,mask=self.images();before=[9,5];meta={'render_visible_footprint_px':before};resize=self.replace('resize_masked_asset_to_visible_footprint',return_value=(asset,mask,meta));paste=self.replace('paste_masked_asset',return_value=(canvas,mask));measure=self.replace('visible_mask_size_px',return_value=[7,3]);result=self.api.paste_physical_object_asset(canvas,asset,mask,(2,3),0,4.9,12,preserve_aspect_ratio=True);self.assertIs(result,meta);resize.assert_called_once_with(asset,mask,(1,4),True);paste.assert_called_once_with(canvas,asset,mask,(2,3),(1,4),12,trim_before_paste=True,return_visible_mask=True,resize_to_target=False);measure.assert_called_once_with(mask);self.assertIs(meta['pre_paste_visible_footprint_px'],before);self.assertEqual(meta['render_visible_footprint_px'],[7,3]);self.assertIs(meta['final_pasted_visible_footprint_px'],meta['render_visible_footprint_px']);self.assertFalse(meta['render_paste_rescaled']);self.assertIs(meta['_visible_mask_canvas'],mask)
    def test_physical_resize_refreshes_paste_and_paste_refreshes_measure(self):
        canvas,asset,mask=self.images();meta={};old_paste=self.replace('paste_masked_asset');old_measure=self.replace('visible_mask_size_px');late_measure=Mock(return_value=[2,1]);late_paste=Mock()
        def paste(*args,**kwargs):self.api.visible_mask_size_px=late_measure;return canvas,mask
        def resize(*args):self.api.paste_masked_asset=late_paste;return asset,mask,meta
        late_paste.side_effect=paste;self.replace('resize_masked_asset_to_visible_footprint',side_effect=resize);result=self.api.paste_physical_object_asset(canvas,asset,mask,(2,3),10,6,0);self.assertIs(result,meta);self.assertEqual(result['render_visible_footprint_px'],[2,1]);old_paste.assert_not_called();old_measure.assert_not_called();late_measure.assert_called_once_with(mask)
    def test_document_fit_preserves_aspect_and_full_mask(self):
        import numpy as np
        canvas,_,_=self.images();asset=np.full((4,8,3),50,dtype=np.uint8);result=self.api.paste_rectified_document_asset(canvas,asset,(20,20),(6,8),0);self.assertEqual(result['render_box_px'],[6,8]);self.assertEqual(result['render_visible_footprint_px'],[6,3]);self.assertEqual(result['source_visible_footprint_px'],[8,4]);self.assertEqual((result['render_scale_x'],result['render_scale_y']),(0.75,0.75));self.assertFalse(result['non_uniform_scaling_applied']);self.assertTrue(result['document_mask_crop_bypassed']);self.assertTrue(result['object_alpha_pipeline_bypassed']);self.assertTrue(result['document_full_asset_pasted']);self.assertEqual(int(np.count_nonzero(result['_visible_mask_canvas'])),18)
    def test_document_outside_keeps_canvas_with_metadata(self):
        import numpy as np
        canvas,asset,_=self.images();before=canvas.copy();result=self.api.paste_rectified_document_asset(canvas,asset,(-100,-100),(10,6),0);self.assertFalse(result['_visible_mask_canvas'].any());self.assertTrue(np.array_equal(canvas,before));self.assertEqual(result['render_visible_footprint_px'],[10,6])
    def test_rotated_rect_adapter_keeps_selection_before_mask_argument(self):
        canvas,asset,mask=self.images();trim=self.replace('trim_rect_asset',return_value=asset);old=self.replace('paste_masked_asset',return_value=canvas);late=Mock(return_value=canvas)
        def physical(value):self.api.paste_masked_asset=late;return mask
        make=self.replace('physical_mask_for_rect_asset',side_effect=physical);self.assertIs(self.api.paste_rotated_asset(canvas,asset,(4,5),(6,7),8),canvas);trim.assert_called_once_with(asset);make.assert_called_once_with(asset);old.assert_called_once_with(canvas,asset,mask,(4,5),(6,7),8);late.assert_not_called()

    def test_trim_exact_twenty_percent_area_is_accepted(self):
        import numpy as np
        image=np.full((40,40,3),100,dtype=np.uint8);stats=np.array([[0,0,40,40,1280],[5,5,20,16,320]],dtype=np.int32);parts=self.stack.enter_context(patch.object(self.api.cv2,'connectedComponentsWithStats',return_value=(2,None,stats,None)));result=self.api.trim_rect_asset(image);self.assertEqual(result.shape,(16,20,3));self.assertFalse(np.shares_memory(result,image));stats[1]=[5,5,29,11,319];self.assertIs(self.api.trim_rect_asset(image),image)
    def test_masked_paste_resize_uses_floor_and_original_interpolation(self):
        canvas,asset,mask=self.images();original=self.api.cv2.resize;resize=self.stack.enter_context(patch.object(self.api.cv2,'resize',wraps=original));self.api.paste_masked_asset(canvas,asset,mask,(20,20),(9,9),0,trim_before_paste=False);self.assertEqual(resize.call_count,2);self.assertEqual(resize.call_args_list[0].args[1],(9,5));self.assertEqual(resize.call_args_list[0].kwargs,{'interpolation':self.api.cv2.INTER_AREA});self.assertEqual(resize.call_args_list[1].args[1],(9,5));self.assertEqual(resize.call_args_list[1].kwargs,{'interpolation':self.api.cv2.INTER_LINEAR})
    def test_document_resize_interpolation_at_and_around_one(self):
        import numpy as np
        canvas,_,_=self.images();asset=np.full((4,8,3),50,dtype=np.uint8);original=self.api.cv2.resize;resize=self.stack.enter_context(patch.object(self.api.cv2,'resize',wraps=original))
        for size,mode in [((4,2),self.api.cv2.INTER_AREA),((8,4),self.api.cv2.INTER_CUBIC),((16,8),self.api.cv2.INTER_CUBIC)]:
            self.api.paste_rectified_document_asset(canvas,asset,(20,20),size,0);self.assertEqual(resize.call_args.kwargs,{'interpolation':mode});self.assertEqual(resize.call_args.args[1],size)
    def test_document_clamps_target_and_keeps_exact_policy_strings(self):
        canvas,asset,_=self.images();result=self.api.paste_rectified_document_asset(canvas,asset,(20,20),(0,-4),0);self.assertEqual(result['render_box_px'],[1,1]);self.assertEqual(result['render_visible_footprint_px'],[1,1]);self.assertEqual(result['document_asset_policy'],'full_rectified_asset_direct_physical_size');self.assertEqual(result['document_physical_scale_basis'],'paper_width_height_mm_to_background_px');self.assertEqual(result['render_resize_policy'],'document_rectified_fit_preserve_aspect_paper_box')
    def test_physical_metadata_get_refreshes_paste(self):
        canvas,asset,mask=self.images();old=self.replace('paste_masked_asset');late=Mock(return_value=(canvas,mask));api=self.api
        class Metadata(dict):
            def get(meta,key,default=None):api.paste_masked_asset=late;return super().get(key,default)
        meta=Metadata(render_visible_footprint_px=[5,3]);self.replace('resize_masked_asset_to_visible_footprint',return_value=(asset,mask,meta));self.replace('visible_mask_size_px',return_value=[5,3]);result=self.api.paste_physical_object_asset(canvas,asset,mask,(20,20),5,3,0);self.assertIs(result,meta);self.assertEqual(result['render_paste_resize_policy'],'trim_already_sized_physical_object_no_second_resize');old.assert_not_called();late.assert_called_once()
    def test_rotated_trim_refreshes_paste_and_mask_callbacks(self):
        canvas,asset,mask=self.images();old_paste=self.replace('paste_masked_asset');old_mask=self.replace('physical_mask_for_rect_asset');late_paste=Mock(return_value=canvas);late_mask=Mock(return_value=mask)
        def trim(value):self.api.paste_masked_asset=late_paste;self.api.physical_mask_for_rect_asset=late_mask;return asset
        self.replace('trim_rect_asset',side_effect=trim);self.assertIs(self.api.paste_rotated_asset(canvas,asset,(4,5),(6,7),8),canvas);old_paste.assert_not_called();old_mask.assert_not_called();late_mask.assert_called_once_with(asset);late_paste.assert_called_once_with(canvas,asset,mask,(4,5),(6,7),8)

    def test_rectangular_physical_mask_shape_dtype_and_independence(self):
        import numpy as np
        for asset in (np.zeros((3,5,4),dtype=np.float32),np.zeros((7,),dtype=np.uint8)):
            result=self.api.physical_mask_for_rect_asset(asset);self.assertEqual(result.shape,asset.shape[:2]);self.assertEqual(result.dtype,np.uint8);self.assertTrue(np.all(result==255));self.assertFalse(np.shares_memory(result,asset))

    def test_two_compositors_use_separate_dependencies_without_root(self):
        from local_inspection_service.accessories.compositing import AssetCompositor
        from local_inspection_service.accessories.compositing_ports import CompositionGeometry,CompositionOperations
        import numpy as np
        names=['trim_masked_asset','resize_masked_asset_to_visible_footprint','visible_mask_size_px','paste_masked_asset','trim_rect_asset','physical_mask_for_rect_asset'];poisons={name:self.replace(name,new=Mock(side_effect=AssertionError('root '+name))) for name in names}
        def build(tag,value):
            asset=np.full((3,5,3),value,dtype=np.uint8);mask=np.full((3,5),255,dtype=np.uint8);metadata={'tag':tag,'render_visible_footprint_px':[5,3]}
            def paste(canvas,*args,**kwargs):return (canvas,mask) if kwargs.get('return_visible_mask') else canvas
            ops={'trim':Mock(return_value=(asset,mask)),'resize':Mock(return_value=(asset,mask,metadata)),'visible':Mock(return_value=[value,value+1]),'paste':Mock(side_effect=paste),'rect':Mock(return_value=asset),'physical':Mock(return_value=mask)};getters={name:Mock(return_value=value) for name,value in ops.items()}
            service=AssetCompositor(CompositionGeometry(getters['trim'],getters['resize'],getters['visible']),CompositionOperations(getters['paste'],getters['rect'],getters['physical']))
            for getter in getters.values():getter.assert_not_called()
            return service,ops,asset,mask,metadata,tag,value
        a=build('compose-a',30);b=build('compose-b',70)
        for service,ops,asset,mask,metadata,tag,value in (a,b,a):
            canvas=np.zeros((32,32,3),dtype=np.uint8);pasted,visible=service.paste_masked_asset(canvas,asset,mask,(16,16),(5,3),0,return_visible_mask=True);self.assertIs(pasted,canvas);self.assertEqual(int(np.count_nonzero(visible)),15);self.assertTrue(np.all(canvas[visible>0]==value))
            result=service.paste_physical_object_asset(canvas,asset,mask,(16,16),5,3,0);self.assertIs(result,metadata);self.assertEqual(result['tag'],tag);self.assertEqual(result['render_visible_footprint_px'],[value,value+1]);self.assertIs(result['_visible_mask_canvas'],mask);self.assertFalse(result['render_paste_rescaled']);ops['resize'].assert_called_with(asset,mask,(5,3),False)
            self.assertIs(service.paste_rotated_asset(canvas,asset,(16,16),(5,3),0),canvas);ops['rect'].assert_called_with(asset);ops['physical'].assert_called_with(asset)
        self.assertEqual([a[1]['trim'].call_count,b[1]['trim'].call_count],[2,1]);self.assertEqual([a[1]['resize'].call_count,b[1]['resize'].call_count],[2,1]);self.assertEqual([a[1]['paste'].call_count,b[1]['paste'].call_count],[4,2]);self.assertEqual([a[1]['visible'].call_count,b[1]['visible'].call_count],[2,1])
        for poison in poisons.values():poison.assert_not_called()

if __name__=='__main__':unittest.main()
