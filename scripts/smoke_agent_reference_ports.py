"""Explicit Agent source readers with real synthetic artifact stores."""
import ast
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import smoke_detection_artifact_ports as fixtures
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable
from local_inspection_service.agent.pose_assets import AgentPoseAssets
from local_inspection_service.agent.pose_asset_ports import PoseAssetPaths
from local_inspection_service.agent.photo_highlight_sources import PhotoHighlightSources
from local_inspection_service.agent.photo_highlight_ports import PhotoSourceMedia
from local_inspection_service.agent.pose_render_content import PoseRenderContent
from local_inspection_service.agent.pose_render_ports import PoseRenderReferences


class AgentReferencePortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)

    def graph(self, index):
        files = BusinessFiles(lambda: self.runtimes[index]); path = self.root / 'normalized_assets/reference.png'
        data = ('synthetic-reference-' + str(index)).encode(); files.write_bytes(path, data)
        assets = AgentPoseAssets(PoseAssetPaths(lambda: Path, lambda: {'.png'}), Mock(), Mock(), Mock(), Mock(), files=files)
        photos = PhotoHighlightSources(PhotoSourceMedia(lambda: Path, lambda: {'.png'}), Mock(), Mock(), files=files)
        digest = Mock(side_effect=lambda value: hashlib.sha256(files.read_bytes(value)).hexdigest())
        references = PoseRenderReferences(lambda: lambda item, **kwargs: [{'source_path': str(path), 'ordinal': 1}], lambda: Path, lambda: lambda name: ('image/png', None), lambda: base64.b64encode, lambda: str, lambda: digest)
        content = PoseRenderContent(references, Mock(), files=files)
        return files, path, data, assets, photos, content, digest

    def test_same_paths_keep_source_inventory_and_encoded_bytes_separate(self):
        def run(index):
            files, path, data, assets, photos, content, digest = self.graph(index)
            asset = {'kind': 'agent_mcp_pose_reference', 'path': path}
            self.assertIs(assets.agent_mcp_pose_reference_assets({'normalized_assets': [asset]})[0], asset); self.assertEqual(asset['path'], str(path))
            self.assertEqual(photos.object_photo_highlight_source_paths({'source_files': [str(path)]}, limit=3), [path])
            body, refs = content.agent_mcp_pose_reference_content({})
            self.assertEqual(base64.b64decode(body[0]['image_url']['url'].split(',', 1)[1]), data)
            self.assertEqual(refs[0]['sha256'], hashlib.sha256(data).hexdigest()); self.assertFalse(path.exists()); return refs[0]['sha256']
        with ThreadPoolExecutor(max_workers=2) as pool: hashes = list(pool.map(run, range(2)))
        self.assertNotEqual(*hashes)

    def test_missing_source_filters_only_its_owner(self):
        graphs = [self.graph(i) for i in range(2)]; graphs[0][0].unlink(graphs[0][1])
        for index, (files, path, data, assets, photos, content, digest) in enumerate(graphs):
            self.assertEqual(len(assets.agent_mcp_pose_reference_assets({'normalized_assets': [{'kind': 'agent_mcp_pose_reference', 'path': path}]})), index)
            self.assertEqual(len(photos.object_photo_highlight_source_paths({'source_files': [str(path)]}, limit=3)), index)
            self.assertEqual(len(content.agent_mcp_pose_reference_content({})[0]), index)

    def test_remote_read_failure_precedes_digest_and_content(self):
        files, path, data, assets, photos, content, digest = self.graph(0)
        failure = ArtifactUnavailable('synthetic Agent reference read')
        with patch.object(self.runtimes[0].store.cache, 'open', side_effect=failure):
            with self.assertRaises(ArtifactUnavailable) as caught: content.agent_mcp_pose_reference_content({})
            self.assertIs(caught.exception, failure)
        digest.assert_not_called()

    def test_photo_filter_order_and_zero_limit_remain_unchanged(self):
        files, path, data, assets, photos, content, digest = self.graph(0)
        rectified = path.with_name('source_rectified.png'); unsupported = path.with_suffix('.txt')
        with patch.object(files, 'exists', wraps=files.exists) as exists:
            self.assertEqual(photos.object_photo_highlight_source_paths({'source_files': [str(rectified), str(unsupported), str(path), str(path)]}, limit=0), [path])
            exists.assert_called_once_with(path)
        asset = {'kind': 'agent_mcp_pose_reference', 'path': path}; failure = ArtifactUnavailable('synthetic exists')
        with patch.object(files, 'exists', side_effect=failure):
            with self.assertRaises(ArtifactUnavailable): assets.agent_mcp_pose_reference_assets({'normalized_assets': [asset]})
        self.assertIs(asset['path'], path)

    def test_required_falsey_readers_and_root_bindings(self):
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness checked')
        classes = (AgentPoseAssets, PhotoHighlightSources, PoseRenderContent)
        for cls in classes:
            args = {name: Mock() for name in inspect.signature(cls).parameters if name != 'files'}
            with self.assertRaises(TypeError): cls(**args)
            with self.assertRaises(TypeError): cls(**args, files=None)
            files = Falsey(); self.assertIs(cls(**args, files=files).files, files)
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'local_inspection_service/server.py').read_text(encoding='utf-8')); names = {'_' + cls.__name__ for cls in classes}; found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in names:
                values = [kw.value for kw in node.keywords if kw.arg == 'files']; self.assertEqual(len(values), 1)
                self.assertEqual(ast.dump(values[0]), ast.dump(ast.parse('_business_files', mode='eval').body)); found.append(node.func.id)
        self.assertCountEqual(found, names)


if __name__ == '__main__': unittest.main()
