"""Frozen original prompt bytes and late dependency behavior, without provider calls."""
import ast
from dataclasses import fields
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE = os.environ.get('VANTALINE_POSE_COLLECTION_PROMPTS_BASELINE_SOURCE')
NAMES = ('pose_collection_dimension_text', 'tabletop_scene_text', 'pose_collection_camera_grid_text',
         'pose_collection_position_specs', 'pose_collection_camera_batch_text', 'upright_spatial_relation_text',
         'build_pose_collection_prompt', 'build_white_table_replacement_prompt', 'build_anchor_replacement_pose_prompt')
BATCHES = [('top_row', '上排三视角', ['top-left', 'top-center', 'top-right']),
           ('middle_row', '中排三视角', ['middle-left', 'center', 'middle-right']),
           ('bottom_row', '下排三视角', ['bottom-left', 'bottom-center', 'bottom-right'])]


def create():
    bindings = {'POSE_COLLECTION_BATCHES': list(BATCHES)}
    if BASELINE:
        nodes = [n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body
                 if isinstance(n, ast.FunctionDef) and n.name in NAMES]
        assert len(nodes) == 9
        bindings.update(Any=Any, math=math)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, 'exec'), bindings)
        return SimpleNamespace(**{n: bindings[n] for n in NAMES}), bindings
    from local_inspection_service.accessories.pose_collection_prompts import PoseCollectionPrompts
    from local_inspection_service.accessories.pose_collection_prompt_ports import PoseCollectionPromptDependencies
    service = PoseCollectionPrompts(PoseCollectionPromptDependencies(**{
        f.name: lambda name=f.name: bindings[name] for f in fields(PoseCollectionPromptDependencies)}))
    bindings.update({n: getattr(service, n) for n in NAMES})
    return service, bindings


class PosePromptContract(unittest.TestCase):
    def test_frozen_original_output_bytes(self):
        service, bindings = create()
        fixture = json.loads((ROOT / 'tests/backend_contract/pose_collection_prompts.json').read_text(encoding='utf-8'))
        self.assertEqual(len(fixture['cases']), 203)
        self.assertEqual(fixture['base'], '789b83d52706eb112b621676223134d1ad122c32')
        for case in fixture['cases']:
            with self.subTest(function=case['name'], args=case['args']):
                value = getattr(service, case['name'])(*case['args'])
                encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                self.assertEqual(hashlib.sha256(encoded).hexdigest(), case['sha256'])
                self.assertEqual(len(encoded), case['bytes'])

    def test_default_values_and_geometry_errors(self):
        service, bindings = create()
        self.assertEqual(service.build_pose_collection_prompt({}), service.build_pose_collection_prompt({}, 'combined', None, 'reference'))
        self.assertEqual(service.tabletop_scene_text(), service.tabletop_scene_text('white'))
        self.assertEqual(service.pose_collection_camera_grid_text({}), service.pose_collection_camera_grid_text({}, 'white'))
        for name in ('pose_collection_position_specs', 'pose_collection_camera_grid_text', 'pose_collection_camera_batch_text'):
            args = ('top_row',) if name.endswith('batch_text') else ()
            with self.subTest(name=name):
                with self.assertRaises(ValueError): getattr(service, name)({'physical_size': {'length_mm': 'invalid'}}, *args)
                with self.assertRaises(TypeError): getattr(service, name)({'physical_size': {'length_mm': [1]}}, *args)
        with self.assertRaises(AttributeError): service.pose_collection_dimension_text({'physical_size': True})

    def test_late_lookup_order_and_identity(self):
        service, bindings = create()
        item = {'name': 'synthetic'}
        events = []
        def dimensions(value):
            self.assertIs(value, item)
            events.append('dimensions')
            bindings['pose_collection_camera_batch_text'] = camera
            return 'DIMENSIONS'
        def camera(value, batch, surface):
            self.assertIs(value, item)
            events.append(('camera', batch, surface))
            bindings['POSE_COLLECTION_BATCHES'] = [('custom', 'CUSTOM', ['center'])]
            bindings['upright_spatial_relation_text'] = lambda: events.append('upright') or 'UPRIGHT'
            return 'CAMERA'
        bindings['pose_collection_dimension_text'] = dimensions
        bindings['pose_collection_camera_batch_text'] = Mock(side_effect=AssertionError('stale camera'))
        result = service.build_pose_collection_prompt(item, 'upright', 'custom', 'reference')
        self.assertIn("batch 'CUSTOM'", result)
        self.assertIn('Create exactly 1 separated object cutouts', result)
        self.assertIn('DIMENSIONS', result)
        self.assertIn('CAMERA', result)
        self.assertIn('UPRIGHT', result)
        self.assertEqual(events, ['dimensions', ('camera', 'custom', 'reference'), 'upright'])

    def test_combined_branch_still_evaluates_earlier_dependencies(self):
        service, bindings = create()
        error = RuntimeError('synthetic camera error')
        dimension = Mock(return_value='dimension')
        camera = Mock(side_effect=error)
        bindings.update(pose_collection_dimension_text=dimension, pose_collection_camera_batch_text=camera)
        with self.assertRaises(RuntimeError) as caught: service.build_pose_collection_prompt({})
        self.assertIs(caught.exception, error)
        dimension.assert_called_once_with({})
        camera.assert_called_once_with({}, None, 'reference')

    def test_unknown_batch_fallback_and_invalid_positions(self):
        service, bindings = create()
        sentinel = object()
        fallback = Mock(return_value=sentinel)
        bindings['pose_collection_camera_grid_text'] = fallback
        for key in (None, '', 'unknown'):
            self.assertIs(service.pose_collection_camera_batch_text({}, key, 'custom'), sentinel)
        self.assertEqual(fallback.call_count, 3)
        bindings['POSE_COLLECTION_BATCHES'] = [('bad', 'invalid', ['missing'])]
        with self.assertRaises(KeyError) as caught: service.pose_collection_camera_batch_text({}, 'bad')
        self.assertEqual(caught.exception.args, ('missing',))
        bindings['POSE_COLLECTION_BATCHES'] = [('empty', 'empty', [])]
        self.assertIn('Generate exactly three', service.pose_collection_camera_batch_text({}, 'empty'))

    @unittest.skipIf(bool(BASELINE), 'candidate assembly only')
    def test_actual_root_forwarders_and_light_import(self):
        tree = ast.parse(read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf-8'))
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
        self.assertEqual(len(functions), 9)
        for node in functions:
            self.assertEqual(len(node.body), 1)
            self.assertIsInstance(node.body[0], ast.Return)
            self.assertEqual(node.body[0].value.func.attr, node.name)
        assembly = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == '_pose_collection_prompts' for t in n.targets))
        getters = assembly.args[0].keywords
        self.assertEqual(len(getters), 7)
        for kw in getters:
            self.assertIsInstance(kw.value, ast.Lambda)
            self.assertEqual(kw.arg, kw.value.body.id)
        service = SimpleNamespace(**{name: Mock(return_value=object()) for name in NAMES})
        ns = {'Any': Any, '_pose_collection_prompts': service}
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<root-forwarders>', 'exec'), ns)
        obj, family, batch, surface = object(), object(), object(), object()
        self.assertIs(ns['build_pose_collection_prompt'](obj, family, batch, surface), service.build_pose_collection_prompt.return_value)
        service.build_pose_collection_prompt.assert_called_once_with(obj, family, batch, surface)
        subprocess.run([sys.executable, '-B', '-c', 'import sys; import local_inspection_service.accessories.pose_collection_prompts; assert "local_inspection_service.server" not in sys.modules'], cwd=ROOT, check=True)


if __name__ == '__main__':
    unittest.main()
