"""Real executor repository cleanup preserving original ContextVar behavior."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smoke_auto_optimization_label_processing import ProcessingContract
from local_inspection_service.training.auto_optimization_label_processing import AutoOptimizationLabelProcessing
from local_inspection_service.runtime.training_tasks import TrainingThreadLifecycle
from local_inspection_service.runtime.connections import ThreadRepositoryFactory
from local_inspection_service.runtime.identity import RequestIdentity
from local_inspection_service.model_profiles.service import Service


class PoolScope(unittest.TestCase):
    def fixture(self):
        identity, profiles = RequestIdentity(), Service(None)
        created = []
        class Connection:
            closed = False
            def __init__(self):
                self.owner = identity.get()
                self.thread = threading.get_ident()
            def close(self):
                assert self.thread == threading.get_ident()
                self.closed = True
        def create():
            connection = Connection()
            created.append(connection)
            return SimpleNamespace(repository=SimpleNamespace(connection=connection))
        repositories = ThreadRepositoryFactory(create, lambda: (identity.get() or {}).get('id'))
        service = AutoOptimizationLabelProcessing(None, None, None,
            runtime=TrainingThreadLifecycle(scope=repositories.thread_scope))
        return SimpleNamespace(identity=identity, profiles=profiles, created=created,
            repositories=repositories, service=service)

    def test_reused_executor_releases_each_connection_without_copying_parent_context(self):
        f = self.fixture()
        def selected():
            conn = f.repositories.selection().repository.connection
            return f.identity.get(), f.profiles.current_snapshot(), conn
        with ThreadPoolExecutor(max_workers=1) as pool:
            for owner in ('a', 'b'):
                with f.identity.bind({'id': owner}), f.profiles.scope({'image': {'version': 1}}):
                    bound = f.service._scoped_sample(selected)
                    got_user, got_snapshot, conn = pool.submit(bound).result(3)
                self.assertIsNone(got_user)
                self.assertIsNone(got_snapshot)
                self.assertTrue(conn.closed)
            self.assertEqual(pool.submit(lambda: (f.identity.get(), f.profiles.current_snapshot())).result(3), (None, None))
        self.assertEqual(len(f.created), 2)
        self.assertEqual(f.created[0].thread, f.created[1].thread)
        self.assertIsNot(f.created[0], f.created[1])

    def test_parallel_tasks_keep_existing_per_thread_identity_and_connections(self):
        f = self.fixture()
        barrier = threading.Barrier(2)
        def selected(owner):
            with f.identity.bind({'id': owner}):
                conn = f.repositories.selection().repository.connection
                barrier.wait(3)
                return f.identity.get()['id'], conn
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(f.service._scoped_sample(selected), owner) for owner in ('a', 'b')]
            results = [future.result(3) for future in results]
        self.assertEqual([x[0] for x in results], ['a', 'b'])
        self.assertNotEqual(results[0][1].thread, results[1][1].thread)
        self.assertTrue(all(x[1].closed for x in results))

    def test_exception_waits_for_scope_exit_and_is_not_replayed(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        error = RuntimeError('synthetic failure')
        @contextmanager
        def scope():
            try:
                yield
            finally:
                entered.set()
                release.wait(3)
        service = AutoOptimizationLabelProcessing(None, None, None, runtime=TrainingThreadLifecycle(scope=scope))
        def selected(value):
            calls.append(value)
            raise error
        value = object()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(service._scoped_sample(selected), value)
            try:
                self.assertTrue(entered.wait(3))
                self.assertFalse(future.done())
            finally:
                release.set()
            with self.assertRaises(RuntimeError) as caught:
                future.result(3)
        self.assertIs(caught.exception, error)
        self.assertEqual(calls, [value])

    def test_scope_entry_failure_does_not_run_target_or_leak_context(self):
        f = self.fixture()
        error = RuntimeError('scope unavailable')
        @contextmanager
        def scope():
            raise error
            yield
        service = replace(f.service, runtime=TrainingThreadLifecycle(scope=scope))
        calls = []
        with f.identity.bind({'id': 'a'}):
            bound = service._scoped_sample(lambda: calls.append(1))
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.assertRaises(RuntimeError) as caught:
                pool.submit(bound).result(3)
            self.assertIsNone(pool.submit(f.identity.get).result(3))
        self.assertIs(caught.exception, error)
        self.assertEqual(calls, [])

    def test_actual_batch_worker_submits_scoped_targets(self):
        fixture = ProcessingContract().fixture()
        f = self.fixture()
        fixture.service = replace(fixture.service, runtime=f.service.runtime)
        fixture.b['ThreadPoolExecutor'] = ThreadPoolExecutor
        fixture.b['as_completed'] = as_completed
        fixture.state['samples'] = [{'sample_id': str(i), 'label_status': 'pending'} for i in range(2)]
        seen = []
        def process(task, pending, settings, model):
            conn = f.repositories.selection().repository.connection
            seen.append((task, pending['sample_id'], f.identity.get(), f.profiles.current_snapshot(), conn))
            return {'sample_id': pending['sample_id'], 'labels': [], 'failures': [],
                'label_artifacts': {}, 'completed_at': 1}
        fixture.b['auto_optimize_process_label_sample'] = process
        user, snapshot = {'id': 'batch-owner'}, {'image': {'id': 'pinned', 'version': 1}}
        with f.identity.bind(user), f.profiles.scope(snapshot):
            fixture.service.auto_optimize_label_worker('task')
        self.assertEqual({x[1] for x in seen}, {'0', '1'})
        self.assertTrue(all(x[0] == 'task' and x[2] is None and x[3] is None and x[4].closed for x in seen))
        self.assertNotIn('last_label_error', fixture.state)


if __name__ == '__main__':
    unittest.main()
