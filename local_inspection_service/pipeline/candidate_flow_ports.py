"""Narrow candidate state, progress and response capabilities."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
Record = dict[str, Any]
State = dict[str, list[str]]

class BusinessFiles(Protocol):
    def exists(self, path: Path) -> bool: ...
    def read_text(self, path: Path, *, encoding: str) -> str: ...

class AuditFields(Protocol):
    def __call__(self, record: Record, path: Path | None = None) -> Record: ...

class HttpError(Exception):
    status_code: int

@dataclass(frozen=True)
class CandidateStorage:
    ACCESSORY_CANDIDATES_DIR: Callable[[], Path]
    _candidate_store_lock: Callable[[], AbstractContextManager[Any]]
    runtime_postgres_repository_or_none: Callable[[], Callable[[], Any]]
    load_accessory_candidate: Callable[[], Callable[[str], Record]]
    HTTPException: Callable[[], type[HttpError]]
    _business_files: Callable[[], BusinessFiles]
    save_accessory_candidate: Callable[[], Callable[[Path, Record], Any]]
    load_config: Callable[[], Callable[[], Record]]
    load_pipeline_state: Callable[[], Callable[[], State]]
    update_pipeline_state: Callable[[], Callable[[Callable[[State], None]], State]]

@dataclass(frozen=True)
class CandidateProgress:
    candidate_image_jobs: Callable[[], Callable[[Record], list[Record]]]
    IMAGE_JOB_ACTIVE_STATUSES: Callable[[], set[str]]
    candidate_confirmed_accessory_id: Callable[[], Callable[[Record], str]]
    ensure_candidate_image_job_task_ids: Callable[[], Callable[[Record], bool]]
    refresh_codex_image_job: Callable[[], Callable[[Record], Record]]
    store_candidate_image_job: Callable[[], Callable[[Record, Record], Any]]
    refresh_pipeline_candidate: Callable[[], Callable[[str], tuple[Record | None, bool]]]

@dataclass(frozen=True)
class CandidateProjection:
    resolve_accessory_id: Callable[[], Callable[[Record, str], tuple[str, Record] | None]]
    enrich_record_audit_fields: Callable[[], AuditFields]
    pipeline_candidate_job_status: Callable[[], Callable[[Record], tuple[str, int, str]]]
    accessory_material_type: Callable[[], Callable[[Record], str]]
    LEGACY_OWNER_ID: Callable[[], str]
    record_owner_username: Callable[[], Callable[[Record], str]]
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    record_visible_to_user: Callable[[], Callable[[Record, Record, str | None], bool]]
    pipeline_candidate_public: Callable[[], Callable[[Record], Record]]
    canonical_pipeline_accessory_ids: Callable[[], Callable[[Record, list[str]], list[str]]]
    serialize_accessory: Callable[[], Callable[[Record], Record]]
