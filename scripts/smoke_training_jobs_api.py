"""Offline task catalog/mutation and image-control HTTP contracts."""
from contextlib import ExitStack
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class JobFixture:
    def __init__(self):
        self.events = []; self.saved = []; self.deleted = []
        self.user = {'id': 'alice', 'role': 'member'}
        self.task = {'job_id': ' raw ', 'label': 'original', 'note': 'original note'}
        self.training = [{'job_id': 'a', 'status': 'queued'}, {'job_id': 'b', 'status': 'completed'}]
        self.images = [{'job_id': 'c', 'status': 'running'}, self.training[0], {'job_id': 'd', 'status': 'Completed'},
                       {'job_id': 'e', 'status': ' completed '}, {'job_id': 'f', 'status': 'COMPLETED'}]
        self.public_result = {'public': 'task'}; self.refresh_result = {'retired': 'worker'}
        self.control_result = {'controlled': True}
        self.current = Mock(side_effect=lambda: self.event('user') or self.user)
        self.admin = Mock(side_effect=lambda user: self.event('admin') or user.get('role') == 'admin')
        self.list_training = Mock(side_effect=lambda **kwargs: self.event('training-list') or self.training)
        self.list_images = Mock(side_effect=lambda **kwargs: self.event('image-list') or self.images)
        self.find = Mock(side_effect=lambda job: self.event('find') or self.task)
        self.require = Mock(side_effect=lambda *args, **kwargs: self.event('require'))
        self.worker = Mock(side_effect=lambda task: self.event('worker') or False)
        self.public = Mock(side_effect=lambda task: self.event('public') or self.public_result)
        self.refresh = Mock(side_effect=lambda *args, **kwargs: self.event('refresh') or self.refresh_result)
        self.clock = Mock(side_effect=lambda: self.event('clock') or 321.9)
        self.save = Mock(side_effect=self.save_record); self.delete = Mock(side_effect=self.delete_record)
        self.job_action = Mock(return_value=self.control_result); self.candidate_action = Mock(return_value=self.control_result)
        self.active = {'queued', 'running'}
    def event(self, name): self.events.append(name)
    def save_record(self, task): self.event('save'); self.saved.append(copy.deepcopy(task))
    def delete_record(self, job, user): self.event('delete'); self.deleted.append((job, user))
    def bind(self, api, stack):
        values = {'current_auth_user': self.current, 'user_is_admin': self.admin, 'list_training_tasks': self.list_training,
                  'list_codex_image_jobs': self.list_images, 'find_training_task': self.find, 'require_record_access': self.require,
                  'training_task_uses_worker': self.worker, 'public_training_task': self.public,
                  'public_refreshed_training_task': self.refresh, 'save_training_task': self.save,
                  'delete_training_task_record': self.delete, 'update_codex_image_job': self.job_action,
                  'update_codex_image_candidate': self.candidate_action, 'IMAGE_JOB_ACTIVE_STATUSES': self.active}
        for name, value in values.items(): stack.enter_context(patch.object(api, name, value))
        stack.enter_context(patch('time.time', self.clock)); return values


class TrainingJobsContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ); cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='training-jobs-root-')
        root = Path(cls.runtime.name); (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.f = JobFixture(); self.f.bind(self.api, self.stack)
        for target in ['requests.request', 'subprocess.Popen', 'os.kill']:
            self.stack.enter_context(patch(target, side_effect=AssertionError('unexpected external operation')))
    def test_list_preserves_order_duplicates_identity_and_exact_statuses(self):
        f = self.f; result = self.api.image_jobs('ignored')
        self.assertEqual(f.events, ['user', 'admin', 'training-list', 'image-list'])
        self.assertEqual(result['items'], f.training + f.images)
        self.assertIs(result['items'][0], result['items'][3]); self.assertIs(result['items'][0], f.training[0])
        self.assertEqual(result['active'], [f.training[0], f.images[0], f.training[0]])
        self.assertEqual(result['completed'], [f.training[1]])
        f.list_training.assert_called_once_with(user=f.user, target_user_id=None)
        f.list_images.assert_called_once_with(user=f.user, target_user_id=None)
        f.active.clear(); f.active.add('Completed')
        self.assertEqual(self.api.image_jobs()['active'], [f.images[2]])
    def test_list_admin_target_values_and_second_list_failure_no_retry(self):
        f = self.f; f.user['role'] = 'admin'
        for target in [None, '', ' raw user ']:
            self.api.image_jobs(target)
            self.assertEqual(f.list_training.call_args, call(user=f.user, target_user_id=target))
            self.assertEqual(f.list_images.call_args, call(user=f.user, target_user_id=target))
        f.list_images.reset_mock(); error = OSError('image-list'); f.list_images.side_effect = [error, f.images]
        with self.assertRaises(OSError) as caught: self.api.image_jobs()
        self.assertIs(caught.exception, error); f.list_images.assert_called_once()
    def test_detail_training_precedence_authorize_before_retired_or_native_projection(self):
        f = self.f
        for worker in [False, True]:
            f.events.clear(); f.worker.side_effect = lambda task: f.event('worker') or worker
            result = self.api.image_job(' raw ')
            self.assertIs(result, f.refresh_result if worker else f.public_result)
            self.assertEqual(f.events, ['user', 'find', 'require', 'worker', 'refresh' if worker else 'public'])
        self.assertEqual(f.find.call_args_list, [call(' raw ')] * 2)
        self.assertEqual(f.require.call_args_list, [call(f.task, f.user)] * 2)
        f.refresh.assert_called_once_with(f.task, allow_remote_refresh=False); f.public.assert_called_once_with(f.task)
        f.list_images.assert_not_called()

    def test_list_dependency_failure_never_retries_or_calls_later_sources(self):
        stages = ['current', 'admin', 'list_training', 'list_images']
        for stage in stages:
            with self.subTest(stage=stage), ExitStack() as stack:
                f = JobFixture(); f.bind(self.api, stack); error = OSError(stage)
                successful = {'current': f.user, 'admin': False, 'list_training': f.training, 'list_images': f.images}
                getattr(f, stage).side_effect = [error, successful[stage]]
                with self.assertRaises(OSError) as caught: self.api.image_jobs('ignored')
                self.assertIs(caught.exception, error); getattr(f, stage).assert_called_once()
                for later in stages[stages.index(stage) + 1:]: getattr(f, later).assert_not_called()
    def test_detail_denial_and_refresh_error_propagate_without_fallback(self):
        f = self.f; denied = HTTPException(403, 'denied'); f.require.side_effect = [denied, None]
        with self.assertRaises(HTTPException) as caught: self.api.image_job(' raw ')
        self.assertIs(caught.exception, denied); f.require.assert_called_once(); f.worker.assert_not_called(); f.list_images.assert_not_called()
        f.worker.side_effect = None; f.worker.return_value = True; error = OSError('refresh')
        f.refresh.side_effect = [error, f.refresh_result]
        with self.assertRaises(OSError) as caught: self.api.image_job(' raw ')
        self.assertIs(caught.exception, error); f.refresh.assert_called_once(); f.public.assert_not_called(); f.list_images.assert_not_called()
    def test_detail_falsey_training_falls_back_to_first_job_or_task_id(self):
        f = self.f; first = {'job_id': 'different', 'task_id': ' raw '}; second = {'job_id': ' raw '}
        f.images = [first, second]
        for empty in [None, {}]:
            f.find.side_effect = None; f.find.return_value = empty
            self.assertIs(self.api.image_job(' raw '), first)
            self.assertEqual(f.list_images.call_args, call(user=f.user))
        f.require.assert_not_called(); f.worker.assert_not_called(); f.refresh.assert_not_called(); f.public.assert_not_called()
        with self.assertRaises(HTTPException) as caught: self.api.image_job('missing')
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (404, 'Image job not found'))
    def test_update_exact_mutation_order_none_empty_and_trimmed_values(self):
        for label, note, old, expected in [(None, None, 'original', 'original'), ('  ', '  ', 'original', 'original'),
                                            ('  ', '', '', '训练任务'), (' new ', ' new note ', 'original', 'new')]:
            with self.subTest(label=label, note=note, old=old), ExitStack() as stack:
                f = JobFixture(); f.bind(self.api, stack); f.task['label'] = old
                def save_false(task): f.save_record(task); return False
                f.save.side_effect = save_false
                request = self.api.TrainingTaskUpdateRequest(label=label, note=note)
                self.assertIs(self.api.update_training_task_endpoint(' raw ', request), f.public_result)
                self.assertEqual(f.events, ['user', 'find', 'require', 'clock', 'save', 'public'])
                f.require.assert_called_once_with(f.task, f.user, write=True); f.find.assert_called_once_with(' raw ')
                f.save.assert_called_once_with(f.task); f.public.assert_called_once_with(f.task)
                self.assertEqual(f.task['label'], expected); self.assertEqual(f.task['updated_at'], 321)
                if label is None: self.assertNotIn('candidate_name', f.task)
                else: self.assertEqual(f.task['candidate_name'], expected)
                self.assertEqual(f.task['note'], 'original note' if note is None else note.strip())
    def test_update_missing_and_denied_records_have_no_mutation(self):
        f = self.f; before = copy.deepcopy(f.task)
        for empty in [None, {}]:
            f.find.side_effect = None; f.find.return_value = empty
            with self.assertRaises(HTTPException) as caught: self.api.update_training_task_endpoint('raw', self.api.TrainingTaskUpdateRequest())
            self.assertEqual((caught.exception.status_code, caught.exception.detail), (404, 'Training task not found'))
        f.require.assert_not_called(); f.find.return_value = f.task; error = HTTPException(403, 'denied'); f.require.side_effect = [error, None]
        with self.assertRaises(HTTPException) as caught: self.api.update_training_task_endpoint('raw', self.api.TrainingTaskUpdateRequest(label='new'))
        self.assertIs(caught.exception, error); f.require.assert_called_once(); self.assertEqual(f.task, before)
        f.clock.assert_not_called(); f.save.assert_not_called(); f.public.assert_not_called()
    def test_update_clock_save_and_projection_failures_preserve_partial_mutation(self):
        for stage in ['clock', 'save', 'public']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f = JobFixture(); f.bind(self.api, stack); error = OSError(stage); target = getattr(f, stage)
                if stage == 'save':
                    def save(task):
                        f.save_record(task)
                        if f.save.call_count == 1: raise error
                    target.side_effect = save
                else: target.side_effect = [error, 999 if stage == 'clock' else f.public_result]
                with self.assertRaises(OSError) as caught: self.api.update_training_task_endpoint('raw', self.api.TrainingTaskUpdateRequest(label='new', note='note'))
                self.assertIs(caught.exception, error); target.assert_called_once()
                self.assertEqual((f.task['label'], f.task['candidate_name'], f.task['note']), ('new', 'new', 'note'))
                self.assertEqual('updated_at' in f.task, stage != 'clock')
                self.assertEqual(f.save.call_count, int(stage != 'clock')); self.assertEqual(f.public.call_count, int(stage == 'public'))
                self.assertEqual(len(f.saved), int(stage != 'clock'))
    def test_delete_raw_id_then_scoped_list_and_failure_residue(self):
        f = self.f; result = self.api.delete_training_task_endpoint(' raw ')
        self.assertEqual(f.events, ['user', 'delete', 'training-list'])
        self.assertEqual(result, {'status': 'deleted', 'job_id': ' raw ', 'items': f.training}); self.assertIs(result['items'], f.training)
        f.delete.assert_called_once_with(' raw ', f.user); f.list_training.assert_called_once_with(user=f.user)
        error = OSError('list-after-delete'); f.delete.reset_mock(); f.list_training.reset_mock(); f.list_training.side_effect = [error, f.training]
        with self.assertRaises(OSError) as caught: self.api.delete_training_task_endpoint(' raw ')
        self.assertIs(caught.exception, error); f.delete.assert_called_once(); f.list_training.assert_called_once(); self.assertEqual(len(f.deleted), 2)
    def test_delete_failure_is_not_retried_and_does_not_list(self):
        f = self.f; error = OSError('delete'); f.delete.side_effect = [error, None]
        with self.assertRaises(OSError) as caught: self.api.delete_training_task_endpoint(' raw ')
        self.assertIs(caught.exception, error); f.delete.assert_called_once_with(' raw ', f.user); f.list_training.assert_not_called()
    def test_control_routes_forward_exact_actions_without_extra_identity_read(self):
        f = self.f
        for name, target, action in [('stop_image_job', f.job_action, 'stop'), ('retry_image_job', f.job_action, 'retry'),
                                    ('delete_image_job', f.job_action, 'delete'), ('stop_image_job_candidate', f.candidate_action, 'stop'),
                                    ('delete_image_job_candidate', f.candidate_action, 'delete')]:
            target.reset_mock(); self.assertIs(getattr(self.api, name)(' raw '), f.control_result); target.assert_called_once_with(' raw ', action)
            target.reset_mock(); error = HTTPException(409, 'control failed'); target.side_effect = [error, f.control_result]
            with self.assertRaises(HTTPException) as caught: getattr(self.api, name)(' raw ')
            self.assertIs(caught.exception, error); target.assert_called_once_with(' raw ', action); target.side_effect = None
        f.current.assert_not_called(); f.find.assert_not_called()
    def test_http_validation_and_identity_errors_keep_response_format(self):
        app = FastAPI(); app.get('/api/image-jobs')(self.api.image_jobs); app.get('/api/image-jobs/{job_id}')(self.api.image_job)
        app.patch('/api/training/tasks/{job_id}')(self.api.update_training_task_endpoint)
        app.delete('/api/training/tasks/{job_id}')(self.api.delete_training_task_endpoint)
        with TestClient(app) as client:
            response = client.patch('/api/training/tasks/job', json={'label': []})
            self.assertEqual(response.status_code, 422); self.f.current.assert_not_called()
            for code in [401, 403]:
                self.f.current.side_effect = HTTPException(code, 'identity denied')
                for method, path, kwargs in [('get', '/api/image-jobs', {}), ('get', '/api/image-jobs/job', {}),
                    ('patch', '/api/training/tasks/job', {'json': {}}), ('delete', '/api/training/tasks/job', {})]:
                    response = getattr(client, method)(path, **kwargs)
                    self.assertEqual((response.status_code, response.json()), (code, {'detail': 'identity denied'}))
            self.f.find.assert_not_called(); self.f.list_training.assert_not_called(); self.f.delete.assert_not_called()


    def test_detail_and_patch_dependency_errors_never_retry_or_fall_back(self):
        for endpoint, stage in [('detail', 'find'), ('patch', 'find'), ('detail', 'worker'), ('detail', 'public'), ('detail', 'list_images')]:
            with self.subTest(endpoint=endpoint, stage=stage), ExitStack() as stack:
                f = JobFixture(); f.bind(self.api, stack); error = OSError(endpoint + '-' + stage)
                successful = {'find': f.task, 'worker': False, 'public': f.public_result, 'list_images': f.images}
                if stage == 'list_images': f.find.side_effect = None; f.find.return_value = None
                getattr(f, stage).side_effect = [error, successful[stage]]
                with self.assertRaises(OSError) as caught:
                    if endpoint == 'detail': self.api.image_job(' raw ')
                    else: self.api.update_training_task_endpoint(' raw ', self.api.TrainingTaskUpdateRequest(label='new'))
                self.assertIs(caught.exception, error); getattr(f, stage).assert_called_once(); f.find.assert_called_once_with(' raw ')
                self.assertEqual(f.require.call_count, int(stage in {'worker', 'public'}))
                self.assertEqual(f.worker.call_count, int(stage in {'worker', 'public'}))
                self.assertEqual(f.public.call_count, int(stage == 'public')); self.assertEqual(f.list_images.call_count, int(stage == 'list_images'))
                f.refresh.assert_not_called(); f.clock.assert_not_called(); f.save.assert_not_called(); f.delete.assert_not_called()
                self.assertEqual(f.task['label'], 'original')

    def test_active_membership_reads_current_policy_after_each_status_lookup(self):
        api = self.api
        class StatusSwitch(dict):
            def get(self, key, default=None):
                if key == 'status': api.IMAGE_JOB_ACTIVE_STATUSES = {'running'}
                return super().get(key, default)
        first = {'job_id': 'first', 'status': 'queued'}; second = StatusSwitch(job_id='second', status='running')
        self.f.training = [first, second]; self.f.images = []; api.IMAGE_JOB_ACTIVE_STATUSES = {'queued'}
        result = api.image_jobs()
        self.assertEqual(result['active'], [first, second]); self.assertIs(result['active'][0], first); self.assertIs(result['active'][1], second)
        self.assertEqual(result['completed'], [])

    def test_real_task_views_keep_retired_worker_read_only_and_native_detail_unsettled(self):
        from local_inspection_service.training.task_lifecycle import training_task_uses_worker
        from local_inspection_service.training.task_views import TrainingTaskViews, TrainingViewAccess
        refresh = Mock(side_effect=AssertionError('unexpected task settlement or worker probe'))
        views = TrainingTaskViews(lambda: [], refresh, TrainingViewAccess(dict, lambda: (lambda value: value), lambda *args: True))
        with patch.object(self.api, 'training_task_uses_worker', training_task_uses_worker), \
             patch.object(self.api, 'public_training_task', views.public_training_task), \
             patch.object(self.api, 'public_refreshed_training_task', views.public_refreshed_training_task):
            self.f.task.update(training_executor='worker', status='running')
            result = self.api.image_job(' raw ')
            self.assertTrue(result['executor_retired']); self.assertTrue(result['remote_refresh_retired']); self.assertEqual(result['status'], 'running')
            self.f.task['training_executor'] = 'runpod'
            result = self.api.image_job(' raw ')
            self.assertNotIn('executor_retired', result); self.assertEqual(result['status'], 'running')
            refresh.assert_not_called()

    def failure_fixture(self, stack, mode):
        f = JobFixture(); values = f.bind(self.api, stack)
        if mode == 'worker': f.worker.side_effect = lambda task: True
        if mode == 'image': f.find.side_effect = lambda job: None; f.images = [{'job_id': 'job'}]
        operations = {
            'list': lambda: self.api.image_jobs(),
            'native': lambda: self.api.image_job('job'),
            'worker': lambda: self.api.image_job('job'),
            'image': lambda: self.api.image_job('job'),
            'update': lambda: self.api.update_training_task_endpoint('job', self.api.TrainingTaskUpdateRequest(label='new', note='note')),
            'delete': lambda: self.api.delete_training_task_endpoint('job'),
        }
        for name in ['stop_image_job', 'retry_image_job', 'delete_image_job', 'stop_image_job_candidate', 'delete_image_job_candidate']:
            operations[name] = lambda name=name: getattr(self.api, name)('job')
        import time
        ports = {name: (self.api, name, port) for name, port in values.items() if isinstance(port, Mock)}
        ports['clock'] = (time, 'time', f.clock)
        return f, operations[mode], ports

    def test_all_callback_first_errors_propagate_without_retry(self):
        modes = ['list', 'native', 'worker', 'image', 'update', 'delete', 'stop_image_job',
                 'retry_image_job', 'delete_image_job', 'stop_image_job_candidate', 'delete_image_job_candidate']
        for mode in modes:
            with ExitStack() as stack:
                _, operation, ports = self.failure_fixture(stack, mode); operation()
                counts = {name: port.call_count for name, (_, _, port) in ports.items() if port.call_count}
            for name, count in counts.items():
                for index in range(1, count + 1):
                    with self.subTest(mode=mode, name=name, index=index), ExitStack() as stack:
                        _, operation, ports = self.failure_fixture(stack, mode)
                        owner, field, original = ports[name]; calls = []; failure = RuntimeError('jobs-first')
                        def fail_once(*args, **kwargs):
                            calls.append(None)
                            if len(calls) == index: raise failure
                            return original(*args, **kwargs)
                        stack.enter_context(patch.object(owner, field, fail_once))
                        with self.assertRaises(RuntimeError) as caught: operation()
                        self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_active_provider_first_error_propagates_at_each_item_without_retry(self):
        query = self.api._training_jobs_query
        for index in range(1, len(self.f.training + self.f.images) + 1):
            with self.subTest(index=index), ExitStack() as stack:
                _, operation, _ = self.failure_fixture(stack, 'list')
                original = query.active; calls = []; failure = RuntimeError('active-first')
                def fail_once():
                    calls.append(None)
                    if len(calls) == index: raise failure
                    return original()
                stack.enter_context(patch.object(query, 'active', fail_once))
                with self.assertRaises(RuntimeError) as caught: operation()
                self.assertIs(caught.exception, failure); self.assertEqual(len(calls), index)

    def test_independent_jobs_apps_threadpool_identity_and_mutation_isolation(self):
        import asyncio
        from contextvars import ContextVar
        import threading
        import httpx
        from local_inspection_service.training.jobs_query import JobsReadAccess, JobsTraining, TrainingJobsQuery
        from local_inspection_service.training.task_mutations import TaskMutationRecords, TrainingTaskMutations
        from local_inspection_service.training.jobs_api import ImageJobActions, register
        identity = ContextVar('training-jobs-fixture-user'); barrier = threading.Barrier(2); instances = []
        def current():
            barrier.wait(timeout=10)
            return identity.get()
        for owner in ['alice', 'bob']:
            f = JobFixture(); f.user = {'id': owner, 'role': 'member'}; f.task['job_id'] = owner
            f.training = [{'job_id': owner, 'status': 'queued'}]; f.images = []
            f.public_result = {'owner': owner}; f.control_result = {'control_owner': owner}
            f.job_action.return_value = f.control_result; f.candidate_action.return_value = f.control_result
            current_port = Mock(side_effect=current); active = Mock(return_value=f.active)
            query = TrainingJobsQuery(JobsReadAccess(current_port, f.admin, f.require),
                JobsTraining(f.find, f.worker, f.public, f.refresh), f.list_training, f.list_images, active)
            mutations = TrainingTaskMutations(current_port, f.require,
                TaskMutationRecords(f.find, f.save, f.public, f.delete, f.list_training), f.clock)
            app = FastAPI()
            @app.middleware('http')
            async def account_context(request, call_next):
                token = identity.set({'id': request.headers['x-fixture-owner'], 'role': 'member'})
                try: return await call_next(request)
                finally: identity.reset(token)
            routes = register(app, query, mutations, ImageJobActions(f.job_action, f.candidate_action))
            for name in routes.__dataclass_fields__:
                self.assertEqual([route.endpoint for route in app.routes if route.name == name], [getattr(routes, name)])
            self.assertEqual(app.router.on_startup, []); self.assertEqual(f.events, [])
            current_port.assert_not_called(); active.assert_not_called(); instances.append((app, f, current_port, active, query))
        for name in ['current_auth_user', 'user_is_admin', 'list_training_tasks', 'list_codex_image_jobs', 'find_training_task',
                     'require_record_access', 'training_task_uses_worker', 'public_training_task', 'public_refreshed_training_task',
                     'save_training_task', 'delete_training_task_record', 'update_codex_image_job', 'update_codex_image_candidate']:
            self.stack.enter_context(patch.object(self.api, name, side_effect=AssertionError('unexpected root dependency')))
        async def request(instance):
            app, f, *_ = instance; owner = f.user['id']; headers = {'x-fixture-owner': owner}
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://fixture.invalid') as client:
                result = await client.get('/api/image-jobs?user_id=ignored', headers=headers)
                self.assertEqual(result.status_code, 200); self.assertEqual(result.json()['items'], f.training)
                result = await client.get('/api/image-jobs/' + owner, headers=headers)
                self.assertEqual(result.status_code, 200); self.assertEqual(result.json(), {'owner': owner})
                result = await client.patch('/api/training/tasks/' + owner, headers=headers, json={'label': 'new ' + owner})
                self.assertEqual(result.status_code, 200); self.assertEqual(result.json(), {'owner': owner})
                result = await client.delete('/api/training/tasks/' + owner, headers=headers)
                self.assertEqual(result.status_code, 200); self.assertEqual(result.json(), {'status': 'deleted', 'job_id': owner, 'items': f.training})
                for method, path in [('post', '/api/image-jobs/' + owner + '/stop'), ('post', '/api/image-jobs/' + owner + '/retry'),
                                     ('delete', '/api/image-jobs/' + owner), ('post', '/api/image-job-candidates/' + owner + '/stop'),
                                     ('delete', '/api/image-job-candidates/' + owner)]:
                    result = await getattr(client, method)(path, headers=headers)
                    self.assertEqual((result.status_code, result.json()), (200, {'control_owner': owner}))
        async def both(): await asyncio.gather(*(request(instance) for instance in instances))
        asyncio.run(both()); self.assertIsNone(identity.get(None))
        for app, f, current_port, active, query in instances:
            owner = f.user['id']; self.assertEqual(current_port.call_count, 4); active.assert_called_once_with()
            self.assertEqual(f.task['label'], 'new ' + owner); self.assertEqual(f.saved[0]['job_id'], owner)
            self.assertEqual(f.deleted, [(owner, f.user)]); self.assertEqual(len(f.saved), 1)
            for entry in f.require.call_args_list: self.assertEqual(entry.args[1]['id'], owner)
            self.assertEqual(f.list_training.call_args_list, [call(user=f.user, target_user_id=None), call(user=f.user)])
            self.assertEqual(f.job_action.call_args_list, [call(owner, 'stop'), call(owner, 'retry'), call(owner, 'delete')])
            self.assertEqual(f.candidate_action.call_args_list, [call(owner, 'stop'), call(owner, 'delete')])
            with patch.object(current_port, 'side_effect', lambda: f.user):
                f.training = [{'status': 'queued'}, {'status': 'completed'}]; f.images = []; active.reset_mock()
                query.image_jobs(); self.assertEqual(active.call_count, 2)
                f.training = []; active.reset_mock()
                self.assertEqual(query.image_jobs(), {'items': [], 'active': [], 'completed': []}); active.assert_not_called()



if __name__ == '__main__': unittest.main()
