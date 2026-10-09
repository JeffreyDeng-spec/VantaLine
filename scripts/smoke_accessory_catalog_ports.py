"""Storage ownership and retained mutation boundaries for accessory catalogs."""
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
import smoke_detection_artifact_ports as fixtures
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.images import ImageFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable
from local_inspection_service.accessories import materialized_assets, preview_sprites
from local_inspection_service.accessories.materialized_assets import SpriteAssetCatalog, TextAssetCatalog
from local_inspection_service.accessories.materialized_asset_ports import MaterializedAssetPaths, SpriteCatalogPoseOperations, SpriteCatalogMaterialPolicy, SpriteCatalogReadiness, TextCatalogOperations


class AccessoryCatalogPortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)
        self.default = Mock(side_effect=AssertionError('implicit catalog storage'))
        for module in (materialized_assets, preview_sprites):
            p = patch.object(module, 'ImageFiles', self.default, create=True); p.start(); self.addCleanup(p.stop)

    def graph(self, index):
        files = BusinessFiles(lambda: self.runtimes[index]); images = ImageFiles(lambda: cv2, files=files)
        path = self.root / 'normalized_assets/catalog.png'
        pixels = np.full((20 + index, 30 + index, 4), 40 + index * 100, np.uint8); pixels[:, :, 3] = 255
        images.imwrite(str(path), pixels)
        paths = MaterializedAssetPaths(lambda: Path)
        sprite = SpriteAssetCatalog(paths, SpriteCatalogPoseOperations(lambda: lambda *args: False, lambda: lambda *args: {}, lambda: Mock(), lambda: Mock()), Mock(), Mock(), files=files, images=images)
        text = TextAssetCatalog(paths, TextCatalogOperations(lambda: {'.png'}, Mock()), files=files, images=images)
        return files, images, path, pixels, sprite, text

    def test_identical_paths_have_independent_dimensions_and_sprite_pixels(self):
        def run(index):
            files, images, path, pixels, sprite, text = self.graph(index)
            asset = {'kind': 'clean_object_sprite', 'path': path}
            self.assertIs(sprite.clean_sprite_assets({'normalized_assets': [asset]})[0], asset)
            self.assertEqual((asset['height'], asset['width']), pixels.shape[:2]); self.assertEqual(asset['path'], str(path))
            canonical = {'kind': 'canonical_text_image', 'path': path}
            self.assertIs(text.canonical_text_assets({'normalized_assets': [canonical]})[0], canonical)
            self.assertEqual((canonical['height'], canonical['width']), pixels.shape[:2]); self.assertIs(canonical['path'], path)
            rgb, alpha = preview_sprites.load_clean_sprite(path, images=images)
            np.testing.assert_array_equal(rgb, pixels[:, :, :3]); np.testing.assert_array_equal(alpha, pixels[:, :, 3])
            self.assertFalse(path.exists()); return rgb.shape
        with ThreadPoolExecutor(max_workers=2) as pool: shapes = list(pool.map(run, range(2)))
        self.assertNotEqual(*shapes); self.default.assert_not_called()

    def test_missing_file_filters_only_owner_catalog(self):
        graphs = [self.graph(i) for i in range(2)]; graphs[0][0].unlink(graphs[0][2])
        for index, (files, images, path, pixels, sprite, text) in enumerate(graphs):
            self.assertEqual(len(sprite.clean_sprite_assets({'normalized_assets': [{'kind': 'clean_object_sprite', 'path': path, 'width': 7, 'height': 9}]})), index)
            self.assertEqual(len(text.canonical_text_assets({'normalized_assets': [{'kind': 'canonical_text_image', 'path': path, 'width': 7, 'height': 9}]})), index)

    def test_decode_failure_keeps_original_sprite_vs_text_mutation_order(self):
        files, images, path, pixels, sprite, text = self.graph(0)
        failure = ArtifactUnavailable('synthetic catalog decode')
        sprite_asset = {'kind': 'clean_object_sprite', 'path': path}; text_asset = {'kind': 'canonical_text_image', 'path': path}
        with patch.object(self.runtimes[0].store.cache, 'open', side_effect=failure) as reads:
            for service, asset, method in [(sprite, sprite_asset, 'clean_sprite_assets'), (text, text_asset, 'canonical_text_assets')]:
                with self.assertRaises(ArtifactUnavailable) as caught: getattr(service, method)({'normalized_assets': [asset]})
                self.assertIs(caught.exception, failure); self.assertNotIn('width', asset)
            with self.assertRaises(ArtifactUnavailable): preview_sprites.load_clean_sprite(path, images=images)
            self.assertEqual(reads.call_count, 3)
        self.assertEqual(sprite_asset['path'], str(path)); self.assertIs(text_asset['path'], path)

    def test_preexisting_zero_dimensions_and_alpha_threshold_are_retained(self):
        files, images, path, pixels, sprite, text = self.graph(0)
        for service, kind, method in [(sprite, 'clean_object_sprite', 'clean_sprite_assets'), (text, 'canonical_text_image', 'canonical_text_assets')]:
            asset = {'kind': kind, 'path': path, 'width': 0, 'height': 0}
            self.assertEqual(len(getattr(service, method)({'normalized_assets': [asset]})), 1)
            self.assertEqual((asset['width'], asset['height']), (0, 0))
        boundary = np.full((16, 15, 4), 9, np.uint8); images.imwrite(str(path), boundary)
        self.assertIsNotNone(preview_sprites.load_clean_sprite(path, images=images))
        boundary[0, 0, 3] = 8; images.imwrite(str(path), boundary)
        self.assertIsNone(preview_sprites.load_clean_sprite(path, images=images))

    def test_required_ports_and_real_root_bindings(self):
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness inspected')
        for cls in (SpriteAssetCatalog, TextAssetCatalog):
            args = {name: Mock() for name in inspect.signature(cls).parameters if name not in {'files', 'images'}}
            with self.assertRaises(TypeError): cls(**args)
            files, images = Falsey(), Falsey()
            for fields in ({'files': None, 'images': images}, {'files': files, 'images': None}):
                with self.assertRaises(TypeError): cls(**args, **fields)
            service = cls(**args, files=files, images=images)
            self.assertIs(service.files, files); self.assertIs(service.images, images)
        with self.assertRaises(TypeError): preview_sprites.load_clean_sprite(Path('synthetic'))
        with self.assertRaises(TypeError): preview_sprites.load_clean_sprite(Path('synthetic'), images=None)
        source = Path(__file__).resolve().parents[1] / 'local_inspection_service/server.py'; tree = ast.parse(source.read_text(encoding='utf-8'))
        expected = {'_SpriteAssetCatalog': {'files': '_business_files', 'images': '_accessory_image_io'}, '_TextAssetCatalog': {'files': '_business_files', 'images': '_accessory_image_io'}, '_load_clean_sprite_impl': {'images': '_accessory_image_io'}}
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in expected:
                for field, name in expected[node.func.id].items():
                    values = [kw.value for kw in node.keywords if kw.arg == field]; self.assertEqual(len(values), 1)
                    self.assertEqual(ast.dump(values[0]), ast.dump(ast.parse(name, mode='eval').body))
                found.append(node.func.id)
        self.assertCountEqual(found, expected)


if __name__ == '__main__': unittest.main()
