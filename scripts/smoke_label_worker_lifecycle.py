"""Real-thread label drain contracts; synthetic dependencies, no DB/provider/PLC."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from local_inspection_service.label_inspection import worker, worker_api
from local_inspection_service.label_inspection.dependencies import RepositoryLifecycle


class LifecycleContracts(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'VANTALINE_LABEL_INSPECTION_ENABLED': 'true'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.releases = []
        self.workers = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for release in self.releases:
            release.set()
        for controller in self.workers:
            result = controller.drain(3)
            self.assertEqual(controller.status()['live_threads'], 0, 'fixture left a live thread')
            if controller.status()['state'] != 'failed':
                self.assertTrue(result)

    def controller(self, repository=lambda: None, clear=lambda: None):
        controller = worker.LabelWorker(RepositoryLifecycle(repository, clear), lambda: Path('fixture'), lambda: None)
        self.workers.append(controller)
        return controller

    def held_iteration(self, controller):
        admitted = threading.Barrier(3)
        release = threading.Event()
        self.releases.append(release)
        calls = []
        lock = threading.Lock()
        def iteration():
            with lock:
                calls.append(threading.current_thread())
            admitted.wait(3)
            release.wait(3)
            return True
        controller._iteration = iteration
        controller.start()
        admitted.wait(3)
        return calls, release

    def test_two_consumers_duplicate_start_stop_timeout_restart(self):
        clear_threads = []
        controller = self.controller(clear=lambda: clear_threads.append(threading.current_thread()))
        calls, release = self.held_iteration(controller)
        old_threads = tuple(controller._threads)
        with ThreadPoolExecutor(6) as pool:
            list(pool.map(lambda _: controller.start(), range(12)))
        self.assertEqual(tuple(controller._threads), old_threads)
        self.assertEqual(len(calls), 2)
        self.assertEqual(controller.status(), {'state': 'running', 'live_threads': 2})
        self.assertFalse(controller.drain(0.02))
        self.assertEqual(controller.status(), {'state': 'timed_out', 'live_threads': 2})
        with self.assertRaisesRegex(RuntimeError, 'draining'):
            controller.start()
        release.set()
        self.assertTrue(controller.drain(3))
        self.assertCountEqual(clear_threads, old_threads)
        self.assertEqual(controller.status(), {'state': 'stopped', 'live_threads': 0})
        self.assertEqual(len(calls), 2)
        self.assertTrue(controller.drain(0))
        controller._iteration = lambda: False
        controller.start()
        self.assertTrue(set(old_threads).isdisjoint(controller._threads))
        self.assertTrue(controller.drain(3))

    def test_blocked_claim_counts_as_inflight_and_finishes_once(self):
        admitted = threading.Barrier(3)
        release = threading.Event()
        self.releases.append(release)
        claimed, processed, cleared = [], [], []
        lock = threading.Lock()
        def claim():
            thread = threading.current_thread()
            with lock:
                claimed.append(thread)
            admitted.wait(3)
            release.wait(3)
            return {'id': thread.name, 'owner_user_id': 'fixture', 'profile_snapshot': {'id': 'pinned'}}
        models = SimpleNamespace(resolve=lambda *args: {'api_key': 'synthetic'}, record_call=lambda *args: None)
        controller = self.controller(lambda: SimpleNamespace(claim=claim), lambda: cleared.append(threading.current_thread()))
        controller.models = lambda: models
        with patch.object(worker, 'LabelRepository', side_effect=lambda repo: repo), \
             patch.object(worker, 'process', side_effect=lambda *a, **k: processed.append(a[2]['id'])):
            controller.start()
            admitted.wait(3)
            controller.request_stop()
            self.assertFalse(controller.drain(0))
            self.assertEqual(processed, [])
            release.set()
            self.assertTrue(controller.drain(3))
        self.assertCountEqual(processed, ['label-inspection-0', 'label-inspection-1'])
        self.assertCountEqual(cleared, claimed)
        self.assertEqual(len(claimed), 2)

    def test_stop_waits_for_connection_cleanup_on_working_threads(self):
        cleaning = threading.Barrier(3)
        release = threading.Event()
        self.releases.append(release)
        cleared = []
        def clear():
            cleared.append(threading.current_thread())
            cleaning.wait(3)
            release.wait(3)
        controller = self.controller(clear=clear)
        controller.start()
        cleaning.wait(3)
        self.assertFalse(controller.drain(0))
        self.assertCountEqual(cleared, controller._threads)
        release.set()
        self.assertTrue(controller.drain(3))

    def test_cleanup_exception_stops_generation_and_redacts_details(self):
        called = threading.Event()
        def clear():
            called.set()
            raise RuntimeError('synthetic-secret database-url customer-field')
        controller = self.controller(clear=clear)
        with self.assertLogs(worker.__name__, level='ERROR') as captured:
            controller.start()
            self.assertTrue(called.wait(3))
            self.assertFalse(controller.drain(3))
        text = '\n'.join(captured.output)
        self.assertIn('label_worker_cleanup_failed', text)
        self.assertNotIn('synthetic-secret', text)
        self.assertEqual(controller.status(), {'state': 'failed', 'live_threads': 0})
        self.assertFalse(controller.drain(0))
        with self.assertRaisesRegex(RuntimeError, 'process restart required'):
            controller.start()

    def test_partial_thread_start_failure_retains_first_thread(self):
        actual_thread = threading.Thread
        made = []
        def create(*a, **kw):
            thread = actual_thread(*a, **kw)
            made.append(thread)
            if len(made) == 2:
                thread.start = lambda: (_ for _ in ()).throw(RuntimeError('synthetic start failed'))
            return thread
        controller = self.controller()
        with patch.object(worker.threading, 'Thread', side_effect=create):
            with self.assertRaisesRegex(RuntimeError, 'synthetic start failed'):
                controller.start()
        self.assertEqual(controller._threads, made)
        self.assertFalse(controller.drain(3))
        self.assertEqual(controller.status(), {'state': 'failed', 'live_threads': 0})
        with self.assertRaisesRegex(RuntimeError, 'process restart required'):
            controller.start()

    def test_start_raises_after_native_launch_never_reports_drained(self):
        actual_thread = threading.Thread
        release = threading.Event()
        self.releases.append(release)
        controller = self.controller()
        controller._loop = lambda stop: release.wait(3)
        class StartThenRaise(actual_thread):
            def start(self):
                super().start()
                raise RuntimeError('synthetic interruption after native start')
        with patch.object(worker.threading, 'Thread', StartThenRaise):
            with self.assertRaisesRegex(RuntimeError, 'after native start'):
                controller.start()
        self.assertEqual(len(controller._threads), 1)
        self.assertEqual(controller.status(), {'state': 'failed', 'live_threads': 1})
        self.assertFalse(controller.drain(0))
        release.set()
        self.assertFalse(controller.drain(3))
        self.assertEqual(controller.status(), {'state': 'failed', 'live_threads': 0})

    def test_concurrent_registration_installs_exactly_one_controller(self):
        app = FastAPI()
        repositories = RepositoryLifecycle(lambda: None, lambda: None)
        directory, models = lambda: Path('fixture'), lambda: None
        barrier = threading.Barrier(8)
        def register(_):
            barrier.wait(3)
            return worker_api.register(app, repositories, directory, models)
        with ThreadPoolExecutor(8) as pool:
            controllers = list(pool.map(register, range(8)))
        self.assertTrue(all(item is controllers[0] for item in controllers))
        self.assertEqual((len(app.router.on_startup), len(app.router.on_shutdown)), (1, 1))

    def test_all_joins_share_one_budget_and_no_start_during_join(self):
        controller = self.controller()
        stop = threading.Event()
        waiting = threading.Event()
        self.releases.append(stop)
        budgets = []
        class HeldThread:
            ident = 1
            def is_alive(self): return True
            def join(self, timeout):
                budgets.append(timeout)
                waiting.set()
                stop.wait(timeout)
        controller._threads = [HeldThread(), HeldThread()]
        with ThreadPoolExecutor(1) as pool:
            result = pool.submit(controller.drain, 0.08)
            self.assertTrue(waiting.wait(3))
            with self.assertRaisesRegex(RuntimeError, 'draining'):
                controller.start()
            self.assertFalse(result.result(3))
        self.assertEqual(len(budgets), 2)
        self.assertLess(budgets[1], 0.01)
        controller._threads = []

    def test_disabled_or_missing_repository_releases_and_drains(self):
        for enabled in ('true', 'false'):
            with self.subTest(enabled=enabled), patch.dict(os.environ, {'VANTALINE_LABEL_INSPECTION_ENABLED': enabled}):
                reached = threading.Event()
                opens = []
                cleared = []
                def clear():
                    cleared.append(threading.current_thread())
                    reached.set()
                controller = self.controller(lambda: opens.append('open'), clear)
                controller.start()
                self.assertTrue(reached.wait(3))
                self.assertTrue(controller.drain(3))
                self.assertGreaterEqual(len(cleared), 1)
                self.assertEqual(bool(opens), enabled == 'true')

    def test_registration_idempotence_and_conflicting_dependencies_fail(self):
        app = FastAPI()
        repositories = RepositoryLifecycle(lambda: None, lambda: None)
        directory, models = lambda: Path('fixture'), lambda: None
        first = worker_api.register(app, repositories, directory, models)
        self.workers.append(first)
        self.assertIs(worker_api.register(app, repositories, directory, models), first)
        self.assertEqual((len(app.router.on_startup), len(app.router.on_shutdown)), (1, 1))
        with self.assertRaisesRegex(RuntimeError, 'different dependencies'):
            worker_api.register(app, RepositoryLifecycle(lambda: None, lambda: None), directory, models)
        for _ in range(2):
            with TestClient(app):
                self.assertEqual(first.status(), {'state': 'running', 'live_threads': 2})
            self.assertEqual(first.status(), {'state': 'stopped', 'live_threads': 0})
        second = worker_api.register(FastAPI(), repositories, directory, models)
        self.assertIsNot(first, second)

    def test_adapter_reports_timeout(self):
        app = FastAPI()
        controller = worker_api.register(app, RepositoryLifecycle(lambda: None, lambda: None), lambda: Path('fixture'), lambda: None)
        with patch.object(controller, 'drain', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'not acknowledged'):
                app.router.on_shutdown[0]()

    def test_truthiness_and_cleanup_precede_idle_decision(self):
        for empty_repository, empty_run in ((True, False), (False, True), (False, False)):
            with self.subTest(empty_repository=empty_repository, empty_run=empty_run):
                run = {} if empty_run else {'id': 'run', 'owner_user_id': 'fixture', 'profile_snapshot': {'id': 'old'}}
                calls = []
                class Repository:
                    def __bool__(self): return not empty_repository
                    def claim(self): calls.append('claim'); return run
                controller = self.controller(lambda: Repository())
                def clear():
                    calls.append('clear')
                    run.clear()
                    controller.request_stop()
                controller.repositories = RepositoryLifecycle(lambda: Repository(), clear)
                controller.models = lambda: SimpleNamespace(resolve=lambda *a: {'api_key': 'fixture'}, record_call=lambda *a: None)
                with patch.object(worker, 'LabelRepository', side_effect=lambda raw: raw), \
                     patch.object(worker, 'process', side_effect=lambda *a, **k: calls.append('process')), \
                     patch.object(controller._stop, 'wait', wraps=controller._stop.wait) as wait:
                    controller._loop(controller._stop)
                    wait.assert_called_once_with(1)
                self.assertEqual(calls, (['claim'] if not empty_repository else []) +
                                 (['process'] if not empty_repository and not empty_run else []) + ['clear'])

    def test_invalid_timeouts(self):
        controller = self.controller()
        for value in (-1, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                controller.drain(value)
        self.assertEqual(worker.LabelWorker.SHUTDOWN_SECONDS, 480)

    def test_import_does_not_load_web_or_server(self):
        source = "from local_inspection_service.label_inspection.worker import LabelWorker; import sys; assert 'local_inspection_service.server' not in sys.modules; assert 'fastapi' not in sys.modules"
        result = subprocess.run([sys.executable, '-X', 'utf8', '-c', source], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
