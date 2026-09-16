"""Capabilities for the existing locked candidate confirmation workflow."""
from collections.abc import Callable, Mapping, Set
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .catalog import RecordGuard
from .creation_ports import EnsureProfile

Record = dict[str, Any]


@dataclass(frozen=True)
class ConfirmationAccess:
    current_user: Callable[[], Record]
    require_access: RecordGuard
    owner_id: Callable[[Record], str]


@dataclass(frozen=True)
class ConfirmationStore:
    directory: Callable[[], Path]
    lock: Callable[[], AbstractContextManager]
    load_candidate: Callable[[str], Record]
    save_candidate: Callable[[Path, Record], None]
    load_config: Callable[[], Record]
    save_item: Callable[[Record, Record], Record | None]
    scope: Callable[[Record, Record], Record]
    unique_name: Callable[[Record, Any, str], None]
    class_names: Callable[[], Mapping[int, str]]


@dataclass(frozen=True)
class ConfirmationJobs:
    ensure_ids: Callable[[Record], bool]
    ensure_pose: Callable[[Record], bool]
    list_jobs: Callable[[Record], list[Record]]
    refresh: Callable[[Record], Record]
    store: Callable[[Record, Record], None]
    active_statuses: Callable[[], Set[str]]
    start_worker: Callable[[], bool]


@dataclass(frozen=True)
class ConfirmationProfiles:
    ensure_reference: Callable[[Record], bool]
    ensure_profile: EnsureProfile
    rejected: Callable[[Record], bool]
    ready: Callable[[Record], bool]
    normalize: Callable[[Record, Record], Record]


@dataclass(frozen=True)
class ConfirmationMedia:
    defer: Callable[[Record], None]
    normalize: Callable[[Record], Record]
    canonical_assets: Callable[[Record], list[Record]]
    complete: Callable[[Record, list[Record]], bool]
    error_detail: Callable[[Record, list[Record], bool, bool], Record]


@dataclass(frozen=True)
class ConfirmationPipeline:
    confirmed_id: Callable[[Record], str]
    add_accessory: Callable[[str], Any]
    remove_pending: Callable[[str], Any]
    payload: Callable[[Record, Record], Record]
