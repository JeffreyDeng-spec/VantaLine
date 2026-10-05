"""Explicit per-application ownership for request, store and JSON read caches."""
from collections.abc import Callable
import contextlib
import contextvars
import json
from pathlib import Path
import threading
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from ..storage.artifacts.files import BusinessFiles

class RequestReadCache:
    def __init__(self):
        self.current: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
            "vantaline_read_path_cache", default=None
        )

    @contextlib.contextmanager
    def scope(self):
        if self.current.get() is not None:
            # Nested scopes reuse the outer cache.
            yield
            return
        token = self.current.set({})
        try:
            yield
        finally:
            self.current.reset(token)


class StoreReadCache:
    def __init__(self, ttl: Callable[[], float], clock: Callable[[], float]):
        self.ttl = ttl
        self.clock = clock
        self.lock = threading.Lock()
        self.values: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> tuple[bool, Any]:
        now = self.clock()
        with self.lock:
            entry = self.values.get(key)
            if entry and now - entry[0] < self.ttl():
                return True, entry[1]
        return False, None


    def put(self, key: str, value: Any) -> None:
        with self.lock:
            self.values[key] = (self.clock(), value)


    def invalidate(self, *keys: str) -> None:
        with self.lock:
            for key in keys:
                self.values.pop(key, None)


class JsonFileReadCache:
    def __init__(self, files: Callable[[], "BusinessFiles"]):
        self.files = files
        self.lock = threading.Lock()
        self.values: dict[str, tuple[int, int, Any]] = {}

    def load(self, path: Path) -> Any:
        'Parse a JSON file with an mtime/size-validated cache. Returns None when\n    the file is missing or invalid. Callers must treat the result as\n    read-only.'
        runtime = self.files().runtime(path)
        if runtime is not None:
            logical = runtime.key(path)
            row = runtime.store.locations.get(logical)
            if row is not None or runtime.mode == "cos":
                if row is None or row.state != "ready":
                    return None
                key = "cos:" + logical
                with self.lock:
                    entry = self.values.get(key)
                    if entry and entry[0] == row.generation and entry[1] == row.size:
                        return entry[2]
                try:
                    with runtime.store.cache.open(row) as local:
                        value = json.loads(self.files().read_text(local, encoding="utf-8"))
                except json.JSONDecodeError:
                    return None
                with self.lock:
                    self.values[key] = (row.generation, row.size, value)
                return value
        try:
            stat_result = path.stat()
        except OSError:
            return None
        key = str(path)
        with self.lock:
            entry = self.values.get(key)
            if entry and entry[0] == stat_result.st_mtime_ns and entry[1] == stat_result.st_size:
                return entry[2]
        try:
            value = json.loads(self.files().read_text(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        with self.lock:
            self.values[key] = (stat_result.st_mtime_ns, stat_result.st_size, value)
        return value
