"""Explicit media, runtime and policy capabilities for image worker diagnostics."""
from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Protocol
Record = dict[str, Any]

class FileStat(Protocol):
    st_mtime: float

class DiagnosticFiles(Protocol):
    def exists(self, path: Path) -> bool: ...
    def read_text(self, path: Path, *, encoding: str, errors: str) -> str: ...
    def read_bytes(self, path: Path) -> bytes: ...
    def open_read(self, path: Path) -> AbstractContextManager[BinaryIO]: ...
    def iterdir(self, path: Path) -> Iterable[Path]: ...
    def stat(self, path: Path) -> FileStat: ...

class ResolvePath(Protocol):
    def __call__(self, path: Any, *, for_write: bool = False) -> Path: ...

class ChildProcess(Protocol):
    def poll(self) -> int | None: ...

@dataclass(frozen=True)
class ImageDiagnosticMedia:
    _business_files: Callable[[], DiagnosticFiles]
    resolve_service_path: Callable[[], ResolvePath]
    safe_name: Callable[[], Callable[[str], str]]
    IMAGE_WORKER_LOG_DIR: Callable[[], Path]
    read_image_worker_log_tail: Callable[[], Callable[[Path], str]]

@dataclass(frozen=True)
class ImageDiagnosticRuntime:
    _image_worker_processes: Callable[[], Mapping[str, ChildProcess]]
    image_worker_process_alive: Callable[[], Callable[[str], bool]]
    codex_process_has_log_open: Callable[[], Callable[[Path], bool]]
    image_job_has_live_worker: Callable[[], Callable[[Record, Path], bool]]

@dataclass(frozen=True)
class ImageDiagnosticPolicy:
    IMAGE_JOB_ACTIVE_STATUSES: Callable[[], set[str]]
    IMAGE_WORKER_LOG_TAIL_BYTES: Callable[[], int]
    IMAGE_WORKER_STALE_SECONDS: Callable[[], int]
    LOCAL_CODEX_IMAGE_PROVIDER: Callable[[], str]
