"""HTTP media ports preserve auth ordering and isolate independently composed stores."""
import asyncio
import ast
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
import smoke_detection_artifact_ports as fixtures
from local_inspection_service.auth.middleware import SecurityDependencies, register_security_middleware
from local_inspection_service.runtime.identity import RequestIdentity
from local_inspection_service.runtime.http_application import create_http_application
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts import http
from local_inspection_service.text_inspection.incoming_api import register_catalog, register_inspections
from local_inspection_service.text_inspection import incoming_api
from local_inspection_service.training.background_query import BackgroundQuery


class HttpArtifactPortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)
        self.default = Mock(side_effect=AssertionError('default HTTP storage used'))
        p = patch.object(http, 'BusinessFiles', self.default); p.start(); self.addCleanup(p.stop)

    def app(self, index):
        runtime = self.runtimes[index]; provider = Mock(return_value=runtime)
        files = BusinessFiles(provider); body = ('graph-' + str(index) + '-0123456789').encode()
        for key in ['outputs/users/a/image.png', 'backgrounds/a/image.png']:
            files.write_bytes(self.root / key, body)
        (self.root / 'outputs').mkdir(exist_ok=True)
        provider.reset_mock()
        app = create_http_application({'VANTALINE_FILE_STORE': 'cos'}, upload_runtime_provider=provider).app
        identity = RequestIdentity()
        def authenticate(request, **options):
            owner = request.headers.get('x-owner')
            perms = [] if request.headers.get('x-blocked') else ['inspection', 'incoming_material_config', 'training_pipeline']
            return ({'id': owner, 'role': 'user', 'permissions': perms} if owner else None, {'users': True}, False)
        register_security_middleware(app, SecurityDependencies(authenticate, lambda store: True, identity,
            lambda path, user: path.startswith('/outputs/users/' + user['id'] + '/'), lambda *args: True, lambda *args: False))
        def selected(owner, kind):
            if owner != identity.get()['id']: raise HTTPException(404, 'Not found')
            return self.root / 'outputs/users/a/image.png'
        register_catalog(app, SimpleNamespace(get_incoming_text_reference_asset=selected), files=lambda: files)
        register_inspections(app, None, SimpleNamespace(get_incoming_text_inspection_evidence=selected), files=lambda: files)
        background = BackgroundQuery(identity.get, lambda user: False, lambda value: value,
            lambda user, *args: [{'id': user['id']}], lambda: {}, lambda: lambda *args: None,
            lambda: self.root / 'backgrounds', lambda: {'.png'}, files=lambda: files)
        app.get('/api/backgrounds/{set_id}/{image_name}')(background.background_image)
        app.mount('/outputs', http.ArtifactStaticFiles(directory=self.root / 'outputs', runtime_provider=provider))
        return app, body, provider, identity

    def test_real_asgi_two_graphs_auth_range_and_context_cleanup(self):
        async def run():
            built = [self.app(i) for i in range(2)]
            async def exercise(index):
                app, body, provider, identity = built[index]
                paths = ['/api/incoming-text/references/a/asset/image', '/api/incoming-text/inspections/a/evidence/image',
                         '/api/backgrounds/a/image.png', '/outputs/users/a/image.png']
                async with AsyncClient(transport=ASGITransport(app), base_url='http://synthetic') as client:
                    for path in paths:
                        provider.reset_mock()
                        self.assertEqual((await client.get(path)).status_code, 401)
                        self.assertEqual((await client.get(path, headers={'x-owner': 'b'})).status_code, 404)
                        if path.startswith('/api/'):
                            self.assertEqual((await client.get(path, headers={'x-owner': 'a', 'x-blocked': '1'})).status_code, 403)
                        provider.assert_not_called()
                        response = await client.get(path, headers={'x-owner': 'a'})
                        self.assertEqual((response.status_code, response.content), (200, body))
                        self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
                        partial = await client.get(path, headers={'x-owner': 'a', 'range': 'bytes=2-4'})
                        self.assertEqual((partial.status_code, partial.content), (206, body[2:5]))
                    head = await client.head(paths[-1], headers={'x-owner': 'a'})
                    self.assertEqual((head.status_code, head.content, head.headers['content-length']), (200, b'', str(len(body))))
                    unchanged = await client.get(paths[-1], headers={'x-owner': 'a', 'if-none-match': head.headers['etag']})
                    self.assertEqual(unchanged.status_code, 304)
                self.assertIsNone(identity.get())
            await asyncio.gather(exercise(0), exercise(1))
        asyncio.run(run()); self.default.assert_not_called()

    def test_explicit_falsey_files_and_omitted_default_compatibility(self):
        class Files:
            def __bool__(self): raise AssertionError('files truthiness read')
            def runtime(self, path): return None
        local = Mock(return_value=object()); path = Path('synthetic.txt')
        result = http.file_response(path, local_factory=local, files=Files(), filename='shown.txt')
        self.assertIs(result, local.return_value); local.assert_called_once_with(path, filename='shown.txt')
        self.default.assert_not_called()
        for _ in range(2):
            default_files = Mock(); default_files.runtime.return_value = None
            with patch.object(http, 'BusinessFiles', return_value=default_files) as constructor:
                http.file_response(path, local_factory=local)
                constructor.assert_called_once_with(); default_files.runtime.assert_called_once_with(path)

    def test_registration_failure_is_before_routes_and_isolation_is_lazy(self):
        for register, args in [(register_catalog, (None,)), (register_inspections, (None, None))]:
            app = create_http_application({}).app
            with self.assertRaises(TypeError): register(app, *args, files=None)
            self.assertEqual(app.routes, [])
            poison = Mock(side_effect=AssertionError('construction touched storage'))
            register(app, *args, files=poison); poison.assert_not_called()
        self.default.assert_not_called()

    def test_response_keeps_selected_generation_when_provider_changes(self):
        one, two = [BusinessFiles(lambda runtime=runtime: runtime) for runtime in self.runtimes]
        path = self.root / 'outputs/users/a/image.png'
        one.write_bytes(path, b'first'); two.write_bytes(path, b'second')
        slot = [self.runtimes[0]]; files = BusinessFiles(lambda: slot[0])
        response = http.file_response(path, files=files)
        slot[0] = self.runtimes[1]
        self.assertIs(response.runtime, self.runtimes[0]); self.assertEqual(response.artifact.size, 5)
        self.default.assert_not_called()

    def test_actual_entry_media_storage_keywords(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse(read_checked_application_source(root / 'local_inspection_service/server.py', encoding='utf-8'))
        selected = {'create_http_application': ('upload_runtime_provider', 'lambda: _business_files.runtime_provider()'),
            'ArtifactStaticFiles': ('runtime_provider', 'lambda: _business_files.runtime_provider()'),
            'BackgroundQuery': ('files', 'lambda: _business_files')}
        seen = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id not in selected: continue
            key, source = selected[node.func.id]; values = [kw.value for kw in node.keywords if kw.arg == key]
            self.assertEqual(len(values), 1); self.assertEqual(ast.dump(values[0]), ast.dump(ast.parse(source, mode='eval').body))
            seen.append(node.func.id)
        self.assertCountEqual(seen, selected)
        owner = ast.parse((root / 'local_inspection_service/text_inspection/incoming_composition.py').read_text(encoding='utf-8'))
        registrations = [n for n in ast.walk(owner) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {'register_catalog', 'register_inspections'}]
        self.assertCountEqual([n.func.id for n in registrations], ['register_catalog', 'register_inspections'])
        for node in registrations:
            values = [kw.value for kw in node.keywords if kw.arg == 'files']
            self.assertEqual(len(values), 1)
            self.assertEqual(ast.dump(values[0]), ast.dump(ast.parse('lambda: self.files', mode='eval').body))
        builders = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'IncomingWorkflows']
        self.assertEqual(len(builders), 1)
        self.assertEqual(ast.unparse(next(kw.value for kw in builders[0].keywords if kw.arg == 'files')), '_business_files')
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == '_incoming_workflows']
        self.assertCountEqual([n.func.attr for n in calls], ['register_catalog', 'register_inspections'])


    def test_explicit_none_files_fails_closed_in_real_asgi(self):
        path = self.root / 'outputs/users/a/image.png'
        with self.assertRaises(TypeError): http.file_response(path, files=None)
        async def run():
            app = create_http_application({}).app; events = []
            def selected(*args): events.append('authorized-path'); return path
            def missing(): events.append('missing-files'); return None
            register_catalog(app, SimpleNamespace(get_incoming_text_reference_asset=selected), files=missing)
            register_inspections(app, None, SimpleNamespace(get_incoming_text_inspection_evidence=selected), files=missing)
            async with AsyncClient(transport=ASGITransport(app, raise_app_exceptions=False), base_url='http://synthetic') as client:
                for route in ['/api/incoming-text/references/a/asset/image', '/api/incoming-text/inspections/a/evidence/image']:
                    events.clear(); response = await client.get(route)
                    self.assertEqual(response.status_code, 500)
                    self.assertEqual(events, ['authorized-path', 'missing-files'])
        asyncio.run(run()); self.default.assert_not_called()


    def test_incoming_callees_are_selected_before_later_dependency_callbacks(self):
        events = []; path = Path('synthetic-local.png')
        first_factory = Mock(side_effect=lambda *args, **kwargs: events.append('first-factory') or 'selected response')
        late_factory = Mock(side_effect=AssertionError('late local factory selected'))
        late_response = Mock(side_effect=AssertionError('late response function selected'))
        def authorized(*args):
            events.append('authorized-path'); incoming_api.file_response = late_response
            return path
        files = BusinessFiles(lambda: None)
        def selected_files():
            events.append('files'); incoming_api.FileResponse = late_factory
            return files
        app = create_http_application({}).app
        route = register_catalog(app, SimpleNamespace(get_incoming_text_reference_asset=authorized), files=selected_files)
        with patch.object(incoming_api, 'file_response', http.file_response), patch.object(incoming_api, 'FileResponse', first_factory):
            result = route.get_incoming_text_reference_asset('a', 'image')
        self.assertEqual(result, 'selected response')
        self.assertEqual(events, ['authorized-path', 'files', 'first-factory'])
        first_factory.assert_called_once_with(path); late_factory.assert_not_called(); late_response.assert_not_called()
        self.default.assert_not_called()


if __name__ == '__main__': unittest.main()
