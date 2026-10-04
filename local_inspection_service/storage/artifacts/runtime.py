"""Validated opt-in composition; local mode imports neither SDK nor Unix locks."""
from __future__ import annotations
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import re
import stat
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


_lock = threading.Lock()
_runtime = None
_signature = None


def get_runtime() -> ArtifactRuntime | None:
    mode = os.environ.get("VANTALINE_FILE_STORE", "local")
    if mode == "local":
        return None
    if mode not in {"hybrid", "cos"}:
        raise ValueError("VANTALINE_FILE_STORE must be local, hybrid or cos")
    required = ("VANTALINE_DATA_ROOT", "VANTALINE_ARTIFACT_WORK_ROOT", "VANTALINE_ARTIFACT_CACHE_ROOT",
                "VANTALINE_COS_BUCKET", "DATABASE_URL", "CREDENTIALS_DIRECTORY")
    values = tuple(os.environ.get(key, "") for key in required)
    if not all(values):
        raise ValueError("COS storage requires data, work, cache, database and systemd credential configuration")
    signature = (mode, *values)
    global _runtime, _signature
    with _lock:
        if _runtime is not None:
            if _signature != signature:
                raise RuntimeError("storage configuration changed; restart is required")
            return _runtime
        _runtime = build_runtime(mode, *values)
        _signature = signature
        return _runtime


def build_runtime(mode, data_root, work_root, cache_root, bucket, database_url, credentials_directory):
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
    if len({p.stat().st_dev for p in required_device_paths}) != 1:
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
    budget = DiskBudget(work / "control")
    store = ArtifactStore(PostgresLocations(connect), objects, ReadCache(cache, budget, objects), budget, work / "staging")
    return ArtifactRuntime(store, root, mode)
