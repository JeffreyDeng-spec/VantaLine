'Auto-optimization state, readiness, status and shadow ownership graph.\n\nSynthetic generation and training scheduling remain separate collaborators.\nConstruction retains typed capabilities without reading records or starting threads.\n'
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Any
from ..detection.workflow_composition import DetectionWorkflows
from ..runtime.training_tasks import TrainingThreadLifecycle
from .auto_optimization_runtime_state import AutoOptimizationRuntimeState
from .auto_optimization_settings import AutoOptimizationSettings
from .auto_optimization_state_store import AutoOptimizationStateStore
from .auto_optimization_state_ports import AutoOptimizationStateStorage, AutoOptimizationStatePolicy
from .auto_optimization_readiness import AutoOptimizationReadiness
from .auto_optimization_readiness_ports import AutoOptimizationReadinessPorts
from .auto_optimization_status import AutoOptimizationStatus
from .auto_optimization_status_ports import AutoOptimizationStatusState, AutoOptimizationStatusPolicy
from .auto_optimization_shadow_evaluation import AutoOptimizationShadowEvaluation
from .auto_optimization_shadow_evaluation_ports import ShadowState, ShadowObservation, ShadowPromotion
from .auto_optimization_recommendations import AutoOptimizationRecommendations
from .auto_optimization_state_ports import AutoOptimizationStateFiles, AutoOptimizationStateRepository
from .auto_optimization_state_ports import AutoOptimizationStateEncoder
from ..model_profiles.dependencies import ResolverProvider
from ..model_profiles.snapshots import pinned
from .auto_optimization_state_ports import AutoOptimizationStateCache
from .auto_optimization_label_generation_ports import ImageFiles
from .auto_optimization_shadow_evaluation_ports import DeleteTrainingRecord, RetirementFiles
Record = dict[str, Any]

@dataclass(frozen=True)
class StateStorage:
    AUTO_OPTIMIZE_DIR: Callable[[], Path]
    AI_DETECTION_MODEL_ID: Callable[[], str]
    _business_files: Callable[[], AutoOptimizationStateFiles]
    runtime_postgres_repository_or_none: Callable[[], Callable[[], AutoOptimizationStateRepository | None]]
@dataclass(frozen=True)
class StatePolicy:
    sanitize_ai_detection_task_id: Callable[[], Callable[[Any], str]]
    safe_record_id: Callable[[], Callable[[Any], str]]
    row_raw_json_list: Callable[[], Callable[[list[Record]], list[Any]]]
    auto_optimize_state_row: Callable[[], AutoOptimizationStateEncoder]
    resolve_model_profiles: Callable[[], ResolverProvider]
@dataclass(frozen=True)
class ReadinessLookups:
    find_training_task: Callable[[], Callable[[str], Record | None]]
    load_config: Callable[[], Callable[[], Record]]
    canonical_pipeline_accessory_ids: Callable[[], Callable[[Record, list[str]], list[str]]]
    normalize_pipeline_accessory_counts: Callable[[], Callable[[Record, list[str], Any], dict[str, int]]]
    load_pipeline_tasks: Callable[[], Callable[[], list[Record]]]
    normalize_pipeline_detection_method: Callable[[], Callable[[str], str]]
    pipeline_task_model_status: Callable[[], Callable[[Record], str]]
    pipeline_task_model_id: Callable[[], Callable[[Record], str]]
@dataclass(frozen=True)
class StatusLookups:
    hydrate_auto_optimize_background_from_ai_task: Callable[[], Callable[[Record], bool]]
    find_training_task: Callable[[], Callable[[str], Record | None]]
    record_visible_to_user: Callable[[], Callable[[Record, Record], bool]]
    current_auth_user: Callable[[], Callable[[], Record | None]]
    start_auto_optimize_label_worker: Callable[[], Callable[[str], None]]
@dataclass(frozen=True)
class StatusProjection:
    auto_optimize_public_sprite_pool: Callable[[], Callable[[Record], list[Record]]]
    background_set_payload: Callable[[], Callable[[str], Record]]
    AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT: Callable[[], int]
    public_path_sanitized: Callable[[], Callable[[Any], Any]]
    normalize_expected_production_count: Callable[[], Callable[[Any], int]]
@dataclass(frozen=True)
class ShadowPolicy:
    sanitize_ai_detection_task_id: Callable[[], Callable[[str], str]]
    bounded_text: Callable[[], Callable[[Any, int], str]]
@dataclass(frozen=True)
class ShadowImages:
    resolve_service_path: Callable[[], Callable[[Any], Path]]
    _image_files: Callable[[], ImageFiles]
    safe_record_id: Callable[[], Callable[[str], str]]
@dataclass(frozen=True)
class Retirement:
    LEGACY_OWNER_ID: Callable[[], str]
    delete_training_task_record: Callable[[], DeleteTrainingRecord]
    training_run_roots: Callable[[], Callable[[], list[Path]]]
    _business_files: Callable[[], RetirementFiles]
class AutoOptimizationCore:
    def __init__(self, *,
                 settings: AutoOptimizationSettings,
                 runtime: AutoOptimizationRuntimeState,
                 detection: Callable[[], DetectionWorkflows],
                 shadow_runtime: TrainingThreadLifecycle,
                 shadow_resolver: ResolverProvider,
                 storage: StateStorage,
                 state_policy: StatePolicy,
                 cache: AutoOptimizationStateCache,
                 readiness: ReadinessLookups,
                 status_state: StatusLookups,
                 status_policy: StatusProjection,
                 shadow_state: ShadowPolicy,
                 observation: ShadowImages,
                 retirement: Retirement,
                 accessory_lookup: Callable[[Record], dict[str, Record]],
                 material_type: Callable[[Record], str],
                 bounded_text: Callable[[], Callable[[Any, int], str]],
                 ):
        self.settings = settings
        self.runtime = runtime
        self.detection = detection
        self.store = AutoOptimizationStateStore(
            storage=AutoOptimizationStateStorage(
                AUTO_OPTIMIZE_DIR=storage.AUTO_OPTIMIZE_DIR,
                AI_DETECTION_MODEL_ID=storage.AI_DETECTION_MODEL_ID,
                _business_files=storage._business_files,
                runtime_postgres_repository_or_none=storage.runtime_postgres_repository_or_none,
                auto_optimize_task_path=lambda: self.auto_optimize_task_path,
            ),
            policy=AutoOptimizationStatePolicy(
                sanitize_ai_detection_task_id=state_policy.sanitize_ai_detection_task_id,
                safe_record_id=state_policy.safe_record_id,
                row_raw_json_list=state_policy.row_raw_json_list,
                auto_optimize_state_row=state_policy.auto_optimize_state_row,
                default_auto_optimize_settings=self.settings.default_auto_optimize_settings,
                resolve_model_profiles=state_policy.resolve_model_profiles,
            ),
            cache=AutoOptimizationStateCache(
                _read_path_cache=cache._read_path_cache,
                store_read_cache_get=cache.store_read_cache_get,
                store_read_cache_put=cache.store_read_cache_put,
                store_read_cache_invalidate=cache.store_read_cache_invalidate,
            ),
        )
        self.recommendations = AutoOptimizationRecommendations(
            settings=self.settings,
            accessory_lookup_by_id=accessory_lookup,
            accessory_material_type=material_type,
            bounded_text=bounded_text,
        )
        self.readiness = AutoOptimizationReadiness(
            AutoOptimizationReadinessPorts(
                find_training_task=readiness.find_training_task,
                auto_optimize_linked_pipeline_model_id=lambda: self.auto_optimize_linked_pipeline_model_id,
                load_config=readiness.load_config,
                canonical_pipeline_accessory_ids=readiness.canonical_pipeline_accessory_ids,
                normalize_pipeline_accessory_counts=readiness.normalize_pipeline_accessory_counts,
                load_pipeline_tasks=readiness.load_pipeline_tasks,
                normalize_pipeline_detection_method=readiness.normalize_pipeline_detection_method,
                pipeline_task_model_status=readiness.pipeline_task_model_status,
                pipeline_task_model_id=readiness.pipeline_task_model_id,
                default_auto_optimize_settings=self.settings.default_auto_optimize_settings,
                auto_optimize_completed_model_id=lambda: self.auto_optimize_completed_model_id,
            ),
        )
        self.status = AutoOptimizationStatus(
            AutoOptimizationStatusState(
                _auto_optimize_lock=lambda: self.runtime.lock,
                load_auto_optimize_state=lambda: self.load_auto_optimize_state,
                save_auto_optimize_state=lambda: self.save_auto_optimize_state,
                hydrate_auto_optimize_background_from_ai_task=status_state.hydrate_auto_optimize_background_from_ai_task,
                auto_optimize_completed_model_id=lambda: self.auto_optimize_completed_model_id,
                auto_optimize_stop_capture_for_model_locked=lambda: self.auto_optimize_stop_capture_for_model_locked,
                find_training_task=status_state.find_training_task,
                record_visible_to_user=status_state.record_visible_to_user,
                current_auth_user=status_state.current_auth_user,
                start_auto_optimize_label_worker=status_state.start_auto_optimize_label_worker,
                public_auto_optimize_state=lambda: self.public_auto_optimize_state,
            ),
            AutoOptimizationStatusPolicy(
                default_auto_optimize_settings=self.settings.default_auto_optimize_settings,
                auto_optimize_public_sprite_pool=status_policy.auto_optimize_public_sprite_pool,
                background_set_payload=status_policy.background_set_payload,
                auto_optimize_samples_per_real_image=self.settings.auto_optimize_samples_per_real_image,
                auto_optimize_training_parameters=self.settings.auto_optimize_training_parameters,
                auto_optimize_training_requirements=self.settings.auto_optimize_training_requirements,
                auto_optimize_negative_samples_per_real_image=self.settings.auto_optimize_negative_samples_per_real_image,
                auto_optimize_positive_derivatives_per_real_image=self.settings.auto_optimize_positive_derivatives_per_real_image,
                AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT=status_policy.AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT,
                public_path_sanitized=status_policy.public_path_sanitized,
                auto_optimize_phase_name=lambda: self.auto_optimize_phase_name,
                normalize_expected_production_count=status_policy.normalize_expected_production_count,
                public_auto_optimize_initialization_payload=lambda: self.public_auto_optimize_initialization_payload,
            ),
        )
        self.pinned_shadow_worker = pinned(
            shadow_resolver,
            lambda identity: self.load_auto_optimize_state(identity),
        )(self.auto_optimize_shadow_worker)
        self.shadow = AutoOptimizationShadowEvaluation(
            state=ShadowState(
                sanitize_ai_detection_task_id=shadow_state.sanitize_ai_detection_task_id,
                _auto_optimize_lock=lambda: self.runtime.lock,
                _auto_optimize_shadow_threads=lambda: self.runtime.shadow_threads,
                auto_optimize_shadow_worker=lambda: self.pinned_shadow_worker,
                load_auto_optimize_state=lambda: self.load_auto_optimize_state,
                save_auto_optimize_state=lambda: self.save_auto_optimize_state,
                bounded_text=shadow_state.bounded_text,
            ),
            observation=ShadowObservation(
                resolve_service_path=observation.resolve_service_path,
                _image_files=observation._image_files,
                analyze_bgr=lambda: self.analyze_bgr,
                safe_record_id=observation.safe_record_id,
            ),
            promotion=ShadowPromotion(
                maybe_promote_auto_optimize_model_locked=lambda: self.maybe_promote_auto_optimize_model_locked,
                default_auto_optimize_settings=self.settings.default_auto_optimize_settings,
                cleanup_auto_optimize_retired_candidate_locked=lambda: self.cleanup_auto_optimize_retired_candidate_locked,
                LEGACY_OWNER_ID=retirement.LEGACY_OWNER_ID,
                delete_training_task_record=retirement.delete_training_task_record,
                training_run_roots=retirement.training_run_roots,
                _business_files=retirement._business_files,
            ),
            runtime=shadow_runtime,
        )

    def auto_optimize_linked_pipeline_model_id(self, state: dict[str, Any]) -> str:
        return self.readiness.auto_optimize_linked_pipeline_model_id(state)

    def auto_optimize_completed_model_id(self, state: dict[str, Any]) -> str:
        return self.readiness.auto_optimize_completed_model_id(state)

    def load_auto_optimize_state(self, task_id: str) -> dict[str, Any]:
        return self.store.load_auto_optimize_state(task_id)

    def save_auto_optimize_state(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.store.save_auto_optimize_state(state)

    def auto_optimize_stop_capture_for_model_locked(self, state: dict[str, Any], model_id: str, *, reason: str) -> bool:
        return self.readiness.auto_optimize_stop_capture_for_model_locked(state, model_id, reason=reason)

    def public_auto_optimize_state(self, task_id: str, *, user: dict[str, Any] | None=None) -> dict[str, Any]:
        return self.status.public_auto_optimize_state(task_id, user=user)

    def auto_optimize_phase_name(self, state: dict[str, Any]) -> str:
        return self.readiness.auto_optimize_phase_name(state)

    def public_auto_optimize_initialization_payload(self, state: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        return self.recommendations.public_auto_optimize_initialization_payload(state, settings)

    def auto_optimize_task_path(self, task_id: str) -> Path:
        return self.store.auto_optimize_task_path(task_id)

    def auto_optimize_shadow_worker(self, task_id: str, sample_id: str) -> None:
        return self.shadow.auto_optimize_shadow_worker(task_id, sample_id)

    def analyze_bgr(self, image, request_id, model_id, *, image_path):
        return self.detection().analyze_bgr(image, request_id, model_id, image_path=image_path)

    def maybe_promote_auto_optimize_model_locked(self, state: dict[str, Any]) -> None:
        return self.shadow.maybe_promote_auto_optimize_model_locked(state)

    def cleanup_auto_optimize_retired_candidate_locked(self, state: dict[str, Any], model_id: str, *, keep_model_id: str) -> None:
        return self.shadow.cleanup_auto_optimize_retired_candidate_locked(state, model_id, keep_model_id=keep_model_id)
