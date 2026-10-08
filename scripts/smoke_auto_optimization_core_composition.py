"""Actual auto-optimization core wiring and synthetic native worker isolation."""
import ast
import copy
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import fields
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_inspection_service.training import core_composition as composition
from local_inspection_service.training.auto_optimization_runtime_state import AutoOptimizationRuntimeState
from local_inspection_service.training.auto_optimization_settings import AutoOptimizationSettings
from local_inspection_service.runtime.training_tasks import TrainingThreadLifecycle, TrainingRuntimeClosed
from local_inspection_service.model_profiles.service import Service

def structure(value):
    return ast.dump(value, include_attributes=False)

def verify_source(source):
    tree = ast.parse(source)
    if any(isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == '_auto_optimization_workflows' for target in node.targets) for node in tree.body):
        from smoke_auto_optimization_workflow_composition import verify_source as verify_owned_workflows
        return verify_owned_workflows(source)
    tree = ast.parse(source)
    fixture = json.loads((ROOT / 'tests/backend_contract/auto_optimization_core_ports.json').read_text())
    protected = {'_auto_optimization_core', *fixture['aliases']}
    nodes = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in protected:
                    if target.id in nodes:
                        raise AssertionError('duplicate owner assignment')
                    nodes[target.id] = node
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            if isinstance(node.target, ast.Name) and node.target.id in protected:
                raise AssertionError('shadowed owner assignment')
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assert node.name not in protected, 'shadowed owner definition'
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                binding = alias.asname or (alias.name.split('.')[0] if isinstance(node, ast.Import) else alias.name)
                assert binding not in protected, 'shadowed owner import'
    call = nodes['_auto_optimization_core'].value
    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == 'AutoOptimizationCore'
    groups = {'storage': 'StateStorage', 'state_policy': 'StatePolicy', 'cache': 'AutoOptimizationStateCache', 'readiness': 'ReadinessLookups', 'status_state': 'StatusLookups', 'status_policy': 'StatusProjection', 'shadow_state': 'ShadowPolicy', 'observation': 'ShadowImages', 'retirement': 'Retirement'}
    allowed = {'AutoOptimizationCore', *groups.values()}
    for key, expected_class in groups.items():
        actual = next(kw.value for kw in call.keywords if kw.arg == key)
        assert isinstance(actual, ast.Call) and isinstance(actual.func, ast.Name) and actual.func.id == expected_class
    for name in allowed:
        expected = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == 'training.core_composition' and n.level == 1 and any(a.name == name and a.asname in (None, name) for a in n.names)]
        assert len(expected) == 1, name
        for n in tree.body:
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                for alias in n.names:
                    binding = alias.asname or (alias.name.split('.')[0] if isinstance(n, ast.Import) else alias.name)
                    if binding == name:
                        assert n is expected[0], name
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                assert n.name != name
            if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                assert not any(isinstance(t, ast.Name) and t.id == name for t in targets)
    arguments = {kw.arg: kw.value for kw in call.keywords}
    assert len(arguments) == len(call.keywords)
    expected_keys = set(fixture['ports']) - {'ownership'} | set(fixture['ports']['ownership'])
    assert set(arguments) == expected_keys
    for group, values in fixture['ports'].items():
        if group == 'ownership':
            for key, value in values.items():
                assert structure(arguments[key]) == structure(ast.parse(value, mode='eval').body)
        elif isinstance(values, dict):
            assert isinstance(arguments[group], ast.Call)
            actual = {kw.arg: kw.value for kw in arguments[group].keywords}
            assert len(actual) == len(arguments[group].keywords) and set(actual) == set(values)
            for key, value in values.items():
                assert structure(actual[key]) == structure(ast.parse(value, mode='eval').body), (group, key)
        else:
            assert structure(arguments[group]) == structure(ast.parse(values, mode='eval').body)
    for name, field in fixture['aliases'].items():
        assert structure(nodes[name].value) == structure(ast.parse('_auto_optimization_core.' + field, mode='eval').body)

def assemble(test, *, poison=False):
    temporary = tempfile.TemporaryDirectory(prefix='auto-core-synthetic-')
    test.addCleanup(temporary.cleanup)
    directory = Path(temporary.name)
    records, events, cache = {}, [], {}
    request_cache = ContextVar('synthetic-auto-read-cache', default=None)
    def fetch(table, key):
        events.append(('fetch', threading.get_ident()))
        return copy.deepcopy(records.get(key['task_id']))
    def save(table, row):
        events.append(('save', threading.get_ident()))
        records[row['task_id']] = copy.deepcopy(row)
    repository = SimpleNamespace(fetch_by_primary_key=fetch, fetch_all=lambda table: copy.deepcopy(list(records.values())), upsert_row=save)
    snapshot = {'training_vision': {'id': 'synthetic', 'version': 7}}
    class Resolver(Service):
        def snapshot_for_record(self, record):
            return copy.deepcopy(snapshot)
        @contextmanager
        def scope(self, selected=None):
            events.append(('model_enter', threading.get_ident(), copy.deepcopy(selected)))
            try:
                with super().scope(selected):
                    yield
            finally:
                events.append(('model_exit', threading.get_ident()))
    resolver = Resolver(None)
    values = {
        'AUTO_OPTIMIZE_DIR': directory, 'AI_DETECTION_MODEL_ID': 'default',
        '_business_files': SimpleNamespace(exists=lambda p: False, read_text=lambda *a, **k: '{}', write_text=lambda *a, **k: None, glob=lambda *a: [], is_dir=lambda p: False, rmtree=lambda p: events.append(('rmtree', p))),
        'runtime_postgres_repository_or_none': lambda: repository,
        'sanitize_ai_detection_task_id': lambda value: str(value or '').strip(),
        'safe_record_id': lambda value: str(value).replace('/', '_'),
        'row_raw_json_list': lambda rows: [row['raw_json'] for row in rows],
        'auto_optimize_state_row': lambda state, *, fallback_id: {'task_id': fallback_id, 'raw_json': state},
        'resolve_model_profiles': lambda: resolver, 'shadow_resolver': resolver,
        '_read_path_cache': request_cache,
        'store_read_cache_get': lambda key: (key in cache, cache.get(key)),
        'store_read_cache_put': lambda key, value: cache.__setitem__(key, value),
        'store_read_cache_invalidate': lambda *keys: [cache.pop(key, None) for key in keys],
        'find_training_task': lambda job: None, 'load_config': lambda: {},
        'canonical_pipeline_accessory_ids': lambda config, ids: ids,
        'normalize_pipeline_accessory_counts': lambda config, ids, counts: {},
        'load_pipeline_tasks': lambda: [], 'normalize_pipeline_detection_method': lambda value: value,
        'pipeline_task_model_status': lambda task: '', 'pipeline_task_model_id': lambda task: '',
        'hydrate_auto_optimize_background_from_ai_task': lambda state: False,
        'record_visible_to_user': lambda record, user: record.get('owner_user_id') == user['id'],
        'current_auth_user': lambda: None, 'start_auto_optimize_label_worker': lambda task: events.append(('label', task)),
        'auto_optimize_public_sprite_pool': lambda state: [], 'background_set_payload': lambda value: {},
        'AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT': 2, 'public_path_sanitized': lambda value: value,
        'normalize_expected_production_count': lambda value: int(value or 0),
        'bounded_text': lambda value, size: str(value)[:size],
        'resolve_service_path': lambda value: directory / str(value),
        '_image_files': SimpleNamespace(imread=lambda *args: np.zeros((4, 4, 3), dtype=np.uint8)),
        'LEGACY_OWNER_ID': 'legacy', 'delete_training_task_record': lambda *args, **kwargs: events.append(('delete', args)),
        'training_run_roots': lambda: [],
    }
    def forbidden():
        raise AssertionError('constructor selected an external capability')
    def group(kind):
        return kind(**{field.name: forbidden if poison else lambda name=field.name: values[name] for field in fields(kind)})
    @contextmanager
    def scope():
        events.append(('enter', threading.get_ident()))
        try:
            yield
        finally:
            events.append(('exit', threading.get_ident()))
    detection = SimpleNamespace(analyze_bgr=lambda *args, **kwargs: {'rule': {'counts': {'part': 1}}})
    core = composition.AutoOptimizationCore(
        settings=AutoOptimizationSettings(2), runtime=AutoOptimizationRuntimeState(),
        detection=forbidden if poison else lambda: detection,
        shadow_runtime=TrainingThreadLifecycle(scope=scope),
        shadow_resolver=forbidden if poison else lambda: values['shadow_resolver'],
        storage=group(composition.StateStorage), state_policy=group(composition.StatePolicy),
        cache=group(composition.AutoOptimizationStateCache), readiness=group(composition.ReadinessLookups),
        status_state=group(composition.StatusLookups), status_policy=group(composition.StatusProjection),
        shadow_state=group(composition.ShadowPolicy), observation=group(composition.ShadowImages),
        retirement=group(composition.Retirement), accessory_lookup=forbidden if poison else lambda config: {},
        material_type=forbidden if poison else lambda record: 'object',
        bounded_text=forbidden if poison else lambda: values['bounded_text'])
    test.addCleanup(lambda: core.shadow.close(3))
    return SimpleNamespace(core=core, records=records, events=events, values=values, repository=repository, detection=detection, resolver=resolver, snapshot=snapshot)

def seed(fixture, *, active='', owner='A'):
    state = {'task_id': 'same', 'settings': {'enabled': True, 'auto_promote': False},
             'active_model_id': active, 'samples': [{'sample_id': 'sample', 'source_image': {'path': 'same.png'}, 'ai_result': {'rule': {'counts': {'part': 1}}}, 'owner_user_id': owner}],
             'candidate_models': [{'model_id': 'candidate', 'job_id': 'job'}]}
    fixture.core.store.save_auto_optimize_state(state)
    return state

class Contracts(unittest.TestCase):
    def test_parent_ports_aliases_and_shadow_mutants(self):
        source = (ROOT / 'local_inspection_service/server.py').read_text(encoding='utf-8')
        verify_source(source)
        for old, new in [
            ('detection=lambda: _detection_workflows', 'detection=lambda: _image_generation'),
            ('shadow_resolver=resolve_model_profiles', 'shadow_resolver=lambda: None'),
            ('_auto_optimization_shadow_evaluation = _auto_optimization_core.shadow', '_auto_optimization_shadow_evaluation = _auto_optimization_core.status'),
            ('AUTO_OPTIMIZE_DIR=lambda: AUTO_OPTIMIZE_DIR', 'AUTO_OPTIMIZE_DIR=lambda: OUTPUT_DIR'),
        ]:
            self.assertIn(old, source)
            with self.assertRaises(AssertionError):
                verify_source(source.replace(old, new, 1))
        for extra in [
            '\n_auto_optimization_core: object = object()\n',
            '\n_auto_optimization_core += object()\n',
            '\nfrom wrong import AutoOptimizationCore\n',
            '\nfrom wrong import _auto_optimization_core\n',
            '\ndef _auto_optimization_core(): pass\n',
            '\nasync def _auto_optimization_core(): pass\n',
            '\nclass _auto_optimization_core: pass\n',
            '\nfrom wrong import _auto_optimization_shadow_evaluation\n',
        ]:
            with self.assertRaises(AssertionError):
                verify_source(source + extra)
        with self.assertRaises(AssertionError):
            verify_source(source.replace('from .training.core_composition import', 'from training.core_composition import', 1))

    def test_poisoned_inert_construction_and_shared_runtime(self):
        a, b = assemble(self, poison=True), assemble(self, poison=True)
        self.assertEqual(a.events, [])
        self.assertEqual(a.records, {})
        self.assertIs(a.core.status.state._auto_optimize_lock(), a.core.runtime.lock)
        self.assertIs(a.core.shadow.state._auto_optimize_shadow_threads(), a.core.runtime.shadow_threads)
        self.assertIsNot(a.core.runtime.lock, b.core.runtime.lock)
        self.assertIsNot(a.core.shadow.runtime, b.core.shadow.runtime)

    def test_owned_callback_selected_after_argument_effect(self):
        f = assemble(self)
        original = f.core.store
        saved = f.core.status.state.load_auto_optimize_state()
        replacement = SimpleNamespace(load_auto_optimize_state=lambda task: {'new': task})
        def argument():
            f.core.store = replacement
            return 'same'
        self.assertEqual(saved(argument()), {'new': 'same'})
        f.core.store = original
        saved = f.core.shadow.observation.analyze_bgr()
        def image():
            f.detection.analyze_bgr = lambda *args, **kwargs: {'selected': 'new'}
            return np.zeros((2, 2, 3))
        self.assertEqual(saved(image(), 'id', 'model', image_path=Path('image')), {'selected': 'new'})

    def test_actual_store_same_ids_status_and_identity_isolation(self):
        a, b = assemble(self), assemble(self)
        seed(a, active='model-A', owner='A')
        seed(b, active='model-B', owner='B')
        self.assertEqual(a.core.status.public_auto_optimize_state('same', user={'id': 'A'})['samples_total'], 1)
        self.assertEqual(a.core.status.public_auto_optimize_state('same', user={'id': 'B'})['samples_total'], 0)
        self.assertEqual(b.core.status.public_auto_optimize_state('same', user={'id': 'B'})['active_model_id'], 'model-B')
        self.assertEqual(a.core.store.load_auto_optimize_state('same')['model_profiles']['training_vision']['version'], 7)
        self.assertNotEqual(a.records, b.records)

    def test_native_shadow_persists_and_closes_only_own_instance(self):
        a, b = assemble(self), assemble(self)
        seed(a); seed(b)
        a.core.shadow.start_auto_optimize_shadow_worker('same', 'sample')
        self.assertTrue(a.core.shadow.close(3))
        self.assertEqual(a.core.store.load_auto_optimize_state('same')['shadow_runs'][0]['agreement'], 1.0)
        self.assertEqual([e[0] for e in a.events if e[0] in ('enter', 'exit')], ['enter', 'exit'])
        worker_id = next(e[1] for e in a.events if e[0] == 'enter')
        self.assertNotEqual(worker_id, threading.get_ident())
        self.assertIn(('save', worker_id), a.events)
        with self.assertRaises(TrainingRuntimeClosed):
            a.core.shadow.start_auto_optimize_shadow_worker('same', 'sample')
        b.core.shadow.start_auto_optimize_shadow_worker('same', 'sample')
        self.assertTrue(b.core.shadow.close(3))
        self.assertEqual(len(b.core.store.load_auto_optimize_state('same')['shadow_runs']), 1)

    def test_inflight_failure_duplicate_and_independent_drain(self):
        a, b = assemble(self), assemble(self)
        seed(a); seed(b)
        entered, release = threading.Event(), threading.Event()
        calls = []
        def fail(*args, **kwargs):
            calls.append(args)
            entered.set()
            if not release.wait(3):
                raise AssertionError('synthetic timeout')
            raise TimeoutError('unknown synthetic result')
        a.detection.analyze_bgr = fail
        a.core.shadow.start_auto_optimize_shadow_worker('same', 'sample')
        self.assertTrue(entered.wait(3))
        try:
            a.core.shadow.start_auto_optimize_shadow_worker('same', 'sample')
            self.assertFalse(a.core.shadow.close(0))
            b.core.shadow.start_auto_optimize_shadow_worker('same', 'sample')
            self.assertTrue(b.core.shadow.close(3))
        finally:
            release.set()
        self.assertTrue(a.core.shadow.close(3))
        self.assertEqual(len(calls), 1)
        self.assertEqual(a.core.store.load_auto_optimize_state('same')['last_shadow_error'], 'unknown synthetic result')
        self.assertEqual(a.core.store.load_auto_optimize_state('same')['shadow_runs'], [])
        self.assertEqual(len(b.core.store.load_auto_optimize_state('same')['shadow_runs']), 1)

    def test_save_failure_retains_original_error_without_retry(self):
        f = assemble(self)
        seed(f)
        error = OSError('synthetic repository failure')
        calls = []
        def fail(*args):
            calls.append(args)
            raise error
        f.repository.upsert_row = fail
        state = f.core.store.load_auto_optimize_state('same')
        with self.assertRaises(OSError) as caught:
            f.core.store.save_auto_optimize_state(state)
        self.assertIs(caught.exception, error)
        self.assertEqual(len(calls), 1)
        self.assertIn('updated_at', state)

    def test_native_task_snapshot_is_pinned_once_after_thread_entry(self):
        f = assemble(self)
        seed(f)
        f.snapshot['training_vision']['version'] = 9
        seen = []
        def analyze(*args, **kwargs):
            seen.append(copy.deepcopy(f.resolver.current_snapshot()))
            return {'rule': {'counts': {'part': 1}}}
        f.detection.analyze_bgr = analyze
        f.core.shadow.start_auto_optimize_shadow_worker('same', 'sample')
        self.assertTrue(f.core.shadow.close(3))
        self.assertEqual([snapshot['training_vision']['version'] for snapshot in seen], [7])
        self.assertIsNone(f.resolver.current_snapshot())
        scope_events = [e[0] for e in f.events if e[0] in ('enter', 'model_enter', 'model_exit', 'exit')]
        self.assertEqual(scope_events, ['enter', 'model_enter', 'model_exit', 'exit'])
        entered = next(i for i, e in enumerate(f.events) if e[0] == 'enter')
        bound = next(i for i, e in enumerate(f.events) if e[0] == 'model_enter')
        self.assertTrue(any(e[0] == 'fetch' for e in f.events[entered + 1:bound]))
        self.assertEqual(len(f.core.store.load_auto_optimize_state('same')['shadow_runs']), 1)

    def test_missing_resolver_fails_before_task_load_and_native_analysis(self):
        f = assemble(self)
        seed(f)
        before = copy.deepcopy(f.records)
        f.values['shadow_resolver'] = None
        calls, errors = [], []
        f.core.store = SimpleNamespace(load_auto_optimize_state=lambda task: calls.append(task))
        f.detection.analyze_bgr = lambda *args, **kwargs: calls.append('analysis')
        with patch.object(threading, 'excepthook', side_effect=lambda event: errors.append(event.exc_value)):
            f.core.shadow.start_auto_optimize_shadow_worker('same', 'sample')
            self.assertTrue(f.core.shadow.close(3))
        self.assertEqual(calls, [])
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RuntimeError)
        self.assertEqual(str(errors[0]), 'Model profile resolver is not configured')
        self.assertEqual(f.records, before)
        self.assertEqual([e[0] for e in f.events if e[0] in ('enter', 'exit')], ['enter', 'exit'])

    def test_public_entry_keeps_one_original_pin_and_empty_snapshot(self):
        from local_inspection_service.model_profiles.snapshots import pinned
        f = assemble(self)
        seed(f)
        f.records['same']['raw_json']['model_profiles'] = {}
        seen = []
        def analyze(*args, **kwargs):
            seen.append(copy.deepcopy(f.resolver.current_snapshot()))
            return {'rule': {'counts': {'part': 1}}}
        f.detection.analyze_bgr = analyze
        source = ROOT / 'local_inspection_service/server.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        worker = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'auto_optimize_shadow_worker')
        namespace = {
            'pinned_model_profiles': pinned, 'resolve_model_profiles': lambda: f.resolver,
            'load_auto_optimize_state': f.core.load_auto_optimize_state,
            '_auto_optimization_shadow_evaluation': f.core.shadow,
        }
        exec(compile(ast.Module(body=[worker], type_ignores=[]), str(source), 'exec'), namespace)
        namespace['auto_optimize_shadow_worker']('same', 'sample')
        self.assertEqual(seen, [{}])
        self.assertEqual(len([e for e in f.events if e[0] == 'model_enter']), 1)
        self.assertEqual(len([e for e in f.events if e[0] == 'model_exit']), 1)
        self.assertIsNone(f.resolver.current_snapshot())
        self.assertEqual(f.core.store.load_auto_optimize_state('same')['model_profiles'], {})

    def test_inherited_scope_and_business_exception_restore_without_retry(self):
        f = assemble(self)
        seed(f)
        f.records['same']['raw_json']['model_profiles'] = None
        outer = {'training_vision': {'id': 'outer', 'version': 19}}
        seen = []
        def fail(*args, **kwargs):
            seen.append(copy.deepcopy(f.resolver.current_snapshot()))
            raise TimeoutError('synthetic ambiguous observation')
        f.detection.analyze_bgr = fail
        with f.resolver.scope(outer):
            f.core.pinned_shadow_worker('same', 'sample')
            self.assertIs(f.resolver.current_snapshot(), outer)
        self.assertIsNone(f.resolver.current_snapshot())
        self.assertEqual(seen, [outer])
        state = f.core.store.load_auto_optimize_state('same')
        self.assertEqual(state['last_shadow_error'], 'synthetic ambiguous observation')
        self.assertEqual(state['shadow_runs'], [])
        self.assertEqual(len([e for e in f.events if e[0] == 'model_enter']), 2)
        self.assertEqual(len([e for e in f.events if e[0] == 'model_exit']), 2)

if __name__ == '__main__':
    unittest.main()
