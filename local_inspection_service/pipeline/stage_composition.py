"""Pipeline AI activation, stage transitions, recommendations and reconciliation."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any
from fastapi import HTTPException
from .query_composition import PipelineQueries
from .runtime_state import PipelineRuntimeState
from .training_status_ports import JobLoader
Record = dict[str, Any]
Getter = Callable[[], Callable[..., Any]]
from .ai_activation_ports import TaskSaver, ActivationPolicy, ActivationStorage
from .ai_task_sync_ports import PipelineAiIdentity, PipelineAiAccessories, PipelineAiAccess, PipelineAiProjection
from .recommendation_ports import PipelineRecommendationMethodPolicy, PipelineRecommendationLinks
from .reconciliation_ports import ReconciliationPolicy, ReconciliationRegistry, ReconciliationCalls
from .stage_advance_ports import StageAdvancePolicy, StageAdvanceAssets, StageAdvanceJobs, StageAdvanceRuntime
from .training_status_ports import TrainingJobLookup, TrainingStatusEffects
from .ai_activation import PipelineAiActivation
from .ai_task_sync import PipelineAiTaskSync
from .training_status import PipelineTrainingStatus
from .stage_advance import PipelineStageAdvancer
from .reconciliation import PipelineReconciliation
from .recommendations import PipelineRecommendations

@dataclass(frozen=True)
class ActivationPolicyInputs:
    HTTPException: Callable[[], type[HTTPException]]
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    clean_ai_detection_task_name: Callable[[], Callable[[Any, str], str]]
    sanitize_ai_detection_task_id: Callable[[], Callable[[Any], str]]

@dataclass(frozen=True)
class ActivationStorageInputs:
    current_owner_fields: Callable[[], Callable[[], Record]]
    find_ai_detection_task: Callable[[], Callable[[str], Record | None]]
    save_ai_detection_task: Callable[[], TaskSaver]
    serialize_ai_detection_task: Callable[[], Callable[[Record, Record], Record]]

@dataclass(frozen=True)
class PipelineAiIdentityInputs:
    safe_record_id: Callable[[], Callable[[Any], str]]
    sanitize_ai_detection_task_id: Callable[[], Callable[[Any], str]]
    ai_detection_task_model_id: Callable[[], Callable[[str], str]]

@dataclass(frozen=True)
class PipelineAiAccessoriesInputs:
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    accessory_material_type: Callable[[], Callable[[Record], str]]

@dataclass(frozen=True)
class PipelineAiAccessInputs:
    source: Callable[[], str]
    record_visible_to_user: Callable[[], Callable[[Record, Record | None, str | None], bool]]
    load_ai_detection_tasks: Callable[[], Callable[[], list[Record]]]

@dataclass(frozen=True)
class PipelineAiProjectionInputs:
    clean_ai_detection_task_name: Callable[[], Callable[[Any, str], str]]
    now: Callable[[], Callable[[], float]]

@dataclass(frozen=True)
class TrainingJobLookupInputs:
    load: Callable[[], JobLoader]
    path: Callable[[], Callable[[str], Path]]
    public: Callable[[], Callable[[Record], Record]]

@dataclass(frozen=True)
class TrainingStatusEffectsInputs:
    orchestration: Callable[[], Callable[[Record], Record]]
    set_stage: Callable[[], Callable[[Record, str, str, int], Any]]

@dataclass(frozen=True)
class StageAdvancePolicyInputs:
    recommend: Getter
    orchestration: Getter
    pause: Getter
    training_quality: Getter
    link_model: Getter
    http_error: Callable[[], type[Exception]]
    cancelled_error: Callable[[], type[Exception]]

@dataclass(frozen=True)
class StageAdvanceAssetsInputs:
    load_config: Getter
    save_config: Getter
    prepare: Getter
    materialize: Getter
    normalize: Getter

@dataclass(frozen=True)
class StageAdvanceJobsInputs:
    request_type: Getter
    sample_generation: Getter
    training: Getter
    task_name: Getter
    log_samples: Getter
    log_training: Getter

@dataclass(frozen=True)
class StageAdvanceRuntimeInputs:
    persist_progress: Getter
    monotonic: Getter
    clock: Getter
    print: Getter

@dataclass(frozen=True)
class ReconciliationRegistryInputs:
    timeout: Callable[[], int]
    now: Callable[[], Callable[[], float]]

@dataclass(frozen=True)
class ReconciliationCallsInputs:
    load_agent_config: Callable[[], Callable[[], Record]]
    supported: Callable[[], Callable[[Record], bool]]
    training_finder: Callable[[], Callable[[], Any]]
    orchestration: Callable[[], Callable[[Record], Record]]

class PipelineStages:
    """Inert graph; native advance registries remain with the supplied runtime."""
    def __init__(self, *, queries: PipelineQueries, runtime: PipelineRuntimeState,
                 activation_policy: ActivationPolicyInputs,
                 activation_storage: ActivationStorageInputs,
                 pipeline_ai_identity: PipelineAiIdentityInputs,
                 pipeline_ai_accessories: PipelineAiAccessoriesInputs,
                 pipeline_ai_access: PipelineAiAccessInputs,
                 pipeline_ai_projection: PipelineAiProjectionInputs,
                 training_job_lookup: TrainingJobLookupInputs,
                 training_status_effects: TrainingStatusEffectsInputs,
                 stage_advance_policy: StageAdvancePolicyInputs,
                 stage_advance_assets: StageAdvanceAssetsInputs,
                 stage_advance_jobs: StageAdvanceJobsInputs,
                 stage_advance_runtime: StageAdvanceRuntimeInputs,
                 reconciliation_registry: ReconciliationRegistryInputs,
                 reconciliation_calls: ReconciliationCallsInputs):
        if runtime is not queries.persistence.runtime:
            raise ValueError('PipelineStages requires the query persistence runtime')
        self.queries = queries
        self.runtime = runtime
        self.activation = PipelineAiActivation(
            policy=ActivationPolicy(
                canonical_pipeline_accessory_ids=lambda: self.canonical_pipeline_accessory_ids,
                HTTPException=activation_policy.HTTPException,
                accessory_lookup_by_id=activation_policy.accessory_lookup_by_id,
                normalize_pipeline_accessory_counts=lambda: self.normalize_pipeline_accessory_counts,
                clean_ai_detection_task_name=activation_policy.clean_ai_detection_task_name,
                sanitize_ai_detection_task_id=activation_policy.sanitize_ai_detection_task_id,
                normalize_pipeline_detection_method=lambda: self.normalize_pipeline_detection_method,
            ),
            storage=ActivationStorage(
                current_owner_fields=activation_storage.current_owner_fields,
                find_ai_detection_task=activation_storage.find_ai_detection_task,
                save_ai_detection_task=activation_storage.save_ai_detection_task,
                serialize_ai_detection_task=activation_storage.serialize_ai_detection_task,
                upsert_pipeline_ai_detection_task=lambda: self.upsert_pipeline_ai_detection_task,
            ),
        )
        self.ai_sync = PipelineAiTaskSync(
            PipelineAiIdentity(
                safe_record_id=pipeline_ai_identity.safe_record_id,
                sanitize_ai_detection_task_id=pipeline_ai_identity.sanitize_ai_detection_task_id,
                ai_detection_task_model_id=pipeline_ai_identity.ai_detection_task_model_id,
            ),
            PipelineAiAccessories(
                accessory_lookup_by_id=pipeline_ai_accessories.accessory_lookup_by_id,
                canonical_pipeline_accessory_ids=lambda: self.canonical_pipeline_accessory_ids,
                accessory_material_type=pipeline_ai_accessories.accessory_material_type,
                normalize_pipeline_accessory_counts=lambda: self.normalize_pipeline_accessory_counts,
            ),
            PipelineAiAccess(
                source=pipeline_ai_access.source,
                record_visible_to_user=pipeline_ai_access.record_visible_to_user,
                load_ai_detection_tasks=pipeline_ai_access.load_ai_detection_tasks,
            ),
            PipelineAiProjection(
                clean_ai_detection_task_name=pipeline_ai_projection.clean_ai_detection_task_name,
                training_route=lambda: self.pipeline_ai_task_training_route,
                task_id=lambda: self.pipeline_ai_task_id,
                now=pipeline_ai_projection.now,
            ),
        )
        self.training = PipelineTrainingStatus(
            TrainingJobLookup(
                load=training_job_lookup.load,
                path=training_job_lookup.path,
                public=training_job_lookup.public,
                linked=lambda: self.linked_training_job,
            ),
            TrainingStatusEffects(
                orchestration=training_status_effects.orchestration,
                set_stage=training_status_effects.set_stage,
            ),
        )
        self.advance = PipelineStageAdvancer(
            StageAdvancePolicy(
                detection_method=lambda: self.normalize_pipeline_detection_method,
                consume_recommendation=lambda: self.consume_pipeline_recommendation,
                recommend=stage_advance_policy.recommend,
                canonical_accessories=lambda: self.canonical_pipeline_accessory_ids,
                orchestration=stage_advance_policy.orchestration,
                pause=stage_advance_policy.pause,
                training_quality=stage_advance_policy.training_quality,
                link_model=stage_advance_policy.link_model,
                http_error=stage_advance_policy.http_error,
                cancelled_error=stage_advance_policy.cancelled_error,
            ),
            StageAdvanceAssets(
                load_config=stage_advance_assets.load_config,
                save_config=stage_advance_assets.save_config,
                activate_ai=lambda: self.activate_pipeline_ai_detection_task,
                prepare=stage_advance_assets.prepare,
                materialize=stage_advance_assets.materialize,
                normalize=stage_advance_assets.normalize,
            ),
            StageAdvanceJobs(
                request_type=stage_advance_jobs.request_type,
                sample_generation=stage_advance_jobs.sample_generation,
                training=stage_advance_jobs.training,
                task_name=stage_advance_jobs.task_name,
                log_samples=stage_advance_jobs.log_samples,
                log_training=stage_advance_jobs.log_training,
            ),
            StageAdvanceRuntime(
                persist_progress=stage_advance_runtime.persist_progress,
                monotonic=stage_advance_runtime.monotonic,
                clock=stage_advance_runtime.clock,
                print=stage_advance_runtime.print,
            ),
        )
        self.reconciliation = PipelineReconciliation(
            ReconciliationPolicy(
                normalize=lambda: self.normalize_pipeline_detection_method,
                uses_training=lambda: self.pipeline_method_uses_training,
            ),
            ReconciliationRegistry(
                lock=lambda: self.runtime.advance_registry_lock,
                inflight=lambda: self.runtime.advance_inflight,
                timeout=reconciliation_registry.timeout,
                now=reconciliation_registry.now,
            ),
            ReconciliationCalls(
                load_agent_config=reconciliation_calls.load_agent_config,
                supported=reconciliation_calls.supported,
                training_finder=reconciliation_calls.training_finder,
                reap=lambda: self.reap_pipeline_advance_zombie,
                sync=lambda: self.sync_pipeline_task,
                needs_auto_agent=lambda: self.pipeline_task_needs_auto_agent,
                orchestration=reconciliation_calls.orchestration,
                signature=lambda: self.pipeline_task_decision_signature,
            ),
        )
        self.recommendations = PipelineRecommendations(
            PipelineRecommendationMethodPolicy(
                normalize=lambda: self.normalize_pipeline_detection_method,
                uses_training=lambda: self.pipeline_method_uses_training,
            ),
            PipelineRecommendationLinks(
                signature=lambda: self.pipeline_recommendation_signature,
                next_stage=lambda: self.pipeline_next_recommendation_stage,
                ready=lambda: self.pipeline_recommendation_ready,
            ),
        )

    def canonical_pipeline_accessory_ids(self, config: Record, ids: list[str]) -> list[str]:
        return self.queries.canonical_pipeline_accessory_ids(config, ids)

    def normalize_pipeline_accessory_counts(self, config: Record, ids: list[str], counts: Any = None) -> dict[str, int]:
        return self.queries.normalize_pipeline_accessory_counts(config, ids, counts)

    def normalize_pipeline_detection_method(self, value: str | None) -> str:
        return self.queries.normalize_pipeline_detection_method(value)

    def pipeline_method_uses_training(self, value: str | None) -> bool:
        return self.queries.pipeline_method_uses_training(value)

    def upsert_pipeline_ai_detection_task(self, task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        return self.activation.upsert_pipeline_ai_detection_task(task, config)

    def activate_pipeline_ai_detection_task(self, task: dict[str, Any], config: dict[str, Any]) -> bool:
        return self.activation.activate_pipeline_ai_detection_task(task, config)

    def pipeline_ai_task_id(self, ai_task_id: str) -> str:
        return self.ai_sync.pipeline_ai_task_id(ai_task_id)

    def pipeline_ai_task_training_route(self, ai_task: dict[str, Any], config: dict[str, Any]) -> str:
        return self.ai_sync.pipeline_ai_task_training_route(ai_task, config)

    def sync_pipeline_ai_detection_tasks(self, tasks: list[dict[str, Any]], config: dict[str, Any], user: dict[str, Any] | None, target_user_id: str | None=None, *, ai_tasks: list[dict[str, Any]] | None=None) -> bool:
        return self.ai_sync.sync_pipeline_ai_detection_tasks(tasks, config, user, target_user_id, ai_tasks=ai_tasks)

    def linked_training_job(self, task: dict[str, Any], load_task: Callable[[Path], dict[str, Any] | None] | None=None) -> dict[str, Any] | None:
        return self.training.linked_training_job(task, load_task)

    def sync_pipeline_task(self, task: dict[str, Any], load_task: Callable[[Path], dict[str, Any] | None] | None=None) -> bool:
        return self.training.sync_pipeline_task(task, load_task)

    def advance_pipeline_task(self, task: dict[str, Any], cancel_event: 'threading.Event | None'=None) -> None:
        return self.advance.advance(task, cancel_event)

    def pipeline_task_decision_signature(self, task: dict[str, Any]) -> str:
        return self.reconciliation.pipeline_task_decision_signature(task)

    def pipeline_task_needs_auto_agent(self, task: dict[str, Any]) -> bool:
        return self.reconciliation.pipeline_task_needs_auto_agent(task)

    def reap_pipeline_advance_zombie(self, task: dict[str, Any]) -> bool:
        return self.reconciliation.reap_pipeline_advance_zombie(task)

    def sync_and_auto_advance_pipeline(self, tasks: list[dict[str, Any]]) -> tuple[bool, list[str], list[str]]:
        return self.reconciliation.sync_and_auto_advance_pipeline(tasks)

    def pipeline_recommendation_signature(self, task: dict[str, Any], stage: str) -> str:
        return self.recommendations.pipeline_recommendation_signature(task, stage)

    def pipeline_next_recommendation_stage(self, task: dict[str, Any]) -> str:
        return self.recommendations.pipeline_next_recommendation_stage(task)

    def pipeline_recommendation_ready(self, task: dict[str, Any], stage: str) -> bool:
        return self.recommendations.pipeline_recommendation_ready(task, stage)

    def consume_pipeline_recommendation(self, task: dict[str, Any], stage: str) -> dict[str, Any] | None:
        return self.recommendations.consume_pipeline_recommendation(task, stage)

    def collect_pipeline_recommendation_pregen(self, tasks: list[dict[str, Any]]) -> list[tuple[str, str]]:
        return self.recommendations.collect_pipeline_recommendation_pregen(tasks)
