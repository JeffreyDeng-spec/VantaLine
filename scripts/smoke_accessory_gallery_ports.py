"""Candidate/gallery storage ownership with synthetic providers and real adapters."""
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
from local_inspection_service.accessories import candidate_factory, gallery
from local_inspection_service.accessories.candidate_factory import CandidateFactory
from local_inspection_service.accessories.gallery import AccessoryGallery
from local_inspection_service.accessories.preparation_ports import CandidateMedia, CandidatePreparation, CandidateStorage
from local_inspection_service.accessories.gallery_ports import GalleryAssets, GalleryStorage, GalleryDisplay


class AccessoryGalleryPortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)
        self.default = Mock(side_effect=AssertionError('implicit gallery storage'))
        for module in (candidate_factory, gallery):
            p = patch.object(module, 'ImageFiles', self.default, create=True); p.start(); self.addCleanup(p.stop)

    def graph(self, index):
        files = BusinessFiles(lambda: self.runtimes[index]); images = ImageFiles(lambda: cv2, files=files)
        source = self.root / 'normalized_assets/source.png'; output = self.root / 'outputs/accessory_gallery/preview.png'
        pixels = np.full((20, 30, 4), 40 + index * 100, np.uint8); pixels[:, :, 3] = 255
        images.imwrite(str(source), pixels)
        events = []
        def stage(name):
            return lambda *args, **kwargs: events.append(name)
        def thumbnail(image, path, angle):
            events.append('thumbnail'); images.imwrite(str(path), image); return {'path': str(path)}
        factory = CandidateFactory(CandidateMedia(lambda identifier, sources: (sources, []), lambda kind: {}, lambda value: '', lambda: {'.png'}, lambda category: self.root / 'outputs' / category, thumbnail), CandidatePreparation(stage('defer'), stage('reference'), stage('profile'), stage('pose')), CandidateStorage(lambda: {'owner_id': str(index)}, lambda: self.root / 'accessory_candidates', lambda path, item: (events.append('save'), files.write_json(path, item))), images=images)
        projection = Mock(); projection.serialize_accessory.side_effect = lambda item: dict(item)
        service = AccessoryGallery(GalleryAssets(lambda item: [], lambda item: None, lambda item: [], lambda item: [{'output_path': str(output)}], Path, lambda item: []), GalleryStorage(lambda: self.root / 'outputs', lambda name: self.root / 'outputs' / name, lambda path: str(path)), GalleryDisplay(str, lambda item, path: {}, lambda: {}, lambda item, user: item), projection, files=files, images=images)
        return files, images, source, output, pixels, factory, service, events

    def test_candidate_and_gallery_pixels_stay_with_their_store(self):
        def run(index):
            files, images, source, output, pixels, factory, service, events = self.graph(index)
            item = factory.create_accessory_candidate('synthetic', 'text', 'target', [str(source)])
            self.assertEqual(events, ['defer', 'reference', 'profile', 'thumbnail', 'pose', 'save'])
            thumbnail = Path(item['thumbnails'][0]['path']); np.testing.assert_array_equal(images.imread(str(thumbnail), cv2.IMREAD_COLOR), pixels[:, :, :3])
            result = service.write_gallery_preview(source, output)
            self.assertEqual((result['width'], result['height']), (30, 20))
            np.testing.assert_array_equal(images.imread(str(output), cv2.IMREAD_COLOR), pixels[:, :, :3])
            self.assertEqual(files.read_json(self.root / 'accessory_candidates' / (item['id'] + '.json'))['owner_id'], str(index))
            self.assertFalse(source.exists()); self.assertFalse(output.exists()); return int(images.imread(str(output), cv2.IMREAD_COLOR).mean())
        with ThreadPoolExecutor(max_workers=2) as pool: values = list(pool.map(run, range(2)))
        self.assertEqual(values, [40, 140]); self.default.assert_not_called()

    def test_pose_existence_uses_gallery_owner(self):
        graphs = [self.graph(i) for i in range(2)]
        graphs[1][6].write_gallery_preview(graphs[1][2], graphs[1][3])
        item = {'id': 'synthetic', 'material_type': 'object'}
        self.assertEqual(graphs[0][6].accessory_detail_payload(item)['gallery'], [])
        self.assertEqual(graphs[1][6].accessory_detail_payload(item)['gallery'][0]['kind'], 'pose_collection')

    def test_remote_read_failure_preserves_candidate_preparation_order(self):
        files, images, source, output, pixels, factory, service, events = self.graph(0)
        failure = ArtifactUnavailable('synthetic source failure')
        with patch.object(self.runtimes[0].store.cache, 'open', side_effect=failure):
            with self.assertRaises(ArtifactUnavailable) as caught: factory.create_accessory_candidate('synthetic', 'text', 'target', [str(source)])
            self.assertIs(caught.exception, failure)
            with self.assertRaises(ArtifactUnavailable): service.write_gallery_preview(source, output)
        self.assertEqual(events, ['defer', 'reference', 'profile']); self.assertFalse(files.exists(output))

    def test_gallery_false_write_keeps_url_but_publication_exception_propagates(self):
        files, images, source, output, pixels, factory, service, events = self.graph(0)
        with patch.object(service, 'images', Mock(imread=images.imread, imwrite=Mock(return_value=False))):
            self.assertEqual(service.write_gallery_preview(source, output)['url'], str(output))
        self.assertFalse(files.exists(output))
        failure = ArtifactUnavailable('synthetic publication failure')
        with patch.object(self.runtimes[0].store, 'put_bytes', side_effect=failure):
            with self.assertRaises(ArtifactUnavailable) as caught: service.write_gallery_preview(source, output)
            self.assertIs(caught.exception, failure)
        self.assertFalse(files.exists(output))

    def test_required_falsey_ports_and_composition_order(self):
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness checked')
        specs = {CandidateFactory: ['images'], AccessoryGallery: ['files', 'images']}
        for cls, fields in specs.items():
            args = {name: Mock() for name in inspect.signature(cls).parameters if name not in fields}
            with self.assertRaises(TypeError): cls(**args)
            ports = {field: Falsey() for field in fields}
            for field in fields:
                with self.assertRaises(TypeError): cls(**args, **{**ports, field: None})
            service = cls(**args, **ports)
            for field in fields: self.assertIs(getattr(service, field), ports[field])
        tree = ast.parse(read_checked_application_source(Path(__file__).resolve().parents[1] / 'local_inspection_service/server.py', encoding='utf-8')); found = []
        allocation = [n.lineno for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_accessory_image_io' for t in n.targets)]
        self.assertEqual(len(allocation), 1)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {c.__name__ for c in specs}:
                cls = next(c for c in specs if c.__name__ == node.func.id)
                for field in specs[cls]:
                    values = [kw.value for kw in node.keywords if kw.arg == field]; self.assertEqual(len(values), 1)
                    self.assertEqual(ast.dump(values[0]), ast.dump(ast.parse('_business_files' if field == 'files' else '_accessory_image_io', mode='eval').body))
                self.assertLess(allocation[0], node.lineno); found.append(cls)
        self.assertCountEqual(found, specs)


if __name__ == '__main__': unittest.main()
