"""Application-owned configuration persistence and protected PLC mutations."""
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any

from .app_store import AppConfigStore
from .app_store_ports import AppConfigFiles, AppConfigPolicy, AppConfigRows, ConfigFiles

Record = dict[str, Any]


@dataclass(frozen=True)
class ConfigurationFiles:
    files: Callable[[], ConfigFiles]
    primary: Callable[[], Path]
    backup: Callable[[], Path]
    directory: Callable[[], Path]
    ensure: Callable[[], Callable[[], None]]


@dataclass(frozen=True)
class ConfigurationPolicy:
    defaults: Callable[[], Record]
    protected_keys: Callable[[], tuple[str, ...] | set[str] | frozenset[str]]
    sanitize: Callable[[], Callable[[Any], Any]]


class ApplicationConfiguration:
    """Allocate local coordination; construction reads no files or repository.

    Protected writes are available through mutate_app_config_atomically, never
    through a caller-supplied authorization flag. The store's recovery reads
    select the same owned store, including after replacing its capability.
    """
    def __init__(self, *, files: ConfigurationFiles, rows: AppConfigRows,
                 policy: ConfigurationPolicy):
        self._lock = threading.RLock()
        self._namespace_authorized = ContextVar("plc_namespace_write_authorized", default=False)
        self.store = AppConfigStore(
            files=AppConfigFiles(
                _business_files=files.files, CONFIG_PATH=files.primary,
                CONFIG_BACKUP_PATH=files.backup, DATA_DIR=files.directory,
                _config_io_lock=lambda: self.lock, ensure_dirs=files.ensure,
                _read_config_file=lambda: self.store._read_config_file,
            ),
            rows=rows,
            policy=AppConfigPolicy(
                DEFAULT_CONFIG=policy.defaults,
                PLC_PROTECTED_CONFIG_KEYS=policy.protected_keys,
                _plc_namespace_write_authorized=lambda: self._namespace_authorized,
                public_path_sanitized=policy.sanitize,
            ),
        )

    @property
    def lock(self):
        return self._lock

    def _read_config_file(self) -> Record | None:
        return self.store._read_config_file()

    def load_config(self) -> Record:
        return self.store.load_config()

    def save_config(self, config: Record) -> None:
        return self.store.save_config(config)

    def save_app_config(self, config: Record) -> None:
        return self.store.save_app_config(config)

    def mutate_app_config_atomically(self, mutator: Callable[[Record], None]) -> Record:
        return self.store.mutate_app_config_atomically(mutator)
