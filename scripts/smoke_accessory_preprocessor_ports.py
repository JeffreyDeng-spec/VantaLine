"""Real storage ownership for sprite preprocessing with synthetic cutouts."""
import ast
from concurrent.futures import ThreadPoolExecutor
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
from local_inspection_service.accessories.object_preprocessing import ObjectSpritePreprocessor
from local_inspection_service.accessories.object_preprocessing_ports import ObjectSpritePolicy, ObjectSpriteSources, ObjectSpriteRuntime, ObjectSpriteCutouts, ObjectSpriteComponents, ObjectSpriteMetadata, ObjectSpriteArtifacts


class AccessoryPreprocessorPortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)

    def graph(self, index):
        files = BusinessFiles(lambda: self.runtimes[index]); images = ImageFiles(lambda: cv2, files=files)
        source = self.root / 'normalized_assets/source.png'; pixels = np.full((20, 30, 4), 40 + index * 100, np.uint8); pixels[:, :, 3] = 255
        images.imwrite(str(source), pixels)
        provider = Mock(side_effect=AssertionError('provider call forbidden'))
        policy = ObjectSpritePolicy(lambda: lambda item: 'object', lambda: lambda item: 'opaque', lambda: lambda item: [], lambda: lambda *args: True)
        sources = ObjectSpriteSources(lambda: lambda item: [], lambda: lambda item: [source], lambda: [], lambda: provider)
        runtime = ObjectSpriteRuntime(lambda: lambda item: 'same', lambda: self.root / 'normalized_assets', lambda: lambda: 123, lambda: np.random.default_rng)
        cutouts = ObjectSpriteCutouts(lambda: provider, lambda: provider, lambda: provider, lambda: provider, lambda: lambda cutout, shape: cutout)
        components = ObjectSpriteComponents(lambda: lambda image: [(image[:, :, :3].copy(), image[:, :, 3].copy())], lambda: provider, lambda: provider, lambda: provider, lambda: provider)
        normalize = Mock(); metadata = ObjectSpriteMetadata(lambda: provider, lambda: normalize, lambda: Mock(), lambda: Mock(), lambda: provider, lambda: provider)
        def write(path, image, mask, evidence):
            images.imwrite(str(path), np.dstack((image, mask)))
            return {'kind': 'clean_object_sprite', 'path': str(path), 'evidence': evidence}
        writer = Mock(side_effect=write)
        service = ObjectSpritePreprocessor(policy, sources, runtime, cutouts, components, metadata, ObjectSpriteArtifacts(lambda: writer), files=files, images=images)
        item = {'created_at': 7, 'normalized_assets': [{'kind': 'reference', 'path': str(source)}]}
        return service, files, images, source, pixels, item, provider, writer, normalize

    def test_source_sprite_publication_and_metadata_keep_owner(self):
        def run(index):
            service, files, images, source, pixels, item, provider, writer, normalize = self.graph(index)
            self.assertTrue(service.preprocess_object_clean_sprites(item, allow_ai_cutout=False))
            self.assertEqual(item['clean_sprite_status'], 'ready'); self.assertEqual(item['clean_sprite_count'], 1)
            self.assertEqual(item['clean_sprite_preprocessed_at'], 123)
            output = Path(item['normalized_assets'][-1]['path'])
            self.assertEqual(item['normalized_assets'][-1]['method'], 'source_png_alpha')
            np.testing.assert_array_equal(images.imread(str(output), cv2.IMREAD_UNCHANGED), pixels)
            writer.assert_called_once(); normalize.assert_called_once(); provider.assert_not_called()
            self.assertFalse(output.exists()); return output
        with ThreadPoolExecutor(max_workers=2) as pool: paths = list(pool.map(run, range(2)))
        self.assertEqual(*paths)

    def test_read_failure_precedes_cutout_and_publication(self):
        service, files, images, source, pixels, item, provider, writer, normalize = self.graph(0)
        failure = ArtifactUnavailable('synthetic preprocessing read')
        with patch.object(self.runtimes[0].store.cache, 'open', side_effect=failure):
            with self.assertRaises(ArtifactUnavailable) as caught: service.preprocess_object_clean_sprites(item, allow_ai_cutout=False)
            self.assertIs(caught.exception, failure)
        self.assertEqual(item['material_alpha_policy'], 'opaque'); self.assertNotIn('clean_sprite_status', item)
        writer.assert_not_called(); provider.assert_not_called(); normalize.assert_not_called()

    def test_metadata_error_keeps_published_sprite_before_item_replacement(self):
        service, files, images, source, pixels, item, provider, writer, normalize = self.graph(0)
        before = item['normalized_assets']; failure = RuntimeError('synthetic normalization')
        normalize.side_effect = failure
        with self.assertRaises(RuntimeError) as caught: service.preprocess_object_clean_sprites(item, allow_ai_cutout=False)
        self.assertIs(caught.exception, failure); self.assertIs(item['normalized_assets'], before)
        output = self.root / 'normalized_assets/same/clean_sprites/sprite_01.png'
        np.testing.assert_array_equal(images.imread(str(output), cv2.IMREAD_UNCHANGED), pixels)
        self.assertNotIn('clean_sprite_status', item); provider.assert_not_called()

    def test_pose_existence_failure_precedes_cache_shortcut(self):
        service, files, images, source, pixels, item, provider, writer, normalize = self.graph(0)
        service._sources = ObjectSpriteSources(lambda: lambda item: [{'output_path': str(source), 'intermediate': True}], lambda: lambda item: [], lambda: [], lambda: provider)
        service._policy = ObjectSpritePolicy(lambda: lambda item: 'object', lambda: lambda item: 'opaque', lambda: lambda item: [{'cached': True}], lambda: lambda *args: True)
        failure = ArtifactUnavailable('synthetic existence failure')
        with patch.object(files, 'exists', side_effect=failure):
            with self.assertRaises(ArtifactUnavailable) as caught: service.preprocess_object_clean_sprites(item, allow_ai_cutout=False)
            self.assertIs(caught.exception, failure)
        self.assertEqual(item['material_alpha_policy'], 'opaque'); writer.assert_not_called(); provider.assert_not_called()

    def test_required_falsey_ports_and_root_binding(self):
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness checked')
        args = [Mock() for _ in range(7)]
        with self.assertRaises(TypeError): ObjectSpritePreprocessor(*args)
        files, images = Falsey(), Falsey()
        for ports in ({'files': None, 'images': images}, {'files': files, 'images': None}):
            with self.assertRaises(TypeError): ObjectSpritePreprocessor(*args, **ports)
        service = ObjectSpritePreprocessor(*args, files=files, images=images); self.assertIs(service.files, files); self.assertIs(service.images, images)
        tree = ast.parse(read_checked_application_source(Path(__file__).resolve().parents[1] / 'local_inspection_service/server.py', encoding='utf-8'))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == '_ObjectSpritePreprocessor']; self.assertEqual(len(calls), 1)
        for field, name in [('files', '_business_files'), ('images', '_accessory_image_io')]:
            values = [kw.value for kw in calls[0].keywords if kw.arg == field]; self.assertEqual(len(values), 1)
            self.assertEqual(ast.dump(values[0]), ast.dump(ast.parse(name, mode='eval').body))


if __name__ == '__main__': unittest.main()
