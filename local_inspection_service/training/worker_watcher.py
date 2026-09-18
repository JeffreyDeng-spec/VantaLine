"""Retired watcher no-ops, lazy settings and explicit loop capabilities; nothing starts a thread."""
from collections.abc import Callable, Mapping
from typing import Any


def worker_training_watcher_enabled() -> bool:
    return False


def _worker_training_watch_once() -> int:
    """Windows-worker execution is retired; historical worker records are read-only."""
    return 0


def start_worker_training_watcher() -> None:
    return None



class WorkerWatcherSettings:
    def __init__(self, environment: Callable[[], Mapping[str, str]]):
        self.environment = environment

    def worker_training_watcher_interval_seconds(self) -> float:
        try:
            return max(5.0, min(600.0, float(self.environment().get("INSPECTION_WORKER_WATCHER_INTERVAL_SECONDS", "") or 20.0)))
        except (TypeError, ValueError):
            return 20.0


class WorkerWatcherLoop:
    def __init__(self, interval: Callable[[], float], watch: Callable[[], Any],
                 report_error: Callable[[], None], sleep: Callable[[float], None]):
        self.interval, self.watch, self.report_error, self.sleep = interval, watch, report_error, sleep

    def _worker_training_watcher_loop(self) -> None:
        interval = self.interval()
        while True:
            try:
                self.watch()
            except Exception:  # noqa: BLE001 - 守护线程必须保持存活
                self.report_error()
            self.sleep(interval)
