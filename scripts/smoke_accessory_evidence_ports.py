"""Explicit image and byte ownership for accessory evidence and preview services."""
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
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
from local_inspection_service.accessories import background_evidence, background_library_selection, reference_evidence, preview_assets
from local_inspection_service.accessories.background_evidence import BackgroundPlateDerivation, BackgroundReferenceSignatures
from local_inspection_service.accessories.background_evidence_ports import PlateSources, PlatePolicy, SignatureSources, SignaturePolicy, BackgroundMasks, SignatureProjections
from local_inspection_service.accessories.background_library_selection import BackgroundCandidateCatalog, BackgroundLibraryMatcher
from local_inspection_service.accessories.background_library_selection_ports import BackgroundOwnership, BackgroundCatalogSources, BackgroundCatalogPolicy, BackgroundMatchSources, BackgroundMatchFeatures
from local_inspection_service.accessories.reference_evidence import ReferenceEvidence
from local_inspection_service.accessories.reference_evidence_ports import ReferencePolicy, ReferenceContexts
from local_inspection_service.accessories.preview_assets import PreviewAssetLoader
from local_inspection_service.accessories.preview_asset_ports import PreviewAssetPolicy, PreviewAssetPaths, PreviewAssetOperations


class AccessoryEvidencePortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)
        self.default = Mock(side_effect=AssertionError('implicit evidence storage'))
        for module in (background_evidence, background_library_selection, reference_evidence, preview_assets):
            p = patch.object(module, 'ImageFiles', self.default, create=True); p.start(); self.addCleanup(p.stop)

    def graph(self, index):
        files = BusinessFiles(lambda: self.runtimes[index]); images = ImageFiles(lambda: cv2, files=files)
        path = self.root / 'normalized_assets/same.png'; pixels = np.full((12, 16, 3), 40 + index * 120, np.uint8)
        images.imwrite(str(path), pixels)
        reference = ReferenceEvidence(ReferencePolicy(lambda: {'.png'}, Mock()), Mock(),
            ReferenceContexts(Mock(), lambda: lambda value, limit: str(value)[:limit], Mock(), Mock()), Mock(), files=files, images=images)
        fallback = Mock(return_value=None)
        preview = PreviewAssetLoader(PreviewAssetPolicy(lambda: self.root, lambda: {'.png'}), PreviewAssetPaths(lambda: Path),
            PreviewAssetOperations(lambda: fallback, Mock(), Mock(), Mock()), files=files, images=images)
        signature = lambda image: {'value': int(image.mean())}
        signatures = BackgroundReferenceSignatures(SignatureSources(lambda: lambda item, **kwargs: [path], lambda: 1),
            SignaturePolicy(lambda: 2), BackgroundMasks(lambda: lambda image: np.zeros(image.shape[:2], np.uint8)),
            SignatureProjections(lambda: lambda w, h: [(0, 0, w, h)], lambda: signature), images=images)
        manifest = {'sets': {'same': {'source': str(path)}}}
        catalog = BackgroundCandidateCatalog(BackgroundOwnership(lambda: 'system', lambda: 'legacy'),
            BackgroundCatalogSources(lambda: lambda: manifest, lambda: lambda: [], lambda: str, lambda: lambda *args: True,
                lambda: lambda directory: [], lambda: Path), BackgroundCatalogPolicy(lambda: self.root / 'backgrounds', lambda: {'.png'}, lambda: 10), files=files)
        matcher = BackgroundLibraryMatcher(BackgroundMatchSources(lambda: lambda item: [{'value': 0}], lambda: catalog.background_library_image_candidates),
            BackgroundMatchFeatures(lambda: lambda w, h: [], lambda: signature, lambda: lambda a, b: 1 + abs(a['value'] - b['value'])), lambda: 1000, images=images)
        return files, path, pixels, reference, preview, fallback, signatures, catalog, matcher

    def test_identical_paths_keep_hashes_pixels_signatures_and_match_values_separate(self):
        def run(index):
            files, path, pixels, reference, preview, fallback, signatures, catalog, matcher = self.graph(index)
            context = reference.image_reference_context(path, 'same', 1)
            self.assertEqual(context['sha256'], hashlib.sha256(files.read_bytes(path)).hexdigest())
            self.assertEqual((context['width'], context['height']), (16, 12))
            loaded, metadata = preview.load_preview_asset_with_metadata({'source_files': [str(path)]})
            np.testing.assert_array_equal(loaded, pixels); self.assertEqual(metadata['asset_source'], 'source_files'); fallback.assert_not_called()
            result = signatures.background_reference_signatures_from_accessory({})
            self.assertEqual(result, [{'value': 40 + index * 120, 'source_path': str(path), 'box_xyxy': [0, 0, 16, 12]}])
            self.assertEqual(len(catalog.background_library_image_candidates('owner')), 1)
            self.assertEqual(matcher.match_background_library_plate({}, 'owner')['distance'], 41 + index * 120)
            self.assertFalse(path.exists()); return context['sha256']
        with ThreadPoolExecutor(max_workers=2) as pool: hashes = list(pool.map(run, range(2)))
        self.assertNotEqual(*hashes); self.default.assert_not_called()

    def test_missing_source_changes_only_its_catalog_and_preserves_preview_fallback(self):
        graphs = [self.graph(i) for i in range(2)]; files, path, pixels, reference, preview, fallback, signatures, catalog, matcher = graphs[0]
        files.unlink(path)
        self.assertEqual(catalog.background_library_image_candidates('owner'), [])
        self.assertEqual(len(graphs[1][7].background_library_image_candidates('owner')), 1)
        self.assertIsNone(preview.load_preview_asset_with_metadata({'source_files': [str(path)]})); fallback.assert_called_once()
        self.assertIsNone(reference.image_reference_context(path, 'same', 1))

    def test_remote_failure_precedes_fallback_signature_or_successful_evidence(self):
        files, path, pixels, reference, preview, fallback, signatures, catalog, matcher = self.graph(0)
        failure = ArtifactUnavailable('synthetic evidence read failure')
        with patch.object(self.runtimes[0].store.cache, 'open', side_effect=failure) as reads:
            for action in (lambda: reference.image_reference_context(path, 'same', 1),
                           lambda: preview.load_preview_asset_with_metadata({'source_files': [str(path)]}),
                           lambda: signatures.background_reference_signatures_from_accessory({}),
                           lambda: matcher.match_background_library_plate({}, 'owner')):
                with self.assertRaises(ArtifactUnavailable) as caught: action()
                self.assertIs(caught.exception, failure)
            self.assertEqual(reads.call_count, 4)
        fallback.assert_not_called(); self.default.assert_not_called()

    def test_normalized_path_mutation_still_precedes_failed_decode(self):
        files, path, pixels, reference, preview, fallback, signatures, catalog, matcher = self.graph(0)
        asset = {'path': path}; item = {'normalized_assets': [asset]}
        with patch.object(self.runtimes[0].store.cache, 'open', side_effect=ArtifactUnavailable('synthetic decode source')):
            with self.assertRaises(ArtifactUnavailable): preview.load_preview_asset_with_metadata(item)
        self.assertEqual(asset['path'], str(path)); fallback.assert_not_called()

    def plate_graph(self, index):
        files = BusinessFiles(lambda: self.runtimes[index]); images = ImageFiles(lambda: cv2, files=files)
        source = self.root / 'normalized_assets/plate-source.png'
        output = self.root / 'backgrounds/plate-output.png'
        pixels = np.full((160, 160, 3), 40 + index * 120, np.uint8)
        pixels[60:100, 60:100] = 255
        images.imwrite(str(source), pixels)
        mask = np.zeros((160, 160), np.uint8); mask[60:100, 60:100] = 255
        service = BackgroundPlateDerivation(
            PlateSources(lambda: lambda item: [{'path': str(source)}], lambda: lambda item, **kwargs: [], lambda: Path, lambda: {'.png'}),
            PlatePolicy(lambda: 60, lambda: 200, lambda: 10, lambda: .5),
            BackgroundMasks(lambda: lambda image: mask), files=files, images=images)
        return service, files, images, source, output

    def test_plate_reads_and_writes_only_its_own_store(self):
        def run(index):
            service, files, images, source, output = self.plate_graph(index)
            self.assertEqual(service.derive_background_plate_from_accessory({}, output), output)
            actual = images.imread(str(output), cv2.IMREAD_COLOR)
            np.testing.assert_array_equal(actual, np.full((160, 160, 3), 40 + index * 120, np.uint8))
            self.assertFalse(source.exists()); self.assertFalse(output.exists())
            return hashlib.sha256(files.read_bytes(output)).hexdigest()
        with ThreadPoolExecutor(max_workers=2) as pool: hashes = list(pool.map(run, range(2)))
        self.assertNotEqual(*hashes); self.default.assert_not_called()

    def test_plate_read_publication_failure_and_false_write_boundaries(self):
        service, files, images, source, output = self.plate_graph(0)
        failure = ArtifactUnavailable('synthetic plate source')
        with patch.object(self.runtimes[0].store.cache, 'open', side_effect=failure):
            with self.assertRaises(ArtifactUnavailable) as caught: service.derive_background_plate_from_accessory({}, output)
            self.assertIs(caught.exception, failure)
        self.assertFalse(files.exists(output))
        false_writer = Mock(imread=images.imread, imwrite=Mock(return_value=False))
        with patch.object(service, 'images', false_writer):
            self.assertIsNone(service.derive_background_plate_from_accessory({}, output)); false_writer.imwrite.assert_called_once()
        with patch.object(self.runtimes[0].store, 'put_bytes', side_effect=failure):
            with self.assertRaises(ArtifactUnavailable) as caught: service.derive_background_plate_from_accessory({}, output)
            self.assertIs(caught.exception, failure)
        self.assertFalse(files.exists(output)); self.default.assert_not_called()

    def test_required_falsey_ports_and_root_bindings(self):
        specs = {BackgroundPlateDerivation: ['files', 'images'], BackgroundReferenceSignatures: ['images'], BackgroundCandidateCatalog: ['files'],
                 BackgroundLibraryMatcher: ['images'], ReferenceEvidence: ['files', 'images'], PreviewAssetLoader: ['files', 'images']}
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness checked')
        for cls, fields in specs.items():
            args = {name: Mock() for name in inspect.signature(cls).parameters if name not in fields}
            with self.assertRaises(TypeError): cls(**args)
            ports = {field: Falsey() for field in fields}
            for field in fields:
                with self.assertRaises(TypeError): cls(**args, **{**ports, field: None})
            service = cls(**args, **ports)
            for field in fields: self.assertIs(getattr(service, field), ports[field])
        root = Path(__file__).resolve().parents[1]; tree = ast.parse(read_checked_application_source(root / 'local_inspection_service/server.py', encoding='utf-8'))
        names = {'_' + cls.__name__: fields for cls, fields in specs.items()}; found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in names:
                for field in names[node.func.id]:
                    expected = '_business_files' if field == 'files' else '_accessory_image_io'
                    values = [kw.value for kw in node.keywords if kw.arg == field]; self.assertEqual(len(values), 1)
                    self.assertEqual(ast.dump(values[0]), ast.dump(ast.parse(expected, mode='eval').body))
                found.append(node.func.id)
        self.assertCountEqual(found, names)


if __name__ == '__main__': unittest.main()
