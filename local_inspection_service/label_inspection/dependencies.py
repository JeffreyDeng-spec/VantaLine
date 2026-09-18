"""Explicit label API and worker capabilities; no identity or live connection state."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository

Record = dict[str, Any]


class LabelModels(Protocol):
    def snapshot(self) -> Record: ...
    def snapshot_for_record(self, record: Record) -> Record: ...
    def resolve(self, purpose: str, reference: Record | None = ...) -> Record: ...
    def record_call(self, settings: Record, elapsed_ms: int, ok: bool, usage: Record) -> None: ...


ModelProvider = Callable[[], LabelModels | None]


def require_models(provider: ModelProvider) -> LabelModels:
    service = provider()
    if service is None:
        raise RuntimeError("Label model profile resolver is not configured")
    return service


@dataclass(frozen=True)
class LabelAccess:
    require_permission: Callable[[str], Any]
    require_admin: Callable[[], Any]
    owner: Callable[[], tuple[str, str]]


@dataclass(frozen=True)
class RepositoryLifecycle:
    repository: Callable[[], PostgresRuntimeRepository | None]
    clear: Callable[[], None]


class ExtractDocx(Protocol):
    def __call__(self, contents: bytes, *, raw_only: bool = False) -> tuple[list[Record], list[bytes]]: ...


class ReadVerified(Protocol):
    def __call__(self, path_value: str, owner_user_id: str, standard_id: str, *,
                 expected_sha256: str = "", max_bytes: int = 120 * 1024 * 1024) -> bytes: ...


@dataclass(frozen=True)
class LabelImports:
    data_directory: Callable[[], Path]
    extract_docx: ExtractDocx
    extract_doc: Callable[[bytes], tuple[list[Record], list[bytes]]]
    asset_bytes: Callable[[Record, str], bytes]
    read_verified: ReadVerified
