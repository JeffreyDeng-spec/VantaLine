"""Validated opt-in composition; local mode imports neither SDK nor Unix locks."""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Callable, Mapping
from typing import Protocol
import json
import logging
import os
from pathlib import Path
import re
import stat
import shutil
import threading

from .types import ArtifactUnavailable, logical_path


@dataclass(frozen=True)
class ArtifactRuntime:
    store: object
    root: Path
    mode: str

    def key(self, path: Path) -> str:
        path = Path(path)
        if ".." in path.parts:
            raise ValueError("invalid business file path")
        # Callers supply paths below the configured real runtime root. Resolving
        # the existing release's data symlink preserves legacy absolute records.
        return logical_path(path.resolve().relative_to(self.root).as_posix())


class RuntimeBuilder(Protocol):
    def __call__(
        self, mode: str, data_root: str, work_root: str, cache_root: str,
        bucket: str, database_url: str, credentials_directory: str,
        *, hard_limits: bool, upload_root: str,
    ) -> ArtifactRuntime: ...


class ArtifactRuntimeProvider:
    """Own one lazy configuration-bound artifact runtime without starting resources."""
    def __init__(
        self, environment: Callable[[], Mapping[str, str]],
        *, builder: RuntimeBuilder | None = None,
    ) -> None:
        self._environment = environment
        self._builder = builder
        self._lock = threading.Lock()
        self._runtime: ArtifactRuntime | None = None
        self._signature: tuple[str, ...] | None = None

    def get(self) -> ArtifactRuntime | None:
        environment = self._environment()
        mode = environment.get("VANTALINE_FILE_STORE", "local")
        if mode == "local":
            return None
        if mode not in {"hybrid", "cos"}:
            raise ValueError("VANTALINE_FILE_STORE must be local, hybrid or cos")
        required = ("VANTALINE_DATA_ROOT", "VANTALINE_ARTIFACT_WORK_ROOT", "VANTALINE_ARTIFACT_CACHE_ROOT",
                    "VANTALINE_COS_BUCKET", "DATABASE_URL", "CREDENTIALS_DIRECTORY")
        values = tuple(environment.get(key, "") for key in required)
        if not all(values):
            raise ValueError("COS storage requires data, work, cache, database and systemd credential configuration")
        hard_limits = environment.get("VANTALINE_ARTIFACT_HARD_LIMITS", "0")
        upload_root = environment.get("VANTALINE_ARTIFACT_UPLOAD_ROOT", "")
        if hard_limits not in {"0", "1"}:
            raise ValueError("invalid temporary hard-limit setting")
        signature = (mode, *values, hard_limits, upload_root)
        with self._lock:
            if self._runtime is not None:
                if self._signature != signature:
                    raise RuntimeError("storage configuration changed; restart is required")
                return self._runtime
            builder = self._builder if self._builder is not None else build_runtime
            self._runtime = builder(mode, *values, hard_limits=hard_limits == "1", upload_root=upload_root)
            self._signature = signature
            return self._runtime


_default_provider = ArtifactRuntimeProvider(lambda: os.environ)


def get_runtime() -> ArtifactRuntime | None:
    """Retain the existing process-default provider for legacy compositions."""
    return _default_provider.get()


def build_runtime(mode, data_root, work_root, cache_root, bucket, database_url, credentials_directory,
                  *, hard_limits=False, upload_root=""):
    from .cos import CosObjects
    from .disk import DiskBudget, ReadCache, directory
    from .postgres import PostgresLocations
    from .store import ArtifactStore
    from ..runtime_selector import default_postgres_connector
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*-[0-9]+", bucket):
        raise ValueError("invalid COS bucket")
    root, work, cache = Path(data_root).resolve(), Path(work_root).resolve(), Path(cache_root).resolve()
    if (not root.is_dir() or work == cache or work in cache.parents or cache in work.parents
            or root in work.parents or root in cache.parents):
        raise ValueError("artifact cache and work roots must be outside business data")
    directory(work)
    directory(cache)
    required_device_paths = (root, work, cache) if mode == "cos" else (work, cache)
    if not hard_limits and len({p.stat().st_dev for p in required_device_paths}) != 1:
        raise ValueError("data, cache and work roots must use the same system filesystem")
    credential = Path(credentials_directory) / "cos-credentials.json"
    fd = os.open(credential, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            raise ValueError("COS credentials must be a private regular file")
        secrets = json.load(handle)
    if not all(isinstance(secrets.get(k), str) and secrets[k] for k in ("COS_SECRET_ID", "COS_SECRET_KEY")):
        raise ValueError("COS credentials are incomplete")
    clients = threading.local()

    def client():
        if not hasattr(clients, "value"):
            from qcloud_cos import CosConfig, CosS3Client
            logging.getLogger("qcloud_cos").setLevel(logging.CRITICAL + 1)
            clients.value = CosS3Client(CosConfig(
                Region="ap-hongkong", Scheme="https", SecretId=secrets["COS_SECRET_ID"],
                SecretKey=secrets["COS_SECRET_KEY"], Token=secrets.get("COS_SESSION_TOKEN"),
                Timeout=30, KeepAlive=True, VerifySSL=True,
            ))
        return clients.value

    def connect():
        try:
            return default_postgres_connector(database_url)
        except Exception:
            raise ArtifactUnavailable("artifact database unavailable") from None

    objects = CosObjects(client, bucket)
    if hard_limits:
        from .volumes import validate_volumes
        from .disk import GiB
        limits = {"cache": 6 * GiB, "work": 12 * GiB, "upload": 2 * GiB}
        roots = {"cache": cache, "work": work, "upload": Path(upload_root).resolve()}
        parent = validate_volumes(work.parent, roots, limits)
        if mode == "cos" and root.stat().st_dev != parent.stat().st_dev:
            raise ValueError("business configuration must reside on the system disk")
        budget = DiskBudget(parent / "control", limits=limits, preallocated=True,
                            free_bytes=lambda: shutil.disk_usage(parent).free,
                            scratch_roots={kind: path / "scratch" for kind, path in roots.items()})
    else:
        budget = DiskBudget(work / "control")
    with budget.locked():
        budget._live()
    store = ArtifactStore(PostgresLocations(connect), objects, ReadCache(cache, budget, objects), budget, work / "staging")
    return ArtifactRuntime(store, root, mode)
