"""Process-local image worker thread and subprocess registry ownership."""
from collections.abc import Callable
import subprocess
import threading
from typing import Protocol

class WorkerThread(Protocol):
    def is_alive(self) -> bool: ...
    def start(self) -> None: ...

class ThreadFactory(Protocol):
    def __call__(self, *, target: Callable[[], None], name: str, daemon: bool) -> WorkerThread: ...

class ImageWorkerRuntime:
    def __init__(self, *, target: Callable[[], Callable[[], None]], threads: Callable[[], ThreadFactory]):
        self.target = target
        self.threads = threads
        self.lock = threading.Lock()
        self.thread: WorkerThread | None = None
        self.processes: dict[str, subprocess.Popen] = {}

    def start(self) -> bool:
        with self.lock:
            if self.thread and self.thread.is_alive():
                return False
            self.thread = self.threads()(target=self.target(), name="image-generation-worker", daemon=True)
            self.thread.start()
            return True
