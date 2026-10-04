"""Explicit business-file operations; configuration and packaged files stay local."""
from contextlib import contextmanager
from pathlib import Path

from .runtime import get_runtime
from .types import BUSINESS_ROOTS, DiskCapacityError


class BusinessFiles:
    def __init__(self, runtime_provider=get_runtime):
        self.runtime_provider = runtime_provider

    def runtime(self, path):
        runtime = self.runtime_provider()
        if runtime is None:
            return None
        resolved = Path(path).resolve()
        try:
            relative = resolved.relative_to(runtime.root)
        except ValueError:
            return None
        if not relative.parts or relative.parts[0] not in BUSINESS_ROOTS:
            return None
        runtime.key(Path(path))  # validate before selecting any local fallback
        return runtime

    def is_file(self, path):
        path = Path(path)
        runtime = self.runtime(path)
        if runtime is not None:
            row = runtime.store.locations.get(runtime.key(path))
            if row is not None or runtime.mode == "cos":
                return row is not None and row.state == "ready"
        return path.is_file()

    def is_dir(self, path):
        path = Path(path)
        runtime = self.runtime(path)
        if runtime is not None:
            rows = runtime.store.list(runtime.key(path))
            if rows or runtime.mode == "cos":
                return bool(rows)
        return path.is_dir()

    def exists(self, path):
        return self.is_file(path) or self.is_dir(path)

    def directories(self, path):
        path = Path(path)
        runtime = self.runtime(path)
        names = set()
        if runtime is None or runtime.mode == "hybrid":
            if path.is_dir():
                names.update(item.name for item in path.iterdir() if item.is_dir())
        if runtime is not None:
            prefix = runtime.key(path)
            for row in runtime.store.list(prefix):
                relative = Path(row.path).relative_to(prefix)
                if len(relative.parts) > 1:
                    names.add(relative.parts[0])
        return [path / name for name in sorted(names)]

    def read_bytes(self, path, *, max_bytes=120*1024*1024):
        path = Path(path)
        runtime = self.runtime(path)
        if runtime is not None:
            key = runtime.key(path)
            row = runtime.store.locations.get(key)
            if row is not None or runtime.mode == "cos":
                return runtime.store.read_bytes(key, max_bytes=max_bytes)
        if path.stat().st_size > max_bytes:
            raise DiskCapacityError("file exceeds operation size limit")
        return path.read_bytes()

    @contextmanager
    def local_file(self, path):
        path = Path(path)
        runtime = self.runtime(path)
        if runtime is not None:
            key = runtime.key(path)
            row = runtime.store.locations.get(key)
            if row is not None or runtime.mode == "cos":
                # Named file lifetime covers the native loader, not its caller.
                with runtime.store.materialize(key) as materialized:
                    yield materialized
                return
        yield path
