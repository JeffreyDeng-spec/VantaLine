"""Explicit pose publication and materialization with isolated artifact stores."""
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import smoke_detection_artifact_ports as fixtures
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable
from local_inspection_service.agent.pose_artifact_store import PoseArtifactStore
from local_inspection_service.agent.pose_render_ports import PoseRenderPaths, PoseRenderArtifacts, PoseRenderPresentation
from local_inspection_service.agent.pose_asset_materialization import PoseAssetMaterialization
from local_inspection_service.agent.pose_materialization_ports import PoseChromaSources, PoseMaterializationState, PoseAssetMedia, PoseMaterializationSprites


class AgentPoseStoragePortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)

    def graph(self, index):
        files = BusinessFiles(lambda: self.runtimes[index]); output = self.root / 'outputs/agent_mcp_pose_images/same/part__front.png'
        task = {'id': 'same', 'owner_user_id': str(index)}; call = {'call_id': 'call', 'accessory_id': 'part', 'pose_id': 'front', 'tool': 'pose', 'status': 'completed', 'output_path': str(output)}
        digest = Mock(side_effect=lambda path: hashlib.sha256(files.read_bytes(path)).hexdigest())
        store = PoseArtifactStore(PoseRenderPaths(lambda: lambda kind, owner: self.root / 'outputs' / kind, lambda: str), PoseRenderArtifacts(lambda: lambda *args: output, lambda: digest, lambda: str, lambda: lambda text, limit: str(text)[:limit], lambda: lambda: 123, lambda: json.dumps), PoseRenderPresentation(lambda: lambda screen: {'name': 'synthetic'}), files=files)
        state = {'tool_calls': [call]}; item = {'id': 'part'}; build = Mock(return_value=False)
        materialization = PoseAssetMaterialization(PoseChromaSources(Mock(), lambda: lambda value: {'name': 'synthetic'}, Mock()), PoseMaterializationState(lambda: lambda task: state, lambda: lambda cfg: {'part': item}, lambda: lambda: 123, lambda: 'pose'), PoseAssetMedia(lambda: Path, lambda: str, lambda: digest, lambda: {'.png'}), PoseMaterializationSprites(lambda: lambda value: [], lambda: lambda *args: False, lambda: build), files=files)
        return files, output, task, call, store, materialization, state, item, build, digest

    def publish(self, graph, index):
        files, output, task, call, store, materialization, state, item, build, digest = graph
        return store.write_agent_mcp_pose_artifact(task, call, {'bytes': ('synthetic-' + str(index)).encode(), 'model': 'test'}, prompt='synthetic prompt', reference_assets=[])

    def test_same_paths_keep_image_metadata_and_materialization_separate(self):
        def run(index):
            graph = self.graph(index); files, output, task, call, store, materialization, state, item, build, digest = graph
            result = self.publish(graph, index); self.assertEqual(files.read_bytes(output), ('synthetic-' + str(index)).encode())
            metadata = files.read_json(Path(result['metadata_path'])); self.assertEqual(metadata['sha256'], result['sha256'])
            self.assertEqual(metadata['sha256'], hashlib.sha256(files.read_bytes(output)).hexdigest())
            self.assertTrue(materialization.materialize_agent_mcp_pose_assets(task, {})); self.assertEqual(item['normalized_assets'][0]['sha256'], result['sha256'])
            self.assertEqual(state['materialized_pose_assets_at'], 123); build.assert_called_once(); self.assertFalse(output.exists()); return result['sha256']
        with ThreadPoolExecutor(max_workers=2) as pool: hashes = list(pool.map(run, range(2)))
        self.assertNotEqual(*hashes)

    def test_missing_owner_output_does_not_materialize_other_store(self):
        graphs = [self.graph(i) for i in range(2)]; self.publish(graphs[1], 1)
        self.assertFalse(graphs[0][5].materialize_agent_mcp_pose_assets(graphs[0][2], {})); self.assertNotIn('normalized_assets', graphs[0][7])
        self.assertTrue(graphs[1][5].materialize_agent_mcp_pose_assets(graphs[1][2], {}))

    def test_metadata_failure_keeps_image_before_success_response(self):
        graph = self.graph(0); files, output, task, call, store, materialization, state, item, build, digest = graph
        failure = ArtifactUnavailable('synthetic metadata publication')
        with patch.object(files, 'write_text', side_effect=failure):
            with self.assertRaises(ArtifactUnavailable) as caught: self.publish(graph, 0)
            self.assertIs(caught.exception, failure)
        self.assertEqual(files.read_bytes(output), b'synthetic-0'); self.assertFalse(files.exists(output.with_suffix('.png.metadata.json')))
        digest.assert_called_once_with(output)

    def test_sprite_failure_retains_appended_reference_before_state_timestamp(self):
        graph = self.graph(0); self.publish(graph, 0)
        files, output, task, call, store, materialization, state, item, build, digest = graph
        failure = RuntimeError('synthetic sprite build'); build.side_effect = failure
        with self.assertRaises(RuntimeError) as caught: materialization.materialize_agent_mcp_pose_assets(task, {})
        self.assertIs(caught.exception, failure); self.assertEqual(item['normalized_assets'][0]['path'], str(output))
        self.assertNotIn('materialized_pose_assets_at', state)

    def test_required_falsey_ports_and_root_bindings(self):
        class Falsey:
            def __bool__(self): raise AssertionError('truthiness checked')
        classes = (PoseArtifactStore, PoseAssetMaterialization)
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
