"""Training preparation parity without media, providers or database access."""
import ast
from dataclasses import fields
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASELINE = os.environ.get('VANTALINE_TRAINING_ASSET_PREPARATION_BASELINE_SOURCE')
NAMES = ('ensure_object_clean_sprites_for_selection', 'ensure_training_normalized_assets_for_selection', 'ensure_training_assets_for_request')


def create(bindings):
    if BASELINE:
        nodes = [n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
        assert len(nodes) == 3
        bindings.update(Any=Any, Path=Path, time=time)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, 'exec'), bindings)
        return SimpleNamespace(**{name: bindings[name] for name in NAMES})
    from local_inspection_service.training.training_asset_preparation import TrainingAssetPreparation
    from local_inspection_service.training.training_asset_preparation_ports import TrainingAssetPolicy, TrainingAssetPersistence
    def ports(cls):
        return cls(**{f.name: lambda name=f.name: bindings[name] for f in fields(cls)})
    service = TrainingAssetPreparation(ports(TrainingAssetPolicy), ports(TrainingAssetPersistence))
    bindings.update({name: getattr(service, name) for name in NAMES})
    return service


class PreparationContract(unittest.TestCase):
    def fixture(self):
        b = dict(accessory_uid=lambda item: item['id'], accessory_material_type=lambda item: item.get('kind', 'object'),
                 clean_sprite_assets=lambda item: item.get('sprites', []), candidate_image_jobs=lambda item: item.get('jobs', []),
                 _business_files=SimpleNamespace(exists=lambda path: str(path) == str(Path('/pose.png'))),
                 POSE_COLLECTION_GRID_POSITIONS=tuple(range(9)), clean_sprites_policy_complete=lambda item, sprites: item.get('complete', False),
                 preprocess_object_clean_sprites=Mock(return_value=True), canonical_text_assets=lambda item: item.get('text_assets', []),
                 canonical_text_assets_complete=lambda item, *args: item.get('complete', False),
                 normalize_accessory_assets=Mock(return_value={'complete': True}),
                 object_photo_highlight_source_paths=lambda item: item.get('photos', []),
                 photo_highlight_clean_sprites_ready=lambda item, paths: item.get('ready', False),
                 PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES=3, HTTPException=HTTPException,
                 merge_scoped_accessory_updates=Mock(), save_config=Mock())
        return create(b), b

    def test_sprite_filter_force_and_nonboolean_result(self):
        s, b = self.fixture()
        text = {'id': 't', 'kind': 'text'}
        ready = {'id': 'r', 'sprites': list(range(18)), 'jobs': [{'output_path': '/pose.png'}] * 3, 'complete': True}
        pending = {'id': 'p', 'sprites': ['old'], 'jobs': [{'output_path': '/pose.png'}]}
        marker = object()
        b['preprocess_object_clean_sprites'].return_value = marker
        result = s.ensure_object_clean_sprites_for_selection({'accessories': [text, ready, pending]}, [])
        self.assertIs(result, marker)
        b['preprocess_object_clean_sprites'].assert_called_once_with(pending, allow_ai_cutout=True, force=True)
        b['preprocess_object_clean_sprites'].reset_mock()
        self.assertFalse(s.ensure_object_clean_sprites_for_selection({'accessories': [pending]}, ['other']))
        b['preprocess_object_clean_sprites'].assert_not_called()

    def test_intermediate_or_missing_outputs_do_not_force(self):
        s, b = self.fixture()
        pending = {'id': 'p', 'sprites': ['old'], 'jobs': [{'output_path': '/pose.png', 'intermediate': True}, {'output_path': '/missing'}]}
        s.ensure_object_clean_sprites_for_selection({'accessories': [pending]}, ['p'])
        b['preprocess_object_clean_sprites'].assert_called_once_with(pending, allow_ai_cutout=True, force=False)

    def test_empty_and_missing_ids_preserve_partial_timestamp(self):
        s, b = self.fixture()
        with self.assertRaises(HTTPException) as raised:
            s.ensure_training_normalized_assets_for_selection({}, [])
        self.assertEqual(raised.exception.status_code, 400)
        item = {'id': 'present', 'kind': 'text', 'complete': True}
        with patch.object(time, 'time', return_value=42.8), self.assertRaises(HTTPException) as raised:
            s.ensure_training_normalized_assets_for_selection({'accessories': [item]}, ['z', 'present', 'a'])
        self.assertEqual((raised.exception.status_code, raised.exception.detail), (404, '配件不存在: a, z'))
        self.assertEqual(item['normalized_for_training_at'], 42)
        b['normalize_accessory_assets'].assert_not_called()

    def test_text_normalization_and_final_failure(self):
        s, b = self.fixture()
        item = {'id': 't', 'kind': 'text', 'normalization_deferred': True}
        self.assertTrue(s.ensure_training_normalized_assets_for_selection({'accessories': [item]}, ['t']))
        self.assertFalse(item['normalization_deferred'])
        self.assertTrue(item['complete'])
        broken = {'id': 'x', 'name': 'Bad', 'kind': 'text'}
        b['normalize_accessory_assets'].return_value = {'partial': True}
        with self.assertRaises(HTTPException) as raised:
            s.ensure_training_normalized_assets_for_selection({'accessories': [broken]}, ['x'])
        self.assertEqual((raised.exception.status_code, raised.exception.detail), (409, '配件 Bad 的文字规范化文件生成失败'))
        self.assertTrue(broken['partial'])
        self.assertNotIn('normalized_for_training_at', broken)

    def test_photo_requirements_and_ready_timestamp_without_changed(self):
        s, _ = self.fixture()
        for item, message in [({'id': 'o'}, '至少需要 3 张'), ({'id': 'o', 'photos': [1, 2, 3]}, '尚未生成'), ({'id': 'o', 'ready': True}, '规范化文件生成失败')]:
            with self.assertRaises(HTTPException) as raised:
                s.ensure_training_normalized_assets_for_selection({'accessories': [item]}, ['o'])
            self.assertEqual(raised.exception.status_code, 409)
            self.assertIn(message, raised.exception.detail)
        item = {'id': 'o', 'ready': True, 'sprites': ['sprite']}
        with patch.object(time, 'time', return_value=88.7):
            self.assertFalse(s.ensure_training_normalized_assets_for_selection({'accessories': [item]}, ['o']))
        self.assertEqual(item['normalized_for_training_at'], 88)

    def test_request_saves_partial_http_error_but_not_other_errors(self):
        s, b = self.fixture()
        events = []
        full, scoped, user = {}, {'accessories': []}, {'id': 'u'}
        failure = HTTPException(409, 'incomplete')
        b['ensure_training_normalized_assets_for_selection'] = Mock(side_effect=failure)
        b['merge_scoped_accessory_updates'].side_effect = lambda *args: events.append(('merge', args))
        b['save_config'].side_effect = lambda *args: events.append(('save', args))
        with self.assertRaises(HTTPException) as raised:
            s.ensure_training_assets_for_request(full, scoped, user, ['a'])
        self.assertIs(raised.exception, failure)
        self.assertEqual(events, [('merge', (full, scoped, user)), ('save', (full,))])
        events.clear()
        b['ensure_training_normalized_assets_for_selection'].side_effect = ValueError('failed')
        with self.assertRaises(ValueError):
            s.ensure_training_assets_for_request(full, scoped, user, ['a'])
        self.assertEqual(events, [])

    def test_request_changed_result_and_persistence_failure(self):
        s, b = self.fixture()
        marker = object()
        b['ensure_training_normalized_assets_for_selection'] = Mock(return_value=marker)
        self.assertIs(s.ensure_training_assets_for_request({}, {}, {}, ['a']), marker)
        b['save_config'].assert_called_once()
        b['save_config'].reset_mock()
        b['ensure_training_normalized_assets_for_selection'].return_value = False
        self.assertFalse(s.ensure_training_assets_for_request({}, {}, {}, ['a']))
        b['save_config'].assert_not_called()
        b['ensure_training_normalized_assets_for_selection'].side_effect = HTTPException(404)
        b['merge_scoped_accessory_updates'].side_effect = RuntimeError('merge failed')
        with self.assertRaisesRegex(RuntimeError, 'merge failed'):
            s.ensure_training_assets_for_request({}, {}, {}, ['a'])
        b['save_config'].assert_not_called()

    @unittest.skipIf(BASELINE, 'candidate composition only')
    def test_explicit_assembly_and_isolation(self):
        from local_inspection_service.training.training_asset_preparation_ports import TrainingAssetPolicy, TrainingAssetPersistence
        tree = ast.parse((ROOT / 'local_inspection_service/server.py').read_text(encoding='utf-8'))
        assignment = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_training_asset_preparation' for t in n.targets))
        for group, cls in zip(assignment.value.keywords, (TrainingAssetPolicy, TrainingAssetPersistence)):
            self.assertEqual({k.arg for k in group.value.keywords}, {f.name for f in fields(cls)})
            for getter in group.value.keywords:
                self.assertIsInstance(getter.value, ast.Lambda)
                self.assertEqual(getter.value.body.id, getter.arg)
                self.assertFalse(getter.value.args.args)
        a, ab = self.fixture()
        b, bb = self.fixture()
        for service in (a, b, a):
            self.assertFalse(service.ensure_object_clean_sprites_for_selection({'accessories': []}, []))
        ab['preprocess_object_clean_sprites'].assert_not_called()
        bb['preprocess_object_clean_sprites'].assert_not_called()
        for name in NAMES:
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            self.assertIsInstance(node.body[0], ast.Return)
            self.assertEqual(node.body[0].value.func.attr, name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
