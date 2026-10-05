"""Typed identity, media and workflow ports for legacy pose-collection job records."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
Record = dict[str, Any]

class FileStat(Protocol):
    st_mtime: float

class PoseJobFiles(Protocol):
    def exists(self, path: Path) -> bool: ...
    def stat(self, path: Path) -> FileStat: ...

class ImageOutputPath(Protocol):
    def __call__(self, job: Record, *, for_write: bool = False) -> Path: ...

@dataclass(frozen=True)
class PoseJobIdentity:
    record_owner_id: Callable[[], Callable[[Record], str]]
    safe_record_id: Callable[[], Callable[[Any], str]]
    accessory_uid: Callable[[], Callable[[Record], str]]
    deterministic_task_id: Callable[[], Callable[[Record, Record], str]]
    record_audit_fields: Callable[[], Callable[[Record], Record]]
    accessory_material_type: Callable[[], Callable[[Record], str]]

@dataclass(frozen=True)
class PoseJobMedia:
    output_write_dir_for_owner: Callable[[], Callable[[str, str], Path]]
    POSE_ANCHOR_IMAGES: Callable[[], Mapping[str, Path]]
    _business_files: Callable[[], PoseJobFiles]
    existing_source_image_paths: Callable[[], Callable[[Record], list[Path]]]
    MAX_IMAGE_WORKER_INPUTS: Callable[[], int]
    pose_collection_output_dir: Callable[[], Callable[[Record], Path]]
    pose_collection_output_name: Callable[[], Callable[[str], str]]
    public_output_url: Callable[[], Callable[[Path], str]]
    source_reference_inputs_for_pose_job: Callable[[], Callable[[Record, str], list[str]]]
    image_job_output_path: Callable[[], ImageOutputPath]

@dataclass(frozen=True)
class PoseJobWorkflow:
    pose_collection_job_id: Callable[[], Callable[[Record, str], str]]
    CODEX_IMAGE_WORKER_QUEUE_STATUS: Callable[[], str]
    LOCAL_CODEX_IMAGE_PROVIDER: Callable[[], str]
    build_anchor_replacement_pose_prompt: Callable[[], Callable[[Record, str], str]]
    ensure_image_job_task_id: Callable[[], Callable[[Record, Record], bool]]
    ensure_anchor_image_provenance: Callable[[], Callable[[Record], bool]]
    ensure_image_job_target_guides: Callable[[], Callable[[Record], bool]]
    POSE_COLLECTION_GRID_ENABLED: Callable[[], bool]
    candidate_image_jobs: Callable[[], Callable[[Record], list[Record]]]
    make_pose_collection_job: Callable[[], Callable[[Record, str], Record]]
