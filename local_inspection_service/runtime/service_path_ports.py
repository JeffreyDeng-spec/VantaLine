"""Focused path settings, file access and per-call identity interfaces."""
from collections.abc import Callable, Set, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
Record = dict[str, Any]
class FileAccess(Protocol):
    def exists(self, path: Path) -> bool: ...
    def read_text(self, path: Path, *, encoding: str) -> str: ...
    def write_text(self, path: Path, text: str, *, encoding: str) -> Any: ...
class RequestUser(Protocol):
    def get(self) -> Record | None: ...
@dataclass(frozen=True)
class ServicePathSettings:
    ROOT: Callable[[], Path]
    APP_DIR: Callable[[], Path]
    OUTPUT_DIR: Callable[[], Path]
@dataclass(frozen=True)
class PathProjectionPolicy:
    STALE_REPO_PATH_PREFIXES: Callable[[], Sequence[str]]
    REMOVED_PHASE1_PUBLIC_CONFIG_KEYS: Callable[[], Set[str]]
    LEGACY_OWNER_ID: Callable[[], str]
    SYSTEM_OWNER_ID: Callable[[], str]
@dataclass(frozen=True)
class PathCalls:
    rebase_stale_local_path_text: Callable[[], Callable[[str], str]]
    rebase_stale_local_payload_text: Callable[[], Callable[[str], str]]
    public_path_sanitized: Callable[[], Callable[[Any], Any]]
    service_rebased_path: Callable[[], Callable[[Path], Path | None]]
    resolve_service_path: Callable[[], Callable[..., Path]]
    path_is_under: Callable[[], Callable[[Path, Path], bool]]
    public_output_url: Callable[[], Callable[[Path], str]]
    output_write_dir_for_owner: Callable[[], Callable[[str, str], Path]]
@dataclass(frozen=True)
class PathFiles:
    _business_files: Callable[[], FileAccess]
@dataclass(frozen=True)
class PathIdentity:
    _request_user: Callable[[], RequestUser]
    user_is_admin: Callable[[], Callable[[Record], bool]]
