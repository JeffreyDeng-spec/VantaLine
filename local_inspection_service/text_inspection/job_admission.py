"""Transfer one acquired text-job slot from submitter to its native target."""
from collections.abc import Callable
import threading
from typing import Any


class JobPermit:
    def __init__(self, semaphore: threading.BoundedSemaphore):
        self._semaphore = semaphore
        self._lock = threading.Lock()
        self._state = 'reserved'

    def cancel(self) -> None:
        """Return only a slot not yet taken over by the target."""
        with self._lock:
            if self._state != 'reserved':
                return
            self._state = 'released'
        self._semaphore.release()

    def wrap(self, selected: Callable[..., Any]) -> Callable[..., Any]:
        def run(*args, **kwargs):
            with self._lock:
                if self._state != 'reserved':
                    return
                self._state = 'running'
            try:
                return selected(*args, **kwargs)
            finally:
                with self._lock:
                    self._state = 'released'
                self._semaphore.release()
        return run
