"""Detection media graph isolation with synthetic objects, models and video frames."""
import asyncio
import ast
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import io
from pathlib import Path
import shutil
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import cv2
import numpy as np
from fastapi import UploadFile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import smoke_detection_artifact_ports as fixtures
from local_inspection_service.detection.image_encoding import ImageEncoding
from local_inspection_service.detection.inspection_image_store import InspectionImageStore
from local_inspection_service.detection.reference_sheet import ReferenceSheet
from local_inspection_service.detection.reference_images import ReferenceTileRenderer
from local_inspection_service.detection.media_ports import InspectionImagePolicy, ReferenceSheetPolicy, ReferenceSheetCache, ReferenceSheetImages
from local_inspection_service.detection.local_models import LocalModels
from local_inspection_service.detection.video_upload import VideoUpload
from local_inspection_service.detection.upload_ports import UploadAccess, UploadPaths, VideoResults
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable


class DetectionMediaPortsTests(unittest.TestCase):
    setUp = fixtures.DetectionArtifactPortsTests.setUp

    def graph(self, index):
        runtime = self.runtimes[index]; provider = lambda: runtime
        files = BusinessFiles(provider)
        encoding = ImageEncoding(lambda: cv2, RuntimeError,
            lambda image, **options: encoding.image_bgr_data_url(image, **options), runtime_provider=provider)
        image_store = InspectionImageStore(lambda: cv2,
            InspectionImagePolicy(lambda: self.root / 'outputs/inspection', lambda: 100, lambda: 90),
            lambda: 123, lambda value: value, runtime_provider=provider)
        renderer = ReferenceTileRenderer(lambda: cv2, lambda: np)
        lock = threading.RLock(); cache = {}
        sheet = ReferenceSheet(lambda: lambda value, limit: str(value)[:limit],
            lambda kind: self.root / 'outputs/sheets',
            ReferenceSheetPolicy(lambda: {'.png'}, lambda: 'sheet', lambda: 83, lambda: 1400),
            ReferenceSheetCache(lambda: lock, lambda: cache),
            ReferenceSheetImages(lambda: cv2, lambda: np, renderer.fit_image_into_cell, lambda: encoding.image_path_data_url),
            files=lambda: files)
        return files, encoding, image_store, sheet

    def test_two_media_graphs_same_names_read_write_and_cache_independently(self):
        def run(index):
            files, encoding, image_store, sheet = self.graph(index)
            pixels = np.full((8, 12, 3), 30 + index * 150, dtype=np.uint8)
            source = self.root / 'uploads/reference.png'
            files.write_bytes(source, cv2.imencode('.png', pixels)[1].tobytes())
            uri = encoding.image_path_data_url(source)
            encoded = base64.b64decode(uri.split(',', 1)[1])
            np.testing.assert_array_equal(cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_COLOR), pixels)
            path = image_store.write_mcp_inspection_image(pixels, 'same')
            self.assertIsNotNone(path); self.assertFalse(path.exists())
            required = [{'accessory_id': 'same', 'name': 'same', 'profile': {'reference_images': [{'source_path': str(source), 'sha256': 'same-synthetic-reference-key'}]}}]
            first = sheet.build_reference_sheet_descriptor(required)
            self.assertEqual(first, sheet.build_reference_sheet_descriptor(required))
            self.assertFalse(Path(first['source_path']).is_file())
            self.assertEqual(files.read_bytes(path), cv2.imencode('.jpg', pixels, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes())
            return first
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(run, range(2)))
        self.assertEqual(first['source_path'], second['source_path'])
        self.assertNotEqual(first['data_url'], second['data_url']); self.poison.assert_not_called()

    def test_model_factories_receive_only_their_pinned_bytes_and_release_paths(self):
        def run(index):
            files, _, _, _ = self.graph(index)
            model_path = self.root / 'training_tasks/same.pt'; payload = ('synthetic-model-' + str(index)).encode()
            files.write_bytes(model_path, payload)
            opened = []
            def factory(path):
                opened.append(Path(path)); self.assertEqual(Path(path).read_bytes(), payload)
                return object()
            models = LocalModels(lambda model_id, config: {'id': model_id, 'path': model_path},
                lambda: factory, lambda: [], lambda *args: [], files=files)
            first = models.model('first')
            self.assertIs(first, models.model('alias'))
            self.assertEqual(len(opened), 1); self.assertFalse(opened[0].exists())
            self.assertFalse(model_path.exists())
            error = RuntimeError('synthetic model constructor failure'); failed_paths = []
            def failed_factory(path): failed_paths.append(Path(path)); raise error
            failed = LocalModels(lambda *args: {'id': 'failed', 'path': model_path},
                lambda: failed_factory, lambda: [], lambda *args: [], files=files)
            with self.assertRaises(RuntimeError) as caught: failed.model('failed')
            self.assertIs(caught.exception, error); self.assertFalse(failed_paths[0].exists())
            self.assertEqual(failed.models, {}); self.assertEqual(failed.paths, {})
            return first
        with ThreadPoolExecutor(max_workers=2) as pool: first, second = list(pool.map(run, range(2)))
        self.assertIsNot(first, second); self.poison.assert_not_called()

    def test_video_store_selection_and_materialization_cleanup_on_analysis_error(self):
        for index in range(2):
            files, _, _, _ = self.graph(index); payload = ('video-' + str(index)).encode()
            paths = []; captures = []
            def capture(path):
                path = Path(path); paths.append(path); self.assertEqual(path.read_bytes(), payload)
                cap = SimpleNamespace(isOpened=lambda: True, get=lambda key: 1,
                    read=Mock(side_effect=[(True, np.zeros((2, 2, 3), np.uint8)), (False, None)]), release=Mock())
                captures.append(cap); return cap
            error = RuntimeError('synthetic inference failure')
            service = VideoUpload(UploadAccess(lambda: None, lambda model: None),
                UploadPaths(lambda: lambda filename: 'same.avi', lambda: self.root / 'uploads'),
                lambda: shutil, lambda: {'video': {'sample_every_seconds': 1, 'max_frames': 2}},
                lambda: SimpleNamespace(VideoCapture=capture, CAP_PROP_FPS=1), Mock(side_effect=error),
                VideoResults(Mock(), Mock()), files=files)
            with self.assertRaises(RuntimeError) as caught:
                asyncio.run(service.analyze_video(UploadFile(file=io.BytesIO(payload), filename='same.avi'), None))
            self.assertIs(caught.exception, error); captures[0].release.assert_called_once()
            self.assertFalse(paths[0].exists()); self.assertEqual(files.read_bytes(self.root / 'uploads/same.avi'), payload)
            service.analyze = Mock(return_value={'passed': True, 'annotated_url': 'synthetic'})
            service.results = VideoResults(lambda result, index, fps: {'passed': result['passed']}, lambda frames: None)
            result = asyncio.run(service.analyze_video(UploadFile(file=io.BytesIO(payload), filename='same.avi'), None))
            self.assertEqual((result['passed'], result['sampled_frames'], result['passed_frames']), (True, 1, 1))
            captures[-1].release.assert_called_once(); self.assertFalse(paths[-1].exists())
            release_error = RuntimeError('synthetic capture release failure')
            def failed_release_capture(path):
                cap = capture(path); cap.release.side_effect = release_error; return cap
            service.videos = lambda: SimpleNamespace(VideoCapture=failed_release_capture, CAP_PROP_FPS=1)
            with self.assertRaises(RuntimeError) as caught:
                asyncio.run(service.analyze_video(UploadFile(file=io.BytesIO(payload), filename='same.avi'), None))
            self.assertIs(caught.exception, release_error); self.assertFalse(paths[-1].exists())
        self.poison.assert_not_called()

    def test_storage_failures_preserve_existing_exception_boundaries(self):
        files, encoding, image_store, sheet = self.graph(0)
        pixels = np.zeros((8, 8, 3), np.uint8)
        self.stores[0].client.fail = True
        with self.assertRaises(ArtifactUnavailable): image_store.write_mcp_inspection_image(pixels, 'failure')
        files2, _, healthy, _ = self.graph(1)
        self.assertIsNotNone(healthy.write_mcp_inspection_image(pixels, 'healthy'))
        error = RuntimeError('existing best effort failure')
        image_store.runtime_provider = Mock(side_effect=error)
        self.assertIsNone(image_store.write_mcp_inspection_image(pixels, 'ordinary-failure'))
        encoding.runtime_provider = Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as caught: encoding.image_path_data_url(self.root / 'uploads/missing.png')
        self.assertIs(caught.exception, error); self.poison.assert_not_called()

    def test_no_detection_component_constructs_default_storage_or_omits_runtime(self):
        root = Path(__file__).resolve().parents[1]
        for path in (root / 'local_inspection_service/detection').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name): continue
                self.assertNotIn(node.func.id, {'BusinessFiles', 'get_runtime'}, str(path))
                if node.func.id == 'image_backend': self.assertEqual(sum(k.arg == 'runtime_provider' for k in node.keywords), 1, str(path))
        tree = ast.parse((root / 'local_inspection_service/server.py').read_text(encoding='utf-8'))
        for name, key, expected in [('_image_encoding', 'runtime_provider', 'lambda: _business_files.runtime_provider()'),
            ('_inspection_image_store', 'runtime_provider', 'lambda: _business_files.runtime_provider()'),
            ('_reference_sheet', 'files', 'lambda: _business_files'), ('_local_models', 'files', '_business_files'), ('_video_upload', 'files', '_business_files')]:
            calls = [n.value for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
            self.assertEqual(len(calls), 1)
            actual = [kw.value for kw in calls[0].keywords if kw.arg == key]
            self.assertEqual(len(actual), 1)
            self.assertEqual(ast.dump(actual[0]), ast.dump(ast.parse(expected, mode='eval').body))


    def test_model_lease_exit_failure_preserves_existing_partial_cache(self):
        error = RuntimeError('synthetic lease exit failure'); created = object()
        @contextmanager
        def lease(path):
            yield path
            raise error
        files = SimpleNamespace(runtime_provider=lambda: object(), is_file=lambda path: True, local_file=lease)
        factory = Mock(return_value=created)
        models = LocalModels(lambda *args: {'id': 'same', 'path': self.root / 'training_tasks/same.pt'},
            lambda: factory, lambda: [], lambda *args: [], files=files)
        with self.assertRaises(RuntimeError) as caught: models.model('same')
        self.assertIs(caught.exception, error)
        self.assertEqual(models.models, {'same': created}); self.assertEqual(models.paths, {})
        self.assertIs(models.model('same'), created); factory.assert_called_once()

    def test_actual_root_object_and_supplier_binding_difference(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / 'local_inspection_service/server.py').read_text(encoding='utf-8'))
        first, second = BusinessFiles(lambda: self.runtimes[0]), BusinessFiles(lambda: self.runtimes[1])
        for name, key, lazy in [('_local_models', 'files', False), ('_video_upload', 'files', False),
                               ('_reference_sheet', 'files', True), ('_image_encoding', 'runtime_provider', True),
                               ('_inspection_image_store', 'runtime_provider', True)]:
            call = next(n.value for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
            expr = next(kw.value for kw in call.keywords if kw.arg == key)
            bindings = {'_business_files': first}
            supplied = eval(compile(ast.Expression(expr), '<actual media binding>', 'eval'), bindings)
            bindings['_business_files'] = second
            self.assertIs(supplied() if lazy else supplied,
                self.runtimes[1] if key == 'runtime_provider' else second if lazy else first)


if __name__ == '__main__': unittest.main()
