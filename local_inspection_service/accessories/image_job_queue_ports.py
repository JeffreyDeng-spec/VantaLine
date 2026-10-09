"""Candidate storage, image metadata and execution capabilities for the queue."""
from collections.abc import Callable, Iterable, Set
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from fastapi import HTTPException
from ..runtime.image_worker import ImageWork
Record = dict[str, Any]
Queued = tuple[Path, Record, Record]

class FileMetadata(Protocol):
    st_mtime: float

class QueueFiles(Protocol):
    def exists(self, path: Path) -> bool: ...
    def read_text(self, path: Path, *, encoding: str) -> str: ...
    def stat(self, path: Path) -> FileMetadata: ...

@dataclass(frozen=True)
class ImageQueueStorage:
    _candidate_store_lock: Callable[[], AbstractContextManager]
    CONFIG_PATH: Callable[[], Path]
    load_config: Callable[[], Callable[[], Record]]
    save_config: Callable[[], Callable[[Record], None]]
    runtime_postgres_repository_or_none: Callable[[], Callable[[], object | None]]
    load_accessory_candidate: Callable[[], Callable[[str], Record]]
    save_accessory_candidate: Callable[[], Callable[[Path, Record], None]]
    list_accessory_candidate_records: Callable[[], Callable[..., Iterable[tuple[Path, Record]]]]
    _business_files: Callable[[], QueueFiles]
    HTTPException: Callable[[], type[HTTPException]]

@dataclass(frozen=True)
class ImageQueueMetadata:
    ensure_image_job_task_id: Callable[[], Callable[[Record, Record], bool]]
    ensure_candidate_image_job_task_ids: Callable[[], Callable[[Record], bool]]
    candidate_image_jobs: Callable[[], Callable[[Record], list[Record]]]
    store_candidate_image_job: Callable[[], Callable[[Record, Record], None]]
    accessory_uid: Callable[[], Callable[[Record], str]]
    file_stem_identifier: Callable[[], Callable[[Path], str]]
    accessory_material_type: Callable[[], Callable[[Record], str]]
    ensure_pose_collection_image_jobs: Callable[[], Callable[[Record], bool]]
    image_job_output_path: Callable[[], Callable[..., Path]]
    public_output_url: Callable[[], Callable[[Path], str]]
    resolve_service_path: Callable[[], Callable[[str], Path]]
    preprocess_object_clean_sprites: Callable[[], Callable[..., Any]]

class ImageQueueRuntime(Protocol):
    @property
    def closing(self) -> bool: ...
    def active_children(self) -> int: ...
    def launch(self, prepare: Callable[[], ImageWork | None]) -> bool: ...
    def wait(self, timeout: float) -> bool: ...


@dataclass(frozen=True)
class ImageQueueExecution:
    _image_worker_runtime: Callable[[], ImageQueueRuntime]
    IMAGE_JOB_QUEUED_STATUSES: Callable[[], Set[str]]
    MAX_PARALLEL_IMAGE_WORKERS: Callable[[], int]
    next_queued_image_job: Callable[[], Callable[[], Queued | None]]
    update_image_worker_status: Callable[[], Callable[..., Record]]
    run_image_generation_job: Callable[[], Callable[[Path, Record, Record], None]]
