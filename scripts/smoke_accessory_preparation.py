"""Original preparation workflows with synthetic media and provider substitutes."""
import copy
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from fastapi import HTTPException


class PreparationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='accessory-preparation-')
        cls.root = Path(cls.temporary.name)
        (cls.root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(cls.root), VANTALINE_DATA_STORE='json',
                          VANTALINE_LABEL_INSPECTION_ENABLED='false', LOCAL_INSPECTION_AUTO_RESUME_WORKER='0')
        from local_inspection_service import server
        cls.server = server

    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    def setUp(self):
        self.stack, self.events = ExitStack(), []
        self.addCleanup(self.stack.close)
        self.stack.enter_context(self.server._request_user.bind({'id':'fixture-owner','username':'fixture-owner','role':'user'}))
        def profile(item, **kwargs):
            self.events.append(('profile',kwargs))
            item['ai_profile'] = {'fixture':True}
        def pose(item):
            self.events.append(('pose',))
            item['codex_image_jobs'] = [{'job_id':'fixture-job','status':'queued'}]
            item['codex_image_job'] = item['codex_image_jobs'][0]
            return True
        def save(path,item):
            self.events.append(('save',Path(path),copy.deepcopy(item)))
        self.stack.enter_context(patch.object(self.server,'ensure_accessory_ai_profile',side_effect=profile))
        self.stack.enter_context(patch.object(self.server,'generate_accessory_ai_profile',side_effect=profile))
        self.stack.enter_context(patch.object(self.server,'ensure_pose_collection_image_jobs',side_effect=pose))
        self.stack.enter_context(patch.object(self.server,'save_accessory_candidate',side_effect=save))
        self.stack.enter_context(patch.object(self.server,'start_image_worker',side_effect=AssertionError('factory must not start worker')))

    def image(self,name):
        path = self.root/(name+'.png')
        self.assertTrue(cv2.imwrite(str(path),np.full((12,20,3),83,dtype=np.uint8)))
        return path

    def test_text_order_limit_crop_set_and_empty_source_result(self):
        sources = ['first.png','first_manual_rectified.png','second_manual_rectified.png','third_manual_rectified.png']
        item = {'id':'text-plan','material_type':'text','source_files':sources,
                'original_source_files':['third.png'],'physical_size':{'width_mm':99}}
        before = copy.deepcopy(item)
        calls = []
        def normalize(path,directory,size):
            calls.append((path.name,directory,size))
            return None if path.name.startswith('first_') else {'path':str(path),'kind':'normalized_text'}
        with patch.object(self.server,'normalize_text_image',side_effect=normalize):
            result = self.server.normalize_accessory_assets(item)
        self.assertEqual([call[0] for call in calls],['first_manual_rectified.png','second_manual_rectified.png'])
        self.assertEqual(calls[0][2],{'width_mm':99})
        self.assertEqual(result['status'],'normalized_text_ready')
        self.assertFalse(result['manual_crop_required'])
        self.assertEqual(len(result['normalized_assets']),1)
        self.assertEqual(item,before)
        self.assertTrue((self.server.NORMALIZED_DIR/'text-plan').is_dir())
        item['original_source_files'] = ['uncropped.png']
        with patch.object(self.server,'normalize_text_image',side_effect=normalize):
            result = self.server.normalize_accessory_assets(item)
        self.assertEqual((result['status'],result['manual_crop_required'],result['manual_crop_reason']),('needs_crop',True,'manual_crop_required'))
        empty = self.server.normalize_accessory_assets({'id':'empty-text','material_type':'text','source_files':[]})
        self.assertEqual((empty['status'],empty['manual_crop_required'],empty['manual_crop_reason']),('needs_crop',False,''))

    def test_object_plan_and_defer_preserve_unrelated_state(self):
        item = {'id':'object-plan','name':'Fixture object','material_type':'object','source_files':['source.PNG','video.mp4']}
        result = self.server.normalize_accessory_assets(item)
        self.assertEqual(result['status'],'image_tool_plan_ready')
        plan = result['normalized_assets'][0]
        self.assertEqual(plan['source_files'],['source.PNG'])
        self.assertEqual(plan['image_tool_prompt'],
            "Image-to-image asset expansion for 'Fixture object'. Generate clean isolated product views with consistent material, multiple angles, standing/lying poses when applicable, calibrated size variants, object-only framing, no background/backing/surface/shadows, and transparent PNG alpha when supported.")
        self.assertEqual([entry['view'] for entry in plan['view_plan']],['front','left_oblique','right_oblique','top','lying_horizontal','standing'])
        item.update(normalized_assets=[{'old':True}],status='preserved',manual_crop_required=True,
                    model_profiles={'image':{'version':1}},codex_image_jobs=[{'old':True}],
                    clean_sprite_status='ready',clean_sprite_count=1,clean_sprite_expected_count=2,
                    clean_sprite_failed_cells=['old'],clean_sprite_preprocessed_at=123,clean_sprite_other='preserved')
        self.server.defer_accessory_normalization(item)
        self.assertEqual(item['normalized_assets'],[])
        self.assertTrue(item['normalization_deferred'])
        self.assertEqual(item['status'],'preserved')
        self.assertTrue(item['manual_crop_required'])
        self.assertEqual(item['model_profiles'],{'image':{'version':1}})
        self.assertEqual(item['codex_image_jobs'],[{'old':True}])
        self.assertEqual([key for key in item if key.startswith('clean_sprite_')],['clean_sprite_other'])

    def test_reference_selection_existing_and_stale_values(self):
        path = self.image('reference-original')
        item = {'source_files':[str(path)],'ai_profile_reference_files':['missing.png']}
        self.assertTrue(self.server.ensure_default_ai_profile_reference(item))
        self.assertEqual(item['ai_profile_reference_files'],[str(path)])
        canonical_path = str(self.server.resolve_service_path(str(path)))
        self.assertEqual(self.server.ensure_default_ai_profile_reference(item),canonical_path != str(path))
        self.assertEqual(item['ai_profile_reference_files'],[canonical_path])
        self.assertFalse(self.server.ensure_default_ai_profile_reference(item))
        stale = {'source_files':[],'ai_profile_reference_files':['missing.png']}
        self.assertFalse(self.server.ensure_default_ai_profile_reference(stale))
        self.assertEqual(stale['ai_profile_reference_files'],['missing.png'])
        item['ai_profile_reference_files'] = [str(path),str(path)]
        self.assertTrue(self.server.ensure_default_ai_profile_reference(item))
        self.assertEqual(item['ai_profile_reference_files'],[canonical_path])

    def test_video_expansion_preserves_duplicates_order_and_prior_files_on_failure(self):
        source = ['one.MP4','still.png','one.MP4','two.mov']
        calls = []
        def extract(path,directory):
            calls.append((path,directory))
            directory.mkdir(parents=True,exist_ok=True)
            frame = directory/(path.stem+'.png')
            frame.write_bytes(b'synthetic video frame')
            return [{'path':str(frame),'source':str(path)}]
        with patch.object(self.server,'extract_video_reference_frames',side_effect=extract):
            expanded, frames = self.server.expand_accessory_reference_sources('candidate',source)
        directory = self.server.UPLOAD_DIR/'accessory_candidates/candidate/video_reference_frames'
        self.assertEqual([path.name for path,_ in calls],['one.MP4','one.MP4','two.mov'])
        self.assertTrue(all(path==directory for _,path in calls))
        self.assertEqual(expanded,source+[str(directory/'one.png'),str(directory/'one.png'),str(directory/'two.png')])
        self.assertEqual(len(frames),3)
        self.assertEqual(source,['one.MP4','still.png','one.MP4','two.mov'])
        def fail_second(path,directory):
            if path.name=='two.mov': raise RuntimeError('synthetic video failure')
            return extract(path,directory)
        with patch.object(self.server,'extract_video_reference_frames',side_effect=fail_second):
            with self.assertRaises(RuntimeError): self.server.expand_accessory_reference_sources('partial',['one.MP4','two.mov'])
        self.assertTrue((self.server.UPLOAD_DIR/'accessory_candidates/partial/video_reference_frames/one.png').exists())

    def test_refresh_force_false_and_provider_failure_keep_prior_mutations(self):
        path = self.image('refresh-source')
        item = {'id':'refresh-object','material_type':'object','source_files':[str(path)],'ai_profile':{'old':True},'normalized_assets':[{'old':True}]}
        self.server.refresh_accessory_assets_after_source_change(item,force_profile=False)
        self.assertEqual(item['normalized_assets'],[])
        self.assertEqual(item['ai_profile'],{'old':True})
        self.assertEqual(item['ai_profile_reference_files'],[str(path)])
        self.assertEqual(self.events,[])
        text = {'id':'refresh-text','material_type':'text','source_files':[]}
        with patch.object(self.server,'normalize_text_image',side_effect=AssertionError('no images')):
            self.server.refresh_accessory_assets_after_source_change(text,force_profile=False)
        self.assertFalse(text['normalization_deferred'])
        self.assertEqual(text['status'],'needs_crop')
        def fail(item, **kwargs):
            self.assertEqual(kwargs,{'allow_provider':True})
            self.assertEqual(item['ai_profile'],{'fallback':True})
            self.assertEqual(item['ai_profile_status'],'ready')
            raise RuntimeError('synthetic provider failure')
        with patch.object(self.server,'fallback_accessory_ai_profile',return_value={'fallback':True}), \
             patch.object(self.server,'generate_accessory_ai_profile',side_effect=fail):
            with self.assertRaises(RuntimeError): self.server.refresh_accessory_assets_after_source_change(item)
        self.assertEqual(item['ai_profile'],{'fallback':True})
        self.assertEqual(item['ai_profile_status'],'ready')
        self.assertEqual(self.events,[])

    def test_candidate_factory_orders_profile_thumbnails_pose_and_save(self):
        paths = [str(self.image('factory-'+str(index))) for index in range(9)]
        size = {'length_mm':17}
        original = self.server.write_thumbnail
        def thumbnail(*args):
            self.events.append(('thumbnail',Path(args[1]).name))
            return original(*args)
        with patch.object(self.server,'write_thumbnail',side_effect=thumbnail):
            item = self.server.create_accessory_candidate('Factory','object','detect_and_classify',paths,size,'opaque','ruler')
        self.assertEqual([event[0] for event in self.events],['profile']+['thumbnail']*8+['pose','save'])
        self.assertEqual(self.events[0],('profile',{'allow_provider':True}))
        self.assertIs(item['physical_size'],size)
        self.assertIs(item['original_source_files'],paths)
        self.assertIsNot(item['source_files'],paths)
        self.assertEqual(item['owner_user_id'],'fixture-owner')
        self.assertEqual(len(item['thumbnails']),8)
        self.assertEqual(item['size_reference'],'ruler')
        self.assertEqual(item['pose_collection_prompt'],'')
        self.assertFalse(item['ai_generation_required'])
        self.assertEqual(self.events[-1][1],self.server.ACCESSORY_CANDIDATES_DIR/(item['id']+'.json'))
        self.assertEqual(self.events[-1][2],item)

    def test_candidate_thumbnail_limit_and_default_size_call(self):
        paths = [str(self.root/'unreadable-first.png')]+[str(self.image(f'limit-{idx}')) for idx in range(8)]
        size = {'fixture':'default size'}
        with patch.object(self.server,'physical_size_payload',return_value=size) as defaults:
            item = self.server.create_accessory_candidate('Limits','object','detect_and_classify',paths,{},'opaque')
        defaults.assert_called_once_with('object')
        self.assertIs(item['physical_size'],size)
        directory = self.server.output_write_dir('accessory_candidates')/item['id']
        self.assertEqual(sorted(path.name for path in directory.iterdir()),[f'source_{idx:02d}.png' for idx in range(2,9)])
        self.assertEqual(len(item['thumbnails']),7)
        written = []
        original_thumbnail = self.server.write_thumbnail
        def thumbnail(image,path,angle):
            self.assertFalse(path.exists())
            written.append(path)
            return original_thumbnail(image,path,angle)
        with patch.object(self.server,'save_accessory_candidate',side_effect=RuntimeError('synthetic save failure')), \
             patch.object(self.server,'write_thumbnail',side_effect=thumbnail):
            with self.assertRaises(RuntimeError):
                self.server.create_accessory_candidate('Save failure','object','detect_and_classify',[paths[1]],material_alpha_policy='opaque')
        self.assertEqual(self.events[-1][0],'pose')
        self.assertEqual(len(written),1)
        self.assertTrue(written[0].exists())

    def test_candidate_expands_before_alpha_validation_and_does_not_save_after_failures(self):
        events = []
        def extract(path,directory):
            directory.mkdir(parents=True,exist_ok=True)
            frame = directory/'already-written.png'
            frame.write_bytes(b'synthetic frame')
            events.append(frame)
            return [{'path':str(frame)}]
        with patch.object(self.server,'extract_video_reference_frames',side_effect=extract):
            with self.assertRaises(HTTPException) as caught:
                self.server.create_accessory_candidate('Invalid','object','detect_and_classify',['video.mp4'])
        self.assertEqual(caught.exception.status_code,400)
        self.assertTrue(events[0].exists())
        self.assertEqual(self.events,[])
        path = self.image('factory-failure')
        with patch.object(self.server,'ensure_accessory_ai_profile',side_effect=RuntimeError('synthetic profile failure')), \
             patch.object(self.server,'write_thumbnail',side_effect=AssertionError('profile failed before thumbnail')):
            with self.assertRaises(RuntimeError):
                self.server.create_accessory_candidate('Fail','object','detect_and_classify',[str(path)],material_alpha_policy='opaque')
        self.assertEqual(self.events,[])
        written = []
        original = self.server.write_thumbnail
        def thumbnail(image,path,angle):
            written.append(path)
            return original(image,path,angle)
        with patch.object(self.server,'write_thumbnail',side_effect=thumbnail), \
             patch.object(self.server,'ensure_pose_collection_image_jobs',side_effect=RuntimeError('synthetic pose failure')):
            with self.assertRaises(RuntimeError):
                self.server.create_accessory_candidate('Fail pose','object','detect_and_classify',[str(path)],material_alpha_policy='opaque')
        self.assertTrue(written[0].exists())
        self.assertNotIn('save',[event[0] for event in self.events])


if __name__ == '__main__': unittest.main()
