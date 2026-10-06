"""Real subprocess signal injection at startup boundaries; no model or database I/O."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.artifacts.runtime import get_runtime
from local_inspection_service.label_inspection.runtime import LabelProcess
from local_inspection_service.label_inspection.dependencies import RepositoryLifecycle
from local_inspection_service.runtime.configuration import ConfigurationSnapshot
from local_inspection_service.runtime.label_identity import LabelRuntimeIdentity


def child(checkpoint, signum):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        snapshot = ConfigurationSnapshot.capture({"VANTALINE_DATA_STORE": "postgres", "DATABASE_URL": "fixture"}, root)
        identity = LabelRuntimeIdentity("a" * 40, "v2026.10.1", "external", snapshot.revision)
        events = []
        repositories = RepositoryLifecycle(lambda: None, lambda: events.append("clear"))
        models = SimpleNamespace(initialize=lambda: events.append("initialize"))
        process = LabelProcess(identity, snapshot, root, repositories, repositories,
            models=models, control_directory=root / "control", allowed_uid=os.getuid(), runtime_provider=get_runtime)
        for number in (signal.SIGTERM, signal.SIGINT):
            signal.signal(number, process.request_stop)
        process.worker._iteration = lambda: events.append("iteration") or False
        def send():
            os.kill(os.getpid(), signum)
            os.kill(os.getpid(), signum)  # Repeated signals must not deadlock cleanup.
        if checkpoint == "before_initialize":
            send()
        elif checkpoint == "initialize":
            models.initialize = lambda: send()
        elif checkpoint == "before_worker_start":
            def start_control():
                send()
                process.worker.start()
            process.control.start = start_control
        elif checkpoint == "idle_wait":
            def start_control():
                process.worker.start(paused=True)
                process.control.socket.thread = SimpleNamespace(is_alive=lambda: True)
                threading.Timer(.1, send).start()
            process.control.start = start_control
            process.control.close = lambda: None
        elif checkpoint == "thread_start":
            original = threading.Thread.start
            def thread_start(thread):
                # Actual LabelWorker.start owns its ordinary lock at this point.
                send()
                original(thread)
            process.control.start = lambda: process.worker.start()
            with patch.object(threading.Thread, "start", thread_start):
                process.run()
            assert "iteration" not in events
            assert not any(thread.is_alive() for thread in process.worker._threads)
            return
        else:
            raise AssertionError(checkpoint)
        process.run()
        assert "iteration" not in events
        assert not any(thread.is_alive() for thread in process.worker._threads)
        if checkpoint in ("before_initialize", "initialize"):
            assert process.worker._threads == []
        if checkpoint == "before_initialize":
            assert "initialize" not in events


class StartupSignals(unittest.TestCase):
    def test_signal_is_monotonic_and_does_not_reenter_startup_locks(self):
        for number in (signal.SIGTERM, signal.SIGINT):
            for checkpoint in ("before_initialize", "initialize", "before_worker_start", "thread_start", "idle_wait"):
                with self.subTest(signal=number, checkpoint=checkpoint):
                    result = subprocess.run([sys.executable, __file__, "--child", checkpoint, str(int(number))],
                        capture_output=True, text=True, timeout=6)
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child(sys.argv[2], int(sys.argv[3]))
    else:
        unittest.main()
