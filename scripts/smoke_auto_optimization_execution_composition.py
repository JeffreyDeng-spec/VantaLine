"""Actual execution owner, native model binding and synthetic state isolation."""
import ast
import copy
from dataclasses import fields
import inspect
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import typing
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from canonical_application_source_contract import read_checked_application_source
from local_inspection_service.training import execution_composition as composition
from local_inspection_service.runtime.training_tasks import TrainingThreadLifecycle, TrainingRuntimeClosed
from local_inspection_service.model_profiles.snapshots import pinned
from smoke_auto_optimization_core_composition import assemble, seed


def structure(value):
    return ast.dump(value, include_attributes=False)


def verify_source(source):
    tree = ast.parse(source)
    if any(isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == '_auto_optimization_workflows' for target in node.targets) for node in tree.body):
        from smoke_auto_optimization_workflow_composition import verify_source as verify_owned_workflows
        return verify_owned_workflows(source)
    fixture = json.loads((ROOT / 'tests/backend_contract/auto_optimization_execution_ports.json').read_text())
    tree = ast.parse(source)
    protected = {'_auto_optimization_execution', *fixture['aliases']}
    assignments = {}
    imported = {}
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
            for name in node.names:
                binding = name.asname or (name.name.split('.')[0] if isinstance(node, ast.Import) else name.name)
                assert binding not in protected, 'shadowed owner import'
                imported.setdefault(binding, []).append(node)
    call = assignments['_auto_optimization_execution'].value
    assert isinstance(call, ast.Call) and structure(call.func) == structure(ast.Name('AutoOptimizationExecution', ast.Load()))
    actual = {keyword.arg: keyword.value for keyword in call.keywords}
    assert len(actual) == len(call.keywords) and set(actual) == set(fixture['arguments'])
    for name, expected in fixture['arguments'].items():
        assert structure(actual[name]) == structure(ast.parse(expected, mode='eval').body), name
    constructors = {'AutoOptimizationExecution', *(v.func.id for v in actual.values() if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id.startswith('External'))}
    for name in constructors:
        selected = imported.get(name, [])
        assert len(selected) == 1 and isinstance(selected[0], ast.ImportFrom)
        assert selected[0].level == 1 and selected[0].module == 'training.execution_composition'
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                assert node.name != name, 'shadowed constructor'
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                assert not any(isinstance(t, ast.Name) and t.id == name for t in targets), 'shadowed constructor'
    for alias, field in fixture['aliases'].items():
        assert structure(assignments[alias].value) == structure(ast.parse('_auto_optimization_execution.' + field, mode='eval').body)
    for name, expected in fixture['wrapper_sources'].items():
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert structure(node) == structure(ast.parse(expected).body[0]), name
    return fixture



def verify_execution_source(source):
    fixture = json.loads((ROOT / 'tests/backend_contract/auto_optimization_execution_ports.json').read_text())
    module = ast.parse(source)
    protected = fixture['constructor_imports']
    for binding, expected in protected.items():
        imports = []
        for node in module.body:
            if isinstance(node, (ast.ImportFrom, ast.Import)):
                for alias in node.names:
                    selected = alias.asname or (alias.name.split('.')[0] if isinstance(node, ast.Import) else alias.name)
                    if selected == binding:
                        imports.append((node, alias))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                assert node.name != binding, 'shadowed construction binding'
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                assert not any(isinstance(target, ast.Name) and target.id == binding for target in targets), 'shadowed construction binding'
        assert len(imports) == 1, binding
        node, alias = imports[0]
        assert isinstance(node, ast.ImportFrom) and node.level == expected['level'] and node.module == expected['module'] and alias.name == expected['original'], binding
    cls = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == 'AutoOptimizationExecution')
    constructor = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    assignments = {}
    for node in constructor.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'self':
                    assert target.attr not in assignments, 'duplicate component'
                    assignments[target.attr] = node.value
    edges = {(edge['service'], edge['port'], edge['field']): edge for edge in fixture['owned_edges']}
    assert len(edges) == len(fixture['owned_edges']) == 62
    runtime_names = {'_auto_optimize_lock': 'lock', '_auto_optimize_label_threads': 'label_threads'}
    seen = set()
    for alias, original in fixture['original_constructors'].items():
        service = fixture['aliases'][alias]
        parent = ast.parse(original).body[0].value
        actual = assignments[service]
        assert isinstance(actual, ast.Call) and structure(actual.func) == structure(parent.func), service
        assert len(actual.args) == len(parent.args) and [k.arg for k in actual.keywords] == [k.arg for k in parent.keywords], service
        old_arguments = [ast.keyword(arg=None, value=value) for value in parent.args] + parent.keywords
        new_arguments = [ast.keyword(arg=None, value=value) for value in actual.args] + actual.keywords
        for old, new in zip(old_arguments, new_arguments):
            if old.arg == 'runtime':
                expected = ast.parse('label_runtime' if service == 'label_processing' else 'scheduling_runtime', mode='eval').body
            elif old.arg == 'model_resolver':
                expected = ast.parse('model_resolver', mode='eval').body
            elif old.arg == 'negative_samples_default':
                expected = ast.parse('negative_samples_default', mode='eval').body
            else:
                assert isinstance(old.value, ast.Call) and isinstance(new.value, ast.Call)
                assert structure(old.value.func) == structure(new.value.func) and not new.value.args
                assert [k.arg for k in old.value.keywords] == [k.arg for k in new.value.keywords]
                port = old.value.func.id
                for old_field, new_field in zip(old.value.keywords, new.value.keywords):
                    key = (service, port, old_field.arg)
                    edge = edges.get(key)
                    if edge:
                        seen.add(key)
                        if edge.get('runtime'):
                            expression = 'lambda: self.runtime.' + runtime_names[old_field.arg]
                        else:
                            method = edge['method']
                            selected = {'auto_optimize_label_worker': 'pinned_label_worker', 'auto_optimize_training_check_worker': 'pinned_check_worker'}.get(method, method)
                            expression = 'lambda: self.' + selected
                        expected_field = ast.parse(expression, mode='eval').body
                    elif isinstance(old_field.value, ast.Attribute) and isinstance(old_field.value.value, ast.Name) and old_field.value.value.id == '_auto_optimization_settings':
                        expected_field = ast.parse('self.settings.' + old_field.value.attr, mode='eval').body
                    else:
                        expected_field = ast.parse('external_' + port + '.' + old_field.arg, mode='eval').body
                    assert structure(new_field.value) == structure(expected_field), key
                continue
            assert structure(new.value) == structure(expected), (service, old.arg)
    assert seen == set(edges)
    for field, method in [('pinned_label_worker', 'auto_optimize_label_worker'), ('pinned_check_worker', 'auto_optimize_training_check_worker')]:
        expected = ast.parse('pinned(model_resolver, lambda identity: self.load_auto_optimize_state(identity))(self.' + method + ')', mode='eval').body
        assert structure(assignments[field]) == structure(expected), field
    imports = [n for n in module.body if isinstance(n, ast.ImportFrom) and any(a.name == 'pinned' for a in n.names)]
    assert len(imports) == 1 and imports[0].level == 2 and imports[0].module == 'model_profiles.snapshots'
    return fixture


def poisoned_owner():
    selections = []
    def forbidden(*args, **kwargs):
        selections.append((args, kwargs))
        raise AssertionError('constructor selected a capability')
    groups = {name: kind for name, kind in vars(composition).items() if name.startswith('External') and isinstance(kind, type)}
    arguments = {'external_' + name.removeprefix('External'): kind(**{field.name: forbidden for field in fields(kind)}) for name, kind in groups.items()}
    arguments.update(core=SimpleNamespace(), settings=composition.AutoOptimizationSettings(2), runtime=composition.AutoOptimizationRuntimeState(), negative_samples_default=2, model_resolver=forbidden, label_runtime=TrainingThreadLifecycle(scope=forbidden), scheduling_runtime=TrainingThreadLifecycle(scope=forbidden))
    return composition.AutoOptimizationExecution(**arguments), selections


def native_owner(test, owner):
    fixture = assemble(test)
    state = seed(fixture, owner=owner)
    state['samples'][0]['label_status'] = 'pending'
    fixture.core.save_auto_optimize_state(state)
    original = copy.deepcopy(fixture.records['same']['raw_json']['model_profiles'])
    fixture.snapshot['training_vision']['version'] = 9
    values = dict(fixture.values)
    import concurrent.futures
    values.update(image_generation_settings=lambda: {'configured': True, 'model': 'synthetic'}, AUTO_OPTIMIZE_MASK_MAX_PARALLEL=2, ThreadPoolExecutor=concurrent.futures.ThreadPoolExecutor, as_completed=concurrent.futures.as_completed, output_write_dir_for_owner=lambda kind, account: fixture.values['AUTO_OPTIMIZE_DIR'], AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT=2)
    def forbidden(*args, **kwargs):
        raise AssertionError('unexpected synthetic capability selected')
    groups = {name: kind for name, kind in vars(composition).items() if name.startswith('External') and isinstance(kind, type)}
    arguments = {'external_' + name.removeprefix('External'): kind(**{field.name: lambda name=field.name: values.get(name, forbidden) for field in fields(kind)}) for name, kind in groups.items()}
    arguments.update(core=fixture.core, settings=fixture.core.settings, runtime=fixture.core.runtime, negative_samples_default=2, model_resolver=lambda: fixture.resolver, label_runtime=TrainingThreadLifecycle(scope=fixture.core.shadow.runtime.scope), scheduling_runtime=TrainingThreadLifecycle(scope=fixture.core.shadow.runtime.scope))
    execution = composition.AutoOptimizationExecution(**arguments)
    def generate(*args):
        selected = fixture.resolver.current_snapshot()
        assert selected == original
        fixture.events.append(('synthetic_generation', threading.get_ident(), owner, copy.deepcopy(selected)))
        return [], [{'status': 'failed', 'reason': 'synthetic-no-paid-model'}], {'api_calls': []}
    execution.label_generation = SimpleNamespace(auto_optimize_generate_labels_for_sample=generate)
    test.addCleanup(lambda: execution.label_processing.close(3))
    test.addCleanup(lambda: execution.training_scheduling.close(3))
    return fixture, execution


class Contracts(unittest.TestCase):
    def test_exact_parent_ports_aliases_and_mutants(self):
        source = read_checked_application_source(ROOT / 'local_inspection_service/server.py')
        verify_source(source)
        execution_source = Path(composition.__file__).read_text()
        verify_execution_source(execution_source)
        for old, new in [('load_auto_optimize_state=lambda: self.load_auto_optimize_state,', 'load_auto_optimize_state=lambda: self.save_auto_optimize_state,'), ('lambda: self.auto_optimize_load_sprite', 'lambda: self.core.auto_optimize_load_sprite'), ('from ..model_profiles.snapshots import pinned', 'from ..model_profiles.dependencies import pinned')]:
            self.assertIn(old, execution_source)
            with self.assertRaises(AssertionError):
                verify_execution_source(execution_source.replace(old, new, 1))
        for extra in ('pinned = None', 'pinned: object = None', 'pinned += None', 'from collections import deque as pinned', 'def pinned(*args): pass', 'class AutoOptimizationRequests: pass', 'import os as RequestState'):
            with self.assertRaises(AssertionError):
                verify_execution_source(execution_source + '\n' + extra + '\n')
        for old, new in [('_auto_optimization_execution.label_processing', '_auto_optimization_execution.label_generation'), ('model_resolver=resolve_model_profiles,', 'model_resolver=None,'), ('from .training.execution_composition import (', 'from training.execution_composition import (')]:
            self.assertIn(old, source)
            with self.assertRaises(AssertionError):
                verify_source(source.replace(old, new, 1))
        for extra in ('_auto_optimization_execution += None', '_auto_optimization_label_processing: object = None', 'import os as AutoOptimizationExecution', 'def AutoOptimizationExecution(): pass'):
            with self.assertRaises(AssertionError):
                verify_source(source + '\n' + extra + '\n')

    def test_constructor_poison_and_all_annotations(self):
        owner, selections = poisoned_owner()
        self.assertEqual(selections, [])
        fixture = verify_execution_source(Path(composition.__file__).read_text())
        for edge in fixture['owned_edges']:
            component = getattr(owner, edge['service'])
            port = next(value for value in vars(component).values() if type(value).__name__ == edge['port'])
            selected = getattr(port, edge['field'])()
            if edge.get('runtime'):
                self.assertIs(selected, owner.runtime.lock if edge['field'] == '_auto_optimize_lock' else owner.runtime.label_threads)
            elif edge['method'] in ('auto_optimize_label_worker', 'auto_optimize_training_check_worker'):
                self.assertIs(selected, owner.pinned_label_worker if edge['method'] == 'auto_optimize_label_worker' else owner.pinned_check_worker)
                self.assertIs(selected.__wrapped__.__self__, owner)
            else:
                self.assertIs(selected.__self__, owner)
                self.assertIs(selected.__func__, getattr(type(owner), edge['method']))
        for name, kind in vars(composition).items():
            if name.startswith('External') and isinstance(kind, type):
                self.assertTrue(typing.get_type_hints(kind))
        for name, method in vars(type(owner)).items():
            if callable(method):
                typing.get_type_hints(method)

    def test_all_forwarders_select_owner_after_arguments(self):
        owner, _ = poisoned_owner()
        fixture = json.loads((ROOT / 'tests/backend_contract/auto_optimization_execution_ports.json').read_text())
        module = ast.parse((ROOT / 'local_inspection_service/training/execution_composition.py').read_text())
        cls = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == 'AutoOptimizationExecution')
        owner.core = SimpleNamespace(store=None, recommendations=None, readiness=None, status=None)
        for name in fixture['execution_forwarders'] + fixture['core_forwarders']:
            node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
            selected = node.body[0].value.func
            container = owner.core if isinstance(selected.value, ast.Attribute) and isinstance(selected.value.value, ast.Attribute) else owner
            field = selected.value.attr
            events = []
            old = SimpleNamespace(**{selected.attr: lambda *args, **kwargs: events.append('old')})
            new = SimpleNamespace(**{selected.attr: lambda *args, **kwargs: events.append('new')})
            setattr(container, field, old)
            fn = getattr(owner, name)
            parameters = inspect.signature(fn).parameters
            values = [object() for p in parameters.values() if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
            keywords = {p.name: object() for p in parameters.values() if p.kind == p.KEYWORD_ONLY}
            class Arguments:
                def __iter__(self):
                    setattr(container, field, new)
                    return iter(values)
            fn(*Arguments(), **keywords)
            self.assertEqual(events, ['new'], name)

    def test_actual_two_native_graphs_persist_failures_and_keep_snapshot(self):
        a, ea = native_owner(self, 'A')
        b, eb = native_owner(self, 'B')
        self.assertIs(ea.runtime, a.core.runtime)
        self.assertIs(eb.settings, b.core.settings)
        self.assertIsNot(ea.runtime.lock, eb.runtime.lock)
        ea.start_auto_optimize_label_worker('same')
        eb.start_auto_optimize_label_worker('same')
        self.assertTrue(ea.label_processing.close(5))
        self.assertTrue(eb.label_processing.close(5))
        for fixture, owner in ((a, 'A'), (b, 'B')):
            stored = fixture.records['same']['raw_json']
            self.assertEqual(stored['samples'][0]['label_status'], 'failed')
            self.assertEqual(stored['samples'][0]['owner_user_id'], owner)
            self.assertEqual(stored['samples'][0]['label_reject_reason'], 'synthetic-no-paid-model')
            self.assertEqual(len([event for event in fixture.events if event[0] == 'synthetic_generation']), 1)
            self.assertIsNone(fixture.resolver.current_snapshot())
            entries = [event for event in fixture.events if event[0] == 'model_enter']
            self.assertTrue(entries)
            self.assertTrue(all(event[2]['training_vision']['version'] == 7 for event in entries))
        before = copy.deepcopy(a.records)
        with self.assertRaises(TrainingRuntimeClosed):
            ea.start_auto_optimize_label_worker('same')
        self.assertEqual(before, a.records)
        eb.start_auto_optimize_training_check_worker('same')
        self.assertTrue(eb.training_scheduling.close(5))
        self.assertEqual(b.records['same']['raw_json']['samples'][0]['owner_user_id'], 'B')

    def test_missing_native_resolver_precedes_task_lookup(self):
        fixture, owner = native_owner(self, 'A')
        owner.pinned_label_worker = pinned(lambda: None, lambda key: owner.load_auto_optimize_state(key))(owner.auto_optimize_label_worker)
        before = copy.deepcopy(fixture.records)
        fixture.events.clear()
        failures = []
        with patch.object(threading, 'excepthook', side_effect=lambda event: failures.append(event.exc_value)):
            owner.start_auto_optimize_label_worker('same')
            self.assertTrue(owner.label_processing.close(5))
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], RuntimeError)
        self.assertEqual(before, fixture.records)
        self.assertFalse(any(event[0] in ('fetch', 'save', 'synthetic_generation') for event in fixture.events))
        self.assertEqual([event[0] for event in fixture.events], ['enter', 'exit'])

    def test_actual_public_worker_decorators_pin_once(self):
        fixture, owner = native_owner(self, 'A')
        source = ast.parse(read_checked_application_source(ROOT / 'local_inspection_service/server.py'))
        for name, alias, method, args in [('auto_optimize_label_worker', '_auto_optimization_label_processing', 'auto_optimize_label_worker', ('same',)), ('auto_optimize_training_check_worker', '_auto_optimization_training_scheduling', 'auto_optimize_training_check_worker', ('same', 0.0))]:
            node = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == name)
            seen = []
            namespace = {'pinned_model_profiles': pinned, 'resolve_model_profiles': lambda: fixture.resolver, 'load_auto_optimize_state': owner.load_auto_optimize_state, alias: SimpleNamespace(**{method: lambda *args: seen.append(fixture.resolver.current_snapshot())})}
            exec(compile(ast.Module(body=[copy.deepcopy(node)], type_ignores=[]), '<actual public worker>', 'exec'), namespace)
            fixture.events.clear()
            namespace[name](*args)
            self.assertEqual(len(seen), 1)
            self.assertEqual(seen[0]['training_vision']['version'], 7)
            self.assertEqual(len([event for event in fixture.events if event[0] == 'model_enter']), 1)
            self.assertIsNone(fixture.resolver.current_snapshot())


if __name__ == '__main__':
    unittest.main()
