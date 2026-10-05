"""Explicit persistence, permissions and presentation dependencies for image job management."""
from collections.abc import Callable, MutableMapping, Iterable
from contextlib import AbstractContextManager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Protocol

Record = dict[str, Any]

class JobFiles(Protocol):
    def exists(self, path: Path) -> bool: ...
    def stat(self, path: Path) -> Any: ...
    def unlink(self, path: Path) -> Any: ...
    def glob(self, path: Path, pattern: str) -> Iterable[Path]: ...
    def read_text(self, path: Path, *, encoding: str) -> str: ...

@dataclass(frozen=True)
class ImageJobStorage:
    _business_files: Callable[[], JobFiles]
    _candidate_store_lock: Callable[[], AbstractContextManager]
    ACCESSORY_CANDIDATES_DIR: Callable[[], Path]
    list_accessory_candidate_records: Callable[[], Callable[..., list[tuple[Path, Record]]]]
    load_accessory_candidate: Callable[[], Callable[[str], Record]]
    save_accessory_candidate: Callable[[], Callable[[Path, Record], None]]
    delete_accessory_candidate: Callable[[], Callable[[str, Path], bool]]
    cleanup_accessory_candidate_artifacts: Callable[[], Callable[[Record], list[str]]]
    runtime_postgres_repository_or_none: Callable[[], Callable[[], Any]]
    load_config: Callable[[], Callable[[], Record]]
    save_config: Callable[[], Callable[[Record], None]]

@dataclass(frozen=True)
class ImageJobAccess:
    _request_user: Callable[[], ContextVar[Record | None]]
    record_visible_to_user: Callable[[], Callable[[Record, Record, str | None], bool]]
    record_mutable_by_user: Callable[[], Callable[[Record, Record], bool]]
    require_record_access: Callable[[], Callable[..., None]]

@dataclass(frozen=True)
class ImageJobMetadata:
    IMAGE_JOB_ACTIVE_STATUSES: Callable[[], set[str]]
    LOCAL_CODEX_IMAGE_PROVIDER: Callable[[], str]
    WINDOWS_WORKER_IMAGE_PROVIDER: Callable[[], str]
    CODEX_IMAGE_JOB_PERSISTED_KEYS: Callable[[], tuple[str, ...]]
    CODEX_IMAGE_WORKER_QUEUE_STATUS: Callable[[], str]
    image_job_output_path: Callable[[], Callable[..., Path]]
    image_job_log_path: Callable[[], Callable[[Record], Path]]
    public_output_url: Callable[[], Callable[[Path], str]]
    public_output_url_for_existing: Callable[[], Callable[[Path], str]]
    classify_image_worker_failure: Callable[[], Callable[..., str]]
    running_image_job_is_stale: Callable[[], Callable[[Record, Path], bool]]
    public_text: Callable[[], Callable[[Any], str]]
    accessory_uid: Callable[[], Callable[[Record], str]]
    accessory_material_type: Callable[[], Callable[[Record], str]]
    candidate_image_jobs: Callable[[], Callable[[Record], list[Record]]]
    deterministic_task_id: Callable[[], Callable[[Record, Record], str]]
    ensure_candidate_image_job_task_ids: Callable[[], Callable[[Record], bool]]
    ensure_image_job_task_id: Callable[[], Callable[[Record, Record], bool]]
    ensure_pose_collection_image_jobs: Callable[[], Callable[[Record], bool]]
    store_candidate_image_job: Callable[[], Callable[[Record, Record], None]]
    image_job_matches: Callable[[], Callable[[Record, Record, str], bool]]
    record_created_at: Callable[[], Callable[[Record, Path | None], Any]]
    record_updated_at: Callable[[], Callable[[Record, Path | None], Any]]
    record_owner_id: Callable[[], Callable[[Record], str]]
    record_owner_username: Callable[[], Callable[[Record], str]]
    enrich_record_audit_fields: Callable[[], Callable[[Record, Path], Record]]

@dataclass(frozen=True)
class ImageJobActions:
    _image_worker_processes: Callable[[], MutableMapping[str, subprocess.Popen]]
    start_image_worker: Callable[[], Callable[[], bool]]
    refresh_codex_image_job: Callable[[], Callable[[Record], Record]]
    public_image_job: Callable[[], Callable[[Record], Record]]
    refreshed_public_codex_jobs_for_record: Callable[[], Callable[..., tuple[list[Record], bool]]]
    apply_codex_image_job_action: Callable[[], Callable[[Record, Record, str, str], Record]]
    stop_candidate_image_task: Callable[[], Callable[[Record], int]]
