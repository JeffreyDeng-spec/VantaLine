"""Publish shared transfer counters using explicit event, thread and task-update capabilities."""
from collections.abc import Callable
import threading
import time
from ..runtime.training_tasks import TrainingThreadLifecycle, ThreadLaunch
from typing import Any, Protocol


class TransferProgressUpdate(Protocol):
    def __call__(self, job_id: str, **updates: Any) -> Any: ...


class TransferProgressThread(Protocol):
    def __call__(self, *, target: Callable[[], None], name: str, daemon: bool) -> threading.Thread: ...


class TransferProgress:
    def __init__(self, update_provider: Callable[[], TransferProgressUpdate], event_factory: Callable[[], threading.Event],
                 thread_provider: Callable[[], TransferProgressThread], *, runtime: TrainingThreadLifecycle | None = None):
        # Each flush captures its updater before reading or converting counters.
        self.update_provider, self.event_factory, self.thread_provider = update_provider, event_factory, thread_provider
        self.runtime = runtime if runtime is not None else TrainingThreadLifecycle()
        self._stop_lock = threading.Lock()
        self._closing = False
        self._stops: list[threading.Event] = []

    def _start_transfer_progress_thread(self,
        job_id: str,
        state: dict[str, int],
        *,
        done_field: str,
        total_field: str,
        status_field: str,
        interval: float = 1.5,
    ) -> tuple[threading.Event, threading.Thread]:
        """Periodically flush an in-memory byte counter to the training task file so the
    frontend can render a live transfer progress bar without per-chunk disk writes."""
        return self.runtime.submit(lambda launch: self._start(job_id, state, done_field=done_field,
            total_field=total_field, status_field=status_field, interval=interval, launch=launch))

    def _start(self, job_id, state, *, done_field, total_field, status_field, interval, launch: ThreadLaunch):
        stop = self.event_factory()
        with self._stop_lock:
            self._stops.append(stop)
            closing = self._closing
        if closing:
            stop.set()

        def _loop() -> None:
            while not stop.wait(interval):
                try:
                    self.update_provider()(
                        job_id,
                        **{
                            done_field: int(state.get("done", 0)),
                            total_field: int(state.get("total", 0)),
                            status_field: "running",
                        },
                    )
                except Exception:  # noqa: BLE001 - progress flushing must never break the transfer
                    pass

        created = []
        def construct(wrap):
            factory = self.thread_provider()
            scoped_loop = wrap(_loop)
            def owned_loop():
                try:
                    return scoped_loop()
                finally:
                    with self._stop_lock:
                        self._stops = [event for event in self._stops if event is not stop]
            thread = factory(target=owned_loop, name=f"transfer-progress-{job_id}", daemon=True)
            created.append(thread)
            return thread
        try:
            launch(construct, lambda thread: None)
        except BaseException:
            if not created:
                with self._stop_lock:
                    self._stops = [event for event in self._stops if event is not stop]
            raise
        return stop, created[0]

    def close(self, timeout: float) -> bool:
        """Stop periodic reporting and drain owned threads; never cancel a transfer."""
        deadline = time.monotonic() + max(0.0, timeout)
        self.runtime.close(0)  # Close admission before signalling current/pending reporters.
        with self._stop_lock:
            self._closing = True
            stops = tuple(self._stops)
        signalled = True
        for stop in stops:
            try:
                stop.set()
            except Exception:
                signalled = False
        drained = self.runtime.close(max(0.0, deadline - time.monotonic()))
        return signalled and drained
