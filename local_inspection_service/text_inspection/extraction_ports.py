"""Account, durable record, verified-media and provider capabilities for extraction."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.request import Request
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository

Record = dict[str, Any]


class Permission(Protocol):
    def __call__(self, permission: str, *, detail: str) -> Any: ...


class SaveRecord(Protocol):
    def __call__(self, kind: str, value: Record, *, insert_only: bool = False) -> bool: ...


class ReadVerified(Protocol):
    def __call__(self, path_value: str, owner: str, standard: str, *,
                 expected_sha256: str = '', max_bytes: int = 120*1024*1024) -> bytes: ...


class ImageProvider(Protocol):
    def generate_image(self, prompt: str, images: list[Record], *, model: str) -> Record: ...


class Transport(Protocol):
    def __call__(self, request: Request, settings: Record, *, timeout: int) -> Any: ...


@dataclass(frozen=True)
class ExtractionAccess:
    require_permission: Permission
    owner: Callable[[], tuple[str, str]]


@dataclass(frozen=True)
class ExtractionRecords:
    repository: Callable[[], PostgresRuntimeRepository | None]
    owned: Callable[[str, str, str], Record | None]
    load: Callable[[str], list[Record]]
    save: SaveRecord


@dataclass(frozen=True)
class ExtractionMedia:
    path: Callable[[str, str, str], Path]
    write: Callable[[Path, bytes], None]
    read_verified: ReadVerified
    digest: Callable[[bytes], str]
    data_url: Callable[[bytes, str], str]


@dataclass(frozen=True)
class ExtractionModels:
    image_settings: Callable[[], Record]
    detection_settings: Callable[[str], Record]
    image_provider: Callable[[Record], ImageProvider]
    transport: Transport
    diagnostic_value: Callable[[Any], Any]
    external_enabled: Callable[[], bool]
