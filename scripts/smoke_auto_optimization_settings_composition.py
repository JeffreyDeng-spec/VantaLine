"""Actual application bindings for stable auto-optimization settings capabilities."""
import ast
from dataclasses import fields, is_dataclass, replace
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from auto_optimization_test_ports import SETTINGS_CAPABILITIES


class CompositionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        cls.server = server
        cls.ports = []
        for value in vars(server).values():
            if isinstance(value, type) or not is_dataclass(value):
                continue
            for field in fields(value):
                port = getattr(value, field.name)
                if isinstance(port, type) or not is_dataclass(port):
                    continue
                for capability in fields(port):
                    if capability.name in SETTINGS_CAPABILITIES:
                        cls.ports.append((port, capability.name))

    def test_all_consumers_share_selected_owner(self):
        self.assertEqual(len(self.ports), 24)
        for port, name in self.ports:
            with self.subTest(name=name, port=type(port).__name__):
                callback = getattr(port, name)
                self.assertIs(callback.__self__, self.server._auto_optimization_settings)
                self.assertIs(callback.__func__, getattr(type(callback.__self__), name))
        for name in SETTINGS_CAPABILITIES:
            alias = getattr(self.server, name)
            self.assertIs(alias.__self__, self.server._auto_optimization_settings)

    def test_no_settings_root_lookup_or_function_forwarder(self):
        tree = ast.parse((ROOT / 'local_inspection_service/server.py').read_text(encoding='utf-8'))
        self.assertFalse(any(isinstance(n, ast.FunctionDef) and n.name in SETTINGS_CAPABILITIES for n in tree.body))
        references = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
                      and isinstance(n.ctx, ast.Load) and n.id in SETTINGS_CAPABILITIES]
        self.assertEqual(references, [])

    def test_root_alias_rebinding_does_not_rewire_consumers(self):
        selected = self.server._auto_optimization_settings
        with patch.object(self.server, '_auto_optimization_settings', object()):
            for name in SETTINGS_CAPABILITIES:
                with patch.object(self.server, name, side_effect=AssertionError('entry lookup')):
                    for port, field in self.ports:
                        if field == name:
                            self.assertIs(getattr(port, field).__self__, selected)
                            args = () if field == 'default_auto_optimize_settings' else ({},)
                            self.assertEqual(getattr(port, field)(*args), getattr(selected, field)(*args))

    def test_environment_is_live_and_errors_precede_overrides(self):
        policy = self.server._auto_optimization_status.policy
        with patch.dict(os.environ, {'VANTALINE_AUTO_OPT_EPOCHS': '7'}):
            self.assertEqual(policy.default_auto_optimize_settings()['training_epochs'], 7)
            os.environ['VANTALINE_AUTO_OPT_EPOCHS'] = '9'
            self.assertEqual(policy.auto_optimize_training_parameters({})['training_epochs'], 9)
            os.environ['VANTALINE_AUTO_OPT_EPOCHS'] = 'broken'
            with self.assertRaises(ValueError):
                policy.auto_optimize_training_parameters({'training_epochs': 11})

    def test_explicit_alternate_owner_is_isolated(self):
        from local_inspection_service.training.auto_optimization_settings import AutoOptimizationSettings
        first, second = AutoOptimizationSettings(2), AutoOptimizationSettings(7)
        source = self.server._auto_optimization_status.policy
        a = replace(source, **{name: getattr(first, name) for name in SETTINGS_CAPABILITIES})
        b = replace(source, **{name: getattr(second, name) for name in SETTINGS_CAPABILITIES})
        self.assertEqual(a.auto_optimize_negative_samples_per_real_image({}), 2)
        self.assertEqual(b.auto_optimize_negative_samples_per_real_image({}), 7)
        self.assertIs(source.default_auto_optimize_settings.__self__, self.server._auto_optimization_settings)


if __name__ == '__main__':
    unittest.main()
