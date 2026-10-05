"""Existing app configuration storage and row conversion capabilities."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

Record = dict[str, Any]

class ConfigFiles(Protocol):
    def read_text(self, path: Path, *, encoding: str) -> str: ...
    def write_text(self, path: Path, value: str, *, encoding: str) -> Any: ...
    def unlink(self, path: Path) -> Any: ...

class ConfigRepository(Protocol):
    def fetch_all(self, table: str) -> list[Record]: ...
    def replace_app_config_preserving_keys(self, rows: list[Record], keys: Any, *, additional_tables: dict[str, list[Record]] | None = None) -> Any: ...
    def mutate_app_config_namespace(self, keys: tuple[str, ...], mutator: Callable[[Record], None], *, updated_at: int) -> Record: ...

@dataclass(frozen=True)
class AppConfigFiles:
    _business_files: Callable[[], ConfigFiles]
    CONFIG_PATH: Callable[[], Path]
    CONFIG_BACKUP_PATH: Callable[[], Path]
    DATA_DIR: Callable[[], Path]
    _config_io_lock: Callable[[], AbstractContextManager]
    ensure_dirs: Callable[[], Callable[[], None]]
    _read_config_file: Callable[[], Callable[[], Record | None]]

@dataclass(frozen=True)
class AppConfigRows:
    runtime_postgres_repository_or_none: Callable[[], Callable[[], ConfigRepository | None]]
    config_from_rows: Callable[[], Callable[[list[Record], list[Record]], Record]]
    app_config_rows: Callable[[], Callable[..., list[Record]]]
    accessory_rows: Callable[[], Callable[[Record], list[Record]]]

@dataclass(frozen=True)
class AppConfigPolicy:
    DEFAULT_CONFIG: Callable[[], Record]
    PLC_PROTECTED_CONFIG_KEYS: Callable[[], tuple[str, ...] | set[str] | frozenset[str]]
    _plc_namespace_write_authorized: Callable[[], ContextVar[bool]]
    public_path_sanitized: Callable[[], Callable[[Any], Any]]
