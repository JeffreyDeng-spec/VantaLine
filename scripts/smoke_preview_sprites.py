"""Offline contracts for preview sprite decoding, selection and orientation."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock,patch,call
sys.path.insert(0,str(Path.cwd()))
class PreviewSpriteContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='preview-sprites-')))
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
    def arrays(self):
        import numpy as np
        return np.zeros((20,20,3),dtype=np.uint8),np.full((20,20),255,dtype=np.uint8)
    def loader_setup(self,sprites=None):
        import numpy as np
        self.asset,self.mask=self.arrays();self.item={'clean_sprite_preprocessed_at':44};self.sprites=sprites if sprites is not None else [{'path':'a.png','pose_family':'lying','source_position':'center','nested':{'keep':1}}];ops={}
        ops['assets']=self.replace('clean_sprite_assets',return_value=self.sprites);ops['preprocess']=self.replace('preprocess_object_clean_sprites',return_value=True);ops['canonical']=self.replace('canonical_pose_family_name',side_effect=lambda family:{'flat':'lying','side':'lying','top':'upright'}.get(family,family));ops['family']=self.replace('sprite_pose_family',side_effect=lambda asset:asset.get('pose_family',''));ops['top']=self.replace('pose_family_is_top_view',side_effect=lambda family:family=='upright');ops['filter']=self.replace('filter_complete_pose_candidates',side_effect=lambda assets,family:assets);self.replace('UPRIGHT_TOP_VIEW_SOURCE_POSITIONS',new=('center',));ops['load']=self.replace('load_clean_sprite',return_value=(self.asset,self.mask));ops['resolve']=self.replace('resolve_service_path',side_effect=lambda path:Path(path));ops['version']=self.replace('accessory_sprite_version',return_value='fixture-version');self.rng=Mock();self.rng.integers.return_value=0;return ops
    def test_decode_missing_or_wrong_shape_returns_none(self):
        import numpy as np
        decode=self.stack.enter_context(patch.object(self.api.cv2,'imread'))
        for image in (None,np.zeros((20,20),dtype=np.uint8),np.zeros((20,20,3),dtype=np.uint8)):
            decode.return_value=image;self.assertIsNone(self.api.load_clean_sprite(Path('synthetic.png')))
        self.assertEqual(decode.call_args,call('synthetic.png',self.api.cv2.IMREAD_UNCHANGED))
    def test_decode_alpha_count_boundary_and_strict_pixel_threshold(self):
        import numpy as np
        image=np.zeros((16,15,4),dtype=np.uint8);image[:,:,3]=9;decode=self.stack.enter_context(patch.object(self.api.cv2,'imread',return_value=image));self.assertIsNotNone(self.api.load_clean_sprite(Path('synthetic.png')));image[0,0,3]=8;self.assertIsNone(self.api.load_clean_sprite(Path('synthetic.png')))
    def test_decode_returns_independent_first_three_channels_and_alpha(self):
        import numpy as np
        image=np.full((16,15,5),9,dtype=np.uint8);image[:,:,0]=17;self.stack.enter_context(patch.object(self.api.cv2,'imread',return_value=image));asset,mask=self.api.load_clean_sprite(Path('synthetic.png'));self.assertEqual(asset.shape,(16,15,3));self.assertFalse(np.shares_memory(asset,image));self.assertFalse(np.shares_memory(mask,image));self.assertTrue(np.array_equal(asset,image[:,:,:3]));self.assertTrue(np.array_equal(mask,image[:,:,3]))
    def test_decode_failure_propagates_identity(self):
        error=RuntimeError('decode');self.stack.enter_context(patch.object(self.api.cv2,'imread',side_effect=error))
        with self.assertRaises(RuntimeError) as seen:self.api.load_clean_sprite(Path('synthetic.png'))
        self.assertIs(seen.exception,error)
    def test_orientation_bypass_preserves_aliases_and_requested_angle(self):
        asset,mask=self.arrays();rotate=self.replace('rotate_masked_asset')
        for value,top,expected in [(45,True,45.0),(0.0499,False,0.0),('bad',False,0.0),(None,False,0.0)]:
            meta={'source_restore_rotation_degrees':value};a,m,applied,remaining=self.api.restore_object_sprite_source_orientation_for_render(asset,mask,meta,top_view_pose=top);self.assertIs(a,asset);self.assertIs(m,mask);self.assertEqual(applied,0.0);self.assertEqual(remaining,expected);self.assertFalse(meta['source_orientation_restored_for_render'])
        rotate.assert_not_called()
    def test_orientation_exact_threshold_rotates_and_records_requested(self):
        asset,mask=self.arrays();new_asset,new_mask=self.arrays();rotate=self.replace('rotate_masked_asset',return_value=(new_asset,new_mask));meta={'source_restore_rotation_degrees':-0.05};a,m,applied,remaining=self.api.restore_object_sprite_source_orientation_for_render(asset,mask,meta,top_view_pose=False);self.assertIs(a,new_asset);self.assertIs(m,new_mask);self.assertEqual((applied,remaining),(-0.05,0.0));self.assertTrue(meta['source_orientation_restored_for_render']);self.assertEqual(meta['source_restore_rotation_degrees_requested'],-0.05);rotate.assert_called_once_with(asset,mask,-0.05)
    def test_orientation_overflow_is_not_swallowed(self):
        asset,mask=self.arrays();error=OverflowError('float');rotate=self.replace('rotate_masked_asset')
        class Value:
            def __float__(value):raise error
        with self.assertRaises(OverflowError) as seen:self.api.restore_object_sprite_source_orientation_for_render(asset,mask,{'source_restore_rotation_degrees':Value()},top_view_pose=False)
        self.assertIs(seen.exception,error);rotate.assert_not_called()
    def test_loader_returns_shallow_metadata_copy_and_indices(self):
        ops=self.loader_setup();asset,mask,meta=self.api.load_object_preview_sprite(self.item,self.rng);self.assertIs(asset,self.asset);self.assertIs(mask,self.mask);self.assertIsNot(meta,self.sprites[0]);self.assertIs(meta['nested'],self.sprites[0]['nested']);self.assertEqual((meta['sprite_index'],meta['sprite_path'],meta['clean_sprite_preprocessed_at'],meta['clean_sprite_version']),(1,'a.png',44,'fixture-version'));self.assertEqual(ops['assets'].call_count,2);ops['preprocess'].assert_not_called();self.rng.integers.assert_called_once_with(0,1)
    def test_loader_empty_inventory_preprocesses_without_ai_and_rereads(self):
        ops=self.loader_setup();ops['assets'].side_effect=[[],self.sprites,self.sprites];self.assertIsNotNone(self.api.load_object_preview_sprite(self.item,self.rng));ops['preprocess'].assert_called_once_with(self.item,allow_ai_cutout=False);self.assertEqual(ops['assets'].call_count,3)
    def test_loader_still_empty_skips_decode_and_rng(self):
        ops=self.loader_setup([]);self.assertIsNone(self.api.load_object_preview_sprite(self.item,self.rng));self.assertEqual(ops['assets'].call_count,2);ops['load'].assert_not_called();self.rng.integers.assert_not_called()
    def test_loader_family_alias_filter_and_unmatched_family_fallback(self):
        sprites=[{'path':'top.png','pose_family':'upright'},{'path':'side.png','pose_family':'side'}];ops=self.loader_setup(sprites);result=self.api.load_object_preview_sprite(self.item,self.rng,pose_family='lying');self.assertEqual(result[2]['sprite_path'],'side.png');self.assertEqual(result[2]['sprite_index'],2);result=self.api.load_object_preview_sprite(self.item,self.rng,pose_family='unknown');self.assertEqual(result[2]['sprite_path'],'top.png')
    def test_loader_top_view_requires_supported_source_position(self):
        ops=self.loader_setup([{'path':'top.png','pose_family':'upright','source_position':'unsupported'}]);self.assertIsNone(self.api.load_object_preview_sprite(self.item,self.rng,pose_family='upright'));ops['filter'].assert_not_called();ops['load'].assert_not_called();self.rng.integers.assert_not_called()
    def test_loader_explicit_source_missing_is_none_except_legacy_marker(self):
        ops=self.loader_setup();self.assertIsNone(self.api.load_object_preview_sprite(self.item,self.rng,source_position='left'));ops['load'].assert_not_called();self.sprites[0]['source_pose_collection_job_id']='legacy_clean_sprite';self.assertIsNotNone(self.api.load_object_preview_sprite(self.item,self.rng,source_position='left'));self.sprites[0]['source_pose_collection_job_id']='real_photo_direct_source';self.assertIsNotNone(self.api.load_object_preview_sprite(self.item,self.rng,source_position='left'))
    def test_loader_source_position_precedes_target_position(self):
        sprites=[{'path':'left.png','source_position':'left'},{'path':'right.png','source_position':'right'}];self.loader_setup(sprites);result=self.api.load_object_preview_sprite(self.item,self.rng,target_position='left',source_position='right');self.assertEqual(result[2]['sprite_path'],'right.png')
    def test_loader_empty_filter_falls_back_to_original_inventory(self):
        ops=self.loader_setup();ops['filter'].side_effect=None;ops['filter'].return_value=[];self.assertIsNotNone(self.api.load_object_preview_sprite(self.item,self.rng));ops['load'].assert_called_once_with(Path('a.png'))
    def test_loader_decode_none_skips_metadata_reread_and_version(self):
        ops=self.loader_setup();ops['load'].return_value=None;self.assertIsNone(self.api.load_object_preview_sprite(self.item,self.rng));ops['assets'].assert_called_once_with(self.item);ops['version'].assert_not_called()
    def test_loader_index_rereads_paths_and_keeps_none_when_missing(self):
        ops=self.loader_setup();ops['assets'].side_effect=[self.sprites,[{'path':'changed.png'}]];result=self.api.load_object_preview_sprite(self.item,self.rng);self.assertIsNone(result[2]['sprite_index']);self.assertEqual(result[2]['sprite_path'],'a.png')
    def test_loader_selects_decode_before_path_resolution(self):
        ops=self.loader_setup();late=Mock(return_value=None)
        def resolve(path):self.api.load_clean_sprite=late;return Path(path)
        ops['resolve'].side_effect=resolve;self.assertIsNotNone(self.api.load_object_preview_sprite(self.item,self.rng));ops['load'].assert_called_once_with(Path('a.png'));late.assert_not_called()

    def test_orientation_float_conversion_refreshes_rotation(self):
        asset,mask=self.arrays();new_asset,new_mask=self.arrays();old=self.replace('rotate_masked_asset');late=Mock(return_value=(new_asset,new_mask));api=self.api
        class Angle:
            def __float__(value):api.rotate_masked_asset=late;return 12.0
        result=self.api.restore_object_sprite_source_orientation_for_render(asset,mask,{'source_restore_rotation_degrees':Angle()},top_view_pose=False)
        self.assertIs(result[0],new_asset);self.assertEqual(result[2:],(12.0,0.0));old.assert_not_called();late.assert_called_once_with(asset,mask,12.0)
    def test_loader_preprocess_refreshes_inventory_callback(self):
        ops=self.loader_setup();ops['assets'].return_value=[];late=Mock(return_value=self.sprites)
        def preprocess(item,**kwargs):self.api.clean_sprite_assets=late
        ops['preprocess'].side_effect=preprocess;self.assertIsNotNone(self.api.load_object_preview_sprite(self.item,self.rng));ops['assets'].assert_called_once_with(self.item);self.assertEqual(late.call_count,2);ops['preprocess'].assert_called_once_with(self.item,allow_ai_cutout=False)
    def test_loader_nested_canonical_callee_precedes_family_argument(self):
        sprites=[{'path':'top.png','pose_family':'upright'},{'path':'side.png','pose_family':'side'}];ops=self.loader_setup(sprites);late=Mock(return_value='upright');seen=[]
        def family(asset):
            seen.append(asset['path'])
            if asset['path']=='side.png' and seen.count('side.png')==2:self.api.canonical_pose_family_name=late
            return asset['pose_family']
        ops['family'].side_effect=family;result=self.api.load_object_preview_sprite(self.item,self.rng,pose_family='lying');self.assertEqual(result[2]['sprite_path'],'side.png');self.assertEqual(ops['canonical'].call_args_list,[call('lying'),call('upright'),call('side')]);late.assert_not_called()
    def test_loader_position_get_refreshes_top_view_positions(self):
        api=self.api
        class Asset(dict):
            def get(asset,key,default=None):
                if key=='source_position':api.UPRIGHT_TOP_VIEW_SOURCE_POSITIONS=('center',)
                return super().get(key,default)
        ops=self.loader_setup([Asset(path='top.png',pose_family='upright',source_position='center')]);self.api.UPRIGHT_TOP_VIEW_SOURCE_POSITIONS=();result=self.api.load_object_preview_sprite(self.item,self.rng,pose_family='upright');self.assertIsNotNone(result);self.assertEqual(result[2]['sprite_path'],'top.png')
    def test_loader_copies_metadata_before_final_inventory_effects(self):
        ops=self.loader_setup();self.sprites[0]['copied']='before';calls=[]
        def assets(item):
            calls.append(item)
            if len(calls)==2:self.sprites[0]['copied']='after'
            return self.sprites
        ops['assets'].side_effect=assets;result=self.api.load_object_preview_sprite(self.item,self.rng);self.assertEqual(result[2]['copied'],'before');self.assertEqual(self.sprites[0]['copied'],'after');self.assertIs(result[2]['nested'],self.sprites[0]['nested']);self.assertEqual(len(calls),2)

    def test_independent_renderers_use_separate_capabilities_without_root(self):
        from local_inspection_service.accessories.preview_sprites import PreviewSpriteRenderer
        from local_inspection_service.accessories.preview_sprite_ports import PreviewSpriteInventory,PreviewSpritePoses,PreviewSpriteMedia,PreviewSpriteGeometry
        import numpy as np
        names=['clean_sprite_assets','preprocess_object_clean_sprites','accessory_sprite_version','canonical_pose_family_name','sprite_pose_family','pose_family_is_top_view','filter_complete_pose_candidates','UPRIGHT_TOP_VIEW_SOURCE_POSITIONS','resolve_service_path','load_clean_sprite','rotate_masked_asset']
        poisons={name:self.replace(name,new=Mock(side_effect=AssertionError('root '+name))) for name in names}
        def build(tag,value):
            asset=np.full((2,3,3),value,dtype=np.uint8);mask=np.full((2,3),255,dtype=np.uint8);rotated=asset.copy()+1;rotated_mask=mask.copy();sprites=[{'path':tag+'.png','pose_family':'upright','source_position':'center','source_restore_rotation_degrees':15}]
            ops={'assets':Mock(),'preprocess':Mock(return_value=True),'version':Mock(return_value=tag),'canonical':Mock(side_effect=lambda x:x),'family':Mock(return_value='upright'),'top_view':Mock(return_value=True),'complete':Mock(side_effect=lambda assets,family:assets),'positions':{'center'},'resolve':Mock(side_effect=lambda path:Path(path)),'decode':Mock(return_value=(asset,mask)),'rotate':Mock(return_value=(rotated,rotated_mask))}
            getters={name:Mock(return_value=value) for name,value in ops.items()}
            service=PreviewSpriteRenderer(PreviewSpriteInventory(getters['assets'],getters['preprocess'],getters['version']),PreviewSpritePoses(getters['canonical'],getters['family'],getters['top_view'],getters['complete'],getters['positions']),PreviewSpriteMedia(getters['resolve'],getters['decode']),PreviewSpriteGeometry(getters['rotate']))
            for getter in getters.values():getter.assert_not_called()
            return service,ops,sprites,asset,mask,rotated,rotated_mask,tag
        a=build('instance-a',3);b=build('instance-b',7)
        for service,ops,sprites,asset,mask,rotated,rotated_mask,tag in (a,b,a):
            ops['assets'].side_effect=[[],sprites,sprites];rng=Mock();rng.integers.return_value=0;item={'clean_sprite_preprocessed_at':9}
            loaded=service.load_object_preview_sprite(item,rng,pose_family='upright',source_position='center');self.assertIs(loaded[0],asset);self.assertIs(loaded[1],mask);self.assertEqual((loaded[2]['sprite_path'],loaded[2]['sprite_index'],loaded[2]['clean_sprite_version']),(tag+'.png',1,tag));rng.integers.assert_called_once_with(0,1)
            restored=service.restore_object_sprite_source_orientation_for_render(loaded[0],loaded[1],loaded[2],top_view_pose=False);self.assertIs(restored[0],rotated);self.assertIs(restored[1],rotated_mask);self.assertEqual(restored[2:],(15.0,0.0));self.assertTrue(loaded[2]['source_orientation_restored_for_render'])
            ops['preprocess'].assert_called_with(item,allow_ai_cutout=False);ops['decode'].assert_called_with(Path(tag+'.png'))
        self.assertEqual([a[1]['assets'].call_count,b[1]['assets'].call_count],[6,3]);self.assertEqual([a[1]['preprocess'].call_count,b[1]['preprocess'].call_count],[2,1]);self.assertEqual([a[1]['rotate'].call_count,b[1]['rotate'].call_count],[2,1])
        for poison in poisons.values():poison.assert_not_called()

if __name__=='__main__':unittest.main()
