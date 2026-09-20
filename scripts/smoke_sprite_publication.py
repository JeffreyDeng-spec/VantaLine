"""Draft original sprite-publication contracts; tiny synthetic arrays only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from itertools import chain, repeat
from contextlib import ExitStack
from unittest.mock import Mock,patch
import numpy as np
sys.path.insert(0,str(Path.cwd()))
class SpritePublicationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='sprite-publication-')))
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
    def writer_inputs(self, count=240):
        asset=np.zeros((20,20,3),np.uint8);mask=np.zeros((20,20),np.uint8);mask.flat[:count]=255
        self.replace('normalize_sprite_upright',side_effect=lambda a,m:(a,m,{'winner':'orientation'}))
        alpha=self.replace('material_aware_object_alpha',side_effect=lambda a,m,meta:(m,{'winner':'alpha'}))
        self.writer=self.stack.enter_context(patch.object(self.api.cv2,'imwrite',return_value=True))
        return asset,mask,alpha
    def test_writer_foreground_threshold_before_alpha(self):
        asset,mask,alpha=self.writer_inputs(239)
        self.assertIsNone(self.api.write_clean_sprite(self.root/'threshold.png',asset,mask));alpha.assert_not_called();self.writer.assert_not_called()
        mask.flat[239]=255
        self.assertIsNotNone(self.api.write_clean_sprite(self.root/'threshold.png',asset,mask));self.assertEqual(alpha.call_count,1);self.assertEqual(self.writer.call_count,1)
    def test_writer_edge_boundary(self):
        asset,mask,alpha=self.writer_inputs();edge=self.replace('alpha_edge_max',return_value=13)
        self.assertIsNone(self.api.write_clean_sprite(self.root/'edge.png',asset,mask));self.writer.assert_not_called();edge.return_value=12
        value=self.api.write_clean_sprite(self.root/'edge.png',asset,mask);self.assertIsNotNone(value);self.assertEqual(value['edge_alpha_max'],12);self.assertTrue(value['edge_alpha_pass'])
    def test_writer_merge_precedence_and_bbox_alias(self):
        asset,mask,alpha=self.writer_inputs();shared=[]
        value=self.api.write_clean_sprite(self.root/'merge.png',asset,mask,{'winner':'caller','custom':shared,'width':999})
        self.assertEqual(value['winner'],'orientation');self.assertEqual(value['width'],999);self.assertIs(value['custom'],shared);self.assertIs(value['normalized_bbox_xyxy'],value['foreground_component_bbox_xyxy']);self.assertEqual(value['post_rotation_safety_margin_px'],18)
    def test_writer_false_and_exception(self):
        asset,mask,alpha=self.writer_inputs();self.writer.return_value=False
        self.assertIsNone(self.api.write_clean_sprite(self.root/'false.png',asset,mask))
        failure=RuntimeError('synthetic writer');self.writer.side_effect=failure
        with self.assertRaises(RuntimeError) as seen:self.api.write_clean_sprite(self.root/'throw.png',asset,mask)
        self.assertIs(seen.exception,failure)
    def test_footprint_failure_occurs_after_write(self):
        asset,mask,alpha=self.writer_inputs();failure=RuntimeError('synthetic footprint')
        footprint=self.replace('pose_render_footprint_metadata',side_effect=failure)
        with self.assertRaises(RuntimeError) as seen:self.api.write_clean_sprite(self.root/'footprint.png',asset,mask,{'physical_size_mm':{},'pose_family':'lying','source_object_size_px':[3,4]})
        self.assertIs(seen.exception,failure);self.writer.assert_called_once();footprint.assert_called_once_with('lying',[3,4],{})
    def test_existing_complete_footprint_skips_projection(self):
        asset,mask,alpha=self.writer_inputs();footprint=self.replace('pose_render_footprint_metadata',side_effect=AssertionError('unexpected footprint'))
        value=self.api.write_clean_sprite(self.root/'complete.png',asset,mask,{'physical_size_mm':{},'render_footprint_px':[3,4],'render_footprint_mm':[5,6],'render_scale_basis':'existing'})
        self.assertEqual(value['render_scale_basis'],'existing');footprint.assert_not_called()
    def canvas_images(self, assets, images):
        self.replace('resolve_service_path',side_effect=lambda p:self.root/str(p))
        decode=self.stack.enter_context(patch.object(self.api.cv2,'imread',side_effect=images))
        writer=self.stack.enter_context(patch.object(self.api.cv2,'imwrite',return_value=True))
        return decode,writer
    def image(self,w,h):
        result=np.zeros((h+4,w+4,4),np.uint8);result[2:h+2,2:w+2,3]=255;return result
    def test_canvas_invalid_and_empty_image_path_updates(self):
        assets=[{'path':'missing'},{'path':'empty'}];decode,writer=self.canvas_images(assets,[None,np.zeros((4,4,4),np.uint8)])
        self.api.normalize_sprite_family_canvases(assets)
        self.assertEqual(assets[0],{'path':'missing'});self.assertEqual(assets[1],{'path':str(self.root/'empty')});self.assertEqual(decode.call_count,2);writer.assert_not_called()
    def test_canvas_all_pose_families_share_maximum(self):
        assets=[{'path':'lying','pose_family':'lying'},{'path':'upright','pose_family':'upright'}];decode,writer=self.canvas_images(assets,[self.image(10,6),self.image(8,20)])
        self.api.normalize_sprite_family_canvases(assets)
        self.assertEqual([a['canonical_visible_major_axis_px'] for a in assets],[20,20]);self.assertEqual(writer.call_count,2)
        for a in assets:self.assertTrue(a['canonical_all_pose_family_size_normalized']);self.assertTrue(a['edge_alpha_pass']);self.assertEqual(a['canonical_asset_dimensions_px'],a['canonical_canvas_size_px'])
    def test_canvas_false_write_still_updates_metadata(self):
        assets=[{'path':'false'}];decode,writer=self.canvas_images(assets,[self.image(10,6)]);writer.return_value=False
        self.api.normalize_sprite_family_canvases(assets)
        self.assertIn('canonical_family_width_normalized',assets[0]);self.assertTrue(assets[0]['canonical_family_width_normalized']);writer.assert_called_once()
    def test_canvas_later_write_failure_preserves_prior_update(self):
        assets=[{'path':'first'},{'path':'second'}];decode,writer=self.canvas_images(assets,[self.image(10,6),self.image(8,20)]);failure=RuntimeError('second writer');writer.side_effect=[True,failure]
        with self.assertRaises(RuntimeError) as seen:self.api.normalize_sprite_family_canvases(assets)
        self.assertIs(seen.exception,failure);self.assertTrue(assets[0]['canonical_all_pose_family_size_normalized']);self.assertEqual(assets[1],{'path':str(self.root/'second')});self.assertEqual(writer.call_count,2)
    def test_writer_encoded_alpha_and_path_argument(self):
        asset,mask,alpha=self.writer_inputs();asset[:,:,0]=17;asset[:,:,1]=29;asset[:,:,2]=43;path=self.root/'encoded.png'
        changed=np.full_like(mask,123);alpha.side_effect=lambda a,m,meta:(changed,{})
        value=self.api.write_clean_sprite(path,asset,mask)
        target,rgba=self.writer.call_args.args
        self.assertEqual(target,str(path));self.assertEqual(rgba.shape,(56,56,4));np.testing.assert_array_equal(rgba[18:38,18:38,3],changed);np.testing.assert_array_equal(rgba[18:38,18:38,:3],asset);self.assertEqual(int(rgba[:18,:,3].sum()),0);self.assertEqual(value['height'],56)
    def test_writer_normalization_precedes_empty_guard(self):
        asset,mask,alpha=self.writer_inputs();normal=self.replace('normalize_sprite_upright',return_value=(np.zeros((0,0,3),np.uint8),np.zeros((0,0),np.uint8),{}))
        with patch.object(Path,'mkdir') as mkdir,patch.object(self.api.cv2,'cvtColor') as convert:
            self.assertIsNone(self.api.write_clean_sprite(self.root/'empty.png',asset,mask));mkdir.assert_not_called();convert.assert_not_called()
        normal.assert_called_once_with(asset,mask);alpha.assert_not_called();self.writer.assert_not_called()
    def test_writer_alpha_callback_refresh_after_normalize(self):
        asset,mask,old=self.writer_inputs();new=Mock(return_value=(mask,{'new_alpha':True}))
        def normalize(a,m):self.api.material_aware_object_alpha=new;return a,m,{}
        self.replace('normalize_sprite_upright',side_effect=normalize)
        value=self.api.write_clean_sprite(self.root/'refresh.png',asset,mask)
        self.assertIn('new_alpha',value);self.assertTrue(value['new_alpha']);old.assert_not_called();new.assert_called_once_with(asset,mask,None)
    def test_canvas_decoder_error_preserves_pre_read_state(self):
        assets=[{'path':'first'},{'path':'second'}];failure=RuntimeError('decode');decode,writer=self.canvas_images(assets,[failure])
        with self.assertRaises(RuntimeError) as seen:self.api.normalize_sprite_family_canvases(assets)
        self.assertIs(seen.exception,failure);self.assertEqual(assets,[{'path':'first'},{'path':'second'}]);decode.assert_called_once();writer.assert_not_called()
    def test_canvas_three_resize_attempts_and_interpolations(self):
        assets=[{'path':'small'},{'path':'large'}];decode,writer=self.canvas_images(assets,[np.zeros((10,10,4),np.uint8),np.zeros((20,20,4),np.uint8)])
        self.replace('trim_masked_asset',side_effect=lambda a,m,pad:(a,m));self.replace('add_sprite_safety_margin',side_effect=lambda a,m,margin:(a,m))
        bounds=self.replace('alpha_bbox',side_effect=chain([[0,0,10,10],[0,0,20,20],[0,0,10,10],[0,0,10,10],[0,0,10,10],[0,0,10,10],[0,0,20,20],[0,0,20,20]],repeat([0,0,20,20])))
        resize=self.stack.enter_context(patch.object(self.api.cv2,'resize',wraps=self.api.cv2.resize))
        self.api.normalize_sprite_family_canvases(assets)
        self.assertEqual(resize.call_count,6);self.assertEqual([c.kwargs['interpolation'] for c in resize.call_args_list],[self.api.cv2.INTER_CUBIC,self.api.cv2.INTER_LINEAR]*3);self.assertEqual(assets[0]['width'],80);self.assertEqual(bounds.call_count,8)
    def test_canvas_shrink_uses_area_and_linear(self):
        assets=[{'path':'shrink'}];decode,writer=self.canvas_images(assets,[np.zeros((40,40,4),np.uint8)])
        self.replace('trim_masked_asset',side_effect=lambda a,m,pad:(a,m));self.replace('add_sprite_safety_margin',side_effect=lambda a,m,margin:(a,m))
        self.replace('alpha_bbox',side_effect=chain([[0,0,20,20],[0,0,40,40],[0,0,20,20],[0,0,20,20]],repeat([0,0,20,20])))
        resize=self.stack.enter_context(patch.object(self.api.cv2,'resize',wraps=self.api.cv2.resize))
        self.api.normalize_sprite_family_canvases(assets)
        self.assertEqual(resize.call_count,2);self.assertEqual([c.kwargs['interpolation'] for c in resize.call_args_list],[self.api.cv2.INTER_AREA,self.api.cv2.INTER_LINEAR]);self.assertEqual(assets[0]['width'],20)
    def test_canvas_empty_batch_performs_no_operations(self):
        names=('resolve_service_path','alpha_bbox','trim_masked_asset','add_sprite_safety_margin','alpha_edge_max','alpha_edge_stats')
        poisons=[self.replace(name,side_effect=AssertionError('empty operation')) for name in names]
        for name in ('imread','resize','cvtColor','imwrite'):poisons.append(self.stack.enter_context(patch.object(self.api.cv2,name,side_effect=AssertionError('empty codec'))))
        self.api.normalize_sprite_family_canvases([])
        for poison in poisons:poison.assert_not_called()
    def test_canvas_second_decode_failure_leaves_first_path_only(self):
        assets=[{'path':'first'},{'path':'second'}];failure=RuntimeError('second decode');decode,writer=self.canvas_images(assets,[self.image(10,6),failure])
        with self.assertRaises(RuntimeError) as seen:self.api.normalize_sprite_family_canvases(assets)
        self.assertIs(seen.exception,failure);self.assertEqual(assets,[{'path':str(self.root/'first')},{'path':'second'}]);self.assertEqual(decode.call_count,2);writer.assert_not_called()
    def test_canvas_postwrite_diagnostics_failure_before_update(self):
        for name in ('alpha_edge_max','alpha_edge_stats'):
            with self.subTest(name=name):
                assets=[{'path':name}];decode,writer=self.canvas_images(assets,[self.image(10,6)]);failure=RuntimeError(name)
                with patch.object(self.api,name,side_effect=failure):
                    with self.assertRaises(RuntimeError) as seen:self.api.normalize_sprite_family_canvases(assets)
                self.assertIs(seen.exception,failure);writer.assert_called_once();self.assertEqual(assets,[{'path':str(self.root/name)}])
    def test_canvas_writer_selected_before_path_argument(self):
        assets=[{'path':'timing'}];decode,old=self.canvas_images(assets,[self.image(10,6)]);new=Mock(return_value=True);calls=[]
        def resolve(value,*,for_write=False):
            calls.append(value)
            if len(calls)==2:self.api.cv2.imwrite=new
            return self.root/str(value)
        self.replace('resolve_service_path',side_effect=resolve)
        self.api.normalize_sprite_family_canvases(assets)
        old.assert_called_once();new.assert_not_called();self.assertEqual(len(calls),2)
    def test_writer_footprint_selected_before_last_metadata_argument(self):
        asset,mask,alpha=self.writer_inputs();old=self.replace('pose_render_footprint_metadata',return_value={'selected':'old'});new=Mock(return_value={'selected':'new'});api=self.api
        class Meta(dict):
            physical_reads=0
            def get(self,key,default=None):
                if key=='physical_size_mm':
                    self.physical_reads+=1
                    if self.physical_reads==2:api.pose_render_footprint_metadata=new
                return super().get(key,default)
        meta=Meta(physical_size_mm={},pose_family='lying',source_object_size_px=[3,4]);value=self.api.write_clean_sprite(self.root/'selection.png',asset,mask,meta)
        self.assertEqual(value['selected'],'old');old.assert_called_once_with('lying',[3,4],{});new.assert_not_called();self.assertEqual(meta.physical_reads,2)
    def test_canvas_writer_refreshed_for_next_asset(self):
        assets=[{'path':'first'},{'path':'second'}];decode,old=self.canvas_images(assets,[self.image(10,6),self.image(10,6)]);new=Mock(return_value=True)
        def write(*args):self.api.cv2.imwrite=new;return True
        old.side_effect=write;self.api.normalize_sprite_family_canvases(assets)
        old.assert_called_once();new.assert_called_once();self.assertTrue(all(a['canonical_all_pose_family_size_normalized'] for a in assets))
    def test_canvas_near_one_scale_does_not_resize(self):
        assets=[{'path':'tolerance'}];decode,writer=self.canvas_images(assets,[np.zeros((2,1005,4),np.uint8)])
        self.replace('trim_masked_asset',side_effect=lambda a,m,pad:(a,m));self.replace('add_sprite_safety_margin',side_effect=lambda a,m,margin:(a,m))
        self.replace('alpha_bbox',side_effect=chain([[0,0,1005,2],[0,0,1000,2],[0,0,1000,2]],repeat([0,0,1000,2])))
        resize=self.stack.enter_context(patch.object(self.api.cv2,'resize',wraps=self.api.cv2.resize))
        self.api.normalize_sprite_family_canvases(assets)
        resize.assert_not_called();writer.assert_called_once();self.assertEqual(assets[0]['canonical_visible_major_axis_px'],1005)
    def independent_publication_services(self, marker):
        from local_inspection_service.accessories import sprite_publication_ports as ports
        from local_inspection_service.accessories.sprite_artifact_writer import SpriteArtifactWriter
        from local_inspection_service.accessories.sprite_canvas_normalization import SpriteCanvasNormalizer
        from local_inspection_service.accessories.mask_geometry import alpha_bbox,alpha_edge_max,alpha_edge_stats,add_sprite_safety_margin,trim_masked_asset
        import cv2
        normalize=Mock(side_effect=lambda a,m:(a,m,{'owner':marker}))
        alpha=Mock(side_effect=lambda a,m,meta:(np.full_like(m,marker),{}));footprint=Mock(return_value={'render_footprint_px':[marker,marker+1]})
        write=Mock(return_value=True);convert=cv2.cvtColor
        encoder=ports.SpriteImageEncoder(convert=lambda:convert,bgra_mode=lambda:cv2.COLOR_BGR2BGRA,write=lambda:write)
        writer=SpriteArtifactWriter(ports.SpriteArtifactGeometry(normalize=lambda:normalize,margin=lambda:add_sprite_safety_margin,bounds=lambda:alpha_bbox,edge_max=lambda:alpha_edge_max,edge_stats=lambda:alpha_edge_stats),ports.SpriteArtifactMetadata(alpha=lambda:alpha,footprint=lambda:footprint),encoder)
        image=self.image(20,20);decode=Mock(return_value=image);resolve=Mock(side_effect=lambda value,**kwargs:self.root/str(value))
        canvas=SpriteCanvasNormalizer(ports.SpriteCanvasGeometry(trim=lambda:trim_masked_asset,margin=lambda:add_sprite_safety_margin,bounds=lambda:alpha_bbox,edge_max=lambda:alpha_edge_max,edge_stats=lambda:alpha_edge_stats),ports.SpriteCanvasImageReads(resolve=lambda:resolve,decode=lambda:decode,unchanged_mode=lambda:cv2.IMREAD_UNCHANGED),ports.SpriteResampling(resize=lambda:cv2.resize,cubic=lambda:cv2.INTER_CUBIC,area=lambda:cv2.INTER_AREA,linear=lambda:cv2.INTER_LINEAR),encoder)
        return writer,canvas,write,decode,normalize,alpha,footprint
    def test_publication_constructors_read_no_capabilities(self):
        from local_inspection_service.accessories import sprite_publication_ports as ports
        from local_inspection_service.accessories.sprite_artifact_writer import SpriteArtifactWriter
        from local_inspection_service.accessories.sprite_canvas_normalization import SpriteCanvasNormalizer
        forbidden=Mock(side_effect=AssertionError('eager dependency read'))
        def group(kind):return kind(**{key:forbidden for key in kind.__dataclass_fields__})
        writer=SpriteArtifactWriter(group(ports.SpriteArtifactGeometry),group(ports.SpriteArtifactMetadata),group(ports.SpriteImageEncoder))
        canvas=SpriteCanvasNormalizer(group(ports.SpriteCanvasGeometry),group(ports.SpriteCanvasImageReads),group(ports.SpriteResampling),group(ports.SpriteImageEncoder))
        self.assertIsInstance(writer,SpriteArtifactWriter);self.assertIsInstance(canvas,SpriteCanvasNormalizer);forbidden.assert_not_called()
    def test_independent_publication_first_second_first(self):
        first=self.independent_publication_services(101);second=self.independent_publication_services(201)
        names=('write_clean_sprite','normalize_sprite_family_canvases','normalize_sprite_upright','material_aware_object_alpha','add_sprite_safety_margin','alpha_bbox','alpha_edge_max','alpha_edge_stats','pose_render_footprint_metadata','resolve_service_path','trim_masked_asset')
        poisons=[self.replace(name,side_effect=AssertionError('root forbidden')) for name in names];owners=[]
        asset=np.full((20,20,3),37,np.uint8);mask=np.full((20,20),255,np.uint8)
        for group in (first,second,first):
            writer,canvas,write,decode,normalize,alpha,footprint=group
            result=writer.write_clean_sprite(self.root/'independent.png',asset,mask,{'physical_size_mm':{}});owners.append(result['owner'])
            self.assertEqual(result['render_footprint_px'],[result['owner'],result['owner']+1]);self.assertEqual(int(write.call_args.args[1][18,18,3]),result['owner'])
            assets=[{'path':'canvas.png'}];canvas.normalize_sprite_family_canvases(assets);self.assertTrue(assets[0]['canonical_all_pose_family_size_normalized']);self.assertEqual(assets[0]['canonical_visible_major_axis_px'],20)
        self.assertEqual(owners,[101,201,101]);self.assertEqual(first[2].call_count,4);self.assertEqual(second[2].call_count,2);self.assertEqual(first[3].call_count,2);self.assertEqual(second[3].call_count,1)
        for poison in poisons:poison.assert_not_called()

if __name__=='__main__':unittest.main()
