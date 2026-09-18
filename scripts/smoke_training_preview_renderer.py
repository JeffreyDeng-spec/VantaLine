"""Original preview rendering pixels, metadata, random sequence and failure contracts."""
from contextlib import ExitStack
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def digest(value):
    if isinstance(value, np.ndarray): return hashlib.sha256(value.tobytes()).hexdigest()
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class RenderFixture:
    def __init__(self, api, root, *, documents=True, sprite='direct', tag=1):
        self.api, self.root, self.documents, self.sprite, self.tag = api, Path(root), documents, sprite, tag
        self.events = []; self.rng = None; self.source_metadata = []; self.masks = []; self.custom_masks = []
        self.sprite_count = 0; self.background = {'source': 'fixture', 'tag': tag, 'nested': []}
        self.asset = np.full((12, 16, 3), [tag, 70, 180], np.uint8)
        self.sprite_image = np.full((20, 30, 3), [90, tag, 40], np.uint8)
        self.sprite_mask = np.zeros((20, 30), np.uint8); self.sprite_mask[2:18, 3:27] = 255
        self.bindings = {}
        simple = {
            'accessory_material_type': lambda item: item['material_type'],
            'physical_render_size_px': lambda item, material: (120, 80) if material == 'text' else (70, 50),
            'load_preview_asset_with_metadata': lambda item: (self.asset, {'unused': True}),
            'clean_sprite_assets': lambda item: [{'pose_family': 'lying'}],
            'available_object_pose_families': lambda item: ['upright', 'lying'],
            'object_pose_render_size_hint': lambda item, family: (77, 55),
            'physical_render_size_for_sprite': lambda item, material, meta=None: (120, 80) if material == 'text' else (84, 56),
            'grid_position_for_center': lambda center: 'middle',
            'pose_family_is_top_view': lambda family, source_size=None: family == 'upright',
            'source_position_for_render_policy': lambda target, angle, family, rng: 'left',
            'pose_selection_reason': lambda target, source, angle: 'fixture-selection',
            'restore_object_sprite_source_orientation_for_render': lambda image, mask, meta, *, top_view_pose: (image.copy(), mask.copy(), 3.25, 8.75),
            'long_axis_unified_render_box': lambda w, h, long, short: (long + 2, short + 1),
            'public_output_url': lambda path: '/fixture/' + Path(path).name,
        }
        for name, fn in simple.items(): self.bindings[name] = self.traced(name, fn)
        for name, fn in {
            'render_training_background': self.render_background,
            'random_center_inside_background': self.random_center,
            'choose_object_center_inside_background': self.choose_center,
            'load_rectified_document_asset_with_metadata': self.load_document,
            'choose_object_pose_family': self.choose_pose,
            'object_render_pose_policy': self.pose_policy,
            'load_object_preview_sprite': self.load_sprite,
            'paste_rectified_document_asset': self.paste_document,
            'paste_physical_object_asset': self.paste_object,
        }.items(): self.bindings[name] = self.traced(name, fn)
        for name in ['visible_mask_size_px', 'mask_from_polygon', 'placement_box_points', 'rotated_rect_tuple',
                     'visible_polygon_from_mask', 'polygon_max_pair_distance_px']:
            self.bindings[name] = self.traced(name, getattr(api, name))

    def summary(self, value):
        if isinstance(value, np.random.Generator):
            if self.rng is None: self.rng = value
            assert value is self.rng, 'renderer changed RNG instance'
            return {'rng_state': digest(value.bit_generator.state)}
        if isinstance(value, np.ndarray): return {'shape': list(value.shape), 'dtype': str(value.dtype), 'pixels': digest(value)}
        if isinstance(value, Path): return value.name
        if isinstance(value, (tuple, list)): return [self.summary(item) for item in value]
        if isinstance(value, dict): return {str(key): self.summary(item) for key, item in value.items()}
        return value

    def traced(self, name, fn):
        def run(*args, **kwargs):
            self.events.append([name, self.summary(args), self.summary(kwargs)])
            return fn(*args, **kwargs)
        return run

    def install(self, stack):
        for name, fn in self.bindings.items(): stack.enter_context(patch.object(self.api, name, fn))
        return self

    def render_background(self, rng, split, background):
        canvas = np.empty((900, 1280, 3), np.uint8)
        canvas[:, :, 0] = np.arange(1280, dtype=np.uint16) % 251
        canvas[:, :, 1] = np.arange(900, dtype=np.uint16)[:, None] % 241
        canvas[:, :, 2] = self.tag
        self.canvas = canvas
        return canvas, self.background

    def random_center(self, rng, size, angle):
        rng.integers(0, 5)
        return (640, 450)

    def choose_center(self, rng, size, angle, placed):
        rng.integers(0, 7)
        return (640, 450), {'object_non_overlap_attempts': 2, 'object_overlap_area_px': 0.0, 'object_non_overlap_pass': True}

    def load_document(self, item, rng):
        rng.integers(0, 3)
        if not self.documents: return None
        meta = {'asset_path': 'synthetic.png', 'document_asset_index': 1, 'document_asset_count': 2,
                'document_asset_selection_policy': 'fixture', 'source_image_size_px': [16, 12],
                'canonical_asset_dimensions_px': [16, 12], 'asset_method': 'synthetic', 'asset_source': 'fixture'}
        self.source_metadata.append(meta)
        return self.asset, meta

    def choose_pose(self, sprites, rng): rng.integers(0, 3); return 'lying'

    def pose_policy(self, family, rng):
        rng.integers(0, 4)
        return {'perspective_rotation_degrees': 90.0, 'placement_angle_degrees': 0.0,
                'source_selection_rule': 'fixture-rule', 'desired_lie_direction': 'left',
                'desired_facing_direction': 'up', 'render_pose_policy': 'fixture-pose'}

    def load_sprite(self, item, rng, target, *, pose_family, source_position):
        self.sprite_count += 1; rng.integers(0, 3)
        if self.sprite == 'missing' or (self.sprite == 'rematch_missing' and self.sprite_count == 2): return None
        actual = 'right' if self.sprite.startswith('rematch') and self.sprite_count == 1 else source_position
        meta = {'source_position': actual, 'source_pose_family': pose_family, 'source_object_size_px': [24, 16],
                'source_image_size_px': [30, 20], 'canonical_asset_dimensions_px': [30, 20],
                'sprite_index': self.sprite_count, 'render_footprint_px': [84, 56],
                'source_restore_rotation_degrees_requested': 8.75, 'method': 'fixture-sprite'}
        self.source_metadata.append(meta)
        return self.sprite_image, self.sprite_mask, meta

    def paste(self, canvas):
        mask = self.custom_masks.pop(0) if self.custom_masks else np.zeros(canvas.shape[:2], np.uint8)
        if not np.any(mask) and not getattr(self, 'keep_empty_mask', False): mask[410:470, 590:670] = 255
        self.masks.append(mask)
        canvas[mask > 24] = (35, 70, self.tag)
        return {'_visible_mask_canvas': mask, 'render_box_px': [86, 57], 'render_visible_footprint_px': [80, 60],
                'render_resize_policy': 'fixture-paste', 'non_uniform_scaling_applied': False,
                'document_full_asset_pasted': True}

    def paste_document(self, canvas, image, center, size, angle): return self.paste(canvas)
    def paste_object(self, canvas, image, mask, center, long, short, angle, *, preserve_aspect_ratio):
        assert preserve_aspect_ratio is True
        return self.paste(canvas)

    def render(self, accessories, **kwargs):
        self.rng = None
        return self.api.draw_training_preview(accessories, self.root / 'preview.png', seed=17, **kwargs)

    def snapshot(self, result):
        pixels = cv2.imread(str(self.root / 'preview.png'))
        return {'pixels_sha256': digest(pixels), 'metadata_sha256': digest(self.summary(result)),
                'calls_sha256': digest(self.events), 'calls_count': len(self.events),
                'rng_state_sha256': digest(self.rng.bit_generator.state)}


def item(name, material='object'):
    return {'id': name, 'name': name.title(), 'material_type': material,
            'physical_size': {'length_mm': 50, 'width_mm': 30, 'height_mm': 20}, 'material_alpha_policy': 'solid'}


CASES = {
    'empty': ({}, [], {}),
    'mixed_placeholders': ({'documents': False, 'sprite': 'missing'}, [item('o1'), item('d1', 'text'), item('o2'), item('d2', 'text')], {}),
    'document': ({}, [item('d1', 'text')], {'split': 'val', 'background_set_id': 'background'}),
    'sprite': ({}, [item('o1')], {'pose_family_policy': 'upright'}),
    'rematch': ({'sprite': 'rematch'}, [item('o1')], {'pose_family_policy': 'invalid'}),
    'rematch_missing': ({'sprite': 'rematch_missing'}, [item('o1')], {}),
    'occluded': ({}, [item('d1', 'text'), item('o1')], {}),
}


class PreviewRendererContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ); cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='preview-renderer-root-')
        root = Path(cls.runtime.name); (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()

    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='preview-renderer-')))
        for target in ['requests.request', 'subprocess.Popen', 'os.kill']:
            self.stack.enter_context(patch(target, side_effect=AssertionError('unexpected external operation')))

    def fixture(self, **kwargs): return RenderFixture(self.api, self.root, **kwargs).install(self.stack)

    def test_original_pixels_full_metadata_call_sequence_and_rng_goldens(self):
        # The production lock includes overlapping OpenCV distributions. Select by
        # the imported runtime version, never by the observed output or hash.
        name = ('training_preview_renderer_opencv410.json' if cv2.__version__ == '4.10.0'
                else 'training_preview_renderer.json')
        baseline = json.loads((Path(__file__).resolve().parents[1] / 'tests/backend_contract' / name).read_text())
        for name, (settings, accessories, kwargs) in CASES.items():
            with self.subTest(case=name), ExitStack() as stack:
                fixture = RenderFixture(self.api, self.root, **settings).install(stack)
                result = fixture.render(copy.deepcopy(accessories), **kwargs)
                self.assertEqual(fixture.snapshot(result), baseline['cases'][name])
                self.assertIs(result['background'], fixture.background)
                for metadata in fixture.source_metadata: self.assertNotIn('target_position', metadata)
                for mask in fixture.masks: self.assertEqual(int(np.count_nonzero(mask)), 4800)

    def test_stable_material_order_initial_object_calls_and_no_input_mutation(self):
        fixture = self.fixture(documents=False, sprite='missing')
        values = [item('o1'), item('d1', 'text'), item('o2'), item('d2', 'text')]; before = copy.deepcopy(values)
        result = fixture.render(values)
        self.assertEqual(values, before)
        self.assertEqual([label['id'] for label in result['labels']], ['d1', 'd2', 'o1', 'o2'])
        self.assertEqual([label['z_index'] for label in result['labels']], [1, 2, 3, 4])
        names = [entry[0] for entry in fixture.events]
        self.assertEqual(names.count('random_center_inside_background'), 4)
        self.assertEqual(names.count('choose_object_center_inside_background'), 2)
        self.assertEqual(names.count('load_preview_asset_with_metadata'), 2)
        for position, name in enumerate(names):
            if name == 'load_preview_asset_with_metadata':
                self.assertEqual(names[position - 2:position], ['physical_render_size_px', 'random_center_inside_background'])
                self.assertEqual(names[position + 1], 'clean_sprite_assets')

    def test_sprite_rematch_success_keeps_center_and_size_calls_and_shallow_metadata(self):
        fixture = self.fixture(sprite='rematch')
        result = fixture.render([item('o1')]); label = result['labels'][0]
        names = [entry[0] for entry in fixture.events]
        self.assertEqual(fixture.sprite_count, 2); self.assertEqual(names.count('object_pose_render_size_hint'), 3)
        self.assertEqual(names.count('physical_render_size_for_sprite'), 3)
        self.assertEqual(names.count('choose_object_center_inside_background'), 1)
        self.assertEqual(label['actual_source_position'], 'left'); self.assertEqual(label['sprite_index'], 2)
        self.assertEqual(label['source_restore_rotation_degrees'], 3.25)
        self.assertEqual(label['ignored_source_restore_rotation_degrees'], 8.75)
        self.assertIs(label['source_image_size_px'], fixture.source_metadata[-1]['source_image_size_px'])
        self.assertIs(label['render_footprint_px'], fixture.source_metadata[-1]['render_footprint_px'])
        self.assertNotIn('target_position', fixture.source_metadata[-1])

    def test_sprite_rematch_failure_keeps_first_and_never_retries(self):
        fixture = self.fixture(sprite='rematch_missing')
        label = fixture.render([item('o1')])['labels'][0]
        self.assertEqual(fixture.sprite_count, 2)
        self.assertEqual(label['actual_source_position'], 'right'); self.assertEqual(label['sprite_index'], 1)
        self.assertFalse(label['target_source_position_match'])
        self.assertEqual([entry[0] for entry in fixture.events].count('object_pose_render_size_hint'), 2)

    def test_rematch_exception_propagates_without_retry_restore_paste_or_output(self):
        fixture = self.fixture(sprite='rematch'); error = OSError('second sprite read failed')
        original = fixture.bindings['load_object_preview_sprite']; calls = []
        def read(*args, **kwargs):
            calls.append((args, kwargs))
            if len(calls) == 2: raise error
            return original(*args, **kwargs)
        with patch.object(self.api, 'load_object_preview_sprite', side_effect=read) as sprite, \
             patch.object(self.api, 'restore_object_sprite_source_orientation_for_render', wraps=fixture.bindings['restore_object_sprite_source_orientation_for_render']) as restore, \
             patch.object(self.api, 'paste_physical_object_asset', wraps=fixture.bindings['paste_physical_object_asset']) as paste, \
             patch.object(cv2, 'imwrite') as write, patch.object(self.api, 'public_output_url', return_value='/unexpected') as link:
            with self.assertRaises(OSError) as caught: fixture.render([item('o1')])
            self.assertIs(caught.exception, error); self.assertEqual(sprite.call_count, 2)
            self.assertEqual(calls[1][1], {'pose_family': 'lying', 'source_position': 'left'})
            for callback in [restore, paste, write, link]: callback.assert_not_called()
        self.assertFalse((self.root / 'preview.png').exists())

    def test_paste_metadata_overrides_placement_and_document_source_metadata(self):
        fixture = self.fixture()
        original = fixture.paste
        def paste(canvas):
            return {**original(canvas), 'object_non_overlap_attempts': 77, 'render_scale_basis': 'paste-override', 'asset_path': 'paste-document.png'}
        fixture.paste = paste
        labels = fixture.render([item('o1'), item('d1', 'text')])['labels']
        self.assertEqual(labels[0]['document_asset_path'], 'paste-document.png')
        self.assertEqual(labels[1]['object_non_overlap_attempts'], 77)
        self.assertEqual(labels[1]['render_policy'], 'paste-override')

    def test_occlusion_copies_masks_keeps_amodal_plus_one_and_dropped_labels(self):
        fixture = self.fixture()
        first = np.zeros((900, 1280), np.uint8); first[400:440, 600:640] = 255
        second = np.zeros_like(first); second[400:440, 620:640] = 25
        originals = [first.copy(), second.copy()]; fixture.custom_masks = [first, second]
        labels = fixture.render([item('d1', 'text'), item('d2', 'text')])['labels']
        self.assertEqual(labels[0]['amodal_bbox_xyxy'], [600, 400, 640, 440])
        self.assertEqual(labels[0]['occlusion_fraction'], 0.5)
        self.assertEqual(labels[0]['final_visible_footprint_px'], [20, 40])
        self.assertEqual(labels[0]['visible_polygon_xy'], [[600, 400], [600, 439], [619, 439], [619, 400]])
        self.assertEqual(labels[1]['amodal_bbox_xyxy'], [620, 400, 640, 440])
        for actual, expected in zip(fixture.masks, originals): np.testing.assert_array_equal(actual, expected)
        self.assertEqual(len(labels), 2)

    def test_render_occlusion_alpha_24_is_excluded_and_25_counts(self):
        fixture = self.fixture()
        first = np.zeros((900, 1280), np.uint8); first[400:420, 600:620] = 25
        # The faint column is excluded from both the full area and the amodal extent.
        first[400:420, 599] = 24
        second = np.zeros_like(first); second[400:420, 600:610] = 24; second[400:420, 610:620] = 25
        fixture.custom_masks = [first, second]
        labels = fixture.render([item('d1', 'text'), item('d2', 'text')])['labels']
        self.assertEqual(labels[0]['amodal_bbox_xyxy'], [600, 400, 620, 420])
        self.assertEqual(labels[0]['occlusion_fraction'], 0.5)
        self.assertEqual(labels[0]['visible_polygon_xy'], [[600, 400], [600, 419], [609, 419], [609, 400]])
        self.assertEqual(labels[1]['amodal_bbox_xyxy'], [610, 400, 620, 420])
        self.assertEqual(labels[1]['occlusion_fraction'], 0.0)
        self.assertEqual(int(np.count_nonzero(first == 25)), 400)
        self.assertEqual(int(np.count_nonzero(second == 25)), 200)

    def test_detection_thresholds_strict_rounding_and_short_circuit(self):
        fixture = self.fixture()
        first = np.zeros((900, 1280), np.uint8); first[400:500, 600:700] = 255; first[500, 600] = 255
        second = np.zeros_like(first); second[400:450, 600:700] = 255; second[500, 600] = 255
        fixture.custom_masks = [first, second]
        with patch.object(self.api, 'DETECTION_MIN_VISIBLE_AREA_PX', 5000), patch.object(self.api, 'DETECTION_MAX_OCCLUSION_FRACTION', 0.5):
            labels = fixture.render([item('d1', 'text'), item('d2', 'text')])['labels']
        self.assertEqual(labels[0]['occlusion_fraction'], 0.5); self.assertFalse(labels[0]['detection_dropped'])
        class ForbiddenComparison:
            def __lt__(self, other): raise AssertionError('unexpected max threshold access')
            def __gt__(self, other): raise AssertionError('unexpected min threshold access')
        fixture = self.fixture(); fixture.keep_empty_mask = True
        with patch.object(self.api, 'DETECTION_MIN_VISIBLE_AREA_PX', ForbiddenComparison()), patch.object(self.api, 'DETECTION_MAX_OCCLUSION_FRACTION', ForbiddenComparison()):
            label = fixture.render([item('d1', 'text')])['labels'][0]
        self.assertIsNone(label['amodal_bbox_xyxy']); self.assertTrue(label['detection_dropped'])

    def test_non_array_mask_leaves_detection_fields_absent(self):
        fixture = self.fixture()
        fixture.paste = lambda canvas: {'_visible_mask_canvas': [[1, 2]], 'render_box_px': [3, 4]}
        label = fixture.render([item('d1', 'text')])['labels'][0]
        self.assertNotIn('amodal_bbox_xyxy', label); self.assertNotIn('detection_dropped', label)
        self.assertEqual(label['render_box_px'], [3, 4])

    def test_imwrite_false_still_links_exception_never_links_and_url_error_keeps_file(self):
        fixture = self.fixture()
        with patch.object(cv2, 'imwrite', return_value=False) as write:
            self.assertEqual(fixture.render([])['url'], '/fixture/preview.png'); write.assert_called_once()
        fixture.events.clear()
        with patch.object(cv2, 'imwrite', side_effect=OSError('write failure')) as write:
            with self.assertRaisesRegex(OSError, 'write failure'): fixture.render([])
            write.assert_called_once()
        self.assertNotIn('public_output_url', [entry[0] for entry in fixture.events])
        with patch.object(self.api, 'public_output_url', side_effect=ValueError('url failure')) as link:
            with self.assertRaisesRegex(ValueError, 'url failure'): fixture.render([])
            link.assert_called_once()
        self.assertTrue((self.root / 'preview.png').is_file())

    def test_asset_failure_propagates_once_before_output(self):
        fixture = self.fixture()
        with patch.object(self.api, 'load_preview_asset_with_metadata', side_effect=RuntimeError('asset failure')) as asset, patch.object(cv2, 'imwrite') as write:
            with self.assertRaisesRegex(RuntimeError, 'asset failure'): fixture.render([item('o1')])
            asset.assert_called_once(); write.assert_not_called()
        names = [entry[0] for entry in fixture.events]
        self.assertNotIn('choose_object_center_inside_background', names); self.assertNotIn('public_output_url', names)


    def test_renderer_dependency_first_error_propagates_without_retry(self):
        scenarios = ['empty', 'mixed_placeholders', 'document', 'sprite', 'rematch', 'rematch_missing']
        for scenario in scenarios:
            settings, accessories, kwargs = CASES[scenario]
            with ExitStack() as scope:
                fixture = RenderFixture(self.api, self.root, **settings).install(scope)
                fixture.render(copy.deepcopy(accessories), **kwargs)
                counts = {}
                for event in fixture.events: counts[event[0]] = counts.get(event[0], 0) + 1
            for name, count in counts.items():
                indices = range(1, count + 1) if count <= 3 else [1, count]
                for index in indices:
                    with self.subTest(scenario=scenario, name=name, index=index), ExitStack() as scope:
                        fixture = RenderFixture(self.api, self.root, **settings).install(scope)
                        original = fixture.bindings[name]; calls = []; failure = RuntimeError('renderer-first-error')
                        def fail_once(*args, **values):
                            calls.append(None)
                            if len(calls) == index: raise failure
                            return original(*args, **values)
                        scope.enter_context(patch.object(self.api, name, fail_once))
                        write = scope.enter_context(patch.object(cv2, 'imwrite', wraps=cv2.imwrite))
                        with self.assertRaises(RuntimeError) as caught:
                            fixture.render(copy.deepcopy(accessories), **kwargs)
                        self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)
                        self.assertEqual(write.call_count, 1 if name == 'public_output_url' else 0)

    def test_new_renderer_getter_first_error_propagates_without_retry(self):
        from dataclasses import replace
        service = self.api._training_preview_renderer
        fields = [('assets', 'object_sprite'), ('assets', 'restore'), ('sizes', 'pose'), ('sizes', 'unified'),
                  ('poses', 'top_view'), ('layout', 'mask'), ('thresholds', 'min_visible_area'), ('thresholds', 'max_occlusion')]
        for group_name, field in fields:
            scenario = 'mixed_placeholders' if field == 'mask' else 'rematch'
            settings, accessories, kwargs = CASES[scenario]
            group = getattr(service, group_name); original = getattr(group, field)
            with ExitStack() as scope:
                fixture = RenderFixture(self.api, self.root, **settings).install(scope)
                observed = Mock(wraps=original)
                scope.enter_context(patch.object(service, group_name, replace(group, **{field: observed})))
                fixture.render(copy.deepcopy(accessories), **kwargs)
                count = observed.call_count
            self.assertGreater(count, 0, field)
            for index in range(1, count + 1):
                with self.subTest(group=group_name, field=field, index=index), ExitStack() as scope:
                    fixture = RenderFixture(self.api, self.root, **settings).install(scope)
                    calls = []; failure = RuntimeError('renderer-getter-first')
                    def fail_once():
                        calls.append(None)
                        if len(calls) == index: raise failure
                        return original()
                    scope.enter_context(patch.object(service, group_name, replace(group, **{field: fail_once})))
                    write = scope.enter_context(patch.object(cv2, 'imwrite', wraps=cv2.imwrite))
                    with self.assertRaises(RuntimeError) as caught: fixture.render(copy.deepcopy(accessories), **kwargs)
                    self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index); write.assert_not_called()

    def test_renderer_callback_capture_before_argument_effects(self):
        for site in ('mask_text', 'mask_object', 'top_initial', 'top_sprite', 'top_rematch', 'pose_sprite', 'pose_rematch', 'object_rematch', 'restore', 'unified'):
            for mode in ('ordinary', 'prior', 'missing'):
                with self.subTest(site=site, mode=mode), ExitStack() as scope:
                    api = self.api
                    f = RenderFixture(api, self.root, documents=site != 'mask_text', sprite='missing' if site == 'mask_object' else 'rematch' if site in ('top_rematch', 'pose_rematch', 'object_rematch') else 'direct').install(scope)
                    target = 'mask_from_polygon' if site.startswith('mask_') else 'pose_family_is_top_view' if site.startswith('top_') else 'object_pose_render_size_hint' if site.startswith('pose_') else 'load_object_preview_sprite' if site == 'object_rematch' else 'restore_object_sprite_source_orientation_for_render' if site == 'restore' else 'long_axis_unified_render_box'
                    events = []
                    armed = [False]
                    done = RuntimeError('selected-callback')
                    base = getattr(api, target)

                    def prior():
                        events.append('prior')
                        armed[0] = True
                        setattr(api, target, None if mode == 'missing' else ports['B'] if mode == 'prior' else ports['A'])

                    def argument():
                        if armed[0]:
                            events.append('argument')
                            setattr(api, target, ports['C'])

                    def selected(label, *args, **kwargs):
                        if armed[0]:
                            events.append(label)
                            raise done
                        return base(*args, **kwargs)
                    ports = {label: Mock(side_effect=lambda *a, _label=label, **k: selected(_label, *a, **k)) for label in ('A', 'B', 'C')}
                    scope.enter_context(patch.object(api, target, ports['A']))

                    class Text(str):

                        def __str__(inner):
                            argument()
                            return 'lying'
                    if site.startswith('mask_'):

                        class Canvas(np.ndarray):

                            @property
                            def shape(inner):
                                argument()
                                return np.ndarray.shape.__get__(inner)
                        original = f.render_background

                        def background(*a, **k):
                            value, meta = original(*a, **k)
                            return (value.view(Canvas), meta)
                        scope.enter_context(patch.object(api, 'render_training_background', background))
                        name = 'polylines' if site == 'mask_text' else 'circle'
                        original_cv = getattr(cv2, name)

                        def drawn(*a, **k):
                            result = original_cv(*a, **k)
                            prior()
                            return result
                        scope.enter_context(patch.object(cv2, name, drawn))
                    elif site == 'top_initial':

                        class Family(str):

                            def __bool__(inner):
                                argument()
                                return True
                        scope.enter_context(patch.object(api, 'choose_object_pose_family', lambda *a: Family('lying')))
                        original = f.pose_policy

                        def policy(*a):
                            value = original(*a)
                            prior()
                            return value
                        scope.enter_context(patch.object(api, 'object_render_pose_policy', policy))
                    elif site in ('top_sprite', 'top_rematch', 'pose_sprite', 'pose_rematch'):
                        original = f.load_sprite
                        wanted = 2 if site.endswith('rematch') else 1

                        def sprite(*a, **k):
                            image, mask, meta = original(*a, **k)
                            if f.sprite_count == wanted:
                                meta['source_pose_family'] = Text('lying')
                                if site.startswith('top_'):
                                    prior()
                            return (image, mask, meta)
                        scope.enter_context(patch.object(api, 'load_object_preview_sprite', sprite))
                        if site.startswith('pose_'):
                            calls = [0]

                            def top(*a, **k):
                                calls[0] += 1
                                if calls[0] == wanted + 1:
                                    prior()
                                return False
                            scope.enter_context(patch.object(api, 'pose_family_is_top_view', top))
                    elif site == 'object_rematch':

                        class Position:

                            def __ne__(inner, other):
                                prior()
                                return True
                        original = f.load_sprite

                        def base(*a, **k):
                            image, mask, meta = original(*a, **k)
                            if f.sprite_count == 1:
                                meta.update(source_position=Position(), source_pose_family=Text('lying'))
                            return (image, mask, meta)
                    elif site == 'restore':

                        class Top:

                            def __bool__(inner):
                                argument()
                                return True
                        scope.enter_context(patch.object(api, 'pose_family_is_top_view', lambda *a: Top()))
                        original = getattr(api, 'physical_render_size_for_sprite')

                        def size(*a, **k):
                            value = original(*a, **k)
                            prior()
                            return value
                        scope.enter_context(patch.object(api, 'physical_render_size_for_sprite', size))
                    else:

                        class Visible(list):

                            def __getitem__(inner, key):
                                if key == 0:
                                    argument()
                                return super().__getitem__(key)

                        def visible(*a):
                            prior()
                            return Visible([24, 16])
                        scope.enter_context(patch.object(api, 'visible_mask_size_px', visible))
                    captured = None
                    try:
                        f.render([item('case', 'text' if site == 'mask_text' else 'object')])
                    except BaseException as exc:
                        captured = exc
                    if mode == 'missing':
                        self.assertIs(type(captured), TypeError)
                    else:
                        self.assertIs(captured, done)
                    expected = ['prior', 'argument'] + ([] if mode == 'missing' else ['B' if mode == 'prior' else 'A'])
                    self.assertEqual(events, expected)
                    self.assertEqual(ports['B'].call_count, int(mode == 'prior'))
                    ports['C'].assert_not_called()

    def test_renderer_callback_binding_refreshes_between_objects(self):
        for target in ('mask_from_polygon', 'restore_object_sprite_source_orientation_for_render', 'long_axis_unified_render_box'):
            for missing in (False, True):
                with self.subTest(target=target, missing=missing), ExitStack() as scope:
                    f = RenderFixture(self.api, self.root, documents=target != 'mask_from_polygon').install(scope)
                    api = self.api
                    base = getattr(api, target)
                    events = []

                    def later(*args, **kwargs):
                        events.append('B')
                        return base(*args, **kwargs)

                    def first(*args, **kwargs):
                        events.append('A')
                        setattr(api, target, None if missing else later)
                        return base(*args, **kwargs)
                    scope.enter_context(patch.object(api, target, first))
                    write = scope.enter_context(patch.object(cv2, 'imwrite', wraps=cv2.imwrite))
                    captured = None
                    try:
                        f.render([item('first', 'text' if target == 'mask_from_polygon' else 'object'), item('second', 'text' if target == 'mask_from_polygon' else 'object')])
                    except BaseException as exc:
                        captured = exc
                    if missing:
                        self.assertIs(type(captured), TypeError)
                    else:
                        self.assertIsNone(captured)
                    self.assertEqual(events, ['A'] if missing else ['A', 'B'])
                    self.assertEqual(write.call_count, 0 if missing else 1)

    def test_independent_renderers_no_constructor_reads_root_access_or_shared_thresholds(self):
        from local_inspection_service.training.preview_ports import (PreviewAssets, PreviewLayout, PreviewPoses, PreviewSizes, PreviewSurface, PreviewThresholds)
        from local_inspection_service.training.preview_renderer import PreviewRenderer
        from local_inspection_service.training import preview_geometry as geometry, preview_masks as masks
        from local_inspection_service.training.preview_placement import PreviewPlacement
        fixtures = [RenderFixture(self.api, self.root, tag=tag) for tag in [1, 2]]
        renderers, minima, maxima = [], [], []
        visible = masks.PreviewMasks(lambda: masks.contour_to_polygon, lambda mask, ratio: visible.visible_polygons_from_mask(mask, ratio))
        placement = PreviewPlacement(lambda: (1280, 900), lambda: geometry.constrained_center_range,
                                     geometry.rotated_rect_tuple, lambda: geometry.rotated_rect_overlap_area,
                                     Mock(side_effect=AssertionError('unexpected placement sampling')),
                                     Mock(side_effect=AssertionError('unexpected overlap sampling')))
        for index, fixture in enumerate(fixtures):
            b = fixture.bindings
            minimum = Mock(return_value=0); maximum = Mock(return_value=[1.0, -1.0][index])
            minima.append(minimum); maxima.append(maximum)
            renderers.append(PreviewRenderer(
                b['accessory_material_type'], PreviewSurface(b['render_training_background'], b['public_output_url']),
                PreviewAssets(b['load_rectified_document_asset_with_metadata'], b['load_preview_asset_with_metadata'],
                              b['clean_sprite_assets'], (lambda fn=b['load_object_preview_sprite']: fn), (lambda fn=b['restore_object_sprite_source_orientation_for_render']: fn),
                              b['paste_rectified_document_asset'], b['paste_physical_object_asset']),
                PreviewSizes(b['physical_render_size_px'], b['physical_render_size_for_sprite'], (lambda fn=b['object_pose_render_size_hint']: fn),
                             b['visible_mask_size_px'], (lambda fn=b['long_axis_unified_render_box']: fn)),
                PreviewPoses(b['available_object_pose_families'], b['choose_object_pose_family'], b['object_render_pose_policy'],
                             (lambda fn=b['pose_family_is_top_view']: fn), b['grid_position_for_center'], b['source_position_for_render_policy'], b['pose_selection_reason']),
                PreviewLayout(b['random_center_inside_background'], b['choose_object_center_inside_background'], lambda: masks.mask_from_polygon,
                              placement.placement_box_points, geometry.rotated_rect_tuple, visible.visible_polygon_from_mask, geometry.polygon_max_pair_distance_px),
                PreviewThresholds(minimum, maximum)))
        for fixture in fixtures: self.assertEqual(fixture.events, []); self.assertIsNone(fixture.rng)
        for callback in minima + maxima: callback.assert_not_called()
        for name in fixtures[0].bindings: self.stack.enter_context(patch.object(self.api, name, side_effect=AssertionError('root callback reached')))
        for index in [1, 0, 1, 0]:
            fixture = fixtures[index]; fixture.rng = None
            result = renderers[index].draw_training_preview([item('doc', 'text')], self.root / 'preview.png', 17)
            self.assertIs(result['background'], fixture.background)
            self.assertEqual(result['labels'][0]['detection_dropped'], bool(index))
            self.assertEqual(cv2.imread(str(self.root / 'preview.png'))[420, 610].tolist(), [35, 70, index + 1])
        self.assertEqual([callback.call_count for callback in minima + maxima], [2, 2, 2, 2])
        fixtures[0].keep_empty_mask = True; fixtures[0].rng = None
        minima[0].side_effect = AssertionError('min read without amodal box'); maxima[0].side_effect = AssertionError('max read without amodal box')
        result = renderers[0].draw_training_preview([item('doc', 'text')], self.root / 'empty.png', 17)
        self.assertTrue(result['labels'][0]['detection_dropped'])
        self.assertEqual((minima[0].call_count, maxima[0].call_count), (2, 2))
        fixtures[0].keep_empty_mask = False; fixtures[0].rng = None
        minima[0].side_effect = None; minima[0].return_value = 5000
        result = renderers[0].draw_training_preview([item('doc', 'text')], self.root / 'small.png', 17)
        self.assertTrue(result['labels'][0]['detection_dropped'])
        self.assertEqual((minima[0].call_count, maxima[0].call_count), (3, 2))


if __name__ == '__main__': unittest.main()
