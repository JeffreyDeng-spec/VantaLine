"""Real incoming workflows use explicit stores; OCR and object transport are synthetic."""
import asyncio
import ast
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import cv2
import httpx
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
import smoke_detection_artifact_ports as stores
from smoke_incoming_text_workflows import Fixture, Upload, RULE
from local_inspection_service.auth.middleware import SecurityDependencies, register_security_middleware
from local_inspection_service.runtime.identity import RequestIdentity
from local_inspection_service.runtime.http_application import create_http_application
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.images import ImageFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable
from local_inspection_service.text_inspection.incoming_api import register_catalog, register_inspections
from local_inspection_service.text_inspection import incoming_catalog, incoming_execution, incoming_reviews, incoming_retention


class IncomingArtifactPortsTests(unittest.TestCase):
    def setUp(self):
        stores.DetectionArtifactPortsTests.setUp(self)
        self.default = Mock(side_effect=AssertionError('implicit incoming storage'))
        for module in (incoming_catalog, incoming_execution, incoming_reviews, incoming_retention):
            for name in ('_business_files', '_image_files'):
                p = patch.object(module, name, self.default, create=True); p.start(); self.addCleanup(p.stop)

    def graph(self, index):
        f = Fixture(self); f.root = self.root / 'outputs'
        f.files = BusinessFiles(lambda: self.runtimes[index]); f.images = ImageFiles(lambda: cv2, files=f.files)
        for name in ('catalog', 'reviews', 'execution', 'retention'):
            old = getattr(f, name); deps = dict(vars(old)); deps['files'] = f.files
            if 'images' in deps: deps['images'] = f.images
            setattr(f, name, type(old)(**deps))
        return f

    def payload(self, index):
        pixels = np.full((320, 320, 3), 40 + index * 120, np.uint8)
        return cv2.imencode('.png', pixels)[1].tobytes()

    def app(self, f):
        identity = RequestIdentity(); f.context = SimpleNamespace(get=lambda: identity.get()['id'])
        app = create_http_application({}).app
        def authenticate(request, **options):
            owner = request.headers.get('x-owner')
            perms = [] if request.headers.get('x-blocked') else ['inspection', 'incoming_material_config']
            return ({'id': owner, 'role': 'user', 'permissions': perms} if owner else None, {'users': True}, False)
        register_security_middleware(app, SecurityDependencies(authenticate, lambda store: True, identity,
            lambda *a: False, lambda *a: True, lambda *a: False))
        register_catalog(app, f.catalog, files=lambda: f.files)
        register_inspections(app, f.execution, f.reviews, files=lambda: f.files)
        return app, identity

    def test_two_real_workflows_http_authorization_evidence_and_retention_are_isolated(self):
        graphs = [self.graph(i) for i in range(2)]
        async def run(index):
            f = graphs[index]; app, identity = self.app(f); body = self.payload(index)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://synthetic') as client:
                headers = {'x-owner': 'alice'}
                response = await client.post('/api/incoming-text/tasks/task/references', headers=headers,
                    files={'file': ('standard.png', body)}, data={'version_label': 'v1'})
                self.assertEqual(response.status_code, 200, response.text)
                reference = f.state['references'][0]; reference['status'] = 'active'; reference['rules'] = [copy.deepcopy(RULE)]
                self.assertEqual(f.files.read_bytes(Path(reference['source_path'])), body)
                self.assertEqual(f.files.read_bytes(Path(reference['canonical_path'])), body)
                response = await client.post('/api/incoming-text/tasks/task/inspect', headers=headers,
                    files={'file': ('capture.png', body)}, data={'capture_id': 'capture-0001'})
                self.assertEqual(response.status_code, 200, response.text)
                record = f.state['inspections'][0]
                self.assertEqual(record['status'], 'completed'); self.assertEqual(record['auto_decision'], 'REVIEW_REQUIRED')
                for path in (response.json()['source_url'], response.json()['corrected_url'],
                             '/api/incoming-text/references/' + reference['id'] + '/asset/canonical'):
                    self.assertEqual((await client.get(path)).status_code, 401)
                    self.assertEqual((await client.get(path, headers={'x-owner': 'bob'})).status_code, 404)
                    self.assertEqual((await client.get(path, headers={**headers, 'x-blocked': '1'})).status_code, 403)
                    result = await client.get(path, headers=headers); self.assertEqual(result.status_code, 200)
                    expected = body if not path.endswith('/corrected') else f.files.read_bytes(Path(record['corrected_path']))
                    self.assertEqual(result.content, expected)
                    self.assertEqual((await client.get(path, headers={**headers, 'range': 'bytes=2-8'})).content, expected[2:9])
                source_path = Path(record['source_path']); self.assertFalse(source_path.exists())
                f.state['inspections'][0]['created_at'] = 1
                self.assertIsNone(identity.get())
                return source_path
        async def both(): return await asyncio.gather(run(0), run(1))
        with patch('uuid.uuid4', return_value=SimpleNamespace(hex='a' * 32)):
            paths = asyncio.run(both())
        self.assertEqual(paths[0], paths[1]); self.assertNotEqual(graphs[0].files.read_bytes(paths[0]), graphs[1].files.read_bytes(paths[1]))
        self.assertEqual(graphs[0].retention.purge(), {'records': 1, 'files': 3})
        self.assertFalse(graphs[0].files.exists(paths[0])); self.assertTrue(graphs[1].files.exists(paths[1]))
        self.assertNotIn('evidence_purged_at', graphs[1].state['inspections'][0]); self.default.assert_not_called(); self.poison.assert_not_called()

    def test_catalog_publication_failure_has_no_cross_store_or_local_fallback(self):
        graphs = [self.graph(i) for i in range(2)]
        self.stores[0].client.fail = True
        with self.assertRaises(ArtifactUnavailable): asyncio.run(graphs[0].catalog.create_incoming_text_reference('task', Upload(self.payload(0)), 'v1'))
        self.assertEqual(graphs[0].state['references'], [])
        result = asyncio.run(graphs[1].catalog.create_incoming_text_reference('task', Upload(self.payload(1)), 'v1'))
        self.assertEqual(result['version_label'], 'v1'); self.default.assert_not_called()

    def test_missing_dependencies_fail_at_construction_without_storage_access(self):
        f = self.graph(0)
        for name in ('catalog', 'reviews', 'execution', 'retention'):
            old = getattr(f, name)
            for dependency in ('files', 'images'):
                if dependency not in vars(old): continue
                for missing in (True, False):
                    deps = dict(vars(old))
                    if missing: del deps[dependency]
                    else: deps[dependency] = None
                    with self.assertRaises(TypeError): type(old)(**deps)
        self.default.assert_not_called()

    def test_falsey_explicit_dependencies_are_not_replaced(self):
        class Files:
            def __bool__(self): raise AssertionError('dependency truthiness used')
        f = self.graph(0); dependency = Files()
        for name in ('catalog', 'reviews', 'execution', 'retention'):
            old = getattr(f, name); deps = dict(vars(old)); deps['files'] = dependency
            if 'images' in deps: deps['images'] = dependency
            service = type(old)(**deps); self.assertIs(service.files, dependency)
            if 'images' in deps: self.assertIs(service.images, dependency)

    def test_actual_composition_uses_one_matching_files_images_graph(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse(read_checked_application_source(root / 'local_inspection_service/server.py', encoding='utf-8'))
        assignments = {n.targets[0].id: n.value for n in tree.body
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)}
        call = assignments['_incoming_workflows']
        self.assertEqual(ast.dump(call.func), ast.dump(ast.parse('IncomingWorkflows', mode='eval').body))
        keywords = {k.arg: k.value for k in call.keywords}
        for name, expression in [('storage', '_text_storage'), ('files', '_business_files'), ('images', '_incoming_image_files')]:
            self.assertEqual(ast.dump(keywords[name]), ast.dump(ast.parse(expression, mode='eval').body))
        self.assertEqual(ast.dump(assignments['_incoming_image_files']),
                         ast.dump(ast.parse('ImageFiles(lambda: cv2, files=_business_files)', mode='eval').body))
        for name in ('catalog', 'reviews', 'execution', 'retention'):
            self.assertEqual(ast.dump(assignments['_incoming_' + name]),
                             ast.dump(ast.parse('_incoming_workflows.' + name, mode='eval').body))
        builder = ast.parse((root / 'local_inspection_service/text_inspection/incoming_composition.py').read_text(encoding='utf-8'))
        found = set()
        for node in ast.walk(builder):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name): continue
            if node.func.id in {'IncomingCatalog', 'IncomingReviews', 'IncomingExecution', 'IncomingRetention'}:
                kwargs = {k.arg: k.value for k in node.keywords}
                self.assertEqual(ast.dump(kwargs['files']), ast.dump(ast.parse('files', mode='eval').body))
                if node.func.id in {'IncomingCatalog', 'IncomingExecution'}:
                    self.assertEqual(ast.dump(kwargs['images']), ast.dump(ast.parse('images', mode='eval').body))
                found.add(node.func.id)
            elif node.func.id == 'IncomingWrites':
                kwargs = {k.arg: k.value for k in node.keywords}
                self.assertEqual(ast.dump(kwargs['guard']), ast.dump(ast.parse('lambda: storage.lock', mode='eval').body))
                found.add(node.func.id)
        self.assertEqual(found, {'IncomingCatalog', 'IncomingReviews', 'IncomingExecution', 'IncomingRetention', 'IncomingWrites'})
        self.assertEqual(sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'IncomingWorkflows'
                             for n in ast.walk(tree)), 1)
        for name in ('catalog', 'reviews', 'execution', 'retention'):
            source = (root / f'local_inspection_service/text_inspection/incoming_{name}.py').read_text(encoding='utf-8')
            self.assertNotIn('BusinessFiles', source); self.assertNotIn('ImageFiles', source)


if __name__ == '__main__': unittest.main()
