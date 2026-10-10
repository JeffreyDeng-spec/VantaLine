"""Real application ownership, ASGI contracts and bounded lifetime failures.

All files/accounts/connections are synthetic. No lifespan/native workers, model
inference, device I/O or external database connection is started here.
"""
import ast
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi import FastAPI
from local_inspection_service.runtime.application import create_application
from local_inspection_service.runtime import application as application_module
from local_inspection_service.runtime.path_configuration_composition import PathConfigurationWorkflows
from local_inspection_service.runtime.application_lifetime import ApplicationLifetime, register_application_lifetime
from local_inspection_service.runtime.connections import ThreadRepositoryFactory
from local_inspection_service.runtime.shutdown import ShutdownStep, WebShutdown, register_web_shutdown
from verify_backend_contract import capture_http_errors, same_capability, assert_owned_text_callbacks


def environment(home):
    (home / 'local_inspection_service/static').mkdir(parents=True)
    return {'LOCAL_INSPECTION_ROOT': str(home), 'VANTALINE_DATA_STORE': 'json',
            'VANTALINE_FILE_STORE': 'local', 'VANTALINE_LABEL_INSPECTION_ENABLED': 'false',
            'LOCAL_INSPECTION_AUTO_RESUME_WORKER': '0', 'INSPECTION_ENABLE_LAN_CORS': '0',
            'INSPECTION_CORS_ORIGINS': ''}


class Connection:
    def __init__(self, owner): self.owner, self.closed = owner, False
    def close(self): self.closed = True


class ApplicationContracts(unittest.TestCase):
    def test_real_photo_source_confirmation_real_http_owner_and_strict_boolean(self):
        import copy
        from contextlib import contextmanager
        from dataclasses import replace
        from fastapi.testclient import TestClient

        class Repository:
            def __init__(self):
                self.state = {'enabled': False, 'classes': [], 'profiles': {}, 'datasets': [],
                              'samples': [{'sample_id': 'sample', 'source_group': 'original-batch',
                                           'image_sha256': 'synthetic', 'geometry': {'width': 80, 'height': 60}}]}
                self.mutations = 0
            def get(self, owner, identifier):
                return copy.deepcopy(self.state)
            def jobs(self, owner, identifier):
                return []
            def statistics(self, owner, identifier):
                return {}
            def mutate(self, owner, identifier, operation):
                candidate = copy.deepcopy(self.state)
                operation(candidate, None)
                self.state = candidate
                self.mutations += 1

        with tempfile.TemporaryDirectory(prefix='application-source-confirmation-') as temporary:
            owned = create_application(environment(Path(temporary)))
            self.addCleanup(lambda: self.assertTrue(owned.lifetime.close(10)))
            client = TestClient(owned.app, base_url='https://testserver')
            anonymous = TestClient(owned.app, base_url='https://testserver')
            self.addCleanup(client.close)
            self.addCleanup(anonymous.close)
            password = 'synthetic-source-confirmation-password'
            response = client.post('/api/auth/bootstrap', json={'username': 'source-owner', 'password': password})
            self.assertEqual(response.status_code, 200, response.text)
            response = client.get('/api/auth/status')
            self.assertEqual(response.status_code, 200, response.text)
            owner = response.json()['user']['id']
            response = client.post('/api/auth/users', json={'username': 'source-neighbor', 'password': password, 'role': 'admin'})
            self.assertEqual(response.status_code, 200, response.text)
            neighbor = TestClient(owned.app, base_url='https://testserver')
            self.addCleanup(neighbor.close)
            response = neighbor.post('/api/auth/login', json={'username': 'source-neighbor', 'password': password})
            self.assertEqual(response.status_code, 200, response.text)
            service = owned.training_pipeline._real_photo_workflows.feedback
            task = {'id': 'task', 'owner_user_id': owner}
            service.ports = replace(service.ports, tasks=lambda: [task])
            repository = Repository()
            @contextmanager
            def scope():
                yield repository
            path = '/api/ai/tasks/task/real-photo/samples/sample/group'
            with patch.object(service, 'repo', scope), patch.dict(os.environ, {'VANTALINE_REAL_PHOTO_ACCOUNTS': owner}):
                self.assertEqual(anonymous.patch(path, json={'source_group': 'known-batch'}).status_code, 401)
                self.assertEqual(neighbor.patch(path, json={'source_group': 'known-batch'}).status_code, 403)
                self.assertEqual(repository.mutations, 0)
                version = 0
                for body, expected in [({'source_group': 'legacy-batch'}, True),
                                       ({'source_group': 'null-batch', 'source_group_confirmed': None}, True),
                                       ({'source_group': 'pending-batch', 'source_group_confirmed': False}, False),
                                       ({'source_group': 'verified-batch', 'source_group_confirmed': True}, True)]:
                    response = client.patch(path, json=body)
                    self.assertEqual(response.status_code, 200, response.text)
                    version += 1
                    sample = response.json()['samples'][0]
                    self.assertIs(sample['source_group_confirmed'], expected)
                    self.assertEqual(sample['source_group_version'], version)
                    self.assertEqual(response.json()['unconfirmed_source_count'], int(not expected))
                    self.assertEqual(response.json()['jobs'], [])
                unchanged = copy.deepcopy(repository.state)
                before = repository.mutations
                for invalid in (0, 1, 'true', 'false', {}, []):
                    response = client.patch(path, json={'source_group': 'known-batch', 'source_group_confirmed': invalid})
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertEqual(repository.state, unchanged)
                    self.assertEqual(repository.mutations, before)
                response = client.patch(path, json={'source_group': 'historical-unconfirmed', 'source_group_confirmed': True})
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(repository.state, unchanged)
                response = client.get('/api/ai/tasks/task/real-photo/samples/sample/versions')
                self.assertEqual(response.status_code, 200, response.text)
                groups = response.json()['source_groups']
                self.assertEqual(len(groups), 5)
                self.assertEqual([item['version'] for item in groups], [0, 1, 2, 3, 4])
                self.assertEqual(groups[-1]['modified_by'], owner)
                self.assertEqual(groups[-1]['source_group'], 'verified-batch')
                self.assertIs(groups[-1]['confirmed'], True)
            self.assertIsNone(owned.infrastructure._request_user.get())

    def test_parent_bindings_and_registered_tuple_exports_are_preserved(self):
        from canonical_application_source_contract import FIXTURE

        def bindings(source):
            names = set()
            for node in ast.parse(source).body:
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    names.update(part.id for target in targets for part in ast.walk(target)
                                 if isinstance(part, ast.Name) and isinstance(part.ctx, ast.Store))
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(node.name)
                elif isinstance(node, ast.Import):
                    names.update(alias.asname or alias.name.split('.')[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    names.update(alias.asname or alias.name for alias in node.names)
            return names

        parent_names = bindings(FIXTURE['parent_source'])
        current_names = bindings((ROOT / 'local_inspection_service/server.py').read_text(encoding='utf-8'))
        self.assertFalse(parent_names - current_names, sorted(parent_names - current_names))
        exports = (
            ('openapi_schema', '/openapi.json', 'GET'),
            ('swagger_ui', '/api/docs', 'GET'),
            ('redoc_ui', '/redoc', 'GET'),
            ('add_pipeline_accessory', '/api/pipeline/accessories/{accessory_id}', 'POST'),
            ('remove_pipeline_accessory', '/api/pipeline/accessories/{accessory_id}', 'DELETE'),
            ('advance_pipeline_task_endpoint', '/api/pipeline/tasks/{task_id}/advance', 'POST'),
            ('cancel_pipeline_advance_endpoint', '/api/pipeline/tasks/{task_id}/cancel-advance', 'POST'),
        )
        with tempfile.TemporaryDirectory(prefix='application-exports-') as temporary:
            with patch.dict(os.environ, environment(Path(temporary) / 'default')):
                from local_inspection_service import server
                for name, path, method in exports:
                    with self.subTest(export=name):
                        routes = [route for route in server.app.routes
                                  if getattr(route, 'path', None) == path and method in (getattr(route, 'methods', ()) or ())]
                        self.assertEqual(len(routes), 1)
                        self.assertIs(getattr(server, name), getattr(server._default_application.http, name))
                        self.assertIs(getattr(server, name), routes[0].endpoint)

    def test_construction_failure_releases_selection_before_lifetime_exists(self):
        connections = []
        with tempfile.TemporaryDirectory(prefix='application-construction-') as temporary:
            env = environment(Path(temporary) / 'failure')
            def connect(url):
                self.assertEqual(url, 'postgresql://synthetic.invalid/failure')
                connection = Connection('failure'); connections.append(connection); return connection
            def fail(values, source, ports):
                source.update(VANTALINE_DATA_STORE='postgres', DATABASE_URL='postgresql://synthetic.invalid/failure')
                ports._runtime_repositories().selection()
                raise ValueError('original construction failure')
            with patch.object(application_module, 'assemble_training_pipeline', fail), self.assertRaisesRegex(ValueError, 'original construction failure'):
                create_application(env, connector=connect)
            self.assertEqual(len(connections), 1)
            self.assertTrue(connections[0].closed)

    def test_final_initialization_preserves_failure_and_releases_interrupted_cleanup(self):
        connections, lifetimes = [], []
        with tempfile.TemporaryDirectory(prefix='application-initialization-') as temporary:
            env = environment(Path(temporary) / 'failure')
            def connect(url):
                self.assertEqual(url, 'postgresql://synthetic.invalid/failure')
                connection = Connection('failure'); connections.append(connection); return connection
            original = application_module.register_application_lifetime
            def register(app, shutdown, factory):
                owner = original(app, shutdown, factory)
                lifetimes.append(owner)
                env.update(VANTALINE_DATA_STORE='postgres', DATABASE_URL='postgresql://synthetic.invalid/failure')
                factory.selection()
                return owner
            with patch.object(application_module, 'register_application_lifetime', register), \
                 patch.object(PathConfigurationWorkflows, 'ensure_dirs', side_effect=ValueError('original initialization failure')), \
                 patch.object(WebShutdown, 'close', side_effect=KeyboardInterrupt('synthetic cleanup interruption')):
                with self.assertRaisesRegex(ValueError, 'original initialization failure'):
                    create_application(env, connector=connect)
            self.assertEqual(len(connections), 1)
            self.assertTrue(connections[0].closed)
            self.assertEqual(len(lifetimes), 1)
            self.assertTrue(lifetimes[0].close(10))

    def test_actual_owned_http_and_mutable_state(self):
        with tempfile.TemporaryDirectory(prefix='application-factory-') as temporary:
            a = create_application(environment(Path(temporary) / 'a'))
            b = create_application(environment(Path(temporary) / 'b'))
            try:
                self.assertIsNot(a.app, b.app)
                for name in ('_request_user', '_runtime_repositories', '_config_io_lock'):
                    self.assertIsNot(getattr(a.infrastructure, name), getattr(b.infrastructure, name))
                self.assertIsNot(a.inspection._provider_transports, b.inspection._provider_transports)
                self.assertIsNot(a.training_pipeline._training_task_runtime, b.training_pipeline._training_task_runtime)
                self.assertIsNot(a.plc._plc_io_executor, b.plc._plc_io_executor)
                self.assertIsNot(a.http._web_shutdown, b.http._web_shutdown)
                for name in ('DEFAULT_CONFIG', 'MODEL_REGISTRY', 'AI_DEFAULT_MODELS'):
                    self.assertIsNot(getattr(a.values, name), getattr(b.values, name))
                expected = json.loads((ROOT / 'tests/backend_contract/application.json').read_text())
                self.assertEqual(a.app.openapi(), expected['openapi'])
                self.assertEqual(capture_http_errors(a.app), expected['http_errors'])
                self.assertEqual([hook.__name__ for hook in a.app.router.on_startup], expected['startup'])
                self.assertEqual([hook.__name__ for hook in a.app.router.on_shutdown], expected['shutdown'])
                self.assertEqual([(route.path, sorted(getattr(route, 'methods', ()) or ())) for route in a.app.routes],
                                 [(route.path, sorted(getattr(route, 'methods', ()) or ())) for route in b.app.routes])
                self.assertIs(a.http.training_background_sets, a.http._background_routes.training_background_sets)
                generation = b.infrastructure._runtime_repositories.generation()
                self.assertTrue(a.lifetime.close(10))
                self.assertTrue(a.lifetime.close(0))
                self.assertFalse(b.lifetime.closed)
                self.assertEqual(b.infrastructure._runtime_repositories.generation(), generation)
                with self.assertRaisesRegex(RuntimeError, 'stopping or closed'):
                    a.app.router.on_startup[0]()
            finally:
                self.assertTrue(a.lifetime.close(10))
                self.assertTrue(b.lifetime.close(10))

    def test_initial_callbacks_reject_same_named_other_application_capabilities(self):
        with tempfile.TemporaryDirectory(prefix='application-capabilities-') as temporary:
            a = create_application(environment(Path(temporary) / 'a'))
            b = create_application(environment(Path(temporary) / 'b'))
            try:
                assert_owned_text_callbacks(a)
                assert_owned_text_callbacks(b)
                first = a.text._incoming_media.output()
                other = b.text._incoming_media.output()
                self.assertTrue(same_capability(first, a.text._incoming_media.output()))
                self.assertFalse(same_capability(first, other))
                native_a = a.infrastructure._service_paths.output_write_dir_for_owner
                native_b = b.infrastructure._service_paths.output_write_dir_for_owner
                self.assertTrue(same_capability(native_a, a.infrastructure._service_paths.output_write_dir_for_owner))
                self.assertFalse(same_capability(native_a, native_b))
                # Actual native behavior distinguishes two same-named methods
                # and two same-signature graph relays without substituting them.
                path_a = first('contract', 'same-user')
                path_b = other('contract', 'same-user')
                self.assertEqual(path_a, native_a('contract', 'same-user'))
                self.assertEqual(path_b, native_b('contract', 'same-user'))
                self.assertNotEqual(path_a, path_b)
                self.assertTrue(path_a.is_relative_to((Path(temporary) / 'a').resolve()))
                self.assertTrue(path_b.is_relative_to((Path(temporary) / 'b').resolve()))
                # The initial-owner proof must reject a wrong graph before any
                # historical server reassignment. The frozen port is restored.
                with patch.object(type(a.text._incoming_media), 'output',
                                  property(lambda _: lambda: other), create=True):
                    with self.assertRaises(AssertionError):
                        assert_owned_text_callbacks(a)
                allowed_b = b.text._incoming_task_access.allowed()
                with patch.object(a.text._incoming_task_access, 'allowed', lambda: allowed_b):
                    with self.assertRaises(AssertionError):
                        assert_owned_text_callbacks(a)
                self.assertTrue(same_capability(first, a.text._incoming_media.output()))
                assert_owned_text_callbacks(a)
                assert_owned_text_callbacks(b)
            finally:
                self.assertTrue(a.lifetime.close(10))
                self.assertTrue(b.lifetime.close(10))

    def test_concurrent_identity_thread_connections_and_exception_release(self):
        connections = []
        with tempfile.TemporaryDirectory(prefix='application-identity-') as temporary:
            owned = []
            for name in ('a', 'b'):
                env = environment(Path(temporary) / name)
                def connect(url, name=name):
                    self.assertEqual(url, 'postgresql://synthetic.invalid/' + name)
                    connection = Connection(name); connections.append(connection); return connection
                app = create_application(env, connector=connect)
                env.update(VANTALINE_DATA_STORE='postgres', DATABASE_URL='postgresql://synthetic.invalid/' + name)
                owned.append(app)
            barrier = threading.Barrier(2)
            async def request(app, name):
                token = app.infrastructure._request_user.set({'id': name, 'role': 'user'})
                try:
                    def work():
                        factory = app.infrastructure._runtime_repositories
                        with factory.thread_scope():
                            self.assertEqual(app.infrastructure._request_user.get()['id'], name)
                            first = factory.selection()
                            self.assertEqual(first.repository.connection.owner, name)
                            self.assertIs(factory.selection(), first)
                            barrier.wait(timeout=10)
                            first.repository.connection.closed = True
                            replacement = factory.selection()
                            self.assertIsNot(replacement, first)
                            self.assertEqual(replacement.repository.connection.owner, name)
                            raise LookupError('synthetic exception cleanup')
                    with self.assertRaisesRegex(LookupError, 'synthetic exception cleanup'):
                        await asyncio.to_thread(work)
                finally:
                    app.infrastructure._request_user.reset(token)
            async def requests(): await asyncio.gather(request(owned[0], 'a'), request(owned[1], 'b'))
            try:
                asyncio.run(requests())
                self.assertEqual(len(connections), 4)
                self.assertTrue(all(connection.closed for connection in connections))
                self.assertTrue(all(app.infrastructure._request_user.get() is None for app in owned))
            finally:
                for app in owned: self.assertTrue(app.lifetime.close(10))

    def test_actual_default_entry_uses_same_factory_without_coupling_new_app(self):
        with tempfile.TemporaryDirectory(prefix='application-default-') as temporary:
            env = environment(Path(temporary) / 'default')
            with patch.dict(os.environ, env):
                from local_inspection_service import server
                from local_inspection_service.runtime.default_application import default_application
                self.assertIs(server.app, default_application.app)
                self.assertIs(server._request_user, default_application.infrastructure._request_user)
                self.assertIs(server.analyze_video, default_application.http.analyze_video)
                self.assertIs(next(route.endpoint for route in server.app.routes if route.path == '/api/analyze/video'), server.analyze_video)
                other = create_application(environment(Path(temporary) / 'other'))
                try:
                    self.assertIsNot(other.app, server.app)
                    self.assertIsNot(other.infrastructure._request_user, server._request_user)
                    other_decoder = other.inspection._detection_task_store.rows.decode()
                    default_decoder = default_application.inspection._detection_task_store.rows.decode()
                    with patch.object(server, 'row_raw_json_list', None):
                        self.assertTrue(callable(other.inspection._detection_task_store.rows.decode()))
                        self.assertTrue(callable(default_application.inspection._detection_task_store.rows.decode()))
                        self.assertTrue(same_capability(other.inspection._detection_task_store.rows.decode(), other_decoder))
                        self.assertTrue(same_capability(default_application.inspection._detection_task_store.rows.decode(), default_decoder))
                    self.assertTrue(same_capability(other.inspection._detection_task_store.rows.decode(), other_decoder))
                    self.assertTrue(same_capability(default_application.inspection._detection_task_store.rows.decode(), default_decoder))
                finally:
                    self.assertTrue(other.lifetime.close(10))
                    self.assertTrue(default_application.lifetime.close(10))


class LifetimeContracts(unittest.TestCase):
    def factory(self): return ThreadRepositoryFactory(lambda: None, lambda: None)

    def test_once_order_repeated_close_and_failure_retry(self):
        events = []
        app = FastAPI()
        app.on_event('startup')(lambda: events.append('first'))
        app.on_event('startup')(lambda: events.append('second'))
        shutdown = register_web_shutdown(app, (ShutdownStep('resource', lambda _: events.append('close') or True),))
        owner = register_application_lifetime(app, shutdown, self.factory())
        for _ in range(2):
            for hook in app.router.on_startup: hook()
        self.assertEqual(events, ['first', 'second'])
        self.assertTrue(owner.close(1)); self.assertTrue(owner.close(0))
        self.assertEqual(events, ['first', 'second', 'close'])
        attempts = []
        owner = ApplicationLifetime(WebShutdown((), (ShutdownStep('retry-drain', lambda _: attempts.append(1) or len(attempts) == 2),)), self.factory())
        self.assertFalse(owner.close(1))
        with self.assertRaises(RuntimeError): owner.startup_hook(0, lambda: None)()
        self.assertTrue(owner.close(1)); self.assertEqual(len(attempts), 2)

    def test_close_timeout_immediately_fences_later_startup(self):
        started, release = threading.Event(), threading.Event()
        errors, later = [], []
        owner = ApplicationLifetime(WebShutdown((), ()), self.factory())
        def start(): started.set(); self.assertTrue(release.wait(10))
        def run():
            try: owner.startup_hook(0, start)()
            except BaseException as error: errors.append(error)
        thread = threading.Thread(target=run)
        thread.start()
        try:
            self.assertTrue(started.wait(10))
            self.assertFalse(owner.close(.01))
        finally:
            release.set(); thread.join(10)
        self.assertFalse(thread.is_alive()); self.assertEqual(errors, [])
        with self.assertRaises(RuntimeError): owner.startup_hook(1, lambda: later.append(1))()
        self.assertEqual(later, []); self.assertTrue(owner.close(1))

    def test_startup_preserves_original_failure_when_cleanup_is_interrupted(self):
        attempts = []
        def cleanup(timeout):
            attempts.append(timeout)
            if len(attempts) == 1: raise KeyboardInterrupt('synthetic cleanup interruption')
            return True
        owner = ApplicationLifetime(WebShutdown((), (ShutdownStep('resource', cleanup),)), self.factory())
        def start(): raise ValueError('original startup failure')
        with self.assertRaisesRegex(ValueError, 'original startup failure'): owner.startup_hook(0, start)()
        with self.assertRaises(RuntimeError): owner.startup_hook(0, lambda: None)()
        self.assertFalse(owner.closed); self.assertTrue(owner.close(1)); self.assertEqual(len(attempts), 2)


if __name__ == '__main__': unittest.main()
