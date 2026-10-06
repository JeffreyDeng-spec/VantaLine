"""Storage, row-policy and cache capabilities used only by auto-optimization state."""
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..model_profiles.dependencies import ResolverProvider

Record = dict[str, Any]


class AutoOptimizationStateRepository(Protocol):
    def fetch_by_primary_key(self, table: str, key: Record) -> Record | None: ...
    def fetch_all(self, table: str) -> list[Record]: ...
    def upsert_row(self, table: str, row: Record) -> Any: ...


class AutoOptimizationStateFiles(Protocol):
    def exists(self, path: Path) -> bool: ...
    def read_text(self, path: Path, *, encoding: str) -> str: ...
    def write_text(self, path: Path, value: str, *, encoding: str) -> Any: ...
    def glob(self, path: Path, pattern: str) -> Iterable[Path]: ...


class AutoOptimizationStateEncoder(Protocol):
    def __call__(self, state: Record, *, fallback_id: str) -> Record | None: ...


class RequestStateCache(Protocol):
    def get(self) -> Record | None: ...


class InvalidateStateCache(Protocol):
    def __call__(self, *keys: str) -> None: ...


@dataclass(frozen=True)
class AutoOptimizationStateStorage:
    AUTO_OPTIMIZE_DIR: Callable[[], Path]
    AI_DETECTION_MODEL_ID: Callable[[], str]
    _business_files: Callable[[], AutoOptimizationStateFiles]
    runtime_postgres_repository_or_none: Callable[[], Callable[[], AutoOptimizationStateRepository | None]]
    auto_optimize_task_path: Callable[[], Callable[[str], Path]]


@dataclass(frozen=True)
class AutoOptimizationStatePolicy:
    sanitize_ai_detection_task_id: Callable[[], Callable[[Any], str]]
    safe_record_id: Callable[[], Callable[[Any], str]]
    row_raw_json_list: Callable[[], Callable[[list[Record]], list[Any]]]
    auto_optimize_state_row: Callable[[], AutoOptimizationStateEncoder]
    default_auto_optimize_settings: Callable[[], Record]
    resolve_model_profiles: Callable[[], ResolverProvider]


@dataclass(frozen=True)
class AutoOptimizationStateCache:
    _read_path_cache: Callable[[], RequestStateCache]
    store_read_cache_get: Callable[[], Callable[[str], tuple[bool, Any]]]
    store_read_cache_put: Callable[[], Callable[[str, Any], None]]
    store_read_cache_invalidate: Callable[[], InvalidateStateCache]
