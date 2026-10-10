"""Historical default-only forwarders. Production business ports use owned graphs."""
from __future__ import annotations
from ..runtime.default_application import default_application as _application
import os
from local_inspection_service.model_providers.proxy_runtime import AI_LOCAL_PROXY_URL
from typing import Any
from local_inspection_service.auth.policy import DEFAULT_USER_PERMISSIONS
from local_inspection_service.auth.policy import FEATURE_PERMISSIONS
from pathlib import Path
from local_inspection_service.schemas.plc import PlcConfigRequest
from local_inspection_service.incoming_text_inspection import TextObservation
from local_inspection_service.plc_web_serial import WEB_SERIAL_PROTOCOL_VERSION
from ultralytics import YOLO
from local_inspection_service.accessories import policy as _accessory_policy
from local_inspection_service.accessories.mask_geometry import add_sprite_safety_margin as _add_sprite_safety_margin_impl
from local_inspection_service.model_providers.payloads import ai_json_text_candidates as _ai_json_text_candidates
from local_inspection_service.accessories.mask_geometry import alpha_bbox as _alpha_bbox_impl
from local_inspection_service.accessories.mask_geometry import alpha_component_count as _alpha_component_count_impl
from local_inspection_service.accessories.crop_analysis import alpha_component_cutouts as _alpha_component_cutouts_impl
from local_inspection_service.accessories.crop_analysis import alpha_component_summary as _alpha_component_summary_impl
from local_inspection_service.accessories.mask_geometry import alpha_edge_max as _alpha_edge_max_impl
from local_inspection_service.accessories.mask_geometry import alpha_edge_stats as _alpha_edge_stats_impl
from local_inspection_service.accessories.background_evidence import background_patch_boxes as _background_patch_boxes_impl
from local_inspection_service.accessories.background_evidence import background_patch_signature as _background_patch_signature_impl
from local_inspection_service.accessories.background_evidence import background_signature_distance as _background_signature_distance_impl
from local_inspection_service.accessories.cutout_masks import bright_green_conveyor_mask as _bright_green_conveyor_mask_impl
from local_inspection_service.accessories.sprite_metadata_values import canonical_pose_family_name as _canonical_pose_family_name_impl
from local_inspection_service.accessories.sprite_metadata_values import canonical_sprite_canvas_size_px as _canonical_sprite_canvas_size_px_impl
from local_inspection_service.accessories.materialized_assets import clean_sprite_metadata_complete as _clean_sprite_metadata_complete_impl
from local_inspection_service.agent.photo_highlight_masks import decode_photo_highlight_mask as _decode_photo_highlight_mask_impl
from local_inspection_service.detection.task_backgrounds import ai_detection_task_background_record as _detection_task_background_record
from local_inspection_service.detection.task_identity import ai_detection_task_model_id as _detection_task_model_id
from local_inspection_service.accessories.cutout_masks import foreground_mask as _foreground_mask_impl
from local_inspection_service.detection.task_backgrounds import hydrate_auto_optimize_background_from_ai_task as _hydrate_detection_task_background
from local_inspection_service.accessories.image_job_metadata import ensure_image_job_task_id as _image_metadata_ensure_id
from local_inspection_service.accessories.image_job_metadata import candidate_image_jobs as _image_metadata_jobs
from local_inspection_service.accessories.image_job_metadata import deterministic_task_id as _image_metadata_task_id
from local_inspection_service.text_inspection.incoming_analysis import corroboration as _incoming_corroboration
from local_inspection_service.text_inspection.incoming_analysis import observations as _incoming_observations
from local_inspection_service.text_inspection.incoming_access import public_record as _incoming_public_record
from local_inspection_service.text_inspection.incoming_access import task_access_allowed as _incoming_task_access_allowed
from local_inspection_service.accessories.preview_sprites import load_clean_sprite as _load_clean_sprite_impl
from local_inspection_service.accessories.compositing import long_axis_unified_render_box as _long_axis_unified_render_box_impl
from local_inspection_service.detection.annotation import normalize_ai_box_2d as _normalize_ai_box_2d
from local_inspection_service.model_providers.payloads import normalize_ai_json_root as _normalize_ai_json_root
from local_inspection_service.accessories.mask_geometry import normalize_angle_180 as _normalize_angle_180_impl
from local_inspection_service.accessories.pose_policy import normalize_cardinal_rotation_degrees as _normalize_cardinal_rotation_degrees_impl
from local_inspection_service.text_inspection.incoming_analysis import result_mapping as _ocr_result_mapping
from local_inspection_service.accessories.compositing import paste_rectified_document_asset as _paste_rectified_document_asset_impl
from local_inspection_service.agent.photo_highlight_masks import photo_highlight_auto_roi_mask as _photo_highlight_auto_roi_mask_impl
from local_inspection_service.accessories.compositing import physical_mask_for_rect_asset as _physical_mask_for_rect_asset_impl
from local_inspection_service.agent.pipeline_background_publication import pipeline_background_plate_prompt as _pipeline_background_plate_prompt_impl
from local_inspection_service.accessories.pose_policy import pose_collection_regions as _pose_collection_regions_impl
from local_inspection_service.accessories.preparation import defer_accessory_normalization as _preparation_defer
from local_inspection_service.accessories.preparation import build_object_view_plan as _preparation_view_plan
from local_inspection_service.text_inspection.images import prepare_provider_image as _prepare_text_provider_image
from local_inspection_service.detection.presence_validation import coerce_detection_count as _presence_count
from local_inspection_service.detection.presence_validation import ai_detection_parsed_covers_required as _presence_covers_required
from local_inspection_service.accessories.display_labels import profile_size_text as _profile_size_text_impl
from local_inspection_service.training.legacy_worker_requests import windows_worker_status as _retired_worker_status
from local_inspection_service.training.worker_watcher import _worker_training_watch_once as _retired_worker_watch_once
from local_inspection_service.training.worker_watcher import worker_training_watcher_enabled as _retired_worker_watcher_enabled
from local_inspection_service.accessories.reference_evidence import saturated_chroma_mask as _saturated_chroma_mask_impl
from local_inspection_service.accessories.preview_assets import select_document_image_candidate as _select_document_image_candidate_impl
from local_inspection_service.accessories.alpha_masks import solid_object_alpha as _solid_object_alpha_impl
from local_inspection_service.accessories.sprite_metadata_values import source_long_short_oriented_px as _source_long_short_oriented_px_impl
from local_inspection_service.accessories.sprite_metadata_values import source_object_long_short_metadata as _source_object_long_short_metadata_impl
from local_inspection_service.accessories.pose_policy import source_object_major_axis_px as _source_object_major_axis_px_impl
from local_inspection_service.accessories.pose_policy import sprite_pose_family as _sprite_pose_family_impl
from local_inspection_service.accessories.cutout_masks import suppress_green_spill as _suppress_green_spill_impl
from local_inspection_service.accessories.materialized_assets import text_accessory_confirm_detail as _text_accessory_confirm_detail_impl
from local_inspection_service.accessories.alpha_masks import transparent_object_alpha as _transparent_object_alpha_impl
from local_inspection_service.accessories.mask_geometry import trim_masked_asset as _trim_masked_asset_impl
from local_inspection_service.accessories.compositing import trim_rect_asset as _trim_rect_asset_impl
from local_inspection_service.training.annotations import write_dataset_yaml as _write_dataset_yaml
from local_inspection_service.storage.runtime_selector import build_runtime_repository
from local_inspection_service.runtime.connections import close_selection
import numpy as np
import os
import re
from local_inspection_service.release_version import release_version_status
from local_inspection_service.training.background_catalog import safe_background_set_id
from local_inspection_service.runtime.connections import selection_is_usable
from local_inspection_service.training.dataset_archives import file_sha256 as strict_training_file_sha256
import time
import urllib.error
import urllib.request
from local_inspection_service.auth.policy import user_is_admin
AI_DETECTION_SYSTEM_PROMPT = _application.values.AI_DETECTION_SYSTEM_PROMPT
AI_DETECTION_TASK_PREFIX = _application.values.AI_DETECTION_TASK_PREFIX
IMAGE_JOB_ACTIVE_STATUSES = _application.values.IMAGE_JOB_ACTIVE_STATUSES
LEGACY_OWNER_ID = _application.values.LEGACY_OWNER_ID
ROOT = _application.values.ROOT
TEXT_INSPECTION_PROVIDER_IMAGE_JPEG_QUALITY = _application.values.TEXT_INSPECTION_PROVIDER_IMAGE_JPEG_QUALITY
TEXT_INSPECTION_PROVIDER_IMAGE_MAX_SIDE = _application.values.TEXT_INSPECTION_PROVIDER_IMAGE_MAX_SIDE
_accessory_image_io = _application.infrastructure._accessory_image_io
_account_projections = _application.infrastructure._account_projections
_app_configuration = _application.infrastructure._app_configuration
_auto_optimization_mask_prompts = _application.training_pipeline._auto_optimization_mask_prompts
_business_files = _application.artifacts.files
_detection_rule_requests = _application.http._detection_rule_requests
_detection_task_store = _application.inspection._detection_task_store
_incoming_ocr_engine = _application.text._incoming_ocr_engine
_local_models = _application.training_pipeline._local_models
_model_profile_configuration = _application.infrastructure._model_profile_configuration
_photo_highlight_selection = _application.training_pipeline._photo_highlight_selection
_plc_config_diagnostics = _application.plc._plc_config_diagnostics
_provider_configuration = _application.infrastructure._provider_configuration
_provider_json_retry = _application.inspection._provider_json_retry
_public_network_policy = _application.infrastructure._public_network_policy
_public_status_projection = _application.infrastructure._public_status_projection
_resource_names = _application.infrastructure._resource_names
_runtime_repositories = _application.infrastructure._runtime_repositories
_runtime_repository_access = _application.infrastructure._runtime_repository_access
_runtime_repository_owner = _application.infrastructure._runtime_repository_owner
_service_paths = _application.infrastructure._service_paths
_sprite_render_metadata = _application.inspection._sprite_render_metadata
current_auth_user = _application.infrastructure.current_auth_user
index = _application.infrastructure.index
record_owner_id = _application.infrastructure.record_owner_id

def current_release_version() -> dict[str, Any]:
    return release_version_status(ROOT, WEB_SERIAL_PROTOCOL_VERSION)

def normalize_origin(value: str) -> str:
    return _public_network_policy.normalize_origin(value)

def same_origin(origin: str, host: str) -> bool:
    return _public_network_policy.same_origin(origin, host)

def cors_origin_allowed(origin: str) -> bool:
    return _public_network_policy.cors_origin_allowed(origin)

def reset_runtime_repository_cache() -> None:
    _runtime_repositories.reset()

def close_runtime_repository_selection(selection: Any) -> None:
    close_selection(selection)

def runtime_repository_selection_is_usable(selection: Any) -> bool:
    return selection_is_usable(selection)

def clear_thread_runtime_repository_selection() -> None:
    _runtime_repositories.clear()

def current_runtime_repository_generation() -> int:
    return _runtime_repositories.generation()

def runtime_repository_selection() -> Any:
    """Build the explicit runtime repository selection with HTTP-safe errors."""
    return _runtime_repository_access.runtime_repository_selection()

def runtime_postgres_repository_or_none() -> Any | None:
    """Return the explicit PostgreSQL repository, or None for JSON runtime."""
    return _runtime_repository_access.runtime_postgres_repository_or_none()

def runtime_store_probe_payload() -> dict[str, Any]:
    """Return a non-secret runtime-store probe for an admin HTTP endpoint."""
    return _runtime_repository_access.runtime_store_probe_payload()

def resource_name_key(value: Any) -> str:
    return _resource_names.resource_name_key(value)

def resource_owner_id_for_new_record(user: dict[str, Any]) -> str:
    return _resource_names.resource_owner_id_for_new_record(user)

def duplicate_name_error(resource_label: str) -> None:
    return _resource_names.duplicate_name_error(resource_label)

def assert_unique_accessory_name(config: dict[str, Any], name: Any, owner_user_id: str, *, exclude_id: str='') -> None:
    return _resource_names.assert_unique_accessory_name(config, name, owner_user_id, exclude_id=exclude_id)

def task_record_name(record: dict[str, Any]) -> str:
    return _resource_names.task_record_name(record)

def task_matches_excluded_identity(task: dict[str, Any], *, excluded_pipeline_task_ids: set[str], excluded_ai_task_ids: set[str]) -> bool:
    return _resource_names.task_matches_excluded_identity(task, excluded_pipeline_task_ids=excluded_pipeline_task_ids, excluded_ai_task_ids=excluded_ai_task_ids)

def assert_unique_task_name(name: Any, owner_user_id: str, *, exclude_pipeline_task_id: str='', exclude_ai_task_id: str='') -> None:
    return _resource_names.assert_unique_task_name(name, owner_user_id, exclude_pipeline_task_id=exclude_pipeline_task_id, exclude_ai_task_id=exclude_ai_task_id)

def assert_unique_dataset_name(name: Any, owner_user_id: str, user: dict[str, Any], *, exclude_dataset_id: str='') -> None:
    return _resource_names.assert_unique_dataset_name(name, owner_user_id, user, exclude_dataset_id=exclude_dataset_id)

def assert_unique_model_name(name: Any, owner_user_id: str, *, exclude_run_id: str='') -> None:
    return _resource_names.assert_unique_model_name(name, owner_user_id, exclude_run_id=exclude_run_id)

def merge_scoped_accessory_updates(full_config: dict[str, Any], scoped_config: dict[str, Any], user: dict[str, Any]) -> None:
    return _account_projections.merge_scoped_accessory_updates(full_config, scoped_config, user)

def scope_config_for_user(config: dict[str, Any], user: dict[str, Any] | None=None, target_user_id: str | None=None) -> dict[str, Any]:
    return _account_projections.scope_config_for_user(config, user, target_user_id)

def require_analyze_model_permission(model_id: str | None) -> None:
    return _account_projections.require_analyze_model_permission(model_id)

def output_path_visible_to_user(request_path: str, user: dict[str, Any]) -> bool:
    return _account_projections.output_path_visible_to_user(request_path, user)

def is_private_or_local_host(hostname: str) -> bool:
    return _public_network_policy.is_private_or_local_host(hostname)

def sanitize_url_for_public_user(value: Any) -> str:
    return _public_network_policy.sanitize_url_for_public_user(value)

def sanitize_path_for_public_user(value: Any) -> str:
    return _public_network_policy.sanitize_path_for_public_user(value)

def include_internal_runtime_details(user: dict[str, Any] | None) -> bool:
    return _public_network_policy.include_internal_runtime_details(user)

def optional_float(value: Any) -> float | None:
    try:
        if value in (None, ''):
            return None
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None

def _read_config_file() -> dict[str, Any] | None:
    """Read config.json, retrying briefly on transient partial/empty reads.

    Returns the parsed dict, an empty dict when the file legitimately does not
    exist, or ``None`` when the file is present but could not be parsed cleanly
    (e.g. mid-write). Callers must NOT treat ``None`` as "no accessories" — doing
    so would silently drop every persisted record whenever a concurrent writer
    is in the middle of replacing the file.
    """
    return _app_configuration._read_config_file()

def load_config() -> dict[str, Any]:
    return _app_configuration.load_config()

def save_config(config: dict[str, Any]) -> None:
    return _app_configuration.save_config(config)

def plc_config_request_payload(request: PlcConfigRequest) -> dict[str, Any]:
    if hasattr(request, 'model_dump'):
        return request.model_dump(exclude_none=True)
    return request.dict(exclude_none=True)

def plc_config_response(config: dict[str, Any] | None=None) -> dict[str, Any]:
    return _plc_config_diagnostics.response(config)

def task_rule_id(value: Any) -> str:
    return re.sub('[^a-zA-Z0-9_.@-]+', '_', str(value or '').strip()).strip('_')[:96]

def task_rule_overrides(config: dict[str, Any], task_id: Any) -> dict[str, Any]:
    return _detection_rule_requests.task_rule_overrides(config, task_id)

def apply_task_rule_override_to_spec(spec: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return _detection_rule_requests.apply_task_rule_override_to_spec(spec, config)

def accessory_uid(item: dict[str, Any]) -> str:
    return _accessory_policy.accessory_uid(item)

def accessory_legacy_uid(item: dict[str, Any]) -> str:
    return _accessory_policy.accessory_legacy_uid(item)

def accessory_material_type(item: dict[str, Any]) -> str:
    return _accessory_policy.accessory_material_type(item)

def accessory_uses_ocr(item: dict[str, Any]) -> bool:
    return _accessory_policy.accessory_uses_ocr(item)

def normalize_object_alpha_material_policy(value: Any) -> str | None:
    return _accessory_policy.normalize_object_alpha_material_policy(value)

def object_alpha_material_policy(item: dict[str, Any] | None=None, metadata: dict[str, Any] | None=None) -> str:
    return _accessory_policy.object_alpha_material_policy(item, metadata)

def object_alpha_policy_label(policy: str) -> str:
    return _accessory_policy.object_alpha_policy_label(policy)

def service_rebased_path(path: Path) -> Path | None:
    return _service_paths.service_rebased_path(path)

def rebase_stale_local_path_text(value: str) -> str:
    return _service_paths.rebase_stale_local_path_text(value)

def rebase_stale_local_payload_text(text: str) -> str:
    return _service_paths.rebase_stale_local_payload_text(text)

def public_path_sanitized(value: Any) -> Any:
    return _service_paths.public_path_sanitized(value)

def public_auth_features(user: dict[str, Any] | None) -> dict[str, str]:
    return FEATURE_PERMISSIONS if user else {}

def public_default_permissions(user: dict[str, Any] | None) -> list[str]:
    return DEFAULT_USER_PERMISSIONS if user else []

def public_legacy_owner_id(user: dict[str, Any] | None) -> str:
    return LEGACY_OWNER_ID if user else ''

def migrate_json_file_paths(path: Path) -> bool:
    return _service_paths.migrate_json_file_paths(path)

def resolve_service_path(value: Any, *, for_write: bool=False) -> Path:
    return _service_paths.resolve_service_path(value, for_write=for_write)

def path_is_under(path: Path, root: Path) -> bool:
    return _service_paths.path_is_under(path, root)

def public_output_url(path: Path) -> str:
    return _service_paths.public_output_url(path)

def public_output_url_for_existing(path: Path) -> str:
    return _service_paths.public_output_url_for_existing(path)

def output_write_dir(kind: str='') -> Path:
    return _service_paths.output_write_dir(kind)

def output_write_dir_for_owner(kind: str='', owner_user_id: str='') -> Path:
    return _service_paths.output_write_dir_for_owner(kind, owner_user_id)

def output_url(path: Path) -> str:
    return _service_paths.output_url(path)

def build_object_view_plan(name: str) -> list[dict[str, Any]]:
    return _preparation_view_plan(name)

def select_document_image_candidate(candidates: list[tuple[np.ndarray, dict[str, Any]]], rng: np.random.Generator | None, *, multi_policy: str, single_policy: str) -> tuple[np.ndarray, dict[str, Any]] | None:
    return _select_document_image_candidate_impl(candidates, rng, multi_policy=multi_policy, single_policy=single_policy)

def candidate_image_jobs(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    return _image_metadata_jobs(candidate)

def deterministic_task_id(candidate: dict[str, Any], job: dict[str, Any]) -> str:
    return _image_metadata_task_id(candidate, job)

def ensure_image_job_task_id(candidate: dict[str, Any], job: dict[str, Any]) -> bool:
    return _image_metadata_ensure_id(candidate, job)

def resolve_model_profiles():
    """Composition-only late binding; domain decorators receive this callable."""
    return _model_profile_configuration.resolve_model_profiles()

def record_model_call(settings, elapsed_ms, ok, usage):
    return resolve_model_profiles().record_call(settings, elapsed_ms, ok, usage)

def profile_size_text(size: dict[str, Any] | None) -> str:
    return _profile_size_text_impl(size)

def saturated_chroma_mask(image_bgr: np.ndarray, screen: dict[str, Any]) -> np.ndarray:
    return _saturated_chroma_mask_impl(image_bgr, screen)

def default_ai_model(provider: str) -> str:
    return _provider_configuration.default_ai_model(provider)

def default_ai_base_url(provider: str) -> str:
    return _provider_configuration.default_ai_base_url(provider)

def ai_provider_label(provider: str) -> str:
    return _provider_configuration.ai_provider_label(provider)

def default_image_generation_model(provider: str) -> str:
    return _provider_configuration.default_image_generation_model(provider)

def default_image_generation_base_url(provider: str) -> str:
    return _provider_configuration.default_image_generation_base_url(provider)

def default_image_generation_api_key_env(provider: str) -> str:
    return _provider_configuration.default_image_generation_api_key_env(provider)

def image_generation_provider_key(provider: str) -> str:
    return _provider_configuration.image_generation_provider_key(provider)

def image_generation_provider_label(provider: str) -> str:
    return _provider_configuration.image_generation_provider_label(provider)

def mask_secret(value: str) -> str:
    return _provider_configuration.mask_secret(value)

def ai_key_id(secret: str) -> str:
    return _provider_configuration.ai_key_id(secret)

def secret_key_item_id(env_name: str, secret: str='') -> str:
    return _provider_configuration.secret_key_item_id(env_name, secret)

def default_secret_env_name(prefix: str, secret: str='', *, provider: str='') -> str:
    return _provider_configuration.default_secret_env_name(prefix, secret, provider=provider)

def load_local_secret_env() -> dict[str, str]:
    return _provider_configuration.load_local_secret_env()

def save_local_secret_env(values: dict[str, str]) -> None:
    return _provider_configuration.save_local_secret_env(values)

def local_secret_env_value(name: str) -> str:
    return _provider_configuration.local_secret_env_value(name)

def set_local_secret_env(name: str, value: str) -> None:
    return _provider_configuration.set_local_secret_env(name, value)

def delete_local_secret_env(name: str) -> None:
    return _provider_configuration.delete_local_secret_env(name)

def persist_secret_key_items(items: list[dict[str, str]], default_prefix: str) -> list[dict[str, str]]:
    return _provider_configuration.persist_secret_key_items(items, default_prefix)

def normalize_ai_key_items(config: dict[str, Any], provider: str | None=None) -> list[dict[str, str]]:
    return _provider_configuration.normalize_ai_key_items(config, provider)

def public_ai_key_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return _provider_configuration.public_ai_key_items(items)

def ai_keys_for_provider(items: list[dict[str, str]], provider: str) -> list[dict[str, str]]:
    return _provider_configuration.ai_keys_for_provider(items, provider)

def normalize_image_key_items(config: dict[str, Any], provider: str) -> list[dict[str, str]]:
    return _provider_configuration.normalize_image_key_items(config, provider)

def normalize_agent_key_items(config: dict[str, Any]) -> list[dict[str, str]]:
    return _provider_configuration.normalize_agent_key_items(config)

def image_keys_for_provider(items: list[dict[str, str]], provider: str) -> list[dict[str, str]]:
    return _provider_configuration.image_keys_for_provider(items, provider)

def agent_keys_for_provider(items: list[dict[str, str]], provider: str) -> list[dict[str, str]]:
    return _provider_configuration.agent_keys_for_provider(items, provider)

def validate_ai_provider(value: Any) -> str:
    return _provider_configuration.validate_ai_provider(value)

def validate_image_generation_provider(value: Any) -> str:
    return _provider_configuration.validate_image_generation_provider(value)

def validate_ai_model(value: Any) -> str:
    return _provider_configuration.validate_ai_model(value)

def validate_ai_base_url(value: Any) -> str:
    return _provider_configuration.validate_ai_base_url(value)

def public_ai_base_url(value: Any) -> str:
    return _provider_configuration.public_ai_base_url(value)

def masked_url_for_status(value: Any) -> str:
    return _provider_configuration.masked_url_for_status(value)

def validate_ai_proxy_url(value: Any) -> str:
    return _provider_configuration.validate_ai_proxy_url(value)

def ai_proxy_url_from_environment() -> tuple[str, str]:
    return _provider_configuration.ai_proxy_url_from_environment()

def local_proxy_available(proxy_url: str=AI_LOCAL_PROXY_URL) -> bool:
    return _provider_configuration.local_proxy_available(proxy_url)

def env_flag_enabled(name: str, default: bool=True) -> bool:
    return _provider_configuration.env_flag_enabled(name, default)

def ai_proxy_url_from_config(local: dict[str, Any], provider: str) -> tuple[str, str, bool]:
    return _provider_configuration.ai_proxy_url_from_config(local, provider)

def ai_urlopen(request: urllib.request.Request, settings: dict[str, Any], *, timeout: float):
    return _provider_configuration.ai_urlopen(request, settings, timeout=timeout)

def validate_ai_timeout(value: Any) -> float:
    return _provider_configuration.validate_ai_timeout(value)

def validate_image_generation_timeout(value: Any) -> float:
    return _provider_configuration.validate_image_generation_timeout(value)

def validate_ai_key_env(value: Any) -> str:
    return _provider_configuration.validate_ai_key_env(value)

def load_ai_local_config() -> dict[str, Any]:
    return _provider_configuration.load_ai_local_config()

def ai_local_config_temp_path() -> Path:
    return _provider_configuration.ai_local_config_temp_path()

def save_ai_local_config(config: dict[str, Any]) -> None:
    return _provider_configuration.save_ai_local_config(config)

def redact_status_payload_for_user(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    return _account_projections.redact_status_payload_for_user(payload, user)

def redact_config_summary_for_user(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    return _account_projections.redact_config_summary_for_user(payload, user)

def redact_accessory_payload_for_user(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    return _account_projections.redact_accessory_payload_for_user(payload, user)

def auto_optimize_mask_target_payload(item: dict[str, Any], index: int) -> dict[str, Any]:
    return _auto_optimization_mask_prompts.auto_optimize_mask_target_payload(item, index)

def ai_detection_settings(purpose: str='pipeline') -> dict[str, Any]:
    return _model_profile_configuration.ai_detection_settings(purpose)

def image_generation_settings() -> dict[str, Any]:
    return _model_profile_configuration.image_generation_settings()

def load_agent_config() -> dict[str, Any]:
    return _model_profile_configuration.load_agent_config()

def _legacy_ai_detection_settings() -> dict[str, Any]:
    return _provider_configuration._legacy_ai_detection_settings()

def public_ai_detection_status() -> dict[str, Any]:
    return _public_status_projection.public_ai_detection_status()

def public_ai_detection_status_for_user(user: dict[str, Any] | None) -> dict[str, Any]:
    return _public_status_projection.public_ai_detection_status_for_user(user)

def public_status_model_for_user(model: dict[str, Any], user: dict[str, Any] | None) -> dict[str, Any]:
    return _public_status_projection.public_status_model_for_user(model, user)

def public_service_status_for_user(user: dict[str, Any] | None, payload: dict[str, Any]) -> dict[str, Any]:
    return _public_status_projection.public_service_status_for_user(user, payload)

def public_config_summary_for_user(user: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    return _public_status_projection.public_config_summary_for_user(user, config)

def _legacy_image_generation_settings() -> dict[str, Any]:
    return _provider_configuration._legacy_image_generation_settings()

def public_image_generation_status() -> dict[str, Any]:
    return _public_status_projection.public_image_generation_status()

def normalize_ai_json_root(parsed: Any) -> dict[str, Any] | None:
    return _normalize_ai_json_root(parsed)

def ai_json_text_candidates(text: str) -> list[str]:
    return _ai_json_text_candidates(text)

def generate_provider_json_with_fallback(settings: dict[str, Any], system_prompt: str, user_content: list[dict[str, Any]], *, max_tokens: int, cached_content: str='', max_attempts: int | None=None, overloaded_retry_delay_seconds: float | None=None, allow_overloaded_model_fallback: bool=True) -> tuple[dict[str, Any], int, dict[str, Any]]:
    return _provider_json_retry.generate_provider_json_with_fallback(settings, system_prompt, user_content, max_tokens=max_tokens, cached_content=cached_content, max_attempts=max_attempts, overloaded_retry_delay_seconds=overloaded_retry_delay_seconds, allow_overloaded_model_fallback=allow_overloaded_model_fallback)

def generate_ai_detection_json(settings: dict[str, Any], user_content: list[dict[str, Any]], *, max_tokens: int) -> tuple[dict[str, Any], int, dict[str, Any]]:
    return generate_provider_json_with_fallback(settings, AI_DETECTION_SYSTEM_PROMPT, user_content, max_tokens=max_tokens)

def ai_tool_provider_meta(settings: dict[str, Any]) -> dict[str, Any]:
    return {'provider': settings.get('provider') or '', 'provider_model': settings.get('model') or '', 'provider_status': settings.get('status') or ''}

def profile_generation_status(settings: dict[str, Any], *, source: str='fallback') -> dict[str, Any]:
    return {'source': source, 'provider': settings.get('provider') or '', 'provider_model': settings.get('model') or '', 'status': settings.get('status') or 'unknown', 'message': settings.get('message') or '', 'updated_at': int(time.time())}

def clean_sprite_metadata_complete(asset: dict[str, Any]) -> bool:
    return _clean_sprite_metadata_complete_impl(asset)

def accessory_ai_profile_ready(item: dict[str, Any]) -> bool:
    return _accessory_policy.accessory_ai_profile_ready(item)

def accessory_ai_profile_rejected(item: dict[str, Any]) -> bool:
    return _accessory_policy.accessory_ai_profile_rejected(item)

def text_accessory_confirm_detail(item: dict[str, Any], text_assets: list[dict[str, Any]], text_assets_complete: bool, profile_ready: bool) -> dict[str, Any]:
    return _text_accessory_confirm_detail_impl(item, text_assets, text_assets_complete, profile_ready)

def canonical_pose_family_name(pose_family: str | None) -> str | None:
    return _canonical_pose_family_name_impl(pose_family)

def load_clean_sprite(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    return _load_clean_sprite_impl(path, images=_accessory_image_io)

def source_object_long_short_metadata(source_size_px: list[int] | tuple[int, int] | None) -> dict[str, Any]:
    return _source_object_long_short_metadata_impl(source_size_px)

def source_long_short_oriented_px(long_side: int, short_side: int, long_axis: Any) -> list[int]:
    return _source_long_short_oriented_px_impl(long_side, short_side, long_axis)

def sprite_render_size_px(item: dict[str, Any], sprite_meta: dict[str, Any] | None, material_type: str) -> tuple[int, int]:
    return _sprite_render_metadata.sprite_render_size_px(item, sprite_meta, material_type)

def canonical_sprite_canvas_size_px(asset: dict[str, Any]) -> tuple[int, int] | None:
    return _canonical_sprite_canvas_size_px_impl(asset)

def transparent_object_alpha(asset: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    return _transparent_object_alpha_impl(asset, mask)

def solid_object_alpha(mask: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    return _solid_object_alpha_impl(mask)

def normalize_angle_180(angle: float) -> float:
    return _normalize_angle_180_impl(angle)

def alpha_bbox(mask: np.ndarray, threshold: int=8) -> list[int]:
    return _alpha_bbox_impl(mask, threshold)

def alpha_edge_max(mask: np.ndarray) -> int:
    return _alpha_edge_max_impl(mask)

def alpha_edge_stats(mask: np.ndarray) -> dict[str, Any]:
    return _alpha_edge_stats_impl(mask)

def alpha_component_count(mask: np.ndarray) -> int:
    return _alpha_component_count_impl(mask)

def add_sprite_safety_margin(asset: np.ndarray, mask: np.ndarray, margin: int=10) -> tuple[np.ndarray, np.ndarray]:
    return _add_sprite_safety_margin_impl(asset, mask, margin)

def alpha_component_cutouts(image: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    return _alpha_component_cutouts_impl(image)

def alpha_component_summary(alpha: np.ndarray, threshold: int=28) -> tuple[int, int]:
    return _alpha_component_summary_impl(alpha, threshold)

def foreground_mask(image: np.ndarray) -> np.ndarray:
    return _foreground_mask_impl(image)

def pose_collection_regions(image: np.ndarray, padded: bool=True) -> list[tuple[int, int, int, int]]:
    return _pose_collection_regions_impl(image, padded)

def normalize_cardinal_rotation_degrees(angle: float) -> int:
    return _normalize_cardinal_rotation_degrees_impl(angle)

def source_object_major_axis_px(asset: dict[str, Any]) -> int | None:
    return _source_object_major_axis_px_impl(asset)

def sprite_pose_family(asset: dict[str, Any]) -> str:
    return _sprite_pose_family_impl(asset)

def trim_masked_asset(asset: np.ndarray, mask: np.ndarray, pad: int=4) -> tuple[np.ndarray, np.ndarray]:
    return _trim_masked_asset_impl(asset, mask, pad)

def physical_mask_for_rect_asset(asset: np.ndarray) -> np.ndarray:
    return _physical_mask_for_rect_asset_impl(asset)

def trim_rect_asset(asset: np.ndarray, pad: int=0) -> np.ndarray:
    return _trim_rect_asset_impl(asset, pad)

def long_axis_unified_render_box(visible_w: int, visible_h: int, target_long_px: int, target_short_px: int) -> tuple[int, int]:
    """Return a render box whose aspect equals the sprite's own visible aspect and
    whose LONG side equals the physical-footprint long side.

    The compositor pastes with preserve_aspect_ratio=min(w/vw, h/vh). When the
    footprint aspect (from physical dims) does not match a particular AI pose
    image's visible aspect, that min() clamps to the short side and the object
    shrinks to a fraction of its true size (the source of the 10x size spread).
    By matching the box aspect to the sprite, min() resolves to the long-axis
    scale, so every view of the same accessory renders at the same long-axis
    length and stays size-consistent without distortion."""
    return _long_axis_unified_render_box_impl(visible_w, visible_h, target_long_px, target_short_px)

def paste_rectified_document_asset(canvas: np.ndarray, asset: np.ndarray, center: tuple[int, int], target_size: tuple[int, int], angle: float) -> dict[str, Any]:
    return _paste_rectified_document_asset_impl(canvas, asset, center, target_size, angle)

def defer_accessory_normalization(item: dict[str, Any]) -> None:
    return _preparation_defer(item)

def candidate_has_active_image_jobs(candidate: dict[str, Any]) -> bool:
    return any((str(job.get('status', '')) in IMAGE_JOB_ACTIVE_STATUSES for job in candidate_image_jobs(candidate)))

def public_text(value: Any) -> str:
    return str(value).replace('Pose Collection', '多角度视图').replace('ImageWorker', '生成任务').replace('Image worker', '生成任务').replace('Codex CLI', '本地生成').replace('Image tool', '生成工具')

def physical_render_size_for_sprite(item: dict[str, Any], material_type: str, sprite_meta: dict[str, Any] | None=None) -> tuple[int, int]:
    return sprite_render_size_px(item, sprite_meta, material_type)

def write_dataset_yaml(path: Path, dataset_dir: Path, names: list[str]) -> None:
    return _write_dataset_yaml(path, dataset_dir, names, files=_business_files)

def windows_worker_status(*, force: bool=False, probe: bool=True, include_services: bool=False) -> dict[str, Any]:
    return _retired_worker_status(force=force, probe=probe, include_services=include_services)

def file_sha256(path: Path) -> str:
    return strict_training_file_sha256(path, files=_business_files)

def worker_training_watcher_enabled() -> bool:
    return _retired_worker_watcher_enabled()

def _worker_training_watch_once() -> int:
    return _retired_worker_watch_once()

def ai_detection_task_model_id(task_id: str) -> str:
    return _detection_task_model_id(task_id, AI_DETECTION_TASK_PREFIX)

def find_ai_detection_task(task_id: str) -> dict[str, Any] | None:
    return _detection_task_store.find_ai_detection_task(task_id)

def ai_detection_task_background_record(task_id: str) -> tuple[str, dict[str, Any]]:
    return _detection_task_background_record(task_id, find_task=lambda value: find_ai_detection_task(value), normalize_background=lambda: safe_background_set_id)

def hydrate_auto_optimize_background_from_ai_task(state: dict[str, Any]) -> bool:
    return _hydrate_detection_task_background(state, background_record=lambda: ai_detection_task_background_record, normalize_background=lambda: safe_background_set_id)

def model(model_id: str | None=None, config: dict[str, Any] | None=None) -> YOLO:
    return _local_models.model(model_id, config)

def ai_detection_output_token_budget(required_count: int) -> int:
    return max(180, min(420, 120 + max(1, required_count) * 64))

def ai_detection_provider_output_token_budget(required_count: int, settings: dict[str, Any]) -> int:
    budget = ai_detection_output_token_budget(required_count)
    if str(settings.get('provider') or '') == 'qwen':
        return min(800, budget * 2)
    return budget

def ai_detection_parsed_covers_required(parsed: Any, required_ids: set[str]) -> bool:
    return _presence_covers_required(parsed, required_ids)

def coerce_detection_count(value: Any) -> int | None:
    return _presence_count(value)

def normalize_ai_box_2d(value: Any) -> list[float] | None:
    return _normalize_ai_box_2d(value)

def get_plc_config() -> dict[str, Any]:
    return plc_config_response()

def _real_photo_repository():
    selection = build_runtime_repository(env=os.environ, postgres_connector=_runtime_repository_owner.connector)
    return selection.repository if selection.store == 'postgres' else None

def agent_base_url_host(base_url: str) -> str:
    return _provider_configuration.agent_base_url_host(base_url)

def is_cursor_base_url(base_url: str) -> bool:
    return _provider_configuration.is_cursor_base_url(base_url)

def detect_agent_provider_from_base_url(base_url: str) -> str:
    return _provider_configuration.detect_agent_provider_from_base_url(base_url)

def normalize_agent_provider(provider: str | None, base_url: str='') -> str:
    return _provider_configuration.normalize_agent_provider(provider, base_url)

def agent_provider_label(provider: str) -> str:
    return _provider_configuration.agent_provider_label(provider)

def normalize_agent_model_options(value: Any) -> list[dict[str, str]]:
    return _provider_configuration.normalize_agent_model_options(value)

def agent_model_options_from_items(items: Any, *, prepend: list[dict[str, str]] | None=None) -> list[dict[str, str]]:
    return _provider_configuration.agent_model_options_from_items(items, prepend=prepend)

def normalize_agent_config(config: dict[str, Any]) -> dict[str, Any]:
    return _provider_configuration.normalize_agent_config(config)

def _legacy_load_agent_config() -> dict[str, Any]:
    return _provider_configuration._legacy_load_agent_config()

def save_agent_config(config: dict[str, Any]) -> None:
    return _provider_configuration.save_agent_config(config)

def suppress_green_spill(image_bgr: np.ndarray) -> np.ndarray:
    """Green-spill decontamination: where the green channel exceeds both red and
    blue (a green-tinted boundary/halo pixel), pull green down to max(red,blue).
    This neutralises the green fringe around a dark object cut from a green plate
    without removing or shrinking the silhouette. Neutral/grey/silver/black object
    pixels (green ~= red ~= blue) are untouched."""
    return _suppress_green_spill_impl(image_bgr)

def bright_green_conveyor_mask(image_bgr: np.ndarray) -> np.ndarray:
    """Boolean mask of UNAMBIGUOUS bright conveyor-green pixels. Tuned to catch the
    saturated, well-lit green plate while sparing dark/olive object pixels (e.g.
    carbon-fibre) and dark anti-aliased object edges, so it can trim a green halo
    without biting into the object."""
    return _bright_green_conveyor_mask_impl(image_bgr)

def pipeline_photo_highlight_object_items(task: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    return _photo_highlight_selection.pipeline_photo_highlight_object_items(task, config)

def pipeline_uses_photo_highlight_sprite_flow(task: dict[str, Any], config: dict[str, Any]) -> bool:
    return bool(pipeline_photo_highlight_object_items(task, config))

def decode_photo_highlight_mask(mask_bgr: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    return _decode_photo_highlight_mask_impl(mask_bgr)

def photo_highlight_auto_roi_mask(roi_bgr: np.ndarray, ai_roi_mask: np.ndarray) -> tuple[np.ndarray | None, dict[str, Any]]:
    return _photo_highlight_auto_roi_mask_impl(roi_bgr, ai_roi_mask)

def pipeline_background_plate_prompt(item: dict[str, Any]) -> str:
    return _pipeline_background_plate_prompt_impl(item)

def background_patch_boxes(width: int, height: int) -> list[tuple[int, int, int, int]]:
    return _background_patch_boxes_impl(width, height)

def background_patch_signature(patch_bgr: np.ndarray) -> dict[str, Any] | None:
    return _background_patch_signature_impl(patch_bgr)

def background_signature_distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    return _background_signature_distance_impl(left, right)

def sync_ready_pipeline_ai_detection_tasks(tasks: list[dict[str, Any]], config: dict[str, Any], user: dict[str, Any] | None, target_user_id: str | None=None) -> bool:
    return False

def _text_v2_owner() -> tuple[str, str]:
    user = current_auth_user()
    return (str(user.get('id') or ''), str(user.get('username') or ''))

def _text_v2_prepare_provider_image(contents: bytes, mime_type: str) -> tuple[bytes, str, str]:
    return _prepare_text_provider_image(contents, mime_type, max_side=lambda: TEXT_INSPECTION_PROVIDER_IMAGE_MAX_SIDE, jpeg_quality=lambda: TEXT_INSPECTION_PROVIDER_IMAGE_JPEG_QUALITY)

def incoming_text_public(record: dict[str, Any]) -> dict[str, Any]:
    return _incoming_public_record(record, sanitize=lambda value: public_path_sanitized(value))

def incoming_text_task_access_allowed(task: dict[str, Any], user: dict[str, Any]) -> bool:
    return _incoming_task_access_allowed(task, user, is_admin=lambda value: user_is_admin(value), owner=lambda value: record_owner_id(value))

def incoming_text_ocr_engine() -> Any:
    return _incoming_ocr_engine.get()

def incoming_text_ocr_observations(image: np.ndarray) -> list[TextObservation]:
    return _incoming_observations(image, engine=lambda: incoming_text_ocr_engine(), mapping_provider=lambda: _ocr_result_mapping)

def incoming_text_corroboration_observations(image: np.ndarray, rules: list[dict[str, Any]]) -> dict[str, list[TextObservation]]:
    return _incoming_corroboration(image, rules, observe=lambda crop: incoming_text_ocr_observations(crop))

def react_production_spa_enabled() -> bool:
    return True
