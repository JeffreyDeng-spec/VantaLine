"""Explicit detection storage ownership using real stores and synthetic object clients."""
import asyncio
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import cv2
import numpy as np
from fastapi import UploadFile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import smoke_artifact_storage as storage_fixture
from smoke_detection_analysis import AnalysisFixture
from local_inspection_service.detection.image_upload import ImageUpload
from local_inspection_service.detection.upload_ports import UploadAccess, UploadPaths
from local_inspection_service.detection.annotation import DetectionAnnotation, normalize_ai_box_2d
from local_inspection_service.detection.analysis import DetectionAnalysis
from local_inspection_service.detection.analysis_ports import AnalysisInput, AnalysisRouting, AnalysisInference, AnalysisOutput
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.runtime import ArtifactRuntime
from local_inspection_service.storage.artifacts import images
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable


def annotation(root, provider, pixels):
    return DetectionAnnotation(normalize_ai_box_2d, Mock(), Mock(), lambda: cv2,
        lambda kind: root / 'outputs', lambda path: path.name,
        lambda *args: pixels, Mock(), runtime_provider=provider)


def analysis(root, provider, pixels):
    f = AnalysisFixture(root)
    service = DetectionAnalysis(
        AnalysisInput(f.load, lambda: f.scope, f.selected, lambda: f.sanitize, f.state_load),
        AnalysisRouting(Mock(), f.ai, f.retired, lambda: f.text),
        AnalysisInference(lambda: f.model, f.device, f.parse, f.ocr, f.apply, f.draw),
        AnalysisOutput(lambda kind: root / 'outputs', lambda: lambda *args: pixels,
                       lambda: 640, lambda: cv2, lambda: 87, f.url), runtime_provider=provider)
    return service, f


class DetectionArtifactPortsTests(unittest.TestCase):
    def setUp(self):
        self.stores = []
        for _ in range(2):
            fixture = storage_fixture.StorageTests()
            fixture.setUp()
            self.addCleanup(fixture.tearDown)
            fixture.budget.limits.update(upload=1000000, cache=1000000)
            fixture.budget.free_bytes = lambda: 10000000
            self.stores.append(fixture)
        # Identical logical AND absolute business names expose cross-composition leakage.
        self.root = self.stores[0].root
        self.runtimes = [ArtifactRuntime(f.store, self.root, 'cos') for f in self.stores]
        self.poison = Mock(side_effect=AssertionError('process-default runtime leaked'))
        p = patch.object(images, 'get_runtime', self.poison)
        p.start(); self.addCleanup(p.stop)

    def test_concurrent_upload_annotation_and_analysis_keep_stores_separate(self):
        def run(index):
            runtime = self.runtimes[index]
            provider = lambda: runtime
            files = BusinessFiles(provider)
            pixels = np.full((8, 12, 3), 40 + index * 120, dtype=np.uint8)
            payload = cv2.imencode('.png', pixels)[1].tobytes()
            analyzed = []
            def inspect(image, request_id, model_id, *, image_path):
                self.assertEqual(files.read_bytes(image_path), payload)
                np.testing.assert_array_equal(image, pixels)
                analyzed.append(request_id)
                return {'saved': True}
            service = ImageUpload(UploadAccess(lambda: None, lambda model: None),
                UploadPaths(lambda: lambda filename: 'same.png', lambda: self.root / 'uploads'),
                lambda: np, lambda: cv2, inspect, files=lambda: files)
            result = asyncio.run(service.analyze_image(UploadFile(file=io.BytesIO(payload), filename='same.png'), None))
            self.assertEqual(result, {'saved': True}); self.assertEqual(analyzed, ['same'])
            a = annotation(self.root, provider, pixels)
            a.write_ai_original_output(pixels, 'same')
            a.write_ai_annotated_output(pixels, 'same', [], {})
            ordinary, fixture = analysis(self.root, provider, pixels)
            ordinary.analyze_bgr(pixels, 'same')
            expected = {'uploads/same.png': payload}
            for name, quality in [('same_ai_original.jpg', 92), ('same_ai_annotated.jpg', 92), ('same_annotated.jpg', 87)]:
                expected['outputs/' + name] = cv2.imencode('.jpg', pixels, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()
            for key, content in expected.items():
                self.assertEqual(runtime.store.stat(key).sha256, hashlib.sha256(content).hexdigest())
                self.assertFalse((self.root / key).exists())
            return {key: runtime.store.stat(key).sha256 for key in expected}
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(run, range(2)))
        self.assertEqual(first.keys(), second.keys())
        self.assertTrue(all(first[key] != second[key] for key in first))
        self.poison.assert_not_called()

    def test_storage_failure_stops_analysis_and_never_falls_back_to_disk(self):
        runtime = self.runtimes[0]; files = BusinessFiles(lambda: runtime)
        self.stores[0].client.fail = True
        pixels = np.zeros((8, 8, 3), dtype=np.uint8)
        payload = cv2.imencode('.png', pixels)[1].tobytes(); inspect = Mock()
        service = ImageUpload(UploadAccess(lambda: None, lambda model: None),
            UploadPaths(lambda: lambda filename: 'same.png', lambda: self.root / 'uploads'),
            lambda: np, lambda: cv2, inspect, files=lambda: files)
        with self.assertRaises(ArtifactUnavailable):
            asyncio.run(service.analyze_image(UploadFile(file=io.BytesIO(payload), filename='same.png'), None))
        inspect.assert_not_called()
        a = annotation(self.root, lambda: runtime, pixels)
        with self.assertRaises(ArtifactUnavailable): a.write_ai_original_output(pixels, 'same')
        ordinary, fixture = analysis(self.root, lambda: runtime, pixels)
        with self.assertRaises(ArtifactUnavailable): ordinary.analyze_bgr(pixels, 'same')
        fixture.url.assert_not_called()
        self.assertEqual(self.stores[0].locations.rows, {})
        self.assertFalse((self.root / 'uploads/same.png').exists())
        self.assertFalse((self.root / 'outputs/same_annotated.jpg').exists())
        self.poison.assert_not_called()

    def test_required_dependencies_fail_at_composition(self):
        for invalid in (None, False, 0):
            with self.subTest(dependency=invalid):
                with self.assertRaises(TypeError): ImageUpload(None, None, None, None, None, files=invalid)
                with self.assertRaises(TypeError): DetectionAnalysis(None, None, None, None, runtime_provider=invalid)
                with self.assertRaises(TypeError): DetectionAnnotation(None, None, None, None, None, None, None, None, runtime_provider=invalid)
        with self.assertRaises(TypeError): ImageUpload(None, None, None, None, None)
        with self.assertRaises(TypeError): DetectionAnalysis(None, None, None, None)

    def test_falsey_provider_and_local_backend_identity(self):
        class Provider:
            calls = 0
            def __bool__(self): raise AssertionError('provider truthiness read')
            def __call__(self): self.calls += 1; return None
        provider = Provider(); backend = object()
        self.assertIs(images.image_backend(backend, runtime_provider=provider), backend)
        self.assertEqual(provider.calls, 1); self.poison.assert_not_called()

    def test_provider_failure_identity_and_default_late_binding(self):
        error = RuntimeError('synthetic selection failure')
        provider = Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as caught:
            images.image_backend(object(), runtime_provider=provider)
        self.assertIs(caught.exception, error); provider.assert_called_once(); self.poison.assert_not_called()
        backend = object()
        with patch.object(images, 'get_runtime', return_value=None) as local:
            self.assertIs(images.image_backend(backend), backend); local.assert_called_once()
        with patch.object(images, 'get_runtime', return_value=self.runtimes[0]) as remote:
            selected = images.image_backend(backend)
            self.assertIs(selected.backend, backend)
            self.assertIs(selected.files.files.runtime_provider(), self.runtimes[0]); remote.assert_called_once()

    def test_upload_reselects_files_after_decode(self):
        pixels = np.zeros((1, 1, 3), dtype=np.uint8)
        first, second = SimpleNamespace(write_bytes=Mock()), SimpleNamespace(write_bytes=Mock())
        slot = [first]
        def decode(*args): slot[0] = second; return pixels
        decoder = SimpleNamespace(imdecode=decode, IMREAD_COLOR=1)
        service = ImageUpload(UploadAccess(lambda: None, lambda model: None),
            UploadPaths(lambda: lambda filename: 'same.png', lambda: self.root / 'uploads'),
            lambda: np, lambda: decoder, Mock(return_value={}), files=lambda: slot[0])
        asyncio.run(service.analyze_image(UploadFile(file=io.BytesIO(b'bytes'), filename='same.png'), None))
        first.write_bytes.assert_not_called()
        second.write_bytes.assert_called_once_with(self.root / 'uploads/same.png', b'bytes')


    def test_unused_output_paths_do_not_resolve_runtime(self):
        provider = Mock(side_effect=AssertionError('unused storage provider'))
        a = annotation(self.root, provider, None)
        a.original = Mock(return_value='original')
        self.assertEqual(a.write_ai_annotated_output(None, 'same', [], {}), 'original')
        ordinary, fixture = analysis(self.root, provider, None)
        fixture.spec = {'id': 'ai', 'is_ai_detection': True}
        self.assertIs(ordinary.analyze_bgr(None, 'same'), fixture.ai_result)
        fixture.spec = {'id': 'retired', 'is_label_sheet_match': True}
        fixture.retired.side_effect = LookupError('retired')
        with self.assertRaises(LookupError): ordinary.analyze_bgr(None, 'same')
        provider.assert_not_called()

    def test_selected_runtime_is_pinned_before_write_arguments(self):
        slot = [self.runtimes[0]]; events = []
        class Backend:
            @property
            def IMWRITE_JPEG_QUALITY(inner):
                events.append('quality'); slot[0] = self.runtimes[1]
                return cv2.IMWRITE_JPEG_QUALITY
            def __getattr__(inner, name): return getattr(cv2, name)
        def provider(): events.append('runtime'); return slot[0]
        pixels = np.zeros((8, 8, 3), dtype=np.uint8)
        a = annotation(self.root, provider, pixels); a.images = lambda: Backend()
        a.write_ai_original_output(pixels, 'same')
        self.assertEqual(events, ['runtime', 'quality'])
        self.assertIsNotNone(self.stores[0].locations.get('outputs/same_ai_original.jpg'))
        self.assertEqual(self.stores[1].locations.rows, {})
        # Failure of one composition must not poison the second graph.
        self.stores[0].client.fail = True
        with self.assertRaises(ArtifactUnavailable):
            annotation(self.root, lambda: self.runtimes[0], pixels).write_ai_original_output(pixels, 'failed')
        annotation(self.root, lambda: self.runtimes[1], pixels).write_ai_original_output(pixels, 'healthy')
        self.assertIsNotNone(self.stores[1].locations.get('outputs/healthy_ai_original.jpg'))

    def test_upload_permission_and_provider_failure_order(self):
        pixels = np.zeros((1, 1, 3), dtype=np.uint8); events = []
        error = RuntimeError('synthetic port unavailable')
        def provider(): events.append('files'); raise error
        decoder = SimpleNamespace(imdecode=lambda *args: events.append('decode') or pixels, IMREAD_COLOR=1)
        analyze = Mock()
        service = ImageUpload(UploadAccess(lambda: events.append('ensure'), lambda model: events.append('permission')),
            UploadPaths(lambda: lambda filename: events.append('name') or 'same.png', lambda: events.append('directory') or self.root),
            lambda: np, lambda: decoder, analyze, files=provider)
        class Upload:
            filename = 'same.png'
            async def read(inner): events.append('read'); return b'bytes'
        with self.assertRaises(RuntimeError) as caught: asyncio.run(service.analyze_image(Upload(), None))
        self.assertIs(caught.exception, error)
        self.assertEqual(events, ['ensure', 'permission', 'read', 'decode', 'name', 'directory', 'files'])
        analyze.assert_not_called()
        events.clear()
        service.access = UploadAccess(lambda: None, Mock(side_effect=PermissionError('denied')))
        with self.assertRaises(PermissionError): asyncio.run(service.analyze_image(Upload(), None))
        self.assertEqual(events, [])


    def test_actual_entry_suppliers_are_explicit_and_late_bound(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / 'local_inspection_service/server.py').read_text(encoding='utf-8'))
        from application_integration_source_contract import verify_actual_compositions
        verify_actual_compositions()
        assignments = {target.id:node.value for node in tree.body if isinstance(node,ast.Assign)
                       for target in node.targets if isinstance(target,ast.Name)}
        self.assertEqual(ast.dump(assignments['_detection_analysis']),ast.dump(ast.parse('_detection_workflows.detection',mode='eval').body))
        owner_tree = ast.parse((root/'local_inspection_service/detection/workflow_composition.py').read_text())
        actual = [node for node in ast.walk(owner_tree) if isinstance(node,ast.Call)
                  and isinstance(node.func,ast.Name) and node.func.id=='DetectionAnalysis']
        self.assertEqual(len(actual),1)
        self.assertEqual(ast.dump(next(kw.value for kw in actual[0].keywords if kw.arg=='runtime_provider')),
                         ast.dump(ast.parse('runtime_provider',mode='eval').body))
        for name, keyword, expected in [
            ('_image_upload', 'files', 'lambda: _business_files'),
            ('_detection_annotation', 'runtime_provider', 'lambda: _business_files.runtime_provider()'),
            ('_detection_workflows', 'runtime_provider', 'lambda: _business_files.runtime_provider()'),
        ]:
            nodes = [node.value for node in tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
            self.assertEqual(len(nodes), 1)
            values = [kw.value for kw in nodes[0].keywords if kw.arg == keyword]
            self.assertEqual(len(values), 1)
            self.assertEqual(ast.dump(values[0]), ast.dump(ast.parse(expected, mode='eval').body))
            first = BusinessFiles(lambda: self.runtimes[0]); second = BusinessFiles(lambda: self.runtimes[1])
            bindings = {'_business_files': first}
            provider = eval(compile(ast.Expression(values[0]), '<actual composition supplier>', 'eval'), bindings)
            self.assertIs(provider(), first if keyword == 'files' else self.runtimes[0])
            bindings['_business_files'] = second
            self.assertIs(provider(), second if keyword == 'files' else self.runtimes[1])


if __name__ == '__main__': unittest.main()
