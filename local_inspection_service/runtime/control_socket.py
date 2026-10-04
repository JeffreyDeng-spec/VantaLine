"""Bounded, root-authenticated local control endpoint with an exclusive process lock."""
from collections.abc import Callable
import json
import os
from pathlib import Path
import socket
import stat
import struct
import threading
import time

from .label_identity import RuntimeUnavailable
from .configuration_contract import CONFIGURATION_LIMIT


class ControlSocket:
    def __init__(self, directory: Path, role: str, handler: Callable[[dict], dict], *, allowed_uid=0, tick: Callable[[], None] | None = None, tick_seconds=5):
        if role not in ("web", "label"):
            raise RuntimeUnavailable("Invalid control role")
        self.directory, self.role, self.handler = directory, role, handler
        self.allowed_uid = allowed_uid
        self.tick, self.tick_seconds = tick, tick_seconds
        self.listener = self.lock_handle = self.thread = None
        self.path = directory / (role + "-control.sock")
        self._stop = threading.Event()

    def acquire(self):
        import fcntl
        if self.listener is not None or self.lock_handle is not None or self.thread is not None:
            raise RuntimeUnavailable("Runtime control endpoint already acquired")
        self._stop.clear()
        try:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = self.directory.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o700):
                raise RuntimeUnavailable("Unsafe runtime control directory")
            path = self.directory / (self.role + "-control.lock")
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            self.lock_handle = os.fdopen(descriptor, "rb+")
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise RuntimeUnavailable("Unsafe runtime control lock")
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.path.is_symlink():
                raise RuntimeUnavailable("Unsafe runtime control socket")
            if self.path.exists():
                info = self.path.lstat()
                if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                    raise RuntimeUnavailable("Unsafe runtime control socket")
                self.path.unlink()  # Exclusive role lock proves no participating owner.
            self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.listener.bind(str(self.path))
            os.chmod(self.path, 0o600)
            self.listener.listen(4)
            self.listener.settimeout(.2)
        except BaseException:
            self.close()
            raise RuntimeUnavailable("Runtime control endpoint unavailable") from None

    def start(self):
        if self.listener is None or self.thread is not None:
            raise RuntimeUnavailable("Runtime control endpoint not acquired")
        self.thread = threading.Thread(target=self._serve, name="label-runtime-control", daemon=True)
        self.thread.start()

    def _serve(self):
        next_tick = time.monotonic() + self.tick_seconds
        while not self._stop.is_set():
            if self.tick is not None and time.monotonic() >= next_tick:
                # Same thread/connection lifecycle as commands. A blocked heartbeat
                # retains the role lock through the existing shutdown deadline.
                self.tick()
                next_tick = time.monotonic() + self.tick_seconds
                if self._stop.is_set():
                    return
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with connection:
                try:
                    _, uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                    if uid != self.allowed_uid:
                        continue
                    deadline = time.monotonic() + 2
                    body = bytearray()
                    while not body.endswith(b"\n"):
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise ValueError()
                        connection.settimeout(remaining)
                        chunk = connection.recv(1025 - len(body))
                        if not chunk or len(body) + len(chunk) > 1024:
                            raise ValueError()
                        body.extend(chunk)
                    value = json.loads(body)
                    response = self.handler(value)
                    encoded = json.dumps(response, separators=(",", ":")).encode() + b"\n"
                    limit = CONFIGURATION_LIMIT + 32768 if isinstance(value, dict) and value.get("command") == "configuration" else 16384
                    if len(encoded) > limit:
                        raise ValueError()
                    connection.settimeout(1)
                    connection.sendall(encoded)
                except Exception:
                    # Never return a driver's/provider's exception or internal path.
                    try:
                        connection.settimeout(.1)
                        connection.sendall(b'{"error":"runtime_control_unavailable"}\n')
                    except OSError:
                        pass

    def close(self):
        self._stop.set()
        if self.listener is not None:
            self.listener.close()
        if self.thread is not None and self.thread.ident is not None:
            self.thread.join(3)
            if self.thread.is_alive():
                raise RuntimeUnavailable("Runtime control thread did not stop")
        self.thread = None
        # Do not unlink a live socket on a failed competing acquire.
        if self.listener is not None:
            self.path.unlink(missing_ok=True)
            self.listener = None
        if self.lock_handle is not None:
            self.lock_handle.close()
            self.lock_handle = None
