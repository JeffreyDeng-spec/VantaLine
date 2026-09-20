"""Draft original object preprocessing contracts; private synthetic fixtures only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch
import numpy as np
sys.path.insert(0,str(Path.cwd()))

class ObjectPreprocessingContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='object-preprocessing-')))
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
        self.directory=Path(self.stack.enter_context(tempfile.TemporaryDirectory(dir=self.root)))
        self.item={'created_at':7,'physical_size':{'width':2},'normalized_assets':[{'kind':'reference','id':'retained'}]}
        self.material=self.replace('accessory_material_type',return_value='rigid')
        self.alpha=self.replace('object_alpha_material_policy',return_value='opaque')
        self.jobs=self.replace('candidate_image_jobs',return_value=[])
        self.existing=self.replace('clean_sprite_assets',return_value=[])
        self.complete=self.replace('clean_sprites_policy_complete',return_value=True)
        self.uid=self.replace('accessory_uid',return_value='uid')
        self.replace('NORMALIZED_DIR',new=self.directory)
        self.paths=self.replace('accessory_image_paths',return_value=[])
        self.image=np.full((20,20,3),90,np.uint8);self.mask=np.full((20,20),255,np.uint8)
        self.read=self.stack.enter_context(patch.object(self.api.cv2,'imread',return_value=self.image))
        self.ai=self.replace('ai_background_cutout',return_value=None)
        self.generic=self.replace('object_cutout_from_image',return_value=None)
        self.components=self.replace('alpha_component_cutouts',return_value=[])
        self.usable=self.replace('usable_object_cutout',side_effect=lambda c,s:c)
        self.writer=self.replace('write_clean_sprite',side_effect=lambda p,a,m,metadata:{'kind':'clean_object_sprite','path':str(p),'metadata':metadata})
        self.events=[]
        self.normalize=self.replace('normalize_sprite_family_canvases',side_effect=lambda a:self.events.append(('normalize',len(a))))
        self.scale=self.replace('apply_upright_scale_correction_metadata',side_effect=lambda a,s:self.events.append(('scale',len(a))))
        self.laying=self.replace('apply_laying_standard_render_size_hints',side_effect=lambda a:self.events.append(('laying',len(a))))
        self.stack.enter_context(patch.object(self.api.time,'time',return_value=123.9))
    def replace(self,name,**kwargs):return self.stack.enter_context(patch.object(self.api,name,**kwargs))
    def build(self,**kwargs):return self.api.preprocess_object_clean_sprites(self.item,**kwargs)
    def test_text_returns_false_without_alpha_or_discovery(self):
        self.material.return_value='text';before=dict(self.item)
        self.assertFalse(self.build());self.assertEqual(self.item,before);self.alpha.assert_not_called();self.jobs.assert_not_called()
    def test_complete_existing_cache_skips_runtime(self):
        self.existing.return_value=[{'kind':'clean_object_sprite'}]
        self.assertFalse(self.build());self.uid.assert_not_called();self.read.assert_not_called();self.assertEqual(self.item['material_alpha_policy'],'opaque')
    def test_force_bypasses_cache_but_no_outputs_returns_false(self):
        self.existing.return_value=[{'path':'missing'}];self.read.return_value=None
        self.assertFalse(self.build(force=True));self.uid.assert_called_once();self.writer.assert_not_called();self.assertNotIn('clean_sprite_status',self.item)
    def test_no_sources_preserves_existing_state_except_alpha(self):
        self.item['clean_sprite_status']='old';before=dict(self.item)
        self.assertFalse(self.build());before['material_alpha_policy']='opaque';self.assertEqual(self.item,before);self.writer.assert_not_called()
    def test_ai_success_retains_other_assets_and_metadata_alias(self):
        self.paths.return_value=[self.directory/'source.png'];self.ai.return_value=(self.image,self.mask)
        self.assertTrue(self.build());self.generic.assert_not_called();self.writer.assert_called_once()
        self.assertEqual(self.item['clean_sprite_status'],'ready');self.assertEqual(self.item['clean_sprite_count'],1)
        self.assertEqual(self.item['normalized_assets'][0]['id'],'retained');self.assertEqual(self.item['normalized_assets'][1]['method'],'source_one_time_ai_cutout')
        self.assertIs(self.writer.call_args.args[3]['physical_size_mm'],self.item['physical_size']);self.assertEqual(self.events,[('normalize',1),('scale',1),('laying',1)])
        self.assertEqual(self.item['clean_sprite_preprocessed_at'],123)
    def test_disabled_ai_uses_generic(self):
        self.paths.return_value=[self.directory/'source.png'];self.generic.return_value=(self.image,self.mask)
        self.assertTrue(self.build(allow_ai_cutout=False));self.ai.assert_not_called();self.generic.assert_called_once();self.assertEqual(self.item['normalized_assets'][1]['method'],'source_lightweight_cutout')
    def test_generated_but_incomplete_returns_true_partial(self):
        self.paths.return_value=[self.directory/'source.png'];self.ai.return_value=(self.image,self.mask);self.complete.return_value=False
        self.assertTrue(self.build());self.assertEqual(self.item['clean_sprite_status'],'partial');self.assertEqual(self.complete.call_count,2)
    def test_fallback_full_image_after_rejected_cutouts(self):
        self.paths.return_value=[self.directory/'source.png']
        self.assertTrue(self.build());self.assertEqual(self.paths.call_count,2);self.assertEqual(self.item['normalized_assets'][1]['method'],'source_full_image_fallback')
        self.assertEqual(self.writer.call_args.args[3]['source_object_bbox_xyxy'],[0,0,20,20]);self.assertEqual(int(self.writer.call_args.args[2].sum()),20*20*255)
    def test_all_writes_fail_preserves_old_normalized_assets(self):
        self.paths.return_value=[self.directory/'source.png'];self.ai.return_value=(self.image,self.mask);self.writer.return_value=None;self.writer.side_effect=None
        old=self.item['normalized_assets'];self.assertFalse(self.build());self.assertIs(self.item['normalized_assets'],old);self.assertNotIn('clean_sprite_status',self.item);self.assertEqual(self.writer.call_count,2)
    def test_png_components_precede_ai_and_cap_before_postprocessing(self):
        self.paths.return_value=[self.directory/'source.png'];self.read.return_value=np.zeros((20,20,4),np.uint8)
        self.components.return_value=[(self.image,self.mask)]*20
        self.assertTrue(self.build());self.ai.assert_not_called();self.assertEqual(self.writer.call_count,20);self.assertEqual(self.item['clean_sprite_count'],18);self.assertEqual(self.events,[('normalize',18),('scale',18),('laying',18)])

    def pose_fixture(self):
        path=self.directory/'pose.png';path.write_bytes(b'synthetic path only')
        self.jobs.return_value=[{'output_path':str(path),'pose_family':'upright','job_id':'job','task_id':'task'}]
        self.replace('POSE_COLLECTION_GRID_POSITIONS',new=['center'])
        self.regions=self.replace('pose_collection_regions',return_value=[(0,0,20,20)])
        self.ai_bounded=self.replace('ai_background_cutout_with_bbox',return_value=None)
        self.green=self.replace('green_screen_object_cutout_with_bbox',return_value=None)
        self.footprint=self.replace('pose_render_footprint_metadata',return_value={'footprint':'yes'})
        return path
    def test_pose_full_cell_fallback_preserves_coordinates(self):
        path=self.pose_fixture()
        self.assertTrue(self.build());self.ai_bounded.assert_called_once();self.green.assert_called_once();self.paths.assert_not_called()
        asset=self.item['normalized_assets'][1];self.assertEqual(asset['method'],'pose_collection_full_cell_fallback')
        self.assertEqual(asset['metadata']['source_object_bbox_xyxy'],[0,0,20,20]);self.assertEqual(asset['metadata']['task_id'],'task');self.assertEqual(asset['metadata']['source_pose_collection'],str(path))
        self.assertEqual(self.item['clean_sprite_expected_count'],1);self.assertEqual(self.item['clean_sprite_failed_cells'],[])
    def test_pose_rejected_usable_still_writes_full_cell_directly(self):
        self.pose_fixture();self.usable.return_value=None;self.usable.side_effect=None
        self.assertTrue(self.build(allow_ai_cutout=False));self.ai_bounded.assert_not_called();self.writer.assert_called_once()
        self.assertTrue(self.writer.call_args.args[3]['pose_collection_full_cell_fallback']);self.assertEqual(self.item['clean_sprite_status'],'ready')
    def test_failed_pose_then_source_result_keeps_failed_cell_partial(self):
        pose=self.pose_fixture();self.paths.return_value=[pose,self.directory/'source.png']
        def writer(path,asset,mask,metadata):
            if metadata.get('source_pose_collection_job_id')=='job':return None
            return {'kind':'clean_object_sprite','metadata':metadata}
        self.writer.side_effect=writer;self.ai.return_value=(self.image,self.mask)
        self.assertTrue(self.build());self.assertEqual(self.item['clean_sprite_status'],'partial');self.assertEqual(len(self.item['clean_sprite_failed_cells']),1)
        failed=self.item['clean_sprite_failed_cells'][0];self.assertEqual(failed['reason'],'no usable object cutout');self.assertEqual(failed['pose_position'],'center');self.assertEqual(self.writer.call_count,3)
    def test_missing_and_intermediate_pose_jobs_do_not_inflate_expected_count(self):
        path=self.directory/'intermediate.png';path.write_bytes(b'not an image')
        self.jobs.return_value=[{'output_path':str(self.directory/'missing.png')},{'output_path':str(path),'intermediate':True}]
        self.paths.return_value=[self.directory/'source.png'];self.ai.return_value=(self.image,self.mask)
        self.assertTrue(self.build());self.assertEqual(self.item['clean_sprite_expected_count'],1)
    def test_legacy_alpha_rebuild_retains_source_metadata(self):
        self.existing.return_value=[{'path':str(self.directory/'old.png'),'source_pose_family':'upright','custom':'retained'}]
        self.complete.return_value=False;rgba=np.zeros((20,20,4),np.uint8);rgba[:,:,3]=255;self.read.return_value=rgba
        self.replace('alpha_bbox',return_value=[0,0,20,20]);self.replace('pose_render_footprint_metadata',return_value={})
        self.assertTrue(self.build());self.paths.assert_not_called();metadata=self.writer.call_args.args[3]
        self.assertEqual(metadata['custom'],'retained');self.assertEqual(metadata['task_id'],'legacy_clean_sprite');self.assertEqual(metadata['legacy_sprite_policy_rebuild_source_path'],str(self.directory/'old.png'))
        self.assertEqual(self.item['normalized_assets'][1]['method'],'legacy_clean_sprite_policy_rebuild');self.assertEqual(self.item['clean_sprite_status'],'partial')

    def test_pose_cleanup_offsets_and_removed_component_maxima(self):
        self.pose_fixture();self.read.return_value=np.full((40,40,3),90,np.uint8);self.regions.return_value=[(10,10,30,30)]
        asset=np.ones((10,10,3),np.uint8);alpha=np.full((10,10),255,np.uint8)
        self.ai_bounded.return_value=(asset,alpha,(5,5,15,15))
        focused=self.replace('filter_cutout_to_focus_cell',return_value=(asset,alpha,(5,5,15,15)))
        summary=self.replace('alpha_component_summary',side_effect=[(3,120),(1,100)])
        cleaned=alpha.copy();cleanup=self.replace('cleanup_crop_alpha_components',return_value=(cleaned,{'removed_stray_component_count':1,'removed_stray_component_area_px':5,'diagnostic':'kept'}))
        bounds=self.replace('alpha_bbox',return_value=[1,2,8,9])
        self.assertTrue(self.build());self.green.assert_not_called();self.assertEqual(summary.call_count,2)
        self.assertEqual(cleanup.call_args.args[2],(5.0,5.0));self.assertIs(cleanup.call_args.args[0],asset);self.assertIs(bounds.call_args.args[0],cleaned)
        metadata=self.writer.call_args.args[3];self.assertEqual(metadata['source_object_bbox_xyxy'],[16,17,23,24]);self.assertIs(metadata['physical_size_mm'],self.item['physical_size']);self.assertEqual(metadata['source_object_size_px'],[7,7])
        self.assertEqual(metadata['removed_stray_component_count'],2);self.assertEqual(metadata['removed_stray_component_area_px'],20);self.assertEqual(metadata['diagnostic'],'kept')
        self.assertEqual(self.item['normalized_assets'][1]['method'],'pose_collection_crop_stage_alpha_cutout')
        self.assertEqual(focused.call_args.args[1].shape,(20,20));self.assertEqual(int((focused.call_args.args[1]>0).sum()),100)

    def test_green_unfocused_crop_still_cleans_and_keeps_fallback_method(self):
        self.pose_fixture();asset=np.ones((10,10,3),np.uint8);alpha=np.full((10,10),255,np.uint8)
        self.green.return_value=(asset,alpha,(5,5,15,15))
        self.replace('filter_cutout_to_focus_cell',return_value=None)
        self.replace('alpha_component_summary',return_value=(1,100))
        cleanup=self.replace('cleanup_crop_alpha_components',return_value=(alpha,{}));self.replace('alpha_bbox',return_value=[0,0,10,10])
        self.assertTrue(self.build(allow_ai_cutout=False));cleanup.assert_called_once();self.ai_bounded.assert_not_called()
        self.assertEqual(self.item['normalized_assets'][1]['method'],'pose_collection_lightweight_cutout');self.assertEqual(self.writer.call_args.args[3]['source_object_bbox_xyxy'],[5,5,15,15])
    def test_insufficient_existing_count_does_not_hit_complete_cache(self):
        self.pose_fixture();self.replace('POSE_COLLECTION_GRID_POSITIONS',new=['left','right']);self.regions.return_value=[(0,0,10,20),(10,0,20,20)]
        self.existing.return_value=[{'kind':'clean_object_sprite'}]
        self.assertTrue(self.build());self.uid.assert_called_once();self.assertEqual(self.writer.call_count,2);self.assertEqual(self.item['clean_sprite_expected_count'],2);self.assertEqual(self.item['clean_sprite_status'],'ready')
    def test_two_pose_cells_one_success_one_failure_is_partial(self):
        self.pose_fixture();self.replace('POSE_COLLECTION_GRID_POSITIONS',new=['left','right']);self.regions.return_value=[(0,0,10,20),(10,0,20,20)]
        self.writer.side_effect=[{'kind':'clean_object_sprite'},None,None]
        self.assertTrue(self.build());self.assertEqual(self.writer.call_count,3);self.paths.assert_not_called();self.assertEqual(self.item['clean_sprite_count'],1);self.assertEqual(self.item['clean_sprite_expected_count'],2)
        self.assertEqual(self.item['clean_sprite_status'],'partial');self.assertEqual(self.item['clean_sprite_failed_cells'][0]['pose_position'],'right')
    def test_writer_exception_escapes_without_retry_or_item_replacement(self):
        self.paths.return_value=[self.directory/'source.png'];self.ai.return_value=(self.image,self.mask);self.writer.side_effect=RuntimeError('synthetic writer failure')
        old=self.item['normalized_assets']
        with self.assertRaisesRegex(RuntimeError,'synthetic writer failure'):self.build()
        self.writer.assert_called_once();self.normalize.assert_not_called();self.assertIs(self.item['normalized_assets'],old);self.assertNotIn('clean_sprite_status',self.item)
    def test_postprocessing_failures_preserve_stage_specific_state(self):
        self.paths.return_value=[self.directory/'source.png'];self.ai.return_value=(self.image,self.mask)
        for stage in ('normalize','scale','laying','complete','clock'):
            with self.subTest(stage=stage),ExitStack() as scope:
                self.item={'created_at':7,'physical_size':{},'normalized_assets':[{'kind':'reference'}]};old=self.item['normalized_assets'];self.events.clear()
                target=getattr(self,stage,None)
                if stage=='clock':scope.enter_context(patch.object(self.api.time,'time',side_effect=RuntimeError('stage failure')))
                elif stage=='complete':target.side_effect=[True,RuntimeError('stage failure')]
                else:target.side_effect=RuntimeError('stage failure')
                with self.assertRaisesRegex(RuntimeError,'stage failure'):self.build()
                if stage in ('normalize','scale','laying'):
                    self.assertIs(self.item['normalized_assets'],old);self.assertNotIn('clean_sprite_status',self.item)
                else:
                    self.assertIsNot(self.item['normalized_assets'],old)
                    if stage=='complete':self.assertNotIn('clean_sprite_status',self.item)
                    else:self.assertEqual(self.item['clean_sprite_status'],'ready');self.assertEqual(self.item['clean_sprite_count'],1);self.assertNotIn('clean_sprite_preprocessed_at',self.item)
                if stage=='complete':target.side_effect=None
                elif stage!='clock':target.side_effect=lambda assets,*args,name=stage:self.events.append((name,len(assets)))

    def test_alpha_policy_is_looked_up_again_for_generated_metadata(self):
        self.paths.return_value=[self.directory/'source.png'];self.ai.return_value=(self.image,self.mask)
        newer=Mock(return_value='second')
        def first(item):
            self.api.object_alpha_material_policy=newer
            return 'first'
        self.alpha.side_effect=first
        self.assertTrue(self.build());self.assertEqual(self.item['material_alpha_policy'],'first');self.assertEqual(self.writer.call_args.args[3]['material_alpha_policy'],'second');newer.assert_called_once()
    def test_rng_callee_is_selected_before_seed_clock_effect(self):
        self.item['created_at']=0;self.paths.return_value=[self.directory/'source.png'];self.generic.return_value=(self.image,self.mask)
        rng=np.random.default_rng(3);old=Mock(return_value=rng);new=Mock(return_value=rng)
        self.stack.enter_context(patch.object(self.api.np.random,'default_rng',old))
        def clock():
            self.api.np.random.default_rng=new
            return 19.9
        self.stack.enter_context(patch.object(self.api.time,'time',side_effect=clock))
        self.assertTrue(self.build(allow_ai_cutout=False));old.assert_called_once_with(19);new.assert_not_called();self.assertIs(self.generic.call_args.args[1],rng)
    def test_final_expected_count_reloads_positions_after_writer(self):
        self.pose_fixture()
        def write(path,asset,mask,metadata):
            self.api.POSE_COLLECTION_GRID_POSITIONS=['left','right']
            return {'kind':'clean_object_sprite'}
        self.writer.side_effect=write
        self.assertTrue(self.build());self.assertEqual(self.item['clean_sprite_expected_count'],2);self.assertEqual(self.item['clean_sprite_status'],'partial');self.assertEqual(self.item['clean_sprite_count'],1)
    def test_writer_is_selected_after_footprint_refresh(self):
        self.pose_fixture();fresh=Mock(return_value={'kind':'clean_object_sprite','fresh':True})
        def footprint(*args):
            self.api.write_clean_sprite=fresh
            return {'marker':'footprint'}
        self.footprint.side_effect=footprint
        self.assertTrue(self.build());self.writer.assert_not_called();fresh.assert_called_once();self.assertTrue(self.item['normalized_assets'][1]['fresh']);self.assertEqual(fresh.call_args.args[3]['marker'],'footprint')


    preprocessing_capability_groups = [['policy',
      'ObjectSpritePolicy',
      {'alpha': 'object_alpha_material_policy',
       'complete': 'clean_sprites_policy_complete',
       'existing': 'clean_sprite_assets',
       'material': 'accessory_material_type'}],
     ['sources',
      'ObjectSpriteSources',
      {'images': 'accessory_image_paths',
       'jobs': 'candidate_image_jobs',
       'positions': 'POSE_COLLECTION_GRID_POSITIONS',
       'regions': 'pose_collection_regions'}],
     ['runtime',
      'ObjectSpriteRuntime',
      {'identifier': 'accessory_uid',
       'now': 'time.time',
       'rng': 'np.random.default_rng',
       'root': 'NORMALIZED_DIR'}],
     ['cutouts',
      'ObjectSpriteCutouts',
      {'ai_bounded': 'ai_background_cutout_with_bbox',
       'ai_plain': 'ai_background_cutout',
       'green': 'green_screen_object_cutout_with_bbox',
       'lightweight': 'object_cutout_from_image',
       'usable': 'usable_object_cutout'}],
     ['components',
      'ObjectSpriteComponents',
      {'bounds': 'alpha_bbox',
       'cleanup': 'cleanup_crop_alpha_components',
       'cutouts': 'alpha_component_cutouts',
       'focus': 'filter_cutout_to_focus_cell',
       'summary': 'alpha_component_summary'}],
     ['metadata',
      'ObjectSpriteMetadata',
      {'footprint': 'pose_render_footprint_metadata',
       'laying': 'apply_laying_standard_render_size_hints',
       'normalize': 'normalize_sprite_family_canvases',
       'scale': 'apply_upright_scale_correction_metadata',
       'task_id': 'deterministic_task_id',
       'top_view': 'pose_family_is_top_view'}],
     ['artifacts', 'ObjectSpriteArtifacts', {'write': 'write_clean_sprite'}]]
    def independent_preprocessor(self, *, second=False):
        from local_inspection_service.accessories import object_preprocessing_ports as ports
        from local_inspection_service.accessories.object_preprocessing import ObjectSpritePreprocessor
        capabilities=[]
        for name,type_name,bindings in self.preprocessing_capability_groups:
            selected={}
            for field,source in bindings.items():
                value=self.api
                for part in source.split('.'):value=getattr(value,part)
                selected[field]=value
            if second and name=='runtime':selected.update(identifier=lambda item:'second-uid',root=self.directory/'second-root',now=lambda:456.9)
            if second and name=='policy':selected['complete']=lambda item,assets:False
            if second and name=='artifacts':selected['write']=lambda path,image,mask,metadata:{'kind':'clean_object_sprite','instance':'second','path':str(path)}
            capabilities.append(getattr(ports,type_name)(**{field:(lambda value=value:value) for field,value in selected.items()}))
        return ObjectSpritePreprocessor(*capabilities)
    def test_preprocessor_constructor_does_not_read_capabilities(self):
        from local_inspection_service.accessories import object_preprocessing_ports as ports
        from local_inspection_service.accessories.object_preprocessing import ObjectSpritePreprocessor
        forbidden=Mock(side_effect=AssertionError('eager capability read'))
        instance=ObjectSpritePreprocessor(*[getattr(ports,kind)(**{field:forbidden for field in bindings}) for name,kind,bindings in self.preprocessing_capability_groups])
        self.assertIsInstance(instance,ObjectSpritePreprocessor);forbidden.assert_not_called()
    def test_independent_preprocessors_first_second_first(self):
        self.paths.return_value=[self.directory/'source.png'];self.ai.return_value=(self.image,self.mask)
        first=self.independent_preprocessor();second=self.independent_preprocessor(second=True)
        second_item={'created_at':9,'physical_size':{},'normalized_assets':[]}
        sources={source for name,kind,bindings in self.preprocessing_capability_groups for source in bindings.values() if '.' not in source and source[0].islower()}
        poisons=[]
        with ExitStack() as stack:
            for name in sources:poisons.append(stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('root callback forbidden'))))
            for service,item in [(first,self.item),(second,second_item),(first,self.item)]:self.assertTrue(service.preprocess_object_clean_sprites(item))
        for forbidden in poisons:forbidden.assert_not_called()
        self.assertEqual(self.writer.call_count,2);self.assertEqual(self.item['clean_sprite_status'],'ready');self.assertEqual(second_item['clean_sprite_status'],'partial')
        self.assertEqual(self.item['clean_sprite_preprocessed_at'],123);self.assertEqual(second_item['clean_sprite_preprocessed_at'],456)
        self.assertEqual(second_item['normalized_assets'][0]['instance'],'second');self.assertIn('second-root',second_item['normalized_assets'][0]['path'])
        self.assertNotIn('second-root',self.item['normalized_assets'][-1]['path']);self.assertEqual(self.ai.call_count,3)


if __name__=='__main__':unittest.main()
