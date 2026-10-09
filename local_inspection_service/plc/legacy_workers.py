"""State ownership for retained, disabled server-side PLC workers.

The Web Serial startup hook does not activate these legacy entry points.
"""
from collections.abc import Callable
from dataclasses import dataclass
import threading
import time
from typing import Any


@dataclass(frozen=True)
class LegacyHeartbeatCapabilities:
    repository: Callable[[], Callable[[], object | None]]
    config: Callable[[], Callable[[], dict[str, Any]]]
    namespace: Callable[[], Callable[[dict[str, Any]], Any]]
    renew: Callable[[], Callable[[], dict[str, Any] | None]]
    seconds: Callable[[], float]


@dataclass(frozen=True)
class LegacyLoopCapabilities:
    reconcile: Callable[[], Callable[[], dict[str, Any] | None]]
    poll: Callable[[], Callable[[], dict[str, Any] | None]]
    seconds: Callable[[], float]


class LegacyPlcWorkers:
    def __init__(self, heartbeat: LegacyHeartbeatCapabilities, loops: LegacyLoopCapabilities):
        self.heartbeat, self.loops = heartbeat, loops
        self._plc_owner_heartbeat_lock = threading.Lock()
        self._plc_owner_heartbeat_thread: threading.Thread | None = None
        self._plc_capture_poller_lock = threading.Lock()
        self._plc_capture_poller_thread: threading.Thread | None = None
        self._plc_dispatch_reconciler_lock = threading.Lock()
        self._plc_dispatch_reconciler_thread: threading.Thread | None = None

    def plc_start_owner_heartbeat(self, epoch: int) -> None:
        with self._plc_owner_heartbeat_lock:
            if self._plc_owner_heartbeat_thread is not None and self._plc_owner_heartbeat_thread.is_alive():
                return
            def heartbeat() -> None:
                while True:
                    time.sleep(self.heartbeat.seconds())
                    try:
                        if self.heartbeat.repository()() is None:
                            return
                        current = self.heartbeat.config()()
                        raw = self.heartbeat.namespace()(current)
                        if not isinstance(raw, dict) or not bool(raw.get("enabled")):
                            return
                        renewed = self.heartbeat.renew()()
                        if renewed is None or int(renewed.get("epoch") or 0) != epoch:
                            return
                    except Exception:
                        return
            self._plc_owner_heartbeat_thread = threading.Thread(
                target=heartbeat,
                name="plc-io-owner-heartbeat",
                daemon=True,
            )
            self._plc_owner_heartbeat_thread.start()


    def start_plc_dispatch_reconciler(self) -> None:
        with self._plc_dispatch_reconciler_lock:
            if self._plc_dispatch_reconciler_thread is not None and self._plc_dispatch_reconciler_thread.is_alive():
                return
            def reconcile() -> None:
                while True:
                    try:
                        self.loops.reconcile()()
                    except Exception:
                        pass
                    time.sleep(self.loops.seconds())
            self._plc_dispatch_reconciler_thread = threading.Thread(
                target=reconcile,
                name="plc-dispatch-reconciler",
                daemon=True,
            )
            self._plc_dispatch_reconciler_thread.start()


    def start_plc_capture_poller(self) -> None:
        with self._plc_capture_poller_lock:
            if self._plc_capture_poller_thread is not None and self._plc_capture_poller_thread.is_alive():
                return
            def poll() -> None:
                while True:
                    try:
                        self.loops.poll()()
                    except Exception:
                        pass
                    time.sleep(self.loops.seconds())
            self._plc_capture_poller_thread = threading.Thread(
                target=poll,
                name="plc-capture-input-poller",
                daemon=True,
            )
            self._plc_capture_poller_thread.start()
