"""Photo-highlight IO isolation using synthetic model output and real adapters."""
from application_integration_source_contract import restore_pose_domain_root
import ast
from concurrent.futures import ThreadPoolExecutor
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
from local_inspection_service.agent.photo_highlight_builder import PhotoHighlightSpriteBuilder
from local_inspection_service.agent import photo_highlight_builder_ports as ports


class AgentPhotoImagePortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)

    def graph(self, index):
        files = BusinessFiles(lambda: self.runtimes[index]); images = ImageFiles(lambda: cv2, files=files)
        source = self.root / 'uploads/source.png'; pixels = np.full((12, 16, 3), 40 + index * 100, np.uint8); images.imwrite(str(source), pixels)
        policy = ports.PhotoBuildPolicy(lambda: lambda item: 'object', lambda: lambda item: [source], lambda: lambda *args: False, lambda: lambda item: 'opaque', lambda: lambda *args: True, lambda: 1)
        runtime = ports.PhotoBuildRuntime(lambda: lambda item: 'part', lambda: self.root / 'normalized_assets', lambda: lambda category, owner: self.root / 'outputs' / category, lambda: str, lambda: lambda: 123, lambda: lambda text, limit: str(text)[:limit])
        masks = ports.PhotoBuildMasks(lambda: lambda item: 'synthetic prompt', lambda: lambda image: (image.copy(), 'data:image/synthetic', 1., 1.), lambda: lambda image: (np.full(image.shape[:2], 255, np.uint8), {'ok': True}), lambda: lambda image, **kwargs: [0, 0, 16, 12], lambda: lambda image, mask: (mask.copy(), {}), lambda: lambda *args: {'ok': True, 'score': 1.})
        model = ports.PhotoBuildModelPolicy(lambda: 1, lambda: RuntimeError, lambda: 1, lambda: 1)
        publish = Mock(); publication = ports.PhotoBuildPublication(lambda: str, lambda: lambda **kwargs: kwargs, lambda: publish)
        def write(path, image, mask, metadata):
            images.imwrite(str(path), np.dstack((image, mask)))
            return {'kind': 'clean_object_sprite', 'path': str(path), **metadata}
        artifacts = ports.PhotoBuildArtifacts(lambda: write, lambda: str)
        metadata = ports.PoseSpriteMetadata(lambda: lambda *args: {}, lambda: Mock(), lambda: Mock(), lambda: Mock())
        provider = Mock(); provider.generate_image.return_value = {'bytes': cv2.imencode('.png', np.full((6, 8, 3), 255, np.uint8))[1].tobytes()}
        service = PhotoHighlightSpriteBuilder(policy, runtime, masks, model, publication, artifacts, metadata, files=files, images=images)
        item = {'name': 'synthetic', 'normalized_assets': [{'kind': 'reference'}]}; task = {'id': 'same', 'owner_user_id': str(index)}
        return service, files, images, source, pixels, provider, publish, item, task

    def test_sources_masks_diagnostics_and_final_sprite_stay_with_owner(self):
        def run(index):
            service, files, images, source, pixels, provider, publish, item, task = self.graph(index)
            self.assertEqual(service.build_clean_sprites_from_photo_highlight_masks(task, item, provider, 'synthetic'), (True, ''))
            final = item['normalized_assets'][-1]; actual = images.imread(final['path'], cv2.IMREAD_UNCHANGED)
            np.testing.assert_array_equal(actual[:, :, :3], pixels); self.assertEqual(final['method'], 'real_photo_highlight_mask_sprite')
            self.assertEqual(item['clean_sprite_status'], 'ready'); provider.generate_image.assert_called_once()
            artifact_dir = self.root / 'outputs/photo_highlight_masks/same/part'
            self.assertTrue(files.exists(artifact_dir / '01_source_highlight_resized.png'))
            np.testing.assert_array_equal(images.imread(str(artifact_dir / '01_source_attempt01_roi.png'), cv2.IMREAD_COLOR), pixels)
            self.assertFalse(Path(final['path']).exists()); return final['path']
        with ThreadPoolExecutor(max_workers=2) as pool: paths = list(pool.map(run, range(2)))
        self.assertEqual(*paths)

    def test_source_failure_follows_initial_records_but_precedes_provider(self):
        service, files, images, source, pixels, provider, publish, item, task = self.graph(0)
        failure = ArtifactUnavailable('synthetic source failure')
        with patch.object(self.runtimes[0].store.cache, 'open', side_effect=failure):
            with self.assertRaises(ArtifactUnavailable) as caught: service.build_clean_sprites_from_photo_highlight_masks(task, item, provider, 'synthetic')
            self.assertIs(caught.exception, failure)
        provider.generate_image.assert_not_called(); publish.assert_called_once()
        self.assertEqual([x['status'] for x in publish.call_args.kwargs['items']], ['completed', 'queued'])
        self.assertEqual(item['normalized_assets'], [{'kind': 'reference'}])

    def test_diagnostic_failure_keeps_mask_and_stops_without_replay(self):
        service, files, images, source, pixels, provider, publish, item, task = self.graph(0)
        original = self.runtimes[0].store.put_bytes; calls = []; failure = ArtifactUnavailable('synthetic ROI publication')
        def put(*args, **kwargs):
            calls.append(1)
            if len(calls) == 3: raise failure
            return original(*args, **kwargs)
        with patch.object(self.runtimes[0].store, 'put_bytes', side_effect=put):
            with self.assertRaises(ArtifactUnavailable) as caught: service.build_clean_sprites_from_photo_highlight_masks(task, item, provider, 'synthetic')
            self.assertIs(caught.exception, failure)
        provider.generate_image.assert_called_once(); self.assertEqual(len(calls), 3)
        artifact_dir = self.root / 'outputs/photo_highlight_masks/same/part'
        self.assertTrue(files.exists(artifact_dir / '01_source_highlight.png')); self.assertTrue(files.exists(artifact_dir / '01_source_highlight_resized.png'))
        self.assertFalse(files.exists(artifact_dir / '01_source_attempt01_roi.png')); self.assertEqual(item['normalized_assets'], [{'kind': 'reference'}])

    def test_ready_cache_does_not_access_images_or_provider(self):
        service, files, images, source, pixels, provider, publish, item, task = self.graph(0)
        service._policy = ports.PhotoBuildPolicy(lambda: lambda item: 'object', lambda: lambda item: [source], lambda: lambda *args: True, Mock(), Mock(), lambda: 1)
        poison = Mock(side_effect=AssertionError('unexpected IO')); service.images = Mock(imread=poison, imwrite=poison); service.files = Mock(write_bytes=poison)
        self.assertEqual(service.build_clean_sprites_from_photo_highlight_masks(task, item, provider, 'synthetic'), (True, ''))
        poison.assert_not_called(); provider.generate_image.assert_not_called(); publish.assert_not_called()

    def test_required_falsey_ports_and_root_bindings(self):
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness checked')
        args = [Mock() for _ in range(7)]
        with self.assertRaises(TypeError): PhotoHighlightSpriteBuilder(*args)
        files, images = Falsey(), Falsey()
        for values in ({'files': None, 'images': images}, {'files': files, 'images': None}):
            with self.assertRaises(TypeError): PhotoHighlightSpriteBuilder(*args, **values)
        service = PhotoHighlightSpriteBuilder(*args, files=files, images=images); self.assertIs(service.files, files); self.assertIs(service.images, images)
        tree = ast.parse(restore_pose_domain_root((Path(__file__).resolve().parents[1] / 'local_inspection_service/server.py').read_text(encoding='utf-8')))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == '_PhotoHighlightSpriteBuilder']; self.assertEqual(len(calls), 1)
        for field, name in [('files', '_business_files'), ('images', '_agent_image_io')]:
            values = [kw.value for kw in calls[0].keywords if kw.arg == field]; self.assertEqual(len(values), 1)
            self.assertEqual(ast.dump(values[0]), ast.dump(ast.parse(name, mode='eval').body))
        assignments = [n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_agent_image_io' for t in n.targets)]; self.assertEqual(len(assignments), 1)
        self.assertEqual(ast.dump(assignments[0].value), ast.dump(ast.parse('ImageFiles(lambda: cv2, files=_business_files)', mode='eval').body))


if __name__ == '__main__': unittest.main()
