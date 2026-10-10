"""Training pixels and YAML remain owned by explicitly composed artifact stores."""
import ast
from concurrent.futures import ThreadPoolExecutor
import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
import smoke_detection_artifact_ports as fixtures
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.images import ImageFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable
from local_inspection_service.training import annotations, preview_renderer
from local_inspection_service.training.annotations import AnnotationPreview, write_dataset_yaml
from local_inspection_service.training.preview_renderer import PreviewRenderer
from local_inspection_service.training.preview_ports import PreviewSurface


class TrainingImagePortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)
        self.default = Mock(side_effect=AssertionError('implicit image dependency'))
        for module in (annotations, preview_renderer):
            p = patch.object(module, 'ImageFiles', self.default, create=True); p.start(); self.addCleanup(p.stop)

    def graph(self, index):
        files = BusinessFiles(lambda: self.runtimes[index]); images = ImageFiles(lambda: cv2, files=files)
        pixels = np.full((32, 48, 3), 40 + index * 120, np.uint8)
        public = Mock(return_value='/synthetic/image')
        renderer = PreviewRenderer(Mock(), PreviewSurface(lambda *args: (pixels.copy(), {'id': str(index)}), public),
            Mock(), Mock(), Mock(), Mock(), Mock(), images=images)
        annotation = AnnotationPreview(public, images=images)
        return files, images, pixels, public, renderer, annotation

    def test_two_stores_publish_distinct_preview_and_annotation_pixels_and_yaml_at_same_paths(self):
        def run(index):
            files, images, pixels, public, renderer, annotation = self.graph(index)
            preview = self.root / 'outputs/same.png'; annotated = self.root / 'outputs/same.jpg'
            result = renderer.draw_training_preview([], preview, 41)
            self.assertEqual(result['background'], {'id': str(index)}); self.assertEqual(result['labels'], [])
            self.assertEqual(annotation.write_training_annotation_preview(preview, [], annotated), '/synthetic/image')
            np.testing.assert_array_equal(images.imread(str(preview), cv2.IMREAD_COLOR), pixels)
            self.assertEqual(files.read_bytes(annotated), cv2.imencode('.jpg', pixels, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes())
            yaml = self.root / 'outputs/dataset.yaml'; write_dataset_yaml(yaml, self.root / 'outputs', ['part ' + str(index)], files=files)
            self.assertIn('  0: part_' + str(index) + '\n', files.read_text(yaml, encoding='utf-8'))
            for path in (preview, annotated, yaml): self.assertFalse(path.exists())
            return files.read_bytes(preview)
        with ThreadPoolExecutor(max_workers=2) as pool: bodies = list(pool.map(run, range(2)))
        self.assertNotEqual(*bodies); self.default.assert_not_called()

    def test_failed_publication_keeps_source_and_prevents_public_link_without_retry(self):
        files, images, pixels, public, renderer, annotation = self.graph(0)
        source = self.root / 'outputs/source.png'; images.imwrite(str(source), pixels)
        failure = ArtifactUnavailable('synthetic publication failure')
        with patch.object(self.runtimes[0].store, 'put_bytes', side_effect=failure) as writes:
            for action in (lambda: renderer.draw_training_preview([], self.root / 'outputs/preview.png', 41),
                           lambda: annotation.write_training_annotation_preview(source, [], self.root / 'outputs/annotation.jpg'),
                           lambda: write_dataset_yaml(self.root / 'outputs/dataset.yaml', self.root, ['part'], files=files)):
                with self.assertRaises(ArtifactUnavailable) as caught: action()
                self.assertIs(caught.exception, failure)
            self.assertEqual(writes.call_count, 3)
        public.assert_not_called(); self.assertTrue(files.exists(source))
        self.assertFalse(BusinessFiles(lambda: self.runtimes[1]).exists(source))

    def test_missing_source_retains_empty_result_while_remote_failure_propagates(self):
        files, images, pixels, public, renderer, annotation = self.graph(0)
        source = self.root / 'outputs/source.png'; output = self.root / 'outputs/annotation.jpg'
        self.assertEqual(annotation.write_training_annotation_preview(source, [], output), '')
        images.imwrite(str(source), pixels)
        with patch.object(self.runtimes[0].store.cache, 'open', side_effect=ArtifactUnavailable('synthetic read')):
            with self.assertRaises(ArtifactUnavailable): annotation.write_training_annotation_preview(source, [], output)
        public.assert_not_called(); self.assertFalse(files.exists(output))

    def test_false_write_still_returns_link_and_selected_callee_precedes_filename_effects(self):
        first = Mock(return_value=False); later = Mock(side_effect=AssertionError('callee reselected'))
        images = Mock(); images.imwrite = first
        renderer = PreviewRenderer(Mock(), PreviewSurface(lambda *args: (np.zeros((8, 8, 3), np.uint8), {}), lambda path: 'linked'),
            Mock(), Mock(), Mock(), Mock(), Mock(), images=images)
        class Name:
            def __str__(self): images.imwrite = later; return '/synthetic/name.png'
        result = renderer.draw_training_preview([], Name(), 7)
        self.assertEqual(result['url'], 'linked'); first.assert_called_once(); later.assert_not_called()

    def test_required_falsey_dependencies_and_root_bindings(self):
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness checked')
        for cls in (AnnotationPreview, PreviewRenderer):
            args = {k: Mock() for k in inspect.signature(cls).parameters if k != 'images'}
            with self.assertRaises(TypeError): cls(**args)
            with self.assertRaises(TypeError): cls(**args, images=None)
            port = Falsey(); self.assertIs(cls(**args, images=port).images, port)
        with self.assertRaises(TypeError): write_dataset_yaml(Path('unused'), Path('unused'), [])
        with self.assertRaises(TypeError): write_dataset_yaml(Path('unused'), Path('unused'), [], files=None)
        root = Path(__file__).resolve().parents[1]; tree = ast.parse(read_checked_application_source(root / 'local_inspection_service/server.py', encoding='utf-8'))
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'AnnotationPreview', 'PreviewRenderer'}:
                values = [kw.value for kw in node.keywords if kw.arg == 'images']; self.assertEqual(len(values), 1)
                self.assertEqual(ast.dump(values[0]), ast.dump(ast.parse('_training_image_io', mode='eval').body)); found.append(node.func.id)
        self.assertCountEqual(found, ['AnnotationPreview', 'PreviewRenderer'])
        wrapper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'write_dataset_yaml')
        self.assertEqual(ast.dump(wrapper), ast.dump(ast.parse('def write_dataset_yaml(path: Path, dataset_dir: Path, names: list[str]) -> None:\n    return _write_dataset_yaml(path, dataset_dir, names, files=_business_files)').body[0]))


if __name__ == '__main__': unittest.main()
