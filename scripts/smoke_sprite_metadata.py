"""Draft original sprite-metadata contracts; tiny synthetic arrays only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock,patch
import numpy as np
sys.path.insert(0,str(Path.cwd()))
class SpriteMetadataContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='sprite-metadata-')))
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
    def test_family_aliases_unknown_and_blank(self):
        self.assertEqual([self.api.canonical_pose_family_name(x) for x in ('SIDE',' top_view ','cap','custom','',None)],['lying','upright','upright','custom',None,None])
    def test_physical_defaults_falsy_negative_and_error(self):
        self.replace('DEFAULT_OBJECT_SIZE_MM',new={'length_mm':11,'width_mm':22,'height_mm':33})
        self.assertEqual(self.api.object_physical_size_mm(None),(11.0,22.0,33.0))
        self.assertEqual(self.api.object_physical_size_mm({'length_mm':0,'width_mm':-2,'height_mm':'4'}),(11.0,-2.0,4.0))
        with self.assertRaises(ValueError):self.api.object_physical_size_mm({'length_mm':'bad'})
    def test_top_view_alias_precedence_and_ratio_boundary(self):
        self.assertTrue(self.api.pose_family_is_top_view('standing',[1000,1]));self.assertFalse(self.api.pose_family_is_top_view('flat',[10,10]))
        self.assertTrue(self.api.pose_family_is_top_view('unknown',[134,100]));self.assertFalse(self.api.pose_family_is_top_view('unknown',[135,100]));self.assertFalse(self.api.pose_family_is_top_view('unknown',None))
    def test_long_short_clamps_and_invalid_resets_both(self):
        result=self.api.source_object_long_short_metadata([4,8]);self.assertEqual((result['source_long_edge_axis'],result['source_long_side_px'],result['source_short_side_px']),('height',8,4));self.assertEqual(result['source_long_short_ratio'],2.0)
        self.assertEqual(self.api.source_object_long_short_metadata([0,0])['source_long_edge_axis'],'width')
        result=self.api.source_object_long_short_metadata([4,'bad']);self.assertEqual([result['source_visible_width_px'],result['source_visible_height_px']],[1,1])
    def test_long_short_orientation_helpers(self):
        self.assertEqual(self.api.oriented_long_short_pair_for_source([2,4],9.0,3.0),[3.0,9.0]);self.assertEqual(self.api.oriented_long_short_pair_for_source([4,4],9.0,3.0),[9.0,3.0])
        self.assertEqual(self.api.source_long_short_oriented_px(9,3,' HEIGHT '),[3,9]);self.assertEqual(self.api.source_long_short_oriented_px(9,3,None),[9,3])
    def test_footprint_elongated_alias_and_axis(self):
        self.replace('MM_TO_PREVIEW_PX',new=2.0);self.replace('SOURCE_ASPECT_ELONGATED_MIN_RATIO',new=1.35)
        result=self.api.pose_render_footprint_metadata('lying',[100,200],{'length_mm':100,'width_mm':20,'height_mm':30})
        self.assertEqual(result['render_footprint_mm'],[50.0,100.0]);self.assertEqual(result['render_footprint_px'],[100,200]);self.assertIs(result['render_size_hint_px'],result['render_footprint_px']);self.assertTrue(result['render_source_aspect_preserved'])
    def test_footprint_shared_top_and_side_branches(self):
        self.replace('MM_TO_PREVIEW_PX',new=2.0);self.replace('SOURCE_ASPECT_ELONGATED_MIN_RATIO',new=1.35)
        shared=self.api.pose_render_footprint_metadata('upright',[100,100],{'length_mm':60,'width_mm':20,'height_mm':30})
        self.assertEqual(shared['render_scale_basis'],'shared_length_width_physical_footprint');self.assertEqual(shared['render_footprint_px'],[120,60])
        top=self.api.pose_render_footprint_metadata('upright',[100,100],{'length_mm':90,'width_mm':20,'height_mm':30});self.assertEqual(top['render_footprint_px'],[60,60])
        side=self.api.pose_render_footprint_metadata('lying',[100,100],{'length_mm':90,'width_mm':20,'height_mm':30});self.assertEqual(side['render_footprint_px'],[43,180]);self.assertFalse(side['render_source_aspect_preserved'])
    def test_median_filters_aliases_shape_and_bad_values(self):
        assets=[{'pose_family':'flat','source_object_size_px':[10,20]},{'source_pose_family':'side','source_object_size_px':[30,40]},{'pose_family':'lying','source_object_size_px':['bad',4]},{'pose_family':'lying','source_object_size_px':(1,100)},{'pose_family':'upright','source_object_size_px':[100,200]}]
        self.assertEqual(self.api.median_source_major_axis_px(assets,'lying'),30.0);self.assertIsNone(self.api.median_source_major_axis_px([], 'lying'))
    def test_scale_correction_invalid_physical_interval_and_fallback(self):
        self.replace('UPRIGHT_SCALE_CORRECTION_MIN_RATIO',new=1.01);self.replace('UPRIGHT_SCALE_CORRECTION_MAX_RATIO',new=3.25);self.replace('UPRIGHT_SCALE_VISUAL_ADJUSTMENT',new=0.8)
        med=self.replace('median_source_major_axis_px',side_effect=[100.0,50.0]);result=self.api.upright_scale_correction_for_assets([],{'length_mm':100,'width_mm':20,'height_mm':20})
        self.assertEqual(result['upright_scale_correction'],1.6);self.assertEqual(result['upright_scale_correction_source_dimensions']['physical_ratio_min'],1.01);self.assertFalse(result['upright_scale_correction_clamped'])
        med.side_effect=[None,None];result=self.api.upright_scale_correction_for_assets([],{'length_mm':10,'width_mm':20,'height_mm':20});self.assertEqual(result['upright_scale_correction'],1.01);self.assertEqual(result['upright_scale_correction_raw'],0.5);self.assertTrue(result['upright_scale_correction_clamped'])
    def test_apply_scale_preserves_skips_and_aliases(self):
        dimensions={};correction={'upright_scale_correction':2.0,'upright_scale_correction_raw':2.5,'upright_scale_correction_source_dimensions':dimensions,'upright_scale_correction_physical_ratio':3.0,'upright_scale_correction_basis':'test'}
        self.replace('upright_scale_correction_for_assets',return_value=correction)
        shared={'pose_family':'top','render_footprint_px':[20,30],'render_scale_basis':'source_visible_long_short_aspect'};scaled={'pose_family':'upright','render_footprint_px':[10,20]};lying={'pose_family':'lying','upright_scale_correction':7};bad={'pose_family':'upright','render_footprint_px':['bad',2]}
        self.api.apply_upright_scale_correction_metadata([shared,scaled,lying,bad],None)
        self.assertEqual(shared['render_footprint_px'],[20,30]);self.assertEqual(shared['upright_scale_correction'],1.0);self.assertIs(shared['render_footprint_px'],shared['render_size_hint_px']);self.assertIs(shared['upright_scale_correction_source_dimensions'],dimensions)
        self.assertEqual(scaled['render_footprint_px'],[20,40]);self.assertIs(scaled['render_footprint_px_after_correction'],scaled['render_footprint_px']);self.assertEqual(lying['upright_scale_correction'],7);self.assertNotIn('upright_scale_correction',bad)
    def test_visible_shape_metadata_precedence_and_fallback(self):
        image=self.stack.enter_context(patch.object(self.api.cv2,'imread',side_effect=AssertionError('unexpected image read')))
        with patch.object(self.api.Path,'__new__',side_effect=AssertionError('unexpected Path construction')) as construct, patch.object(self.api.Path,'exists',side_effect=AssertionError('unexpected exists')) as exists:
            self.assertEqual(self.api.asset_visible_shape_px({'visible_width_px':8,'visible_height_px':4,'canonical_visible_width_px':9,'canonical_visible_height_px':5}),(8,4))
            self.assertEqual(self.api.asset_visible_shape_px({'visible_width_px':'bad','canonical_visible_width_px':9,'canonical_visible_height_px':5}),(9,5))
            self.assertEqual(self.api.asset_visible_shape_px({'normalized_bbox_xyxy':[2,3,10,9]}),(8,6))
            construct.assert_not_called();exists.assert_not_called();image.assert_not_called()
        missing=str(self.root/'absent.png');self.assertEqual(self.api.asset_visible_shape_px({'path':missing,'source_object_size_px':[4,7]}),(4,7));self.assertIsNone(self.api.asset_visible_shape_px({'path':missing,'source_object_size_px':['bad',7]}))
    def test_visible_shape_alpha_file_and_decode_fallback(self):
        path=self.root/'synthetic.png';path.write_bytes(b'private synthetic placeholder')
        image=np.zeros((8,10,4),np.uint8);image[2:6,3:8,3]=255
        decode=self.stack.enter_context(patch.object(self.api.cv2,'imread',return_value=image))
        self.assertEqual(self.api.asset_visible_shape_px({'path':str(path),'source_object_size_px':[2,3]}),(5,4));decode.return_value=None
        self.assertEqual(self.api.asset_visible_shape_px({'path':str(path),'source_object_size_px':[2,3]}),(2,3))
    def test_laying_reference_and_source_axis_override(self):
        lying={'pose_family':'flat','visible_width_px':8,'visible_height_px':4,'render_footprint_px':[20,50]};top={'pose_family':'top','visible_width_px':2,'visible_height_px':9,'render_footprint_px':[30,60]};source={'pose_family':'top','render_footprint_px':[70,40],'render_scale_basis':'source_visible_long_short_aspect','source_long_edge_axis':'height'}
        self.api.apply_laying_standard_render_size_hints([lying,top,source]);self.assertEqual(lying['render_footprint_px'],[50,20]);self.assertEqual(top['render_footprint_px'],[60,30]);self.assertEqual(source['render_footprint_px'],[40,70]);self.assertEqual(top['render_laying_standard_reference_visible_size_px'],[8.0,4.0]);self.assertIs(top['render_footprint_px'],top['render_size_hint_px'])
    def test_laying_no_shapes_is_noop(self):
        self.replace('asset_visible_shape_px',return_value=None);asset={'pose_family':'lying','render_footprint_px':[3,4]};before=dict(asset);self.api.apply_laying_standard_render_size_hints([asset]);self.assertEqual(asset,before)
    def test_sprite_render_hint_and_fallback_precedence(self):
        physical=self.replace('physical_render_size_px',return_value=(3,4));footprint=self.replace('pose_render_footprint_metadata',return_value={'render_footprint_px':[31,42]})
        self.assertEqual(self.api.sprite_render_size_px({}, {'render_size_hint_px':[90,80]},'text'),(3,4));physical.assert_called_once()
        self.assertEqual(self.api.sprite_render_size_px({}, {'render_size_hint_px':[1,2]},'object'),(16,16));footprint.assert_not_called()
        item={'physical_size':{}};self.assertEqual(self.api.sprite_render_size_px(item, {'render_size_hint_px':['bad',2],'width':8,'height':9,'pose_family':'lying'},'object'),(31,42));self.assertEqual(footprint.call_args.args[:2],('lying',[8,9]));self.assertIs(footprint.call_args.args[2],item['physical_size'])
    def test_canvas_primary_invalid_does_not_fall_through(self):
        self.assertEqual(self.api.canonical_sprite_canvas_size_px({'canonical_asset_dimensions_px':[0,-2]}),(1,1));self.assertEqual(self.api.canonical_sprite_canvas_size_px({'canonical_canvas_size_px':[4,5]}),(4,5));self.assertIsNone(self.api.canonical_sprite_canvas_size_px({'canonical_asset_dimensions_px':['bad',2],'canonical_canvas_size_px':[4,5]}))

    def test_footprint_elongation_boundary_and_minimum_pixels(self):
        self.replace('MM_TO_PREVIEW_PX',new=0.01);self.replace('SOURCE_ASPECT_ELONGATED_MIN_RATIO',new=1.35)
        size={'length_mm':100,'width_mm':20,'height_mm':20}
        boundary=self.api.pose_render_footprint_metadata('lying',[135,100],size)
        below=self.api.pose_render_footprint_metadata('lying',[134,100],size)
        self.assertEqual(boundary['render_scale_basis'],'source_visible_long_short_aspect');self.assertEqual(boundary['render_footprint_px'],[16,16]);self.assertEqual(below['render_scale_basis'],'side_major_axis_length_mm')
    def test_visible_shape_decoder_exception_propagates(self):
        path=self.root/'decoder-error.png';path.write_bytes(b'private synthetic placeholder')
        decode=self.stack.enter_context(patch.object(self.api.cv2,'imread',side_effect=RuntimeError('decode sentinel')))
        with self.assertRaisesRegex(RuntimeError,'decode sentinel'):self.api.asset_visible_shape_px({'path':str(path),'source_object_size_px':[4,5]})
        decode.assert_called_once()
    def test_laying_all_assets_fallback_and_tie_height(self):
        asset={'pose_family':'upright','visible_width_px':12,'visible_height_px':12,'render_footprint_px':[50,20]}
        self.api.apply_laying_standard_render_size_hints([asset]);self.assertEqual(asset['render_long_edge_axis'],'height');self.assertEqual(asset['render_footprint_px'],[20,50]);self.assertEqual(asset['render_laying_standard_reference_visible_size_px'],[12.0,12.0])

    def test_scale_all_three_bypass_bases(self):
        dimensions={};correction={'upright_scale_correction':2.0,'upright_scale_correction_raw':2.5,'upright_scale_correction_source_dimensions':dimensions,'upright_scale_correction_physical_ratio':3.0,'upright_scale_correction_basis':'test'}
        self.replace('upright_scale_correction_for_assets',return_value=correction)
        for basis in ('top_view_length_width_physical_footprint','shared_length_width_physical_footprint','source_visible_long_short_aspect'):
            with self.subTest(basis=basis):
                asset={'pose_family':'upright','render_footprint_px':[20,30],'render_scale_basis':basis}
                self.api.apply_upright_scale_correction_metadata([asset],None)
                self.assertEqual(asset['render_scale_basis'],basis);self.assertEqual(asset['render_footprint_px'],[20,30]);self.assertEqual(asset['upright_scale_visual_adjustment'],1.0);self.assertEqual(asset['upright_scale_correction_basis'],'source_visible_long_short_aspect');self.assertIs(asset['render_footprint_px'],asset['render_footprint_px_after_correction']);self.assertIs(asset['upright_scale_correction_source_dimensions'],dimensions)
    def test_scale_partial_state_when_second_family_lookup_fails(self):
        correction={'upright_scale_correction':2.0,'upright_scale_correction_basis':'test'}
        self.replace('upright_scale_correction_for_assets',return_value=correction);error=RuntimeError('second family')
        family=self.replace('canonical_pose_family_name',side_effect=['upright',error])
        first={'pose_family':'upright','render_footprint_px':[20,30]};second={'pose_family':'upright','render_footprint_px':[40,50]};before=dict(second)
        with self.assertRaises(RuntimeError) as caught:self.api.apply_upright_scale_correction_metadata([first,second],None)
        self.assertIs(caught.exception,error);self.assertEqual(family.call_count,2);self.assertEqual(first['render_footprint_px'],[40,60]);self.assertEqual(second,before);self.assertIs(second['render_footprint_px'],before['render_footprint_px'])
    def test_laying_partial_state_when_second_orientation_fails(self):
        error=RuntimeError('second orientation');orient=self.replace('source_long_short_oriented_px',side_effect=[[9,3],error])
        self.replace('asset_visible_shape_px',return_value=(8,4))
        first={'pose_family':'lying','render_footprint_px':[3,9],'render_scale_basis':'source_visible_long_short_aspect'};second={'pose_family':'lying','render_footprint_px':[4,10],'render_scale_basis':'source_visible_long_short_aspect'};before=dict(second)
        with self.assertRaises(RuntimeError) as caught:self.api.apply_laying_standard_render_size_hints([first,second])
        self.assertIs(caught.exception,error);self.assertEqual(orient.call_count,2);self.assertEqual(first['render_footprint_px'],[9,3]);self.assertEqual(second,before);self.assertIs(second['render_footprint_px'],before['render_footprint_px'])

    def test_physical_defaults_refresh_between_field_reads(self):
        self.replace('DEFAULT_OBJECT_SIZE_MM',new={'length_mm':11,'width_mm':22,'height_mm':33});api=self.api
        class ChangingSize(dict):
            def get(self,key,default=None):
                if key=='width_mm':api.DEFAULT_OBJECT_SIZE_MM={'length_mm':77,'width_mm':88,'height_mm':99}
                return 0
        self.assertEqual(self.api.object_physical_size_mm(ChangingSize(marker=True)),(11.0,88.0,99.0))
    def test_scale_refreshes_median_between_families(self):
        new=Mock(return_value=20.0);api=self.api
        def lying(*args):
            api.median_source_major_axis_px=new
            return 100.0
        old=self.replace('median_source_major_axis_px',side_effect=lying)
        result=self.api.upright_scale_correction_for_assets([],{'length_mm':100,'width_mm':20,'height_mm':20})
        old.assert_called_once();new.assert_called_once();self.assertEqual(new.call_args.args[1],'upright');self.assertEqual(result['upright_scale_correction_raw'],5.0)
    def test_render_footprint_callee_selected_before_item_argument(self):
        old=self.replace('pose_render_footprint_metadata',return_value={'render_footprint_px':[31,42]});new=Mock(return_value={'render_footprint_px':[99,88]});api=self.api
        class ChangingItem(dict):
            def get(self,key,default=None):
                if key=='physical_size':api.pose_render_footprint_metadata=new
                return super().get(key,default)
        self.assertEqual(self.api.sprite_render_size_px(ChangingItem(physical_size={}),{'source_object_size_px':[8,9]},'object'),(31,42));old.assert_called_once();new.assert_not_called()
    def test_visible_bounds_selected_after_decoder(self):
        path=self.root/'late-bounds.png';path.write_bytes(b'private synthetic placeholder');image=np.zeros((10,10,4),np.uint8)
        old=self.replace('alpha_bbox',return_value=[0,0,1,1]);new=Mock(return_value=[1,2,6,8]);api=self.api
        def decode(*args):
            api.alpha_bbox=new
            return image
        self.stack.enter_context(patch.object(self.api.cv2,'imread',side_effect=decode))
        self.assertEqual(self.api.asset_visible_shape_px({'path':str(path)}),(5,6));old.assert_not_called();new.assert_called_once();self.assertTrue(np.shares_memory(new.call_args.args[0],image))

    def independent_metadata_services(self, second=False):
        from local_inspection_service.accessories import sprite_metadata_ports as ports, sprite_metadata_values as values
        from local_inspection_service.accessories.sprite_footprint import SpriteFootprintMetadata
        from local_inspection_service.accessories.sprite_scale import SpriteScaleMetadata
        from local_inspection_service.accessories.sprite_render_metadata import SpriteRenderMetadata
        from local_inspection_service.accessories.mask_geometry import alpha_bbox
        defaults={'length_mm':60.0,'width_mm':30.0,'height_mm':30.0} if second else {'length_mm':100.0,'width_mm':20.0,'height_mm':20.0}
        footprint=SpriteFootprintMetadata(
            ports.SpritePhysicalPolicy(defaults=lambda:defaults,elongated_min=lambda:1.35,pixels_per_mm=lambda:3.0 if second else 2.0),
            ports.SpriteFootprintMetadataOperations(family=lambda:values.canonical_pose_family_name,physical=lambda:footprint.object_physical_size_mm,source=lambda:values.source_object_long_short_metadata,orient=lambda:footprint.oriented_long_short_pair_for_source,top_view=lambda:footprint.pose_family_is_top_view))
        scale=SpriteScaleMetadata(
            ports.SpriteScalePolicy(minimum=lambda:1.01,maximum=lambda:3.25,visual=lambda:0.9 if second else 0.8),
            ports.SpriteScaleOperations(family=lambda:values.canonical_pose_family_name,median=lambda:scale.median_source_major_axis_px,physical=lambda:footprint.object_physical_size_mm,correction=lambda:scale.upright_scale_correction_for_assets))
        image=np.zeros((5,6,4) if second else (3,4,4),np.uint8);image[:,:,3]=255;decode=Mock(return_value=image)
        physical=Mock(return_value=(70,80) if second else (7,8))
        render=SpriteRenderMetadata(
            ports.SpriteRenderOperations(bounds=lambda:alpha_bbox,family=lambda:values.canonical_pose_family_name,visible=lambda:render.asset_visible_shape_px,orient=lambda:values.source_long_short_oriented_px,footprint=lambda:footprint.pose_render_footprint_metadata,physical=lambda:physical),
            ports.SpriteImageReads(path=lambda:Path,decode=lambda:decode,unchanged_mode=lambda:-1))
        return footprint,scale,render,decode,physical
    def test_metadata_constructors_do_not_read_capabilities(self):
        from local_inspection_service.accessories import sprite_metadata_ports as ports
        from local_inspection_service.accessories.sprite_footprint import SpriteFootprintMetadata
        from local_inspection_service.accessories.sprite_scale import SpriteScaleMetadata
        from local_inspection_service.accessories.sprite_render_metadata import SpriteRenderMetadata
        forbidden=Mock(side_effect=AssertionError('eager capability read'))
        def group(kind):return kind(**{name:forbidden for name in kind.__dataclass_fields__})
        footprint=SpriteFootprintMetadata(group(ports.SpritePhysicalPolicy),group(ports.SpriteFootprintMetadataOperations))
        scale=SpriteScaleMetadata(group(ports.SpriteScalePolicy),group(ports.SpriteScaleOperations))
        render=SpriteRenderMetadata(group(ports.SpriteRenderOperations),group(ports.SpriteImageReads))
        self.assertIsInstance(footprint,SpriteFootprintMetadata);self.assertIsInstance(scale,SpriteScaleMetadata);self.assertIsInstance(render,SpriteRenderMetadata);forbidden.assert_not_called()
    def test_independent_metadata_first_second_first(self):
        first=self.independent_metadata_services();second=self.independent_metadata_services(second=True)
        path=self.root/'independent-metadata.png';path.write_bytes(b'private synthetic placeholder')
        names=('canonical_pose_family_name','object_physical_size_mm','pose_family_is_top_view','source_object_long_short_metadata','oriented_long_short_pair_for_source','source_long_short_oriented_px','pose_render_footprint_metadata','median_source_major_axis_px','upright_scale_correction_for_assets','apply_upright_scale_correction_metadata','asset_visible_shape_px','apply_laying_standard_render_size_hints','sprite_render_size_px','canonical_sprite_canvas_size_px','physical_render_size_px','alpha_bbox','Path')
        poisons=[];footprints=[];ratios=[];shapes=[];texts=[]
        with ExitStack() as stack:
            for name in names:poisons.append(stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('root dependency forbidden'))))
            for footprint,scale,render,decode,physical in (first,second,first):
                footprints.append(footprint.pose_render_footprint_metadata('upright',[100,100],None)['render_footprint_px'])
                assets=[{'pose_family':'lying','source_object_size_px':[100,10]},{'pose_family':'upright','source_object_size_px':[50,10]}]
                ratios.append(scale.upright_scale_correction_for_assets(assets,None)['upright_scale_correction'])
                shapes.append(render.asset_visible_shape_px({'path':str(path)}));texts.append(render.sprite_render_size_px({},None,'text'))
                self.assertEqual(render.sprite_render_size_px({},{'pose_family':'upright','source_object_size_px':[100,100]},'object'),tuple(footprints[-1]))
                self.assertEqual(footprint.oriented_long_short_pair_for_source([2,4],9.0,3.0),[3.0,9.0])
        for poison in poisons:poison.assert_not_called()
        self.assertEqual(footprints,[[40,40],[180,90],[40,40]]);self.assertEqual(ratios,[1.6,1.8,1.6]);self.assertEqual(shapes,[(4,3),(6,5),(4,3)]);self.assertEqual(texts,[(7,8),(70,80),(7,8)])
        self.assertEqual(first[3].call_count,2);self.assertEqual(second[3].call_count,1);self.assertEqual(first[4].call_count,2);self.assertEqual(second[4].call_count,1)

if __name__=='__main__':unittest.main()
