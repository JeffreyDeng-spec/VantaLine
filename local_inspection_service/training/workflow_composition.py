"""Owned automatic-optimization state and execution graph; inert construction."""
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from ..detection.workflow_composition import DetectionWorkflows
from ..runtime.training_tasks import TrainingThreadLifecycle
from ..model_profiles.dependencies import ResolverProvider
from .auto_optimization_runtime_state import AutoOptimizationRuntimeState
from .auto_optimization_settings import AutoOptimizationSettings
from .core_composition import (
    AutoOptimizationCore,
    StateStorage,
    StatePolicy,
    AutoOptimizationStateCache,
    ReadinessLookups,
    StatusLookups,
    StatusProjection,
    ShadowPolicy,
    ShadowImages,
    Retirement,
)
from .execution_composition import (
    AutoOptimizationExecution,
    ExternalAutoOptimizationAdvisorPorts,
    ExternalAutoOptimizationTaskInitializationPorts,
    ExternalAutoOptimizationMaskPromptPorts,
    ExternalAutoOptimizationMaskVisualPorts,
    ExternalAutoOptimizationMaskVerificationPorts,
    ExternalSpritePublication,
    ExternalLabelGenerationArtifacts,
    ExternalLabelGenerationPolicy,
    ExternalLabelGenerationModels,
    ExternalProcessingState,
    ExternalProcessingArtifacts,
    ExternalProcessingExecution,
    ExternalSchedulingPolicy,
    ExternalSchedulingSubmission,
    ExternalSchedulingState,
    ExternalSpriteFiles,
    ExternalSpriteGeometry,
    ExternalSyntheticGeometry,
    ExternalSyntheticPublication,
    ExternalSyntheticBatchConfiguration,
    ExternalSyntheticBatchPublication,
    ExternalDatasetConfiguration,
    ExternalDatasetSources,
    ExternalDatasetPublication,
    ExternalDatasetLayout,
    ExternalRequestAccess,
    ExternalRequestActions,
)
Record = dict[str, Any]

@dataclass(frozen=True)
class AutoOptimizationStatusLookups:
    hydrate_auto_optimize_background_from_ai_task: Callable[[], Callable[[Record], bool]]
    find_training_task: Callable[[], Callable[[str], Record | None]]
    record_visible_to_user: Callable[[], Callable[[Record, Record], bool]]
    current_auth_user: Callable[[], Callable[[], Record | None]]

@dataclass(frozen=True)
class AutoOptimizationStatusProjection:
    background_set_payload: Callable[[], Callable[[str], Record]]
    AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT: Callable[[], int]
    public_path_sanitized: Callable[[], Callable[[Any], Any]]
    normalize_expected_production_count: Callable[[], Callable[[Any], int]]

class AutoOptimizationWorkflows:
    def __init__(self, *,
        settings: AutoOptimizationSettings,
        runtime: AutoOptimizationRuntimeState,
        detection: Callable[[], DetectionWorkflows],
        shadow_runtime: TrainingThreadLifecycle,
        storage: StateStorage,
        state_policy: StatePolicy,
        cache: AutoOptimizationStateCache,
        readiness: ReadinessLookups,
        status_state: AutoOptimizationStatusLookups,
        status_policy: AutoOptimizationStatusProjection,
        shadow_state: ShadowPolicy,
        observation: ShadowImages,
        retirement: Retirement,
        accessory_lookup: Callable[[Record], dict[str, Record]],
        material_type: Callable[[Record], str],
        bounded_text: Callable[[], Callable[[Any, int], str]],
        shadow_resolver: ResolverProvider,
        model_resolver: ResolverProvider,
        negative_samples_default: int,
        label_runtime: TrainingThreadLifecycle,
        scheduling_runtime: TrainingThreadLifecycle,
        external_AutoOptimizationAdvisorPorts: ExternalAutoOptimizationAdvisorPorts,
        external_AutoOptimizationTaskInitializationPorts: ExternalAutoOptimizationTaskInitializationPorts,
        external_AutoOptimizationMaskPromptPorts: ExternalAutoOptimizationMaskPromptPorts,
        external_AutoOptimizationMaskVisualPorts: ExternalAutoOptimizationMaskVisualPorts,
        external_AutoOptimizationMaskVerificationPorts: ExternalAutoOptimizationMaskVerificationPorts,
        external_SpritePublication: ExternalSpritePublication,
        external_LabelGenerationArtifacts: ExternalLabelGenerationArtifacts,
        external_LabelGenerationPolicy: ExternalLabelGenerationPolicy,
        external_LabelGenerationModels: ExternalLabelGenerationModels,
        external_ProcessingState: ExternalProcessingState,
        external_ProcessingArtifacts: ExternalProcessingArtifacts,
        external_ProcessingExecution: ExternalProcessingExecution,
        external_SchedulingPolicy: ExternalSchedulingPolicy,
        external_SchedulingSubmission: ExternalSchedulingSubmission,
        external_SchedulingState: ExternalSchedulingState,
        external_SpriteFiles: ExternalSpriteFiles,
        external_SpriteGeometry: ExternalSpriteGeometry,
        external_SyntheticGeometry: ExternalSyntheticGeometry,
        external_SyntheticPublication: ExternalSyntheticPublication,
        external_SyntheticBatchConfiguration: ExternalSyntheticBatchConfiguration,
        external_SyntheticBatchPublication: ExternalSyntheticBatchPublication,
        external_DatasetConfiguration: ExternalDatasetConfiguration,
        external_DatasetSources: ExternalDatasetSources,
        external_DatasetPublication: ExternalDatasetPublication,
        external_DatasetLayout: ExternalDatasetLayout,
        external_RequestAccess: ExternalRequestAccess,
        external_RequestActions: ExternalRequestActions,
    ):
        self.core = AutoOptimizationCore(
            settings=settings,
            runtime=runtime,
            detection=detection,
            shadow_runtime=shadow_runtime,
            shadow_resolver=shadow_resolver,
            storage=storage,
            state_policy=state_policy,
            cache=cache,
            readiness=readiness,
            status_state=StatusLookups(
                hydrate_auto_optimize_background_from_ai_task=status_state.hydrate_auto_optimize_background_from_ai_task,
                find_training_task=status_state.find_training_task,
                record_visible_to_user=status_state.record_visible_to_user,
                current_auth_user=status_state.current_auth_user,
                start_auto_optimize_label_worker=lambda: self.start_auto_optimize_label_worker,
            ),
            status_policy=StatusProjection(
                auto_optimize_public_sprite_pool=lambda: self.auto_optimize_public_sprite_pool,
                background_set_payload=status_policy.background_set_payload,
                AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT=status_policy.AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT,
                public_path_sanitized=status_policy.public_path_sanitized,
                normalize_expected_production_count=status_policy.normalize_expected_production_count,
            ),
            shadow_state=shadow_state,
            observation=observation,
            retirement=retirement,
            accessory_lookup=accessory_lookup,
            material_type=material_type,
            bounded_text=bounded_text,
        )
        self.execution = AutoOptimizationExecution(
            core=self.core,
            settings=settings,
            runtime=runtime,
            negative_samples_default=negative_samples_default,
            model_resolver=model_resolver,
            label_runtime=label_runtime,
            scheduling_runtime=scheduling_runtime,
            external_AutoOptimizationAdvisorPorts=external_AutoOptimizationAdvisorPorts,
            external_AutoOptimizationTaskInitializationPorts=external_AutoOptimizationTaskInitializationPorts,
            external_AutoOptimizationMaskPromptPorts=external_AutoOptimizationMaskPromptPorts,
            external_AutoOptimizationMaskVisualPorts=external_AutoOptimizationMaskVisualPorts,
            external_AutoOptimizationMaskVerificationPorts=external_AutoOptimizationMaskVerificationPorts,
            external_SpritePublication=external_SpritePublication,
            external_LabelGenerationArtifacts=external_LabelGenerationArtifacts,
            external_LabelGenerationPolicy=external_LabelGenerationPolicy,
            external_LabelGenerationModels=external_LabelGenerationModels,
            external_ProcessingState=external_ProcessingState,
            external_ProcessingArtifacts=external_ProcessingArtifacts,
            external_ProcessingExecution=external_ProcessingExecution,
            external_SchedulingPolicy=external_SchedulingPolicy,
            external_SchedulingSubmission=external_SchedulingSubmission,
            external_SchedulingState=external_SchedulingState,
            external_SpriteFiles=external_SpriteFiles,
            external_SpriteGeometry=external_SpriteGeometry,
            external_SyntheticGeometry=external_SyntheticGeometry,
            external_SyntheticPublication=external_SyntheticPublication,
            external_SyntheticBatchConfiguration=external_SyntheticBatchConfiguration,
            external_SyntheticBatchPublication=external_SyntheticBatchPublication,
            external_DatasetConfiguration=external_DatasetConfiguration,
            external_DatasetSources=external_DatasetSources,
            external_DatasetPublication=external_DatasetPublication,
            external_DatasetLayout=external_DatasetLayout,
            external_RequestAccess=external_RequestAccess,
            external_RequestActions=external_RequestActions,
        )

    def start_auto_optimize_label_worker(self, task_id: str) -> None:
        return self.execution.start_auto_optimize_label_worker(task_id)

    def auto_optimize_public_sprite_pool(self, state: Record, limit: int = 80) -> list[Record]:
        return self.execution.auto_optimize_public_sprite_pool(state, limit)
