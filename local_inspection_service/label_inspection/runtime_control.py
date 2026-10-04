"""Label control operations shared by embedded and independent consumer processes."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import threading
import time
import uuid

from ..runtime.control_socket import ControlSocket
from ..runtime.label_identity import LabelRuntimeIdentity, RuntimeUnavailable
from ..storage.label_runtime import LabelRuntimeStore


class LabelRuntimeControl:
    def __init__(self, identity: LabelRuntimeIdentity, repositories, worker, *, role="web",
                 directory=Path("/opt/vantaline/shared/data/runtime-control"), allowed_uid=0):
        self.identity, self.repositories, self.worker = identity, repositories, worker
        self.role = role
        self.instance = uuid.uuid4().hex
        self.pid = os.getpid()
        self._lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._started = False
        self.socket = ControlSocket(directory, role, self.command, allowed_uid=allowed_uid)

    @contextmanager
    def store(self):
        try:
            repository = self.repositories.repository()
            if repository is None:
                raise RuntimeUnavailable("Label runtime database unavailable")
            # This thread owns this connection. Bound each control SQL operation.
            with repository.connection.cursor() as cursor:
                cursor.execute("SET statement_timeout='1500ms'; SET lock_timeout='1000ms'")
            repository.connection.commit()
            yield LabelRuntimeStore(repository)
        finally:
            self.repositories.clear()

    def start(self):
        with self._lifecycle_lock:
            if self._started:
                if (self.socket.thread is None or not self.socket.thread.is_alive()
                        or (self.worker is not None and self.worker.runtime_status()["state"] not in ("ready", "drained"))):
                    raise RuntimeUnavailable("Label runtime lifecycle is not available")
                return
            self.instance, self.pid = uuid.uuid4().hex, os.getpid()
            self.socket.acquire()
            try:
                with self.store() as store:
                    if self.role == "web":
                        state = store.initialize(self.identity)
                    else:
                        state, _ = store.snapshot(self.identity)
                if self.worker is not None:
                    self.worker.runtime_identity = self.identity
                    self.worker.start(paused=state["paused"])
                self.socket.start()
                self._started = True
            except BaseException:
                if self.worker is not None and not self.worker.drain(3):
                    raise RuntimeUnavailable("Label runtime startup drain failed") from None
                self.socket.close()
                raise

    def command(self, value):
        if (not isinstance(value, dict) or value.keys() != {"schema", "command", "revision"}
                or type(value["schema"]) is not int or value["schema"] != 1
                or not isinstance(value["revision"], str) or not re.fullmatch(r"[0-9a-f]{32}", value["revision"])):
            raise RuntimeUnavailable("Invalid runtime control request")
        command = value["command"]
        if command not in ("status", "pause", "resume", "open_admission", "close_admission"):
            raise RuntimeUnavailable("Unsupported runtime control request")
        if command in ("open_admission", "close_admission") and self.role != "web":
            raise RuntimeUnavailable("Only Web controls admission")
        if command in ("pause", "resume") and self.worker is None:
            raise RuntimeUnavailable("This process is not the label consumer")
        with self._lock, self.store() as store:
            if command in ("open_admission", "close_admission"):
                store.change(self.identity, value["revision"], maintenance=command == "close_admission")
            elif command == "pause":
                store.change(self.identity, value["revision"], paused=True)
                self.worker.request_pause()
            elif command == "resume":
                # Validate this generation before changing the durable intent.
                if self.worker.runtime_status()["state"] not in ("ready", "drained"):
                    raise RuntimeUnavailable("Label consumer cannot resume")
                store.change(self.identity, value["revision"], paused=False)
                self.worker.resume()
            state, queue = store.snapshot(self.identity)
            runtime = self.worker.runtime_status() if self.worker is not None else {"state": "ready", "active_iterations": 0}
            return {"schema": 1, "git_commit": self.identity.commit, "release": self.identity.release,
                    "worker_mode": self.identity.mode, "role": self.role, "instance": self.instance,
                    "pid": self.pid, "heartbeat": time.monotonic(), "control_revision": state["revision"],
                    "maintenance": state["maintenance"], "config_revision": self.identity.config_revision,
                    "queued_runs": queue["queued_runs"], "active_runs": queue["active_runs"], **runtime}

    def close(self):
        with self._lifecycle_lock:
            self.socket.close()
            self._started = False
