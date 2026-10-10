"""Historical default-only forwarders. Production business ports use owned graphs."""
from __future__ import annotations
from ..runtime.default_application import default_application as _application
import os
from typing import Any
from typing import Callable
from pathlib import Path
from local_inspection_service.schemas.training import TrainingStartRequest
from ultralytics import YOLO
import numpy as np
from local_inspection_service.model_profiles.snapshots import pinned as pinned_model_profiles
import tempfile
import threading
import urllib.error
import urllib.request
BACKGROUND_ROI_PX = _application.values.BACKGROUND_ROI_PX
PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES = _application.values.PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES
_agent_chat_transport = _application.training_pipeline._agent_chat_transport
_agent_connection_discovery = _application.training_pipeline._agent_connection_discovery
_agent_conversation = _application.training_pipeline._agent_conversation
_agent_decision_context = _application.training_pipeline._agent_decision_context
_agent_decision_flow = _application.training_pipeline._agent_decision_flow
_agent_decision_policy = _application.training_pipeline._agent_decision_policy
_agent_orchestration_state = _application.training_pipeline._agent_orchestration_state
_agent_pipeline_actions = _application.training_pipeline._agent_pipeline_actions
_agent_pipeline_turns = _application.training_pipeline._agent_pipeline_turns
_agent_pose_assets = _application.training_pipeline._agent_pose_assets
_agent_pose_templates = _application.training_pipeline._agent_pose_templates
_agent_protocol_policy = _application.training_pipeline._agent_protocol_policy
_agent_recommendation = _application.training_pipeline._agent_recommendation
_agent_settings_projection = _application.training_pipeline._agent_settings_projection
_agent_tool_call_records = _application.training_pipeline._agent_tool_call_records
_auto_optimization_dataset = _application.training_pipeline._auto_optimization_dataset
_auto_optimization_initialization = _application.training_pipeline._auto_optimization_initialization
_auto_optimization_label_generation = _application.training_pipeline._auto_optimization_label_generation
_auto_optimization_label_processing = _application.training_pipeline._auto_optimization_label_processing
_auto_optimization_links = _application.training_pipeline._auto_optimization_links
_auto_optimization_mask_prompts = _application.training_pipeline._auto_optimization_mask_prompts
_auto_optimization_mask_verification = _application.training_pipeline._auto_optimization_mask_verification
_auto_optimization_mask_visuals = _application.training_pipeline._auto_optimization_mask_visuals
_auto_optimization_readiness = _application.training_pipeline._auto_optimization_readiness
_auto_optimization_recommendations = _application.training_pipeline._auto_optimization_recommendations
_auto_optimization_rendering = _application.training_pipeline._auto_optimization_rendering
_auto_optimization_shadow_evaluation = _application.training_pipeline._auto_optimization_shadow_evaluation
_auto_optimization_sprite_publication = _application.training_pipeline._auto_optimization_sprite_publication
_auto_optimization_sprites = _application.training_pipeline._auto_optimization_sprites
_auto_optimization_state_store = _application.training_pipeline._auto_optimization_state_store
_auto_optimization_status = _application.training_pipeline._auto_optimization_status
_auto_optimization_synthetic_batch = _application.training_pipeline._auto_optimization_synthetic_batch
_auto_optimization_training_scheduling = _application.training_pipeline._auto_optimization_training_scheduling
_background_catalog = _application.training_pipeline._background_catalog
_background_codex_generation = _application.training_pipeline._background_codex_generation
_background_codex_thread = _application.training_pipeline._background_codex_thread
_background_image_files = _application.training_pipeline._background_image_files
_background_manifest = _application.training_pipeline._background_manifest
_background_minimum_images = _application.training_pipeline._background_minimum_images
_background_seeding = _application.training_pipeline._background_seeding
_background_selection = _application.training_pipeline._background_selection
_background_task_runner = _application.training_pipeline._background_task_runner
_background_task_submission = _application.training_pipeline._background_task_submission
_background_validation = _application.training_pipeline._background_validation
_background_variants = _application.training_pipeline._background_variants
_background_writes = _application.training_pipeline._background_writes
_dataset_catalog = _application.training_pipeline._dataset_catalog
_legacy_worker_refresh = _application.training_pipeline._legacy_worker_refresh
_legacy_worker_requests = _application.training_pipeline._legacy_worker_requests
_legacy_worker_tasks = _application.training_pipeline._legacy_worker_tasks
_local_models = _application.training_pipeline._local_models
_model_catalog = _application.training_pipeline._model_catalog
_model_profile_configuration = _application.infrastructure._model_profile_configuration
_model_selection = _application.training_pipeline._model_selection
_photo_highlight_comparison = _application.training_pipeline._photo_highlight_comparison
_photo_highlight_image_input = _application.training_pipeline._photo_highlight_image_input
_photo_highlight_selection = _application.training_pipeline._photo_highlight_selection
_photo_highlight_sources = _application.training_pipeline._photo_highlight_sources
_photo_highlight_workflow = _application.training_pipeline._photo_highlight_workflow
_pipeline_advance_runtime = _application.training_pipeline._pipeline_advance_runtime
_pipeline_ai_activation = _application.training_pipeline._pipeline_ai_activation
_pipeline_ai_task_sync = _application.training_pipeline._pipeline_ai_task_sync
_pipeline_auto_agent_runtime = _application.training_pipeline._pipeline_auto_agent_runtime
_pipeline_background_publication = _application.training_pipeline._pipeline_background_publication
_pipeline_candidate_flow = _application.training_pipeline._pipeline_candidate_flow
_pipeline_recommendation_runtime = _application.training_pipeline._pipeline_recommendation_runtime
_pipeline_recommendations = _application.training_pipeline._pipeline_recommendations
_pipeline_reconciliation = _application.training_pipeline._pipeline_reconciliation
_pipeline_resource_links = _application.training_pipeline._pipeline_resource_links
_pipeline_resource_status = _application.training_pipeline._pipeline_resource_status
_pipeline_stage_advancer = _application.training_pipeline._pipeline_stage_advancer
_pipeline_state_store = _application.training_pipeline._pipeline_state_store
_pipeline_task_metadata = _application.training_pipeline._pipeline_task_metadata
_pipeline_task_mutations = _application.training_pipeline._pipeline_task_mutations
_pipeline_task_snapshots = _application.training_pipeline._pipeline_task_snapshots
_pipeline_task_store = _application.training_pipeline._pipeline_task_store
_pipeline_trained_model_link = _application.training_pipeline._pipeline_trained_model_link
_pipeline_training_status = _application.training_pipeline._pipeline_training_status
_pipeline_training_sync = _application.training_pipeline._pipeline_training_sync
_pose_artifact_store = _application.training_pipeline._pose_artifact_store
_pose_asset_materialization = _application.training_pipeline._pose_asset_materialization
_pose_call_execution = _application.training_pipeline._pose_call_execution
_pose_call_registration = _application.training_pipeline._pose_call_registration
_pose_chroma_policy = _application.training_pipeline._pose_chroma_policy
_pose_cutout_pipeline = _application.training_pipeline._pose_cutout_pipeline
_pose_plan_assembly = _application.training_pipeline._pose_plan_assembly
_pose_plan_generation = _application.training_pipeline._pose_plan_generation
_pose_plan_policy = _application.training_pipeline._pose_plan_policy
_pose_render_configuration = _application.training_pipeline._pose_render_configuration
_pose_render_content = _application.training_pipeline._pose_render_content
_pose_sample_preparation = _application.training_pipeline._pose_sample_preparation
_pose_sprite_builder = _application.training_pipeline._pose_sprite_builder
_preview_masks = _application.training_pipeline._preview_masks
_preview_placement = _application.training_pipeline._preview_placement
_real_photo_workflows = _application.training_pipeline._real_photo_workflows
_remote_training = _application.training_pipeline._remote_training
_runpod_artifacts = _application.training_pipeline._runpod_artifacts
_runpod_client = _application.training_pipeline._runpod_client
_runpod_exports = _application.training_pipeline._runpod_exports
_runpod_flow = _application.training_pipeline._runpod_flow
_runpod_output_parser = _application.training_pipeline._runpod_output_parser
_runpod_payload = _application.training_pipeline._runpod_payload
_runpod_submission = _application.training_pipeline._runpod_submission
_task_background_store = _application.training_pipeline._task_background_store
_task_projection = _application.training_pipeline._task_projection
_trained_model_catalog = _application.training_pipeline._trained_model_catalog
_training_account_state = _application.training_pipeline._training_account_state
_training_annotation_preview = _application.training_pipeline._training_annotation_preview
_training_asset_preparation = _application.training_pipeline._training_asset_preparation
_training_background_library = _application.training_pipeline._training_background_library
_training_background_renderer = _application.training_pipeline._training_background_renderer
_training_candidate_sync = _application.training_pipeline._training_candidate_sync
_training_dataset_archives = _application.training_pipeline._training_dataset_archives
_training_dataset_generator = _application.training_pipeline._training_dataset_generator
_training_dataset_links = _application.training_pipeline._training_dataset_links
_training_execution = _application.training_pipeline._training_execution
_training_executor_settings = _application.training_pipeline._training_executor_settings
_training_links = _application.training_pipeline._training_links
_training_output_links = _application.training_pipeline._training_output_links
_training_preview_cache = _application.training_pipeline._training_preview_cache
_training_preview_renderer = _application.training_pipeline._training_preview_renderer
_training_resource_mutations = _application.training_pipeline._training_resource_mutations
_training_resources = _application.training_pipeline._training_resources
_training_sample_planner = _application.training_pipeline._training_sample_planner
_training_state_workflows = _application.training_pipeline._training_state_workflows
_training_task_lookup = _application.training_pipeline._training_task_lookup
_training_task_models = _application.training_pipeline._training_task_models
_training_task_workflows = _application.training_pipeline._training_task_workflows
_transfer_progress = _application.training_pipeline._transfer_progress
_worker_artifact_import = _application.training_pipeline._worker_artifact_import
_worker_artifact_summary = _application.training_pipeline._worker_artifact_summary
_worker_bundle_metadata = _application.training_pipeline._worker_bundle_metadata
_worker_bundle_submission = _application.training_pipeline._worker_bundle_submission
_worker_bundle_timeout = _application.training_pipeline._worker_bundle_timeout
_worker_transfers = _application.training_pipeline._worker_transfers
_worker_watcher_loop = _application.training_pipeline._worker_watcher_loop
_worker_watcher_settings = _application.training_pipeline._worker_watcher_settings
status = _application.http.status

def legacy_model_specs() -> list[dict[str, Any]]:
    return _model_catalog.legacy_model_specs()

def default_training_state() -> dict[str, Any]:
    return _training_account_state.default_training_state()

def normalize_training_owner_key(owner_user_id: Any) -> str:
    return _training_account_state.normalize_training_owner_key(owner_user_id)

def training_state_store(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _training_account_state.training_state_store(config)

def sanitize_training_state_for_user(training: dict[str, Any] | None, user: dict[str, Any], selected_ids: set[str], target_user_id: str | None=None) -> dict[str, Any]:
    return _training_account_state.sanitize_training_state_for_user(training, user, selected_ids, target_user_id)

def training_state_for_user(config: dict[str, Any], user: dict[str, Any], selected_ids: set[str], target_user_id: str | None=None) -> dict[str, Any]:
    return _training_account_state.training_state_for_user(config, user, selected_ids, target_user_id)

def set_training_state_for_user(config: dict[str, Any], user: dict[str, Any], training_state: dict[str, Any]) -> None:
    return _training_account_state.set_training_state_for_user(config, user, training_state)

def sync_training_state_from_task(job_id: str) -> None:
    return _training_account_state.sync_training_state_from_task(job_id)

def training_task_model_id(task: dict[str, Any], job_id: str) -> str:
    return _training_task_models.training_task_model_id(task, job_id)

def auto_optimize_task_id_from_pipeline_task(pipeline_task_id: str, pipeline_task: dict[str, Any] | None=None) -> str:
    return _pipeline_training_sync.auto_optimize_task_id_from_pipeline_task(pipeline_task_id, pipeline_task)

def sync_auto_optimize_training_candidate_from_task(task: dict[str, Any], *, ai_task_id: str, model_id: str) -> None:
    return _training_candidate_sync.sync_auto_optimize_training_candidate_from_task(task, ai_task_id=ai_task_id, model_id=model_id)

def sync_pipeline_training_state_from_task(task: dict[str, Any]) -> None:
    return _pipeline_training_sync.sync_pipeline_training_state_from_task(task)

def resolve_model_profiles():
    """Composition-only late binding; domain decorators receive this callable."""
    return _model_profile_configuration.resolve_model_profiles()

def choose_agent_mcp_chroma_screen(item: dict[str, Any]) -> dict[str, Any]:
    return _pose_chroma_policy.choose_agent_mcp_chroma_screen(item)

def auto_optimize_task_path(task_id: str) -> Path:
    return _auto_optimization_state_store.auto_optimize_task_path(task_id)

def auto_optimize_complexity_rule_recommendation(config: dict[str, Any], accessory_ids: list[str], expected_production_count: int) -> dict[str, Any]:
    return _auto_optimization_recommendations.auto_optimize_complexity_rule_recommendation(config, accessory_ids, expected_production_count)

def clamp_auto_optimize_initialization_recommendation(raw: dict[str, Any], fallback: dict[str, Any], expected_production_count: int) -> dict[str, Any]:
    return _auto_optimization_recommendations.clamp_auto_optimize_initialization_recommendation(raw, fallback, expected_production_count)

def public_auto_optimize_initialization_payload(state: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    return _auto_optimization_recommendations.public_auto_optimize_initialization_payload(state, settings)

def agent_auto_optimize_initialization_recommendation(config: dict[str, Any], accessory_ids: list[str], expected_production_count: int, fallback: dict[str, Any]) -> dict[str, Any]:
    return _auto_optimization_initialization.agent_auto_optimize_initialization_recommendation(config, accessory_ids, expected_production_count, fallback)

def initialize_auto_optimize_for_pipeline_task(task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return _auto_optimization_initialization.initialize_auto_optimize_for_pipeline_task(task, config)

def load_auto_optimize_state(task_id: str) -> dict[str, Any]:
    return _auto_optimization_state_store.load_auto_optimize_state(task_id)

def save_auto_optimize_state(state: dict[str, Any]) -> dict[str, Any]:
    return _auto_optimization_state_store.save_auto_optimize_state(state)

def list_auto_optimize_states() -> list[dict[str, Any]]:
    return _auto_optimization_state_store.list_auto_optimize_states()

def public_auto_optimize_state(task_id: str, *, user: dict[str, Any] | None=None) -> dict[str, Any]:
    return _auto_optimization_status.public_auto_optimize_state(task_id, user=user)

def auto_optimize_phase_name(state: dict[str, Any]) -> str:
    return _auto_optimization_readiness.auto_optimize_phase_name(state)

def auto_optimize_completed_model_id(state: dict[str, Any]) -> str:
    return _auto_optimization_readiness.auto_optimize_completed_model_id(state)

def auto_optimize_linked_pipeline_model_id(state: dict[str, Any]) -> str:
    return _auto_optimization_readiness.auto_optimize_linked_pipeline_model_id(state)

def pipeline_task_model_id(task: dict[str, Any]) -> str:
    return _pipeline_task_metadata.pipeline_task_model_id(task)

def auto_optimize_stop_capture_for_model_locked(state: dict[str, Any], model_id: str, *, reason: str) -> bool:
    return _auto_optimization_readiness.auto_optimize_stop_capture_for_model_locked(state, model_id, reason=reason)

def auto_optimize_capture_enabled(state: dict[str, Any]) -> bool:
    return _auto_optimization_readiness.auto_optimize_capture_enabled(state)

def auto_optimize_update_settings(task_id: str, request: Any) -> dict[str, Any]:
    return _auto_optimization_status.auto_optimize_update_settings(task_id, request)

def auto_optimize_mask_system_prompt() -> str:
    return _auto_optimization_mask_prompts.auto_optimize_mask_system_prompt()

def auto_optimize_mask_owner_user(sample: dict[str, Any]) -> dict[str, Any]:
    return _auto_optimization_mask_prompts.auto_optimize_mask_owner_user(sample)

def auto_optimize_accessory_lookup_for_sample(sample: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _auto_optimization_mask_prompts.auto_optimize_accessory_lookup_for_sample(sample)

def auto_optimize_mask_target_profile(candidate: dict[str, Any], accessories_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return _auto_optimization_mask_prompts.auto_optimize_mask_target_profile(candidate, accessories_by_id)

def auto_optimize_mask_user_prompt(assignments: list[dict[str, Any]], *, input_w: int, input_h: int, task_type: str='multi_class_segmentation_mask') -> str:
    return _auto_optimization_mask_prompts.auto_optimize_mask_user_prompt(assignments, input_w=input_w, input_h=input_h, task_type=task_type)

def auto_optimize_multicolor_mask_prompt(assignments: list[dict[str, Any]], *, input_w: int=0, input_h: int=0) -> str:
    return _auto_optimization_mask_prompts.auto_optimize_multicolor_mask_prompt(assignments, input_w=input_w, input_h=input_h)

def decode_multicolor_mask(mask_bgr: np.ndarray, assignments: list[dict[str, Any]]) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    return _auto_optimization_mask_visuals.decode_multicolor_mask(mask_bgr, assignments)

def draw_auto_optimize_review_overlay(image_bgr: np.ndarray, labels: list[dict[str, Any]], failures: list[dict[str, Any]], output_path: Path) -> tuple[str, dict[str, Any]]:
    return _auto_optimization_mask_visuals.draw_auto_optimize_review_overlay(image_bgr, labels, failures, output_path)

def auto_optimize_text_mask_requires_document_gate(candidate: dict[str, Any], profile: dict[str, Any]) -> bool:
    return _auto_optimization_mask_visuals.auto_optimize_text_mask_requires_document_gate(candidate, profile)

def validate_auto_optimize_text_mask_region(image_bgr: np.ndarray, full_mask: np.ndarray, bbox: list[int], candidate: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    return _auto_optimization_mask_visuals.validate_auto_optimize_text_mask_region(image_bgr, full_mask, bbox, candidate, profile)

def auto_optimize_mask_verifier_overlay(image_bgr: np.ndarray, labels: list[dict[str, Any]]) -> np.ndarray:
    return _auto_optimization_mask_visuals.auto_optimize_mask_verifier_overlay(image_bgr, labels)

def auto_optimize_mask_verifier_crop(image_bgr: np.ndarray, label: dict[str, Any]) -> np.ndarray | None:
    return _auto_optimization_mask_visuals.auto_optimize_mask_verifier_crop(image_bgr, label)

def clamp_unit_score(value: Any, default: float=0.0) -> float:
    return _auto_optimization_mask_visuals.clamp_unit_score(value, default)

def verify_auto_optimize_mask_sample(sample: dict[str, Any], image_bgr: np.ndarray, labels: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    return _auto_optimization_mask_verification.verify_auto_optimize_mask_sample(sample, image_bgr, labels)

def auto_optimize_write_sprite_artifact(*, image_bgr: np.ndarray, full_mask: np.ndarray, bbox: list[int], sample_id: str, accessory_id: str, label_name: str, artifact_dir: Path, source_image_path: Path) -> dict[str, Any]:
    return _auto_optimization_sprite_publication.auto_optimize_write_sprite_artifact(image_bgr=image_bgr, full_mask=full_mask, bbox=bbox, sample_id=sample_id, accessory_id=accessory_id, label_name=label_name, artifact_dir=artifact_dir, source_image_path=source_image_path)

def auto_optimize_generate_labels_for_sample(sample: dict[str, Any], provider_settings: dict[str, Any], model: str, artifact_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    return _auto_optimization_label_generation.auto_optimize_generate_labels_for_sample(sample, provider_settings, model, artifact_dir)

def auto_optimize_generate_label_for_candidate(sample: dict[str, Any], candidate: dict[str, Any], provider_settings: dict[str, Any], model: str, artifact_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    return _auto_optimization_label_generation.auto_optimize_generate_label_for_candidate(sample, candidate, provider_settings, model, artifact_dir)

def start_auto_optimize_label_worker(task_id: str) -> None:
    return _auto_optimization_label_processing.start_auto_optimize_label_worker(task_id)

def auto_optimize_process_label_sample(task_id: str, pending: dict[str, Any], provider_settings: dict[str, Any], model: str) -> dict[str, Any]:
    return _auto_optimization_label_processing.auto_optimize_process_label_sample(task_id, pending, provider_settings, model)

@pinned_model_profiles(resolve_model_profiles, lambda identity: load_auto_optimize_state(identity))
def auto_optimize_label_worker(task_id: str) -> None:
    return _auto_optimization_label_processing.auto_optimize_label_worker(task_id)

def maybe_start_auto_optimize_training_locked(state: dict[str, Any]) -> None:
    return _auto_optimization_training_scheduling.maybe_start_auto_optimize_training_locked(state)

@pinned_model_profiles(resolve_model_profiles, lambda identity: load_auto_optimize_state(identity))
def auto_optimize_training_check_worker(task_id: str, delay_seconds: float=0.0) -> None:
    return _auto_optimization_training_scheduling.auto_optimize_training_check_worker(task_id, delay_seconds)

def start_auto_optimize_training_check_worker(task_id: str, delay_seconds: float=0.0) -> None:
    return _auto_optimization_training_scheduling.start_auto_optimize_training_check_worker(task_id, delay_seconds)

def auto_optimize_load_sprite(sprite: dict[str, Any]) -> tuple[np.ndarray, np.ndarray] | None:
    return _auto_optimization_sprites.auto_optimize_load_sprite(sprite)

def auto_optimize_sprite_records_for_sample(sample: dict[str, Any]) -> list[dict[str, Any]]:
    return _auto_optimization_sprites.auto_optimize_sprite_records_for_sample(sample)

def auto_optimize_resolve_artifact_path(value: Any) -> Path:
    return _auto_optimization_sprites.auto_optimize_resolve_artifact_path(value)

def auto_optimize_backfill_missing_sprites_for_sample(task_id: str, state: dict[str, Any], sample: dict[str, Any]) -> int:
    return _auto_optimization_sprites.auto_optimize_backfill_missing_sprites_for_sample(task_id, state, sample)

def auto_optimize_public_sprite_pool(state: dict[str, Any], limit: int=80) -> list[dict[str, Any]]:
    return _auto_optimization_sprites.auto_optimize_public_sprite_pool(state, limit)

def auto_optimize_sprite_visible_size(sprite_mask: np.ndarray) -> tuple[int, int] | None:
    return _auto_optimization_sprites.auto_optimize_sprite_visible_size(sprite_mask)

def auto_optimize_source_to_canvas_scale(source_path_value: Any, cache: dict[str, float]) -> float:
    return _auto_optimization_sprites.auto_optimize_source_to_canvas_scale(source_path_value, cache)

def auto_optimize_canonical_sprite_sizes(state: dict[str, Any], extra_sprites: list[dict[str, Any]] | None=None) -> dict[str, dict[str, int]]:
    return _auto_optimization_sprites.auto_optimize_canonical_sprite_sizes(state, extra_sprites)

def auto_optimize_sprite_target_size(sprite_mask: np.ndarray, canonical_size: dict[str, int] | None=None) -> tuple[int, int]:
    return _auto_optimization_sprites.auto_optimize_sprite_target_size(sprite_mask, canonical_size)

def auto_optimize_render_synthetic_sample(*, sprites: list[dict[str, Any]], class_index: dict[str, int], accessories_by_id: dict[str, dict[str, Any]], output_path: Path, label_path: Path, annotated_path: Path, split: str, rng: np.random.Generator, canonical_sizes: dict[str, dict[str, int]] | None=None, background_set_id: str | None=None) -> dict[str, Any] | None:
    return _auto_optimization_rendering.auto_optimize_render_synthetic_sample(sprites=sprites, class_index=class_index, accessories_by_id=accessories_by_id, output_path=output_path, label_path=label_path, annotated_path=annotated_path, split=split, rng=rng, canonical_sizes=canonical_sizes, background_set_id=background_set_id)

def auto_optimize_generate_synthetic_batch_for_sample(task_id: str, state: dict[str, Any], sample: dict[str, Any]) -> list[dict[str, Any]]:
    return _auto_optimization_synthetic_batch.auto_optimize_generate_synthetic_batch_for_sample(task_id, state, sample)

def auto_optimize_bbox_training_entries(sample: dict[str, Any]) -> list[dict[str, Any]]:
    return _auto_optimization_dataset.auto_optimize_bbox_training_entries(sample)

def build_auto_optimize_dataset(task_id: str, state: dict[str, Any], samples: list[dict[str, Any]]) -> dict[str, Any] | None:
    return _auto_optimization_dataset.build_auto_optimize_dataset(task_id, state, samples)

def start_auto_optimize_shadow_worker(task_id: str, sample_id: str) -> None:
    return _auto_optimization_shadow_evaluation.start_auto_optimize_shadow_worker(task_id, sample_id)

@pinned_model_profiles(resolve_model_profiles, lambda identity: load_auto_optimize_state(identity))
def auto_optimize_shadow_worker(task_id: str, sample_id: str) -> None:
    return _auto_optimization_shadow_evaluation.auto_optimize_shadow_worker(task_id, sample_id)

def maybe_promote_auto_optimize_model_locked(state: dict[str, Any]) -> None:
    return _auto_optimization_shadow_evaluation.maybe_promote_auto_optimize_model_locked(state)

def cleanup_auto_optimize_retired_candidate_locked(state: dict[str, Any], model_id: str, *, keep_model_id: str) -> None:
    return _auto_optimization_shadow_evaluation.cleanup_auto_optimize_retired_candidate_locked(state, model_id, keep_model_id=keep_model_id)

def agent_mcp_pose_reference_assets(item: dict[str, Any]) -> list[dict[str, Any]]:
    return _agent_pose_assets.agent_mcp_pose_reference_assets(item)

def agent_mcp_accessory_pose_images_exist(item: dict[str, Any]) -> bool:
    return _agent_pose_assets.agent_mcp_accessory_pose_images_exist(item)

def dedup_agent_mcp_pose_references(item: dict[str, Any]) -> bool:
    return _pose_sprite_builder.dedup_agent_mcp_pose_references(item)

def agent_mcp_accessory_standard_images_ready(item: dict[str, Any]) -> bool:
    return _agent_pose_assets.agent_mcp_accessory_standard_images_ready(item)

def agent_mcp_clean_sprites_need_rebuild(item: dict[str, Any]) -> bool:
    return _agent_pose_assets.agent_mcp_clean_sprites_need_rebuild(item)

def accessory_sprite_version(item: dict[str, Any]) -> str:
    return _training_preview_cache.accessory_sprite_version(item)

def preview_cache_key(selected: list[dict[str, Any]]) -> str:
    return _training_preview_cache.preview_cache_key(selected)

def training_preview_metadata_missing(training: dict[str, Any], selected: list[dict[str, Any]]) -> bool:
    return _training_preview_cache.training_preview_metadata_missing(training, selected)

def training_task_path(task_id: str) -> Path:
    return _training_state_workflows.training_task_path(task_id)

def load_training_task_records() -> list[dict[str, Any]]:
    return _training_state_workflows.load_training_task_records()

def save_training_task(task: dict[str, Any]) -> None:
    return _training_state_workflows.save_training_task(task)

def load_training_task(path: Path) -> dict[str, Any] | None:
    return _training_state_workflows.load_training_task(path)

def find_training_task(job_id: str) -> dict[str, Any] | None:
    return _training_state_workflows.find_training_task(job_id)

def local_training_task_is_active(task: dict[str, Any]) -> bool:
    return _training_state_workflows.local_training_task_is_active(task)

def refresh_interrupted_local_training_task(task: dict[str, Any]) -> dict[str, Any]:
    return _training_state_workflows.refresh_interrupted_local_training_task(task)

def public_refreshed_training_task(task: dict[str, Any], *, allow_remote_refresh: bool=False) -> dict[str, Any]:
    return _training_state_workflows.public_refreshed_training_task(task, allow_remote_refresh=allow_remote_refresh)

def list_training_tasks(user: dict[str, Any] | None=None, target_user_id: str | None=None, *, allow_remote_refresh: bool=False) -> list[dict[str, Any]]:
    return _training_state_workflows.list_training_tasks(user, target_user_id, allow_remote_refresh=allow_remote_refresh)

def public_training_task(task: dict[str, Any]) -> dict[str, Any]:
    return _training_state_workflows.public_training_task(task)

def update_training_task(job_id: str, **updates: Any) -> dict[str, Any]:
    return _training_state_workflows.update_training_task(job_id, **updates)

def stop_training_task_process(task: dict[str, Any], *, note: str) -> dict[str, Any]:
    return _training_state_workflows.stop_training_task_process(task, note=note)

def delete_training_task_record(job_id: str, user: dict[str, Any], *, missing_ok: bool=False) -> dict[str, Any] | None:
    return _training_state_workflows.delete_training_task_record(job_id, user, missing_ok=missing_ok)

def ensure_object_clean_sprites_for_selection(config: dict[str, Any], ids: list[str]) -> bool:
    return _training_asset_preparation.ensure_object_clean_sprites_for_selection(config, ids)

def ensure_training_normalized_assets_for_selection(config: dict[str, Any], ids: list[str]) -> bool:
    return _training_asset_preparation.ensure_training_normalized_assets_for_selection(config, ids)

def ensure_training_assets_for_request(full_config: dict[str, Any], scoped_config: dict[str, Any], user: dict[str, Any], ids: list[str]) -> bool:
    return _training_asset_preparation.ensure_training_assets_for_request(full_config, scoped_config, user, ids)

def random_center_inside_background(rng: np.random.Generator, target_size: tuple[int, int], angle: float, roi: tuple[int, int, int, int]=BACKGROUND_ROI_PX) -> tuple[int, int]:
    return _preview_placement.random_center_inside_background(rng, target_size, angle, roi)

def object_placement_overlap_area(center: tuple[int, int], target_size: tuple[int, int], angle: float, placed_objects: list[dict[str, Any]]) -> float:
    return _preview_placement.object_placement_overlap_area(center, target_size, angle, placed_objects)

def choose_object_center_inside_background(rng: np.random.Generator, target_size: tuple[int, int], angle: float, placed_objects: list[dict[str, Any]], roi: tuple[int, int, int, int]=BACKGROUND_ROI_PX) -> tuple[tuple[int, int], dict[str, Any]]:
    return _preview_placement.choose_object_center_inside_background(rng, target_size, angle, placed_objects, roi)

def placement_box_points(center: tuple[int, int], target_size: tuple[int, int], angle: float) -> list[list[int]]:
    return _preview_placement.placement_box_points(center, target_size, angle)

def visible_polygons_from_mask(mask: np.ndarray, epsilon_ratio: float=0.0035) -> list[list[list[int]]]:
    return _preview_masks.visible_polygons_from_mask(mask, epsilon_ratio)

def visible_polygon_from_mask(mask: np.ndarray, epsilon_ratio: float=0.0035) -> list[list[int]]:
    return _preview_masks.visible_polygon_from_mask(mask, epsilon_ratio)

def load_training_background_manifest() -> dict[str, Any]:
    return _training_background_library.load_training_background_manifest()

def load_background_sets_manifest() -> dict[str, Any]:
    return _background_manifest.load_background_sets_manifest()

def write_background_sets_manifest(manifest: dict[str, Any]) -> None:
    return _background_manifest.write_background_sets_manifest(manifest)

def image_file_list(path: Path) -> list[Path]:
    return _background_image_files.image_file_list(path)

def seed_default_background_set() -> None:
    return _background_seeding.seed_default_background_set()

def background_set_dirs() -> list[Path]:
    return _background_seeding.background_set_dirs()

def background_set_payload(set_id: str, meta: dict[str, Any] | None=None) -> dict[str, Any]:
    return _background_catalog.background_set_payload(set_id, meta)

def list_background_sets(user: dict[str, Any] | None=None, target_user_id: str | None=None) -> list[dict[str, Any]]:
    return _background_catalog.list_background_sets(user, target_user_id)

def selected_background_set_id(background_set_id: str | None, user: dict[str, Any] | None=None, target_user_id: str | None=None) -> str | None:
    return _background_selection.selected_background_set_id(background_set_id, user, target_user_id)

def background_set_image_files(background_set_id: str | None) -> list[Path]:
    return _background_selection.background_set_image_files(background_set_id)

def create_background_variants_from_source(source_path: Path, set_dir: Path, count: int=5) -> list[Path]:
    return _background_variants.create_background_variants_from_source(source_path, set_dir, count)

def run_codex_background_generation(source_path: Path, set_dir: Path, set_id: str, count: int=5) -> list[Path]:
    return _background_codex_generation.run_codex_background_generation(source_path, set_dir, set_id, count)

def start_codex_background_generation(source_path: Path, set_dir: Path, set_id: str, count: int=5) -> None:
    return _background_codex_thread.start_codex_background_generation(source_path, set_dir, set_id, count)

def ensure_background_set_minimum_images(set_id: str, min_count: int=6) -> None:
    return _background_minimum_images.ensure_background_set_minimum_images(set_id, min_count)

def unique_background_set_id(base_id: str) -> str:
    return _background_writes.unique_background_set_id(base_id)

def update_background_set_manifest(set_id: str, **updates: Any) -> dict[str, Any]:
    return _background_writes.update_background_set_manifest(set_id, **updates)

def save_task_environment_background_set(task_id: str, source_path: Path, user: dict[str, Any], display_name: str='') -> dict[str, Any]:
    return _task_background_store.save_task_environment_background_set(task_id, source_path, user, display_name)

def validate_task_environment_background_image(task_id: str, task: dict[str, Any], source_path: Path) -> dict[str, Any]:
    return _background_validation.validate_task_environment_background_image(task_id, task, source_path)

def run_background_set_task(job_id: str) -> None:
    return _background_task_runner.run_background_set_task(job_id)

def enqueue_background_set_task(set_id: str, name: str, source_path: Path) -> dict[str, Any]:
    return _background_task_submission.enqueue_background_set_task(set_id, name, source_path)

def training_background_library(background_set_id: str | None=None) -> list[dict[str, Any]]:
    return _training_background_library.training_background_library(background_set_id)

def render_training_background(rng: np.random.Generator, split: str | None=None, background_set_id: str | None=None) -> tuple[np.ndarray, dict[str, Any]]:
    return _training_background_renderer.render_training_background(rng, split, background_set_id)

def draw_training_preview(accessories: list[dict[str, Any]], output_path: Path, seed: int, pose_family_policy: str | None=None, split: str | None=None, background_set_id: str | None=None) -> dict[str, Any]:
    return _training_preview_renderer.draw_training_preview(accessories, output_path, seed, pose_family_policy, split, background_set_id)

def build_training_sample_plan(selected: list[dict[str, Any]], sample_count: int, seed: int, pose_policy: str) -> list[dict[str, Any]]:
    return _training_sample_planner.build_training_sample_plan(selected, sample_count, seed, pose_policy)

def public_training_output_url(path: Path) -> str:
    return _training_output_links.public_training_output_url(path)

def write_training_annotation_preview(image_path: Path, labels: list[dict[str, Any]], out_path: Path) -> str:
    return _training_annotation_preview.write_training_annotation_preview(image_path, labels, out_path)

def generate_training_dataset(task: dict[str, Any]) -> dict[str, Any]:
    return _training_dataset_generator.generate_training_dataset(task)

def training_executor_mode() -> str:
    return _training_executor_settings.training_executor_mode()

def worker_local_training_fallback_enabled() -> bool:
    return _training_executor_settings.worker_local_training_fallback_enabled()

def validate_remote_training_endpoint(value: Any) -> str:
    return _training_executor_settings.validate_remote_training_endpoint(value)

def validate_windows_worker_base_url(value: Any) -> str:
    return _training_executor_settings.validate_windows_worker_base_url(value)

def remote_training_endpoint() -> str:
    return _training_executor_settings.remote_training_endpoint()

def windows_worker_base_url() -> str:
    return _training_executor_settings.windows_worker_base_url()

def remote_training_timeout_seconds() -> float:
    return _training_executor_settings.remote_training_timeout_seconds()

def windows_worker_timeout_seconds() -> float:
    return _training_executor_settings.windows_worker_timeout_seconds()

def windows_worker_image_timeout_seconds() -> float:
    return _training_executor_settings.windows_worker_image_timeout_seconds()

def windows_worker_headers() -> dict[str, str]:
    return _training_executor_settings.windows_worker_headers()

def windows_worker_request(method: str, path: str, *, json_body: dict[str, Any] | None=None, timeout_seconds: float | None=None) -> dict[str, Any]:
    return _legacy_worker_requests.windows_worker_request(method, path, json_body=json_body, timeout_seconds=timeout_seconds)

def windows_worker_form_request(method: str, path: str, *, data: dict[str, Any] | None=None, files: dict[str, Any] | None=None, timeout_seconds: float | None=None) -> dict[str, Any]:
    return _legacy_worker_requests.windows_worker_form_request(method, path, data=data, files=files, timeout_seconds=timeout_seconds)

def training_execution_status(*, include_worker_probe: bool=False, include_worker_services: bool=False) -> dict[str, Any]:
    return _training_executor_settings.training_execution_status(include_worker_probe=include_worker_probe, include_worker_services=include_worker_services)

def package_training_dataset(dataset_dir: Path, job_id: str) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    return _training_dataset_archives.package_training_dataset(dataset_dir, job_id)

def build_worker_training_bundle(dataset_dir: Path, job_id: str) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    return _training_dataset_archives.build_worker_training_bundle(dataset_dir, job_id)

def dataset_file_manifest(dataset_dir: Path) -> list[dict[str, Any]]:
    return _training_dataset_archives.dataset_file_manifest(dataset_dir)

def worker_training_bundle_metadata(job_id: str, task: dict[str, Any], dataset: dict[str, Any], dataset_dir: Path, archive_path: Path) -> dict[str, Any]:
    return _worker_bundle_metadata.worker_training_bundle_metadata(job_id, task, dataset, dataset_dir, archive_path)

def worker_training_upload_timeout_seconds() -> float:
    return _worker_bundle_timeout.worker_training_upload_timeout_seconds()

def windows_worker_upload_bundle_streamed(path: str, *, metadata_json: str, archive_path: Path, state: dict[str, int], timeout_seconds: float) -> dict[str, Any]:
    return _worker_transfers.windows_worker_upload_bundle_streamed(path, metadata_json=metadata_json, archive_path=archive_path, state=state, timeout_seconds=timeout_seconds)

def post_worker_training_bundle(job_id: str, task: dict[str, Any], dataset: dict[str, Any]) -> dict[str, Any]:
    return _worker_bundle_submission.post_worker_training_bundle(job_id, task, dataset)

def run_remote_training_task(job_id: str, task: dict[str, Any], dataset: dict[str, Any]) -> None:
    return _remote_training.run_remote_training_task(job_id, task, dataset)

def runpod_yolo_endpoint_id() -> str:
    return _training_executor_settings.runpod_yolo_endpoint_id()

def runpod_yolo_api_key() -> str:
    return _training_executor_settings.runpod_yolo_api_key()

def runpod_yolo_api_base() -> str:
    return _training_executor_settings.runpod_yolo_api_base()

def runpod_yolo_public_base_url() -> str:
    return _training_executor_settings.runpod_yolo_public_base_url()

def runpod_yolo_job_timeout_seconds() -> int:
    return _training_executor_settings.runpod_yolo_job_timeout_seconds()

def runpod_yolo_client_timeout_seconds() -> float:
    return _training_executor_settings.runpod_yolo_client_timeout_seconds()

def runpod_yolo_poll_interval_seconds() -> float:
    return _training_executor_settings.runpod_yolo_poll_interval_seconds()

def runpod_yolo_dataset_token_ttl_seconds() -> int:
    return _training_executor_settings.runpod_yolo_dataset_token_ttl_seconds()

def runpod_yolo_inline_dataset_max_bytes() -> int:
    return _training_executor_settings.runpod_yolo_inline_dataset_max_bytes()

def runpod_yolo_artifact_max_bytes() -> int:
    return _training_executor_settings.runpod_yolo_artifact_max_bytes()

def runpod_yolo_url(path: str) -> str:
    return _training_executor_settings.runpod_yolo_url(path)

def runpod_yolo_authorization_values() -> list[str]:
    return _training_executor_settings.runpod_yolo_authorization_values()

def runpod_yolo_http_request(method: str, path: str, *, json_body: dict[str, Any] | None=None, timeout_seconds: float | None=None) -> dict[str, Any]:
    return _runpod_client.runpod_yolo_http_request(method, path, json_body=json_body, timeout_seconds=timeout_seconds)

def runpod_public_response_summary(value: Any) -> Any:
    return _runpod_client.runpod_public_response_summary(value)

def create_runpod_training_dataset_archive(job_id: str, task: dict[str, Any], dataset: dict[str, Any]) -> dict[str, Any]:
    return _runpod_exports.create_runpod_training_dataset_archive(job_id, task, dataset)

def create_runpod_training_artifact_upload(job_id: str, task: dict[str, Any]) -> dict[str, Any]:
    return _runpod_exports.create_runpod_training_artifact_upload(job_id, task)

def runpod_training_input_payload(job_id: str, task: dict[str, Any], archive: dict[str, Any]) -> dict[str, Any]:
    return _runpod_payload.runpod_training_input_payload(job_id, task, archive)

def submit_runpod_yolo_training(payload: dict[str, Any]) -> dict[str, Any]:
    return _runpod_submission.submit_runpod_yolo_training(payload)

def extract_runpod_worker_output(status_body: dict[str, Any]) -> dict[str, Any]:
    return _runpod_output_parser.extract_runpod_worker_output(status_body)

def import_runpod_yolo_artifacts(task: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    return _runpod_artifacts.import_runpod_yolo_artifacts(task, output)

def run_runpod_training_task(job_id: str, task: dict[str, Any], dataset: dict[str, Any]) -> None:
    return _runpod_flow.run_runpod_training_task(job_id, task, dataset)

def run_worker_dataset_generation_task(job_id: str, task: dict[str, Any]) -> None:
    return _legacy_worker_tasks.run_worker_dataset_generation_task(job_id, task)

def run_worker_training_task(job_id: str, task: dict[str, Any], dataset: dict[str, Any] | None=None) -> None:
    return _legacy_worker_tasks.run_worker_training_task(job_id, task, dataset)

def worker_training_artifact_summary(item: dict[str, Any]) -> dict[str, Any]:
    return _worker_artifact_summary.worker_training_artifact_summary(item)

def import_worker_training_artifacts(task: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    return _worker_artifact_import.import_worker_training_artifacts(task, artifacts)

def _start_transfer_progress_thread(job_id: str, state: dict[str, int], *, done_field: str, total_field: str, status_field: str, interval: float=1.5) -> tuple[threading.Event, threading.Thread]:
    return _transfer_progress._start_transfer_progress_thread(job_id, state, done_field=done_field, total_field=total_field, status_field=status_field, interval=interval)

def windows_worker_get_json_streamed(path: str, *, state: dict[str, int], timeout_seconds: float) -> dict[str, Any]:
    return _worker_transfers.windows_worker_get_json_streamed(path, state=state, timeout_seconds=timeout_seconds)

def refresh_worker_training_task(task: dict[str, Any], *, include_artifacts: bool=False) -> dict[str, Any]:
    return _legacy_worker_refresh.refresh_worker_training_task(task, include_artifacts=include_artifacts)

def windows_worker_request_with_retry(method: str, path: str, *, json_body: dict[str, Any] | None=None, timeout_seconds: float | None=None, attempts: int=3, backoff_seconds: float=4.0) -> dict[str, Any]:
    return _legacy_worker_requests.windows_worker_request_with_retry(method, path, json_body=json_body, timeout_seconds=timeout_seconds, attempts=attempts, backoff_seconds=backoff_seconds)

def worker_training_watcher_interval_seconds() -> float:
    return _worker_watcher_settings.worker_training_watcher_interval_seconds()

def _worker_training_watcher_loop() -> None:
    return _worker_watcher_loop._worker_training_watcher_loop()

def run_training_task(job_id: str) -> None:
    return _training_execution.run_training_task(job_id)

def enqueue_training_task(request: TrainingStartRequest, selected: list[dict[str, Any]], action: str, dataset: dict[str, Any] | None=None) -> dict[str, Any]:
    return _training_execution.enqueue_training_task(request, selected, action, dataset)

def training_task_finder() -> Callable[[Path], dict[str, Any] | None]:
    return _training_task_lookup.training_task_finder()

def pipeline_task_link_for_training_run(run_id: str, tasks: list[dict[str, Any]] | None=None) -> dict[str, str]:
    return _training_links.pipeline_task_link_for_training_run(run_id, tasks)

def list_trained_model_specs(config: dict[str, Any] | None=None) -> list[dict[str, Any]]:
    return _trained_model_catalog.list_trained_model_specs(config)

def selected_model_spec(model_id: str | None, config: dict[str, Any] | None=None) -> dict[str, Any]:
    return _model_selection.selected_model_spec(model_id, config)

def model(model_id: str | None=None, config: dict[str, Any] | None=None) -> YOLO:
    return _local_models.model(model_id, config)

def yolo_loaded_model_ids(config: dict[str, Any]) -> list[str]:
    return _local_models.yolo_loaded_model_ids(config)

def yolo_model_ready(model_id: str, config: dict[str, Any]) -> bool:
    return _local_models.yolo_model_ready(model_id, config)

def save_pipeline_task_batch_changes(tasks: list[dict[str, Any]], changed_tasks: list[dict[str, Any]]) -> None:
    return _pipeline_task_mutations.save_pipeline_task_batch_changes(tasks, changed_tasks)

def mark_pipeline_ai_task_deleted(ai_task_id: str, user: dict[str, Any]) -> int:
    return _pipeline_task_mutations.mark_pipeline_ai_task_deleted(ai_task_id, user)

def _freeze_real_photo_original(user, data, sha):
    return _real_photo_workflows.freeze_original(user, data, sha)

def _disable_legacy_feedback_for_real_photo(task_id):
    return _real_photo_workflows.disable_legacy(task_id)

def _real_photo_training_metadata(job):
    return _real_photo_workflows.training_metadata(job)

def _submit_real_photo_training(job, dataset):
    return _real_photo_workflows.submit_training(job, dataset)

def dataset_for_training(dataset_id: str, user: dict[str, Any] | None=None) -> dict[str, Any]:
    return _training_task_workflows.dataset_for_training(dataset_id, user)

def validate_approved_preview(config: dict[str, Any], request: TrainingStartRequest, selected: list[dict[str, Any]], user: dict[str, Any] | None=None) -> None:
    return _training_task_workflows.validate_approved_preview(config, request, selected, user)

def filtered_training_state(config: dict[str, Any], user: dict[str, Any] | None=None, target_user_id: str | None=None) -> dict[str, Any]:
    return _training_task_workflows.filtered_training_state(config, user, target_user_id)

def dataset_resource_item(dataset_dir: Path, *, include_samples: bool=True) -> dict[str, Any] | None:
    return _dataset_catalog.dataset_resource_item(dataset_dir, include_samples=include_samples)

def training_task_dataset_resource_id(task: dict[str, Any]) -> str:
    return _dataset_catalog.training_task_dataset_resource_id(task)

def find_dataset_resource(dataset_id: str, user: dict[str, Any] | None=None, *, include_samples: bool=False, write: bool=False) -> tuple[Path | None, dict[str, Any] | None]:
    return _dataset_catalog.find_dataset_resource(dataset_id, user, include_samples=include_samples, write=write)

def training_dataset_roots() -> list[Path]:
    return _dataset_catalog.training_dataset_roots()

def training_run_roots() -> list[Path]:
    return _dataset_catalog.training_run_roots()

def training_resources_payload(*, include_samples: bool=False, user: dict[str, Any] | None=None, target_user_id: str | None=None) -> dict[str, Any]:
    return _training_resources.training_resources_payload(include_samples=include_samples, user=user, target_user_id=target_user_id)

def delete_training_dataset_resource(dataset_id: str, user: dict[str, Any], *, missing_ok: bool=False) -> dict[str, Any] | None:
    return _training_resource_mutations.delete_training_dataset_resource(dataset_id, user, missing_ok=missing_ok)

def mark_pipeline_dataset_deleted(dataset_id: str, user: dict[str, Any]) -> int:
    return _pipeline_resource_links.mark_pipeline_dataset_deleted(dataset_id, user)

def mark_training_task_dataset_deleted(dataset_id: str, user: dict[str, Any]) -> int:
    return _training_dataset_links.mark_training_task_dataset_deleted(dataset_id, user)

def delete_training_model_resource(run_id: str, user: dict[str, Any], *, missing_ok: bool=False) -> dict[str, Any] | None:
    return _training_resource_mutations.delete_training_model_resource(run_id, user, missing_ok=missing_ok)

def mark_pipeline_model_deleted(run_id: str, user: dict[str, Any]) -> int:
    return _pipeline_resource_links.mark_pipeline_model_deleted(run_id, user)

def agent_required_fields_present(config: dict[str, Any]) -> bool:
    return _agent_settings_projection.agent_required_fields_present(config)

def agent_credentials_present(config: dict[str, Any]) -> bool:
    return _agent_settings_projection.agent_credentials_present(config)

def agent_connected(config: dict[str, Any]) -> bool:
    return _agent_settings_projection.agent_connected(config)

def agent_recommendation_supported(config: dict[str, Any]) -> bool:
    return _agent_settings_projection.agent_recommendation_supported(config)

def agent_configured(config: dict[str, Any] | None=None) -> bool:
    return _agent_settings_projection.agent_configured(config)

def public_agent_config(config: dict[str, Any] | None=None) -> dict[str, Any]:
    return _agent_settings_projection.public_agent_config(config)

def openai_compatible_chat_url(base_url: str) -> str:
    return _agent_protocol_policy.openai_compatible_chat_url(base_url)

def openai_compatible_models_url(base_url: str) -> str:
    return _agent_protocol_policy.openai_compatible_models_url(base_url)

def agent_http_error_message(prefix: str, exc: urllib.error.HTTPError) -> str:
    return _agent_chat_transport.agent_http_error_message(prefix, exc)

def agent_openai_chat_completion(messages: list[dict[str, str]], config: dict[str, Any] | None=None, *, require_connected: bool=True) -> str:
    return _agent_chat_transport.agent_openai_chat_completion(messages, config, require_connected=require_connected)

def agent_chat_completion(messages: list[dict[str, str]], config: dict[str, Any] | None=None) -> str:
    return _agent_chat_transport.agent_chat_completion(messages, config)

def cursor_auth_headers(api_key: str) -> dict[str, str]:
    return _agent_protocol_policy.cursor_auth_headers(api_key)

def cursor_api_url(base_url: str, path: str) -> str:
    return _agent_protocol_policy.cursor_api_url(base_url, path)

def cursor_model_available(model: str, items: list[dict[str, Any]]) -> bool:
    return _agent_protocol_policy.cursor_model_available(model, items)

def fetch_openai_compatible_model_options(config: dict[str, Any]) -> list[dict[str, str]]:
    return _agent_connection_discovery.fetch_openai_compatible_model_options(config)

def test_cursor_agent_connection(config: dict[str, Any]) -> dict[str, Any]:
    return _agent_connection_discovery.test_cursor_agent_connection(config)

def test_openai_agent_connection(config: dict[str, Any]) -> dict[str, Any]:
    return _agent_connection_discovery.test_openai_agent_connection(config)

def test_agent_connection(config: dict[str, Any]) -> dict[str, Any]:
    return _agent_connection_discovery.test_agent_connection(config)

def parse_agent_json(content: str) -> dict[str, Any]:
    return _agent_recommendation.parse_agent_json(content)

def rule_recommendation(stage: str, selected: list[dict[str, Any]], sample_count: int | None=None) -> dict[str, Any]:
    return _agent_recommendation.rule_recommendation(stage, selected, sample_count)

def clamp_recommend_params(stage: str, params: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    return _agent_recommendation.clamp_recommend_params(stage, params, fallback)

def agent_recommendation(stage: str, accessory_ids: list[str], sample_count: int | None=None) -> dict[str, Any]:
    return _agent_recommendation.agent_recommendation(stage, accessory_ids, sample_count)

def load_pipeline_tasks() -> list[dict[str, Any]]:
    return _pipeline_task_store.load_pipeline_tasks()

def save_pipeline_tasks(tasks: list[dict[str, Any]]) -> None:
    return _pipeline_task_store.save_pipeline_tasks(tasks)

def load_pipeline_task(task_id: str) -> dict[str, Any] | None:
    return _pipeline_task_store.load_pipeline_task(task_id)

def save_pipeline_task(task: dict[str, Any]) -> dict[str, Any] | None:
    return _pipeline_task_store.save_pipeline_task(task)

def delete_pipeline_task_row(task_id: str) -> bool:
    return _pipeline_task_store.delete_pipeline_task_row(task_id)

def mark_pipeline_task_advancing(task: dict[str, Any]) -> None:
    """Flag a task (in memory) as queued for the async advance runner. The caller
    persists it and then schedules the worker after releasing _pipeline_tasks_lock."""
    return _pipeline_task_mutations.mark_pipeline_task_advancing(task)

def persist_pipeline_task_progress(task_id: str, *, job_note: str | None=None, progress: int | None=None, status: str | None=None) -> None:
    """Write live sub-step progress to the stored task record so the UI reflects
    an in-flight advance immediately. Safe to call from the advance worker thread
    (it briefly takes _pipeline_tasks_lock); never call while already holding it."""
    return _pipeline_task_mutations.persist_pipeline_task_progress(task_id, job_note=job_note, progress=progress, status=status)

def normalize_pipeline_detection_method(value: str | None) -> str:
    return _pipeline_task_metadata.normalize_pipeline_detection_method(value)

def pipeline_method_uses_training(method: str | None) -> bool:
    return _pipeline_task_metadata.pipeline_method_uses_training(method)

def canonical_pipeline_accessory_ids(config: dict[str, Any], raw_ids: list[str]) -> list[str]:
    return _pipeline_candidate_flow.canonical_pipeline_accessory_ids(config, raw_ids)

def load_pipeline_state() -> dict[str, list[str]]:
    return _pipeline_state_store.load_pipeline_state()

def save_pipeline_state(state: dict[str, list[str]]) -> None:
    return _pipeline_state_store.save_pipeline_state(state)

def save_pipeline_state_keys(state: dict[str, list[str]], changed_keys: set[str]) -> None:
    return _pipeline_state_store.save_pipeline_state_keys(state, changed_keys)

def update_pipeline_state(mutator: Callable[[dict[str, list[str]]], None]) -> dict[str, list[str]]:
    return _pipeline_state_store.update_pipeline_state(mutator)

def add_pipeline_accessory_id(accessory_id: str) -> dict[str, list[str]]:
    return _pipeline_state_store.add_pipeline_accessory_id(accessory_id)

def remove_pipeline_accessory_id(accessory_id: str) -> dict[str, list[str]]:
    return _pipeline_state_store.remove_pipeline_accessory_id(accessory_id)

def add_pipeline_pending_candidate_id(candidate_id: str) -> dict[str, list[str]]:
    return _pipeline_state_store.add_pipeline_pending_candidate_id(candidate_id)

def remove_pipeline_pending_candidate_id(candidate_id: str) -> dict[str, list[str]]:
    return _pipeline_state_store.remove_pipeline_pending_candidate_id(candidate_id)

def candidate_confirmed_accessory_id(candidate: dict[str, Any]) -> str:
    return _pipeline_candidate_flow.candidate_confirmed_accessory_id(candidate)

def pipeline_candidate_job_status(candidate: dict[str, Any]) -> tuple[str, int, str]:
    return _pipeline_candidate_flow.pipeline_candidate_job_status(candidate)

def pipeline_candidate_public(candidate: dict[str, Any]) -> dict[str, Any]:
    return _pipeline_candidate_flow.pipeline_candidate_public(candidate)

def refresh_pipeline_candidate(candidate_id: str) -> tuple[dict[str, Any] | None, bool]:
    return _pipeline_candidate_flow.refresh_pipeline_candidate(candidate_id)

def pipeline_accessories_payload(config: dict[str, Any] | None=None, user: dict[str, Any] | None=None, target_user_id: str | None=None) -> dict[str, Any]:
    return _pipeline_candidate_flow.pipeline_accessories_payload(config, user, target_user_id)

def pipeline_task_label_snapshot(task: dict[str, Any]) -> dict[str, str]:
    return _pipeline_task_snapshots.pipeline_task_label_snapshot(task)

def pipeline_task_accessory_snapshot(config: dict[str, Any], task: dict[str, Any], accessory_ids: list[str]) -> tuple[dict[str, str], list[str]]:
    return _pipeline_task_snapshots.pipeline_task_accessory_snapshot(config, task, accessory_ids)

def ensure_pipeline_task_accessory_objects(config: dict[str, Any], tasks: list[dict[str, Any]]) -> bool:
    return _pipeline_task_metadata.ensure_pipeline_task_accessory_objects(config, tasks)

def pipeline_task_dataset_status(task: dict[str, Any]) -> str:
    return _pipeline_resource_status.pipeline_task_dataset_status(task)

def pipeline_task_model_status(task: dict[str, Any], *, ai_task_ids: set[str] | None=None, trained_model_specs: list[dict[str, Any]] | None=None) -> str:
    return _pipeline_resource_status.pipeline_task_model_status(task, ai_task_ids=ai_task_ids, trained_model_specs=trained_model_specs)

def fast_completed_auto_optimize_model_id(state: dict[str, Any]) -> str:
    return _auto_optimization_links.fast_completed_auto_optimize_model_id(state)

def public_auto_optimize_link_for_task_id(task_id: str, *, source: str, state: dict[str, Any] | None=None) -> dict[str, Any] | None:
    return _auto_optimization_links.public_auto_optimize_link_for_task_id(task_id, source=source, state=state)

def auto_optimize_states_by_task_id(states: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return _auto_optimization_links.auto_optimize_states_by_task_id(states)

def pipeline_task_auto_optimize_link(task: dict[str, Any], config: dict[str, Any], *, auto_optimize_states: list[dict[str, Any]] | None=None, auto_optimize_states_by_id: dict[str, dict[str, Any]] | None=None) -> dict[str, Any] | None:
    return _auto_optimization_links.pipeline_task_auto_optimize_link(task, config, auto_optimize_states=auto_optimize_states, auto_optimize_states_by_id=auto_optimize_states_by_id)

def pipeline_task_public(task: dict[str, Any], config: dict[str, Any], *, ai_task_ids: set[str] | None=None, trained_model_specs: list[dict[str, Any]] | None=None, auto_optimize_states: list[dict[str, Any]] | None=None, auto_optimize_states_by_id: dict[str, dict[str, Any]] | None=None, sanitize: bool=True) -> dict[str, Any]:
    return _task_projection.pipeline_task_public(task, config, ai_task_ids=ai_task_ids, trained_model_specs=trained_model_specs, auto_optimize_states=auto_optimize_states, auto_optimize_states_by_id=auto_optimize_states_by_id, sanitize=sanitize)

def normalize_pipeline_accessory_counts(config: dict[str, Any], accessory_ids: list[str], raw_counts: Any=None) -> dict[str, int]:
    return _pipeline_task_metadata.normalize_pipeline_accessory_counts(config, accessory_ids, raw_counts)

def agent_mcp_now() -> int:
    return _agent_orchestration_state.agent_mcp_now()

def agent_mcp_gemini_image_config() -> dict[str, Any]:
    return _pose_render_configuration.agent_mcp_gemini_image_config()

def agent_mcp_default_stages() -> list[dict[str, Any]]:
    return _agent_orchestration_state.agent_mcp_default_stages()

def agent_mcp_orchestration(task: dict[str, Any]) -> dict[str, Any]:
    return _agent_orchestration_state.agent_mcp_orchestration(task)

def set_agent_mcp_stage(orchestration: dict[str, Any], key: str, status: str, progress: int, **extra: Any) -> None:
    return _agent_orchestration_state.set_agent_mcp_stage(orchestration, key, status, progress, **extra)

def agent_mcp_object_kind(item: dict[str, Any]) -> str:
    return _agent_pose_templates.agent_mcp_object_kind(item)

def agent_mcp_pose_request() -> dict[str, Any]:
    return _agent_pose_templates.agent_mcp_pose_request()

def agent_mcp_pose_templates(base_id: str, object_kind: str) -> list[dict[str, Any]]:
    return _agent_pose_templates.agent_mcp_pose_templates(base_id, object_kind)

def accessory_pose_plan_prompt_payload(item: dict[str, Any]) -> dict[str, Any]:
    return _pose_plan_policy.accessory_pose_plan_prompt_payload(item)

def pose_plan_system_prompt() -> str:
    return _pose_plan_policy.pose_plan_system_prompt()

def fallback_accessory_pose_plan(item: dict[str, Any]) -> dict[str, Any]:
    return _pose_plan_policy.fallback_accessory_pose_plan(item)

def normalize_accessory_pose_plan(raw: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    return _pose_plan_policy.normalize_accessory_pose_plan(raw, item)

def generate_accessory_pose_plan(item: dict[str, Any], *, allow_provider: bool=True, force: bool=False) -> dict[str, Any] | None:
    return _pose_plan_generation.generate_accessory_pose_plan(item, allow_provider=allow_provider, force=force)

def ensure_accessory_pose_plan(item: dict[str, Any], *, force: bool=False) -> dict[str, Any] | None:
    return _pose_plan_generation.ensure_accessory_pose_plan(item, force=force)

def build_agent_mcp_pose_plan(task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return _pose_plan_assembly.build_agent_mcp_pose_plan(task, config)

def agent_mcp_tool_call_id(task_id: str, tool_name: str, accessory_id: str='', pose_id: str='') -> str:
    return _agent_tool_call_records.agent_mcp_tool_call_id(task_id, tool_name, accessory_id, pose_id)

def upsert_agent_mcp_tool_call(orchestration: dict[str, Any], call: dict[str, Any]) -> dict[str, Any]:
    return _agent_tool_call_records.upsert_agent_mcp_tool_call(orchestration, call)

def agent_mcp_pose_reference_content(item: dict[str, Any], *, max_images: int=3) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _pose_render_content.agent_mcp_pose_reference_content(item, max_images=max_images)

def agent_mcp_pose_prompt(task: dict[str, Any], plan: dict[str, Any], pose: dict[str, Any], chroma_screen: dict[str, Any] | None=None) -> str:
    return _pose_render_content.agent_mcp_pose_prompt(task, plan, pose, chroma_screen)

def agent_mcp_pose_output_path(task: dict[str, Any], accessory_id: str, pose_id: str, mime_type: str) -> Path:
    return _pose_artifact_store.agent_mcp_pose_output_path(task, accessory_id, pose_id, mime_type)

def write_agent_mcp_pose_artifact(task: dict[str, Any], call: dict[str, Any], result: dict[str, Any], *, prompt: str, reference_assets: list[dict[str, Any]]) -> dict[str, Any]:
    return _pose_artifact_store.write_agent_mcp_pose_artifact(task, call, result, prompt=prompt, reference_assets=reference_assets)

def segment_agent_mcp_pose_object(image_bgr: np.ndarray, rng: np.random.Generator, chroma_screen: dict[str, Any] | None=None) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    return _pose_cutout_pipeline.segment_agent_mcp_pose_object(image_bgr, rng, chroma_screen)

def object_photo_highlight_source_paths(item: dict[str, Any], *, limit: int=PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES) -> list[Path]:
    return _photo_highlight_sources.object_photo_highlight_source_paths(item, limit=limit)

def photo_highlight_clean_sprites_ready(item: dict[str, Any], source_paths: list[Path]) -> bool:
    return _photo_highlight_sources.photo_highlight_clean_sprites_ready(item, source_paths)

def pipeline_photo_highlight_object_items(task: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    return _photo_highlight_selection.pipeline_photo_highlight_object_items(task, config)

def mark_legacy_pose_flow_skipped_for_photo_highlight(task: dict[str, Any], config: dict[str, Any], orchestration: dict[str, Any]) -> dict[str, Any]:
    return _photo_highlight_workflow.mark_legacy_pose_flow_skipped_for_photo_highlight(task, config, orchestration)

def photo_highlight_mask_prompt(item: dict[str, Any]) -> str:
    return _photo_highlight_image_input.photo_highlight_mask_prompt(item)

def photo_highlight_input_data_url(image_bgr: np.ndarray) -> tuple[np.ndarray, str, float, float] | None:
    return _photo_highlight_image_input.photo_highlight_input_data_url(image_bgr)

def photo_highlight_auto_compare(ai_roi_mask: np.ndarray, auto_roi_mask: np.ndarray | None) -> dict[str, Any]:
    return _photo_highlight_comparison.photo_highlight_auto_compare(ai_roi_mask, auto_roi_mask)

def prepare_photo_highlight_sprites_for_task(task: dict[str, Any], config: dict[str, Any], orchestration: dict[str, Any]) -> tuple[bool, bool]:
    return _photo_highlight_workflow.prepare_photo_highlight_sprites_for_task(task, config, orchestration)

def build_clean_sprites_from_agent_mcp_poses(item: dict[str, Any], *, force: bool=False) -> bool:
    return _pose_sprite_builder.build_clean_sprites_from_agent_mcp_poses(item, force=force)

def materialize_agent_mcp_pose_assets(task: dict[str, Any], config: dict[str, Any]) -> bool:
    return _pose_asset_materialization.materialize_agent_mcp_pose_assets(task, config)

def agent_mcp_accessory_has_existing_or_pose_asset(item: dict[str, Any], orchestration: dict[str, Any]) -> bool:
    return _agent_pose_assets.agent_mcp_accessory_has_existing_or_pose_asset(item, orchestration)

def agent_mcp_missing_existing_asset_names(task: dict[str, Any], config: dict[str, Any], orchestration: dict[str, Any]) -> list[str]:
    return _agent_pose_assets.agent_mcp_missing_existing_asset_names(task, config, orchestration)

def execute_agent_mcp_pose_tool_calls(task: dict[str, Any], config: dict[str, Any]) -> bool:
    return _pose_call_execution.execute_agent_mcp_pose_tool_calls(task, config)

def ensure_agent_mcp_pose_plan(task: dict[str, Any], config: dict[str, Any], *, force: bool=False) -> dict[str, Any]:
    return _photo_highlight_workflow.ensure_agent_mcp_pose_plan(task, config, force=force)

def ensure_agent_mcp_pose_tool_calls(task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return _pose_call_registration.ensure_agent_mcp_pose_tool_calls(task, config)

def pause_agent_mcp_task(task: dict[str, Any], orchestration: dict[str, Any], *, stage: str, reason: str, suggested_actions: list[str]) -> None:
    return _agent_orchestration_state.pause_agent_mcp_task(task, orchestration, stage=stage, reason=reason, suggested_actions=suggested_actions)

def ensure_pipeline_background_plate(task: dict[str, Any], config: dict[str, Any]) -> str | None:
    """Select or generate a single strict top-down empty background plate for the
    task, register it as a per-task background set, and reuse it for both sprite
    preparation and sample-generation backgrounds."""
    return _pipeline_background_publication.ensure_pipeline_background_plate(task, config)

def prepare_agent_mcp_before_sample_generation(task: dict[str, Any], config: dict[str, Any]) -> bool:
    return _pose_sample_preparation.prepare_agent_mcp_before_sample_generation(task, config)

def log_agent_mcp_sample_tool_call(task: dict[str, Any], job: dict[str, Any]) -> None:
    return _agent_tool_call_records.log_agent_mcp_sample_tool_call(task, job)

def log_agent_mcp_training_tool_call(task: dict[str, Any], job: dict[str, Any]) -> None:
    return _agent_tool_call_records.log_agent_mcp_training_tool_call(task, job)

def agent_mcp_training_quality_gate(task: dict[str, Any]) -> bool:
    return _agent_orchestration_state.agent_mcp_training_quality_gate(task)

def upsert_pipeline_ai_detection_task(task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return _pipeline_ai_activation.upsert_pipeline_ai_detection_task(task, config)

def activate_pipeline_ai_detection_task(task: dict[str, Any], config: dict[str, Any]) -> bool:
    return _pipeline_ai_activation.activate_pipeline_ai_detection_task(task, config)

def pipeline_ai_task_id(ai_task_id: str) -> str:
    return _pipeline_ai_task_sync.pipeline_ai_task_id(ai_task_id)

def pipeline_ai_task_training_route(ai_task: dict[str, Any], config: dict[str, Any]) -> str:
    return _pipeline_ai_task_sync.pipeline_ai_task_training_route(ai_task, config)

def sync_pipeline_ai_detection_tasks(tasks: list[dict[str, Any]], config: dict[str, Any], user: dict[str, Any] | None, target_user_id: str | None=None, *, ai_tasks: list[dict[str, Any]] | None=None) -> bool:
    """Represent AI detection tasks as first-class pipeline tasks.

    These entries let the task pipeline show VLM-first tasks even before a YOLO
    model exists. They do not remove the original AI task; they keep a stable
    pipeline card linked to it so optimization/training state has one task home.
    """
    return _pipeline_ai_task_sync.sync_pipeline_ai_detection_tasks(tasks, config, user, target_user_id, ai_tasks=ai_tasks)

def normalize_pipeline_task_auto_advance_defaults(tasks: list[dict[str, Any]]) -> bool:
    return _pipeline_task_metadata.normalize_pipeline_task_auto_advance_defaults(tasks)

def linked_training_job(task: dict[str, Any], load_task: Callable[[Path], dict[str, Any] | None] | None=None) -> dict[str, Any] | None:
    return _pipeline_training_status.linked_training_job(task, load_task)

def sync_pipeline_task(task: dict[str, Any], load_task: Callable[[Path], dict[str, Any] | None] | None=None) -> bool:
    return _pipeline_training_status.sync_pipeline_task(task, load_task)

def link_pipeline_trained_model(task: dict[str, Any]) -> dict[str, Any] | None:
    """Link the freshly trained model to the pipeline task so the model library and
    detection workbench can use it immediately (transfer-back deployment path)."""
    return _pipeline_trained_model_link.link_pipeline_trained_model(task)

def advance_pipeline_task(task: dict[str, Any], cancel_event: 'threading.Event | None'=None) -> None:
    return _pipeline_stage_advancer.advance(task, cancel_event)

def agent_mcp_append_conversation(task: dict[str, Any], role: str, message: str, *, action: str='', reason: str='', target_stage: str='', source: str='', needs_user: bool=False, agent_error: str='') -> dict[str, Any]:
    return _agent_conversation.agent_mcp_append_conversation(task, role, message, action=action, reason=reason, target_stage=target_stage, source=source, needs_user=needs_user, agent_error=agent_error)

def agent_pipeline_quality_signals(task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return _agent_decision_context.agent_pipeline_quality_signals(task, config)

def agent_pipeline_context(task: dict[str, Any], config: dict[str, Any], user_message: str | None, trigger: str) -> dict[str, Any]:
    return _agent_decision_context.agent_pipeline_context(task, config, user_message, trigger)

def normalize_agent_pipeline_decision(parsed: dict[str, Any]) -> dict[str, Any]:
    return _agent_decision_policy.normalize_agent_pipeline_decision(parsed)

def _rule_rerun_failed_stage(stage: str) -> tuple[str, str]:
    return _agent_decision_policy._rule_rerun_failed_stage(stage)

def agent_pipeline_rule_decision(task: dict[str, Any], user_message: str | None, trigger: str) -> dict[str, Any]:
    return _agent_decision_policy.agent_pipeline_rule_decision(task, user_message, trigger)

@pinned_model_profiles(resolve_model_profiles)
def agent_pipeline_decide(task: dict[str, Any], config: dict[str, Any], *, user_message: str | None=None, trigger: str='chat') -> dict[str, Any]:
    return _agent_decision_flow.agent_pipeline_decide(task, config, user_message=user_message, trigger=trigger)

def agent_safe_advance(task: dict[str, Any], config: dict[str, Any], pending_advances: list[str] | None=None) -> None:
    return _agent_pipeline_actions.agent_safe_advance(task, config, pending_advances)

def reset_pipeline_task_to_stage(task: dict[str, Any], target: str, user: dict[str, Any] | None) -> None:
    return _agent_pipeline_actions.reset_pipeline_task_to_stage(task, target, user)

def apply_agent_pipeline_decision(task: dict[str, Any], config: dict[str, Any], decision: dict[str, Any], user: dict[str, Any] | None, *, trigger: str='chat', pending_advances: list[str] | None=None) -> None:
    return _agent_pipeline_actions.apply_agent_pipeline_decision(task, config, decision, user, trigger=trigger, pending_advances=pending_advances)

def commit_pipeline_agent_turn(task: dict[str, Any], config: dict[str, Any], user: dict[str, Any] | None, user_message: str | None, decision: dict[str, Any], trigger: str, pending_advances: list[str] | None=None) -> dict[str, Any]:
    return _agent_pipeline_turns.commit_pipeline_agent_turn(task, config, user, user_message, decision, trigger, pending_advances)

def pipeline_task_decision_signature(task: dict[str, Any]) -> str:
    return _pipeline_reconciliation.pipeline_task_decision_signature(task)

def pipeline_task_needs_auto_agent(task: dict[str, Any]) -> bool:
    return _pipeline_reconciliation.pipeline_task_needs_auto_agent(task)

@pinned_model_profiles(resolve_model_profiles, lambda identity: load_pipeline_task(identity))
def _run_pipeline_auto_agent_step(task_id: str, user: dict[str, Any] | None) -> None:
    _pipeline_auto_agent_runtime.run(task_id, user)

def schedule_pipeline_auto_agent(task_ids: list[str], user: dict[str, Any] | None) -> None:
    _pipeline_auto_agent_runtime.schedule(task_ids, user)

def advance_pipeline_task_guarded(task: dict[str, Any], config: dict[str, Any], cancel_event: 'threading.Event | None'=None) -> None:
    """Advance one stage, converting precondition/runtime failures into a paused
    state with a clear reason (mirrors the previous agent_safe_advance UX) so the
    async runner never crashes and the user always sees why a task stopped."""
    _pipeline_advance_runtime.guarded(task, config, cancel_event)

@pinned_model_profiles(resolve_model_profiles, lambda identity: load_pipeline_task(identity))
def _run_pipeline_advance(task_id: str, user: dict[str, Any] | None) -> None:
    _pipeline_advance_runtime.run(task_id, user)

def schedule_pipeline_advance(task_id: str, user: dict[str, Any] | None) -> bool:
    """Enqueue an async advance for a task. Idempotent: if a thread is already
    advancing this task, returns False without stacking a second one."""
    return _pipeline_advance_runtime.schedule(task_id, user)

def cancel_pipeline_advance(task_id: str) -> bool:
    """Signal a running advance worker to stop at the next checkpoint. Returns True
    if a worker was inflight."""
    return _pipeline_advance_runtime.cancel(task_id)

def pipeline_recommendation_signature(task: dict[str, Any], stage: str) -> str:
    return _pipeline_recommendations.pipeline_recommendation_signature(task, stage)

def pipeline_next_recommendation_stage(task: dict[str, Any]) -> str:
    """Which stage's params should be pre-computed so the next step is ready."""
    return _pipeline_recommendations.pipeline_next_recommendation_stage(task)

def pipeline_recommendation_ready(task: dict[str, Any], stage: str) -> bool:
    return _pipeline_recommendations.pipeline_recommendation_ready(task, stage)

def consume_pipeline_recommendation(task: dict[str, Any], stage: str) -> dict[str, Any] | None:
    """Return (and clear) the pre-generated params for a stage if present."""
    return _pipeline_recommendations.consume_pipeline_recommendation(task, stage)

@pinned_model_profiles(resolve_model_profiles, lambda identity: load_pipeline_task(identity))
def _run_pipeline_recommendation_pregen(task_id: str, stage: str, user: dict[str, Any] | None) -> None:
    _pipeline_recommendation_runtime.run(task_id, stage, user)

def schedule_pipeline_recommendation_pregen(items: list[tuple[str, str]], user: dict[str, Any] | None) -> None:
    _pipeline_recommendation_runtime.schedule(items, user)

def collect_pipeline_recommendation_pregen(tasks: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return _pipeline_recommendations.collect_pipeline_recommendation_pregen(tasks)

def reap_pipeline_advance_zombie(task: dict[str, Any]) -> bool:
    """Reset a task left in the advancing state with no live worker thread (e.g.
    the process restarted mid-advance) so the UI can distinguish working from
    timed-out and the user can retry. Returns True if the task was modified."""
    return _pipeline_reconciliation.reap_pipeline_advance_zombie(task)

def sync_and_auto_advance_pipeline(tasks: list[dict[str, Any]]) -> tuple[bool, list[str], list[str]]:
    return _pipeline_reconciliation.sync_and_auto_advance_pipeline(tasks)
