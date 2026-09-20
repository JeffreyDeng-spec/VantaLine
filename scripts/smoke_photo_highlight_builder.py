"""Draft original photo-highlight builder contracts; private synthetic fixtures only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch
import numpy as np
sys.path.insert(0,str(Path.cwd()))

class PhotoHighlightBuilderContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='photo-builder-')))
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
        self.task={'id':'task','owner_user_id':'owner'}
        self.retained={'kind':'reference','marker':'kept'}
        self.old={'kind':'clean_object_sprite','marker':'old'}
        self.item={'name':'Synthetic','physical_size':{'width':2},'normalized_assets':[self.retained,self.old]}
        self.source=self.directory/'source.png';self.image=np.full((12,16,3),70,np.uint8)
        self.provider=Mock();self.provider.generate_image.return_value={'bytes':b'synthetic','latency_ms':7}
        self.material=self.replace('accessory_material_type',return_value='rigid')
        self.sources=self.replace('object_photo_highlight_source_paths',return_value=[self.source])
        self.ready=self.replace('photo_highlight_clean_sprites_ready',return_value=False)
        self.alpha=self.replace('object_alpha_material_policy',return_value='opaque')
        self.uid=self.replace('accessory_uid',return_value='uid')
        self.replace('NORMALIZED_DIR',new=self.directory/'normalized')
        self.output=self.replace('output_write_dir_for_owner',return_value=self.directory/'output')
        self.replace('PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES',new=1)
        self.replace('PHOTO_HIGHLIGHT_MASK_MAX_ATTEMPTS',new=2)
        self.replace('AGENT_MCP_SPRITE_BUILD_VERSION',new=41)
        self.replace('PHOTO_HIGHLIGHT_SPRITE_BUILD_VERSION',new=42)
        self.safe=self.replace('safe_record_id',side_effect=str)
        self.record=self.replace('sanitize_data_analysis_record_id',side_effect=str)
        self.prompt=self.replace('photo_highlight_mask_prompt',return_value='exact synthetic prompt')
        self.publish=self.replace('upsert_data_analysis_image_processing_record',return_value={})
        self.processing=self.replace('image_processing_item',side_effect=lambda **kw:kw)
        self.read=self.stack.enter_context(patch.object(self.api.cv2,'imread',return_value=self.image.copy()))
        self.image_write=self.stack.enter_context(patch.object(self.api.cv2,'imwrite',return_value=True))
        self.input=self.replace('photo_highlight_input_data_url',return_value=(self.image.copy(),'data:image/test',0.5,0.75))
        self.decode=self.replace('decode_photo_highlight_mask',return_value=(np.full((12,16),255,np.uint8),{'ok':True,'origin':'synthetic'}))
        self.bounds=self.replace('alpha_bbox',return_value=[1,2,9,10])
        self.roi=self.replace('photo_highlight_auto_roi_mask',side_effect=lambda image,mask:(mask.copy(),{'status':'available'}))
        self.compare=self.replace('photo_highlight_auto_compare',return_value={'ok':True,'score':0.9})
        self.url=self.replace('public_output_url_for_existing',side_effect=lambda p:'output/'+p.name)
        self.footprint=self.replace('pose_render_footprint_metadata',return_value={'footprint':'kept'})
        self.asset={'kind':'clean_object_sprite','width':8,'height':8,'pose_id':'generated'}
        self.writer=self.replace('write_clean_sprite',return_value=self.asset)
        self.events=[]
        self.normalize=self.replace('normalize_sprite_family_canvases',side_effect=lambda assets:self.events.append('normalize'))
        self.scale=self.replace('apply_upright_scale_correction_metadata',side_effect=lambda assets,size:self.events.append('scale'))
        self.laying=self.replace('apply_laying_standard_render_size_hints',side_effect=lambda assets:self.events.append('laying'))
        self.complete=self.replace('clean_sprites_policy_complete',return_value=True)
        self.stack.enter_context(patch.object(self.api.time,'time',return_value=123.9))
    def replace(self,name,**kwargs):return self.stack.enter_context(patch.object(self.api,name,**kwargs))
    def build(self,**kwargs):return self.api.build_clean_sprites_from_photo_highlight_masks(self.task,self.item,self.provider,'model',**kwargs)
    def statuses(self):return [(x['item_type'],x['status']) for c in self.publish.call_args_list for x in c.kwargs['items']]
    def test_text_skips_sources_and_all_work(self):
        self.material.return_value='text'
        self.assertEqual(self.build(),(True,''));self.sources.assert_not_called();self.provider.generate_image.assert_not_called()
    def test_source_count_precedes_cached_readiness(self):
        self.sources.return_value=[];self.ready.return_value=True
        self.assertEqual(self.build(),(False,'配件 Synthetic 至少需要 1 张不同角度实拍图'));self.ready.assert_not_called();self.alpha.assert_not_called()
    def test_cache_exit_and_force(self):
        self.ready.return_value=True
        self.assertEqual(self.build(),(True,''));self.alpha.assert_not_called()
        self.assertEqual(self.build(force=True),(True,''));self.assertEqual(self.ready.call_count,1);self.assertEqual(self.provider.generate_image.call_count,1)
    def test_unreadable_source_keeps_prior_assets(self):
        self.read.return_value=None
        ok,reason=self.build();self.assertFalse(ok);self.assertIn('source_unreadable',reason)
        self.provider.generate_image.assert_not_called();self.assertEqual(self.item['normalized_assets'],[self.retained,self.old]);self.assertEqual(self.statuses(),[('source_photo','completed'),('ai_mask','queued'),('source_photo','failed')])
    def test_encode_failure_never_calls_provider(self):
        self.input.return_value=None
        ok,reason=self.build();self.assertFalse(ok);self.assertIn('input_encode_failed',reason);self.provider.generate_image.assert_not_called();self.assertEqual(self.statuses()[-1],('ai_mask','failed'))
    def test_provider_error_attempts_and_unexpected_exception(self):
        self.provider.generate_image.side_effect=self.api.AiProviderError('synthetic provider failure')
        ok,reason=self.build();self.assertFalse(ok);self.assertIn('attempt 2: synthetic provider failure',reason);self.assertEqual(self.provider.generate_image.call_count,2)
        self.provider.generate_image.reset_mock();self.provider.generate_image.side_effect=ValueError('unexpected')
        with self.assertRaisesRegex(ValueError,'unexpected'):self.build()
        self.assertEqual(self.provider.generate_image.call_count,1)
    def test_generated_mask_unreadable(self):
        self.read.side_effect=lambda name,mode:self.image if name==str(self.source) else None
        ok,reason=self.build();self.assertFalse(ok);self.assertIn('generated_mask_unreadable',reason);self.assertEqual(self.provider.generate_image.call_count,2);self.decode.assert_not_called()
        self.assertEqual(self.statuses().count(('ai_mask','failed')),2)
    def test_invalid_decode_then_success_uses_second_attempt(self):
        self.decode.side_effect=[(np.zeros((12,16),np.uint8),{'ok':False,'reason':'rejected-mask'}),(np.full((12,16),255,np.uint8),{'ok':True})]
        self.assertEqual(self.build(),(True,''));self.assertEqual(self.provider.generate_image.call_count,2)
        meta=self.writer.call_args.args[3];self.assertEqual(meta['photo_highlight_generation_attempts'],2);self.assertIn('_attempt02.png',meta['photo_highlight_mask_path']);self.assertIn(('ai_mask','rejected'),self.statuses())
    def test_empty_scaled_mask_does_not_write_sprite(self):
        self.bounds.return_value=[0,0,0,0]
        ok,reason=self.build();self.assertFalse(ok);self.assertIn('empty_scaled_mask',reason);self.writer.assert_not_called();self.assertEqual(self.provider.generate_image.call_count,2)
    def test_rejected_candidates_record_best_without_acceptance(self):
        self.compare.side_effect=[{'ok':False,'score':0.7,'mask_iou':0.6},{'ok':False,'score':0.2,'mask_iou':0.1}]
        ok,reason=self.build();self.assertFalse(ok);self.assertIn('best_score=0.7 iou=0.6',reason);self.writer.assert_not_called();self.assertEqual(self.provider.generate_image.call_count,2)
    def test_mask_resize_and_preview_order(self):
        self.read.side_effect=lambda name,mode:self.image if name==str(self.source) else np.zeros((6,8,3),np.uint8)
        self.assertEqual(self.build(),(True,''))
        paths=[Path(c.args[0]).name for c in self.image_write.call_args_list]
        self.assertEqual(paths,['01_source_highlight_attempt01_resized.png','01_source_attempt01_roi.png','01_source_attempt01_ai_roi_mask.png','01_source_attempt01_traditional_roi_mask.png','01_source_attempt01_transparent_sprite.png'])
        self.assertEqual(self.decode.call_args.args[0].shape,(12,16,3));self.assertIn('_resized.png',self.writer.call_args.args[3]['photo_highlight_mask_path'])
    def test_success_preserves_metadata_identity_and_postprocessing(self):
        self.alpha.side_effect=['first','second']
        self.assertEqual(self.build(),(True,''));self.assertEqual(self.item['material_alpha_policy'],'first')
        path,image,mask,meta=self.writer.call_args.args
        self.assertEqual(path,self.directory/'normalized/uid/clean_sprites/photo_highlight_01_source.png')
        self.assertEqual(image.shape,(8,8,3));self.assertEqual(mask.shape,(8,8))
        self.assertEqual(meta['material_alpha_policy'],'second');self.assertIs(meta['physical_size_mm'],self.item['physical_size'])
        self.assertEqual([meta[k] for k in ('agent_mcp_sprite_build','photo_highlight_sprite_build','photo_highlight_latency_ms')],[41,42,7])
        self.assertEqual(meta['source_object_bbox_xyxy'],[1,2,9,10]);self.assertEqual(meta['photo_highlight_scale_xy'],[0.5,0.75]);self.assertEqual(meta['footprint'],'kept')
        self.assertEqual(self.events,['normalize','scale','laying']);self.assertIs(self.item['normalized_assets'][0],self.retained);self.assertIs(self.item['normalized_assets'][1],self.asset)
        self.assertEqual(self.asset['method'],'real_photo_highlight_mask_sprite');self.assertEqual(self.item['clean_sprite_status'],'ready');self.assertEqual(self.item['clean_sprite_preprocessed_at'],123)
        self.assertEqual(self.complete.call_count,2);self.assertEqual(self.provider.generate_image.call_count,1)
        self.assertEqual(self.provider.generate_image.call_args.args[0],'exact synthetic prompt');self.assertEqual(self.provider.generate_image.call_args.kwargs,{'model':'model'})
        self.assertEqual(self.provider.generate_image.call_args.args[1][1],{'type':'image_url','image_url':{'url':'data:image/test','detail':'high'}})
    def test_writer_failure_preserves_prior_assets(self):
        self.writer.return_value=None
        ok,reason=self.build();self.assertFalse(ok);self.assertIn('clean_sprite_write_failed',reason);self.normalize.assert_not_called();self.assertEqual(self.item['normalized_assets'],[self.retained,self.old]);self.assertEqual(self.statuses()[-1],('clean_sprite','failed'))
    def test_publication_exception_is_swallowed_but_base_exception_escapes(self):
        self.publish.side_effect=RuntimeError('audit unavailable')
        self.assertEqual(self.build(),(True,''))
        self.publish.side_effect=KeyboardInterrupt('stop')
        with self.assertRaises(KeyboardInterrupt):self.build()
    def test_processing_item_error_is_outside_publication_catch(self):
        self.processing.side_effect=ValueError('item builder')
        with self.assertRaisesRegex(ValueError,'item builder'):self.build()
        self.publish.assert_not_called();self.provider.generate_image.assert_not_called()
    def test_preview_write_exception_swallowed_but_url_error_escapes(self):
        self.image_write.side_effect=OSError('preview write')
        self.assertEqual(self.build(),(True,''));self.assertEqual(self.image_write.call_count,1)
        self.url.side_effect=RuntimeError('url failure')
        with self.assertRaisesRegex(RuntimeError,'url failure'):self.build()
    def test_postprocessing_error_precedes_final_item_replacement(self):
        self.scale.side_effect=RuntimeError('scale failure')
        with self.assertRaisesRegex(RuntimeError,'scale failure'):self.build()
        self.assertEqual(self.events,['normalize']);self.laying.assert_not_called();self.assertEqual(self.item['normalized_assets'],[self.retained,self.old]);self.assertEqual(self.asset['method'],'real_photo_highlight_mask_sprite')
    def test_completion_is_read_twice_and_return_preserves_first_status(self):
        self.complete.side_effect=[True,False]
        self.assertEqual(self.build(),(False,''));self.assertEqual(self.item['clean_sprite_status'],'ready');self.assertEqual(self.complete.call_count,2)
        self.complete.side_effect=[False,True]
        self.assertEqual(self.build(),(True,'photo_highlight_clean_sprite_incomplete'));self.assertEqual(self.item['clean_sprite_status'],'partial')

    def test_mask_file_write_error_and_malformed_result_escape_without_retry(self):
        with patch.object(Path,'write_bytes',side_effect=OSError('mask write')):
            with self.assertRaisesRegex(OSError,'mask write'):self.build()
        self.assertEqual(self.provider.generate_image.call_count,1);self.writer.assert_not_called()
        self.provider.generate_image.reset_mock();self.provider.generate_image.return_value={}
        with self.assertRaises(KeyError):self.build()
        self.assertEqual(self.provider.generate_image.call_count,1)
    def test_single_attempt_has_unsuffixed_mask_name(self):
        self.replace('PHOTO_HIGHLIGHT_MASK_MAX_ATTEMPTS',new=1)
        self.assertEqual(self.build(),(True,''));self.assertEqual(self.provider.generate_image.call_count,1)
        self.assertTrue(self.writer.call_args.args[3]['photo_highlight_mask_path'].endswith('/01_source_highlight.png') or self.writer.call_args.args[3]['photo_highlight_mask_path'].endswith('\\01_source_highlight.png'))
        self.assertEqual(self.writer.call_args.args[3]['photo_highlight_max_attempts'],1)
    def test_multiple_sources_keep_failures_and_success_order(self):
        self.replace('PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES',new=2)
        paths=[self.directory/(name+'.png') for name in ('missing','second','third')];self.sources.return_value=paths
        self.read.side_effect=lambda name,mode:None if name==str(paths[0]) else self.image.copy()
        written=[]
        def write(path,image,mask,metadata):
            asset={'kind':'clean_object_sprite','ordinal':len(written)};written.append((path,asset));return asset
        self.writer.side_effect=write
        self.assertEqual(self.build(),(True,''));self.assertEqual(self.provider.generate_image.call_count,2)
        self.assertEqual([p.name for p,a in written],['photo_highlight_02_second.png','photo_highlight_03_third.png'])
        self.assertEqual(self.item['normalized_assets'],[self.retained,*[a for p,a in written]])
        self.assertEqual(self.item['clean_sprite_failed_cells'],['missing.png: source_unreadable'])
        self.assertEqual(self.item['photo_highlight_sprite_status']['source_count'],3);self.assertEqual(self.item['clean_sprite_count'],2)

    def test_alpha_callee_refreshes_after_first_call(self):
        newer=Mock(return_value='new-alpha')
        def first(item):self.api.object_alpha_material_policy=newer;return 'old-alpha'
        self.alpha.side_effect=first
        self.assertEqual(self.build(),(True,''));self.assertEqual(self.item['material_alpha_policy'],'old-alpha')
        self.assertEqual(self.writer.call_args.args[3]['material_alpha_policy'],'new-alpha');newer.assert_called_once_with(self.item)
    def test_audit_publisher_refreshes_between_publications(self):
        newer=Mock(return_value={})
        def first(**kwargs):self.api.upsert_data_analysis_image_processing_record=newer;return {}
        self.publish.side_effect=first
        self.assertEqual(self.build(),(True,''));self.publish.assert_called_once();self.assertEqual(newer.call_count,3)
        self.assertEqual(newer.call_args_list[0].kwargs['items'][0]['status'],'running')
    def test_writer_selected_after_footprint_metadata(self):
        newer=Mock(return_value=self.asset)
        def footprint(*args):self.api.write_clean_sprite=newer;return {'footprint':'new'}
        self.footprint.side_effect=footprint
        self.assertEqual(self.build(),(True,''));self.writer.assert_not_called();newer.assert_called_once()
        self.assertEqual(newer.call_args.args[3]['footprint'],'new')
    def test_completion_callee_refreshes_after_status_assignment(self):
        newer=Mock(return_value=False)
        def first(item,assets):self.api.clean_sprites_policy_complete=newer;return True
        self.complete.side_effect=first
        self.assertEqual(self.build(),(False,''));self.assertEqual(self.item['clean_sprite_status'],'ready');self.complete.assert_called_once();newer.assert_called_once()

    builder_capability_groups = [['policy',
      'PhotoBuildPolicy',
      {'material': 'accessory_material_type',
       'sources': 'object_photo_highlight_source_paths',
       'ready': 'photo_highlight_clean_sprites_ready',
       'alpha': 'object_alpha_material_policy',
       'complete': 'clean_sprites_policy_complete',
       'minimum': 'PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES'}],
     ['runtime',
      'PhotoBuildRuntime',
      {'identifier': 'accessory_uid',
       'root': 'NORMALIZED_DIR',
       'output': 'output_write_dir_for_owner',
       'safe_id': 'safe_record_id',
       'now': 'time.time',
       'bounded': 'bounded_text'}],
     ['masks',
      'PhotoBuildMasks',
      {'prompt': 'photo_highlight_mask_prompt',
       'input': 'photo_highlight_input_data_url',
       'decode': 'decode_photo_highlight_mask',
       'bounds': 'alpha_bbox',
       'roi': 'photo_highlight_auto_roi_mask',
       'compare': 'photo_highlight_auto_compare'}],
     ['model',
      'PhotoBuildModelPolicy',
      {'attempts': 'PHOTO_HIGHLIGHT_MASK_MAX_ATTEMPTS',
       'error': 'AiProviderError',
       'pose_version': 'AGENT_MCP_SPRITE_BUILD_VERSION',
       'photo_version': 'PHOTO_HIGHLIGHT_SPRITE_BUILD_VERSION'}],
     ['publication',
      'PhotoBuildPublication',
      {'sanitize': 'sanitize_data_analysis_record_id',
       'item': 'image_processing_item',
       'publish': 'upsert_data_analysis_image_processing_record'}],
     ['artifacts',
      'PhotoBuildArtifacts',
      {'write': 'write_clean_sprite', 'public_url': 'public_output_url_for_existing'}],
     ['metadata',
      'PoseSpriteMetadata',
      {'footprint': 'pose_render_footprint_metadata',
       'normalize': 'normalize_sprite_family_canvases',
       'scale': 'apply_upright_scale_correction_metadata',
       'laying': 'apply_laying_standard_render_size_hints'}]]
    def independent_builder(self, *, second=False):
        from local_inspection_service.agent import photo_highlight_builder_ports as ports
        from local_inspection_service.agent.photo_highlight_builder import PhotoHighlightSpriteBuilder
        groups = self.builder_capability_groups
        capabilities=[]
        for name,type_name,bindings in groups:
            selected={field:(self.api.time.time if source=='time.time' else getattr(self.api,source)) for field,source in bindings.items()}
            if second and name=='runtime':
                selected.update(identifier=lambda item:'second-uid',root=self.directory/'second-normalized',output=lambda kind,owner:self.directory/'second-output')
            if second and name=='policy':selected['complete']=lambda item,assets:False
            if second and name=='artifacts':selected['write']=lambda path,image,mask,metadata:{'kind':'clean_object_sprite','instance':'second'}
            capabilities.append(getattr(ports,type_name)(**{field:(lambda value=value:value) for field,value in selected.items()}))
        return PhotoHighlightSpriteBuilder(*capabilities)
    def test_constructor_reads_no_capability(self):
        from local_inspection_service.agent import photo_highlight_builder_ports as ports
        from local_inspection_service.agent.photo_highlight_builder import PhotoHighlightSpriteBuilder
        groups=self.builder_capability_groups
        forbidden=Mock(side_effect=AssertionError('eager capability read'))
        instance=PhotoHighlightSpriteBuilder(*[getattr(ports,type_name)(**{field:forbidden for field in bindings}) for name,type_name,bindings in groups])
        self.assertIsInstance(instance,PhotoHighlightSpriteBuilder);forbidden.assert_not_called()
    def test_independent_builders_first_second_first_success_with_root_poisoned(self):
        first=self.independent_builder();second=self.independent_builder(second=True)
        second_item={'name':'Second','physical_size':{'width':4},'normalized_assets':[]}
        second_provider=Mock();second_provider.generate_image.return_value={'bytes':b'second-synthetic','latency_ms':4}
        sources={source for name,type_name,bindings in self.builder_capability_groups for source in bindings.values() if source!='time.time' and source[0].islower()}
        poisoned_mocks=[]
        with ExitStack() as poisoned:
            for name in sources:poisoned_mocks.append(poisoned.enter_context(patch.object(self.api,name,side_effect=AssertionError('root business callback forbidden'))))
            for builder,item,provider,expected in [(first,self.item,self.provider,(True,'')),(second,second_item,second_provider,(False,'photo_highlight_clean_sprite_incomplete')),(first,self.item,self.provider,(True,''))]:
                self.assertEqual(builder.build_clean_sprites_from_photo_highlight_masks(self.task,item,provider,'model'),expected)
        for forbidden in poisoned_mocks:forbidden.assert_not_called()
        self.assertEqual(self.publish.call_count,12)
        self.assertEqual(self.provider.generate_image.call_count,2);self.assertEqual(second_provider.generate_image.call_count,1)
        self.assertEqual(self.item['clean_sprite_status'],'ready');self.assertEqual(second_item['clean_sprite_status'],'partial')
        self.assertIs(self.item['normalized_assets'][-1],self.asset);self.assertEqual(second_item['normalized_assets'][-1]['instance'],'second')
        self.assertEqual(self.writer.call_count,2)
        self.assertTrue((self.directory/'second-output/task/second-uid/01_source_highlight_attempt01.png').exists())

if __name__=='__main__':unittest.main()
