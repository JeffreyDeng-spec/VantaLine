"""Capabilities used by accessory file edits, with no request or connection state."""
from collections.abc import Callable, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from fastapi import UploadFile
from .catalog import RecordGuard

Record = dict[str, Any]


class RefreshAssets(Protocol):
    def __call__(self, item: Record, *, force_profile: bool = True) -> None: ...


class GenerateProfile(Protocol):
    def __call__(self, item: Record, *, allow_provider: bool = True) -> Record: ...


class ValidateTextUploads(Protocol):
    def __call__(self, files: list[UploadFile], *, existing_count: int = 0) -> None: ...


@dataclass(frozen=True)
class FileAccess:
    current_user: Callable[[], Record]
    require_access: RecordGuard


@dataclass(frozen=True)
class FileStore:
    load_config: Callable[[], Record]
    save_item: Callable[[Record, Record], Record | None]
    scope_config: Callable[[Record, Record], Record]


@dataclass(frozen=True)
class FileMedia:
    upload_directory: Callable[[], Path]
    data_directory: Callable[[], Path]
    image_suffixes: Callable[[], Set[str]]
    safe_name: Callable[[str], str]
    validate_text_uploads: ValidateTextUploads
    text_source_count: Callable[[Record], int]
    existing_source_paths: Callable[[Record], list[Path]]
    is_rectified: Callable[[Path], bool]
    crop_stem: Callable[[Path], str]
    detail: Callable[[Record], Record]
    clean_sprites: Callable[[Record], list[Record]]
    image_jobs: Callable[[Record], list[Record]]


@dataclass(frozen=True)
class FileProfiles:
    refresh: RefreshAssets
    fallback: Callable[[Record], Record]
    generate: GenerateProfile
    save_cache: Callable[[Record], None]
    bounded_text: Callable[[Any, int], str]
