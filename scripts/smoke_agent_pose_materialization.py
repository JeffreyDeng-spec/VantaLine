"""Draft contracts against the original Agent pose materialization functions."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
from contextlib import ExitStack
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path.cwd()))

class AgentPoseMaterializationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ)
        cls.environment.start()
        cls.root = tempfile.TemporaryDirectory(prefix='pose-materialization-contract-')
        (Path(cls.root.name) / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=cls.root.name, VANTALINE_DATA_STORE='json', LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.root.cleanup()
        cls.environment.stop()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory(dir=self.root.name)))
        for name in ('requests.sessions.Session.request', 'urllib.request.urlopen', 'subprocess.Popen', 'os.kill'):
            self.stack.enter_context(patch(name, side_effect=AssertionError('External operation forbidden')))

    def replace(self, name, **kwargs):
        return self.stack.enter_context(patch.object(self.api, name, **kwargs))

    def test_chroma_green_short_circuit_keeps_result_identity(self):
        item = {}
        fraction = self.replace('accessory_reference_chroma_fraction', return_value=0.2)
        self.replace('CHROMA_SCREEN_REFERENCE_FRACTION_THRESHOLD', new=0.2)
        screen = {'label': 'green'}
        normalize = self.replace('normalize_chroma_screen', return_value=screen)
        result = self.api.choose_agent_mcp_chroma_screen(item)
        self.assertIs(result, screen)
        fraction.assert_called_once_with(item, 'green')
        normalize.assert_called_once_with('green')
        self.assertEqual(result['reference_chroma_fraction'], 0.2)

    def test_chroma_blue_red_order_and_fallback(self):
        item = {}
        fraction = self.replace('accessory_reference_chroma_fraction', side_effect=[0.9, 0.8, 0.7])
        self.replace('CHROMA_SCREEN_REFERENCE_FRACTION_THRESHOLD', new=0.2)
        screen = {}
        normalize = self.replace('normalize_chroma_screen', return_value=screen)
        self.assertIs(self.api.choose_agent_mcp_chroma_screen(item), screen)
        self.assertEqual([c.args[1] for c in fraction.call_args_list], ['green', 'blue', 'red'])
        normalize.assert_called_once_with('blue')
        self.assertEqual(screen, {'reference_green_fraction': 0.9, 'reference_blue_fraction': 0.8, 'reference_red_fraction': 0.7})

    def test_dedup_no_removal_preserves_list_and_invalid_entries(self):
        assets = [None, {'kind': 'other'}, {'kind': 'agent_mcp_pose_reference', 'pose_id': 'top'}]
        item = {'normalized_assets': assets}
        self.assertFalse(self.api.dedup_agent_mcp_pose_references(item))
        self.assertIs(item['normalized_assets'], assets)
        self.assertFalse(self.api.dedup_agent_mcp_pose_references({'normalized_assets': {}}))

    def test_dedup_first_pose_and_empty_key_win_without_copying_objects(self):
        first = {'kind': 'agent_mcp_pose_reference', 'pose_id': 'top', 'path': 'first'}
        empty = {'kind': 'agent_mcp_pose_reference'}
        retained = {'kind': 'other'}
        assets = [first, {'kind': 'agent_mcp_pose_reference', 'pose_id': 'top', 'path': 'second'}, empty, {'kind': 'agent_mcp_pose_reference', 'path': ''}, retained]
        item = {'normalized_assets': assets}
        self.assertTrue(self.api.dedup_agent_mcp_pose_references(item))
        self.assertIsNot(item['normalized_assets'], assets)
        self.assertEqual(item['normalized_assets'], [first, empty, retained])
        self.assertIs(item['normalized_assets'][0], first)
        self.assertEqual(len(assets), 5)

    def cutouts(self):
        names = ['chroma_screen_object_cutout', 'precise_green_plate_cutout', 'green_conveyor_object_cutout', 'ai_background_cutout_with_bbox', 'object_cutout_from_image', 'green_screen_object_cutout_with_bbox']
        callbacks = [self.replace(name, return_value=None) for name in names]
        usable = self.replace('usable_object_cutout', return_value=None)
        return callbacks, usable

    def test_cutout_invalid_input_does_not_call_sources(self):
        callbacks, usable = self.cutouts()
        self.assertIsNone(self.api.segment_agent_mcp_pose_object(None, None))
        self.assertIsNone(self.api.segment_agent_mcp_pose_object(np.zeros((4, 4)), None))
        for callback in callbacks:
            callback.assert_not_called()
        usable.assert_not_called()

    def test_cutout_first_usable_preserves_bbox_and_stops_fallbacks(self):
        callbacks, usable = self.cutouts()
        image = np.zeros((4, 6, 3), dtype=np.uint8)
        cut, mask, bbox = object(), object(), [1, 2, 3, 4]
        callbacks[0].return_value = (cut, mask, bbox)
        usable.return_value = (cut, mask)
        screen = {'label': 'green'}
        result = self.api.segment_agent_mcp_pose_object(image, None, screen)
        self.assertIs(result[0], cut)
        self.assertIs(result[1], mask)
        self.assertIs(result[2], bbox)
        callbacks[0].assert_called_once_with(image, screen)
        usable.assert_called_once_with((cut, mask), image.shape)
        for callback in callbacks[1:]:
            callback.assert_not_called()

    def test_cutout_rejects_unusable_sources_in_original_order(self):
        callbacks, usable = self.cutouts()
        image = np.zeros((4, 6, 3), dtype=np.uint8)
        rng = object()
        events = []
        for i, callback in enumerate(callbacks):
            callback.side_effect = lambda *args, index=i: (events.append(index) or ((object(), object()) if index == 4 else (object(), object(), (0, 0, 2, 2))))
        self.assertIsNone(self.api.segment_agent_mcp_pose_object(image, rng))
        self.assertEqual(events, list(range(6)))
        self.assertEqual(usable.call_count, 6)
        callbacks[4].assert_called_once_with(image, rng)
        callbacks[5].assert_called_once_with(image, rng)

    def test_cutout_generic_fallback_uses_full_source_bbox(self):
        callbacks, usable = self.cutouts()
        image = np.zeros((4, 6, 3), dtype=np.uint8)
        cut, mask = object(), object()
        callbacks[4].return_value = (cut, mask)
        usable.return_value = (cut, mask)
        self.assertEqual(self.api.segment_agent_mcp_pose_object(image, None), (cut, mask, (0, 0, 6, 4)))
        callbacks[5].assert_not_called()

    def builder(self, count=1):
        item = {'created_at': 7, 'physical_size': {'width': 12}, 'normalized_assets': [{'kind': 'retained'}]}
        self.material = self.replace('accessory_material_type', return_value='object')
        self.dedup = self.replace('dedup_agent_mcp_pose_references', return_value=False)
        self.refs = [{'path': 'pose' + str(i) + '.png', 'pose_id': 'top', 'call_id': 'call' + str(i)} for i in range(count)]
        self.replace('agent_mcp_pose_reference_assets', return_value=self.refs)
        self.existing = self.replace('clean_sprite_assets', return_value=[])
        self.complete = self.replace('clean_sprites_policy_complete', return_value=True)
        self.alpha = type('SyntheticPolicy', (str,), {})('synthetic')
        self.policy = self.replace('object_alpha_material_policy', return_value=self.alpha)
        self.replace('accessory_uid', return_value='part')
        self.replace('NORMALIZED_DIR', new=self.directory)
        self.rng = object()
        self.rng_factory = self.stack.enter_context(patch.object(self.api.np.random, 'default_rng', return_value=self.rng))
        self.clock = self.stack.enter_context(patch.object(self.api.time, 'time', return_value=10))
        self.replace('resolve_service_path', side_effect=Path)
        self.image = np.zeros((10, 12, 3), dtype=np.uint8)
        self.imread = self.stack.enter_context(patch.object(self.api.cv2, 'imread', return_value=self.image))
        self.screen_value = {'label': 'green'}
        self.replace('normalize_chroma_screen', return_value=self.screen_value)
        self.cut, self.mask = object(), object()
        self.segment = self.replace('segment_agent_mcp_pose_object', return_value=(self.cut, self.mask, (1, 2, 7, 8)))
        self.replace('safe_record_id', side_effect=str)
        self.footprint = self.replace('pose_render_footprint_metadata', return_value={'footprint': 'synthetic'})
        self.writer = self.replace('write_clean_sprite', side_effect=lambda path, cut, mask, metadata: {'kind': 'clean_object_sprite', 'path': str(path), **metadata})
        self.normalize = self.replace('normalize_sprite_family_canvases')
        self.scale = self.replace('apply_upright_scale_correction_metadata')
        self.laying = self.replace('apply_laying_standard_render_size_hints')
        return item

    def test_builder_text_exits_before_dedup_or_policy(self):
        item = self.builder()
        self.material.return_value = 'text'
        self.assertFalse(self.api.build_clean_sprites_from_agent_mcp_poses(item))
        self.dedup.assert_not_called()
        self.policy.assert_not_called()
        self.writer.assert_not_called()

    def test_builder_reuses_only_complete_ai_provenance(self):
        item = self.builder()
        self.existing.return_value = [{'agent_mcp_pose_reference_path': 'old'}]
        self.assertFalse(self.api.build_clean_sprites_from_agent_mcp_poses(item))
        self.complete.assert_called_once_with(item, self.existing.return_value)
        self.policy.assert_not_called()
        self.writer.assert_not_called()

    def test_builder_dedup_forces_rebuild_even_with_complete_cached_assets(self):
        item = self.builder()
        self.existing.return_value = [{'agent_mcp_pose_reference_path': 'old'}]
        self.dedup.return_value = True
        self.assertTrue(self.api.build_clean_sprites_from_agent_mcp_poses(item))
        self.assertEqual(self.writer.call_count, 1)
        self.assertEqual(self.policy.call_count, 2)
        self.assertEqual(item['clean_sprite_status'], 'ready')
        self.assertEqual(self.complete.call_count, 1)

    def test_builder_writes_all_inputs_then_caps_and_preserves_metadata_aliases(self):
        item = self.builder(19)
        retained = item['normalized_assets'][0]
        events = []
        self.normalize.side_effect = lambda assets: events.append(('normalize', len(assets)))
        self.scale.side_effect = lambda assets, size: events.append(('scale', len(assets)))
        self.laying.side_effect = lambda assets: events.append(('laying', len(assets)))
        self.assertTrue(self.api.build_clean_sprites_from_agent_mcp_poses(item))
        self.assertEqual(self.writer.call_count, 19)
        self.assertEqual(events, [('normalize', 18), ('scale', 18), ('laying', 18)])
        self.assertIs(item['normalized_assets'][0], retained)
        self.assertEqual((item['clean_sprite_count'], item['clean_sprite_expected_count'], item['clean_sprite_preprocessed_at']), (18, 19, 10))
        metadata = self.writer.call_args_list[0].args[3]
        self.assertIs(metadata['physical_size_mm'], item['physical_size'])
        self.assertIs(metadata['material_alpha_policy'], self.alpha)
        self.assertIs(metadata['chroma_screen'], self.screen_value)
        self.assertEqual((metadata['pose_family'], metadata['source_pose_collection_job_id'], metadata['source_object_size_px']), ('upright', 'legacy_clean_sprite', [6, 6]))
        self.rng_factory.assert_called_once_with(7)
        self.scale.assert_called_once_with(item['normalized_assets'][1:], item['physical_size'])

    def test_builder_no_decodable_images_retains_existing_assets_and_partial_policy(self):
        item = self.builder()
        assets = item['normalized_assets']
        self.imread.return_value = None
        self.assertFalse(self.api.build_clean_sprites_from_agent_mcp_poses(item))
        self.assertIs(item['normalized_assets'], assets)
        self.assertIs(item['material_alpha_policy'], self.alpha)
        self.assertNotIn('clean_sprite_status', item)
        self.segment.assert_not_called()
        self.writer.assert_not_called()

    def test_builder_late_writer_error_leaves_policy_without_asset_commit(self):
        item = self.builder(2)
        assets = item['normalized_assets']
        self.writer.side_effect = [{'kind': 'clean_object_sprite'}, OSError('write')]
        with self.assertRaisesRegex(OSError, 'write'):
            self.api.build_clean_sprites_from_agent_mcp_poses(item)
        self.assertIs(item['normalized_assets'], assets)
        self.assertIs(item['material_alpha_policy'], self.alpha)
        self.assertEqual(self.writer.call_count, 2)
        self.normalize.assert_not_called()
        self.assertNotIn('clean_sprite_status', item)

    def materialization(self):
        task, config = {'id': 'task'}, {}
        path = self.directory / 'pose.png'
        path.write_bytes(b'synthetic')
        item = {'id': 'part', 'normalized_assets': []}
        call = {'tool': self.api.AGENT_MCP_TOOL_POSE_IMAGE, 'status': 'completed', 'accessory_id': 'part', 'output_path': str(path), 'pose_id': 'top'}
        state = {'tool_calls': [call]}
        self.replace('agent_mcp_orchestration', return_value=state)
        self.lookup = self.replace('accessory_lookup_by_id', return_value={'part': item})
        self.clock = self.replace('agent_mcp_now', return_value=123)
        self.replace('resolve_service_path', side_effect=Path)
        self.replace('public_output_url', return_value='/synthetic')
        self.screen_value = {'label': 'green'}
        self.replace('normalize_chroma_screen', return_value=self.screen_value)
        self.digest = self.replace('file_sha256', return_value=None)
        self.sources = self.replace('object_photo_highlight_source_paths', return_value=[])
        self.ready = self.replace('photo_highlight_clean_sprites_ready', return_value=False)
        self.build = self.replace('build_clean_sprites_from_agent_mcp_poses', return_value=False)
        return task, config, state, item, call, path

    def test_materialization_photo_policy_short_circuits_lookup(self):
        task, config, state, item, call, path = self.materialization()
        state['photo_highlight_sprite_policy'] = {}
        self.assertFalse(self.api.materialize_agent_mcp_pose_assets(task, config))
        self.lookup.assert_not_called()
        self.clock.assert_not_called()
        self.build.assert_not_called()

    def test_materialization_adds_nullable_hash_reference_and_marks_change(self):
        task, config, state, item, call, path = self.materialization()
        self.assertTrue(self.api.materialize_agent_mcp_pose_assets(task, config))
        asset = item['normalized_assets'][0]
        self.assertEqual((asset['path'], asset['sha256'], asset['created_at']), (str(path), None, 123))
        self.assertIs(asset['chroma_screen'], self.screen_value)
        self.digest.assert_called_once_with(path)
        self.build.assert_called_once_with(item, force=False)
        self.assertEqual((state['materialized_pose_assets_at'], state['updated_at']), (123, 123))

    def test_materialization_existing_path_and_photo_ready_avoid_hash_and_rebuild(self):
        task, config, state, item, call, path = self.materialization()
        asset = {'kind': 'agent_mcp_pose_reference', 'path': str(path)}
        item['normalized_assets'] = [asset]
        self.ready.return_value = True
        self.assertFalse(self.api.materialize_agent_mcp_pose_assets(task, config))
        self.assertIs(item['normalized_assets'][0], asset)
        self.digest.assert_not_called()
        self.build.assert_not_called()
        self.assertNotIn('updated_at', state)

    def test_materialization_ignores_unfinished_missing_and_unsupported_calls(self):
        task, config, state, item, call, path = self.materialization()
        unsupported = self.directory / 'pose.txt'
        unsupported.write_text('synthetic')
        state['tool_calls'] = [{**call, 'status': 'running'}, {**call, 'output_path': str(self.directory / 'missing.png')}, {**call, 'output_path': str(unsupported)}]
        self.assertFalse(self.api.materialize_agent_mcp_pose_assets(task, config))
        self.assertEqual(item['normalized_assets'], [])
        self.build.assert_not_called()
        self.digest.assert_not_called()

    def test_materialization_rebuild_only_updates_timestamps_when_builder_changes(self):
        task, config, state, item, call, path = self.materialization()
        item['normalized_assets'] = [{'kind': 'agent_mcp_pose_reference', 'path': str(path)}]
        self.build.return_value = True
        self.assertTrue(self.api.materialize_agent_mcp_pose_assets(task, config))
        self.build.assert_called_once_with(item, force=False)
        self.assertEqual(state['updated_at'], 123)
        self.digest.assert_not_called()

    def test_chroma_fraction_callback_is_refreshed_after_green(self):
        item = {}
        replacement = Mock(return_value=0.1)
        def green(*args):
            self.api.accessory_reference_chroma_fraction = replacement
            return 0.9
        original = self.replace('accessory_reference_chroma_fraction', side_effect=green)
        self.replace('CHROMA_SCREEN_REFERENCE_FRACTION_THRESHOLD', new=0.2)
        normalize = self.replace('normalize_chroma_screen', return_value={})
        self.api.choose_agent_mcp_chroma_screen(item)
        original.assert_called_once_with(item, 'green')
        self.assertEqual([c.args[1] for c in replacement.call_args_list], ['blue', 'red'])
        normalize.assert_called_once_with('blue')

    def test_cutout_usability_callback_is_refreshed_after_source(self):
        callbacks, usable = self.cutouts()
        image = np.zeros((4, 6, 3), dtype=np.uint8)
        cut, mask, bbox = object(), object(), (0, 0, 2, 2)
        replacement = Mock(return_value=(cut, mask))
        def source(*args):
            self.api.usable_object_cutout = replacement
            return cut, mask, bbox
        callbacks[0].side_effect = source
        result = self.api.segment_agent_mcp_pose_object(image, None)
        self.assertIsNotNone(result)
        self.assertIs(result[0], cut)
        usable.assert_not_called()
        replacement.assert_called_once_with((cut, mask), image.shape)

    def test_builder_evaluates_alpha_policy_twice_with_refreshed_callback(self):
        item = self.builder()
        second = type('SecondPolicy', (str,), {})('second')
        replacement = Mock(return_value=second)
        def policy(*args):
            self.api.object_alpha_material_policy = replacement
            return self.alpha
        self.policy.side_effect = policy
        self.assertTrue(self.api.build_clean_sprites_from_agent_mcp_poses(item))
        self.assertIs(item['material_alpha_policy'], self.alpha)
        self.assertIs(self.writer.call_args.args[3]['material_alpha_policy'], second)
        self.policy.assert_called_once_with(item)
        replacement.assert_called_once_with(item)

    def test_materialization_provided_digest_skips_hash_callback(self):
        task, config, state, item, call, path = self.materialization()
        call['sha256'] = 'already-bound'
        self.assertTrue(self.api.materialize_agent_mcp_pose_assets(task, config))
        self.assertEqual(item['normalized_assets'][0]['sha256'], 'already-bound')
        self.digest.assert_not_called()



    def test_materialization_constructors_do_not_read_capabilities(self):
        from dataclasses import fields
        from local_inspection_service.agent import pose_materialization_ports as ports
        from local_inspection_service.agent.pose_chroma_policy import PoseChromaPolicy
        from local_inspection_service.agent.pose_cutout_pipeline import PoseCutoutPipeline
        from local_inspection_service.agent.pose_sprite_builder import PoseSpriteBuilder
        from local_inspection_service.agent.pose_asset_materialization import PoseAssetMaterialization
        getters = []
        def group(port_type):
            values = {f.name: Mock(return_value=None) for f in fields(port_type)}
            getters.extend(values.values())
            return port_type(**values)
        PoseChromaPolicy(group(ports.PoseChromaSources))
        PoseCutoutPipeline(group(ports.PoseCutoutSources))
        PoseSpriteBuilder(group(ports.PoseChromaSources), group(ports.PoseSpritePolicy), group(ports.PoseSpriteRuntime), group(ports.PoseSpriteImages), group(ports.PoseSpriteMetadata), group(ports.PoseAssetMedia))
        PoseAssetMaterialization(group(ports.PoseChromaSources), group(ports.PoseMaterializationState), group(ports.PoseAssetMedia), group(ports.PoseMaterializationSprites))
        for getter in getters:
            getter.assert_not_called()

    def test_materialization_two_live_compositions_keep_callbacks_independent(self):
        from dataclasses import fields
        from local_inspection_service.agent import pose_materialization_ports as ports
        from local_inspection_service.agent.pose_chroma_policy import PoseChromaPolicy
        from local_inspection_service.agent.pose_cutout_pipeline import PoseCutoutPipeline
        from local_inspection_service.agent.pose_sprite_builder import PoseSpriteBuilder
        from local_inspection_service.agent.pose_asset_materialization import PoseAssetMaterialization
        def group(port_type, **selected):
            return port_type(**{f.name: selected.get(f.name, lambda: None) for f in fields(port_type)})
        def make(name):
            screen = {'label': name}
            chroma_ports = group(ports.PoseChromaSources, fraction=lambda: lambda *args: 0.0, screen=lambda: lambda value: screen, threshold=lambda: 0.2)
            chroma = PoseChromaPolicy(chroma_ports)
            cut, mask = np.full((2, 2, 3), len(name), dtype=np.uint8), np.ones((2, 2), dtype=np.uint8)
            bbox = [0, 0, 2, 2]
            cutouts = group(ports.PoseCutoutSources, chroma=lambda: lambda *args: (cut, mask, bbox), usable=lambda: lambda *args: (cut, mask))
            pipeline = PoseCutoutPipeline(cutouts)
            builder = PoseSpriteBuilder(chroma_ports, group(ports.PoseSpritePolicy, material=lambda: lambda item: 'text'), group(ports.PoseSpriteRuntime), group(ports.PoseSpriteImages), group(ports.PoseSpriteMetadata), group(ports.PoseAssetMedia))
            state = {'photo_highlight_sprite_policy': {'name': name}}
            materialization = PoseAssetMaterialization(chroma_ports, group(ports.PoseMaterializationState, current=lambda: lambda task: state), group(ports.PoseAssetMedia), group(ports.PoseMaterializationSprites))
            return chroma, pipeline, builder, materialization, screen, cut, bbox
        instances = {name: make(name) for name in ('first', 'second')}
        image = np.zeros((4, 6, 3), dtype=np.uint8)
        with patch.object(self.api, 'accessory_reference_chroma_fraction', side_effect=AssertionError('root fraction')), patch.object(self.api, 'chroma_screen_object_cutout', side_effect=AssertionError('root cutout')), patch.object(self.api, 'accessory_material_type', side_effect=AssertionError('root material')), patch.object(self.api, 'agent_mcp_orchestration', side_effect=AssertionError('root state')):
            for name in ('first', 'second', 'first'):
                chroma, pipeline, builder, materialization, screen, cut, bbox = instances[name]
                self.assertIs(chroma.choose_agent_mcp_chroma_screen({}), screen)
                result = pipeline.segment_agent_mcp_pose_object(image, None)
                self.assertIs(result[0], cut)
                self.assertIs(result[2], bbox)
                self.assertFalse(builder.build_clean_sprites_from_agent_mcp_poses({}))
                self.assertFalse(materialization.materialize_agent_mcp_pose_assets({}, {}))


if __name__ == '__main__':
    unittest.main()
