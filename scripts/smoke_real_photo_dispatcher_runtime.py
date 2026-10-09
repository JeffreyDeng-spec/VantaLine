"""Real dispatcher threads, scope exits and dependent teardown without providers."""
from contextlib import contextmanager, nullcontext
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.training.dispatcher_runtime import DispatcherRuntime
from local_inspection_service.runtime.shutdown import WebShutdown, ShutdownStep
from local_inspection_service.runtime.training_tasks import TrainingRuntimeClosed


class DispatcherContracts(unittest.TestCase):
    def owner(self, scope=nullcontext, **kwargs):
        owner = DispatcherRuntime(scope=scope, **kwargs)
        self.addCleanup(lambda: owner.close(3))
        return owner

    def test_constructor_inert_and_repeated_start_then_close_is_terminal(self):
        scope, create = Mock(side_effect=AssertionError("eager scope")), Mock(side_effect=AssertionError("eager thread"))
        owner = DispatcherRuntime(scope=scope, create_thread=create)
        scope.assert_not_called(); create.assert_not_called()
        self.assertTrue(owner.close(0))
        with self.assertRaises(TrainingRuntimeClosed): owner.start(lambda: None, None)
        create.assert_not_called()
        made = []
        def factory(**kwargs):
            thread = threading.Thread(**kwargs); made.append(thread); return thread
        owner = self.owner(create_thread=factory)
        owner.start(lambda: None, lambda: None)
        owner.start(lambda: self.fail("duplicate mask"), lambda: self.fail("duplicate training"))
        self.assertEqual(len(made), 2)
        self.assertTrue(owner.close(2))
        self.assertTrue(owner.close(0))
        with self.assertRaises(TrainingRuntimeClosed): owner.start(lambda: None, None)

    def test_blocked_tick_stops_dependency_close_and_does_not_repeat_call(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        calls = []
        def tick():
            calls.append("same-id"); entered.set(); release.wait(4)
        owner = self.owner(); owner.start(tick, None)
        self.assertTrue(entered.wait(3))
        dependencies = []
        shutdown = WebShutdown((owner.stop,), (
            ShutdownStep("real-photo-dispatch", owner.close),
            ShutdownStep("training", lambda budget: dependencies.append("training") or True),
            ShutdownStep("model-mcp", lambda budget: dependencies.append("model-mcp") or True)))
        self.assertFalse(shutdown.close(.01))
        self.assertEqual(shutdown.failed_component, "real-photo-dispatch")
        self.assertEqual(dependencies, [])
        release.set()
        self.assertTrue(shutdown.close(2))
        self.assertEqual(dependencies, ["training", "model-mcp"])
        self.assertEqual(calls, ["same-id"])

    def test_scope_exit_is_part_of_drain(self):
        exiting, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        @contextmanager
        def scope():
            try: yield
            finally: exiting.set(); release.wait(4)
        owner = self.owner(scope=scope); owner.start(lambda: None, None)
        owner.stop(); self.assertTrue(exiting.wait(2))
        self.assertFalse(owner.close(.01))
        release.set(); self.assertTrue(owner.close(2))

    def test_partial_constructor_failure_keeps_first_thread_and_no_restart(self):
        threads = []
        def factory(**kwargs):
            if threads: raise ValueError("second constructor failed")
            thread = threading.Thread(**kwargs); threads.append(thread); return thread
        owner = self.owner(create_thread=factory)
        with self.assertRaisesRegex(ValueError, "second constructor"):
            owner.start(lambda: None, lambda: None)
        with self.assertRaises(TrainingRuntimeClosed): owner.start(lambda: self.fail("retry"), None)
        self.assertEqual(len(threads), 1)
        self.assertTrue(owner.close(2)); self.assertFalse(threads[0].is_alive())

    def test_uncertain_start_fails_closed_and_is_not_retried(self):
        class Unknown:
            def start(self): raise RuntimeError("uncertain start")
            def join(self, timeout): raise RuntimeError("unjoinable")
        create = Mock(return_value=Unknown())
        owner = self.owner(create_thread=create)
        with self.assertRaisesRegex(RuntimeError, "uncertain start"):
            owner.start(lambda: None, None)
        with self.assertRaises(TrainingRuntimeClosed): owner.start(lambda: None, None)
        create.assert_called_once()
        self.assertFalse(owner.close(.01))

    def test_two_owners_and_start_close_race_have_independent_scopes(self):
        events, lock = [], threading.Lock()
        def scope(name):
            @contextmanager
            def entered():
                with lock: events.append((name, "enter"))
                try: yield
                finally:
                    with lock: events.append((name, "exit"))
            return entered
        a, b = self.owner(scope("a")), self.owner(scope("b"))
        a.start(lambda: None, None); b.start(lambda: None, None)
        self.assertTrue(a.close(2)); self.assertFalse(b._stop.is_set())
        self.assertTrue(b.close(2))
        self.assertCountEqual(events, [("a", "enter"), ("a", "exit"), ("b", "enter"), ("b", "exit")])
        for _ in range(8):
            owner = self.owner(); barrier = threading.Barrier(2)
            def start():
                barrier.wait()
                try: owner.start(lambda: self.fail("closing tick"), None)
                except TrainingRuntimeClosed: pass
            def close(): barrier.wait(); return owner.close(2)
            with ThreadPoolExecutor(2) as pool:
                started = pool.submit(start); closed = pool.submit(close)
                started.result(3); self.assertTrue(closed.result(3))
            with self.assertRaises(TrainingRuntimeClosed): owner.start(lambda: None, None)


if __name__ == "__main__": unittest.main()
