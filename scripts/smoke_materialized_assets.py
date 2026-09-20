"""Offline contracts for materialized accessory assets and readiness."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock,patch,call
sys.path.insert(0,str(Path.cwd()))
class MaterializedAssetContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='materialized-assets-')))
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
    def file(self,name):
        path=self.root/name;path.touch();return path
    def sprite_setup(self):
        self.replace('resolve_service_path',side_effect=lambda value:Path(value))
        upright=self.replace('apply_upright_scale_correction_metadata');laying=self.replace('apply_laying_standard_render_size_hints')
        footprint=self.replace('pose_render_footprint_metadata',return_value={});top=self.replace('pose_family_is_top_view',return_value=False)
        return upright,laying,footprint,top
    def test_sprite_filters_kind_existence_and_suffix(self):
        upright,laying,footprint,top=self.sprite_setup();png=self.file('filter.PNG');jpg=self.file('filter.jpg');assets=[{'kind':'other'},{'kind':'clean_object_sprite','path':str(self.root/'absent.png')},{'kind':'clean_object_sprite','path':str(jpg)},{'kind':'clean_object_sprite','path':str(png),'width':4,'height':2}]
        result=self.api.clean_sprite_assets({'normalized_assets':assets});self.assertEqual(len(result),1);self.assertIs(result[0],assets[-1]);self.assertEqual(result[0]['path'],str(png));upright.assert_called_once_with(result,None);laying.assert_called_once_with(result)
    def test_sprite_populates_metadata_preserving_aliases(self):
        upright,laying,footprint,top=self.sprite_setup();path=self.file('metadata.png');size={'length_mm':8};render=[9,4];footprint.return_value={'render_footprint_px':render};asset={'kind':'clean_object_sprite','path':path,'width':6,'height':3,'pose_position':'left'}
        result=self.api.clean_sprite_assets({'normalized_assets':[asset],'physical_size':size});self.assertIs(result[0],asset);self.assertIs(asset['physical_size_mm'],size);self.assertIs(asset['render_size_hint_px'],render);self.assertEqual(asset['source_object_size_px'],[6,3]);self.assertEqual(asset['source_image_size_px'],[6,3]);self.assertEqual((asset['source_image_width'],asset['source_image_height']),(6,3));self.assertEqual((asset['source_pose_family'],asset['pose_family'],asset['source_position']),('lying','lying','left'));self.assertEqual(asset['task_id'],'legacy_clean_sprite');footprint.assert_called_once_with('lying',[6,3],size)
    def test_sprite_existing_false_dimensions_are_not_overwritten(self):
        import numpy as np
        self.sprite_setup();path=self.file('false.png');asset={'kind':'clean_object_sprite','path':str(path),'width':0,'height':None};decode=self.stack.enter_context(patch.object(self.api.cv2,'imread',return_value=np.zeros((7,9,4),dtype=np.uint8)))
        self.api.clean_sprite_assets({'normalized_assets':[asset]});self.assertEqual(asset['width'],0);self.assertIsNone(asset['height']);self.assertNotIn('source_object_size_px',asset);decode.assert_called_once_with(str(path),self.api.cv2.IMREAD_UNCHANGED)
    def test_sprite_missing_dimensions_are_filled_from_decode(self):
        import numpy as np
        self.sprite_setup();path=self.file('decode.png');asset={'kind':'clean_object_sprite','path':str(path)};decode=self.stack.enter_context(patch.object(self.api.cv2,'imread',return_value=np.zeros((7,9,4),dtype=np.uint8)))
        self.api.clean_sprite_assets({'normalized_assets':[asset]});self.assertEqual((asset['width'],asset['height']),(9,7));self.assertEqual(asset['source_object_size_px'],[9,7]);decode.assert_called_once()
    def test_sprite_none_decode_keeps_missing_dimensions(self):
        self.sprite_setup();path=self.file('none.png');asset={'kind':'clean_object_sprite','path':str(path)};self.stack.enter_context(patch.object(self.api.cv2,'imread',return_value=None));self.api.clean_sprite_assets({'normalized_assets':[asset]});self.assertNotIn('width',asset);self.assertNotIn('height',asset);self.assertEqual(asset['pose_position'],'center')
    def test_sprite_source_family_and_image_dimensions_precede_fallback(self):
        _,_,footprint,top=self.sprite_setup();path=self.file('source.png');asset={'kind':'clean_object_sprite','path':str(path),'width':6,'height':3,'source_pose_family':'top','source_image_width':40,'source_image_height':50,'task_id':'keep'}
        self.api.clean_sprite_assets({'normalized_assets':[asset]});self.assertEqual(asset['pose_family'],'top');self.assertEqual(asset['source_image_size_px'],[40,50]);self.assertEqual(asset['task_id'],'keep');top.assert_not_called()
    def test_sprite_final_adjustments_run_empty_and_in_order(self):
        upright,laying,_,_=self.sprite_setup();events=[];upright.side_effect=lambda assets,size:events.append(('upright',assets,size));laying.side_effect=lambda assets:events.append(('laying',assets));item={'physical_size':{}};result=self.api.clean_sprite_assets(item);self.assertEqual(result,[]);self.assertEqual([e[0] for e in events],['upright','laying']);self.assertIs(events[0][1],result);self.assertIs(events[1][1],result);self.assertIs(events[0][2],item['physical_size'])
    def test_sprite_decode_exception_preserves_partial_path_mutation(self):
        upright,laying,_,_=self.sprite_setup();path=self.file('error.png');asset={'kind':'clean_object_sprite','path':path};error=RuntimeError('decode');self.stack.enter_context(patch.object(self.api.cv2,'imread',side_effect=error))
        with self.assertRaises(RuntimeError) as seen:self.api.clean_sprite_assets({'normalized_assets':[asset]})
        self.assertIs(seen.exception,error);self.assertEqual(asset['path'],str(path));upright.assert_not_called();laying.assert_not_called()
    def test_metadata_presence_accepts_false_and_rejects_none(self):
        keys=['task_id', 'source_pose_collection_job_id', 'pose_family', 'source_pose_family', 'pose_position', 'source_position', 'original_orientation_angle', 'original_orientation_angle_degrees', 'rotation_degrees_applied', 'rotation_degrees_applied_to_upright', 'source_restore_rotation_degrees', 'normalized_axis_target_degrees', 'source_region_bbox_xyxy', 'source_object_bbox_xyxy', 'source_object_center_xy', 'source_object_size_px', 'normalized_asset_size_px', 'normalized_asset_dimensions_px', 'normalized_bbox_xyxy', 'pre_rotation_safety_margin_px', 'post_rotation_safety_margin_px', 'edge_alpha_max', 'edge_alpha_pass', 'mask_strategy', 'foreground_component_bbox_xyxy', 'removed_stray_component_count', 'removed_stray_component_area_px', 'alpha_edge_stats', 'transparent_alpha_policy', 'material_alpha_policy', 'object_alpha_material_policy', 'render_scale_basis', 'render_footprint_mm', 'render_footprint_px', 'canonical_width_px', 'canonical_height_px', 'physical_footprint_basis', 'source_long_side_px', 'source_short_side_px', 'source_long_edge_axis', 'source_short_edge_axis', 'source_long_short_ratio', 'source_length_width_rule']
        self.assertEqual(len(keys),43);asset=dict.fromkeys(keys,False);self.assertTrue(self.api.clean_sprite_metadata_complete(asset))
        for key in keys:
            missing=dict(asset);missing[key]=None;self.assertFalse(self.api.clean_sprite_metadata_complete(missing))
    def test_material_match_uses_normalized_policy_and_expected(self):
        item={};asset={'material_alpha_policy':'raw'};expected=self.replace('object_alpha_material_policy',return_value='transparent');normal=self.replace('normalize_object_alpha_material_policy',return_value='transparent');self.assertTrue(self.api.clean_sprite_material_policy_matches(item,asset));expected.assert_called_once_with(item);normal.assert_called_once_with('raw');normal.return_value='';self.assertFalse(self.api.clean_sprite_material_policy_matches(item,asset))
    def test_sprite_completeness_explicit_empty_skips_discovery(self):
        assets=self.replace('clean_sprite_assets',return_value=[{}]);metadata=self.replace('clean_sprite_metadata_complete',return_value=True);material=self.replace('clean_sprite_material_policy_matches',return_value=True);self.assertFalse(self.api.clean_sprites_policy_complete({},[]));assets.assert_not_called();metadata.assert_not_called();material.assert_not_called();self.assertTrue(self.api.clean_sprites_policy_complete({}));assets.assert_called_once_with({})
    def test_sprite_incomplete_metadata_short_circuits_material(self):
        metadata=self.replace('clean_sprite_metadata_complete',return_value=False);material=self.replace('clean_sprite_material_policy_matches',return_value=True);self.assertFalse(self.api.clean_sprites_policy_complete({},[{},{}]));metadata.assert_called_once_with({});material.assert_not_called()
    def test_text_filters_preserve_path_and_alias(self):
        import numpy as np
        path=self.file('text.JPG');asset={'kind':'canonical_text_image','path':'relative-text'};resolve=self.replace('resolve_service_path',return_value=path);self.replace('IMAGE_REFERENCE_SUFFIXES',new={'.jpg'});decode=self.stack.enter_context(patch.object(self.api.cv2,'imread',return_value=np.zeros((4,8,3),dtype=np.uint8)))
        result=self.api.canonical_text_assets({'normalized_assets':[{'kind':'other'},asset]});self.assertIs(result[0],asset);self.assertEqual(asset['path'],'relative-text');self.assertEqual((asset['width'],asset['height']),(8,4));resolve.assert_called_once_with('relative-text');decode.assert_called_once_with(str(path),self.api.cv2.IMREAD_COLOR)
    def test_text_none_and_false_dimensions_are_preserved(self):
        import numpy as np
        path=self.file('text-false.png');asset={'kind':'canonical_text_image','path':str(path),'width':0,'height':None};self.replace('resolve_service_path',return_value=path);self.replace('IMAGE_REFERENCE_SUFFIXES',new={'.png'});self.stack.enter_context(patch.object(self.api.cv2,'imread',return_value=np.zeros((4,8,3),dtype=np.uint8)));self.api.canonical_text_assets({'normalized_assets':[asset]});self.assertEqual(asset['width'],0);self.assertIsNone(asset['height'])
    def test_text_complete_manual_crop_and_explicit_empty_skip_discovery(self):
        discover=self.replace('canonical_text_assets',return_value=[{'width':3,'height':4}]);self.assertFalse(self.api.canonical_text_assets_complete({'manual_crop_required':True}));self.assertFalse(self.api.canonical_text_assets_complete({},[]));discover.assert_not_called();self.assertTrue(self.api.canonical_text_assets_complete({}));discover.assert_called_once_with({});self.assertFalse(self.api.canonical_text_assets_complete({},[{'width':0,'height':4}]))
    def test_text_detail_is_supplied_projection(self):
        discover=self.replace('canonical_text_assets',side_effect=AssertionError('not recomputed'));item={'ai_profile_status':{'status':'ready','source':'fixture','message':'ok'}};result=self.api.text_accessory_confirm_detail(item,[{},{}],False,True);self.assertEqual(result,{'message':'文字/文档素材未完成','canonical_text_asset_count':2,'canonical_text_assets_complete':False,'ai_profile_ready':True,'ai_profile_status':'ready','ai_profile_source':'fixture','ai_profile_message':'ok'});discover.assert_not_called();self.assertEqual(self.api.text_accessory_confirm_detail({'ai_profile_status':[]},[],True,False)['ai_profile_status'],'')

    def test_final_sprite_adjustment_reselects_laying_callback(self):
        upright,old,_,_=self.sprite_setup();new=Mock();upright.side_effect=lambda *args:setattr(self.api,'apply_laying_standard_render_size_hints',new);result=self.api.clean_sprite_assets({});old.assert_not_called();new.assert_called_once_with(result)
    def test_material_match_reselects_normalizer_after_expected_policy(self):
        old=self.replace('normalize_object_alpha_material_policy',return_value='wrong');new=Mock(return_value='opaque')
        def expected(item):self.api.normalize_object_alpha_material_policy=new;return 'opaque'
        self.replace('object_alpha_material_policy',side_effect=expected);self.assertTrue(self.api.clean_sprite_material_policy_matches({}, {'material_alpha_policy':'raw'}));old.assert_not_called();new.assert_called_once_with('raw')
    def test_sprite_readiness_reselects_material_after_metadata(self):
        old=self.replace('clean_sprite_material_policy_matches',return_value=False);new=Mock(return_value=True)
        def metadata(asset):self.api.clean_sprite_material_policy_matches=new;return True
        self.replace('clean_sprite_metadata_complete',side_effect=metadata);asset={};item={};self.assertTrue(self.api.clean_sprites_policy_complete(item,[asset]));old.assert_not_called();new.assert_called_once_with(item,asset)
    def test_text_suffix_policy_is_selected_after_exists(self):
        path=self.file('timing.JPG');self.replace('IMAGE_REFERENCE_SUFFIXES',new=set())
        class Resolved:
            suffix='.JPG'
            def exists(inner):self.api.IMAGE_REFERENCE_SUFFIXES={'.jpg'};return True
            def __str__(inner):return str(path)
        self.replace('resolve_service_path',return_value=Resolved());asset={'kind':'canonical_text_image','path':'source','width':1,'height':1};self.assertEqual(self.api.canonical_text_assets({'normalized_assets':[asset]}),[asset])
    def test_text_decode_callee_selected_before_path_string_conversion(self):
        import numpy as np
        events=[];late=Mock(return_value=np.zeros((1,1,3),dtype=np.uint8));image=np.zeros((4,8,3),dtype=np.uint8);first=self.stack.enter_context(patch.object(self.api.cv2,'imread',return_value=image))
        class Resolved:
            suffix='.png'
            def exists(inner):return True
            def __str__(inner):events.append('str');self.api.cv2.imread=late;return 'synthetic-path'
        self.replace('resolve_service_path',return_value=Resolved());self.replace('IMAGE_REFERENCE_SUFFIXES',new={'.png'});asset={'kind':'canonical_text_image','path':'source'};self.api.canonical_text_assets({'normalized_assets':[asset]});self.assertEqual((asset['width'],asset['height']),(8,4));self.assertEqual(events,['str']);first.assert_called_once_with('synthetic-path',self.api.cv2.IMREAD_COLOR);late.assert_not_called()

    def test_two_catalog_compositions_do_not_resolve_root_callbacks(self):
        from local_inspection_service.accessories.materialized_assets import SpriteAssetCatalog,TextAssetCatalog
        from local_inspection_service.accessories.materialized_asset_ports import MaterializedAssetPaths,SpriteCatalogPoseOperations,SpriteCatalogMaterialPolicy,SpriteCatalogReadiness,TextCatalogOperations
        names=['resolve_service_path','pose_family_is_top_view','pose_render_footprint_metadata','apply_upright_scale_correction_metadata','apply_laying_standard_render_size_hints','object_alpha_material_policy','normalize_object_alpha_material_policy','clean_sprite_assets','clean_sprite_metadata_complete','clean_sprite_material_policy_matches','canonical_text_assets','IMAGE_REFERENCE_SUFFIXES']
        poisoned={name:self.replace(name,new=Mock(side_effect=AssertionError('root '+name))) for name in names}
        def build(tag,size):
            path=self.file(tag+'.png');ops={'resolve':Mock(return_value=path),'top':Mock(return_value=False),'footprint':Mock(return_value={'render_footprint_px':[size,size]}),'upright':Mock(),'laying':Mock(),'expected':Mock(return_value=tag),'normalize':Mock(return_value=tag),'sprites':Mock(return_value=[{'id':tag}]),'metadata':Mock(return_value=True),'material':Mock(return_value=True),'suffixes':{'.png'},'text':Mock(return_value=[{'width':size,'height':size}])}
            getters={key:Mock(return_value=value) for key,value in ops.items()}
            paths=MaterializedAssetPaths(getters['resolve']);sprite=SpriteAssetCatalog(paths,SpriteCatalogPoseOperations(getters['top'],getters['footprint'],getters['upright'],getters['laying']),SpriteCatalogMaterialPolicy(getters['expected'],getters['normalize']),SpriteCatalogReadiness(getters['sprites'],getters['metadata'],getters['material']));text=TextAssetCatalog(paths,TextCatalogOperations(getters['suffixes'],getters['text']))
            for getter in getters.values():getter.assert_not_called()
            return sprite,text,ops,path,size
        a=build('catalog-a',7);b=build('catalog-b',11)
        for sprite,text,ops,path,size in (a,b,a):
            asset={'kind':'clean_object_sprite','path':'token','width':3,'height':2};item={'normalized_assets':[asset]};result=sprite.clean_sprite_assets(item)
            self.assertIs(result[0],asset);self.assertEqual(asset['path'],str(path));self.assertEqual(asset['render_size_hint_px'],[size,size]);self.assertTrue(sprite.clean_sprite_material_policy_matches(item,asset));self.assertTrue(sprite.clean_sprites_policy_complete(item))
            text_asset={'kind':'canonical_text_image','path':'text-token','width':3,'height':2};result=text.canonical_text_assets({'normalized_assets':[text_asset]});self.assertIs(result[0],text_asset);self.assertEqual(text_asset['path'],'text-token');self.assertTrue(text.canonical_text_assets_complete({}))
        self.assertEqual([a[2]['resolve'].call_count,b[2]['resolve'].call_count],[4,2]);self.assertEqual([a[2]['sprites'].call_count,b[2]['sprites'].call_count],[2,1]);self.assertEqual([a[2]['text'].call_count,b[2]['text'].call_count],[2,1])
        for poison in poisoned.values():poison.assert_not_called()

if __name__=='__main__':unittest.main()
