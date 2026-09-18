"""Publish shared transfer counters using explicit event, thread and task-update capabilities."""
from collections.abc import Callable
import threading
from typing import Any, Protocol


class TransferProgressUpdate(Protocol):
    def __call__(self, job_id: str, **updates: Any) -> Any: ...


class TransferProgressThread(Protocol):
    def __call__(self, *, target: Callable[[], None], name: str, daemon: bool) -> threading.Thread: ...


class TransferProgress:
    def __init__(self, update_provider: Callable[[], TransferProgressUpdate], event_factory: Callable[[], threading.Event],
                 thread_provider: Callable[[], TransferProgressThread]):
        # Each flush captures its updater before reading or converting counters.
        self.update_provider, self.event_factory, self.thread_provider = update_provider, event_factory, thread_provider

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
        stop = self.event_factory()

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

        thread = self.thread_provider()(target=_loop, name=f"transfer-progress-{job_id}", daemon=True)
        thread.start()
        return stop, thread
