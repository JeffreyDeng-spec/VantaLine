"""Automatic-optimization domain assembly without paid or physical I/O."""
import ast
import copy
from dataclasses import fields
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import typing
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from canonical_application_source_contract import read_checked_application_source
from local_inspection_service.training import workflow_composition as composition
from local_inspection_service.training import core_composition, execution_composition
from local_inspection_service.runtime.training_tasks import TrainingThreadLifecycle, TrainingRuntimeClosed
from smoke_auto_optimization_execution_composition import native_owner


def structure(node):
    return ast.dump(node, include_attributes=False)


def verify_source(source):
    fixture = json.loads((ROOT / 'tests/backend_contract/auto_optimization_workflow_ports.json').read_text())
    tree = ast.parse(source)
    protected = {'_auto_optimization_workflows', *fixture['aliases']}
    assignments = {}
    imports = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in protected:
                    assert target.id not in assignments, 'duplicate owner'
                    assignments[target.id] = node
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            assert not (isinstance(node.target, ast.Name) and node.target.id in protected), 'shadowed owner'
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assert node.name not in protected, 'shadowed owner'
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                binding = alias.asname or (alias.name.split('.')[0] if isinstance(node, ast.Import) else alias.name)
                assert binding not in protected, 'owner import shadow'
                imports.setdefault(binding, []).append(node)
    call = assignments['_auto_optimization_workflows'].value
    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == 'AutoOptimizationWorkflows'
    assert not call.args and len(call.keywords) == len(fixture['arguments'])
    actual = {keyword.arg: keyword.value for keyword in call.keywords}
    assert set(actual) == set(fixture['arguments'])
    for name, value in fixture['arguments'].items():
        assert structure(actual[name]) == structure(ast.parse(value, mode='eval').body), name
    constructors = {'AutoOptimizationWorkflows', 'AutoOptimizationCore', 'AutoOptimizationExecution', *(value.func.id for value in actual.values() if isinstance(value, ast.Call) and isinstance(value.func, ast.Name))}
    for name in constructors:
        matches = imports.get(name, [])
        assert len(matches) == 1 and isinstance(matches[0], ast.ImportFrom), name
        assert matches[0].level == 1
        expected = 'training.workflow_composition' if name in ('AutoOptimizationWorkflows', 'AutoOptimizationStatusLookups', 'AutoOptimizationStatusProjection') else 'training.execution_composition' if name.startswith('External') or name == 'AutoOptimizationExecution' else 'runtime.training_tasks' if name == 'TrainingThreadLifecycle' else 'training.core_composition'
        assert matches[0].module == expected, name
        alias = next(alias for alias in matches[0].names if (alias.asname or alias.name) == name)
        assert alias.name == name, 'wrong constructor imported under expected binding'
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                assert node.name != name
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                assert not any(isinstance(target, ast.Name) and target.id == name for target in targets)
        assert matches[0].lineno < assignments['_auto_optimization_workflows'].lineno, name
    for alias, value in fixture['aliases'].items():
        assert structure(assignments[alias].value) == structure(ast.parse(value, mode='eval').body), alias
    for name, value in fixture['root_wrappers'].items():
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert structure(node) == structure(ast.parse(value).body[0]), name
    for name in fixture['supplied_fields_defined_before_core']:
        bindings = [node for node in tree.body if (isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name) or (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))]
        assert bindings and all(node.lineno < assignments['_auto_optimization_workflows'].lineno for node in bindings), name
    return fixture


def verify_composition_source(source):
    tree = ast.parse(source)
    protected = {'AutoOptimizationCore': 'core_composition', 'AutoOptimizationExecution': 'execution_composition', 'StatusLookups': 'core_composition', 'StatusProjection': 'core_composition'}
    for binding, expected_module in protected.items():
        imports = []
        for node in tree.body:
            if isinstance(node, (ast.ImportFrom, ast.Import)):
                for alias in node.names:
                    selected = alias.asname or (alias.name.split('.')[0] if isinstance(node, ast.Import) else alias.name)
                    if selected == binding: imports.append((node, alias))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                assert node.name != binding
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                assert not any(isinstance(target, ast.Name) and target.id == binding for target in targets)
        assert len(imports) == 1
        node, alias = imports[0]
        assert isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == expected_module and alias.name == binding
    definitions = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'AutoOptimizationWorkflows']
    assert len(definitions) == 1, 'duplicate workflow owner'
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name != 'AutoOptimizationWorkflows'
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            assert not any(isinstance(target, ast.Name) and target.id == 'AutoOptimizationWorkflows' for target in targets)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            assert not any((alias.asname or (alias.name.split('.')[0] if isinstance(node, ast.Import) else alias.name)) == 'AutoOptimizationWorkflows' for alias in node.names)
    cls = definitions[0]
    init = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == '__init__')
    calls = {node.targets[0].attr: node.value for node in init.body if isinstance(node, ast.Assign)}
    assert list(calls) == ['core', 'execution']
    for target, kind in [('core', core_composition.AutoOptimizationCore), ('execution', execution_composition.AutoOptimizationExecution)]:
        call = calls[target]
        assert call.func.id == kind.__name__ and not call.args
        import inspect
        assert [keyword.arg for keyword in call.keywords] == list(inspect.signature(kind.__init__).parameters)[1:]
        for keyword in call.keywords:
            if target == 'core' and keyword.arg in ('status_state', 'status_policy'):
                port = core_composition.StatusLookups if keyword.arg == 'status_state' else core_composition.StatusProjection
                assert keyword.value.func.id == port.__name__
                assert [field.arg for field in keyword.value.keywords] == [field.name for field in fields(port)]
                for field in keyword.value.keywords:
                    expected = 'lambda: self.' + field.arg if field.arg in ('start_auto_optimize_label_worker', 'auto_optimize_public_sprite_pool') else keyword.arg + '.' + field.arg
                    assert structure(field.value) == structure(ast.parse(expected, mode='eval').body)
            else:
                expected = 'self.core' if target == 'execution' and keyword.arg == 'core' else keyword.arg
                assert structure(keyword.value) == structure(ast.parse(expected, mode='eval').body)
    for name, body in [('start_auto_optimize_label_worker', 'return self.execution.start_auto_optimize_label_worker(task_id)'), ('auto_optimize_public_sprite_pool', 'return self.execution.auto_optimize_public_sprite_pool(state, limit)')]:
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
        assert len(method.body) == 1 and structure(method.body[0]) == structure(ast.parse(body).body[0])


def arguments(test, account, *, poison=False):
    captured = {}
    old_core = core_composition.AutoOptimizationCore.__init__
    old_execution = execution_composition.AutoOptimizationExecution.__init__
    def core(self, **values):
        captured['core'] = dict(values)
        old_core(self, **values)
    def execution(self, **values):
        captured['execution'] = dict(values)
        old_execution(self, **values)
    with patch.object(core_composition.AutoOptimizationCore, '__init__', core), patch.object(execution_composition.AutoOptimizationExecution, '__init__', execution):
        fixture, original = native_owner(test, account)
    values = captured['core']
    for key, kind in [('status_state', composition.AutoOptimizationStatusLookups), ('status_policy', composition.AutoOptimizationStatusProjection)]:
        old = values[key]
        values[key] = kind(**{field.name: getattr(old, field.name) for field in fields(kind)})
    for key, value in captured['execution'].items():
        if key not in ('core', 'settings', 'runtime'):
            values[key] = value
    scope = captured['core']['shadow_runtime'].scope
    selected = []
    def forbidden(*args, **kwargs):
        selected.append((args, kwargs))
        raise AssertionError('constructor selected a capability')
    for name in ('shadow_runtime', 'label_runtime', 'scheduling_runtime'):
        values[name] = TrainingThreadLifecycle(scope=forbidden if poison else scope)
    if poison:
        for key, value in list(values.items()):
            if hasattr(type(value), '__dataclass_fields__'):
                values[key] = type(value)(**{field.name: forbidden for field in fields(value)})
            elif callable(value):
                values[key] = forbidden
    return values, fixture, original, selected


def assemble(test, account):
    values, fixture, original, _ = arguments(test, account)
    owner = composition.AutoOptimizationWorkflows(**values)
    fixture.core = owner.core
    owner.execution.label_generation = original.label_generation
    test.addCleanup(lambda: owner.core.shadow.close(3))
    test.addCleanup(lambda: owner.execution.label_processing.close(3))
    test.addCleanup(lambda: owner.execution.training_scheduling.close(3))
    return fixture, owner


class Contracts(unittest.TestCase):
    def test_parent_root_wiring_and_actual_composition_mutants(self):
        source = read_checked_application_source(ROOT / 'local_inspection_service/server.py')
        verify_source(source)
        for old, new in [('_auto_optimization_workflows.core', '_auto_optimization_workflows.execution'), ('shadow_resolver=resolve_model_profiles,', 'shadow_resolver=lambda: None,'), ('from .training.workflow_composition import', 'from training.workflow_composition import')]:
            self.assertIn(old, source)
            with self.assertRaises(AssertionError): verify_source(source.replace(old, new, 1))
        for old, new in [('AutoOptimizationStatusLookups, AutoOptimizationStatusProjection', 'AutoOptimizationStatusProjection as AutoOptimizationStatusLookups, AutoOptimizationStatusProjection'), ('    ExternalRequestActions,', '    ExternalRequestAccess as ExternalRequestActions,'), ('AutoOptimizationCore, StateStorage', 'StateStorage as AutoOptimizationCore, StateStorage')]:
            self.assertIn(old, source)
            with self.assertRaises(AssertionError): verify_source(source.replace(old, new, 1))
        for extra in ('_auto_optimization_workflows += None', '_auto_optimization_core: object = None', 'import os as AutoOptimizationWorkflows'):
            with self.assertRaises(AssertionError): verify_source(source + '\n' + extra)
        source = Path(composition.__file__).read_text()
        verify_composition_source(source)
        for extra in ('AutoOptimizationCore = None', 'AutoOptimizationExecution: object = None', 'from collections import deque as StatusLookups', 'def StatusProjection(): pass', 'class AutoOptimizationWorkflows: pass', 'AutoOptimizationWorkflows = None', 'AutoOptimizationWorkflows: object = None', 'AutoOptimizationWorkflows += None', 'import os as AutoOptimizationWorkflows'):
            with self.assertRaises(AssertionError): verify_composition_source(source + '\n' + extra)
        for old, new in [('lambda: self.start_auto_optimize_label_worker', 'lambda: self.auto_optimize_public_sprite_pool'), ('return self.execution.auto_optimize_public_sprite_pool', 'return self.core.public_auto_optimize_state')]:
            self.assertIn(old, source)
            with self.assertRaises(AssertionError): verify_composition_source(source.replace(old, new, 1))

    def test_constructor_inert_types_and_failure_does_not_publish(self):
        values, _, _, selected = arguments(self, 'A', poison=True)
        owner = composition.AutoOptimizationWorkflows(**values)
        self.assertEqual(selected, [])
        self.assertIs(owner.core.settings, owner.execution.settings)
        self.assertIs(owner.core.runtime, owner.execution.runtime)
        self.assertIs(owner.execution.core, owner.core)
        self.assertIsNot(owner.core.shadow.runtime, owner.execution.label_processing.runtime)
        self.assertIsNot(owner.execution.label_processing.runtime, owner.execution.training_scheduling.runtime)
        typing.get_type_hints(composition.AutoOptimizationWorkflows.__init__)
        typing.get_type_hints(composition.AutoOptimizationStatusLookups)
        typing.get_type_hints(composition.AutoOptimizationStatusProjection)
        failure = RuntimeError('synthetic construction failure')
        with patch.object(composition.AutoOptimizationExecution, '__init__', side_effect=failure):
            with self.assertRaises(RuntimeError) as raised:
                composition.AutoOptimizationWorkflows(**values)
        self.assertIs(raised.exception, failure)
        self.assertEqual(selected, [])

    def test_same_id_status_to_native_execution_remains_account_bound(self):
        a, wa = assemble(self, 'A')
        b, wb = assemble(self, 'B')
        self.assertIsNot(wa.core.runtime, wb.core.runtime)
        for fixture, owner in [(a, wa), (b, wb)]:
            self.assertIs(owner.core.status.state.start_auto_optimize_label_worker().__self__, owner)
            self.assertIs(owner.core.status.policy.auto_optimize_public_sprite_pool().__self__, owner)
            result = owner.core.status.auto_optimize_update_settings('same', {'enabled': True})
            self.assertEqual(result['task_id'], 'same')
            self.assertTrue(owner.execution.label_processing.close(3))
            self.assertEqual(fixture.records['same']['raw_json']['samples'][0]['label_status'], 'failed')
            generations = [event[3] for event in fixture.events if event[0] == 'synthetic_generation']
            self.assertEqual(len(generations), 1)
            self.assertEqual(generations[0]['training_vision']['version'], 7)
        self.assertEqual(a.records['same']['raw_json']['samples'][0]['owner_user_id'], 'A')
        self.assertEqual(b.records['same']['raw_json']['samples'][0]['owner_user_id'], 'B')
        with self.assertRaises(TrainingRuntimeClosed): wa.start_auto_optimize_label_worker('same')
        self.assertIsNone(wb.execution.start_auto_optimize_training_check_worker('same'))
        self.assertTrue(wb.execution.training_scheduling.close(3))

    def test_both_saved_callbacks_select_execution_after_argument_effects(self):
        owner = object.__new__(composition.AutoOptimizationWorkflows)
        for method in ('start_auto_optimize_label_worker', 'auto_optimize_public_sprite_pool'):
            events = []
            owner.execution = SimpleNamespace(**{method: lambda *args: events.append('old')})
            saved = getattr(owner, method)
            class Arguments:
                def __iter__(self):
                    owner.execution = SimpleNamespace(**{method: lambda *args: events.append('new')})
                    return iter(('same',) if method.startswith('start') else ({}, 80))
            saved(*Arguments())
            self.assertEqual(events, ['new'])


if __name__ == '__main__':
    unittest.main()
