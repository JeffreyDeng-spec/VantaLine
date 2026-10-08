"""Real-thread pause/claim/cleanup fences without model calls or PostgreSQL."""
from pathlib import Path
import sys
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.artifacts.runtime import get_runtime
from local_inspection_service.label_inspection.worker import LabelWorker
from local_inspection_service.label_inspection.dependencies import RepositoryLifecycle


class PauseContracts(unittest.TestCase):
    def setUp(self):
        self.events, self.workers = [], []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for event in self.events:
            event.set()
        for worker in self.workers:
            self.assertTrue(worker.drain(3))

    def event(self):
        event = threading.Event()
        self.events.append(event)
        return event

    def worker(self, clear=lambda: None):
        worker = LabelWorker(RepositoryLifecycle(lambda: None, clear), lambda: Path("synthetic"), lambda: None, runtime_provider=get_runtime)
        self.workers.append(worker)
        return worker

    def wait_state(self, worker, state):
        deadline = time.monotonic() + 3
        while worker.runtime_status()["state"] != state and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertEqual(worker.runtime_status()["state"], state)

    def test_initial_pause_has_no_claim_and_resume_reuses_two_threads(self):
        worker = self.worker()
        entered, release = threading.Barrier(3), self.event()
        calls = []
        def iteration():
            calls.append(threading.current_thread())
            entered.wait(3)
            release.wait(3)
            return True
        worker._iteration = iteration
        worker.start(paused=True)
        original = tuple(worker._threads)
        self.assertEqual(worker.runtime_status(), {"state": "drained", "active_iterations": 0})
        self.assertEqual(calls, [])
        worker.start()  # Duplicate lifecycle startup cannot override a pause.
        self.assertEqual(worker.runtime_status()["state"], "drained")
        worker.resume()
        entered.wait(3)
        worker.request_pause()
        self.assertEqual(worker.runtime_status(), {"state": "draining", "active_iterations": 2})
        release.set()
        self.wait_state(worker, "drained")
        self.assertEqual(len(calls), 2)
        self.assertEqual(tuple(worker._threads), original)
        self.assertTrue(all(thread.is_alive() for thread in original))
        worker._iteration = lambda: False
        worker.resume()
        self.assertEqual(worker.runtime_status()["state"], "ready")
        worker.request_pause()
        self.wait_state(worker, "drained")

    def test_connection_cleanup_is_included_before_drained_ack(self):
        entered, release = threading.Barrier(3), self.event()
        def clear():
            entered.wait(3)
            release.wait(3)
        worker = self.worker(clear)
        worker._iteration = lambda: False
        worker.start()
        entered.wait(3)
        worker.request_pause()
        self.assertEqual(worker.runtime_status(), {"state": "draining", "active_iterations": 2})
        release.set()
        self.wait_state(worker, "drained")

    def test_stop_while_paused_exits_and_cannot_resume(self):
        worker = self.worker()
        worker.start(paused=True)
        self.assertTrue(worker.drain(1))
        self.assertEqual(worker.runtime_status()["state"], "failed")
        with self.assertRaises(RuntimeError):
            worker.resume()

    def test_many_pause_resume_cycles_never_replace_threads(self):
        worker = self.worker()
        worker._iteration = lambda: False
        worker.start(paused=True)
        threads = tuple(worker._threads)
        for _ in range(20):
            worker.resume()
            worker.request_pause()
            self.wait_state(worker, "drained")
        self.assertEqual(tuple(worker._threads), threads)


if __name__ == "__main__":
    unittest.main()
