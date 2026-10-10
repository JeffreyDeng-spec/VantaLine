"""Pipeline candidate refresh, task metadata and public resource projections."""
from __future__ import annotations
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .persistence_composition import PipelinePersistence
from .candidate_flow_ports import AuditFields, HttpError, BusinessFiles
from ..training.auto_optimization_status_ports import StopCapture
Record = dict[str, Any]
State = dict[str, list[str]]
from .task_metadata import PipelineTaskMetadata
from .task_metadata_ports import MetadataPolicy, MetadataSnapshots

@dataclass(frozen=True)
class QueryMetadataPolicyInputs:
    PIPELINE_DETECTION_METHODS: Callable[[], set[str]]
    PIPELINE_TRAINING_METHODS: Callable[[], set[str]]

@dataclass(frozen=True)
class QueryMetadataSnapshotsInputs:
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    LEGACY_OWNER_ID: Callable[[], str]
    record_owner_username: Callable[[], Callable[[Record], str]]
    accessory_id_aliases: Callable[[], Callable[[Record], list[str]]]
from .candidate_flow import PipelineCandidateFlow
from .candidate_flow_ports import BusinessFiles, AuditFields, HttpError, CandidateStorage, CandidateProgress, CandidateProjection

@dataclass(frozen=True)
class QueryCandidateStorageInputs:
    ACCESSORY_CANDIDATES_DIR: Callable[[], Path]
    _candidate_store_lock: Callable[[], AbstractContextManager[Any]]
    runtime_postgres_repository_or_none: Callable[[], Callable[[], Any]]
    load_accessory_candidate: Callable[[], Callable[[str], Record]]
    HTTPException: Callable[[], type[HttpError]]
    _business_files: Callable[[], BusinessFiles]
    save_accessory_candidate: Callable[[], Callable[[Path, Record], Any]]
    load_config: Callable[[], Callable[[], Record]]

@dataclass(frozen=True)
class QueryCandidateProgressInputs:
    candidate_image_jobs: Callable[[], Callable[[Record], list[Record]]]
    IMAGE_JOB_ACTIVE_STATUSES: Callable[[], set[str]]
    ensure_candidate_image_job_task_ids: Callable[[], Callable[[Record], bool]]
    refresh_codex_image_job: Callable[[], Callable[[Record], Record]]
    store_candidate_image_job: Callable[[], Callable[[Record, Record], Any]]

@dataclass(frozen=True)
class QueryCandidateProjectionInputs:
    resolve_accessory_id: Callable[[], Callable[[Record, str], tuple[str, Record] | None]]
    enrich_record_audit_fields: Callable[[], AuditFields]
    accessory_material_type: Callable[[], Callable[[Record], str]]
    LEGACY_OWNER_ID: Callable[[], str]
    record_owner_username: Callable[[], Callable[[Record], str]]
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    record_visible_to_user: Callable[[], Callable[[Record, Record, str | None], bool]]
    serialize_accessory: Callable[[], Callable[[Record], Record]]
from .task_snapshots import PipelineTaskSnapshots
from .task_snapshot_ports import PipelineTaskSnapshotLinks

@dataclass(frozen=True)
class QueryPipelineTaskSnapshotLinksInputs:
    load_ai_tasks: Callable[[], Callable[[], list[dict[str, Any]]]]
    accessory_lookup: Callable[[], Callable[[dict[str, Any]], dict[str, dict[str, Any]]]]
from .resource_status import PipelineResourceStatus
from .resource_status_ports import PipelineResourceStatusLinks, PipelineResourceFiles

@dataclass(frozen=True)
class QueryPipelineResourceStatusLinksInputs:
    find_dataset: Callable[[], Callable[[str], tuple[Any, Any]]]
    load_ai_tasks: Callable[[], Callable[[], list[dict[str, Any]]]]
    list_trained_specs: Callable[[], Callable[[], list[dict[str, Any]]]]
from .auto_optimization_links import PipelineAutoOptimizationLinks
from .auto_optimization_links_ports import PublicLink, LinkState, LinkProjection, LinkMatching

@dataclass(frozen=True)
class QueryLinkStateInputs:
    sanitize_ai_detection_task_id: Callable[[], Callable[[Any], str]]
    _auto_optimize_lock: Callable[[], AbstractContextManager[Any]]
    load_auto_optimize_state: Callable[[], Callable[[str], Record]]
    auto_optimize_completed_model_id: Callable[[], Callable[[Record], str]]
    auto_optimize_stop_capture_for_model_locked: Callable[[], StopCapture]
    save_auto_optimize_state: Callable[[], Callable[[Record], None]]
    list_auto_optimize_states: Callable[[], Callable[[], list[Record]]]

@dataclass(frozen=True)
class QueryLinkProjectionInputs:
    auto_optimize_phase_name: Callable[[], Callable[[Record], str]]
    ai_detection_task_model_id: Callable[[], Callable[[str], str]]
from .task_projection import PipelineTaskProjection
from .task_projection_ports import ModelStatus, TrainingLink, ProjectionMetadata, ProjectionResources

@dataclass(frozen=True)
class QueryProjectionMetadataInputs:
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    enrich_record_audit_fields: Callable[[], Callable[[Record], Record]]
    resolve_accessory_id: Callable[[], Callable[[Record, str], tuple[str, Record] | None]]
    accessory_material_type: Callable[[], Callable[[Record], str]]

@dataclass(frozen=True)
class QueryProjectionResourcesInputs:
    public_path_sanitized: Callable[[], Callable[[Any], Any]]

class PipelineQueries:
    """Inert graph; request-time policy and persistence suppliers remain explicit."""
    def __init__(self, *, persistence: PipelinePersistence, files: PipelineResourceFiles,
                 metadata_policy: QueryMetadataPolicyInputs,
                 metadata_snapshots: QueryMetadataSnapshotsInputs,
                 candidates_storage: QueryCandidateStorageInputs,
                 candidates_progress: QueryCandidateProgressInputs,
                 candidates_projection: QueryCandidateProjectionInputs,
                 snapshots_0: QueryPipelineTaskSnapshotLinksInputs,
                 resources_0: QueryPipelineResourceStatusLinksInputs,
                 optimization_state: QueryLinkStateInputs,
                 optimization_projection: QueryLinkProjectionInputs,
                 projection_metadata: QueryProjectionMetadataInputs,
                 projection_resources: QueryProjectionResourcesInputs):
        self.persistence = persistence
        self.metadata = PipelineTaskMetadata(
            policy=MetadataPolicy(
                PIPELINE_DETECTION_METHODS=metadata_policy.PIPELINE_DETECTION_METHODS,
                PIPELINE_TRAINING_METHODS=metadata_policy.PIPELINE_TRAINING_METHODS,
                normalize_pipeline_detection_method=lambda: self.normalize_pipeline_detection_method,
            ),
            snapshots=MetadataSnapshots(
                accessory_lookup_by_id=metadata_snapshots.accessory_lookup_by_id,
                pipeline_task_label_snapshot=lambda: self.pipeline_task_label_snapshot,
                LEGACY_OWNER_ID=metadata_snapshots.LEGACY_OWNER_ID,
                record_owner_username=metadata_snapshots.record_owner_username,
                accessory_id_aliases=metadata_snapshots.accessory_id_aliases,
            ),
        )
        self.candidates = PipelineCandidateFlow(
            storage=CandidateStorage(
                ACCESSORY_CANDIDATES_DIR=candidates_storage.ACCESSORY_CANDIDATES_DIR,
                _candidate_store_lock=candidates_storage._candidate_store_lock,
                runtime_postgres_repository_or_none=candidates_storage.runtime_postgres_repository_or_none,
                load_accessory_candidate=candidates_storage.load_accessory_candidate,
                HTTPException=candidates_storage.HTTPException,
                _business_files=candidates_storage._business_files,
                save_accessory_candidate=candidates_storage.save_accessory_candidate,
                load_config=candidates_storage.load_config,
                load_pipeline_state=lambda: self.load_pipeline_state,
                update_pipeline_state=lambda: self.update_pipeline_state,
            ),
            progress=CandidateProgress(
                candidate_image_jobs=candidates_progress.candidate_image_jobs,
                IMAGE_JOB_ACTIVE_STATUSES=candidates_progress.IMAGE_JOB_ACTIVE_STATUSES,
                candidate_confirmed_accessory_id=lambda: self.candidate_confirmed_accessory_id,
                ensure_candidate_image_job_task_ids=candidates_progress.ensure_candidate_image_job_task_ids,
                refresh_codex_image_job=candidates_progress.refresh_codex_image_job,
                store_candidate_image_job=candidates_progress.store_candidate_image_job,
                refresh_pipeline_candidate=lambda: self.refresh_pipeline_candidate,
            ),
            projection=CandidateProjection(
                resolve_accessory_id=candidates_projection.resolve_accessory_id,
                enrich_record_audit_fields=candidates_projection.enrich_record_audit_fields,
                pipeline_candidate_job_status=lambda: self.pipeline_candidate_job_status,
                accessory_material_type=candidates_projection.accessory_material_type,
                LEGACY_OWNER_ID=candidates_projection.LEGACY_OWNER_ID,
                record_owner_username=candidates_projection.record_owner_username,
                accessory_lookup_by_id=candidates_projection.accessory_lookup_by_id,
                record_visible_to_user=candidates_projection.record_visible_to_user,
                pipeline_candidate_public=lambda: self.pipeline_candidate_public,
                canonical_pipeline_accessory_ids=lambda: self.canonical_pipeline_accessory_ids,
                serialize_accessory=candidates_projection.serialize_accessory,
            ),
        )
        self.snapshots = PipelineTaskSnapshots(
            PipelineTaskSnapshotLinks(
                load_ai_tasks=snapshots_0.load_ai_tasks,
                accessory_lookup=snapshots_0.accessory_lookup,
                label_snapshot=lambda: self.pipeline_task_label_snapshot,
            ),
        )
        self.resources = PipelineResourceStatus(
            PipelineResourceStatusLinks(
                find_dataset=resources_0.find_dataset,
                load_ai_tasks=resources_0.load_ai_tasks,
                list_trained_specs=resources_0.list_trained_specs,
            ),
            files=files,
        )
        self.optimization = PipelineAutoOptimizationLinks(
            state=LinkState(
                sanitize_ai_detection_task_id=optimization_state.sanitize_ai_detection_task_id,
                _auto_optimize_lock=optimization_state._auto_optimize_lock,
                load_auto_optimize_state=optimization_state.load_auto_optimize_state,
                auto_optimize_completed_model_id=optimization_state.auto_optimize_completed_model_id,
                auto_optimize_stop_capture_for_model_locked=optimization_state.auto_optimize_stop_capture_for_model_locked,
                save_auto_optimize_state=optimization_state.save_auto_optimize_state,
                fast_completed_auto_optimize_model_id=lambda: self.fast_completed_auto_optimize_model_id,
                list_auto_optimize_states=optimization_state.list_auto_optimize_states,
                auto_optimize_states_by_task_id=lambda: self.auto_optimize_states_by_task_id,
            ),
            projection=LinkProjection(
                auto_optimize_phase_name=optimization_projection.auto_optimize_phase_name,
                ai_detection_task_model_id=optimization_projection.ai_detection_task_model_id,
                public_auto_optimize_link_for_task_id=lambda: self.public_auto_optimize_link_for_task_id,
            ),
            matching=LinkMatching(
                canonical_pipeline_accessory_ids=lambda: self.canonical_pipeline_accessory_ids,
                normalize_pipeline_accessory_counts=lambda: self.normalize_pipeline_accessory_counts,
            ),
        )
        self.projection = PipelineTaskProjection(
            metadata=ProjectionMetadata(
                accessory_lookup_by_id=projection_metadata.accessory_lookup_by_id,
                enrich_record_audit_fields=projection_metadata.enrich_record_audit_fields,
                normalize_pipeline_detection_method=lambda: self.normalize_pipeline_detection_method,
                pipeline_method_uses_training=lambda: self.pipeline_method_uses_training,
                resolve_accessory_id=projection_metadata.resolve_accessory_id,
                normalize_pipeline_accessory_counts=lambda: self.normalize_pipeline_accessory_counts,
                pipeline_task_accessory_snapshot=lambda: self.pipeline_task_accessory_snapshot,
                accessory_material_type=projection_metadata.accessory_material_type,
            ),
            resources=ProjectionResources(
                pipeline_task_dataset_status=lambda: self.pipeline_task_dataset_status,
                pipeline_task_model_status=lambda: self.pipeline_task_model_status,
                pipeline_task_auto_optimize_link=lambda: self.pipeline_task_auto_optimize_link,
                public_path_sanitized=projection_resources.public_path_sanitized,
            ),
        )

    def load_pipeline_state(self) -> State:
        return self.persistence.load_pipeline_state()

    def update_pipeline_state(self, mutator: Callable[[State], None]) -> State:
        return self.persistence.update_pipeline_state(mutator)

    def pipeline_task_model_id(self, task: dict[str, Any]) -> str:
        return self.metadata.pipeline_task_model_id(task)

    def normalize_pipeline_detection_method(self, value: str | None) -> str:
        return self.metadata.normalize_pipeline_detection_method(value)

    def pipeline_method_uses_training(self, method: str | None) -> bool:
        return self.metadata.pipeline_method_uses_training(method)

    def ensure_pipeline_task_accessory_objects(self, config: dict[str, Any], tasks: list[dict[str, Any]]) -> bool:
        return self.metadata.ensure_pipeline_task_accessory_objects(config, tasks)

    def normalize_pipeline_accessory_counts(self, config: dict[str, Any], accessory_ids: list[str], raw_counts: Any=None) -> dict[str, int]:
        return self.metadata.normalize_pipeline_accessory_counts(config, accessory_ids, raw_counts)

    def normalize_pipeline_task_auto_advance_defaults(self, tasks: list[dict[str, Any]]) -> bool:
        return self.metadata.normalize_pipeline_task_auto_advance_defaults(tasks)

    def canonical_pipeline_accessory_ids(self, config: dict[str, Any], raw_ids: list[str]) -> list[str]:
        return self.candidates.canonical_pipeline_accessory_ids(config, raw_ids)

    def candidate_confirmed_accessory_id(self, candidate: dict[str, Any]) -> str:
        return self.candidates.candidate_confirmed_accessory_id(candidate)

    def pipeline_candidate_job_status(self, candidate: dict[str, Any]) -> tuple[str, int, str]:
        return self.candidates.pipeline_candidate_job_status(candidate)

    def pipeline_candidate_public(self, candidate: dict[str, Any]) -> dict[str, Any]:
        return self.candidates.pipeline_candidate_public(candidate)

    def refresh_pipeline_candidate(self, candidate_id: str) -> tuple[dict[str, Any] | None, bool]:
        return self.candidates.refresh_pipeline_candidate(candidate_id)

    def pipeline_accessories_payload(self, config: dict[str, Any] | None=None, user: dict[str, Any] | None=None, target_user_id: str | None=None) -> dict[str, Any]:
        return self.candidates.pipeline_accessories_payload(config, user, target_user_id)

    def pipeline_task_label_snapshot(self, task: dict[str, Any]) -> dict[str, str]:
        return self.snapshots.pipeline_task_label_snapshot(task)

    def pipeline_task_accessory_snapshot(self, config: dict[str, Any], task: dict[str, Any], accessory_ids: list[str]) -> tuple[dict[str, str], list[str]]:
        return self.snapshots.pipeline_task_accessory_snapshot(config, task, accessory_ids)

    def pipeline_task_dataset_status(self, task: dict[str, Any]) -> str:
        return self.resources.pipeline_task_dataset_status(task)

    def pipeline_task_model_status(self, task: dict[str, Any], *, ai_task_ids: set[str] | None=None, trained_model_specs: list[dict[str, Any]] | None=None) -> str:
        return self.resources.pipeline_task_model_status(task, ai_task_ids=ai_task_ids, trained_model_specs=trained_model_specs)

    def fast_completed_auto_optimize_model_id(self, state: dict[str, Any]) -> str:
        return self.optimization.fast_completed_auto_optimize_model_id(state)

    def public_auto_optimize_link_for_task_id(self, task_id: str, *, source: str, state: dict[str, Any] | None=None) -> dict[str, Any] | None:
        return self.optimization.public_auto_optimize_link_for_task_id(task_id, source=source, state=state)

    def auto_optimize_states_by_task_id(self, states: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return self.optimization.auto_optimize_states_by_task_id(states)

    def pipeline_task_auto_optimize_link(self, task: dict[str, Any], config: dict[str, Any], *, auto_optimize_states: list[dict[str, Any]] | None=None, auto_optimize_states_by_id: dict[str, dict[str, Any]] | None=None) -> dict[str, Any] | None:
        return self.optimization.pipeline_task_auto_optimize_link(task, config, auto_optimize_states=auto_optimize_states, auto_optimize_states_by_id=auto_optimize_states_by_id)

    def pipeline_task_public(self, task: dict[str, Any], config: dict[str, Any], *, ai_task_ids: set[str] | None=None, trained_model_specs: list[dict[str, Any]] | None=None, auto_optimize_states: list[dict[str, Any]] | None=None, auto_optimize_states_by_id: dict[str, dict[str, Any]] | None=None, sanitize: bool=True) -> dict[str, Any]:
        return self.projection.pipeline_task_public(task, config, ai_task_ids=ai_task_ids, trained_model_specs=trained_model_specs, auto_optimize_states=auto_optimize_states, auto_optimize_states_by_id=auto_optimize_states_by_id, sanitize=sanitize)
