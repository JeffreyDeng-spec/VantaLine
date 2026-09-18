"""Original training input, preview fingerprint and status settlement contracts."""
from contextlib import ExitStack
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch
from fastapi import HTTPException
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class SyntheticStatPath:
    def __init__(self, name, *, stamp=123456789, size=37, error=None):
        self.name, self.stamp, self.size, self.error = name, stamp, size, error
        self.calls = 0
    def __str__(self): return self.name
    def stat(self):
        self.calls += 1
        if self.error: raise self.error
        return SimpleNamespace(st_mtime_ns=self.stamp, st_size=self.size)


def fingerprint_fixture():
    item = {'id': 'part', 'material_type': 'object', 'physical_size': {'z': 8, 'a': 3},
            'clean_sprite_status': 'ready', 'clean_sprite_preprocessed_at': 77, 'clean_sprite_count': 0,
            'clean_sprite_expected_count': 6}
    asset = {'path': 'first', 'task_id': 'task', 'source_position': 'left', 'pose_position': 'ignored',
             'source_pose_family': 'lying', 'pose_family': 'ignored', 'material_alpha_policy': 'solid',
             'object_alpha_material_policy': 'opaque', 'physical_size_mm': {'z': 9, 'a': 1},
             'source_object_bbox_xyxy': [1, 2, 3, 4], 'source_object_size_px': [5, 6],
             'source_long_side_px': 6, 'source_short_side_px': 5, 'source_long_edge_axis': 'y',
             'source_short_edge_axis': 'x', 'source_long_short_ratio': 1.2, 'normalized_bbox_xyxy': [2, 3, 4, 5],
             'render_footprint_px': [7, 8], 'render_footprint_mm': [9, 10], 'render_size_hint_px': [11, 12]}
    sprites = [asset, {**asset, 'path': 'second', 'source_position': '', 'source_pose_family': ''}, asset]
    paths = {'first': SyntheticStatPath('raw/../synthetic first.png'),
             'second': SyntheticStatPath('other-path.png', stamp=987654321, size=71)}
    return item, sprites, paths


class TrainingInputStateContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ); cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='training-input-root-')
        root = Path(cls.runtime.name); (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()

    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='training-input-')))
        self.jobs = self.root / 'jobs'; self.jobs.mkdir()
        self.user = {'id': 'alice', 'role': 'member'}; self.selected = []; self.records = {}
        self.bindings = {
            'TRAINING_JOBS_DIR': self.jobs,
            'PREVIEW_CACHE_SCHEMA_VERSION': 'fixture-schema-v4',
            'clean_sprite_assets': Mock(return_value=[]),
            'accessory_uid': Mock(side_effect=lambda item: item['id']),
            'accessory_material_type': Mock(side_effect=lambda item: item['material_type']),
            'object_alpha_material_policy': Mock(return_value='solid'),
            'resolve_service_path': Mock(side_effect=lambda value: Path(value)),
            'selected_background_set_id': Mock(return_value=None),
            'find_dataset_resource': Mock(return_value=(None, None)),
            'public_path_sanitized': Mock(side_effect=lambda value: value),
            'require_record_access': Mock(),
            'find_training_task': Mock(side_effect=lambda job: self.records.get(job)),
            'public_refreshed_training_task': Mock(side_effect=lambda task: task),
            'record_visible_to_user': Mock(side_effect=lambda task, user, target=None: task.get('owner_user_id') == (target or user['id'])),
            'user_is_admin': Mock(side_effect=lambda user: user.get('role') == 'admin'),
            'record_owner_id': Mock(side_effect=lambda value: value.get('owner_user_id', '')),
            'selected_accessories': Mock(side_effect=lambda config, ids: self.selected),
        }
        for name, value in self.bindings.items(): self.stack.enter_context(patch.object(self.api, name, value))
        for target in ['requests.request', 'subprocess.Popen', 'os.kill']:
            self.stack.enter_context(patch(target, side_effect=AssertionError('unexpected external operation')))

    def cache_fixture(self):
        item, sprites, paths = fingerprint_fixture()
        self.bindings['clean_sprite_assets'].return_value = sprites
        self.bindings['resolve_service_path'].side_effect = lambda value: paths[value]
        return item, sprites, paths

    def preview(self, **values):
        payload = {'selected_accessories': [{'id': 'a'}, {'id': 'b'}], 'background_set_id': None, 'preview_cache_key': 'key', **values}
        path = self.jobs / 'approved.json'; path.write_text(json.dumps(payload), encoding='utf-8'); return path

    def request(self, approved='approved'):
        return self.api.TrainingStartRequest(selected_accessory_ids=['a', 'b'], approved_preview_id=approved)

    def assert_http(self, status, detail, callback):
        with self.assertRaises(HTTPException) as caught: callback()
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (status, detail))
        return caught.exception

    def test_original_fingerprint_golden_order_duplicates_and_all_asset_fields(self):
        item, sprites, paths = self.cache_fixture()
        expected = json.loads((Path(__file__).resolve().parents[1] / 'tests/backend_contract/training_preview_cache.json').read_text())
        before = copy.deepcopy((item, sprites))
        self.assertEqual(self.api.accessory_sprite_version(item), expected['original_fingerprint'])
        self.assertEqual((item, sprites), before); self.assertEqual([paths['first'].calls, paths['second'].calls], [2, 1])
        self.assertEqual(self.bindings['resolve_service_path'].call_args_list, [call('first'), call('second'), call('first')])
        self.assertEqual(self.bindings['accessory_material_type'].call_count, 2)
        for key in sprites[0]:
            if key in {'path', 'pose_position', 'pose_family'}: continue
            with self.subTest(field=key):
                original = sprites[0][key]; sprites[0][key] = 'changed'
                self.assertNotEqual(self.api.accessory_sprite_version(item), expected['original_fingerprint'])
                sprites[0][key] = original
        sprites.reverse(); self.assertEqual(self.api.accessory_sprite_version(item), expected['original_fingerprint'])
        sprites[0], sprites[1] = sprites[1], sprites[0]
        self.assertNotEqual(self.api.accessory_sprite_version(item), expected['original_fingerprint'])
        sprites.pop(); self.assertNotEqual(self.api.accessory_sprite_version(item), expected['original_fingerprint'])

    def test_fingerprint_stat_oserror_only_path_string_and_sorted_json(self):
        item, sprites, paths = self.cache_fixture()
        baseline = self.api.accessory_sprite_version(item)
        item['physical_size'] = {'a': 3, 'z': 8}; sprites[0]['physical_size_mm'] = {'a': 1, 'z': 9}
        self.assertEqual(self.api.accessory_sprite_version(item), baseline)
        paths['first'].name = 'synthetic first.png'; self.assertNotEqual(self.api.accessory_sprite_version(item), baseline)
        paths['first'].error = OSError('missing'); failed = self.api.accessory_sprite_version(item)
        paths['first'].error = None; paths['first'].stamp = paths['first'].size = 0
        self.assertEqual(self.api.accessory_sprite_version(item), failed)
        paths['first'].error = ValueError('bad stat')
        with self.assertRaisesRegex(ValueError, 'bad stat'): self.api.accessory_sprite_version(item)
        paths['first'].error = None; self.bindings['resolve_service_path'].side_effect = OSError('resolve')
        with self.assertRaisesRegex(OSError, 'resolve'): self.api.accessory_sprite_version(item)

    def test_cache_key_order_and_duplicates_use_late_version_dependency(self):
        values = [{'id': 'b'}, {'id': 'a'}, {'id': 'b'}]; events = []
        self.bindings['accessory_uid'].side_effect = lambda item: events.append(('id', item)) or item['id']
        with patch.object(self.api, 'accessory_sprite_version', side_effect=lambda item: events.append(('version', item)) or 'v') as version:
            self.assertEqual(self.api.preview_cache_key(values), hashlib.sha1(b'b:v|a:v|b:v').hexdigest()[:16])
            self.assertEqual(events, [(kind, item) for item in values for kind in ['id', 'version']])
            self.assertEqual(version.call_count, 3)
            self.assertEqual(self.api.preview_cache_key([]), hashlib.sha1(b'').hexdigest()[:16])

    def test_missing_metadata_truthiness_and_material_short_circuit(self):
        object_item = {'id': 'a', 'material_type': 'object'}; text_item = {'id': 'b', 'material_type': 'text'}
        for state in [{}, {'preview_urls': []}, {'previews': []}, {'last_preview_id': ''}]:
            self.assertFalse(self.api.training_preview_metadata_missing(state, [object_item]))
        for state in [{'preview_urls': ['x']}, {'previews': [{}]}, {'last_preview_id': 'x'}]:
            self.assertTrue(self.api.training_preview_metadata_missing(state, [object_item]))
            self.assertFalse(self.api.training_preview_metadata_missing(state, [text_item]))
            for versions, missing in [(None, True), ([], True), ({}, True), ({'a': {}}, False)]:
                self.assertEqual(self.api.training_preview_metadata_missing({**state, 'preview_cache_key': 'k', 'preview_sprite_versions': versions}, [object_item]), missing)
        kind = self.bindings['accessory_material_type']; kind.reset_mock()
        self.assertTrue(self.api.training_preview_metadata_missing({'last_preview_id': 'x'}, [object_item, text_item])); kind.assert_called_once_with(object_item)

    def test_approval_no_id_returns_before_file_or_background_work(self):
        with patch.object(Path, 'exists', side_effect=AssertionError('unexpected file read')), patch.object(self.api, 'preview_cache_key', side_effect=AssertionError('unexpected cache')):
            self.assertIsNone(self.api.validate_approved_preview({}, self.request(None), [], self.user))
        self.bindings['selected_background_set_id'].assert_not_called()

    def test_approval_missing_decode_oserror_only_and_exists_exception(self):
        validate = lambda: self.api.validate_approved_preview({'training': {}}, self.request(), [{'id': 'a'}, {'id': 'b'}], self.user)
        missing = 'Approved preview is no longer available. Generate a fresh preview.'
        unreadable = 'Approved preview metadata is unreadable. Generate a fresh preview.'
        self.assert_http(409, missing, validate)
        path = self.preview(); path.write_text('{broken')
        self.assert_http(409, unreadable, validate)
        with patch.object(Path, 'read_text', side_effect=OSError('read')): self.assert_http(409, unreadable, validate)
        path.write_bytes(bytes([255]))
        with self.assertRaises(UnicodeDecodeError): validate()
        with patch.object(Path, 'exists', side_effect=OSError('exists')):
            with self.assertRaisesRegex(OSError, 'exists'): validate()
        path.write_text('[]')
        with self.assertRaises(AttributeError): validate()
        self.bindings['selected_background_set_id'].assert_not_called()

    def test_approval_order_exact_ids_background_then_cache_and_stale_in_place(self):
        selected = [{'id': 'a'}, {'id': 'b'}]; state = {'previews': ['old'], 'preview_urls': ['old'], 'untouched': []}; config = {'training': state}
        path = self.preview(selected_accessories=[{'id': 'b'}, {'id': 'a'}])
        with patch.object(self.api, 'preview_cache_key', return_value='new') as cache:
            self.assert_http(409, 'Approved preview does not match the selected accessories.', lambda: self.api.validate_approved_preview(config, self.request(), selected, self.user))
            self.bindings['selected_background_set_id'].assert_not_called(); cache.assert_not_called()
            self.preview(background_set_id='wrong')
            self.assert_http(409, 'Approved preview does not match the selected background set. Generate a fresh preview.', lambda: self.api.validate_approved_preview(config, self.request(), selected, self.user))
            cache.assert_not_called(); self.assertEqual(state['previews'], ['old'])
            self.preview()
            self.assert_http(409, 'Approved preview is stale. Generate a fresh preview.', lambda: self.api.validate_approved_preview(config, self.request(), selected, self.user))
            self.assertIs(config['training'], state); self.assertEqual(state['preview_urls'], []); self.assertEqual(state['previews'], [])
            self.assertEqual((state['preview_stale_reason'], state['current_preview_cache_key']), ('clean_sprite_version_changed', 'new'))
            cache.assert_called_once_with(selected)
            cache.return_value = 'key'; self.assertIsNone(self.api.validate_approved_preview(config, self.request(), selected, self.user))
        self.bindings['selected_background_set_id'].assert_called_with(None, self.user)

    def test_approval_empty_selection_skips_cache_and_non_dict_entries_are_ignored(self):
        self.preview(selected_accessories=[None, 'ignored', 1], preview_cache_key=None)
        with patch.object(self.api, 'preview_cache_key', side_effect=AssertionError('unexpected empty cache')):
            self.assertIsNone(self.api.validate_approved_preview({'training': {}}, self.request(), [], None))

    def dataset(self, manifest):
        path = self.root / 'dataset'; path.mkdir(exist_ok=True)
        (path / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8'); (path / 'dataset.yaml').write_text('synthetic')
        self.bindings['find_dataset_resource'].return_value = (path, {'owner_user_id': 'alice'})
        return path

    def test_dataset_input_lookup_file_require_order_and_sanitized_count_priority(self):
        selected_ids = ['b', 'a', 'b']; path = self.dataset({'samples': [{'id': 1}], 'sample_count': 999, 'selected_accessory_ids': selected_ids})
        self.bindings['public_path_sanitized'].return_value = [{'id': 2}, {'id': 3}]; self.bindings['public_path_sanitized'].side_effect = None
        result = self.api.dataset_for_training('raw-id', self.user)
        self.assertEqual(result, {'id': 'dataset', 'dataset_dir': str(path), 'dataset_yaml': str(path / 'dataset.yaml'),
                         'manifest_path': str(path / 'manifest.json'), 'sample_count': 2, 'selected_accessory_ids': selected_ids,
                         'background_set_id': '', 'display_name': 'dataset'})
        self.bindings['find_dataset_resource'].assert_called_once_with('raw-id', user=self.user, include_samples=False)
        self.bindings['require_record_access'].assert_called_once_with({'owner_user_id': 'alice'}, self.user)
        self.bindings['public_path_sanitized'].assert_called_once_with([{'id': 1}])
        self.bindings['require_record_access'].reset_mock()
        self.api.dataset_for_training('raw-id', {}); self.bindings['require_record_access'].assert_not_called()
        self.bindings['find_dataset_resource'].return_value = (path, {})
        self.api.dataset_for_training('raw-id', self.user); self.bindings['require_record_access'].assert_not_called()

    def test_dataset_missing_read_errors_and_unicode_boundary_precede_access(self):
        read = lambda: self.api.dataset_for_training('data', self.user)
        self.assert_http(404, 'Training dataset not found', read)
        path = self.dataset({'sample_count': 1}); (path / 'dataset.yaml').unlink()
        self.assert_http(404, 'Training dataset not found', read)
        (path / 'dataset.yaml').write_text(''); (path / 'manifest.json').write_text('{broken')
        self.assert_http(500, 'Training dataset manifest is unreadable', read)
        with patch.object(Path, 'read_text', side_effect=OSError('read')): self.assert_http(500, 'Training dataset manifest is unreadable', read)
        (path / 'manifest.json').write_bytes(bytes([255]))
        with self.assertRaises(UnicodeDecodeError): read()
        self.bindings['require_record_access'].assert_not_called(); self.bindings['public_path_sanitized'].assert_not_called()

    def test_dataset_no_samples_fallback_count_and_permission_before_projection(self):
        self.dataset({'samples': 'not-a-list', 'sample_count': '3'})
        self.assertEqual(self.api.dataset_for_training('data', self.user)['sample_count'], 3)
        self.bindings['public_path_sanitized'].assert_called_once_with([])
        self.dataset({'samples': [], 'sample_count': 0})
        self.assert_http(409, 'Training dataset has no samples', lambda: self.api.dataset_for_training('data', self.user))
        self.bindings['public_path_sanitized'].reset_mock(); self.bindings['require_record_access'].side_effect = HTTPException(403, 'denied')
        self.assert_http(403, 'denied', lambda: self.api.dataset_for_training('data', self.user)); self.bindings['public_path_sanitized'].assert_not_called()

    def test_status_hydrates_in_place_whitelisted_keys_and_dataset_fallback(self):
        state = {'active_training_task_id': ' job ', 'status': 'running', 'selected_accessory_ids': ['a'], 'nested': []}
        task = {'job_id': 'job', 'owner_user_id': 'alice', 'status': 'completed', 'progress': 100, 'error': None,
                'dataset_dir': 'synthetic', 'source_dataset_id': 'source', 'action': 'train_model', 'private': 'hidden'}
        self.records['job'] = task
        result = self.api.filtered_training_state({'training': state}, self.user)
        self.assertIs(result, state); self.assertEqual(state['dataset_id'], 'source'); self.assertEqual(state['active_training_action'], 'train_model')
        self.assertEqual(state['status'], 'completed'); self.assertIsNone(state['error']); self.assertNotIn('private', state)
        self.bindings['public_refreshed_training_task'].assert_called_once_with(task)
        self.bindings['selected_accessories'].assert_called_once_with({'training': state}, ['a'])

    def test_status_hidden_missing_and_blank_id_refresh_order(self):
        hidden = {'job_id': 'hidden', 'owner_user_id': 'bob', 'status': 'running'}; self.records['hidden'] = hidden
        for identifier, status, expected in [('hidden', 'queued', 'stopped'), ('missing', 'running', 'stopped'), ('missing', 'completed', 'completed'), (' ', 'running', 'running')]:
            state = {'active_training_task_id': identifier, 'status': status}
            self.assertIs(self.api.filtered_training_state({'training': state}, self.user), state)
            self.assertEqual(state['status'], expected)
            if expected == 'stopped': self.assertEqual(state['progress'], 100); self.assertEqual(state['error'], 'Active training task record is missing. Start a new task.')
        self.bindings['public_refreshed_training_task'].assert_not_called(); self.assertEqual(hidden['status'], 'running')
        self.api.filtered_training_state({'training': {'active_training_task_id': 'hidden'}}, None)
        self.bindings['public_refreshed_training_task'].assert_called_once_with(hidden)

    def test_status_children_admin_target_and_duplicate_refresh_no_dedup(self):
        self.user['role'] = 'admin'
        first = {'active_training_task_id': 'same', 'owner_user_id': 'bob'}
        second = {'active_training_task_id': 'same', 'owner_user_id': 'alice'}
        state = {'active_training_task_id': 'same', 'training_states': [first, 'ignored', second]}
        task = {'job_id': 'same', 'owner_user_id': 'alice', 'status': 'completed'}; self.records['same'] = task
        self.bindings['record_visible_to_user'].side_effect = None; self.bindings['record_visible_to_user'].return_value = True
        self.api.filtered_training_state({'training': state}, self.user)
        self.assertEqual(self.bindings['find_training_task'].call_args_list, [call('same')] * 3)
        self.assertEqual(self.bindings['record_visible_to_user'].call_args_list, [call(task, self.user, None), call(task, self.user, 'bob'), call(task, self.user, 'alice')])
        self.assertEqual(self.bindings['public_refreshed_training_task'].call_count, 3)
        self.bindings['record_visible_to_user'].reset_mock(); self.bindings['record_owner_id'].reset_mock()
        self.api.filtered_training_state({'training': state}, self.user, 'target')
        self.assertEqual(self.bindings['record_visible_to_user'].call_args_list, [call(task, self.user, 'target')] * 3)
        self.bindings['record_owner_id'].assert_not_called()

    def test_status_stale_shallow_copy_after_hydration_and_reason_priority(self):
        nested = []; state = {'active_training_task_id': 'job', 'preview_urls': ['old'], 'previews': ['old'], 'preview_cache_key': 'old', 'nested': nested}
        self.selected = [{'id': 'a', 'material_type': 'object'}]
        self.records['job'] = {'job_id': 'job', 'owner_user_id': 'alice', 'status': 'completed'}
        with patch.object(self.api, 'preview_cache_key', return_value='current') as cache:
            result = self.api.filtered_training_state({'training': state}, self.user)
            self.assertIsNot(result, state); self.assertIs(result['nested'], nested)
            self.assertEqual(state['status'], 'completed'); self.assertEqual(state['preview_urls'], ['old'])
            self.assertEqual(result['preview_urls'], []); self.assertEqual(result['preview_stale_reason'], 'missing_preview_sprite_version')
            state['preview_sprite_versions'] = {'a': 'old'}
            result = self.api.filtered_training_state({'training': state}, self.user)
            self.assertEqual(result['preview_stale_reason'], 'clean_sprite_version_changed'); self.assertEqual(result['current_preview_cache_key'], 'current')
            cache.return_value = 'old'; self.assertIs(self.api.filtered_training_state({'training': state}, self.user), state)

    def test_status_real_lifecycle_settlement_writes_and_failure_stops_projection(self):
        from local_inspection_service.runtime.training_tasks import TrainingTaskState
        from local_inspection_service.training.task_lifecycle import TrainingTaskLifecycle, TrainingTaskRecords, TrainingTaskWrites
        from local_inspection_service.training.task_views import TrainingTaskViews, TrainingViewAccess
        task = {'job_id': 'job', 'owner_user_id': 'alice', 'status': 'running'}; self.records['job'] = task
        save = Mock(); guard = threading.RLock()
        lifecycle = TrainingTaskLifecycle(TrainingTaskState(lambda: guard, lambda: {}, lambda: {}),
            TrainingTaskRecords(lambda job: self.root / job, lambda path: self.records[path.name], save, lambda job: self.records[job]),
            TrainingTaskWrites(Mock(), Mock(), Mock()), Mock())
        views = TrainingTaskViews(lambda: [], lifecycle.refresh_interrupted_local_training_task,
                                  TrainingViewAccess(dict, lambda: (lambda value: value), self.bindings['record_visible_to_user']))
        with patch.object(self.api, 'public_refreshed_training_task', wraps=views.public_refreshed_training_task) as refresh:
            empty_user = {}; target = 'target'
            visible = self.bindings['record_visible_to_user']
            visible.side_effect = None; visible.return_value = False
            state = {'active_training_task_id': 'job', 'status': 'running'}
            self.api.filtered_training_state({'training': state}, empty_user, target)
            visible.assert_called_once_with(task, empty_user, target)
            self.assertIs(visible.call_args.args[1], empty_user)
            refresh.assert_not_called(); save.assert_not_called()
            self.assertEqual((state['status'], state['progress'], task['status']), ('stopped', 100, 'running'))
            self.assertEqual(state['error'], 'Active training task record is missing. Start a new task.')
            visible.reset_mock()
            state = {'active_training_task_id': 'job', 'status': 'running'}
            self.api.filtered_training_state({'training': state}, None, target)
            visible.assert_not_called(); refresh.assert_called_once_with(task); save.assert_called_once_with(task)
            self.assertEqual((state['status'], task['status']), ('stopped', 'stopped'))
            task['status'] = 'running'; save.reset_mock(); refresh.reset_mock(); visible.return_value = True
            state = {'active_training_task_id': 'job', 'status': 'running'}
            self.api.filtered_training_state({'training': state}, self.user)
            self.assertEqual((state['status'], task['status']), ('stopped', 'stopped')); save.assert_called_once_with(task)
            task['status'] = 'running'; state['status'] = 'running'; save.reset_mock(); save.side_effect = OSError('settlement write failed')
            self.bindings['selected_accessories'].reset_mock()
            with self.assertRaisesRegex(OSError, 'settlement write failed'): self.api.filtered_training_state({'training': state}, self.user)
            save.assert_called_once(); self.bindings['selected_accessories'].assert_not_called()
            self.assertEqual(state['status'], 'running'); self.assertEqual(task['status'], 'stopped')


    def test_callback_capture_before_argument_effects(self):
        for site, target in [('resolve', 'resolve_service_path'), ('background', 'selected_background_set_id'), ('sanitize', 'public_path_sanitized'), ('selected', 'selected_accessories')]:
            for mode in ('ordinary', 'prior', 'missing'):
                with self.subTest(site=site, mode=mode), ExitStack() as scope:
                    api = self.api
                    events = []
                    armed = [False]
                    done = RuntimeError('chosen-callee')

                    def hit(label, *a, **k):
                        events.append(label)
                        raise done
                    ports = {name: Mock(side_effect=lambda *a, _label=name, **k: hit(_label, *a, **k)) for name in ('A', 'B', 'C')}
                    scope.enter_context(patch.object(api, target, ports['A']))

                    def prior():
                        events.append('prior')
                        armed[0] = True
                        setattr(api, target, None if mode == 'missing' else ports['B'] if mode == 'prior' else ports['A'])

                    def argument():
                        events.append('argument')
                        setattr(api, target, ports['C'])
                    if site == 'resolve':

                        class Asset(dict):

                            def get(inner, key, *default):
                                if key == 'path':
                                    argument()
                                return super().get(key, *default)

                        class Sprites(list):

                            def __iter__(inner):
                                prior()
                                yield from super().__iter__()
                        item = {'id': 'a', 'material_type': 'object', 'clean_sprite_count': 1}
                        sprites = Sprites([Asset(path='synthetic')])
                        scope.enter_context(patch.object(api, 'clean_sprite_assets', return_value=sprites))
                        operation = lambda: api.accessory_sprite_version(item)
                        argument_count = 1
                    elif site == 'background':
                        self.preview(selected_accessories=[{'id': 'a'}])
                        config = {'training': {}}

                        class ID(str):

                            def __eq__(inner, other):
                                prior()
                                return str.__eq__(inner, other)

                        class Request(api.TrainingStartRequest):

                            def __getattribute__(inner, key):
                                value = super().__getattribute__(key)
                                if key == 'background_set_id':
                                    argument()
                                return value
                        request = Request(selected_accessory_ids=['a'], approved_preview_id='approved')
                        selected = [{'id': ID('a')}]
                        operation = lambda: api.validate_approved_preview(config, request, selected, self.user)
                        argument_count = 1
                    elif site == 'sanitize':
                        self.dataset({'samples': [{'id': 1}]})

                        class Manifest(dict):

                            def get(inner, key, *default):
                                if key == 'samples':
                                    argument()
                                return super().get(key, *default)
                        scope.enter_context(patch.object(api.json, 'loads', return_value=Manifest(samples=[{'id': 1}])))
                        scope.enter_context(patch.object(api, 'require_record_access', side_effect=lambda *a: prior()))
                        operation = lambda: api.dataset_for_training('dataset', self.user)
                        argument_count = 2
                    else:

                        class Training(dict):

                            def get(inner, key, *default):
                                if key == 'training_states':
                                    prior()
                                if key == 'selected_accessory_ids':
                                    argument()
                                return super().get(key, *default)
                        config = {'training': Training()}
                        operation = lambda: api.filtered_training_state(config, self.user)
                        argument_count = 1
                    caught = None
                    try:
                        operation()
                    except BaseException as exc:
                        caught = exc
                    if mode == 'missing':
                        self.assertIs(type(caught), TypeError)
                    else:
                        self.assertIs(caught, done)
                    self.assertEqual(events, ['prior'] + ['argument'] * argument_count + ([] if mode == 'missing' else ['B' if mode == 'prior' else 'A']))
                    self.assertEqual(ports['A'].call_count, int(mode == 'ordinary'))
                    self.assertEqual(ports['B'].call_count, int(mode == 'prior'))
                    ports['C'].assert_not_called()

    def test_resolver_refreshes_between_assets(self):
        for missing in (False, True):
            with self.subTest(missing=missing), ExitStack() as scope:
                api = self.api
                item, sprites, paths = fingerprint_fixture()
                events = []

                class Asset(dict):

                    def get(inner, key, *default):
                        if key == 'path':
                            events.append('argument-second')
                        return super().get(key, *default)
                rows = [sprites[0], Asset(sprites[1])]

                def first(value):
                    events.append('A')
                    setattr(api, 'resolve_service_path', None if missing else second)
                    return paths[value]

                def later(value):
                    events.append('B')
                    return paths[value]
                second = Mock(side_effect=later)
                initial = Mock(side_effect=first)
                scope.enter_context(patch.object(api, 'clean_sprite_assets', return_value=rows))
                scope.enter_context(patch.object(api, 'resolve_service_path', initial))
                caught = None
                try:
                    api.accessory_sprite_version(item)
                except BaseException as exc:
                    caught = exc
                if missing:
                    self.assertIs(type(caught), TypeError)
                else:
                    self.assertIsNone(caught)
                self.assertEqual(events, ['A', 'argument-second'] + ([] if missing else ['B']))
                initial.assert_called_once_with('first')
                self.assertEqual(second.call_count, int(not missing))
                self.assertEqual(paths['first'].calls, 1)
                self.assertEqual(paths['second'].calls, int(not missing))

    def test_file_first_failure_preserves_http_cause_and_never_retries(self):
        for mode in ['approval', 'dataset']:
            for site, kind in [('exists', 'os'), ('read_text', 'os'), ('read_text', 'unicode'), ('loads', 'json'), ('loads', 'runtime')]:
                with self.subTest(mode=mode, site=site, kind=kind), ExitStack() as scope:
                    fixture, operation, _ = self.failure_fixture(scope, mode)
                    failure = {'os': OSError('first file error'), 'unicode': UnicodeDecodeError('utf-8', b'x', 0, 1, 'fixture'),
                               'json': json.JSONDecodeError('fixture', 'x', 0), 'runtime': RuntimeError('first parse error')}[kind]
                    owner = json if site == 'loads' else Path
                    original = getattr(owner, site); calls = []
                    target = fixture.jobs / 'approved.json' if mode == 'approval' else fixture.root / 'dataset' / 'manifest.json'
                    def fail_once(*args, **kwargs):
                        if site == 'loads' or args[0] == target:
                            calls.append(None)
                            if len(calls) == 1: raise failure
                        return original(*args, **kwargs)
                    scope.enter_context(patch.object(owner, site, fail_once))
                    converted = site != 'exists' and kind in ['os', 'json']
                    with self.assertRaises(HTTPException if converted else type(failure)) as caught: operation()
                    self.assertEqual(len(calls), 1)
                    if converted:
                        self.assertIs(caught.exception.__cause__, failure)
                        self.assertEqual(caught.exception.status_code, 409 if mode == 'approval' else 500)
                        self.assertEqual(caught.exception.detail, 'Approved preview metadata is unreadable. Generate a fresh preview.' if mode == 'approval' else 'Training dataset manifest is unreadable')
                    else: self.assertIs(caught.exception, failure)
                    fixture.bindings['require_record_access'].assert_not_called()
                    fixture.bindings['public_path_sanitized'].assert_not_called()
                    fixture.bindings['selected_background_set_id'].assert_not_called()

    def test_stat_first_oserror_zeros_fingerprint_without_retry(self):
        for kind in ['os', 'runtime']:
            with self.subTest(kind=kind), ExitStack() as scope:
                fixture, _, _ = self.failure_fixture(scope, 'version')
                item, sprites, paths = fixture.cache_fixture(); fixture.bindings['clean_sprite_assets'].return_value = sprites[:1]
                path = paths['first']; stamp, size = path.stamp, path.size
                path.stamp = path.size = 0; expected = self.api.accessory_sprite_version(item)
                path.stamp, path.size = stamp, size; calls = []; original = path.stat
                failure = OSError('stat-first') if kind == 'os' else RuntimeError('stat-first')
                def fail_once():
                    calls.append(None)
                    if len(calls) == 1: raise failure
                    return original()
                scope.enter_context(patch.object(path, 'stat', fail_once))
                if kind == 'os': self.assertEqual(self.api.accessory_sprite_version(item), expected)
                else:
                    with self.assertRaises(RuntimeError) as caught: self.api.accessory_sprite_version(item)
                    self.assertIs(caught.exception, failure)
                self.assertEqual(len(calls), 1)

    def test_dataset_directory_and_yaml_first_exists_error_stop_before_read(self):
        for name in ['directory', 'yaml']:
            with self.subTest(name=name), ExitStack() as scope:
                fixture, operation, _ = self.failure_fixture(scope, 'dataset')
                target = fixture.root / 'dataset'
                if name == 'yaml': target = target / 'dataset.yaml'
                original = Path.exists; calls = []; failure = OSError('exists-first')
                def fail_once(path):
                    if path == target:
                        calls.append(None)
                        if len(calls) == 1: raise failure
                    return original(path)
                scope.enter_context(patch.object(Path, 'exists', fail_once))
                read = scope.enter_context(patch.object(Path, 'read_text', side_effect=AssertionError('unexpected read')))
                with self.assertRaises(OSError) as caught: operation()
                self.assertIs(caught.exception, failure); self.assertEqual(len(calls), 1)
                read.assert_not_called(); fixture.bindings['require_record_access'].assert_not_called()
                fixture.bindings['public_path_sanitized'].assert_not_called()

    def failure_fixture(self, scope, mode):
        fixture = TrainingInputStateContracts(); fixture.setUp(); scope.callback(fixture.doCleanups)
        fixture.bindings['selected_background_set_id'].return_value = None
        fixture.bindings['user_is_admin'].return_value = True
        fixture.bindings['user_is_admin'].side_effect = None
        ports = {name: (self.api, name, port) for name, port in fixture.bindings.items() if callable(port)}
        if mode == 'version':
            item, _, _ = fixture.cache_fixture()
            operation = lambda: self.api.accessory_sprite_version(item)
        elif mode == 'key':
            port = Mock(return_value='version'); scope.enter_context(patch.object(self.api, 'accessory_sprite_version', port))
            ports['accessory_sprite_version'] = (self.api, 'accessory_sprite_version', port)
            operation = lambda: self.api.preview_cache_key([{'id': 'a'}, {'id': 'b'}])
        elif mode == 'metadata':
            operation = lambda: self.api.training_preview_metadata_missing({'preview_urls': ['url']}, [{'id': 'a', 'material_type': 'object'}])
        elif mode == 'approval':
            fixture.preview(); selected = [{'id': 'a'}, {'id': 'b'}]
            port = Mock(return_value='key'); scope.enter_context(patch.object(self.api, 'preview_cache_key', port))
            ports['preview_cache_key'] = (self.api, 'preview_cache_key', port)
            operation = lambda: self.api.validate_approved_preview({'training': {}}, fixture.request(), selected, fixture.user)
        elif mode == 'dataset':
            dataset = fixture.root / 'dataset'; dataset.mkdir()
            (dataset / 'dataset.yaml').write_text('fixture')
            (dataset / 'manifest.json').write_text(json.dumps({'samples': [{'id': 'sample'}]}))
            fixture.bindings['find_dataset_resource'].return_value = (dataset, {'owner_user_id': 'alice'})
            operation = lambda: self.api.dataset_for_training('dataset', fixture.user)
        else:
            fixture.selected = [{'id': 'a', 'material_type': 'object'}]
            fixture.records['job'] = {'job_id': 'job', 'owner_user_id': 'alice', 'status': 'completed'}
            state = {'active_training_task_id': 'job', 'training_states': [{'active_training_task_id': 'job', 'owner_user_id': 'alice'}]}
            operation = lambda: self.api.filtered_training_state({'training': state}, fixture.user)
        return fixture, operation, ports

    def test_first_dependency_failure_propagates_without_retry(self):
        for mode in ['version', 'key', 'metadata', 'approval', 'dataset', 'status']:
            with ExitStack() as scope:
                _, operation, ports = self.failure_fixture(scope, mode); operation()
                counts = {name: port.call_count for name, (_, _, port) in ports.items() if port.call_count}
            for name, count in counts.items():
                for index in range(1, count + 1):
                    with self.subTest(mode=mode, name=name, index=index), ExitStack() as scope:
                        _, operation, ports = self.failure_fixture(scope, mode)
                        owner, field, original = ports[name]; calls = []; failure = RuntimeError('input-first')
                        def fail_once(*args, **kwargs):
                            calls.append(None)
                            if len(calls) == index: raise failure
                            return original(*args, **kwargs)
                        scope.enter_context(patch.object(owner, field, fail_once))
                        with self.assertRaises(RuntimeError) as caught: operation()
                        self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_new_input_getter_errors_propagate_without_retry(self):
        from dataclasses import replace
        fields = [('version', self.api._training_preview_cache, None, 'resolve'),
                  ('version', self.api._training_preview_cache, None, 'schema'),
                  ('approval', self.api._training_preview_approval, None, 'jobs'),
                  ('approval', self.api._training_preview_approval, None, 'background'),
                  ('dataset', self.api._training_dataset_input, None, 'sanitize'),
                  ('status', self.api._training_status_projection, 'preview', 'selected')]
        def install(scope, service, group_name, field, port):
            if group_name:
                group = getattr(service, group_name)
                scope.enter_context(patch.object(service, group_name, replace(group, **{field: port})))
            else: scope.enter_context(patch.object(service, field, port))
        for mode, service, group_name, field in fields:
            original = getattr(getattr(service, group_name) if group_name else service, field)
            with ExitStack() as scope:
                _, operation, _ = self.failure_fixture(scope, mode); observed = Mock(wraps=original)
                install(scope, service, group_name, field, observed); operation(); count = observed.call_count
            self.assertGreater(count, 0)
            for index in range(1, count + 1):
                with self.subTest(mode=mode, field=field, index=index), ExitStack() as scope:
                    _, operation, _ = self.failure_fixture(scope, mode); calls = []; failure = RuntimeError('input-getter-first')
                    def fail_once(*args, **kwargs):
                        calls.append(None)
                        if len(calls) == index: raise failure
                        return original(*args, **kwargs)
                    install(scope, service, group_name, field, fail_once)
                    with self.assertRaises(RuntimeError) as caught: operation()
                    self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_independent_input_status_compositions_without_constructor_reads_or_root_access(self):
        from local_inspection_service.training.preview_cache import SpriteVersionInputs, TrainingPreviewCache
        from local_inspection_service.training.preview_approval import TrainingPreviewApproval
        from local_inspection_service.training.dataset_input import TrainingDatasetInput
        from local_inspection_service.training.status_projection import StatusTasks, StatusAccess, StatusPreview, TrainingStatusProjection
        def build(owner):
            root = self.root / owner; selected = [{'id': owner, 'material_type': 'object'}]
            dataset = root / 'dataset'; task = {'job_id': owner, 'owner_user_id': owner, 'status': 'completed', 'dataset_dir': str(dataset)}
            mocks = []
            def port(fn):
                value = Mock(side_effect=fn); mocks.append(value); return value
            cache = TrainingPreviewCache(SpriteVersionInputs(port(lambda item: []), port(lambda item: item['id']),
                port(lambda item: item['material_type']), port(lambda item: 'solid')), port(lambda: 'schema-' + owner),
                (lambda: Path), port(lambda item: cache.accessory_sprite_version(item)))
            approval = TrainingPreviewApproval(port(lambda: root), port(lambda: (lambda background, user: None)), port(cache.preview_cache_key))
            source = TrainingDatasetInput(port(lambda identifier, **kwargs: (dataset, {'owner_user_id': owner})),
                                         port(lambda record, user, **kwargs: self.assertEqual((record['owner_user_id'], user['id']), (owner, owner))), port(lambda: (lambda rows: rows)))
            status = TrainingStatusProjection(StatusTasks(port(lambda job: task if job == owner else None), port(lambda value: dict(value))),
                StatusAccess(port(lambda value, user, target: value['owner_user_id'] == user['id']), port(lambda user: False), port(lambda record: record['owner_user_id'])),
                StatusPreview(port(lambda: (lambda config, ids: selected)), port(cache.preview_cache_key), port(cache.training_preview_metadata_missing)))
            return owner, root, selected, dataset, cache, approval, source, status, mocks
        instances = [build(owner) for owner in ['alice', 'bob']]
        for *_, mocks in instances:
            for callback in mocks: callback.assert_not_called()
        for owner, root, selected, dataset, cache, *_ in instances:
            dataset.mkdir(parents=True); (dataset / 'dataset.yaml').write_text('synthetic')
            (dataset / 'manifest.json').write_text(json.dumps({'sample_count': 1, 'selected_accessory_ids': [owner]}))
            (root / 'approved.json').write_text(json.dumps({'selected_accessories': selected, 'background_set_id': None, 'preview_cache_key': cache.preview_cache_key(selected)}))
        for name in self.bindings:
            if callable(getattr(self.api, name)):
                self.stack.enter_context(patch.object(self.api, name, side_effect=AssertionError('unexpected root dependency')))
        for name in ['accessory_sprite_version', 'preview_cache_key', 'training_preview_metadata_missing']:
            self.stack.enter_context(patch.object(self.api, name, side_effect=AssertionError('unexpected root cache')))
        hashes = {}
        for index in [1, 0, 1, 0]:
            owner, root, selected, dataset, cache, approval, source, status, _ = instances[index]
            user = {'id': owner}; key = cache.preview_cache_key(selected)
            if owner in hashes: self.assertEqual(key, hashes[owner])
            hashes[owner] = key
            self.assertIsNone(approval.validate_approved_preview({'training': {}}, self.request(), selected, user))
            self.assertEqual(source.dataset_for_training('data', user)['selected_accessory_ids'], [owner])
            state = {'active_training_task_id': owner, 'status': 'running', 'preview_urls': ['preview'],
                     'preview_cache_key': key, 'preview_sprite_versions': {owner: key}}
            result = status.filtered_training_state({'training': state}, user)
            self.assertIs(result, state); self.assertEqual(result['status'], 'completed'); self.assertEqual(result['dataset_id'], owner)
        self.assertNotEqual(hashes['alice'], hashes['bob'])


if __name__ == '__main__': unittest.main()
