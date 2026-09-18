"""Offline contracts for sample planning, annotations and dataset generation."""
from collections import Counter
from contextlib import ExitStack
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class DatasetFixture:
    def __init__(self, root):
        self.root = Path(root)
        self.events = []
        self.config = {'synthetic': True}
        self.selected = [{'id': 'a', 'name': 'Alpha'}, {'id': 'b', 'name': 'Manual', 'ocr': True}]
        self.task = {'job_id': 'fixture-job', 'selected_accessory_ids': ['a', 'b'], 'sample_count': 3,
                     'seed': 41, 'mode': 'yolo_ocr', 'owner_user_id': 'alice', 'owner_username': 'Alice',
                     'pipeline_task_id': 'pipeline', 'pipeline_task_name': 'Synthetic pipeline'}
        self.plan = [
            self.item(0, 'train', True, ['a', 'b']),
            self.item(1, 'val', False, ['a'], missing=['b']),
            self.item(2, 'test', False, ['a', 'b', 'a'], extra=['a']),
        ]
        self.load = Mock(side_effect=lambda: self.event('load') or self.config)
        self.ensure = Mock(side_effect=lambda *args: self.event('ensure', *args) or True)
        self.save = Mock(side_effect=lambda *args: self.event('save', *args))
        self.select = Mock(side_effect=lambda *args: self.event('select', *args) or self.selected)
        self.pose = Mock(side_effect=lambda value: self.event('pose', value) or 'lying')
        self.background = Mock(side_effect=lambda value: self.event('background', value) or 'synthetic-background')
        self.planner = Mock(side_effect=lambda *args: self.event('plan', *args) or self.plan)
        self.output = Mock(side_effect=lambda *args: self.event('output', *args) or self.root / 'datasets')
        self.render = Mock(side_effect=self.draw)
        self.update = Mock(side_effect=lambda *args, **kwargs: self.event('update', args, kwargs))
        self.ocr = Mock(side_effect=lambda item: item.get('ocr', False))
        self.public = Mock(side_effect=lambda path: '/synthetic/' + path.relative_to(self.root).as_posix())

    @staticmethod
    def item(index, split, truth, present, missing=None, extra=None):
        missing, extra = missing or [], extra or []
        return {'index': index, 'split': split, 'is_true': truth, 'required_accessory_ids': ['a', 'b'],
                'present_accessory_ids': present, 'missing_accessory_ids': missing, 'extra_accessory_ids': extra,
                'missing_count': len(missing), 'extra_count': len(extra), 'pose_family_policy': 'lying',
                'false_reason': 'extra_one_accessory' if extra else 'missing_accessory' if missing else None}

    def event(self, name, *args):
        self.events.append((name, args))

    def draw(self, selected, path, **kwargs):
        self.event('render', selected, path, kwargs)
        cv2.imwrite(str(path), np.full((900, 1280, 3), 80, dtype=np.uint8))
        labels = [
            {'id': 'a', 'name': 'Alpha', 'amodal_bbox_xyxy': [128, 90, 512, 450]},
            {'id': 'b', 'name': 'Manual', 'amodal_bbox_xyxy': [640, 0, 1280, 900], 'material_type': 'text',
             'document_asset_path': 'synthetic-document', 'document_asset_index': 0, 'document_asset_count': 2,
             'document_asset_selection_policy': 'fixture', 'document_asset_source': 'fixture-source',
             'document_asset_method': 'fixture-method'},
            {'id': 'a', 'detection_dropped': True, 'amodal_bbox_xyxy': [0, 0, 10, 10]},
            {'id': 'unknown', 'amodal_bbox_xyxy': None},
        ]
        return {'url': '/synthetic/image', 'labels': labels,
                'background': {'background_id': 'bg1', 'background_source': 'fixture'}}

    def bind(self, api, stack):
        values = {'load_config': self.load, 'save_config': self.save,
                  'ensure_training_normalized_assets_for_selection': self.ensure, 'selected_accessories': self.select,
                  'normalize_preview_pose_family_policy': self.pose, 'selected_background_set_id': self.background,
                  'build_training_sample_plan': self.planner, 'output_write_dir_for_owner': self.output,
                  'draw_training_preview': self.render, 'update_training_task': self.update,
                  'accessory_uses_ocr': self.ocr, 'OUTPUT_DIR': self.root, 'public_output_url': self.public}
        for name, value in values.items():
            stack.enter_context(patch.object(api, name, value))


class TrainingDatasetContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ)
        cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='training-dataset-root-')
        root = Path(cls.runtime.name)
        (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.runtime.cleanup()
        cls.environment.stop()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='training-dataset-')))
        self.stack.enter_context(patch('requests.request', side_effect=AssertionError('unexpected network')))
        self.stack.enter_context(patch('subprocess.Popen', side_effect=AssertionError('unexpected process')))
        self.stack.enter_context(patch('os.kill', side_effect=AssertionError('unexpected signal')))

    def fixture(self):
        fixture = DatasetFixture(self.root)
        fixture.bind(self.api, self.stack)
        return fixture

    def test_estimate_bounds_formula_defaults_and_raw_input_errors(self):
        api = self.api
        self.assertEqual(api.training_estimate(25, True, True, 10, 640, 2, 'yolo'), {
            'sample_count': 25, 'estimated_minutes': 4, 'estimated_generate_minutes': 1,
            'estimated_train_minutes': 3, 'estimated_gb': 0.04, 'estimate_formula_version': 'gpu-cache-autobatch-v3'})
        self.assertEqual(api.training_estimate(20001, True, True, 501, 2000, 101, 'yolo_ocr'), {
            'sample_count': 20000, 'estimated_minutes': 59307, 'estimated_generate_minutes': 880,
            'estimated_train_minutes': 58427, 'estimated_gb': 35.16, 'estimate_formula_version': 'gpu-cache-autobatch-v3'})
        self.assertEqual(api.training_estimate(0), api.training_estimate(1))
        self.assertEqual(api.training_estimate(1, False, False)['estimated_minutes'], 1)
        self.assertEqual(api.training_estimate(30, True, True, 0, 0, 0), api.training_estimate(30, True, True, 1, 640, 1))
        for value, error in [('invalid', ValueError), (None, TypeError), (float('inf'), OverflowError)]:
            with self.assertRaises(error):
                api.training_estimate(value)

    def test_labels_exact_coordinates_and_yaml_bytes(self):
        api = self.api
        self.assertEqual(api.yolo_label_line(2, [[-1, 0], [100, 50], [200, 100]], 100, 100),
                         '2 0.000000 0.000000 1.000000 0.500000 1.000000 1.000000')
        self.assertIsNone(api.yolo_label_line(1, [[0, 0], [1, 1]]))
        self.assertEqual(api.yolo_detection_label_line(3, [90, 80, 10, 20], 100, 100), '3 0.500000 0.500000 0.800000 0.600000')
        self.assertEqual(api.yolo_detection_label_line(0, [-100, -100, 200, 200], 100, 100), '0 0.500000 0.500000 1.000000 1.000000')
        self.assertEqual(api.yolo_detection_label_line(0, [-100, 10, -50, 30], 100, 100), '0 0.000000 0.200000 0.500000 0.200000')
        self.assertEqual(api.yolo_detection_label_line(0, [-50, 10, 50, 30], 100, 100), '0 0.000000 0.200000 1.000000 0.200000')
        self.assertIsNone(api.yolo_detection_label_line(0, [1, 1, 1, 2]))
        self.assertIsNone(api.yolo_detection_label_line(0, [1, 2, 3]))
        with self.assertRaises(ZeroDivisionError):
            api.yolo_detection_label_line(0, [0, 0, 1, 1], 0)
        path = self.root / 'dataset.yaml'
        api.write_dataset_yaml(path, self.root, ['A B', '中文', '', 0, '__x__'])
        self.assertEqual(path.read_text(encoding='utf-8'), f'path: {self.root.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: A_B\n  1: class_1\n  2: class_2\n  3: class_3\n  4: x\n')
        with self.assertRaises(FileNotFoundError):
            api.write_dataset_yaml(self.root / 'absent/dataset.yaml', self.root, [])

    def test_split_counts_and_missing_sampling_boundaries(self):
        api = self.api
        for total, expected in [(0, (1, 0, 0)), (2, (2, 0, 0)), (3, (1, 1, 1)), (15, (11, 2, 2)), (200, (160, 20, 20))]:
            self.assertEqual(tuple(api.split_counts(total).values()), expected)
        rng = Mock()
        self.assertEqual(api.missing_count_for_false_sample(1, rng), 1)
        rng.random.assert_not_called()
        rng.random.return_value = 0.949999
        self.assertEqual(api.missing_count_for_false_sample(4, rng), 1)
        rng.choice.assert_not_called()
        rng.random.return_value = 0.95
        rng.choice.return_value = np.int64(3)
        self.assertEqual(api.missing_count_for_false_sample(4, rng), 3)
        rng.choice.assert_called_once()
        args, kwargs = rng.choice.call_args
        self.assertEqual(args, ([2, 3, 4],))
        np.testing.assert_array_equal(kwargs['p'], np.array([4/7, 2/7, 1/7]))

    def test_seeded_plan_exact_order_extra_negatives_and_aliases(self):
        selected = [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}]
        with patch.object(self.api, 'preview_pose_family_sequence', return_value=['lying', 'upright'] * 10) as pose:
            plan = self.api.build_training_sample_plan(selected, 20, 42, 'auto')
        pose.assert_called_once_with(selected, 20, 'auto')
        expected = [('train', False, 'a', ''), ('train', False, 'b', ''), ('train', False, 'b', ''),
                    ('train', True, '', ''), ('train', True, '', ''), ('train', True, '', ''), ('train', True, '', ''),
                    ('train', False, 'abc', ''), ('train', True, '', ''), ('train', False, 'c', ''),
                    ('train', True, '', ''), ('train', False, 'a', ''), ('train', True, '', ''), ('train', True, '', ''),
                    ('train', False, 'b', ''), ('train', False, '', 'a'), ('val', True, '', ''),
                    ('val', False, 'b', ''), ('test', False, 'b', ''), ('test', True, '', '')]
        self.assertEqual([(x['split'], x['is_true'], ''.join(x['missing_accessory_ids']), ''.join(x['extra_accessory_ids'])) for x in plan], expected)
        self.assertEqual([x['pose_family_policy'] for x in plan], ['lying', 'upright'] * 10)
        self.assertEqual([x['index'] for x in plan], list(range(20)))
        self.assertEqual(plan[15]['present_accessory_ids'], ['a', 'b', 'c', 'a'])
        self.assertEqual(plan[15]['false_reason'], 'extra_one_accessory')
        self.assertTrue(all(x['required_accessory_ids'] is plan[0]['required_accessory_ids'] for x in plan))
        self.assertIsNot(plan[15]['present_accessory_ids'], plan[15]['required_accessory_ids'])
        with patch.object(self.api, 'preview_pose_family_sequence', return_value=[]):
            minimal = self.api.build_training_sample_plan([{'id': 'a'}], 0, 42, 'auto')
            self.assertEqual(len(minimal), 1)
            self.assertIsNone(minimal[0]['pose_family_policy'])
            with self.assertRaises(ValueError):
                self.api.build_training_sample_plan([], 1, 42, 'auto')

    def test_generation_real_files_manifest_labels_and_render_order(self):
        f = self.fixture()
        with patch('time.time', return_value=1700000000.9):
            result = self.api.generate_training_dataset(f.task)
        directory = self.root / 'datasets/fixture-job'
        self.assertEqual(result, {'dataset_dir': str(directory), 'dataset_yaml': str(directory / 'dataset.yaml'), 'manifest_path': str(directory / 'manifest.json')})
        self.assertEqual([event[0] for event in f.events[:8]], ['load', 'ensure', 'save', 'select', 'pose', 'background', 'plan', 'output'])
        f.ensure.assert_called_once_with(f.config, ['a', 'b'])
        self.assertIs(f.ensure.call_args.args[0], f.config)
        f.save.assert_called_once_with(f.config)
        f.output.assert_called_once_with('training_datasets', 'alice')
        f.planner.assert_called_once_with(f.selected, 3, 41, 'lying')
        self.assertEqual(f.render.call_count, 3)
        self.assertEqual([[x['id'] for x in c.args[0]] for c in f.render.call_args_list], [['a', 'b'], ['a'], ['a', 'b', 'a']])
        self.assertIs(f.render.call_args_list[2].args[0][0], f.render.call_args_list[2].args[0][2])
        self.assertEqual([c.kwargs['seed'] for c in f.render.call_args_list], [41, 42, 43])
        self.assertEqual([c.kwargs['split'] for c in f.render.call_args_list], ['train', 'val', 'test'])
        self.assertEqual([c.kwargs['progress'] for c in f.update.call_args_list], [29, 50, 72])
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['created_at'], 1700000000)
        for key, value in {'sample_count': 3, 'true_count': 1, 'false_count': 2, 'model_variant': 'yolo_ocr', 'owner_user_id': 'alice',
                           'owner_username': 'Alice', 'pipeline_task_id': 'pipeline', 'pipeline_task_name': 'Synthetic pipeline',
                           'split_counts': {'train': 1, 'val': 1, 'test': 1}, 'selected_accessory_ids': ['a', 'b'],
                           'accessory_class_map': {'0': 'a', '1': 'b'}, 'class_accessory_map': {'a': 0, 'b': 1},
                           'required_accessory_counts': {'a': 1, 'b': 1}, 'ocr_accessory_ids': ['b'],
                           'false_reason_distribution': {'missing_accessory': 1, 'extra_one_accessory': 1},
                           'document_asset_index_distribution': {'0': 3}, 'document_asset_path_distribution': {'synthetic-document': 3},
                           'background_set_id_distribution': {'synthetic-background': 3}, 'background_id_distribution': {'bg1': 3}}.items():
            self.assertEqual(manifest[key], value, key)
        for sample in manifest['samples']:
            self.assertEqual(Path(sample['labels']).read_text(encoding='utf-8'), '0 0.250000 0.300000 0.300000 0.400000\n1 0.750000 0.500000 0.500000 1.000000\n')
            self.assertTrue(np.all(cv2.imread(sample['image']) == 80))
            self.assertTrue(sample['annotated_url'].startswith('/synthetic/datasets/fixture-job/previews/'))
            self.assertEqual(sample['document_assets'][0]['document_asset_index'], 0)
        self.assertEqual(len(list((directory / 'previews').rglob('*.jpg'))), 3)
        self.assertTrue(manifest['sample_generation_policy']['training_images_are_clean'])
        self.assertIn('>85%', manifest['sample_generation_policy']['occlusion_policy'])
        self.assertIn('220px', manifest['sample_generation_policy']['occlusion_policy'])

    def test_asset_config_save_exception_boundary_and_no_later_side_effects(self):
        f = self.fixture()
        failure = HTTPException(409, 'fixture asset error')
        f.ensure.side_effect = failure
        with self.assertRaises(HTTPException) as raised:
            self.api.generate_training_dataset(f.task)
        self.assertIs(raised.exception, failure)
        f.save.assert_called_once_with(f.config)
        f.select.assert_not_called()
        f.output.assert_not_called()
        f.save.reset_mock()
        f.ensure.side_effect = RuntimeError('unexpected asset failure')
        with self.assertRaisesRegex(RuntimeError, 'unexpected asset failure'):
            self.api.generate_training_dataset(f.task)
        f.save.assert_not_called()
        f.ensure.side_effect = failure
        f.save.side_effect = ValueError('save failure')
        with self.assertRaisesRegex(ValueError, 'save failure'):
            self.api.generate_training_dataset(f.task)
        f.select.assert_not_called()
        self.assertFalse((self.root / 'datasets').exists())

    def test_no_asset_change_bounds_seed_fallback_and_declared_count(self):
        f = self.fixture()
        f.ensure.side_effect = None
        f.ensure.return_value = False
        f.planner.side_effect = None
        f.planner.return_value = []
        for requested, expected in [(0, 100), (-1, 1), (30000, 20000)]:
            f.task.update(sample_count=requested, seed=0, mode=None)
            f.planner.reset_mock()
            with patch('time.time', side_effect=[123.456, 999]):
                result = self.api.generate_training_dataset(f.task)
            f.planner.assert_called_once_with(f.selected, expected, 123456, 'lying')
            manifest = json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'))
            self.assertEqual(manifest['sample_count'], expected)
            self.assertEqual(manifest['samples'], [])
            self.assertEqual(manifest['model_variant'], 'yolo')
        f.save.assert_not_called()
        f.render.assert_not_called()
        f.update.assert_not_called()

    def test_progress_is_original_plan_index_based_and_final_update(self):
        f = self.fixture()
        f.task['sample_count'] = 100
        f.plan = [f.item(i, 'train', True, ['a']) for i in [0, 1, 2, 97, 99]]
        self.api.generate_training_dataset(f.task)
        self.assertEqual([c.kwargs['completed_samples'] for c in f.update.call_args_list], [1, 2, 98, 100])
        self.assertEqual([c.kwargs['progress'] for c in f.update.call_args_list], [8, 9, 70, 72])
        self.assertEqual(f.render.call_count, 5)

    def test_render_and_update_failures_preserve_partial_files_without_retry(self):
        f = self.fixture()
        count = 0
        def render(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError('render unknown outcome')
            return f.draw(*args, **kwargs)
        f.render.side_effect = render
        with self.assertRaisesRegex(RuntimeError, 'render unknown outcome'):
            self.api.generate_training_dataset(f.task)
        self.assertEqual(f.render.call_count, 2)
        f.update.assert_called_once()
        directory = self.root / 'datasets/fixture-job'
        self.assertTrue((directory / 'images/train/sample_000001.png').exists())
        self.assertTrue((directory / 'labels/train/sample_000001.txt').exists())
        self.assertTrue((directory / 'previews/train/sample_000001_boxed.jpg').exists())
        self.assertFalse((directory / 'dataset.yaml').exists())
        self.assertFalse((directory / 'manifest.json').exists())
        f.render.side_effect = f.draw
        f.render.reset_mock()
        f.update.side_effect = ValueError('progress save')
        with self.assertRaisesRegex(ValueError, 'progress save'):
            self.api.generate_training_dataset(f.task)
        f.render.assert_called_once()
        self.assertFalse((directory / 'manifest.json').exists())

    def test_annotation_real_pixels_palette_skips_and_lexical_public_prefix(self):
        image = self.root / 'image.png'
        cv2.imwrite(str(image), np.zeros((100, 100, 3), dtype=np.uint8))
        output = self.root / 'nested/annotated.jpg'
        with patch.object(self.api, 'OUTPUT_DIR', self.root), patch.object(self.api, 'public_output_url', return_value='/fixture') as public:
            result = self.api.write_training_annotation_preview(image, [
                {'detection_dropped': True, 'amodal_bbox_xyxy': [0, 0, 90, 90]},
                {'name': 'B', 'amodal_bbox_xyxy': [10, 30, 60, 70]}, {'amodal_bbox_xyxy': []}], output)
            self.assertEqual(result, '/fixture')
            public.assert_called_once_with(output)
            rendered = cv2.imread(str(output))
            np.testing.assert_allclose(rendered[50, 10], [45, 125, 255], atol=25)
            self.assertTrue(np.all(rendered[90, 90] == 0))
            self.assertTrue(np.all(cv2.imread(str(image)) == 0))
            public.reset_mock()
            self.assertEqual(self.api.public_training_output_url(Path(str(self.root) + '-sibling/file')), '/fixture')
            public.assert_called_once()
            public.reset_mock()
            self.assertEqual(self.api.public_training_output_url(self.root.parent / 'elsewhere'), '')
            public.assert_not_called()
            self.assertEqual(self.api.write_training_annotation_preview(self.root / 'missing.png', [], output), '')
            public.assert_not_called()
            with patch.object(cv2, 'imwrite', return_value=False):
                self.assertEqual(self.api.write_training_annotation_preview(image, [], output), '/fixture')


    def test_request_background_identity_differs_from_task_owner_and_string_zero_seed(self):
        f = self.fixture()
        f.task.update(seed='0', model_variant='yolo', mode='yolo_ocr')
        f.background.side_effect = lambda value: 'background-' + self.api._request_user.get()['id']
        token = self.api._request_user.set({'id': 'bob'})
        try:
            result = self.api.generate_training_dataset(f.task)
        finally:
            self.api._request_user.reset(token)
        f.background.assert_called_once_with(None)
        f.output.assert_called_once_with('training_datasets', 'alice')
        f.planner.assert_called_once_with(f.selected, 3, 0, 'lying')
        manifest = json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'))
        self.assertEqual(manifest['background_set_id'], 'background-bob')
        self.assertEqual(manifest['owner_user_id'], 'alice')
        self.assertEqual(manifest['model_variant'], 'yolo_ocr')

    def test_duplicate_ids_reindexed_each_render_fixed_label_classes_and_shallow_metadata(self):
        f = self.fixture()
        first, last, newest = {'id': 7, 'name': 'First'}, {'id': '7', 'name': 'Last'}, {'id': '7', 'name': 'Newest'}
        f.selected = [first, last]
        f.plan = [f.item(i, 'train', True, ['7', '7']) for i in (0, 1)]
        background = {'background_id': 'shared', 'background_set_id': 'explicit'}
        seen = []
        def render(selected, path, **kwargs):
            seen.append(list(selected))
            if len(seen) == 1:
                f.selected.append(newest)
            return {'labels': [{'id': '7', 'amodal_bbox_xyxy': [0, 0, 640, 450]},
                               {'id': 'unknown', 'amodal_bbox_xyxy': [0, 0, 1280, 900]}], 'background': background}
        f.render.side_effect = render
        original_dumps = json.dumps
        captured = []
        def capture(value, **kwargs):
            captured.append(value)
            self.assertEqual(kwargs, {'indent': 2})
            return original_dumps(value, **kwargs)
        with patch.object(self.api, 'write_training_annotation_preview', return_value=''), \
             patch.object(self.api, 'yolo_detection_label_line', wraps=self.api.yolo_detection_label_line) as label, \
             patch('json.dumps', side_effect=capture):
            result = self.api.generate_training_dataset(f.task)
        self.assertEqual(seen, [[last, last], [newest, newest]])
        self.assertTrue(all(len(call.args) == 2 and not call.kwargs for call in label.call_args_list))
        self.assertEqual([call.args[0] for call in label.call_args_list], [1, 0, 1, 0])
        manifest = captured[0]
        self.assertEqual(manifest['class_names'], ['First', 'Last'])
        self.assertEqual(manifest['selected_accessory_ids'], [7, '7', '7'])
        self.assertEqual(manifest['class_accessory_map'], {'7': 2})
        self.assertEqual(manifest['accessory_class_map'], {'0': '7', '1': '7', '2': '7'})
        self.assertEqual(manifest['required_accessory_counts'], {'7': 1})
        self.assertIsInstance(manifest['split_counts'], Counter)
        for index, sample in enumerate(manifest['samples']):
            self.assertIs(sample['background'], background)
            self.assertIs(sample['required_accessory_ids'], f.plan[index]['required_accessory_ids'])
            self.assertIs(sample['present_accessory_ids'], f.plan[index]['present_accessory_ids'])
            self.assertEqual(Path(sample['labels']).read_text(), '1 0.250000 0.250000 0.500000 0.500000\n0 0.500000 0.500000 1.000000 1.000000\n')
        self.assertTrue(Path(result['manifest_path']).exists())

    def test_plan_ports_order_rounding_duplicate_ids_and_short_pose_sequence(self):
        events = []
        selected = [{'id': 'a'}, {'id': 'a'}]
        original_split = self.api.split_counts
        def split(count):
            events.append('split')
            return original_split(count)
        def pose(*args):
            events.append('pose')
            return ['upright']
        with patch.object(self.api, 'split_counts', side_effect=split), \
             patch.object(self.api, 'preview_pose_family_sequence', side_effect=pose) as pose_call, \
             patch.object(self.api, 'missing_count_for_false_sample', return_value=1) as missing:
            plan = self.api.build_training_sample_plan(selected, 10, 3, 'auto')
        self.assertEqual(events, ['split', 'pose'])
        pose_call.assert_called_once_with(selected, 10, 'auto')
        self.assertEqual(missing.call_count, 5)
        self.assertEqual(sum(bool(item['extra_accessory_ids']) for item in plan), 1)
        self.assertEqual(plan[0]['pose_family_policy'], 'upright')
        self.assertTrue(all(item['pose_family_policy'] is None for item in plan[1:]))
        for item in plan:
            self.assertEqual(item['required_accessory_ids'], ['a', 'a'])
            self.assertIs(item['required_accessory_ids'], plan[0]['required_accessory_ids'])
            if item['extra_accessory_ids']:
                self.assertEqual(item['present_accessory_ids'], ['a', 'a', 'a'])
            elif item['missing_accessory_ids']:
                self.assertEqual(item['present_accessory_ids'], [])

    def test_file_and_metadata_failures_stop_once_with_original_residue(self):
        original_write = Path.write_text
        for failure in ('label', 'annotation', 'yaml', 'ocr', 'serialize', 'manifest'):
            with self.subTest(failure=failure), ExitStack() as stack:
                f = DatasetFixture(self.root / failure)
                f.bind(self.api, stack)
                f.plan = f.plan[:1]
                def write(path, data, *args, **kwargs):
                    kind = 'label' if path.suffix == '.txt' else 'yaml' if path.name == 'dataset.yaml' else 'manifest'
                    if kind == failure:
                        if failure == 'manifest':
                            original_write(path, 'partial', encoding='utf-8')
                        raise OSError(failure + ' failure')
                    return original_write(path, data, *args, **kwargs)
                writes = stack.enter_context(patch.object(Path, 'write_text', autospec=True, side_effect=write))
                annotation = stack.enter_context(patch.object(self.api, 'write_training_annotation_preview', wraps=self.api.write_training_annotation_preview))
                if failure == 'annotation':
                    annotation.side_effect = RuntimeError('annotation failure')
                if failure == 'ocr':
                    f.ocr.side_effect = RuntimeError('ocr failure')
                if failure == 'serialize':
                    stack.enter_context(patch('json.dumps', side_effect=TypeError('serialize failure')))
                with self.assertRaisesRegex((OSError, RuntimeError, TypeError), failure + ' failure'):
                    self.api.generate_training_dataset(f.task)
                directory = f.root / 'datasets/fixture-job'
                f.render.assert_called_once()
                self.assertTrue((directory / 'images/train/sample_000001.png').exists())
                self.assertEqual((directory / 'labels/train/sample_000001.txt').exists(), failure != 'label')
                self.assertEqual((directory / 'previews/train/sample_000001_boxed.jpg').exists(), failure not in ('label', 'annotation'))
                self.assertEqual((directory / 'dataset.yaml').exists(), failure in ('ocr', 'serialize', 'manifest'))
                self.assertEqual((directory / 'manifest.json').exists(), failure == 'manifest')
                if failure == 'manifest':
                    self.assertEqual((directory / 'manifest.json').read_text(), 'partial')
                self.assertEqual(annotation.call_count, 0 if failure == 'label' else 1)
                self.assertEqual(f.update.call_count, 0 if failure in ('label', 'annotation') else 1)
                self.assertEqual(f.ocr.call_count, 1 if failure == 'ocr' else 2 if failure in ('serialize', 'manifest') else 0)
                attempted = [call.args[0].name for call in writes.call_args_list]
                self.assertEqual(attempted.count('sample_000001.txt'), 1)
                self.assertEqual(attempted.count('dataset.yaml'), 0 if failure in ('label', 'annotation') else 1)
                self.assertEqual(attempted.count('manifest.json'), 1 if failure == 'manifest' else 0)

    def test_empty_labels_and_colliding_yaml_names_keep_exact_bytes(self):
        f = self.fixture()
        f.plan = f.plan[:1]
        f.selected[0]['name'] = 'a b'
        f.selected[1]['name'] = 'a-b'
        f.render.side_effect = lambda *args, **kwargs: {'labels': []}
        with patch.object(self.api, 'write_training_annotation_preview', return_value=''):
            result = self.api.generate_training_dataset(f.task)
        directory = Path(result['dataset_dir'])
        self.assertEqual((directory / 'labels/train/sample_000001.txt').read_bytes(), b'')
        self.assertTrue((directory / 'dataset.yaml').read_text().endswith('  0: a_b\n  1: a_b\n'))

    def test_annotation_output_adapter_resolves_after_image_write(self):
        image = self.root / 'input.png'
        output = self.root / 'annotation.jpg'
        cv2.imwrite(str(image), np.zeros((20, 30, 3), dtype=np.uint8))
        old = Mock(return_value='old')
        late = Mock(return_value='late')
        original_write = cv2.imwrite
        def write(*args, **kwargs):
            self.api.public_training_output_url = late
            return original_write(*args, **kwargs)
        with patch.object(self.api, 'public_training_output_url', old), patch.object(cv2, 'imwrite', side_effect=write):
            self.assertEqual(self.api.write_training_annotation_preview(image, [], output), 'late')
        old.assert_not_called()
        late.assert_called_once_with(output)

    def test_generator_keeps_fully_and_partly_outside_amodal_labels(self):
        f = self.fixture()
        f.plan = f.plan[:1]
        f.render.side_effect = lambda *args, **kwargs: {'labels': [
            {'id': 'a', 'amodal_bbox_xyxy': [-1280, 90, -640, 270]},
            {'id': 'a', 'amodal_bbox_xyxy': [-640, 90, 640, 270]},
        ]}
        with patch.object(self.api, 'write_training_annotation_preview', return_value=''):
            result = self.api.generate_training_dataset(f.task)
        label = Path(result['dataset_dir']) / 'labels/train/sample_000001.txt'
        self.assertEqual(label.read_text(encoding='utf-8'),
                         '0 0.000000 0.200000 0.500000 0.200000\n0 0.000000 0.200000 1.000000 0.200000\n')


    @staticmethod
    def compose_dataset(f, identity):
        from local_inspection_service.training.annotations import AnnotationMedia, AnnotationPreview, TrainingOutputLinks, write_dataset_yaml, yolo_detection_label_line
        from local_inspection_service.training.dataset_generation import DatasetGenerator, DatasetRecords, DatasetPlanning, DatasetRendering
        root = Mock(return_value=f.root)
        links = TrainingOutputLinks(AnnotationMedia(root, f.public))
        preview = AnnotationPreview(links.public_training_output_url)
        occlusion, area = Mock(return_value=0.5), Mock(return_value=33)
        generator = DatasetGenerator(
            DatasetRecords(f.load, f.save, f.ensure, f.select, f.ocr),
            DatasetPlanning(lambda:f.pose, lambda:lambda value: 'background-' + identity.get()['id'], f.planner),
            DatasetRendering(lambda:f.render, lambda:yolo_detection_label_line, lambda:preview.write_training_annotation_preview,
                             write_dataset_yaml, occlusion, area), lambda:f.output, lambda:f.update)
        return generator, (root, occlusion, area)

    def test_independent_services_and_zero_provider_construction(self):
        from local_inspection_service.runtime.identity import RequestIdentity
        from local_inspection_service.training.sample_plan import SamplePlanner, split_counts, missing_count_for_false_sample
        identity = RequestIdentity()
        first, second = DatasetFixture(self.root / 'one'), DatasetFixture(self.root / 'two')
        for f, name in [(first, 'one'), (second, 'two')]:
            generator, providers = self.compose_dataset(f, identity)
            self.assertEqual(f.events, [])
            for provider in providers:
                provider.assert_not_called()
            with identity.bind({'id': name}), patch.object(self.api, 'load_config', side_effect=AssertionError('root dependency')):
                result = generator.generate_training_dataset(f.task)
            manifest = json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'))
            self.assertEqual(manifest['background_set_id'], 'background-' + name)
            self.assertIn('>50%', manifest['sample_generation_policy']['occlusion_policy'])
            self.assertIn('33px', manifest['sample_generation_policy']['occlusion_policy'])
            self.assertTrue(Path(result['manifest_path']).is_relative_to(f.root))
        self.assertIsNone(identity.get())
        poses = Mock(return_value=[None] * 10)
        planner = SamplePlanner(split_counts, missing_count_for_false_sample, poses)
        poses.assert_not_called()
        result = planner.build_training_sample_plan([{'id': 'x'}], 10, 42, 'auto')
        self.assertEqual(len(result), 10)
        poses.assert_called_once()

    def test_shared_generator_keeps_two_async_thread_identities_and_task_owners(self):
        import asyncio
        import threading
        from local_inspection_service.runtime.identity import RequestIdentity
        identity = RequestIdentity()
        f = DatasetFixture(self.root)
        f.output.side_effect = lambda kind, owner: self.root / owner
        generator, _ = self.compose_dataset(f, identity)
        barrier = threading.Barrier(2)
        original_pose = f.pose.side_effect
        def pose(value):
            barrier.wait(timeout=10)
            return original_pose(value)
        f.pose.side_effect = pose
        async def invoke(request_user, owner):
            with identity.bind({'id': request_user}):
                task = {**f.task, 'owner_user_id': owner}
                result = await asyncio.to_thread(generator.generate_training_dataset, task)
                self.assertEqual(identity.get()['id'], request_user)
                return json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'))
        async def run():
            return await asyncio.gather(invoke('request-a', 'task-b'), invoke('request-b', 'task-a'))
        first, second = asyncio.run(run())
        self.assertEqual((first['background_set_id'], first['owner_user_id']), ('background-request-a', 'task-b'))
        self.assertEqual((second['background_set_id'], second['owner_user_id']), ('background-request-b', 'task-a'))
        self.assertIsNone(identity.get())


    def test_dataset_captures_callback_before_argument_evaluation(self):
        api=self.api
        for stage in ('pose','background','output','draw','label','annotation','update'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(stage=stage,mode=mode),ExitStack() as stack:
                    f=DatasetFixture(self.root/(stage+'-'+mode));f.root.mkdir();f.bind(api,stack);f.plan=f.plan[:1];events=[]
                    field={'pose':'normalize_preview_pose_family_policy','background':'selected_background_set_id','output':'output_write_dir_for_owner','draw':'draw_training_preview','label':'yolo_detection_label_line','annotation':'write_training_annotation_preview','update':'update_training_task'}[stage]
                    original=getattr(api,field)
                    def callback(label):
                        def call(*args,**kwargs):events.append(label);return original(*args,**kwargs)
                        return call
                    stack.enter_context(patch.object(api,field,callback('A')))
                    def before():
                        if mode!='ordinary':setattr(api,field,callback('B') if mode=='prior' else None)
                    def argument():events.append('argument');setattr(api,field,callback('C'))
                    class Task(dict):
                        def get(self,key,default=None):
                            if key=={'pose':'preview_pose_family_policy','background':'background_set_id','output':'owner_user_id'}.get(stage):argument()
                            return super().get(key,default)
                        def __getitem__(self,key):
                            if stage=='update' and key=='job_id':
                                counts.append(True)
                                if len(counts)==2:argument()
                            return super().__getitem__(key)
                    counts=[];f.task=Task(f.task)
                    if stage in ('pose','background','output'):
                        old=f.select.side_effect
                        f.select.side_effect=lambda *args:before() or old(*args)
                    elif stage=='draw':
                        class Plan(dict):
                            def get(self,key,default=None):
                                if key=='pose_family_policy':argument()
                                return super().get(key,default)
                        f.plan[0]=Plan(f.plan[0]);old=f.output.side_effect
                        f.output.side_effect=lambda *args:before() or old(*args)
                    elif stage in ('label','annotation'):
                        draw=f.render.side_effect
                        class Label(dict):
                            def get(self,key,default=None):
                                if key=='id':argument()
                                return super().get(key,default)
                        class Rendered(dict):
                            def get(self,key,default=None):
                                if key=='labels':
                                    reads.append(True)
                                    if len(reads)==2:argument()
                                return super().get(key,default)
                        reads=[]
                        def render(*args,**kwargs):
                            value=draw(*args,**kwargs);before()
                            if stage=='label':value['labels']=[Label(value['labels'][0])]
                            else:value=Rendered(value)
                            return value
                        f.render.side_effect=render
                    else:
                        old_annotation=api.write_training_annotation_preview
                        stack.enter_context(patch.object(api,'write_training_annotation_preview',side_effect=lambda *args:before() or old_annotation(*args)))
                    caught=None
                    try:api.generate_training_dataset(f.task)
                    except BaseException as error:caught=error
                    self.assertIn('argument',events)
                    if mode=='missing':
                        self.assertIsInstance(caught,TypeError);self.assertFalse(any(x in events for x in ('A','B','C')))
                    else:
                        self.assertIsNone(caught);calls=[x for x in events if x in ('A','B','C')]
                        self.assertTrue(calls);self.assertEqual(calls[0],'A' if mode=='ordinary' else 'B')
                        self.assertLess(events.index('argument'),events.index(calls[0]))


    def test_first_dependency_failure_is_not_retried_and_preserves_files(self):
        api=self.api
        stages=('load','ensure-http','ensure-other','save','select','pose','background','plan','output','render','label','annotation','update','yaml','ocr','serialize','manifest')
        for stage in stages:
            with self.subTest(stage=stage),ExitStack() as stack:
                f=DatasetFixture(self.root/stage);f.root.mkdir();f.bind(api,stack);f.plan=f.plan[:1];calls=[]
                failure=HTTPException(409,'asset failure') if stage=='ensure-http' else OSError('first-'+stage)
                field={'load':'load_config','ensure-http':'ensure_training_normalized_assets_for_selection','ensure-other':'ensure_training_normalized_assets_for_selection','save':'save_config','select':'selected_accessories','pose':'normalize_preview_pose_family_policy','background':'selected_background_set_id','plan':'build_training_sample_plan','output':'output_write_dir_for_owner','render':'draw_training_preview','label':'yolo_detection_label_line','annotation':'write_training_annotation_preview','update':'update_training_task','yaml':'write_dataset_yaml','ocr':'accessory_uses_ocr','serialize':'dumps','manifest':'write_text'}[stage]
                target=json if stage=='serialize' else Path if stage=='manifest' else api
                original=getattr(target,field)
                def failing(*args,**kwargs):
                    applies=stage!='manifest' or args[0].name=='manifest.json'
                    if applies:
                        calls.append(True)
                        if len(calls)==1:
                            if stage=='manifest':original(args[0],'partial',encoding='utf-8')
                            raise failure
                    return original(*args,**kwargs)
                stack.enter_context(patch.object(target,field,failing))
                with self.assertRaises(BaseException) as caught:api.generate_training_dataset(f.task)
                self.assertIs(caught.exception,failure);self.assertEqual(len(calls),1)
                directory=f.root/'datasets/fixture-job';index=stages.index(stage)
                self.assertEqual((directory/'images/train/sample_000001.png').exists(),index>stages.index('render'))
                self.assertEqual((directory/'labels/train/sample_000001.txt').exists(),index>stages.index('label'))
                self.assertEqual((directory/'previews/train/sample_000001_boxed.jpg').exists(),index>stages.index('annotation'))
                self.assertEqual((directory/'dataset.yaml').exists(),index>stages.index('yaml'))
                self.assertEqual((directory/'manifest.json').exists(),stage=='manifest')
                if stage=='manifest':self.assertEqual((directory/'manifest.json').read_text(),'partial')
                if stage in ('ensure-http','ensure-other'):self.assertEqual(f.save.call_count,int(stage=='ensure-http'))
                self.assertEqual(f.render.call_count,int(index>stages.index('render')))
                self.assertEqual(f.update.call_count,int(index>stages.index('update')))

    def test_dataset_getter_failures_stop_at_original_side_effect_boundary(self):
        from dataclasses import replace
        api=self.api
        for stage in ('pose','background','output','draw','label','annotation','update','max-occlusion','min-area'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=DatasetFixture(self.root/stage);f.root.mkdir();f.bind(api,stack);f.plan=f.plan[:1]
                failure=OSError('getter-'+stage);calls=[]
                def getter():calls.append(True);raise failure
                g=api._training_dataset_generator
                if stage in ('pose','background'):stack.enter_context(patch.object(g,'plan',replace(g.plan,**{'normalize_pose' if stage=='pose' else 'background':getter})))
                elif stage in ('output','update'):stack.enter_context(patch.object(g,'output' if stage=='output' else 'update_provider',getter))
                else:stack.enter_context(patch.object(g,'render',replace(g.render,**{stage.replace('-','_').replace('min_area','min_visible_area'):getter})))
                with self.assertRaises(BaseException) as caught:api.generate_training_dataset(f.task)
                self.assertIs(caught.exception,failure);self.assertEqual(calls,[True])
                self.assertEqual(f.render.call_count,int(stage in ('label','annotation','update','max-occlusion','min-area')))
                self.assertEqual(f.update.call_count,int(stage in ('max-occlusion','min-area')))
                self.assertFalse((f.root/'datasets/fixture-job/manifest.json').exists())


    def test_output_and_annotation_first_errors_are_never_repeated(self):
        api=self.api
        for stage in ('output-public','imread','rectangle','putText','mkdir','imwrite','annotation-public'):
            with self.subTest(stage=stage),ExitStack() as stack:
                root=self.root/stage;root.mkdir();image=root/'source.png';cv2.imwrite(str(image),np.zeros((30,30,3),dtype=np.uint8));out=root/'previews/result.jpg'
                stack.enter_context(patch.object(api,'OUTPUT_DIR',root));stack.enter_context(patch.object(api,'public_output_url',return_value='/fixture'))
                target=Path if stage=='mkdir' else api if stage in ('output-public','annotation-public') else cv2
                field={'output-public':'public_output_url','annotation-public':'public_training_output_url'}.get(stage,stage)
                original=getattr(target,field);failure=OSError('first-'+stage);calls=[]
                def first(*args,**kwargs):
                    calls.append(True)
                    if len(calls)==1:raise failure
                    return original(*args,**kwargs)
                stack.enter_context(patch.object(target,field,first))
                with self.assertRaises(BaseException) as caught:
                    if stage=='output-public':api.public_training_output_url(image)
                    else:api.write_training_annotation_preview(image,[{'id':'a','name':'A','amodal_bbox_xyxy':[2,2,20,20]}],out)
                self.assertIs(caught.exception,failure);self.assertEqual(calls,[True])
                self.assertEqual(out.exists(),stage=='annotation-public')
                self.assertEqual(out.parent.exists(),stage in ('imwrite','annotation-public'))
                self.assertFalse(np.any(cv2.imread(str(image)))) if stage!='imread' else None

    def test_planner_first_port_failure_stops_once(self):
        api=self.api
        for stage,field in [('split','split_counts'),('poses','preview_pose_family_sequence'),('missing','missing_count_for_false_sample')]:
            with self.subTest(stage=stage),ExitStack() as stack:
                original=getattr(api,field);failure=OSError(stage);calls=[]
                def first(*args,**kwargs):
                    calls.append(True)
                    if len(calls)==1:raise failure
                    return original(*args,**kwargs)
                stack.enter_context(patch.object(api,field,first))
                with self.assertRaises(BaseException) as caught:api.build_training_sample_plan([{'id':'a'},{'id':'b'}],100,41,'auto')
                self.assertIs(caught.exception,failure);self.assertEqual(calls,[True])

    def test_generator_directory_clock_and_http_save_failures(self):
        import time
        api=self.api
        for stage in ('images-mkdir','labels-mkdir','http-save','seed-clock','manifest-clock'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=DatasetFixture(self.root/stage);f.root.mkdir();f.bind(api,stack);f.plan=f.plan[:1];calls=[];failure=OSError(stage)
                target=Path if 'mkdir' in stage else time if 'clock' in stage else api
                field='mkdir' if target is Path else 'time' if target is time else 'save_config'
                original=getattr(target,field)
                if stage=='http-save':f.ensure.side_effect=HTTPException(409,'original asset failure')
                if stage=='seed-clock':f.task['seed']=0
                def first(*args,**kwargs):
                    applies='mkdir' not in stage or args[0].parent.name==stage.split('-')[0]
                    if applies:
                        calls.append(True)
                        if len(calls)==1:raise failure
                    return original(*args,**kwargs)
                stack.enter_context(patch.object(target,field,first))
                with self.assertRaises(BaseException) as caught:api.generate_training_dataset(f.task)
                self.assertIs(caught.exception,failure);self.assertEqual(calls,[True]);directory=f.root/'datasets/fixture-job'
                self.assertEqual(f.render.call_count,int(stage=='manifest-clock'));self.assertEqual(f.update.call_count,int(stage=='manifest-clock'))
                self.assertEqual((directory/'images/train').exists(),stage in ('labels-mkdir','manifest-clock'))
                self.assertEqual((directory/'dataset.yaml').exists(),stage=='manifest-clock');self.assertFalse((directory/'manifest.json').exists())
                if stage=='http-save':f.select.assert_not_called()

    def test_draw_is_resolved_again_for_each_sample(self):
        f=self.fixture();f.plan=f.plan[:2];api=self.api;events=[];original=api.draw_training_preview
        def first(*args,**kwargs):events.append('A');return original(*args,**kwargs)
        def second(*args,**kwargs):events.append('B');return original(*args,**kwargs)
        class Plan(dict):
            def get(self,key,default=None):
                if key=='pose_family_policy':api.draw_training_preview=second
                return super().get(key,default)
        f.plan[0]=Plan(f.plan[0]);self.stack.enter_context(patch.object(api,'draw_training_preview',first))
        result=api.generate_training_dataset(f.task);self.assertEqual(events,['A','B'])
        self.assertEqual(len(json.loads(Path(result['manifest_path']).read_text())['samples']),2)

        # A formatter selected for one label is not cached for the next label.
        with ExitStack() as stack:
            f=DatasetFixture(self.root/'labels');f.root.mkdir();f.bind(api,stack);f.plan=f.plan[:1];events=[];formatter=api.yolo_detection_label_line
            def first_label(*args,**kwargs):events.append('A');return formatter(*args,**kwargs)
            def second_label(*args,**kwargs):events.append('B');return formatter(*args,**kwargs)
            class Label(dict):
                def get(self,key,default=None):
                    if key=='id':api.yolo_detection_label_line=second_label
                    return super().get(key,default)
            original_draw=f.render.side_effect
            def draw(*args,**kwargs):
                value=original_draw(*args,**kwargs);value['labels']=[Label(value['labels'][0]),value['labels'][1]];return value
            f.render.side_effect=draw;stack.enter_context(patch.object(api,'yolo_detection_label_line',first_label))
            result=api.generate_training_dataset(f.task);self.assertEqual(events,['A','B'])
            self.assertEqual(len((Path(result['dataset_dir'])/'labels/train/sample_000001.txt').read_text().splitlines()),2)

    def test_output_root_provider_failure_is_not_retried(self):
        from dataclasses import replace
        service=self.api._training_output_links;failure=OSError('root');calls=[]
        def root():
            calls.append(True)
            if len(calls)==1:raise failure
            return self.root
        with patch.object(service,'media',replace(service.media,output_root=root)):
            with self.assertRaises(BaseException) as caught:service.public_training_output_url(self.root/'x')
        self.assertIs(caught.exception,failure);self.assertEqual(calls,[True])


if __name__ == '__main__':
    unittest.main()
