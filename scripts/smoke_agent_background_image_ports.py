"""Explicit pipeline background media ports with synthetic artifact stores."""
import ast
import hashlib
import inspect
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import smoke_detection_artifact_ports as fixtures
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.images import ImageFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable
from local_inspection_service.agent.pipeline_background_publication import PipelineBackgroundPublication
from local_inspection_service.agent.pipeline_background_publication_ports import (
    BackgroundPublicationTasks, BackgroundPublicationPaths, BackgroundPublicationSelection,
    BackgroundPublicationProviders, BackgroundPublicationCatalog, BackgroundPublicationProjection)


class BackgroundImagePortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)

    def graph(self, index, *, generated=False):
        files = BusinessFiles(lambda: self.runtimes[index]); images = ImageFiles(pil_provider=lambda: Image, files=files)
        source = self.root / 'normalized_assets/source.png'; output = self.root / 'outputs/background'
        sets = self.root / 'backgrounds'; pixel = (30 + 100 * index, 50, 80)
        content = io.BytesIO(); Image.new('RGB', (9, 7), pixel).save(content, format='PNG'); payload = content.getvalue()
        files.write_bytes(source, payload)
        state = {}; task = {'id': 'same', 'owner_user_id': str(index), 'accessory_ids': ['part']}; manifest = {'sets': {}}
        provider = Mock(); provider.generate_image.return_value = {'bytes': payload, 'mime_type': 'image/png'}
        config = Mock(return_value={'configured': True, 'model': 'synthetic', 'timeout_seconds': 1, 'provider_name': 'gemini'})
        refs = Mock(return_value=([{'synthetic': True}], [])); derive = Mock(return_value=None); publish = Mock(); variants = Mock()
        service = PipelineBackgroundPublication(
            BackgroundPublicationTasks(lambda: lambda task: state, lambda: lambda config, ids: ids, lambda: lambda config: {'part': {'id': 'part'}}),
            BackgroundPublicationPaths(lambda: lambda kind, owner: output, lambda: str, lambda: str, lambda: Path, lambda: sets),
            BackgroundPublicationSelection(lambda: lambda item: 'synthetic prompt', lambda: lambda item, owner: None if generated else {'image_path': str(source)}, lambda: derive),
            BackgroundPublicationProviders(lambda: config, lambda: refs, lambda: lambda: {}, lambda: lambda settings: provider, lambda: ValueError),
            BackgroundPublicationCatalog(lambda: lambda path: list(files.glob(path, '*.png')), lambda: variants, lambda: lambda: manifest, lambda: publish),
            BackgroundPublicationProjection(lambda: lambda text, limit: text[:limit], lambda: lambda path: '/synthetic/' + str(index), lambda: lambda path: hashlib.sha256(files.read_bytes(path)).hexdigest(), lambda: lambda: 'synthetic-now', lambda: 'legacy'),
            files=files, images=images)
        return service, files, task, state, manifest, provider, config, refs, derive, publish, variants, pixel, output/'same/plate.png', sets/'task_plate_same/plate.png'

    def test_same_paths_keep_library_and_generated_pixels_in_their_owner(self):
        graphs = [self.graph(i, generated=bool(i)) for i in range(2)]
        for index, graph in enumerate(graphs):
            service, files, task, state, manifest, provider, config, refs, derive, publish, variants, pixel, plate, target = graph
            self.assertEqual(service.ensure_pipeline_background_plate(task, {}), 'task_plate_same')
            for path in (plate, target):
                with service.images.open(path) as image: self.assertEqual(image.getpixel((0, 0)), pixel)
                self.assertFalse(path.exists())
            config.assert_called_once_with(); refs.assert_called_once_with({'id': 'part'}, max_images=2)
            self.assertEqual(provider.generate_image.call_count, index); derive.assert_not_called()
            variants.assert_called_once_with(plate, target.parent, count=6); publish.assert_called_once_with(manifest)
            self.assertEqual(state['background_plate']['api_calls'], index)
        for index, graph in enumerate(graphs):
            with graph[0].images.open(graph[-1]) as image: self.assertEqual(image.getpixel((0, 0)), graph[-3])

    def test_remote_library_read_error_propagates_before_model_config(self):
        service, files, task, state, manifest, provider, config, refs, derive, publish, variants, pixel, plate, target = self.graph(0)
        failure = ArtifactUnavailable('synthetic library read')
        with patch.object(self.runtimes[0].store.cache, 'open', side_effect=failure):
            with self.assertRaises(ArtifactUnavailable) as caught: service.ensure_pipeline_background_plate(task, {})
        self.assertIs(caught.exception, failure); config.assert_not_called(); provider.generate_image.assert_not_called()
        derive.assert_not_called(); publish.assert_not_called(); self.assertNotIn('background_plate', state)

    def test_generated_payload_write_failure_has_one_provider_call_without_fallback(self):
        service, files, task, state, manifest, provider, config, refs, derive, publish, variants, pixel, plate, target = self.graph(0, generated=True)
        failure = ArtifactUnavailable('synthetic payload publication')
        with patch.object(self.runtimes[0].store, 'put_bytes', side_effect=failure):
            with self.assertRaises(ArtifactUnavailable) as caught: service.ensure_pipeline_background_plate(task, {})
        self.assertIs(caught.exception, failure); self.assertEqual(provider.generate_image.call_count, 1)
        derive.assert_not_called(); variants.assert_not_called(); publish.assert_not_called()
        self.assertNotIn('background_set_id', task); self.assertFalse(files.exists(plate))

    def test_set_copy_failure_retains_plate_and_removal_before_manifest(self):
        service, files, task, state, manifest, provider, config, refs, derive, publish, variants, pixel, plate, target = self.graph(0)
        stale = target.with_name('stale.png'); files.write_bytes(stale, b'synthetic stale')
        original = self.runtimes[0].store.put_bytes; failure = ArtifactUnavailable('synthetic set copy')
        def put(path, data, **kwargs):
            if path == 'backgrounds/task_plate_same/plate.png': raise failure
            return original(path, data, **kwargs)
        with patch.object(self.runtimes[0].store, 'put_bytes', side_effect=put):
            with self.assertRaises(ArtifactUnavailable) as caught: service.ensure_pipeline_background_plate(task, {})
        self.assertIs(caught.exception, failure); self.assertTrue(files.exists(plate)); self.assertFalse(files.exists(stale))
        variants.assert_not_called(); publish.assert_not_called(); self.assertNotIn('background_plate', state)
        self.assertEqual(state['background_plate_error'], ''); self.assertNotIn('background_set_id', task)

    def test_required_falsey_ports_and_matching_root_owners(self):
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness checked')
        args = {name: Mock() for name in inspect.signature(PipelineBackgroundPublication).parameters if name not in ('files', 'images')}
        with self.assertRaises(TypeError): PipelineBackgroundPublication(**args)
        for missing in ('files', 'images'):
            ports = dict(files=Mock(), images=Mock()); ports[missing] = None
            with self.assertRaises(TypeError): PipelineBackgroundPublication(**args, **ports)
        files, images = Falsey(), Falsey(); service = PipelineBackgroundPublication(**args, files=files, images=images)
        self.assertIs(service.files, files); self.assertIs(service.images, images)
        tree = ast.parse((Path(__file__).resolve().parents[1]/'local_inspection_service/server.py').read_text(encoding='utf-8'))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == '_PipelineBackgroundPublication']
        self.assertEqual(len(calls), 1); bindings = {kw.arg: ast.dump(kw.value) for kw in calls[0].keywords}
        for key, value in [('files', '_business_files'), ('images', '_agent_pil_images')]: self.assertEqual(bindings[key], ast.dump(ast.parse(value, mode='eval').body))
        allocations = [node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_agent_pil_images' for t in node.targets)]
        self.assertEqual(len(allocations), 1)
        self.assertEqual(ast.dump(next(kw.value for kw in allocations[0].value.keywords if kw.arg == 'files')), ast.dump(ast.parse('_business_files', mode='eval').body))


if __name__ == '__main__': unittest.main()
