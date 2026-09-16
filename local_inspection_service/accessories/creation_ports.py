"""Capabilities for accessory creation and candidate preview."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from .file_ports import ValidateTextUploads

Record = dict[str, Any]


class EnsureProfile(Protocol):
    def __call__(self, item: Record, *, force: bool = False, allow_provider: bool = True) -> bool: ...


class PhysicalSize(Protocol):
    def __call__(self, material_type: str, paper_preset: str, paper_width_mm: str,
                 paper_height_mm: str, object_length_mm: str, object_width_mm: str,
                 object_height_mm: str) -> Record: ...


@dataclass(frozen=True)
class CreationAccess:
    current_user: Callable[[], Record]
    owner_fields: Callable[[], Record]
    new_owner_id: Callable[[Record], str]
    request_user: Callable[[], Record | None]


@dataclass(frozen=True)
class CreationStore:
    load: Callable[[], Record]
    save: Callable[[Record, Record], Record | None]
    scope: Callable[[Record, Record], Record]
    unique_name: Callable[[Record, Any, str], None]
    class_names: Callable[[], Mapping[int, str]]


@dataclass(frozen=True)
class CreationMedia:
    upload_directory: Callable[[], Path]
    safe_name: Callable[[str], str]
    validate_text: ValidateTextUploads
    size_reference: Callable[[str], str]
    physical_size: PhysicalSize
    expand_sources: Callable[[str, list[str]], tuple[list[str], list[Record]]]
    normalize: Callable[[Record], Record]
    defer: Callable[[Record], None]


@dataclass(frozen=True)
class CreationProfiles:
    ensure_reference: Callable[[Record], bool]
    ensure_profile: EnsureProfile
    ensure_pose_jobs: Callable[[Record], bool]
    has_active_jobs: Callable[[Record], bool]
    start_worker: Callable[[], bool]


@dataclass(frozen=True)
class CandidateCreation:
    create: Callable[[str, str, str, list[str], Record, str | None, str], Record]
    save: Callable[[Path, Record], None]
    directory: Callable[[], Path]


@dataclass(frozen=True)
class CreationPipeline:
    add_accessory: Callable[[str], Any]
    add_pending: Callable[[str], Any]
    payload: Callable[[Record, Record | None], Record]
