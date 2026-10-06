"""Own cancellable deadline timers through actual native-thread completion."""
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
import threading
import time
from .training_tasks import TrainingThreadLifecycle


class DeadlineTimers:
    def __init__(self, *, scope: Callable[[], AbstractContextManager] = nullcontext):
        self.runtime = TrainingThreadLifecycle(scope=scope)
        self._lock = threading.Lock()
        self._closing = False
        self._timers: list[tuple[threading.Timer, threading.Event]] = []

    def start(self, interval: float, callback: Callable[[], None]) -> threading.Timer:
        return self.runtime.submit(lambda launch: self._start(interval, callback, launch))

    def _start(self, interval, callback, launch):
        created = []
        def construct(wrap):
            completed = threading.Event()
            selected = wrap(callback)
            def finish_callback():
                try: return selected()
                finally: completed.set()
            timer = threading.Timer(interval, finish_callback)
            timer.daemon = True
            created.append(timer)
            with self._lock:
                self._timers = [(value, done) for value, done in self._timers
                                if not ((done.is_set() or value.finished.is_set()) and not value.is_alive())]
                self._timers.append((timer, completed))
                closing = self._closing
            if closing:
                timer.cancel()
            return timer
        try:
            launch(construct, lambda thread: None)
        except BaseException:
            if created:
                try: created[0].cancel()
                except Exception: pass  # Original startup failure stays primary; close retries cancellation.
            raise
        return created[0]

    def close(self, timeout: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout)
        self.runtime.close(0)
        with self._lock:
            self._closing = True
            timers = tuple(timer for timer, _ in self._timers)
        cancelled = True
        for timer in timers:
            try: timer.cancel()
            except Exception: cancelled = False
        drained = self.runtime.close(max(0.0, deadline - time.monotonic()))
        return cancelled and drained
