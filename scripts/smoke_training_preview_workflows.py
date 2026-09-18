"""Offline contracts for training plan reads and preview submission persistence/order."""
from contextlib import ExitStack
import copy
import json
import itertools
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class PreviewWorkflowFixture:
    def __init__(self, api, root, owner='alice'):
        self.api, self.root = api, Path(root); self.user = {'id': owner, 'role': 'member'}
        self.events = []; self.drawn = []; self.ensure_changed = False; self.draw_failure = None
        self.selected = [
            {'id': 'object', 'name': 'Object', 'material_type': 'object', 'clean_sprite_count': 3, 'clean_sprite_preprocessed_at': 44},
            {'id': 'manual', 'name': 'Manual', 'material_type': 'text'}]
        self.full = {'accessories': self.selected, 'training_by_user': {}}
        self.scoped = {'accessories': self.selected, 'scope_version': 1}
        self.rescoped = {'accessories': self.selected, 'scope_version': 2}
        self.training = {'status': 'old', 'background_set_id': 'remembered'}
        self.backgrounds = [{'id': 'available'}]; self.physical = {'width_mm': 1234}
        self.output = self.root / 'output'; self.jobs = self.root / 'jobs'; self.jobs.mkdir(parents=True)
        self.clock = self.callback('clock', Mock(side_effect=[1700.9, 1701.234, 1702.8]))
        self.uuid = self.callback('uuid', lambda: SimpleNamespace(hex='abcdef123456'))
        self.scope_calls = 0
        self.bindings = {
            'current_auth_user': self.callback('current', lambda: self.user),
            'user_is_admin': self.callback('admin', lambda user: user.get('role') == 'admin'),
            'load_config': self.callback('load', lambda: self.full),
            'scope_config_for_user': self.callback('scope', self.scope),
            'filtered_training_state': self.callback('filtered', lambda cfg, user, target=None: self.training),
            'serialize_accessory_items': self.callback('serialize', lambda items, *, summary: [{'public': item['id']} for item in items]),
            'list_background_sets': self.callback('backgrounds', lambda user, target=None: self.backgrounds),
            'selected_background_set_id': self.callback('background', lambda selected, user=None, target=None: 'chosen-background'),
            'training_execution_status': self.callback('execution', lambda *, include_worker_probe: {'probe': include_worker_probe}),
            'public_path_sanitized': self.callback('sanitize', lambda result: {**result, 'sanitized': True}),
            'ensure_training_assets_for_request': self.callback('ensure', lambda full, config, user, ids: self.ensure_changed),
            'selected_accessories': self.callback('selected', lambda config, ids: self.selected),
            'normalize_preview_pose_family_policy': self.callback('normalize', lambda policy: 'lying'),
            'accessory_material_type': self.callback('material', lambda item: item['material_type']),
            'accessory_uid': self.callback('uid', lambda item: item['id']),
            'clean_sprite_assets': self.callback('sprites', lambda item: [{'asset': 1}, {'asset': 2}]),
            'accessory_sprite_version': self.callback('version', lambda item: 'version-' + item['id']),
            'preview_cache_key': self.callback('cache', lambda selected: 'cache-key'),
            'output_write_dir': self.callback('output', lambda kind: self.output),
            'preview_pose_family_sequence': self.callback('sequence', lambda selected, count, policy: ['lying'] * count),
            'preview_pose_family_sequence_label': self.callback('sequence_label', lambda sequence: 'lying-label'),
            'draw_training_preview': self.callback('draw', self.draw),
            'set_training_state_for_user': self.callback('state', self.state),
            'merge_scoped_accessory_updates': self.callback('merge', lambda full, config, user: full.update(merged=config['scope_version'])),
            'save_config': self.callback('save', lambda full: True),
        }

    def callback(self, name, fn):
        def run(*args, **kwargs):
            self.events.append((name, args, kwargs)); return fn(*args, **kwargs)
        return Mock(side_effect=run)

    def scope(self, full, user, target=None):
        self.scope_calls += 1
        return self.rescoped if self.ensure_changed and self.scope_calls > 1 else self.scoped

    def state(self, full, user, state): full['training_by_user'][user['id']] = state

    def draw(self, selected, path, *, seed, pose_family_policy, background_set_id):
        Path(path).write_bytes(b'synthetic-preview'); index = len(self.drawn)
        result = {'url': '/synthetic/' + Path(path).name, 'labels': []}
        self.drawn.append(result)
        if self.draw_failure: self.draw_failure(index, result)
        return result

    def install(self, stack):
        for name, value in self.bindings.items(): stack.enter_context(patch.object(self.api, name, value))
        for name, value in {'time': SimpleNamespace(time=self.clock), 'uuid': SimpleNamespace(uuid4=self.uuid),
                            'TRAINING_JOBS_DIR': self.jobs, 'BACKGROUND_SIZE_MM': self.physical}.items():
            stack.enter_context(patch.object(self.api, name, value))
        mkdir, write_text = Path.mkdir, Path.write_text
        def directory(path, *args, **kwargs):
            if path == self.directory and kwargs.get('parents'): self.events.append(('mkdir', (path,), kwargs))
            return mkdir(path, *args, **kwargs)
        def write(path, *args, **kwargs):
            if path == self.plan_path: self.events.append(('write_plan', (path,) + args, kwargs))
            return write_text(path, *args, **kwargs)
        stack.enter_context(patch.object(Path, 'mkdir', directory)); stack.enter_context(patch.object(Path, 'write_text', write))
        return self

    @property
    def directory(self): return self.output / 'preview_1700_abcdef'
    @property
    def plan_path(self): return self.jobs / 'preview_1700_abcdef.json'
    def names(self): return [name for name, _, _ in self.events]
    def request(self, **values): return self.api.TrainingPreviewRequest(selected_accessory_ids=['object', 'manual'], **values)


class PreviewWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ); cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='preview-workflow-root-')
        root = Path(cls.runtime.name); (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()

    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='preview-workflow-')))
        self.f = PreviewWorkflowFixture(self.api, self.root).install(self.stack)
        for target in ['requests.request', 'subprocess.Popen', 'os.kill']:
            self.stack.enter_context(patch(target, side_effect=AssertionError('unexpected external operation')))

    def test_plan_member_admin_scope_identity_projection_and_no_worker_probe(self):
        for role, target in [('member', None), ('admin', 'bob')]:
            self.f.user['role'] = role; self.f.events.clear()
            result = self.api.training_plan('bob')
            self.assertIs(result['training'], self.f.training); self.assertIs(result['background_sets'], self.f.backgrounds)
            self.assertIs(result['render_policy']['background_physical_size'], self.f.physical)
            self.assertEqual(result['training_execution'], {'probe': False}); self.assertTrue(result['sanitized'])
            self.f.bindings['scope_config_for_user'].assert_called_with(self.f.full, self.f.user, target)
            self.f.bindings['filtered_training_state'].assert_called_with(self.f.scoped, self.f.user, target)
            self.f.bindings['selected_background_set_id'].assert_called_with('remembered', self.f.user, target)
            self.f.bindings['serialize_accessory_items'].assert_called_with(self.f.selected, summary=True)
            self.assertEqual(self.f.names(), ['current', 'admin', 'load', 'scope', 'filtered', 'serialize', 'backgrounds', 'background', 'execution', 'sanitize'])
            self.f.clock.assert_not_called(); self.f.bindings['save_config'].assert_not_called()

    def test_preview_success_original_order_aliases_three_clocks_and_force_false(self):
        request = self.f.request(preview_count=2, sample_count=50000, force_refresh=False)
        result = self.api.training_preview(request)
        self.assertNotIn('sanitized', result); self.f.bindings['public_path_sanitized'].assert_not_called()
        self.assertEqual(result['id'], 'preview_1700_abcdef'); self.assertEqual(result['sample_count'], 20000)
        self.assertEqual(result['train_mode'], 'yolo_ocr'); self.assertEqual(result['status'], 'preview_ready')
        self.assertIs(result['selected_accessories'], self.f.selected); self.assertEqual(result['previews'], self.f.drawn)
        self.assertEqual(result['preview_sprite_versions'], {'object': {'clean_sprite_preprocessed_at': 44, 'clean_sprite_count': 3, 'clean_sprite_version': 'version-object'}})
        self.f.bindings['clean_sprite_assets'].assert_not_called()
        self.assertEqual(self.f.clock.call_count, 3); self.f.uuid.assert_called_once_with()
        self.assertEqual([entry.kwargs for entry in self.f.bindings['draw_training_preview'].call_args_list], [
            {'seed': 1701234 + i, 'pose_family_policy': 'lying', 'background_set_id': 'chosen-background'} for i in range(2)])
        for callback_name in ['preview_cache_key', 'preview_pose_family_sequence', 'draw_training_preview']:
            for entry in self.f.bindings[callback_name].call_args_list: self.assertIs(entry.args[0], self.f.selected)
        self.assertEqual(json.loads(self.f.plan_path.read_text()), result)
        state = self.f.full['training_by_user']['alice']
        self.assertEqual(state['preview_generated_at'], 1702); self.assertEqual(state['mode'], 'yolo_ocr')
        self.assertIs(state['previews'], result['previews']); self.assertIs(state['preview_sprite_versions'], result['preview_sprite_versions'])
        self.assertEqual(self.f.names(), ['current', 'load', 'scope', 'ensure', 'selected', 'normalize', 'background',
                         'material', 'uid', 'version', 'material', 'cache', 'clock', 'uuid', 'output', 'mkdir',
                         'sequence', 'sequence_label', 'clock', 'draw', 'draw', 'write_plan', 'clock', 'state', 'merge', 'save'])
        self.f.bindings['save_config'].assert_called_once_with(self.f.full)
        self.f.bindings['merge_scoped_accessory_updates'].assert_called_once_with(self.f.full, self.f.scoped, self.f.user)

    def test_no_background_remains_none_in_query_draw_plan_json_and_user_state(self):
        background = self.f.bindings['selected_background_set_id']; background.side_effect = None; background.return_value = None
        self.assertIsNone(self.api.training_plan()['default_background_set_id'])
        plan = self.api.training_preview(self.f.request(preview_count=1))
        self.assertIsNone(plan['background_set_id'])
        self.assertIsNone(self.f.bindings['draw_training_preview'].call_args.kwargs['background_set_id'])
        self.assertIsNone(json.loads(self.f.plan_path.read_text())['background_set_id'])
        self.assertIsNone(self.f.full['training_by_user']['alice']['background_set_id'])

    def test_state_failure_keeps_plan_and_partial_memory_without_merge_or_save(self):
        error = RuntimeError('state update failed')
        def update_then_fail(full, user, value):
            self.f.state(full, user, value)
            if state.call_count == 1: raise error
        state = self.f.bindings['set_training_state_for_user']; state.side_effect = update_then_fail
        with self.assertRaises(RuntimeError) as caught: self.api.training_preview(self.f.request(preview_count=1))
        self.assertIs(caught.exception, error); state.assert_called_once()
        self.assertTrue(self.f.plan_path.is_file()); self.assertIn('alice', self.f.full['training_by_user'])
        self.f.bindings['merge_scoped_accessory_updates'].assert_not_called(); self.f.bindings['save_config'].assert_not_called()

    def test_ensure_rescope_and_request_ids_same_objects(self):
        self.f.ensure_changed = True
        request = self.f.request(preview_count=0, sample_count=0)
        result = self.api.training_preview(request)
        self.assertEqual(result['sample_count'], 1); self.assertEqual(len(result['previews']), 1)
        self.assertEqual(self.f.bindings['scope_config_for_user'].call_count, 2)
        args = self.f.bindings['ensure_training_assets_for_request'].call_args.args
        for actual, expected in zip(args, (self.f.full, self.f.scoped, self.f.user, request.selected_accessory_ids)): self.assertIs(actual, expected)
        self.f.bindings['selected_accessories'].assert_called_once_with(self.f.rescoped, request.selected_accessory_ids)
        self.f.bindings['merge_scoped_accessory_updates'].assert_called_once_with(self.f.full, self.f.rescoped, self.f.user)

    def test_max_preview_count_duplicate_uid_last_value_and_truthy_count_short_circuit(self):
        self.f.selected[:] = [{'id': 'first', 'material_type': 'object', 'clean_sprite_count': '0'},
                              {'id': 'second', 'material_type': 'object', 'clean_sprite_count': 0}]
        self.f.bindings['accessory_uid'].side_effect = lambda item: 'same'
        result = self.api.training_preview(self.f.request(preview_count=99))
        self.assertEqual(len(result['previews']), 12)
        self.assertEqual(result['preview_sprite_versions'], {'same': {'clean_sprite_preprocessed_at': None, 'clean_sprite_count': 2, 'clean_sprite_version': 'version-second'}})
        self.f.bindings['clean_sprite_assets'].assert_called_once_with(self.f.selected[1])
        self.assertEqual(self.f.bindings['accessory_sprite_version'].call_count, 2)

    def test_draw_object_fallback_409_keeps_files_and_stops_without_plan_or_state(self):
        def fail(index, result):
            result['labels'] = [{'material_type': 'text', 'source_fallback_error': 'allowed'}] if index == 0 else [{'material_type': 'object', 'source_fallback_error': 'missing'}]
        self.f.draw_failure = fail
        with self.assertRaises(HTTPException) as caught: self.api.training_preview(self.f.request(preview_count=3))
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (409, 'Clean sprite is unavailable. Regenerate clean sprites before preview.'))
        self.assertEqual(sorted(path.name for path in self.f.directory.iterdir()), ['sample_01.png', 'sample_02.png'])
        self.assertFalse(self.f.plan_path.exists()); self.assertEqual(self.f.clock.call_count, 2)
        for name in ['set_training_state_for_user', 'merge_scoped_accessory_updates', 'save_config']: self.f.bindings[name].assert_not_called()

    def test_render_exception_after_file_write_propagates_without_retry_or_plan(self):
        error = OSError('second render failed after write')
        def fail_once(index, result):
            if index == 1: raise error
        self.f.draw_failure = fail_once
        with self.assertRaises(OSError) as caught: self.api.training_preview(self.f.request(preview_count=3))
        self.assertIs(caught.exception, error)
        self.assertEqual(self.f.bindings['draw_training_preview'].call_count, 2)
        self.assertEqual(sorted(path.name for path in self.f.directory.iterdir()), ['sample_01.png', 'sample_02.png'])
        self.assertFalse(self.f.plan_path.exists()); self.assertEqual(self.f.clock.call_count, 2)
        for name in ['set_training_state_for_user', 'merge_scoped_accessory_updates', 'save_config']: self.f.bindings[name].assert_not_called()

    def test_text_fallback_and_empty_object_error_are_allowed(self):
        self.f.draw_failure = lambda index, result: result.update(labels=[{'material_type': 'text', 'source_fallback_error': 'missing'}, {'material_type': 'object', 'source_fallback_error': ''}])
        self.assertEqual(self.api.training_preview(self.f.request(preview_count=1))['status'], 'preview_ready')

    def test_mkdir_precedes_pose_failure_and_no_cleanup_retry_or_state(self):
        error = ValueError('pose unavailable'); self.f.bindings['preview_pose_family_sequence'].side_effect = error
        with self.assertRaises(ValueError) as caught: self.api.training_preview(self.f.request())
        self.assertIs(caught.exception, error); self.assertTrue(self.f.directory.is_dir())
        self.assertEqual(list(self.f.directory.iterdir()), []); self.assertFalse(self.f.plan_path.exists())
        self.assertEqual(self.f.clock.call_count, 1); self.f.bindings['preview_pose_family_sequence'].assert_called_once()
        self.f.bindings['draw_training_preview'].assert_not_called(); self.f.bindings['save_config'].assert_not_called()

    def test_jobs_root_is_read_after_drawing_and_original_json_options_remain(self):
        relocated = self.root / 'relocated'; relocated.mkdir()
        self.f.selected[0].update(name='合成物件', optional_number=float('nan'))
        self.f.draw_failure = lambda index, result: setattr(self.api, 'TRAINING_JOBS_DIR', relocated)
        result = self.api.training_preview(self.f.request(preview_count=1))
        actual = (relocated / self.f.plan_path.name).read_text(encoding='utf-8')
        self.assertEqual(actual, json.dumps(result, indent=2)); self.assertIn('NaN', actual)
        self.assertNotIn('合成物件', actual); self.assertFalse(self.f.plan_path.exists())
        self.f.bindings['output_write_dir'].assert_called_once_with('training_previews')

    def test_serialization_failure_keeps_images_without_plan_or_state(self):
        self.f.selected[0]['unserializable'] = object()
        with self.assertRaises(TypeError): self.api.training_preview(self.f.request(preview_count=1))
        self.assertTrue((self.f.directory / 'sample_01.png').is_file()); self.assertFalse(self.f.plan_path.exists())
        self.assertEqual(self.f.clock.call_count, 2)
        for name in ['set_training_state_for_user', 'merge_scoped_accessory_updates', 'save_config']: self.f.bindings[name].assert_not_called()

    def test_plan_write_error_preserves_images_and_prevents_state(self):
        error = OSError('plan write failed')
        with patch.object(Path, 'write_text', side_effect=error) as write:
            with self.assertRaises(OSError) as caught: self.api.training_preview(self.f.request(preview_count=1))
            self.assertIs(caught.exception, error); write.assert_called_once()
            self.assertEqual(write.call_args.kwargs, {'encoding': 'utf-8'})
        self.assertTrue((self.f.directory / 'sample_01.png').is_file()); self.assertFalse(self.f.plan_path.exists())
        for name in ['set_training_state_for_user', 'merge_scoped_accessory_updates', 'save_config']: self.f.bindings[name].assert_not_called()

    def test_missing_jobs_parent_preserves_images_and_skips_state(self):
        self.f.jobs.rmdir()
        with self.assertRaises(FileNotFoundError): self.api.training_preview(self.f.request(preview_count=1))
        self.assertTrue((self.f.directory / 'sample_01.png').is_file()); self.assertFalse(self.f.jobs.exists())
        self.assertEqual(self.f.clock.call_count, 2); self.f.bindings['set_training_state_for_user'].assert_not_called()
        self.f.bindings['save_config'].assert_not_called()

    def test_missing_url_keeps_written_plan_but_not_user_state(self):
        self.f.draw_failure = lambda index, result: result.pop('url')
        with self.assertRaises(KeyError): self.api.training_preview(self.f.request(preview_count=1))
        plan = json.loads(self.f.plan_path.read_text()); self.assertNotIn('url', plan['previews'][0])
        self.assertEqual(self.f.clock.call_count, 2); self.f.bindings['set_training_state_for_user'].assert_not_called()
        self.f.bindings['merge_scoped_accessory_updates'].assert_not_called(); self.f.bindings['save_config'].assert_not_called()

    def test_merge_failure_leaves_plan_and_in_memory_state_without_save(self):
        error = OSError('merge failure'); self.f.bindings['merge_scoped_accessory_updates'].side_effect = error
        with self.assertRaises(OSError) as caught: self.api.training_preview(self.f.request(preview_count=1))
        self.assertIs(caught.exception, error); self.assertTrue(self.f.plan_path.exists())
        self.assertEqual(self.f.full['training_by_user']['alice']['status'], 'preview_ready')
        self.f.bindings['merge_scoped_accessory_updates'].assert_called_once(); self.f.bindings['save_config'].assert_not_called()

    def test_save_failure_propagates_once_after_plan_state_merge(self):
        error = OSError('save failure'); self.f.bindings['save_config'].side_effect = error
        with self.assertRaises(OSError) as caught: self.api.training_preview(self.f.request(preview_count=1))
        self.assertIs(caught.exception, error); self.assertTrue(self.f.plan_path.exists())
        self.assertEqual(self.f.full['merged'], 1); self.assertIn('alice', self.f.full['training_by_user'])
        self.f.bindings['save_config'].assert_called_once()

    def test_false_save_result_still_returns_original_plan(self):
        self.f.bindings['save_config'].side_effect = None; self.f.bindings['save_config'].return_value = False
        result = self.api.training_preview(self.f.request(preview_count=1))
        self.assertEqual(result, json.loads(self.f.plan_path.read_text())); self.assertEqual(result['status'], 'preview_ready')

    def test_http_schema_default_errors_and_identity_failures(self):
        app = FastAPI(); app.get('/api/training/plan')(self.api.training_plan); app.post('/api/training/preview')(self.api.training_preview)
        with TestClient(app) as client:
            response = client.post('/api/training/preview', json={})
            self.assertEqual(response.status_code, 422); self.assertEqual(response.json()['detail'][0]['loc'], ['body', 'selected_accessory_ids'])
            self.f.bindings['current_auth_user'].assert_not_called()
            for status in [401, 403]:
                self.f.bindings['current_auth_user'].side_effect = HTTPException(status_code=status, detail='identity denied')
                for method, path, kwargs in [('get', '/api/training/plan', {}), ('post', '/api/training/preview', {'json': {'selected_accessory_ids': []}})]:
                    response = getattr(client, method)(path, **kwargs)
                    self.assertEqual(response.status_code, status); self.assertEqual(response.json(), {'detail': 'identity denied'})
            self.f.bindings['load_config'].assert_not_called()
        defaults = self.api.TrainingPreviewRequest(selected_accessory_ids=[])
        self.assertEqual((defaults.sample_count, defaults.train_mode, defaults.preview_count, defaults.preview_pose_family_policy, defaults.background_set_id, defaults.force_refresh), (4000, 'yolo_ocr', 5, 'auto', None, True))


    def test_workflow_callback_capture_before_argument_effects(self):
        targets = {'scope': 'scope_config_for_user', 'sanitize': 'public_path_sanitized', 'serialize': 'serialize_accessory_items', 'query_background': 'selected_background_set_id', 'ensure': 'ensure_training_assets_for_request', 'selected': 'selected_accessories', 'normalize': 'normalize_preview_pose_family_policy', 'submit_background': 'selected_background_set_id', 'draw': 'draw_training_preview'}
        for site, target in targets.items():
            for mode in ('ordinary', 'prior', 'missing'):
                with self.subTest(site=site, mode=mode), ExitStack() as scope:
                    api = self.api
                    f = PreviewWorkflowFixture(api, Path(scope.enter_context(tempfile.TemporaryDirectory(prefix='capture-workflow-')))).install(scope)
                    events = []
                    armed = [False]
                    done = RuntimeError('selected-callback')

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
                        if armed[0]:
                            events.append('argument')
                            setattr(api, target, ports['C'])

                    def after(name):
                        original = getattr(api, name)

                        def callback(*a, **k):
                            value = original(*a, **k)
                            prior()
                            return value
                        scope.enter_context(patch.object(api, name, callback))
                    if site == 'scope':
                        after('user_is_admin')
                        original = f.bindings['load_config']

                        def load():
                            argument()
                            return original()
                        scope.enter_context(patch.object(api, 'load_config', load))
                    elif site == 'sanitize':
                        after('filtered_training_state')
                        original = f.bindings['serialize_accessory_items']

                        def serialize(*a, **k):
                            argument()
                            return original(*a, **k)
                        scope.enter_context(patch.object(api, 'serialize_accessory_items', serialize))
                    elif site == 'serialize':

                        class Config(dict):

                            def get(inner, key, *default):
                                if key == 'accessories':
                                    argument()
                                return super().get(key, *default)
                        f.scoped = Config(f.scoped)
                        after('filtered_training_state')
                    elif site == 'query_background':

                        class Training(dict):

                            def get(inner, key, *default):
                                if key == 'background_set_id':
                                    argument()
                                return super().get(key, *default)
                        f.training = Training(f.training)
                        after('list_background_sets')
                    elif site == 'draw':

                        class Sequence(list):

                            def __getitem__(inner, key):
                                argument()
                                return super().__getitem__(key)
                        scope.enter_context(patch.object(api, 'preview_pose_family_sequence', lambda selected, count, policy: Sequence(['lying'] * count)))
                        original = f.clock
                        calls = [0]

                        def clock():
                            calls[0] += 1
                            value = original()
                            if calls[0] == 2:
                                prior()
                            return value
                        scope.enter_context(patch.object(api, 'time', SimpleNamespace(time=clock)))
                    else:
                        after({'ensure': 'scope_config_for_user', 'selected': 'ensure_training_assets_for_request', 'normalize': 'selected_accessories', 'submit_background': 'normalize_preview_pose_family_policy'}[site])
                    if site in ('scope', 'sanitize', 'serialize', 'query_background'):
                        operation = lambda: api.training_plan()
                    else:
                        field = {'ensure': 'selected_accessory_ids', 'selected': 'selected_accessory_ids', 'normalize': 'preview_pose_family_policy', 'submit_background': 'background_set_id'}.get(site)

                        class Request(api.TrainingPreviewRequest):

                            def __getattribute__(inner, key):
                                value = super().__getattribute__(key)
                                if key == field:
                                    argument()
                                return value
                        request = Request(selected_accessory_ids=['object', 'manual'], preview_count=1)
                        operation = lambda: api.training_preview(request)
                    caught = None
                    try:
                        operation()
                    except BaseException as exc:
                        caught = exc
                    if mode == 'missing':
                        self.assertIs(type(caught), TypeError)
                    else:
                        self.assertIs(caught, done)
                    self.assertEqual(events, ['prior', 'argument'] + ([] if mode == 'missing' else ['B' if mode == 'prior' else 'A']))
                    self.assertEqual(ports['A'].call_count, int(mode == 'ordinary'))
                    self.assertEqual(ports['B'].call_count, int(mode == 'prior'))
                    ports['C'].assert_not_called()

    def test_artifact_first_io_error_preserves_partial_outputs_without_retry(self):
        for site in ['mkdir', 'dumps', 'write_text']:
            with self.subTest(site=site), ExitStack() as scope:
                fixture, operation, _ = self.failure_fixture(scope, 'preview')
                calls = []; failure = OSError('artifact-first')
                original = json.dumps if site == 'dumps' else getattr(Path, site)
                def fail_once(*args, **kwargs):
                    target = site == 'dumps' or args[0] == (fixture.directory if site == 'mkdir' else fixture.plan_path)
                    if target:
                        calls.append(None)
                        if len(calls) == 1: raise failure
                    return original(*args, **kwargs)
                scope.enter_context(patch.object(json if site == 'dumps' else Path, site, fail_once))
                with self.assertRaises(OSError) as caught: operation()
                self.assertIs(caught.exception, failure); self.assertEqual(len(calls), 1)
                self.assertEqual(fixture.directory.exists(), site != 'mkdir')
                self.assertEqual((fixture.directory / 'sample_01.png').exists(), site != 'mkdir')
                self.assertFalse(fixture.plan_path.exists())
                for name in ['set_training_state_for_user', 'merge_scoped_accessory_updates', 'save_config']:
                    fixture.bindings[name].assert_not_called()

    def test_workflow_callbacks_refresh_after_rescope_and_between_previews(self):
        for site in ('rescope-selected', 'draw-refresh'):
            for missing in (False, True):
                with self.subTest(site=site, missing=missing), ExitStack() as scope:
                    api = self.api
                    f = PreviewWorkflowFixture(api, Path(scope.enter_context(tempfile.TemporaryDirectory(prefix='refresh-workflow-')))).install(scope)
                    events = []
                    armed = [False]
                    if site == 'rescope-selected':
                        f.ensure_changed = True
                        target = 'selected_accessories'

                        def selected(label, *a, **k):
                            events.append(label)
                            return f.selected
                        ports = {label: Mock(side_effect=lambda *a, _label=label, **k: selected(_label, *a, **k)) for label in ('A', 'B', 'C')}
                        scope.enter_context(patch.object(api, target, ports['A']))
                        original = f.bindings['scope_config_for_user']

                        def scoped(*a, **k):
                            value = original(*a, **k)
                            if f.scope_calls == 2:
                                events.append('rescope')
                                armed[0] = True
                                setattr(api, target, None if missing else ports['B'])
                            return value
                        scope.enter_context(patch.object(api, 'scope_config_for_user', scoped))

                        class Request(api.TrainingPreviewRequest):

                            def __getattribute__(inner, key):
                                value = super().__getattribute__(key)
                                if key == 'selected_accessory_ids' and armed[0]:
                                    events.append('argument')
                                    armed[0] = False
                                    setattr(api, target, ports['C'])
                                return value
                        request = Request(selected_accessory_ids=['object', 'manual'], preview_count=1)
                    else:
                        target = 'draw_training_preview'

                        def draw(label, *a, **k):
                            events.append(label)
                            value = f.draw(*a, **k)
                            if label == 'A':
                                setattr(api, target, None if missing else ports['B'])
                            return value
                        ports = {label: Mock(side_effect=lambda *a, _label=label, **k: draw(_label, *a, **k)) for label in ('A', 'B')}
                        scope.enter_context(patch.object(api, target, ports['A']))
                        request = f.request(preview_count=2)
                    caught = None
                    try:
                        api.training_preview(request)
                    except BaseException as exc:
                        caught = exc
                    if missing:
                        self.assertIs(type(caught), TypeError)
                        self.assertFalse(f.plan_path.exists())
                        f.bindings['set_training_state_for_user'].assert_not_called()
                    else:
                        self.assertIsNone(caught)
                        self.assertTrue(f.plan_path.is_file())
                    if site == 'rescope-selected':
                        self.assertEqual(events, ['rescope', 'argument'] + ([] if missing else ['B']))
                        ports['A'].assert_not_called()
                        ports['C'].assert_not_called()
                    else:
                        self.assertEqual(events, ['A'] + ([] if missing else ['B']))
                        self.assertEqual(ports['A'].call_count, 1)
                    self.assertEqual(ports['B'].call_count, int(not missing))

    def failure_fixture(self, scope, mode):
        root = Path(scope.enter_context(tempfile.TemporaryDirectory(dir=self.root, prefix='first-error-')))
        fixture = PreviewWorkflowFixture(self.api, root)
        fixture.ensure_changed = mode == 'rescope'
        fixture.selected[0]['clean_sprite_count'] = 0
        fixture.clock = fixture.callback('clock', Mock(side_effect=itertools.chain([1700.9, 1701.234], itertools.repeat(1702.8))))
        fixture.install(scope)
        operation = (lambda: self.api.training_plan('bob')) if mode == 'query' else (lambda: self.api.training_preview(fixture.request(preview_count=2)))
        ports = {name: (self.api, name, port) for name, port in fixture.bindings.items()}
        ports.update(clock=(self.api.time, 'time', fixture.clock), uuid=(self.api.uuid, 'uuid4', fixture.uuid))
        return fixture, operation, ports

    def test_workflow_first_callback_error_propagates_without_retry(self):
        for mode in ['query', 'preview', 'rescope']:
            with ExitStack() as scope:
                _, operation, ports = self.failure_fixture(scope, mode); operation()
                counts = {name: port.call_count for name, (_, _, port) in ports.items() if port.call_count}
            for name, count in counts.items():
                for index in range(1, count + 1):
                    with self.subTest(mode=mode, name=name, index=index), ExitStack() as scope:
                        _, operation, ports = self.failure_fixture(scope, mode)
                        owner, field, original = ports[name]; calls = []; failure = RuntimeError('workflow-first')
                        def fail_once(*args, **kwargs):
                            calls.append(None)
                            if len(calls) == index: raise failure
                            return original(*args, **kwargs)
                        scope.enter_context(patch.object(owner, field, fail_once))
                        with self.assertRaises(RuntimeError) as caught: operation()
                        self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_new_workflow_getter_errors_propagate_without_retry(self):
        from dataclasses import replace
        query = self.api._training_plan_query; submission = self.api._training_preview_submission
        artifacts = self.api._training_preview_artifacts
        fields = [('query', query, 'access', 'sanitize'), ('query', query, 'config', 'scope'),
                  ('query', query, None, 'serialize'), ('query', query, 'backgrounds', 'selected'), ('query', query, 'backgrounds', 'physical_size'),
                  ('preview', submission, 'config', 'ensure'), ('preview', submission, 'selection', 'selected'),
                  ('preview', submission, 'policy', 'normalize'), ('preview', submission, 'policy', 'background'),
                  ('preview', submission, None, 'draw'), ('preview', artifacts, None, 'output'), ('preview', artifacts, None, 'jobs')]
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
                with self.subTest(mode=mode, group=group_name, field=field, index=index), ExitStack() as scope:
                    _, operation, _ = self.failure_fixture(scope, mode); calls = []; failure = RuntimeError('workflow-getter-first')
                    def fail_once(*args, **kwargs):
                        calls.append(None)
                        if len(calls) == index: raise failure
                        return original(*args, **kwargs)
                    install(scope, service, group_name, field, fail_once)
                    with self.assertRaises(RuntimeError) as caught: operation()
                    self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_independent_apps_threadpool_identity_storage_and_zero_constructor_reads(self):
        import asyncio
        from contextvars import ContextVar
        import threading
        import httpx
        from local_inspection_service.training.preview_query import PlanAccess, PlanBackgrounds, PlanConfiguration, TrainingPlanQuery
        from local_inspection_service.training.preview_submission import PreviewConfiguration, PreviewSelection, PreviewPolicy, TrainingPreviewSubmission
        from local_inspection_service.training.preview_artifacts import PreviewArtifactStore
        from local_inspection_service.training.preview_api import register
        identity = ContextVar('preview-workflow-user'); barrier = threading.Barrier(2)
        instances = []
        for index, owner in enumerate(['alice', 'bob']):
            fixture = PreviewWorkflowFixture(self.api, self.root / owner, owner)
            fixture.selected[0]['id'] = owner + '-object'; fixture.training['owner_marker'] = owner
            b = fixture.bindings
            def current():
                barrier.wait(timeout=10)
                return identity.get()
            current_port = Mock(side_effect=current)
            output = Mock(return_value=fixture.output); jobs = Mock(return_value=fixture.jobs)
            physical = Mock(return_value=fixture.physical)
            artifacts = PreviewArtifactStore(output, jobs)
            query = TrainingPlanQuery(PlanAccess(current_port, b['user_is_admin'], (lambda fn=b['public_path_sanitized']: fn)),
                                      PlanConfiguration(b['load_config'], (lambda fn=b['scope_config_for_user']: fn), b['filtered_training_state']),
                                      PlanBackgrounds(b['list_background_sets'], (lambda fn=b['selected_background_set_id']: fn), physical),
                                      (lambda fn=b['serialize_accessory_items']: fn), b['training_execution_status'])
            submission = TrainingPreviewSubmission(current_port,
                PreviewConfiguration(b['load_config'], b['scope_config_for_user'], (lambda fn=b['ensure_training_assets_for_request']: fn),
                                     b['set_training_state_for_user'], b['merge_scoped_accessory_updates'], b['save_config']),
                PreviewSelection((lambda fn=b['selected_accessories']: fn), b['accessory_uid'], b['accessory_material_type'], b['clean_sprite_assets'], b['accessory_sprite_version'], b['preview_cache_key']),
                PreviewPolicy((lambda fn=b['normalize_preview_pose_family_policy']: fn), (lambda fn=b['selected_background_set_id']: fn), b['preview_pose_family_sequence'], b['preview_pose_family_sequence_label']),
                artifacts, (lambda fn=b['draw_training_preview']: fn), fixture.clock, fixture.uuid)
            app = FastAPI()
            @app.middleware('http')
            async def account_context(request, call_next):
                token = identity.set({'id': request.headers['x-fixture-owner'], 'role': 'member'})
                try: return await call_next(request)
                finally: identity.reset(token)
            routes = register(app, query, submission)
            for name in routes.__dataclass_fields__:
                self.assertEqual([route.endpoint for route in app.routes if route.name == name], [getattr(routes, name)])
            self.assertEqual(app.router.on_startup, [])
            self.assertEqual(fixture.events, [])
            for callback in [current_port, output, jobs, physical, fixture.clock, fixture.uuid]: callback.assert_not_called()
            instances.append((app, fixture, current_port, output, jobs, physical))
        for name in self.f.bindings:
            self.stack.enter_context(patch.object(self.api, name, side_effect=AssertionError('unexpected root dependency')))
        async def request(instance):
            app, fixture, *_ = instance; owner = fixture.user['id']
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://fixture.invalid') as client:
                headers = {'x-fixture-owner': owner}
                result = await client.get('/api/training/plan?user_id=ignored', headers=headers)
                self.assertEqual(result.status_code, 200); self.assertEqual(result.json()['training']['owner_marker'], owner)
                result = await client.post('/api/training/preview', headers=headers,
                    json={'selected_accessory_ids': [owner + '-object'], 'preview_count': 1, 'force_refresh': False})
                self.assertEqual(result.status_code, 200); self.assertEqual(result.json()['selected_accessories'][0]['id'], owner + '-object')
                self.assertNotIn('sanitized', result.json())
                return result.json()
        async def both(): return await asyncio.gather(*(request(instance) for instance in instances))
        results = asyncio.run(both())
        for (_, fixture, current, output, jobs, physical), result in zip(instances, results):
            owner = fixture.user['id']
            self.assertEqual(json.loads(fixture.plan_path.read_text()), result)
            self.assertEqual(set(fixture.full['training_by_user']), {owner})
            for entry in fixture.bindings['scope_config_for_user'].call_args_list:
                self.assertIs(entry.args[0], fixture.full); self.assertEqual(entry.args[1]['id'], owner)
            self.assertEqual(fixture.bindings['scope_config_for_user'].call_args_list[0].args[2], None)
            self.assertEqual(len(fixture.bindings['scope_config_for_user'].call_args_list[1].args), 2)
            self.assertEqual(current.call_count, 2); self.assertEqual(fixture.clock.call_count, 3)
            output.assert_called_once_with('training_previews'); jobs.assert_called_once_with()
            physical.assert_called_once_with()
            fixture.bindings['public_path_sanitized'].assert_called_once()
        self.assertIsNone(identity.get(None))


if __name__ == '__main__': unittest.main()
