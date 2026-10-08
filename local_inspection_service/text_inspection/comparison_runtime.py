"""Prepared-comparison threads, deadline timers and per-application capacity."""
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
import threading
import time
from ..runtime.training_tasks import TrainingThreadLifecycle
from ..runtime.deadline_tasks import DeadlineTimers


class ComparisonRuntime:
    def __init__(self, *, scope: Callable[[], AbstractContextManager] = nullcontext):
        self.threads = TrainingThreadLifecycle(scope=scope)
        self.deadlines = DeadlineTimers(scope=scope)
        self.local_slots = threading.BoundedSemaphore(1)
        self.qwen_slots = threading.BoundedSemaphore(1)

    def close(self, timeout: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout)
        if not self.threads.close(max(0.0, deadline - time.monotonic())):
            return False  # Active comparisons still require their timeout callbacks.
        return self.deadlines.close(max(0.0, deadline - time.monotonic()))


class ComparisonSlot:
    """Acquire inside one worker, return capacity after its outer repository scope."""
    def __init__(self, semaphore: threading.BoundedSemaphore):
        self._semaphore = semaphore
        self._acquired = False
        self._release_requested = False

    def acquire(self, *, timeout: float) -> bool:
        if self._acquired:
            raise RuntimeError("Comparison slot already acquired")
        self._acquired = self._semaphore.acquire(timeout=timeout)
        return self._acquired

    def release(self) -> None:
        if not self._acquired or self._release_requested:
            raise ValueError("Comparison slot released without an acquisition")
        self._release_requested = True

    def wrap(self, target):
        def run(*args, **kwargs):
            try:
                return target(*args, **kwargs)
            finally:
                if self._acquired:
                    self._acquired = False
                    self._semaphore.release()
        return run
