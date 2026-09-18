"""Offline training resource catalog, projection, identity and route contracts."""
from contextlib import ExitStack
from contextvars import ContextVar
import asyncio
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, call, patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.concurrency import run_in_threadpool
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class ResourceCatalogContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ); cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='training-catalog-root-')
        root = Path(cls.runtime.name)
        (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.runtime.cleanup(); cls.environment.stop()

    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='training-catalog-'))).resolve()
        self.events = []
        self.user = {'id': 'alice'}
        self.tasks = []
        self.specs = []
        self.ai = []
        self.config = {'accessories': [], 'raw': True}
        self.scoped = {'accessories': [], 'scoped': True}
        self.audit = Mock(side_effect=lambda data, path: {'created_at': 11, 'updated_at': 22,
                           'owner_user_id': data.get('owner_user_id', 'audit-owner'), 'owner_username': 'audit-name'})
        self.resolve = Mock(side_effect=lambda value: Path(value))
        self.created = Mock(return_value=31)
        self.updated = Mock(return_value=32)
        self.visible = Mock(side_effect=lambda item, user, target=None: item.get('owner_user_id') == user['id'])
        self.mutable = Mock(return_value=False)
        self.list_tasks = Mock(side_effect=lambda **kwargs: self.tasks)
        self.list_models = Mock(side_effect=lambda: self.specs)
        self.load = Mock(side_effect=lambda: self.config)
        self.scope = Mock(return_value=self.scoped)
        self.load_ai = Mock(side_effect=lambda: self.ai)
        self.serialize = Mock(side_effect=lambda task, config: {**task, 'source': config['scoped']})
        self.sanitize = Mock(side_effect=lambda payload: payload)
        self.owner = Mock(return_value='resolved-owner-name')
        self.read = Mock(side_effect=lambda path: json.loads(path.read_text(encoding='utf-8')))
        self.bind = {'OUTPUT_DIR': self.root, 'load_json_file_mtime_cached': self.read,
                     'record_audit_fields': self.audit, 'resolve_service_path': self.resolve,
                     'record_created_at': self.created, 'record_updated_at': self.updated,
                     'record_visible_to_user': self.visible, 'record_mutable_by_user': self.mutable,
                     'list_training_tasks': self.list_tasks, 'list_trained_model_specs': self.list_models,
                     'load_config': self.load, 'scope_config_for_user': self.scope,
                     'load_ai_detection_tasks': self.load_ai, 'serialize_ai_detection_task': self.serialize,
                     'public_path_sanitized': self.sanitize, 'record_owner_username': self.owner,
                     'LEGACY_OWNER_ID': 'legacy-owner', 'current_auth_user': lambda: self.user,
                     'user_is_admin': lambda user: user.get('role') == 'admin'}
        for name, value in self.bind.items(): self.stack.enter_context(patch.object(self.api, name, value))
        for target in ('requests.request', 'subprocess.Popen', 'os.kill'):
            self.stack.enter_context(patch(target, side_effect=AssertionError('unexpected external operation')))

    def dataset(self, name='data', parent=None, stamp=100, **values):
        path = (parent or self.root / 'training_datasets') / name
        path.mkdir(parents=True, exist_ok=True)
        payload = {'samples': [], 'owner_user_id': 'alice', **values}
        (path / 'manifest.json').write_text(json.dumps(payload), encoding='utf-8')
        os.utime(path, (stamp, stamp))
        return path

    def model(self, run='run', **values):
        return {'id': 'trained_' + run, 'run_id': run, 'task_id': run, 'variant': 'yolo',
                'path': str(self.root / 'training_runs' / run / 'weights/best.pt'),
                'label': 'Synthetic', 'owner_user_id': 'alice', **values}

    def test_resource_ids_and_late_unsorted_owner_roots(self):
        for raw, expected in [(None, ''), (0, ''), (' ..._ ', ''), (' ../A 中 /B.. ', 'A_B'), ('A.b-1', 'A.b-1')]:
            self.assertEqual(self.api.clean_training_resource_id(raw), expected)
        self.assertEqual(self.api.training_task_dataset_resource_id({'dataset_dir': ' /some/A 中/ '}), 'A')
        self.assertEqual(self.api.training_task_dataset_resource_id({}), '')
        self.assertEqual(self.api.training_dataset_roots(), [self.root / 'training_datasets'])
        owners = self.root / 'users'; owners.mkdir()
        (owners / 'z').mkdir(); (owners / 'a').mkdir(); (owners / 'file').write_text('x')
        original = Path.iterdir
        def ordered(path):
            return iter([owners / 'z', owners / 'file', owners / 'a']) if path == owners else original(path)
        with patch.object(Path, 'iterdir', ordered):
            self.assertEqual(self.api.training_dataset_roots(), [self.root / 'training_datasets', owners / 'z/training_datasets', owners / 'a/training_datasets'])
            self.assertEqual(self.api.training_run_roots(), [self.root / 'training_runs', owners / 'z/training_runs', owners / 'a/training_runs'])
        with patch.object(self.api, 'OUTPUT_DIR', self.root / 'other'):
            self.assertEqual(self.api.training_dataset_roots(), [self.root / 'other/training_datasets'])

    def test_summary_counts_without_sample_path_or_audit_hydration(self):
        path = self.dataset(samples=[{'image': 'must-not-resolve'}, None, 'bad', {}], sample_count=99, note=' note ')
        result = self.api.dataset_resource_item(path, include_samples=False)
        self.assertEqual(result, {'id': 'data', 'kind': 'dataset', 'display_name': 'data', 'note': ' note ',
            'path': str(path), 'manifest_path': str(path / 'manifest.json'), 'sample_count': 2,
            'created_at': 11, 'updated_at': 22, 'selected_accessory_ids': [], 'background_set_id': '',
            'owner_user_id': 'alice', 'owner_username': 'audit-name', 'samples_loaded': False})
        self.resolve.assert_not_called(); self.created.assert_not_called(); self.updated.assert_not_called()
        self.audit.assert_called_once(); self.read.assert_called_once_with(path / 'manifest.json')
        for samples in [[], ['bad'], {'image': 'bad'}, None]:
            self.dataset(samples=samples, sample_count='7')
            self.assertEqual(self.api.dataset_resource_item(path, include_samples=False)['sample_count'], '7')

    def test_detail_copies_samples_with_two_existence_checks_and_owner_fallback(self):
        present = self.root / 'present'; present.write_bytes(b'image')
        absent = self.root / 'absent'
        source = {'samples': [{'image': str(present), 'owner_user_id': 'bob', 'nested': ['shared']},
                              {'image': str(absent), 'owner_username': 'custom'}, {}, 0]}
        before = copy.deepcopy(source)
        path = self.dataset(); self.read.side_effect = None; self.read.return_value = source
        result = self.api.dataset_resource_item(path)
        self.assertEqual(source, before)
        self.assertEqual(result['sample_count'], 3)
        self.assertEqual(self.resolve.call_args_list, [call(str(present)), call(str(absent))])
        self.assertEqual([item.args[1] for item in self.created.call_args_list], [present, path, path])
        self.assertEqual([item.args[1] for item in self.updated.call_args_list], [present, path, path])
        self.assertEqual([s['owner_user_id'] for s in result['samples']], ['bob', 'audit-owner', 'audit-owner'])
        self.assertEqual([s['owner_username'] for s in result['samples']], ['audit-name', 'custom', 'audit-name'])
        self.assertIsNot(result['samples'][0], source['samples'][0])
        self.assertIs(result['samples'][0]['nested'], source['samples'][0]['nested'])
        # A disappearing source must be re-checked separately for created and updated timestamps.
        self.created.reset_mock(); self.updated.reset_mock()
        original_exists = Path.exists; choices = iter([True, False])
        with patch.object(Path, 'exists', lambda p: next(choices) if p == present else original_exists(p)):
            self.api.dataset_resource_item(path)
        self.assertEqual(self.created.call_args_list[0].args[1], present)
        self.assertEqual(self.updated.call_args_list[0].args[1], path)

    def test_missing_nonmapping_and_read_failure_order(self):
        self.assertIsNone(self.api.dataset_resource_item(self.root / 'absent'))
        self.read.assert_not_called(); self.audit.assert_not_called()
        path = self.dataset(); self.read.side_effect = None
        for value in [[], None, False, 5]:
            self.read.return_value = value
            self.assertIsNone(self.api.dataset_resource_item(path))
        self.audit.assert_not_called()
        self.read.reset_mock(); self.read.side_effect = OSError('fixture')
        with self.assertRaisesRegex(OSError, 'fixture'): self.api.dataset_resource_item(path)
        self.read.assert_called_once(); self.audit.assert_not_called()

    def test_find_sanitization_root_order_and_read_write_permissions(self):
        a = self.dataset(parent=self.root / 'one')
        b = self.dataset(parent=self.root / 'two', owner_user_id='bob')
        roots = Mock(return_value=[self.root / 'missing', a.parent, b.parent])
        with patch.object(self.api, 'training_dataset_roots', roots):
            self.assertEqual(self.api.find_dataset_resource('...___', self.user), (None, None)); roots.assert_not_called()
            self.visible.side_effect = lambda item, user: item['owner_user_id'] == 'bob'
            found, item = self.api.find_dataset_resource('../data..', self.user)
            self.assertEqual(found, b); self.assertFalse(item['samples_loaded']); self.mutable.assert_not_called()
            self.assertEqual(len(self.visible.call_args_list), 2)
            self.mutable.return_value = True; self.visible.reset_mock()
            found, item = self.api.find_dataset_resource('data', self.user, include_samples=True, write=True)
            self.assertEqual(found, a); self.assertTrue(item['samples_loaded'])
            self.visible.assert_not_called(); self.mutable.assert_called_once()
            self.mutable.reset_mock()
            self.assertEqual(self.api.find_dataset_resource('data', {}, write=True)[0], a)
            self.mutable.assert_not_called()

    def test_root_local_sort_real_duplicates_and_historical_fallback_linking(self):
        one = self.root / 'one'; two = self.root / 'two'
        self.dataset('old', parent=one, stamp=1); self.dataset('same', parent=one, stamp=3)
        self.dataset('same', parent=two, stamp=100); self.dataset('new', parent=two, stamp=200)
        self.tasks[:] = [
            {'job_id': 'different-job', 'action': 'train_model', 'dataset_dir': '/missing/history', 'completed_samples': '4', 'sample_count': 90, 'created_at': '8', 'label': 'old label'},
            {'job_id': 'history', 'action': 'generate_samples', 'dataset_dir': '/another/history', 'label': 'duplicate'},
            {'job_id': 'same', 'action': 'train_model', 'dataset_dir': '/missing/same'},
            {'job_id': 'deleted', 'action': 'train_model', 'dataset_dir': '/missing/deleted', 'dataset_status': 'deleted'},
            {'job_id': 'bad-action', 'action': 'other', 'dataset_dir': '/missing/bad'},
            {'job_id': 'no-dir', 'action': 'train_model'},
            {'job_id': 'blank', 'action': 'train_model', 'dataset_dir': '...'},
        ]
        with patch.object(self.api, 'training_dataset_roots', return_value=[one, two]):
            result = self.api.training_resources_payload(user=self.user, target_user_id='target')
        datasets = result['datasets']
        self.assertEqual([d['id'] for d in datasets], ['same', 'old', 'new', 'same', 'history'])
        historical = datasets[-1]
        self.assertEqual(historical['sample_count'], 4); self.assertEqual(historical['created_at'], 8)
        self.assertEqual(historical['display_name'], 'old label'); self.assertTrue(historical['missing_files'])
        self.assertIsNone(historical['samples']); self.assertFalse(historical['samples_loaded'])
        self.assertNotIn('updated_at', historical)
        self.assertIs(result['tasks'], self.tasks)
        completed = result['training_tasks']
        self.assertEqual([t['job_id'] for t in completed], ['different-job', 'history', 'same', 'deleted', 'no-dir', 'blank'])
        self.assertIsNone(completed[0]['dataset']); self.assertIs(completed[1]['dataset'], historical)
        self.assertIs(completed[2]['dataset'], datasets[0])
        self.list_tasks.assert_called_once_with(user=self.user, target_user_id='target')
        self.sanitize.assert_called_once_with(result)

    def test_models_timestamps_flags_owner_and_task_projection(self):
        run = self.root / 'training_runs/run'; run.mkdir(parents=True); os.utime(run, (123, 123))
        model_file = self.root / 'model.pt'; model_file.write_bytes(b'not-a-model'); os.utime(model_file, (456, 456))
        self.specs[:] = [self.model(owner_user_id='', created_at=0, updated_at=0, owner_username=''),
                        self.model('existing', path=str(model_file), created_at=7, updated_at=0, uses_ocr='false', owner_username='named'),
                        self.model('hidden', owner_user_id='bob')]
        self.tasks[:] = [{'job_id': 'run', 'action': 'train_model'}]
        self.visible.side_effect = lambda item, user, target=None: item.get('owner_user_id') != 'bob'
        result = self.api.training_resources_payload(user=self.user)
        missing, existing = result['models']
        self.assertEqual(missing, {'id': 'trained_run', 'run_id': 'run', 'task_id': 'run', 'pipeline_task_id': '',
            'pipeline_task_name': '', 'variant': 'yolo', 'kind': 'model', 'label': 'Synthetic', 'note': '',
            'path': str(run / 'weights/best.pt'), 'exists': False, 'uses_ocr': False, 'created_at': 123,
            'updated_at': 123, 'accessory_names': [], 'selected_accessory_ids': [], 'owner_user_id': 'legacy-owner', 'owner_username': 'resolved-owner-name'})
        self.assertEqual((existing['created_at'], existing['updated_at'], existing['uses_ocr'], existing['exists']), (7, 7, True, True))
        self.owner.assert_called_once_with(self.specs[0])
        self.assertIs(result['training_tasks'][0]['models'][0], missing)
        self.assertEqual(len(self.resolve.call_args_list), 2)

    def test_configuration_scope_ai_visibility_and_final_sanitizer_order(self):
        self.ai[:] = [{'id': 'yes', 'owner_user_id': 'alice'}, {'id': 'no', 'owner_user_id': 'bob'}]
        expected = {'redacted': True}
        self.sanitize.side_effect = lambda value: expected
        self.assertIs(self.api.training_resources_payload(user=self.user, target_user_id='target'), expected)
        self.load.assert_called_once_with(); self.scope.assert_called_once_with(self.config, self.user, 'target')
        self.serialize.assert_called_once_with(self.ai[0], self.scoped)
        self.assertEqual(self.sanitize.call_args.args[0]['ai_detection_tasks'], [{'id': 'yes', 'owner_user_id': 'alice', 'source': True, 'kind': 'ai_detection_task', 'task_type': 'ai_detection'}])
        self.load.reset_mock(); self.scope.reset_mock(); self.serialize.reset_mock(); self.visible.reset_mock()
        self.serialize.side_effect = lambda task, config: dict(task)
        self.api.training_resources_payload()
        self.scope.assert_not_called(); self.visible.assert_not_called(); self.load.assert_called_once_with()
        self.assertEqual(self.serialize.call_args_list, [call(self.ai[0], self.config), call(self.ai[1], self.config)])

    def test_early_failures_never_retry_or_continue_later_sources(self):
        for stage in ['item', 'tasks', 'models', 'config', 'scope', 'ai', 'serialize', 'sanitize']:
            with self.subTest(stage=stage), ExitStack() as stack:
                self.dataset()
                names = ['dataset_resource_item', 'list_training_tasks', 'list_trained_model_specs', 'load_config', 'scope_config_for_user', 'load_ai_detection_tasks', 'serialize_ai_detection_task', 'public_path_sanitized']
                defaults = [None, [], [], {}, {}, [{'owner_user_id': 'alice'}], {}, {}]
                target = ['item', 'tasks', 'models', 'config', 'scope', 'ai', 'serialize', 'sanitize'].index(stage)
                mocks = [stack.enter_context(patch.object(self.api, name, side_effect=[OSError(stage), value] if index == target else None, return_value=value)) for index, (name, value) in enumerate(zip(names, defaults))]
                with self.assertRaisesRegex(OSError, stage): self.api.training_resources_payload(user=self.user)
                self.assertEqual(mocks[target].call_count, 1)
                for later in mocks[target+1:]: later.assert_not_called()

    def test_read_endpoints_arguments_status_and_error_shape(self):
        payload = Mock(return_value={'marker': True}); find = Mock(return_value=(None, None))
        with patch.object(self.api, 'training_resources_payload', payload), patch.object(self.api, 'find_dataset_resource', find):
            app = FastAPI(); app.get('/api/training/resources')(self.api.training_resources)
            app.get('/api/training/resources/datasets/{dataset_id}/detail')(self.api.training_dataset_detail)
            client = TestClient(app)
            response = client.get('/api/training/resources?include_samples=true&user_id=bob')
            self.assertEqual((response.status_code, response.json()), (200, {'marker': True}))
            payload.assert_called_once_with(include_samples=True, user=self.user, target_user_id=None)
            self.user['role'] = 'admin'; payload.reset_mock()
            client.get('/api/training/resources?user_id=bob')
            payload.assert_called_once_with(include_samples=False, user=self.user, target_user_id='bob')
            response = client.get('/api/training/resources/datasets/missing/detail')
            self.assertEqual((response.status_code, response.json()), (404, {'detail': 'Dataset not found'}))
            find.assert_called_once_with('missing', user=self.user, include_samples=True)
            find.return_value = (self.root, {'id': 'visible'})
            self.assertEqual(client.get('/api/training/resources/datasets/visible/detail').json(), {'status': 'ready', 'dataset': {'id': 'visible'}})
            self.sanitize.assert_called_once_with({'status': 'ready', 'dataset': {'id': 'visible'}})
            response = client.get('/api/training/resources?include_samples=nonsense')
            self.assertEqual(response.status_code, 422)
            with patch.object(self.api, 'current_auth_user', side_effect=HTTPException(401, 'Authentication required')):
                self.assertEqual(client.get('/api/training/resources').json(), {'detail': 'Authentication required'})
            with patch.object(self.api, 'current_auth_user', side_effect=HTTPException(403, 'Forbidden')):
                self.assertEqual(client.get('/api/training/resources/datasets/visible/detail').status_code, 403)

    def test_forbidden_detail_is_hydrated_before_permission_and_shared_read_is_not_write(self):
        path = self.dataset(samples=[{'image': 'bad-image'}])
        self.resolve.side_effect = OSError('sample unavailable')
        with self.assertRaisesRegex(OSError, 'sample unavailable'):
            self.api.find_dataset_resource('data', self.user, include_samples=True)
        self.visible.assert_not_called(); self.mutable.assert_not_called()
        self.visible.side_effect = None; self.visible.return_value = True
        self.assertEqual(self.api.find_dataset_resource('data', self.user)[0], path)
        self.assertEqual(self.api.find_dataset_resource('data', self.user, write=True), (None, None))

    def test_real_task_views_refresh_only_visible_tasks_and_stop_on_save_failure(self):
        from local_inspection_service.training.task_views import TrainingTaskViews, TrainingViewAccess
        from local_inspection_service.training.task_lifecycle import TrainingTaskLifecycle, TrainingTaskRecords, TrainingTaskWrites
        from local_inspection_service.runtime.training_tasks import TrainingTaskState
        visible = {'job_id': 'visible', 'status': 'running', 'action': 'train_model', 'owner_user_id': 'alice'}
        hidden = {'job_id': 'hidden', 'status': 'running', 'action': 'train_model', 'owner_user_id': 'bob'}
        records = {task['job_id']: task for task in [hidden, visible]}
        save = Mock()
        state = TrainingTaskState(lambda: threading.RLock(), lambda: {}, lambda: {})
        lifecycle = TrainingTaskLifecycle(state, TrainingTaskRecords(lambda job: self.root / job,
            lambda path: records[path.name], save, lambda job: records[job]),
            TrainingTaskWrites(Mock(), Mock(), Mock()), Mock())
        refresh = Mock(wraps=lifecycle.refresh_interrupted_local_training_task)
        views = TrainingTaskViews(lambda: list(records.values()), refresh,
            TrainingViewAccess(dict, lambda: (lambda task: task), self.visible))
        with patch.object(self.api, 'list_training_tasks', views.list_training_tasks):
            result = self.api.training_resources_payload(user=self.user)
            self.assertEqual(result['tasks'][0]['status'], 'stopped')
            self.assertEqual(hidden['status'], 'running')
            refresh.assert_called_once_with(visible); save.assert_called_once_with(visible)
            visible['status'] = 'running'; save.reset_mock(); refresh.reset_mock()
            save.side_effect = OSError('save failed')
            for mock in [self.list_models, self.load, self.scope, self.load_ai, self.serialize, self.sanitize]: mock.reset_mock()
            with self.assertRaisesRegex(OSError, 'save failed'): self.api.training_resources_payload(user=self.user)
            refresh.assert_called_once_with(visible); save.assert_called_once()
            for mock in [self.list_models, self.load, self.scope, self.load_ai, self.serialize, self.sanitize]: mock.assert_not_called()

    def test_ambient_model_identity_no_argument_and_hidden_malformed_spec(self):
        identity = ContextVar('catalog-model-owner')
        spec = self.model(owner_user_id='bob')
        seen = []
        def models(*args, **kwargs):
            seen.append((identity.get(), args, kwargs))
            return [{'owner_user_id': 'hidden'}, spec]
        token = identity.set({'id': 'alice'})
        try:
            with patch.object(self.api, 'list_trained_model_specs', models):
                result = self.api.training_resources_payload(user={'id': 'bob'})
        finally: identity.reset(token)
        self.assertEqual(seen, [({'id': 'alice'}, (), {})])
        self.assertEqual([m['owner_user_id'] for m in result['models']], ['bob'])
        self.resolve.assert_called_once()

    def test_independent_services_construct_without_reads_and_two_apps_keep_request_identity(self):
        import httpx
        from local_inspection_service.training.dataset_catalog import DatasetCatalog, DatasetPaths, DatasetAudit, DatasetAccess, clean_training_resource_id
        from local_inspection_service.training.resource_queries import TrainingResources, ResourceDatasets, ResourceRecords, ResourceConfiguration, ResourceAccess
        from local_inspection_service.training.resource_api import register, ResourceReadAccess
        identity = ContextVar('independent-resource-identity')
        barrier = threading.Barrier(2)
        instances = []
        for index, owner in enumerate(['alice', 'bob']):
            directory = self.root / str(index)
            output = Mock(return_value=directory)
            roots = Mock(return_value=[directory / 'training_datasets'])
            catalog = DatasetCatalog(DatasetPaths(output, lambda: self.resolve, roots, clean_training_resource_id),
                                     self.read, DatasetAudit(self.audit, lambda: self.created, lambda: self.updated),
                                     DatasetAccess(self.visible, self.mutable), Mock())
            catalog.item.side_effect = catalog.dataset_resource_item
            tasks = Mock(return_value=[])
            sanitize = Mock(side_effect=lambda value, marker=index: {**value, 'app_marker': marker})
            queries = TrainingResources(ResourceDatasets(roots, catalog.dataset_resource_item, catalog.training_task_dataset_resource_id),
                                        ResourceRecords(tasks, self.list_models, self.load_ai),
                                        ResourceConfiguration(self.load, lambda: self.scope, self.serialize),
                                        ResourceAccess(self.visible, self.owner, lambda: 'legacy', sanitize),
                                        lambda: self.resolve, output)
            def current():
                barrier.wait(timeout=5)
                return identity.get()
            current_port = Mock(side_effect=current)
            admin_port = Mock(side_effect=lambda user: user.get('role') == 'admin')
            app = FastAPI()
            @app.middleware('http')
            async def account_context(request, call_next):
                token = identity.set({'id': request.headers['x-fixture-owner']})
                try: return await call_next(request)
                finally: identity.reset(token)
            routes = register(app, ResourceReadAccess(current_port, admin_port, sanitize),
                              lambda queries=queries: queries.training_resources_payload, catalog.find_dataset_resource)
            for name in routes.__dataclass_fields__:
                self.assertEqual([route.endpoint for route in app.routes if route.name == name], [getattr(routes, name)])
            self.assertEqual(app.router.on_startup, [])
            instances.append((app, owner, directory, tasks, sanitize, current_port, admin_port, output, roots, catalog))
        for instance in instances:
            for callback in instance[3:9]: callback.assert_not_called()
            instance[9].item.assert_not_called()
        for callback in [self.resolve, self.read, self.audit, self.created, self.updated, self.visible,
                         self.mutable, self.list_models, self.load_ai, self.load, self.scope, self.serialize, self.owner]:
            callback.assert_not_called()
        for index, (_, owner, directory, *_) in enumerate(instances):
            self.dataset('data-' + str(index), parent=directory / 'training_datasets', owner_user_id=owner)
        async def request(index, instance):
            app, owner = instance[:2]
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://fixture.invalid') as client:
                response = await client.get('/api/training/resources?user_id=ignored', headers={'x-fixture-owner': owner})
                self.assertEqual(response.status_code, 200)
                result = response.json()
                detail = await client.get('/api/training/resources/datasets/data-' + str(index) + '/detail', headers={'x-fixture-owner': owner})
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(detail.json()['app_marker'], index)
                self.assertEqual(detail.json()['dataset']['id'], 'data-' + str(index))
                return result
        async def both():
            return await asyncio.gather(*(request(index, instance) for index, instance in enumerate(instances)))
        with ExitStack() as stack:
            for name in ['current_auth_user', 'training_resources_payload', 'find_dataset_resource', 'dataset_resource_item', 'load_config']:
                stack.enter_context(patch.object(self.api, name, side_effect=AssertionError('entry point dependency')))
            results = asyncio.run(both())
        self.assertEqual([[d['id'] for d in result['datasets']] for result in results], [['data-0'], ['data-1']])
        self.assertEqual([result['app_marker'] for result in results], [0, 1])
        for index, instance in enumerate(instances):
            _, owner, _, tasks, sanitize, current_port, admin_port, output, roots, catalog = instance
            tasks.assert_called_once_with(user={'id': owner}, target_user_id=None)
            self.assertEqual(sanitize.call_count, 2); self.assertEqual(current_port.call_count, 2)
            admin_port.assert_called_once_with({'id': owner})
            catalog.item.assert_called_once()
        self.assertEqual(identity.get(None), None)

    def test_history_deleted_state_is_exact_and_samples_shape_is_preserved(self):
        self.tasks[:] = [{'job_id': name, 'action': 'train_model', 'dataset_dir': '/missing/' + name,
                         'dataset_status': status, 'sample_count': '2'}
                        for name, status in [('exact', 'deleted'), ('upper', 'DELETED'), ('spaces', ' deleted ')]]
        for include_samples in [False, True]:
            with self.subTest(include_samples=include_samples):
                result = self.api.training_resources_payload(include_samples=include_samples, user=self.user)
                self.assertEqual([item['id'] for item in result['datasets']], ['upper', 'spaces'])
                self.assertEqual([item['samples'] for item in result['datasets']], [[], []] if include_samples else [None, None])
                self.assertEqual([item['samples_loaded'] for item in result['datasets']], [include_samples] * 2)
                self.assertEqual([item['sample_count'] for item in result['datasets']], [2, 2])
                self.assertIsNone(result['training_tasks'][0]['dataset'])
                for task, dataset in zip(result['training_tasks'][1:], result['datasets']):
                    self.assertIs(task['dataset'], dataset)

    def test_two_request_identities_survive_async_threadpool_entry(self):
        identity = ContextVar('resource-test-user'); barrier = threading.Barrier(2)
        def current():
            barrier.wait(timeout=5)
            return identity.get()
        def payload(**kwargs): return kwargs
        async def account(name):
            token = identity.set({'id': name})
            try: return await run_in_threadpool(self.api.training_resources, user_id='ignored')
            finally: identity.reset(token)
        async def run(): return await asyncio.gather(account('alice'), account('bob'))
        with patch.object(self.api, 'current_auth_user', current), patch.object(self.api, 'training_resources_payload', payload):
            results = asyncio.run(run())
        self.assertEqual([item['user']['id'] for item in results], ['alice', 'bob'])
        self.assertEqual([item['target_user_id'] for item in results], [None, None])


    def test_callbacks_capture_before_resource_arguments(self):
        api=self.api
        for site in ('sample-resolve','created','updated','model-resolve','scope','payload'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(site=site,mode=mode),ExitStack() as stack:
                    value=self.root/'present';value.write_bytes(b'fixture')
                    target={'sample-resolve':'resolve_service_path','created':'record_created_at','updated':'record_updated_at','model-resolve':'resolve_service_path','scope':'scope_config_for_user','payload':'training_resources_payload'}[site]
                    result=value if 'resolve' in site else 42 if site in ('created','updated') else self.scoped if site=='scope' else {'marker':'captured'}
                    a=Mock(return_value=result);b=Mock(return_value=result);c=Mock(return_value=result);events=[]
                    stack.enter_context(patch.object(api,target,a))
                    def prior():
                        if mode=='prior':setattr(api,target,b)
                        elif mode=='missing':setattr(api,target,None)
                    def argument():events.append('argument');setattr(api,target,c)
                    if site in ('sample-resolve','created','updated'):
                        path=self.dataset();sample={'image':str(value)}
                        if site=='sample-resolve':
                            class Sample(dict):
                                count=0
                                def get(inner,key,*args):
                                    if key=='image':
                                        inner.count+=1
                                        if inner.count==2:argument()
                                    return super().get(key,*args)
                            sample=Sample(sample)
                        manifest={'samples':[sample]}
                        def read(_):prior();return manifest
                        stack.enter_context(patch.object(api,'load_json_file_mtime_cached',read))
                        if site in ('created','updated'):
                            original=Path.exists;counts=[]
                            def exists(p):
                                if p==value:
                                    counts.append(True)
                                    if len(counts)==(1 if site=='created' else 2):argument()
                                return original(p)
                            stack.enter_context(patch.object(Path,'exists',exists))
                        action=lambda:api.dataset_resource_item(path)
                    elif site=='model-resolve':
                        class Spec(dict):
                            def get(inner,key,*args):
                                if key=='run_dir':argument()
                                return super().get(key,*args)
                        spec=Spec(self.model(run_dir=str(value),created_at=1,updated_at=2))
                        def models():prior();return [spec]
                        stack.enter_context(patch.object(api,'list_trained_model_specs',models))
                        stack.enter_context(patch.object(api,'training_dataset_roots',lambda:[]))
                        action=lambda:api.training_resources_payload(user=self.user)
                    elif site=='scope':
                        def models():prior();return []
                        def load():argument();return self.config
                        stack.enter_context(patch.object(api,'list_trained_model_specs',models));stack.enter_context(patch.object(api,'load_config',load));stack.enter_context(patch.object(api,'training_dataset_roots',lambda:[]))
                        action=lambda:api.training_resources_payload(user=self.user)
                    else:
                        def current():prior();return self.user
                        def admin(user):argument();return False
                        stack.enter_context(patch.object(api,'current_auth_user',current));stack.enter_context(patch.object(api,'user_is_admin',admin))
                        action=lambda:api.training_resources()
                    if mode=='missing':
                        with self.assertRaises(TypeError):action()
                        a.assert_not_called();b.assert_not_called()
                    else:
                        action();(a if mode=='ordinary' else b).assert_called_once();(b if mode=='ordinary' else a).assert_not_called()
                    self.assertEqual(events,['argument']);c.assert_not_called()


    def test_new_callback_getter_failures_precede_argument_effects(self):
        from dataclasses import replace
        from local_inspection_service.training.resource_api import register,ResourceReadAccess
        api=self.api
        for site in ('sample-resolve','created','updated','model-resolve','scope','payload'):
            with self.subTest(site=site),ExitStack() as stack:
                failure=OSError(site);calls=[];effects=[]
                if site in ('sample-resolve','created','updated'):
                    service=api._dataset_catalog;container='paths' if site=='sample-resolve' else 'audit';field='resolve' if site=='sample-resolve' else site
                    path=self.dataset();media=self.root/'media';media.write_bytes(b'fixture')
                    self.read.return_value={'samples':[{'image':str(media)}]};self.read.side_effect=None
                    original_exists=Path.exists
                    def exists(p):
                        if p==media:effects.append('exists')
                        return original_exists(p)
                    stack.enter_context(patch.object(Path,'exists',exists))
                    action=lambda:api.dataset_resource_item(path)
                elif site in ('model-resolve','scope'):
                    service=api._training_resources;container='config' if site=='scope' else None;field='scope' if site=='scope' else 'resolve'
                    stack.enter_context(patch.object(api,'training_dataset_roots',lambda:[]))
                    if site=='model-resolve':
                        class Spec(dict):
                            def get(inner,key,*args):
                                if key=='run_dir':effects.append('run_dir')
                                return super().get(key,*args)
                        self.specs[:]=[Spec(self.model(created_at=1,updated_at=2))]
                    else:
                        self.specs[:]=[]
                        stack.enter_context(patch.object(api,'load_config',lambda: effects.append('load') or self.config))
                    action=lambda:api.training_resources_payload(user=self.user)
                if site!='payload':
                    owner=getattr(service,container) if container else service;original=getattr(owner,field)
                    def getter():
                        calls.append(True)
                        if len(calls)==1:raise failure
                        return original()
                    if container:stack.enter_context(patch.object(service,container,replace(owner,**{field:getter})))
                    else:stack.enter_context(patch.object(service,field,getter))
                else:
                    payload=Mock(return_value={})
                    def getter():
                        calls.append(True)
                        if len(calls)==1:raise failure
                        return payload
                    routes=register(FastAPI(),ResourceReadAccess(lambda:self.user,lambda user:effects.append('admin') or False,lambda x:x),getter,Mock())
                    action=routes.training_resources
                with self.assertRaises(OSError) as caught:action()
                self.assertIs(caught.exception,failure);self.assertEqual(calls,[True]);self.assertEqual(effects,['exists'] if site=='updated' else [])


    def test_catalog_and_resource_first_errors_do_not_retry(self):
        api=self.api
        stages=('item-exists','item-read','item-audit','item-resolve','item-created','item-updated','find-clean','find-roots','find-exists','find-is_dir','find-item','find-visible','find-mutable','roots-exists','roots-iterdir','roots-is_dir','query-roots','query-exists','query-iterdir','query-is_dir','query-stat','query-visible','query-task-id','query-resolve','query-owner','query-ai-visible','route-current','route-admin','route-find','route-sanitize')
        for stage in stages:
            with self.subTest(stage=stage),ExitStack() as stack:
                path=self.dataset();media=self.root/'media';media.write_bytes(b'fixture')
                self.dataset(samples=[{'image':str(media)}]);self.tasks[:]=[];self.specs[:]=[];self.ai[:]=[]
                users=self.root/'users';users.mkdir(exist_ok=True);(users/'alice').mkdir(exist_ok=True)
                failure=OSError(stage);calls=[]
                def first(fn,*args,**kwargs):
                    calls.append(True)
                    if len(calls)==1:raise failure
                    return fn(*args,**kwargs)
                kind,part=stage.split('-',1)
                if kind=='item':
                    action=lambda:api.dataset_resource_item(path)
                    field={'read':'load_json_file_mtime_cached','audit':'record_audit_fields','resolve':'resolve_service_path','created':'record_created_at','updated':'record_updated_at'}.get(part)
                    target_path=path/'manifest.json'
                elif kind=='find':
                    action=lambda:api.find_dataset_resource('data',self.user,write=part=='mutable')
                    field={'clean':'clean_training_resource_id','roots':'training_dataset_roots','item':'dataset_resource_item','visible':'record_visible_to_user','mutable':'record_mutable_by_user'}.get(part)
                    target_path=path
                elif kind=='roots':
                    action=api.training_dataset_roots;field=None;target_path=users/'alice' if part=='is_dir' else users
                elif kind=='query':
                    action=lambda:api.training_resources_payload(user=self.user)
                    field={'roots':'training_dataset_roots','visible':'record_visible_to_user','task-id':'training_task_dataset_resource_id','resolve':'resolve_service_path','owner':'record_owner_username','ai-visible':'record_visible_to_user'}.get(part)
                    target_path=path if part in ('stat','is_dir') else path.parent
                    if part in ('task-id','resolve','owner','ai-visible'):
                        stack.enter_context(patch.object(api,'training_dataset_roots',lambda:[]))
                    if part=='task-id':self.tasks[:]=[{'job_id':'job','action':'train_model','dataset_dir':'missing'}]
                    elif part in ('resolve','owner'):self.specs[:]=[self.model(created_at=1,updated_at=2)]
                    elif part=='ai-visible':self.ai[:]=[{'owner_user_id':'alice'}]
                else:
                    field={'current':'current_auth_user','admin':'user_is_admin','find':'find_dataset_resource','sanitize':'public_path_sanitized'}[part]
                    action=api.training_resources if part in ('current','admin') else lambda:api.training_dataset_detail('data')
                if field:
                    original=getattr(api,field)
                    def method(*args,**kwargs):return first(original,*args,**kwargs)
                    stack.enter_context(patch.object(api,field,method))
                else:
                    original=getattr(Path,part)
                    def method(p,*args,**kwargs):return first(original,p,*args,**kwargs) if p==target_path else original(p,*args,**kwargs)
                    stack.enter_context(patch.object(Path,part,method))
                with self.assertRaises(OSError) as caught:action()
                self.assertIs(caught.exception,failure);self.assertEqual(calls,[True])


    def test_callbacks_capture_at_last_preceding_boundary(self):
        api=self.api
        for site in ('sample-resolve','created','model-resolve','scope'):
            for mode in ('prior','missing'):
                with self.subTest(site=site,mode=mode),ExitStack() as stack:
                    value=self.root/'present';value.write_bytes(b'fixture')
                    target={'sample-resolve':'resolve_service_path','created':'record_created_at','updated':'record_updated_at','model-resolve':'resolve_service_path','scope':'scope_config_for_user','payload':'training_resources_payload'}[site]
                    result=value if 'resolve' in site else 42 if site in ('created','updated') else self.scoped if site=='scope' else {'marker':'captured'}
                    a=Mock(return_value=result);b=Mock(return_value=result);c=Mock(return_value=result);events=[]
                    stack.enter_context(patch.object(api,target,a))
                    def prior():
                        if mode=='prior':setattr(api,target,b)
                        elif mode=='missing':setattr(api,target,None)
                    def argument():events.append('argument');setattr(api,target,c)
                    if site in ('sample-resolve','created','updated'):
                        path=self.dataset();sample={'image':str(value)}
                        if site=='sample-resolve':
                            class Sample(dict):
                                count=0
                                def get(inner,key,*args):
                                    if key=='image':
                                        inner.count+=1
                                        if inner.count==1:prior()
                                        if inner.count==2:argument()
                                    return super().get(key,*args)
                            sample=Sample(sample)
                        manifest={'samples':[sample]}
                        def read(_):return manifest
                        stack.enter_context(patch.object(api,'load_json_file_mtime_cached',read))
                        if site=='created':
                            def resolve(value):prior();return self.resolve(value)
                            stack.enter_context(patch.object(api,'resolve_service_path',resolve))
                        if site in ('created','updated'):
                            original=Path.exists;counts=[]
                            def exists(p):
                                if p==value:
                                    counts.append(True)
                                    if len(counts)==(1 if site=='created' else 2):argument()
                                return original(p)
                            stack.enter_context(patch.object(Path,'exists',exists))
                        action=lambda:api.dataset_resource_item(path)
                    elif site=='model-resolve':
                        class Spec(dict):
                            def get(inner,key,*args):
                                if key=='run_dir':argument()
                                return super().get(key,*args)
                        class RunId:
                            def __str__(inner):prior();return 'run'
                        spec=Spec(self.model(run_id=RunId(),run_dir=str(value),created_at=1,updated_at=2))
                        def models():return [spec]
                        stack.enter_context(patch.object(api,'list_trained_model_specs',models))
                        stack.enter_context(patch.object(api,'training_dataset_roots',lambda:[]))
                        action=lambda:api.training_resources_payload(user=self.user)
                    elif site=='scope':
                        class Task(dict):
                            def get(inner,key,*args):
                                if key=='job_id':prior()
                                return super().get(key,*args)
                        stack.enter_context(patch.object(api,'list_training_tasks',lambda **options:[Task(action='train_model',job_id='task')]))
                        def models():return []
                        def load():argument();return self.config
                        stack.enter_context(patch.object(api,'list_trained_model_specs',models));stack.enter_context(patch.object(api,'load_config',load));stack.enter_context(patch.object(api,'training_dataset_roots',lambda:[]))
                        action=lambda:api.training_resources_payload(user=self.user)
                    else:
                        def current():prior();return self.user
                        def admin(user):argument();return False
                        stack.enter_context(patch.object(api,'current_auth_user',current));stack.enter_context(patch.object(api,'user_is_admin',admin))
                        action=lambda:api.training_resources()
                    if mode=='missing':
                        with self.assertRaises(TypeError):action()
                        a.assert_not_called();b.assert_not_called()
                    else:
                        action();(a if mode=='ordinary' else b).assert_called_once();(b if mode=='ordinary' else a).assert_not_called()
                    self.assertEqual(events,['argument']);c.assert_not_called()


    def test_remaining_read_first_errors_keep_exact_call_positions(self):
        api=self.api
        stages=('sample-exists-1','sample-exists-2','task-clean','run-exists','run-iterdir','run-is_dir','config-anonymous','model-visible','model-exists-1','model-exists-2','timestamp-exists-1','timestamp-exists-2','timestamp-stat-1','timestamp-stat-2','sort-stat','detail-current')
        for stage in stages:
            with self.subTest(stage=stage),ExitStack() as stack:
                path=self.dataset();media=self.root/'sample';media.write_bytes(b'fixture');self.dataset(samples=[{'image':str(media)}]);self.tasks[:]=[];self.specs[:]=[];self.ai[:]=[]
                users=self.root/'users';users.mkdir(exist_ok=True);(users/'alice').mkdir(exist_ok=True)
                run=self.root/'training_runs/run';run.mkdir(parents=True,exist_ok=True);model=run/'weights/best.pt'
                calls=[];failure=OSError(stage);fail_at=int(stage[-1]) if stage[-1] in '12' else 1
                def first(fn,*args,**kwargs):
                    calls.append(True)
                    if len(calls)==fail_at:raise failure
                    return fn(*args,**kwargs)
                if stage.startswith('sample-'):
                    target,field=Path,'exists';wanted=media;action=lambda:api.dataset_resource_item(path)
                elif stage.startswith('run-'):
                    target,field=Path,stage[4:];wanted=users/'alice' if field=='is_dir' else users;action=api.training_run_roots
                elif stage=='task-clean':
                    target,field=api,'clean_training_resource_id';action=lambda:api.training_task_dataset_resource_id({'dataset_dir':'/data'})
                elif stage=='detail-current':
                    target,field=api,'current_auth_user';action=lambda:api.training_dataset_detail('data')
                elif stage=='sort-stat':
                    target,field,wanted=Path,'stat',path;original_is_dir=Path.is_dir
                    stack.enter_context(patch.object(Path,'is_dir',lambda p:True if p==path else original_is_dir(p)))
                    action=lambda:api.training_resources_payload(user=self.user)
                else:
                    stack.enter_context(patch.object(api,'training_dataset_roots',lambda:[]))
                    if stage!='config-anonymous':self.specs[:]=[self.model(run_dir=str(run))]
                    if stage=='config-anonymous':target,field=api,'load_config';action=api.training_resources_payload
                    elif stage=='model-visible':target,field=api,'record_visible_to_user';action=lambda:api.training_resources_payload(user=self.user)
                    else:
                        target,field=Path,'stat' if '-stat-' in stage else 'exists';wanted=model if stage.startswith('model-') else run
                        if field=='stat':
                            original_exists=Path.exists
                            stack.enter_context(patch.object(Path,'exists',lambda p:True if p==run else original_exists(p)))
                        action=lambda:api.training_resources_payload(user=self.user)
                original=getattr(target,field)
                if target is Path:
                    def method(p,*args,**kwargs):return first(original,p,*args,**kwargs) if p==wanted else original(p,*args,**kwargs)
                else:
                    def method(*args,**kwargs):return first(original,*args,**kwargs)
                stack.enter_context(patch.object(target,field,method))
                with self.assertRaises(OSError) as caught:action()
                self.assertIs(caught.exception,failure);self.assertEqual(len(calls),fail_at)

    def test_new_output_and_legacy_provider_failures_do_not_retry(self):
        from dataclasses import replace
        api=self.api
        for stage in ('dataset-output-1','dataset-output-2','run-output-1','run-output-2','query-output','query-legacy'):
            with self.subTest(stage=stage),ExitStack() as stack:
                failure=OSError(stage);calls=[];fail_at=2 if stage.endswith('-2') else 1
                if stage.startswith(('dataset-','run-')):
                    service=api._dataset_catalog;owner=service.paths;field='output';original=owner.output
                    action=api.training_dataset_roots if stage.startswith('dataset-') else api.training_run_roots
                    container='paths'
                else:
                    service=api._training_resources;container='access' if stage=='query-legacy' else None;owner=service.access if container else service;field='legacy_owner' if container else 'output';original=getattr(owner,field)
                    stack.enter_context(patch.object(api,'training_dataset_roots',lambda:[]));self.specs[:]=[self.model(owner_user_id='',created_at=1,updated_at=2)]
                    action=api.training_resources_payload
                def getter():
                    calls.append(True)
                    if len(calls)==fail_at:raise failure
                    return original()
                if container:stack.enter_context(patch.object(service,container,replace(owner,**{field:getter})))
                else:stack.enter_context(patch.object(service,field,getter))
                with self.assertRaises(OSError) as caught:action()
                self.assertIs(caught.exception,failure);self.assertEqual(len(calls),fail_at)


if __name__ == '__main__':
    unittest.main()
