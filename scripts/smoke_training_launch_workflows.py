"""Offline contracts for training launch sequencing and account-scoped status queries."""
from contextlib import ExitStack
import copy
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, call, patch
from fastapi import HTTPException
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class LaunchFixture:
    def __init__(self):
        self.events = []; self.saved = []; self.states = []; self.queued = []
        self.user = {'id': 'alice', 'role': 'member'}
        self.full = {'training': {'preview_urls': ['old']}}
        self.config = {'scope': 1}; self.fresh = {'scope': 2}
        self.selected = [{'id': 'b'}, {'id': 'a'}, {'id': 'b'}]
        self.renewed = [{'id': 'c'}, {'id': 'c'}]
        self.task = {'job_id': 'queued', 'sample_count': 19, 'epochs': 7, 'image_size': 512,
                     'background_set_id': None, 'note': 'queued note', 'estimated_minutes': 3, 'estimated_gb': 0.5}
        self.dataset = {'id': 'data', 'selected_accessory_ids': ['z', 'z']}
        self.physical = {'width': 11, 'height': 22}
        self.result = {'internal': 'already projected'}
        self.current = Mock(side_effect=lambda: self.event('user') or self.user)
        self.load = Mock(side_effect=lambda: self.event('load') or self.full)
        self.scope = Mock(side_effect=lambda *args: self.event('scope') or self.config)
        self.select = Mock(side_effect=lambda *args: self.event('select') or self.selected)
        self.find_dataset = Mock(side_effect=lambda *args, **kwargs: self.event('dataset') or self.dataset)
        self.approve = Mock(side_effect=lambda *args, **kwargs: self.event('approve'))
        self.ensure = Mock(side_effect=lambda *args: self.event('ensure') or False)
        self.enqueue = Mock(side_effect=self.queue)
        self.clock = Mock(side_effect=lambda: self.event('clock') or 100.9)
        self.set_state = Mock(side_effect=self.state)
        self.merge = Mock(side_effect=lambda *args: self.event('merge'))
        self.save = Mock(side_effect=self.persist)
        self.admin = Mock(side_effect=lambda user: self.event('admin') or user.get('role') == 'admin')
        self.filtered = Mock(side_effect=lambda *args: self.event('filtered') or self.result)
    def event(self, name): self.events.append(name)
    def queue(self, *args, **kwargs): self.event('enqueue'); self.queued.append((args, kwargs)); return self.task
    def state(self, full, user, state): self.event('state'); self.states.append(state); full['training'] = state
    def persist(self, full): self.event('save'); self.saved.append(copy.deepcopy(full)); return False
    def bind(self, api, stack):
        values = {'current_auth_user': self.current, 'load_config': self.load, 'scope_config_for_user': self.scope,
                  'selected_accessories': self.select, 'dataset_for_training': self.find_dataset,
                  'validate_approved_preview': self.approve, 'ensure_training_assets_for_request': self.ensure,
                  'enqueue_training_task': self.enqueue, 'set_training_state_for_user': self.set_state,
                  'merge_scoped_accessory_updates': self.merge, 'save_config': self.save, 'BACKGROUND_SIZE_MM': self.physical,
                  'user_is_admin': self.admin, 'filtered_training_state': self.filtered}
        for name, value in values.items(): stack.enter_context(patch.object(api, name, value))
        stack.enter_context(patch('time.time', self.clock))
        stack.enter_context(patch.object(api, 'public_path_sanitized', side_effect=AssertionError('unexpected sanitization')))
        return values


class TrainingLaunchContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ); cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='training-launch-root-')
        root = Path(cls.runtime.name); (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server; cls.original_enqueue = staticmethod(server.enqueue_training_task)
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.f = LaunchFixture(); self.f.bind(self.api, self.stack)
        for target in ['requests.request', 'subprocess.Popen', 'os.kill']:
            self.stack.enter_context(patch(target, side_effect=AssertionError('unexpected external operation')))
    def request(self, **kwargs):
        return self.api.TrainingStartRequest(selected_accessory_ids=['requested'], approved_preview_id='approved', **kwargs)
    def test_start_exact_order_state_and_identity_without_dataset(self):
        f = self.f; request = self.request()
        self.assertIs(self.api.request_training(request), f.task)
        self.assertEqual(f.events, ['user', 'load', 'scope', 'select', 'approve', 'ensure', 'enqueue', 'clock', 'state', 'merge', 'save'])
        f.scope.assert_called_once_with(f.full, f.user); f.select.assert_called_once_with(f.config, request.selected_accessory_ids)
        f.approve.assert_called_once_with(f.config, request, f.selected, user=f.user)
        f.ensure.assert_called_once_with(f.full, f.config, f.user, ['b', 'a', 'b'])
        f.enqueue.assert_called_once_with(request, f.selected, 'train_model', dataset=None)
        self.assertIs(f.enqueue.call_args.args[1], f.selected)
        expected = {'status': 'queued', 'last_requested_at': 100, 'selected_accessory_ids': ['b', 'a', 'b'],
                    'sample_count': 19, 'mode': request.train_mode, 'epochs': 7, 'image_size': 512,
                    'background_set_id': None, 'approved_preview_id': 'approved', 'active_training_task_id': 'queued',
                    'note': 'queued note', 'estimated_minutes': 3}
        self.assertEqual(f.states, [expected]); f.set_state.assert_called_once_with(f.full, f.user, expected)
        self.assertIs(f.full['training'], f.states[0]); f.merge.assert_called_once_with(f.full, f.config, f.user)
        f.save.assert_called_once_with(f.full); f.find_dataset.assert_not_called()
    def test_start_ensure_true_reselects_after_single_approval(self):
        f = self.f; request = self.request(); f.ensure.side_effect = lambda *args: f.event('ensure') or True
        f.scope.side_effect = lambda *args: f.event('scope') or (f.config if f.scope.call_count == 1 else f.fresh)
        f.select.side_effect = lambda config, ids: f.event('select') or (f.selected if config is f.config else f.renewed)
        self.api.request_training(request)
        self.assertEqual(f.events, ['user', 'load', 'scope', 'select', 'approve', 'ensure', 'scope', 'select', 'enqueue', 'clock', 'state', 'merge', 'save'])
        f.approve.assert_called_once_with(f.config, request, f.selected, user=f.user)
        self.assertEqual(f.select.call_args_list, [call(f.config, request.selected_accessory_ids), call(f.fresh, request.selected_accessory_ids)])
        f.enqueue.assert_called_once_with(request, f.renewed, 'train_model', dataset=None)
        self.assertEqual(f.states[0]['selected_accessory_ids'], ['c', 'c']); f.merge.assert_called_once_with(f.full, f.fresh, f.user)
    def test_start_dataset_selection_fallback_and_empty_dataset_identity(self):
        for dataset in [{'id': 'd', 'selected_accessory_ids': ['z', 'z']}, {'id': 'd', 'selected_accessory_ids': []}, {}]:
            with self.subTest(dataset=dataset), ExitStack() as stack:
                f = LaunchFixture(); f.bind(self.api, stack); f.find_dataset.side_effect = lambda *args, **kwargs: f.event('dataset') or dataset
                request = self.request(dataset_id=' '); self.api.request_training(request)
                self.assertEqual(f.events, ['user', 'load', 'scope', 'dataset', 'select', 'enqueue', 'clock', 'state', 'merge', 'save'])
                f.find_dataset.assert_called_once_with(' ', user=f.user)
                f.select.assert_called_once_with(f.config, dataset.get('selected_accessory_ids') or request.selected_accessory_ids)
                f.enqueue.assert_called_once_with(request, f.selected, 'train_model', dataset=dataset)
                self.assertIs(f.enqueue.call_args.kwargs['dataset'], dataset)
                f.approve.assert_not_called(); f.ensure.assert_not_called()
    def test_empty_dataset_id_uses_approval_and_rejects_before_queue(self):
        f = self.f; error = HTTPException(409, 'approval mismatch'); f.approve.side_effect = error
        with self.assertRaises(HTTPException) as caught: self.api.request_training(self.request(dataset_id=''))
        self.assertIs(caught.exception, error); f.find_dataset.assert_not_called(); f.ensure.assert_not_called(); f.enqueue.assert_not_called(); f.save.assert_not_called()
    def test_dataset_failure_propagates_before_selection(self):
        f = self.f; error = HTTPException(403, 'denied'); f.find_dataset.side_effect = [error, f.dataset]
        with self.assertRaises(HTTPException) as caught: self.api.request_training(self.request(dataset_id='data'))
        self.assertIs(caught.exception, error); f.find_dataset.assert_called_once_with('data', user=f.user)
        f.select.assert_not_called(); f.approve.assert_not_called(); f.ensure.assert_not_called()
        f.enqueue.assert_not_called(); f.clock.assert_not_called(); f.set_state.assert_not_called(); f.merge.assert_not_called(); f.save.assert_not_called()
    def test_generate_ignores_dataset_reselects_and_clears_preview_metadata(self):
        f = self.f; request = self.request(dataset_id='must not load')
        f.ensure.side_effect = lambda *args: f.event('ensure') or True
        f.scope.side_effect = lambda *args: f.event('scope') or (f.config if f.scope.call_count == 1 else f.fresh)
        f.select.side_effect = lambda config, ids: f.event('select') or (f.selected if config is f.config else f.renewed)
        self.assertIs(self.api.request_sample_generation(request), f.task)
        self.assertEqual(f.events, ['user', 'load', 'scope', 'select', 'approve', 'ensure', 'scope', 'select', 'enqueue', 'clock', 'state', 'merge', 'save'])
        f.approve.assert_called_once_with(f.config, request, f.selected, user=f.user)
        f.ensure.assert_called_once_with(f.full, f.config, f.user, ['b', 'a', 'b'])
        f.enqueue.assert_called_once_with(request, f.renewed, 'generate_samples'); f.find_dataset.assert_not_called()
        expected = {'status': 'queued', 'last_requested_at': 100, 'selected_accessory_ids': ['c', 'c'], 'sample_count': 19,
                    'mode': request.train_mode, 'background_set_id': None, 'approved_preview_id': 'approved',
                    'preview_urls': [], 'previews': [], 'preview_cache_key': None, 'preview_sprite_versions': {},
                    'render_policy': {'background_physical_size': f.physical,
                      'physical_size_rule': 'Object samples use clean alpha sprites scaled by physical_size; document samples paste the saved rectified full document directly at paper physical_size.',
                      'pose_collection_rule': 'Pose Collection provides pose only; physical_size is applied only during preview and dataset rendering.'},
                    'active_training_task_id': 'queued', 'note': 'queued note', 'estimated_minutes': 3, 'estimated_gb': 0.5}
        self.assertEqual(f.states, [expected]); self.assertIs(f.states[0]['render_policy']['background_physical_size'], f.physical)
        f.merge.assert_called_once_with(f.full, f.fresh, f.user); f.save.assert_called_once_with(f.full)
    def test_launch_failures_preserve_partial_state_and_never_retry(self):
        stages = ['enqueue', 'set_state', 'merge', 'save']
        for name in ['request_training', 'request_sample_generation']:
            for stage in stages:
                with self.subTest(name=name, stage=stage), ExitStack() as stack:
                    f = LaunchFixture(); f.bind(self.api, stack); target = getattr(f, stage); original = target.side_effect
                    error = OSError('failed ' + stage)
                    def fail_once(*args, **kwargs):
                        result = original(*args, **kwargs)
                        if target.call_count == 1: raise error
                        return result
                    target.side_effect = fail_once
                    with self.assertRaises(OSError) as caught: getattr(self.api, name)(self.request())
                    self.assertIs(caught.exception, error)
                    for index, value in enumerate(stages): self.assertEqual(getattr(f, value).call_count, int(index <= stages.index(stage)))
                    self.assertEqual(len(f.queued), 1); self.assertEqual(len(f.states), int(stage != 'enqueue'))
                    self.assertEqual(len(f.saved), int(stage == 'save'))
                    if stage != 'enqueue': self.assertIs(f.full['training'], f.states[0])
                    self.assertEqual(f.clock.call_count, int(stage != 'enqueue'))
    def test_selection_approval_and_asset_errors_never_enqueue(self):
        for name in ['request_training', 'request_sample_generation']:
            stages = ['current', 'load', 'scope', 'select', 'approve', 'ensure']
            for stage in stages:
                with self.subTest(name=name, stage=stage), ExitStack() as stack:
                    f = LaunchFixture(); f.bind(self.api, stack); target = getattr(f, stage)
                    successful = {'current': f.user, 'load': f.full, 'scope': f.config,
                                  'select': f.selected, 'approve': None, 'ensure': False}
                    error = RuntimeError(stage); target.side_effect = [error, successful[stage]]
                    with self.assertRaises(RuntimeError) as caught: getattr(self.api, name)(self.request())
                    self.assertIs(caught.exception, error); target.assert_called_once(); f.enqueue.assert_not_called(); f.set_state.assert_not_called(); f.save.assert_not_called()
                    for value in stages[stages.index(stage) + 1:]: getattr(f, value).assert_not_called()
                    f.clock.assert_not_called(); f.merge.assert_not_called()
            for stage in ['scope', 'select']:
                with self.subTest(name=name, refresh_stage=stage), ExitStack() as stack:
                    f = LaunchFixture(); f.bind(self.api, stack); f.ensure.side_effect = None; f.ensure.return_value = True
                    target = getattr(f, stage); error = RuntimeError('refresh ' + stage)
                    target.side_effect = [f.config, error, f.fresh] if stage == 'scope' else [f.selected, error, f.renewed]
                    request = self.request()
                    with self.assertRaises(RuntimeError) as caught: getattr(self.api, name)(request)
                    self.assertIs(caught.exception, error); self.assertEqual(target.call_count, 2)
                    self.assertEqual(f.scope.call_count, 2); self.assertEqual(f.select.call_count, 1 if stage == 'scope' else 2)
                    f.approve.assert_called_once_with(f.config, request, f.selected, user=f.user)
                    f.ensure.assert_called_once_with(f.full, f.config, f.user, ['b', 'a', 'b'])
                    f.enqueue.assert_not_called(); f.clock.assert_not_called(); f.set_state.assert_not_called(); f.merge.assert_not_called(); f.save.assert_not_called()
    def test_missing_task_fields_fail_after_enqueue_without_state_save(self):
        for name, field in [('request_training', 'epochs'), ('request_sample_generation', 'estimated_gb')]:
            with self.subTest(name=name), ExitStack() as stack:
                f = LaunchFixture(); f.bind(self.api, stack); del f.task[field]
                with self.assertRaises(KeyError): getattr(self.api, name)(self.request())
                f.enqueue.assert_called_once(); f.clock.assert_called_once(); f.set_state.assert_not_called(); f.merge.assert_not_called(); f.save.assert_not_called()
    def test_status_target_scope_order_and_unsanitized_result(self):
        for role in ['admin', 'member']:
            for target in [None, '', 'bob']:
                with self.subTest(role=role, target=target), ExitStack() as stack:
                    f = LaunchFixture(); f.user['role'] = role; f.bind(self.api, stack)
                    self.assertIs(self.api.training_status(target), f.result)
                    self.assertEqual(f.events, ['user', 'admin', 'load', 'scope', 'filtered'])
                    expected = target if role == 'admin' else None
                    f.admin.assert_called_once_with(f.user); f.scope.assert_called_once_with(f.full, f.user, expected)
                    f.filtered.assert_called_once_with(f.config, f.user, expected); f.save.assert_not_called(); f.enqueue.assert_not_called()
    def test_status_dependency_errors_propagate_once(self):
        stages = ['current', 'admin', 'load', 'scope', 'filtered']
        for stage in stages:
            with self.subTest(stage=stage), ExitStack() as stack:
                f = LaunchFixture(); f.bind(self.api, stack); error = RuntimeError(stage)
                getattr(f, stage).side_effect = [error, {}]
                with self.assertRaises(RuntimeError) as caught: self.api.training_status('bob')
                self.assertIs(caught.exception, error)
                for index, value in enumerate(stages): self.assertEqual(getattr(f, value).call_count, int(index <= stages.index(stage)))
    def test_real_submission_nullable_background_and_frozen_task_binding(self):
        from scripts.smoke_training_runner import Fixture
        f = self.f
        with ExitStack() as stack:
            runner = Fixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='launch-binding-'))); runner.bind(self.api, stack)
            runner.background.side_effect = None; runner.background.return_value = None
            runner.estimate.side_effect = lambda *args, **kwargs: {'estimated_minutes': 2, 'estimated_gb': 0.1}
            runner.public.side_effect = lambda task: task
            stack.enter_context(patch.object(self.api, 'enqueue_training_task', self.original_enqueue))
            stack.enter_context(patch.object(threading, 'Thread', runner.thread_factory))
            token = self.api._request_user.set(f.user); stack.callback(self.api._request_user.reset, token)
            task = self.api.request_training(self.request())
            self.assertIs(task, runner.saved[0]); self.assertIsNone(task['background_set_id']); self.assertIsNone(f.states[0]['background_set_id'])
            self.assertEqual(task['model_profiles'], {'pipeline': {'version': 1}})
            runner.resolver.version = 99; self.assertEqual(task['model_profiles'], {'pipeline': {'version': 1}})
            runner.thread.start.assert_called_once(); runner.popen.assert_not_called(); runner.generate.assert_not_called()
            self.assertIs(runner.threads[task['job_id']], runner.thread)


    def test_clock_failure_after_enqueue_preserves_task_without_later_writes(self):
        for name in ['request_training', 'request_sample_generation']:
            with self.subTest(name=name), ExitStack() as stack:
                f = LaunchFixture(); f.bind(self.api, stack); error = RuntimeError('clock after queue')
                f.clock.side_effect = [error, 200]
                with self.assertRaises(RuntimeError) as caught: getattr(self.api, name)(self.request())
                self.assertIs(caught.exception, error); f.enqueue.assert_called_once(); f.clock.assert_called_once()
                self.assertEqual(len(f.queued), 1); f.set_state.assert_not_called(); f.merge.assert_not_called(); f.save.assert_not_called()

    def test_http_validation_identity_errors_and_route_order(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI()
        app.post('/api/training/start')(self.api.request_training)
        app.post('/api/training/generate')(self.api.request_sample_generation)
        app.get('/api/training/status')(self.api.training_status)
        with TestClient(app) as client:
            for path in ['/api/training/start', '/api/training/generate']:
                response = client.post(path, json={})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()['detail'][0]['loc'], ['body', 'selected_accessory_ids'])
            self.f.current.assert_not_called()
            for status in [401, 403]:
                self.f.current.side_effect = HTTPException(status, 'identity denied')
                for path in ['/api/training/start', '/api/training/generate']:
                    response = client.post(path, json={'selected_accessory_ids': []})
                    self.assertEqual((response.status_code, response.json()), (status, {'detail': 'identity denied'}))
                response = client.get('/api/training/status?user_id=bob')
                self.assertEqual((response.status_code, response.json()), (status, {'detail': 'identity denied'}))
            self.f.load.assert_not_called()
            self.f.current.side_effect = lambda: self.f.user
            self.f.approve.side_effect = HTTPException(409, 'stale preview')
            response = client.post('/api/training/start', json={'selected_accessory_ids': []})
            self.assertEqual((response.status_code, response.json()), (409, {'detail': 'stale preview'})); self.f.enqueue.assert_not_called()
        paths = [getattr(route, 'path', '') for route in self.api.app.routes]
        sequence = ['/api/training/start', '/api/training/runpod/datasets/{job_id}/{token}/dataset.zip',
                    '/api/training/runpod/artifacts/{job_id}/{token}/run.zip', '/api/training/generate', '/api/training/status']
        positions = [paths.index(path) for path in sequence]
        self.assertEqual(positions, sorted(positions)); self.assertTrue(all(paths.count(path) == 1 for path in sequence))

    def test_callback_capture_before_argument_effects(self):
        for site in ['dataset', 'dataset-select', 'dataset-select-fallback', 'train-select', 'generate-select', 'train-reselect', 'generate-reselect', 'train-ensure', 'generate-ensure', 'status']:
            for mode in ['ordinary', 'prior', 'missing']:
                with self.subTest(site=site, mode=mode), ExitStack() as stack:
                    f = LaunchFixture()
                    api = self.api
                    f.bind(api, stack)
                    events = []
                    armed = [False]
                    done = RuntimeError('captured callback')
                    hooks = {}
                    reads = {}
                    target = 'dataset_for_training' if site == 'dataset' else 'ensure_training_assets_for_request' if site.endswith('ensure') else 'scope_config_for_user' if site == 'status' else 'selected_accessories'

                    def hit(label, *args, **kwargs):
                        if site.endswith('reselect') and (not armed[0]):
                            return f.selected
                        events.append(label)
                        raise done
                    ports = {label: Mock(side_effect=lambda *a, _label=label, **k: hit(_label, *a, **k)) for label in ['A', 'B', 'C']}
                    stack.enter_context(patch.object(api, target, ports['A']))

                    def prior():
                        events.append('prior')
                        armed[0] = True
                        setattr(api, target, None if mode == 'missing' else ports['B'] if mode == 'prior' else ports['A'])

                    def argument(label='argument'):
                        events.append(label)
                        setattr(api, target, ports['C'])

                    class Request(api.TrainingStartRequest):

                        def __getattribute__(inner, key):
                            value = super().__getattribute__(key)
                            if key in hooks:
                                hooks[key]()
                            return value
                    request = Request(selected_accessory_ids=['requested'], approved_preview_id='approved', dataset_id='data' if site.startswith('dataset') else None)

                    def read_dataset():
                        reads['dataset'] = reads.get('dataset', 0) + 1
                        if reads['dataset'] == 1:
                            prior()
                        else:
                            argument()
                    if site == 'dataset':
                        hooks['dataset_id'] = read_dataset
                    elif site in ['dataset-select', 'dataset-select-fallback']:

                        class Dataset(dict):

                            def get(inner, key, *default):
                                if key == 'selected_accessory_ids':
                                    argument('get')
                                return super().get(key, *default)
                        dataset = Dataset(selected_accessory_ids=[] if site.endswith('fallback') else ['dataset-selected'])
                        f.find_dataset.side_effect = lambda *a, **k: prior() or dataset
                        if site.endswith('fallback'):
                            hooks['selected_accessory_ids'] = lambda: argument('request')
                    elif site in ['train-select', 'generate-select']:
                        hooks['selected_accessory_ids'] = argument
                        if site == 'train-select':
                            hooks['dataset_id'] = prior
                        else:
                            f.scope.side_effect = lambda *a: prior() or f.config
                    elif site.endswith('reselect'):
                        f.ensure.side_effect = lambda *a: True

                        def scope(*args):
                            if f.scope.call_count == 2:
                                prior()
                            return f.config
                        f.scope.side_effect = scope

                        def selected_attribute():
                            reads['selected'] = reads.get('selected', 0) + 1
                            if reads['selected'] == 2:
                                argument()
                        hooks['selected_accessory_ids'] = selected_attribute
                    elif site.endswith('ensure'):

                        class Item(dict):

                            def __getitem__(inner, key):
                                if key == 'id':
                                    argument()
                                return super().__getitem__(key)
                        f.selected = [Item(id='a')]
                        f.approve.side_effect = lambda *a, **k: prior()
                    else:
                        f.admin.side_effect = lambda *a: prior() or False
                        f.load.side_effect = lambda: argument() or f.full
                    operation = (lambda: api.training_status('bob')) if site == 'status' else (lambda: api.request_sample_generation(request)) if site.startswith('generate') else lambda: api.request_training(request)
                    caught = None
                    try:
                        operation()
                    except BaseException as exc:
                        caught = exc
                    if mode == 'missing':
                        self.assertIs(type(caught), TypeError)
                    else:
                        self.assertIs(caught, done)
                    arguments = ['get', 'request'] if site == 'dataset-select-fallback' else ['get'] if site == 'dataset-select' else ['argument']
                    self.assertEqual(events, ['prior'] + arguments + ([] if mode == 'missing' else ['B' if mode == 'prior' else 'A']))
                    self.assertEqual(ports['A'].call_count, int(site.endswith('reselect')) + int(mode == 'ordinary'))
                    self.assertEqual(ports['B'].call_count, int(mode == 'prior'))
                    ports['C'].assert_not_called()

    def failure_fixture(self, scope, mode):
        fixture = LaunchFixture(); values = fixture.bind(self.api, scope)
        if mode.endswith('rescope'): fixture.ensure.side_effect = lambda *args: fixture.event('ensure') or True
        if mode == 'status': operation = lambda: self.api.training_status('bob')
        elif mode.startswith('generate'): operation = lambda: self.api.request_sample_generation(self.request())
        else: operation = lambda: self.api.request_training(self.request(dataset_id='data' if mode == 'dataset' else None))
        ports = {name: (self.api, name, port) for name, port in values.items() if callable(port)}
        import time
        ports['clock'] = (time, 'time', fixture.clock)
        return fixture, operation, ports

    def test_first_dependency_error_propagates_without_retry(self):
        for mode in ['start', 'start_rescope', 'generate', 'generate_rescope', 'dataset', 'status']:
            with ExitStack() as scope:
                _, operation, ports = self.failure_fixture(scope, mode); operation()
                counts = {name: port.call_count for name, (_, _, port) in ports.items() if port.call_count}
            for name, count in counts.items():
                for index in range(1, count + 1):
                    with self.subTest(mode=mode, name=name, index=index), ExitStack() as scope:
                        _, operation, ports = self.failure_fixture(scope, mode)
                        owner, field, original = ports[name]; calls = []; failure = RuntimeError('launch-first')
                        def fail_once(*args, **kwargs):
                            calls.append(None)
                            if len(calls) == index: raise failure
                            return original(*args, **kwargs)
                        scope.enter_context(patch.object(owner, field, fail_once))
                        with self.assertRaises(RuntimeError) as caught: operation()
                        self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_new_launch_getter_first_error_propagates_without_retry(self):
        from dataclasses import replace
        submission = self.api._training_launch_submission; query = self.api._training_status_query
        fields = [(mode, submission, group, field) for mode in ['start', 'start_rescope', 'generate', 'generate_rescope']
                  for group, field in [('inputs', 'selected'), ('config', 'ensure')]]
        fields += [('dataset', submission, 'inputs', 'selected'), ('dataset', submission, 'inputs', 'dataset'),
                   ('generate', submission, None, 'physical_size'), ('status', query, None, 'scope')]
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
                    _, operation, _ = self.failure_fixture(scope, mode); calls = []; failure = RuntimeError('launch-getter-first')
                    def fail_once(*args, **kwargs):
                        calls.append(None)
                        if len(calls) == index: raise failure
                        return original(*args, **kwargs)
                    install(scope, service, group_name, field, fail_once)
                    with self.assertRaises(RuntimeError) as caught: operation()
                    self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_independent_apps_threadpool_identity_and_late_physical_provider(self):
        import asyncio
        from contextvars import ContextVar
        import httpx
        from fastapi import FastAPI
        from local_inspection_service.training.launch_submission import LaunchConfiguration, LaunchInputs, TrainingLaunchSubmission
        from local_inspection_service.training.status_query import TrainingStatusQuery
        from local_inspection_service.training.launch_api import register_start, register_generate, register_status
        identity = ContextVar('launch-fixture-user'); barrier = threading.Barrier(2); instances = []
        def current():
            barrier.wait(timeout=10)
            return identity.get()
        for owner in ['alice', 'bob']:
            f = LaunchFixture(); f.user = {'id': owner, 'role': 'member'}
            f.selected = [{'id': owner}]; f.task['job_id'] = owner; f.result = {'owner': owner}
            current_port = Mock(side_effect=current); physical = Mock(return_value=f.physical)
            submission = TrainingLaunchSubmission(current_port,
                LaunchConfiguration(f.load, f.scope, (lambda fixture=f: fixture.ensure), f.set_state, f.merge, f.save),
                LaunchInputs((lambda fixture=f: fixture.select), (lambda fixture=f: fixture.find_dataset), f.approve), f.enqueue, f.clock, physical)
            query = TrainingStatusQuery(current_port, f.admin, f.load, (lambda fixture=f: fixture.scope), f.filtered)
            app = FastAPI()
            @app.middleware('http')
            async def account_context(request, call_next):
                token = identity.set({'id': request.headers['x-fixture-owner'], 'role': 'member'})
                try: return await call_next(request)
                finally: identity.reset(token)
            endpoints = [register_start(app, submission), register_generate(app, submission), register_status(app, query)]
            for endpoint in endpoints:
                self.assertEqual([route.endpoint for route in app.routes if route.name == endpoint.__name__], [endpoint])
            self.assertEqual(app.router.on_startup, []); self.assertEqual(f.events, [])
            current_port.assert_not_called(); physical.assert_not_called()
            instances.append((app, f, current_port, physical, submission))
        root_names = ['current_auth_user', 'load_config', 'scope_config_for_user', 'selected_accessories', 'dataset_for_training',
                      'validate_approved_preview', 'ensure_training_assets_for_request', 'enqueue_training_task',
                      'set_training_state_for_user', 'merge_scoped_accessory_updates', 'save_config', 'user_is_admin', 'filtered_training_state']
        for name in root_names: self.stack.enter_context(patch.object(self.api, name, side_effect=AssertionError('unexpected root dependency')))
        async def request(instance):
            app, f, _, physical, _ = instance; owner = f.user['id']
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://fixture.invalid') as client:
                headers = {'x-fixture-owner': owner}
                response = await client.post('/api/training/start', headers=headers, json={'selected_accessory_ids': [owner]})
                self.assertEqual(response.status_code, 200); self.assertEqual(response.json()['job_id'], owner); physical.assert_not_called()
                response = await client.post('/api/training/generate', headers=headers, json={'selected_accessory_ids': [owner]})
                self.assertEqual(response.status_code, 200); self.assertEqual(response.json()['job_id'], owner)
                response = await client.get('/api/training/status?user_id=ignored', headers=headers)
                self.assertEqual(response.status_code, 200); self.assertEqual(response.json(), {'owner': owner})
        async def both(): await asyncio.gather(*(request(instance) for instance in instances))
        asyncio.run(both()); self.assertIsNone(identity.get(None))
        for _, f, current_port, physical, submission in instances:
            owner = f.user['id']; self.assertEqual(current_port.call_count, 3); physical.assert_called_once_with()
            self.assertEqual(len(f.saved), 2); self.assertEqual(len(f.queued), 2)
            for entry in f.scope.call_args_list:
                self.assertIs(entry.args[0], f.full); self.assertEqual(entry.args[1]['id'], owner)
            self.assertEqual(f.states[0]['selected_accessory_ids'], [owner]); self.assertEqual(f.states[1]['selected_accessory_ids'], [owner])
            self.assertIs(f.states[1]['render_policy']['background_physical_size'], f.physical)
            self.assertEqual(f.filtered.call_args.args[1]['id'], owner); self.assertIsNone(f.filtered.call_args.args[2])
            # Late provider failure happens after enqueue and before any further state persistence.
            submission.current = lambda: f.user
            error = RuntimeError('physical provider'); physical.side_effect = [error, f.physical]
            with self.assertRaises(RuntimeError) as caught: submission.request_sample_generation(self.request())
            self.assertIs(caught.exception, error); self.assertEqual(physical.call_count, 2)
            self.assertEqual(len(f.queued), 3); self.assertEqual(len(f.saved), 2); self.assertEqual(len(f.states), 2)


if __name__ == '__main__': unittest.main()
