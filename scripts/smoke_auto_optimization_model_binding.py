"""Model-only executor binding, with explicit parent behavior counterexample."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import ContextVar
from dataclasses import replace
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.model_profiles.service import Service
from local_inspection_service.model_profiles.snapshots import bind_current
from local_inspection_service.runtime.identity import RequestIdentity
from local_inspection_service.runtime.read_caches import RequestReadCache
from local_inspection_service.training.auto_optimization_label_processing import AutoOptimizationLabelProcessing
import smoke_auto_optimization_label_processing as business


class Binding(unittest.TestCase):
    def test_parent_bare_pool_loses_snapshot_and_explicit_binding_keeps_version(self):
        resolver = Service(None)
        old = {'training_vision': {'id': 'profile', 'version': 1, 'secret_ref': 'synthetic-version-one'}}
        with resolver.scope(old):
            selected = lambda: resolver.current_snapshot()
            bound = bind_current(lambda: resolver, selected)
            with ThreadPoolExecutor(1) as pool:
                self.assertIsNone(pool.submit(selected).result(3))
                old['training_vision']['version'] = 2
                got = pool.submit(bound).result(3)
                self.assertEqual(got['training_vision']['version'], 1)
                self.assertEqual(got['training_vision']['secret_ref'], 'synthetic-version-one')
                self.assertIsNone(pool.submit(resolver.current_snapshot).result(3))
        self.assertEqual(old['training_vision']['version'], 2)

    def test_only_model_binding_crosses_threads(self):
        resolver, identity, cache = Service(None), RequestIdentity(), RequestReadCache()
        authorization = ContextVar('synthetic_write_authorization', default=False)
        authorization.set(True)
        with identity.bind({'id': 'parent'}), cache.scope(), resolver.scope({'image': {'version': 7}}):
            cache.current.get()['mutable'] = []
            bound = bind_current(lambda: resolver, lambda: (
                resolver.current_snapshot(), identity.get(), cache.current.get(), authorization.get()))
            with ThreadPoolExecutor(1) as pool:
                result = pool.submit(bound).result(3)
        self.assertEqual(result, ({'image': {'version': 7}}, None, None, False))

    def test_parallel_bindings_are_private_and_do_not_change_each_other(self):
        resolver = Service(None)
        barrier = threading.Barrier(2)
        def selected():
            current = resolver.current_snapshot()
            barrier.wait(3)
            current['local'] = True
            return current
        bindings, snapshots = [], []
        for version in (1, 2):
            snapshot = {'image': {'version': version}}
            snapshots.append(snapshot)
            with resolver.scope(snapshot):
                bindings.append(bind_current(lambda: resolver, selected))
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(bound) for bound in bindings]
            results = [future.result(3) for future in futures]
        self.assertEqual([x['image']['version'] for x in results], [1, 2])
        self.assertTrue(all('local' not in x for x in snapshots))
        self.assertIsNot(results[0], results[1])

    def test_exception_restores_existing_worker_model_context_without_replay(self):
        resolver = Service(None)
        error, calls, marker = RuntimeError('synthetic failure'), [], object()
        def selected(value, *, flag):
            calls.append((value, flag, resolver.current_snapshot()))
            raise error
        with resolver.scope({}):
            bound = bind_current(lambda: resolver, selected)
        def work():
            prior = {'image': {'version': 99}}
            with resolver.scope(prior):
                with self.assertRaises(RuntimeError) as caught:
                    bound(marker, flag=True)
                self.assertIs(caught.exception, error)
                self.assertIs(resolver.current_snapshot(), prior)
        with ThreadPoolExecutor(1) as pool:
            pool.submit(work).result(3)
        self.assertEqual(calls, [(marker, True, {})])

    def test_missing_resolver_or_binding_fails_before_callback(self):
        selected = Mock()
        with self.assertRaisesRegex(RuntimeError, 'resolver'):
            bind_current(lambda: None, selected)
        resolver = Service(None)
        with self.assertRaisesRegex(RuntimeError, 'bound model snapshot'):
            bind_current(lambda: resolver, selected)
        service = AutoOptimizationLabelProcessing(None, None, None)
        with self.assertRaisesRegex(RuntimeError, 'resolver'):
            service._scoped_sample(selected)
        selected.assert_not_called()

    def test_actual_batch_uses_bound_training_vision_snapshot(self):
        fixture = business.ProcessingContract().fixture()
        resolver = Service(None)
        fixture.service = replace(fixture.service, model_resolver=lambda: resolver)
        fixture.b['ThreadPoolExecutor'] = ThreadPoolExecutor
        fixture.b['as_completed'] = as_completed
        fixture.state['samples'] = [{'sample_id': str(i), 'label_status': 'pending'} for i in range(2)]
        seen = []
        def process(task, pending, settings, model):
            seen.append(resolver.current_snapshot()['training_vision']['version'])
            return {'sample_id': pending['sample_id'], 'labels': [], 'failures': [], 'label_artifacts': {}, 'completed_at': 1}
        fixture.b['auto_optimize_process_label_sample'] = process
        with resolver.scope({'training_vision': {'id': 'pinned', 'version': 7}}):
            fixture.service.auto_optimize_label_worker('task')
        self.assertEqual(seen, [7, 7])
        self.assertNotIn('last_label_error', fixture.state)

    def test_later_binding_failure_joins_earlier_submission_without_replay(self):
        fixture = business.ProcessingContract().fixture()
        resolver = Service(None)
        selected, release = threading.Event(), threading.Event()
        bindings, calls = [], []
        def provider():
            bindings.append(1)
            return resolver if len(bindings) == 1 else None
        fixture.service = replace(fixture.service, model_resolver=provider)
        fixture.b['ThreadPoolExecutor'] = ThreadPoolExecutor
        fixture.b['as_completed'] = as_completed
        fixture.state['samples'] = [{'sample_id': str(i), 'label_status': 'pending'} for i in range(2)]
        def process(task, pending, settings, model):
            calls.append(pending['sample_id'])
            selected.set()
            release.wait(3)
            return {'sample_id': pending['sample_id'], 'labels': [], 'failures': [], 'label_artifacts': {}, 'completed_at': 1}
        fixture.b['auto_optimize_process_label_sample'] = process
        def coordinator():
            with resolver.scope({'training_vision': {'version': 7}}):
                fixture.service.auto_optimize_label_worker('task')
        caller = threading.Thread(target=coordinator)
        caller.start()
        try:
            self.assertTrue(selected.wait(3))
            self.assertTrue(caller.is_alive())
        finally:
            release.set()
            caller.join(3)
        self.assertFalse(caller.is_alive())
        self.assertEqual(calls, ['0'])
        self.assertEqual(len(bindings), 2)
        self.assertIn('resolver', fixture.state['last_label_error'])
        self.assertEqual([sample['label_status'] for sample in fixture.state['samples']], ['labeling', 'labeling'])

    def test_missing_batch_dependency_records_failure_without_paid_submission(self):
        fixture = business.ProcessingContract().fixture()
        fixture.service = replace(fixture.service, model_resolver=None)
        fixture.state['samples'] = [{'sample_id': 'one', 'label_status': 'pending'}]
        callback = Mock()
        fixture.b['auto_optimize_process_label_sample'] = callback
        fixture.service.auto_optimize_label_worker('task')
        self.assertIn('resolver', fixture.state['last_label_error'])
        self.assertFalse(any(event[0] == 'submit' for event in fixture.events))
        callback.assert_not_called()


if __name__ == '__main__':
    unittest.main()
