"""Explicit business-file operations; configuration and packaged files stay local."""
from contextlib import contextmanager
import os
import fnmatch
import shutil
import json
from types import SimpleNamespace
from pathlib import Path

from .runtime import get_runtime
from .types import BUSINESS_ROOTS, DiskCapacityError
from .types import Artifact, ArtifactConflict


def _path(value):
    # Preserve Path subclasses and their observable local behavior.
    return value if isinstance(value, Path) else Path(value)


class VersionedDocument(dict):
    """Version travels with an in-process JSON document, never in API/JSON data."""
    def __init__(self, value, path, generation):
        super().__init__(value)
        self.artifact_version = (path, generation)


class BusinessFiles:
    def __init__(self, runtime_provider=get_runtime):
        self.runtime_provider = runtime_provider

    def runtime(self, path):
        runtime = self.runtime_provider()
        if runtime is None:
            return None
        resolved = _path(path).resolve()
        try:
            relative = resolved.relative_to(runtime.root)
        except ValueError:
            return None
        if not relative.parts or relative.parts[0] not in BUSINESS_ROOTS:
            return None
        runtime.key(_path(path))  # validate before selecting any local fallback
        return runtime

    def is_file(self, path):
        path = _path(path)
        runtime = self.runtime(path)
        if runtime is not None:
            row = runtime.store.locations.get(runtime.key(path))
            if row is not None or runtime.mode == "cos":
                return row is not None and row.state == "ready"
        return path.is_file()

    def is_dir(self, path):
        path = _path(path)
        runtime = self.runtime(path)
        if runtime is not None:
            rows = runtime.store.list(runtime.key(path))
            if rows or runtime.mode == "cos":
                return bool(rows)
        return path.is_dir()

    def exists(self, path):
        if self.runtime(path) is None:
            return _path(path).exists()
        return self.is_file(path) or self.is_dir(path)

    def stat(self, path):
        path = _path(path)
        runtime = self.runtime(path)
        if runtime is None:
            return path.stat()
        key = runtime.key(path)
        row = runtime.store.locations.get(key)
        if row is not None:
            if row.state != "ready":
                raise FileNotFoundError("business file not found")
            size, modified = row.size, row.mtime_ns
        else:
            rows = runtime.store.list(key)
            if not rows:
                if runtime.mode == "hybrid":
                    return path.stat()
                raise FileNotFoundError("business path not found")
            size, modified = 0, max(item.mtime_ns for item in rows)
        return SimpleNamespace(st_size=size, st_mtime=modified / 1e9, st_mtime_ns=modified,
                               st_ctime=modified / 1e9, st_ctime_ns=modified)

    def write_bytes(self, path, contents):
        path = _path(path)
        runtime = self.runtime(path)
        if runtime is None:
            return path.write_bytes(contents)
        key = runtime.key(path)
        previous = runtime.store.locations.get(key)
        runtime.store.put_bytes(key, contents, expected_generation=previous.generation if previous else 0)
        return len(contents)

    def read_json(self, path):
        path = _path(path)
        runtime = self.runtime(path)
        if runtime is None:
            return json.loads(path.read_text(encoding="utf-8"))
        key = runtime.key(path)
        row = runtime.store.locations.get(key)
        if row is None and runtime.mode == "hybrid":
            value, generation = json.loads(path.read_text(encoding="utf-8")), 0
        else:
            if row is None or row.state != "ready":
                raise FileNotFoundError("business document not found")
            with runtime.store.cache.open(row) as cached:
                value, generation = json.loads(cached.read_text(encoding="utf-8")), row.generation
        return VersionedDocument(value, key, generation) if isinstance(value, dict) else value

    def write_json(self, path, value, **dump_options):
        path = _path(path)
        runtime = self.runtime(path)
        contents = json.dumps(value, **dump_options)
        if runtime is None:
            return path.write_text(contents, encoding="utf-8")
        key = runtime.key(path)
        version = getattr(value, "artifact_version", (key, 0))
        if version[0] != key:
            raise ArtifactConflict("document belongs to a different logical file")
        row = runtime.store.put_bytes(key, contents.encode(), expected_generation=version[1])
        if isinstance(value, VersionedDocument):
            value.artifact_version = (key, row.generation)

    def write_text(self, path, text, *args, **kwargs):
        if self.runtime(path) is None:
            return _path(path).write_text(text, *args, **kwargs)
        encoding = (args[0] if args else kwargs.get("encoding")) or "utf-8"
        errors = (args[1] if len(args) > 1 else kwargs.get("errors")) or "strict"
        self.write_bytes(path, text.encode(encoding, errors))
        return len(text)

    def read_text(self, path, *args, **kwargs):
        if self.runtime(path) is None:
            return _path(path).read_text(*args, **kwargs)
        encoding = (args[0] if args else kwargs.get("encoding")) or "utf-8"
        errors = (args[1] if len(args) > 1 else kwargs.get("errors")) or "strict"
        return self.read_bytes(path).decode(encoding, errors)

    def unlink(self, path, *, missing_ok=False):
        path = _path(path)
        runtime = self.runtime(path)
        if runtime is None:
            return path.unlink(missing_ok=True) if missing_ok else path.unlink()
        key = runtime.key(path)
        previous = runtime.store.locations.get(key)
        if previous is None or previous.state != "ready":
            if missing_ok:
                return
            raise FileNotFoundError("business file not found")
        runtime.store.remove(key, expected_generation=previous.generation)

    def copy_stream(self, path, source, copy):
        path = _path(path)
        runtime = self.runtime(path)
        if runtime is None:
            with path.open("wb") as output:
                copy(source, output)
            return
        key = runtime.key(path)
        previous = runtime.store.locations.get(key)
        runtime.store.put_stream(key, source, expected_generation=previous.generation if previous else 0)

    def rmtree(self, path, **kwargs):
        path = _path(path)
        ignore_errors = kwargs.get("ignore_errors", False)
        runtime = self.runtime(path)
        if runtime is None:
            return shutil.rmtree(path, **kwargs)
        rows = runtime.store.list(runtime.key(path))
        if not rows and not ignore_errors:
            raise FileNotFoundError("business directory not found")
        for row in rows:
            runtime.store.remove(row.path, expected_generation=row.generation)

    def copy2(self, source, target, *, local_copy=None):
        source, target = _path(source), _path(target)
        local_copy = local_copy if local_copy is not None else shutil.copy2
        source_runtime, target_runtime = self.runtime(source), self.runtime(target)
        if source_runtime is None and target_runtime is None:
            return local_copy(source, target)
        if target_runtime is None:
            with self.local_file(source) as cached:
                return local_copy(cached, target)
        key = target_runtime.key(target)
        previous = target_runtime.store.locations.get(key)
        generation = previous.generation if previous else 0
        row = source_runtime.store.locations.get(source_runtime.key(source)) if source_runtime is not None else None
        if row is not None and row.state == "ready":
            target_runtime.store.objects.verify(row)
            target_runtime.store.locations.publish(Artifact(key, generation + 1, row.sha256, row.size), expected_generation=generation)
        elif source_runtime is not None and (row is not None or source_runtime.mode == "cos"):
            raise FileNotFoundError("copy source is not available")
        else:
            target_runtime.store.put(key, source, expected_generation=generation)
        return str(target)

    def glob(self, path, pattern, *, recursive=False):
        path = _path(path)
        runtime = self.runtime(path)
        if runtime is None:
            return path.rglob(pattern) if recursive else path.glob(pattern)
        if pattern.startswith("/") or ".." in Path(pattern).parts:
            raise ValueError("invalid business glob")
        prefix = runtime.key(path)
        candidates = set()
        for row in runtime.store.list(prefix):
            relative = Path(row.path).relative_to(prefix)
            for count in range(1, len(relative.parts) + 1):
                candidates.add(Path(*relative.parts[:count]))
        parts = ("**/" + pattern if recursive else pattern).split("/")
        def matches(names, patterns):
            if not patterns:
                return not names
            if patterns[0] == "**":
                return matches(names, patterns[1:]) or bool(names) and matches(names[1:], patterns)
            return bool(names) and fnmatch.fnmatchcase(names[0], patterns[0]) and matches(names[1:], patterns[1:])
        result = {path / relative for relative in candidates if matches(relative.parts, parts)}
        if runtime.mode == "hybrid":
            local = path.rglob(pattern) if recursive else path.glob(pattern)
            result.update(item for item in local if self.exists(item))
        return iter(sorted(result))

    def iterdir(self, path):
        if self.runtime(path) is None:
            return _path(path).iterdir()
        return self.glob(path, "*")

    def directories(self, path):
        path = _path(path)
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
        path = _path(path)
        runtime = self.runtime(path)
        if runtime is not None:
            key = runtime.key(path)
            row = runtime.store.locations.get(key)
            if row is not None or runtime.mode == "cos":
                return runtime.store.read_bytes(key, max_bytes=max_bytes)
        return path.read_bytes()

    @contextmanager
    def open_read(self, path):
        path = _path(path)
        runtime = self.runtime(path)
        if runtime is not None:
            key = runtime.key(path)
            row = runtime.store.locations.get(key)
            if row is not None or runtime.mode == "cos":
                with runtime.store.read(key) as stream:
                    yield stream
                return
        with path.open("rb") as stream:
            yield stream

    @contextmanager
    def local_file(self, path):
        path = _path(path)
        runtime = self.runtime(path)
        if runtime is not None:
            key = runtime.key(path)
            row = runtime.store.locations.get(key)
            if row is not None or runtime.mode == "cos":
                # A named link preserves the extension without a second copy.
                # Immutable cross-user blobs cannot be hard-linked on hosts with
                # protected_hardlinks; the cache pin prevents target eviction.
                artifact = runtime.store.stat(key)
                with runtime.store.cache.open(artifact) as cached:
                    with runtime.store.budget.workspace("cache", 0) as workspace:
                        named = workspace / path.name
                        named.symlink_to(cached)
                        yield named
                return
        yield path
