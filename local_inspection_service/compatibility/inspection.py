"""Historical default-only forwarders. Production business ports use owned graphs."""
from __future__ import annotations
from ..runtime.default_application import default_application as _application
import os
from local_inspection_service.schemas.detection import AiDetectionTaskRequest
from local_inspection_service.model_providers.errors import AiProviderError
from typing import Any
from pathlib import Path
from fastapi import UploadFile
from ultralytics import YOLO
import numpy as np
from local_inspection_service.model_profiles.snapshots import pinned as pinned_model_profiles
import urllib.error
import urllib.request
AI_PROFILE_REFERENCE_IMAGES = _application.values.AI_PROFILE_REFERENCE_IMAGES
AgnesImageProvider = _application.inspection.AgnesImageProvider
BACKGROUND_ROI_PX = _application.values.BACKGROUND_ROI_PX
GeminiAiProvider = _application.inspection.GeminiAiProvider
MAX_VIDEO_REFERENCE_FRAMES = _application.values.MAX_VIDEO_REFERENCE_FRAMES
OpenAICompatibleAiProvider = _application.inspection.OpenAICompatibleAiProvider
QwenImageProvider = _application.inspection.QwenImageProvider
_accessory_dimensions = _application.inspection._accessory_dimensions
_accessory_gallery = _application.inspection._accessory_gallery
_accessory_labels = _application.inspection._accessory_labels
_accessory_lookup = _application.inspection._accessory_lookup
_accessory_preparation = _application.inspection._accessory_preparation
_accessory_profile_generation = _application.inspection._accessory_profile_generation
_accessory_profile_payloads = _application.inspection._accessory_profile_payloads
_accessory_profile_projection = _application.inspection._accessory_profile_projection
_accessory_projection = _application.inspection._accessory_projection
_accessory_reference_media = _application.inspection._accessory_reference_media
_accessory_refresh = _application.inspection._accessory_refresh
_accessory_repository = _application.inspection._accessory_repository
_accessory_selection = _application.inspection._accessory_selection
_accessory_text_preparation = _application.inspection._accessory_text_preparation
_ai_detection_analysis = _application.inspection._ai_detection_analysis
_asset_compositor = _application.inspection._asset_compositor
_auto_optimization_capture = _application.inspection._auto_optimization_capture
_background_candidate_catalog = _application.inspection._background_candidate_catalog
_background_cutouts = _application.inspection._background_cutouts
_background_library_matcher = _application.inspection._background_library_matcher
_background_plate_derivation = _application.inspection._background_plate_derivation
_background_reference_signatures = _application.inspection._background_reference_signatures
_candidate_artifacts = _application.inspection._candidate_artifacts
_candidate_factory = _application.inspection._candidate_factory
_candidate_repository = _application.inspection._candidate_repository
_chroma_cutouts = _application.inspection._chroma_cutouts
_crop_selection = _application.inspection._crop_selection
_cutout_selection = _application.inspection._cutout_selection
_detection_analysis = _application.inspection._detection_analysis
_detection_annotation = _application.inspection._detection_annotation
_detection_failure_result = _application.inspection._detection_failure_result
_detection_ocr_engine = _application.inspection._detection_ocr_engine
_detection_task_catalog = _application.inspection._detection_task_catalog
_detection_task_projection = _application.inspection._detection_task_projection
_detection_task_requests = _application.inspection._detection_task_requests
_detection_task_store = _application.inspection._detection_task_store
_failure_projection = _application.inspection._failure_projection
_image_encoding = _application.inspection._image_encoding
_image_job_execution = _application.inspection._image_job_execution
_image_job_management = _application.inspection._image_job_management
_image_job_metadata = _application.inspection._image_job_metadata
_image_job_queue = _application.inspection._image_job_queue
_image_payload_codec = _application.inspection._image_payload_codec
_image_provider_configuration = _application.inspection._image_provider_configuration
_image_worker_diagnostics = _application.inspection._image_worker_diagnostics
_inspection_image_store = _application.inspection._inspection_image_store
_local_models = _application.training_pipeline._local_models
_material_alpha = _application.inspection._material_alpha
_model_profile_configuration = _application.infrastructure._model_profile_configuration
_model_tool_dispatch = _application.inspection._model_tool_dispatch
_object_sprite_preprocessor = _application.inspection._object_sprite_preprocessor
_photo_highlight_sprite_builder = _application.training_pipeline._photo_highlight_sprite_builder
_pose_candidate_policy = _application.inspection._pose_candidate_policy
_pose_collection_jobs = _application.inspection._pose_collection_jobs
_pose_collection_prompts = _application.inspection._pose_collection_prompts
_pose_grid_policy = _application.inspection._pose_grid_policy
_presence_inspection = _application.inspection._presence_inspection
_presence_payload = _application.inspection._presence_payload
_presence_results = _application.inspection._presence_results
_preview_asset_loader = _application.inspection._preview_asset_loader
_preview_pose_policy = _application.inspection._preview_pose_policy
_preview_sprite_renderer = _application.inspection._preview_sprite_renderer
_profile_cache_flow = _application.inspection._profile_cache_flow
_profile_cache_policy = _application.inspection._profile_cache_policy
_profile_cache_store = _application.inspection._profile_cache_store
_provider_failure_evidence = _application.inspection._provider_failure_evidence
_provider_http_errors = _application.inspection._provider_http_errors
_provider_image_retry = _application.inspection._provider_image_retry
_provider_json_retry = _application.inspection._provider_json_retry
_provider_keys = _application.inspection._provider_keys
_provider_payloads = _application.inspection._provider_payloads
_provider_retry_policy = _application.inspection._provider_retry_policy
_provider_selection = _application.inspection._provider_selection
_reference_collection = _application.inspection._reference_collection
_reference_dimensions = _application.inspection._reference_dimensions
_reference_evidence = _application.inspection._reference_evidence
_reference_sheet = _application.inspection._reference_sheet
_reference_tile_renderer = _application.inspection._reference_tile_renderer
_rembg_runtime = _application.inspection._rembg_runtime
_required_accessories = _application.inspection._required_accessories
_sprite_artifact_writer = _application.inspection._sprite_artifact_writer
_sprite_asset_catalog = _application.inspection._sprite_asset_catalog
_sprite_canvas_normalizer = _application.inspection._sprite_canvas_normalizer
_sprite_footprint = _application.inspection._sprite_footprint
_sprite_geometry = _application.inspection._sprite_geometry
_sprite_render_metadata = _application.inspection._sprite_render_metadata
_sprite_scale = _application.inspection._sprite_scale
_text_asset_catalog = _application.inspection._text_asset_catalog
_video_summary = _application.inspection._video_summary
_warmup_candidates = _application.inspection._warmup_candidates
_warmup_prediction = _application.inspection._warmup_prediction
_yolo_warmup_runtime = _application.inspection._yolo_warmup_runtime
status = _application.http.status

def normalize_size_reference(value: Any) -> str:
    return _reference_dimensions.normalize_size_reference(value)

def size_reference_payload(reference_key: str) -> dict[str, Any] | None:
    return _reference_dimensions.size_reference_payload(reference_key)

def physical_size_payload(material_type: str, paper_preset: str='A4', paper_width_mm: Any=None, paper_height_mm: Any=None, object_length_mm: Any=None, object_width_mm: Any=None, object_height_mm: Any=None) -> dict[str, Any]:
    return _accessory_dimensions.physical_size_payload(material_type, paper_preset, paper_width_mm, paper_height_mm, object_length_mm, object_width_mm, object_height_mm)

def ai_profile_dimensions_from_physical_size(physical_size: dict[str, Any] | None) -> dict[str, Any]:
    return _accessory_dimensions.ai_profile_dimensions_from_physical_size(physical_size)

def ai_profile_top_view_aspect_ratio(dimensions: dict[str, Any] | None) -> float:
    return _accessory_dimensions.ai_profile_top_view_aspect_ratio(dimensions)

def normalize_ai_profile_dimensions(raw: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    return _accessory_dimensions.normalize_ai_profile_dimensions(raw, fallback)

def apply_ai_profile_dimensions_to_physical_size(item: dict[str, Any], dimensions: dict[str, Any] | None) -> bool:
    """When the AI Profile judges real-world dimensions, feed them into the
    accessory physical_size so the compositor renders a consistent footprint for
    this accessory across every training set."""
    return _accessory_dimensions.apply_ai_profile_dimensions_to_physical_size(item, dimensions)

def save_accessory_item(item: dict[str, Any], config: dict[str, Any] | None=None) -> dict[str, Any] | None:
    return _accessory_repository.save_accessory_item(item, config)

def delete_accessory_item(accessory_id: str, config: dict[str, Any] | None=None) -> bool:
    return _accessory_repository.delete_accessory_item(accessory_id, config)

def serialize_accessory(item: dict[str, Any]) -> dict[str, Any]:
    return _accessory_projection.serialize_accessory(item)

def serialize_accessory_summary(item: dict[str, Any]) -> dict[str, Any]:
    return _accessory_projection.serialize_accessory_summary(item)

def serialize_accessory_items(items: list[dict[str, Any]], *, summary: bool=True) -> list[dict[str, Any]]:
    return _accessory_projection.serialize_accessory_items(items, summary=summary)

def order_points(points: np.ndarray) -> np.ndarray:
    return _accessory_text_preparation.order_points(points)

def target_paper_pixel_size(physical_size: dict[str, Any] | None) -> tuple[int, int]:
    return _accessory_text_preparation.target_paper_pixel_size(physical_size)

def ratio_close(value: float, target: float, tolerance: float=0.08) -> bool:
    return _accessory_text_preparation.ratio_close(value, target, tolerance)

def quad_is_axis_aligned(rect: np.ndarray, image_shape: tuple[int, ...]) -> bool:
    return _accessory_text_preparation.quad_is_axis_aligned(rect, image_shape)

def best_document_quad(image: np.ndarray, target_aspect: float | None=None) -> np.ndarray | None:
    return _accessory_text_preparation.best_document_quad(image, target_aspect)

def document_quad_mean_size(quad: np.ndarray) -> tuple[float, float]:
    """Mean width / height (px) of an ordered tl,tr,br,bl quad — used to recover
    the document's true (deskewed) proportions."""
    return _accessory_text_preparation.document_quad_mean_size(quad)

def detect_document_quad(image: np.ndarray, target_aspect: float | None=None) -> np.ndarray | None:
    """Robustly auto-crop the document/manual body. Tries edge contours first, then
    bright-paper (Otsu) and low-saturation paper segmentation, so a manual shot on
    a darker tabletop is still found even when its edges are weak. Returns an
    ordered tl,tr,br,bl quad or None."""
    return _accessory_text_preparation.detect_document_quad(image, target_aspect)

def letterbox_document_onto_paper(image: np.ndarray, target_w: int, target_h: int, pad_value: tuple[int, int, int]=(255, 255, 255)) -> np.ndarray:
    """Place a document image onto a clean paper-sized canvas preserving aspect
    (white letterbox). Never stretches the content non-uniformly."""
    return _accessory_text_preparation.letterbox_document_onto_paper(image, target_w, target_h, pad_value)

def resize_document_to_paper(image: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """Resize a document image directly to the chosen paper pixel size."""
    return _accessory_text_preparation.resize_document_to_paper(image, target_w, target_h)

def is_text_rectified_path(path: Path | str) -> bool:
    return _accessory_text_preparation.is_text_rectified_path(path)

def stable_text_crop_stem(path: Path | str) -> str:
    return _accessory_text_preparation.stable_text_crop_stem(path)

def text_raw_crop_prefix(path: Path | str) -> str:
    return _accessory_text_preparation.text_raw_crop_prefix(path)

def text_raw_has_rectified(raw_path: Path | str, rectified_sources: list[Path]) -> bool:
    return _accessory_text_preparation.text_raw_has_rectified(raw_path, rectified_sources)

def text_image_paths_for_upload_limit(item: dict[str, Any]) -> list[Path]:
    return _accessory_text_preparation.text_image_paths_for_upload_limit(item)

def text_accessory_source_count(item: dict[str, Any]) -> int:
    return _accessory_text_preparation.text_accessory_source_count(item)

def validate_text_accessory_uploads(files: list[UploadFile], *, existing_count: int=0) -> None:
    return _accessory_text_preparation.validate_text_accessory_uploads(files, existing_count=existing_count)

def normalize_text_image(src: Path, target_dir: Path, physical_size: dict[str, Any] | None=None) -> dict[str, Any] | None:
    """Lightweight document pipeline (no image generation): auto-crop the document
    body, deskew/perspective-correct any tilt, then normalize onto the chosen paper
    page (A4/A5/...). The output is always exactly the paper pixel size."""
    return _accessory_text_preparation.normalize_text_image(src, target_dir, physical_size)

def default_asset_for_accessory(item: dict[str, Any]) -> Path | None:
    return _preview_asset_loader.default_asset_for_accessory(item)

def load_preview_asset_with_metadata(item: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]] | None:
    return _preview_asset_loader.load_preview_asset_with_metadata(item)

def load_document_image_candidate(path_value: Any, metadata: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]] | None:
    return _preview_asset_loader.load_document_image_candidate(path_value, metadata)

def load_rectified_document_asset_with_metadata(item: dict[str, Any], rng: np.random.Generator | None=None) -> tuple[np.ndarray, dict[str, Any]] | None:
    return _preview_asset_loader.load_rectified_document_asset_with_metadata(item, rng)

def load_preview_asset(item: dict[str, Any]) -> np.ndarray | None:
    return _preview_asset_loader.load_preview_asset(item)

def ensure_anchor_image_provenance(job: dict[str, Any]) -> bool:
    return _image_job_metadata.ensure_anchor_image_provenance(job)

def ensure_image_job_target_guides(job: dict[str, Any]) -> bool:
    return _image_job_metadata.ensure_image_job_target_guides(job)

def ensure_candidate_image_job_task_ids(candidate: dict[str, Any]) -> bool:
    return _image_job_metadata.ensure_candidate_image_job_task_ids(candidate)

def resolve_model_profiles():
    """Composition-only late binding; domain decorators receive this callable."""
    return _model_profile_configuration.resolve_model_profiles()

def store_candidate_image_job(candidate: dict[str, Any], updated_job: dict[str, Any]) -> None:
    return _image_job_metadata.store_candidate_image_job(candidate, updated_job)

def accessory_image_paths(item: dict[str, Any]) -> list[Path]:
    return _reference_evidence.accessory_image_paths(item)

def ai_profile_reference_paths(item: dict[str, Any]) -> list[Path]:
    return _reference_evidence.ai_profile_reference_paths(item)

def compact_english_accessory_name(value: Any, *, max_words: int=6) -> str:
    return _accessory_labels.compact_english_accessory_name(value, max_words=max_words)

def preferred_english_accessory_name(item: dict[str, Any]) -> str:
    return _accessory_labels.preferred_english_accessory_name(item)

def ensure_accessory_english_name(item: dict[str, Any]) -> bool:
    return _accessory_labels.ensure_accessory_english_name(item)

def accessory_display_label(item: dict[str, Any]) -> str:
    return _accessory_labels.accessory_display_label(item)

def image_reference_context(path: Path, accessory_id: str, ordinal: int) -> dict[str, Any] | None:
    return _reference_evidence.image_reference_context(path, accessory_id, ordinal)

def accessory_reference_image_contexts(item: dict[str, Any], *, max_images: int=AI_PROFILE_REFERENCE_IMAGES) -> list[dict[str, Any]]:
    return _reference_evidence.accessory_reference_image_contexts(item, max_images=max_images)

def normalize_chroma_screen(value: Any) -> dict[str, Any]:
    return _reference_evidence.normalize_chroma_screen(value)

def accessory_reference_chroma_fraction(item: dict[str, Any], screen_name: str, *, max_images: int=3) -> float:
    return _reference_evidence.accessory_reference_chroma_fraction(item, screen_name, max_images=max_images)

def fallback_accessory_ai_profile(item: dict[str, Any], reference_images: list[dict[str, Any]] | None=None) -> dict[str, Any]:
    return _accessory_profile_projection.fallback_accessory_ai_profile(item, reference_images)

def normalize_accessory_ai_profile(raw: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    return _accessory_profile_projection.normalize_accessory_ai_profile(raw, item)

def auto_optimize_detection_candidates(result: dict[str, Any]) -> list[dict[str, Any]]:
    return _auto_optimization_capture.auto_optimize_detection_candidates(result)

def record_auto_optimize_capture(record: dict[str, Any] | None, result: dict[str, Any], request_id: str, image_path: Path | None) -> None:
    return _auto_optimization_capture.record_auto_optimize_capture(record, result, request_id, image_path)

def provider_http_error(message_prefix: str, exc: urllib.error.HTTPError) -> AiProviderError:
    return _provider_http_errors.provider_http_error(message_prefix, exc)

def parse_ai_json_object(text: str) -> dict[str, Any]:
    return _provider_payloads.parse_ai_json_object(text)

def data_url_payload(data_url: str) -> tuple[str, str]:
    return _provider_payloads.data_url_payload(data_url)

def ai_provider_from_settings(settings: dict[str, Any]) -> OpenAICompatibleAiProvider | GeminiAiProvider:
    return _provider_selection.ai_provider_from_settings(settings)

def ai_provider() -> OpenAICompatibleAiProvider | GeminiAiProvider:
    return _provider_selection.ai_provider()

def image_generation_provider_from_settings(settings: dict[str, Any]) -> GeminiAiProvider | AgnesImageProvider | QwenImageProvider:
    return _provider_selection.image_generation_provider_from_settings(settings)

def ai_settings_match_runtime(settings: dict[str, Any]) -> bool:
    return _provider_selection.ai_settings_match_runtime(settings)

def ai_provider_key_candidates(settings: dict[str, Any]) -> list[dict[str, str]]:
    return _provider_keys.ai_provider_key_candidates(settings)

def rotate_ai_provider_key(settings: dict[str, Any], used_key_ids: set[str]) -> dict[str, Any] | None:
    return _provider_keys.rotate_ai_provider_key(settings, used_key_ids)

def require_ai_json_object(parsed: Any) -> dict[str, Any]:
    return _provider_failure_evidence.require_ai_json_object(parsed)

def provider_error_is_retryable(exc: AiProviderError) -> bool:
    return _provider_retry_policy.provider_error_is_retryable(exc)

def image_provider_error_is_retryable(exc: AiProviderError) -> bool:
    return _provider_retry_policy.image_provider_error_is_retryable(exc)

def auto_optimize_retry_delay_seconds(attempt: int, exc: AiProviderError | None=None) -> float:
    return _provider_retry_policy.auto_optimize_retry_delay_seconds(attempt, exc)

def auto_optimize_generate_image_with_retry(settings: dict[str, Any], model: str, prompt: str, user_content: list[dict[str, Any]], *, system_prompt: str='') -> dict[str, Any]:
    return _provider_image_retry.auto_optimize_generate_image_with_retry(settings, model, prompt, user_content, system_prompt=system_prompt)

def provider_error_needs_repair_prompt(exc: AiProviderError) -> bool:
    return _provider_failure_evidence.provider_error_needs_repair_prompt(exc)

def provider_failure_usage_metadata(provider: OpenAICompatibleAiProvider | GeminiAiProvider | None, exc: AiProviderError) -> dict[str, Any]:
    return _provider_failure_evidence.provider_failure_usage_metadata(provider, exc)

def annotate_provider_failure(exc: AiProviderError, *, attempt: int, errors: list[str], failed_usage_metadata: list[dict[str, Any]], usage_metadata: dict[str, Any] | None=None, fallback_model: str='', fallback_reason: str='') -> AiProviderError:
    return _provider_failure_evidence.annotate_provider_failure(exc, attempt=attempt, errors=errors, failed_usage_metadata=failed_usage_metadata, usage_metadata=usage_metadata, fallback_model=fallback_model, fallback_reason=fallback_reason)

def generate_provider_json_with_fallback(settings: dict[str, Any], system_prompt: str, user_content: list[dict[str, Any]], *, max_tokens: int, cached_content: str='', max_attempts: int | None=None, overloaded_retry_delay_seconds: float | None=None, allow_overloaded_model_fallback: bool=True) -> tuple[dict[str, Any], int, dict[str, Any]]:
    return _provider_json_retry.generate_provider_json_with_fallback(settings, system_prompt, user_content, max_tokens=max_tokens, cached_content=cached_content, max_attempts=max_attempts, overloaded_retry_delay_seconds=overloaded_retry_delay_seconds, allow_overloaded_model_fallback=allow_overloaded_model_fallback)

def image_bgr_data_url(image_bgr: np.ndarray, max_side: int=1280, quality: int=82) -> str:
    return _image_encoding.image_bgr_data_url(image_bgr, max_side=max_side, quality=quality)

def write_mcp_inspection_image(image_bgr: np.ndarray, request_id: str) -> Path | None:
    return _inspection_image_store.write_mcp_inspection_image(image_bgr, request_id)

def image_path_data_url(path: Path, max_side: int=1024, quality: int=78) -> str | None:
    return _image_encoding.image_path_data_url(path, max_side=max_side, quality=quality)

def accessory_profile_prompt_payload(item: dict[str, Any]) -> dict[str, Any]:
    return _accessory_profile_payloads.accessory_profile_prompt_payload(item)

def required_accessory_profile_payload(item: dict[str, Any], expected_count: int, profile: dict[str, Any] | None=None) -> dict[str, Any]:
    return _accessory_profile_payloads.required_accessory_profile_payload(item, expected_count, profile)

def resolve_required_accessory_refs(required_refs: list[Any]) -> list[dict[str, Any]]:
    return _accessory_profile_payloads.resolve_required_accessory_refs(required_refs)

def provider_generate_json_error_payload(settings: dict[str, Any], meta: dict[str, Any], exc: BaseException | str, *, timed_out: bool=False, overloaded: bool=False, latency_ms: int=0) -> dict[str, Any]:
    return _model_tool_dispatch.provider_generate_json_error_payload(settings, meta, exc, timed_out=timed_out, overloaded=overloaded, latency_ms=latency_ms)

def tool_provider_gemini_generate_json(payload: dict[str, Any]) -> dict[str, Any]:
    return _model_tool_dispatch.tool_provider_gemini_generate_json(payload)

def tool_accessory_reference_collect(payload: dict[str, Any]) -> dict[str, Any]:
    return _reference_collection.tool_accessory_reference_collect(payload)

def load_ai_profile_cache() -> dict[str, Any]:
    return _profile_cache_store.load_ai_profile_cache()

def save_ai_profile_cache(cache: dict[str, Any]) -> None:
    return _profile_cache_store.save_ai_profile_cache(cache)

def required_accessory_cache_key(required_accessories: list[dict[str, Any]], settings: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    return _profile_cache_policy.required_accessory_cache_key(required_accessories, settings)

def fit_image_into_cell(image: np.ndarray, width: int, height: int) -> np.ndarray:
    return _reference_tile_renderer.fit_image_into_cell(image, width, height)

def build_reference_sheet_descriptor(required_accessories: list[dict[str, Any]]) -> dict[str, Any] | None:
    return _reference_sheet.build_reference_sheet_descriptor(required_accessories)

def profile_reference_descriptors(required_accessories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _profile_cache_policy.profile_reference_descriptors(required_accessories)

def cached_profile_context_content(required_accessories: list[dict[str, Any]], references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _profile_cache_policy.cached_profile_context_content(required_accessories, references)

def ensure_required_profile_cache(required_accessories: list[dict[str, Any]], settings: dict[str, Any]) -> dict[str, Any]:
    return _profile_cache_flow.ensure_required_profile_cache(required_accessories, settings)

def tool_accessory_profile_generate(payload: dict[str, Any]) -> dict[str, Any]:
    return _accessory_profile_generation.tool_accessory_profile_generate(payload)

def tool_vision_inspect_presence(payload: dict[str, Any]) -> dict[str, Any]:
    return _presence_inspection.tool_vision_inspect_presence(payload)

def call_ai_mcp_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _model_tool_dispatch.call_ai_mcp_tool(tool_name, payload)

def generate_accessory_ai_profile(item: dict[str, Any], *, allow_provider: bool=True) -> dict[str, Any]:
    return _accessory_profile_generation.generate_accessory_ai_profile(item, allow_provider=allow_provider)

def ensure_accessory_ai_profile(item: dict[str, Any], *, force: bool=False, allow_provider: bool=True) -> bool:
    return _accessory_profile_generation.ensure_accessory_ai_profile(item, force=force, allow_provider=allow_provider)

def clean_sprite_assets(item: dict[str, Any]) -> list[dict[str, Any]]:
    return _sprite_asset_catalog.clean_sprite_assets(item)

def clean_sprite_material_policy_matches(item: dict[str, Any], asset: dict[str, Any]) -> bool:
    return _sprite_asset_catalog.clean_sprite_material_policy_matches(item, asset)

def clean_sprites_policy_complete(item: dict[str, Any], assets: list[dict[str, Any]] | None=None) -> bool:
    return _sprite_asset_catalog.clean_sprites_policy_complete(item, assets)

def canonical_text_assets(item: dict[str, Any]) -> list[dict[str, Any]]:
    return _text_asset_catalog.canonical_text_assets(item)

def canonical_text_assets_complete(item: dict[str, Any], assets: list[dict[str, Any]] | None=None) -> bool:
    return _text_asset_catalog.canonical_text_assets_complete(item, assets)

def available_object_pose_families(item: dict[str, Any]) -> list[str]:
    return _preview_pose_policy.available_object_pose_families(item)

def normalize_preview_pose_family_policy(value: str | None) -> str:
    return _preview_pose_policy.normalize_preview_pose_family_policy(value)

def preview_pose_family_for_policy(accessories: list[dict[str, Any]], policy: str) -> str | None:
    return _preview_pose_policy.preview_pose_family_for_policy(accessories, policy)

def preview_pose_families_for_policy(accessories: list[dict[str, Any]], policy: str) -> list[str]:
    return _preview_pose_policy.preview_pose_families_for_policy(accessories, policy)

def preview_pose_family_sequence(accessories: list[dict[str, Any]], count: int, policy: str='auto') -> list[str | None]:
    return _preview_pose_policy.preview_pose_family_sequence(accessories, count, policy)

def preview_pose_family_sequence_label(sequence: list[str | None]) -> str | None:
    return _preview_pose_policy.preview_pose_family_sequence_label(sequence)

def object_physical_size_mm(size: dict[str, Any] | None) -> tuple[float, float, float]:
    return _sprite_footprint.object_physical_size_mm(size)

def pose_family_is_top_view(pose_family: str, source_size_px: list[int] | tuple[int, int] | None=None) -> bool:
    return _sprite_footprint.pose_family_is_top_view(pose_family, source_size_px)

def oriented_long_short_pair_for_source(source_size_px: list[int] | tuple[int, int] | None, long_value: float, short_value: float) -> list[float]:
    return _sprite_footprint.oriented_long_short_pair_for_source(source_size_px, long_value, short_value)

def pose_render_footprint_metadata(pose_family: str, source_size_px: list[int] | tuple[int, int], physical_size: dict[str, Any] | None) -> dict[str, Any]:
    return _sprite_footprint.pose_render_footprint_metadata(pose_family, source_size_px, physical_size)

def median_source_major_axis_px(assets: list[dict[str, Any]], canonical_family: str) -> float | None:
    return _sprite_scale.median_source_major_axis_px(assets, canonical_family)

def upright_scale_correction_for_assets(assets: list[dict[str, Any]], physical_size: dict[str, Any] | None) -> dict[str, Any]:
    return _sprite_scale.upright_scale_correction_for_assets(assets, physical_size)

def apply_upright_scale_correction_metadata(assets: list[dict[str, Any]], physical_size: dict[str, Any] | None) -> None:
    return _sprite_scale.apply_upright_scale_correction_metadata(assets, physical_size)

def asset_visible_shape_px(asset: dict[str, Any]) -> tuple[int, int] | None:
    return _sprite_render_metadata.asset_visible_shape_px(asset)

def apply_laying_standard_render_size_hints(assets: list[dict[str, Any]]) -> None:
    return _sprite_render_metadata.apply_laying_standard_render_size_hints(assets)

def sprite_render_size_px(item: dict[str, Any], sprite_meta: dict[str, Any] | None, material_type: str) -> tuple[int, int]:
    return _sprite_render_metadata.sprite_render_size_px(item, sprite_meta, material_type)

def material_aware_object_alpha(asset: np.ndarray, mask: np.ndarray, metadata: dict[str, Any] | None=None) -> tuple[np.ndarray, dict[str, Any]]:
    return _material_alpha.material_aware_object_alpha(asset, mask, metadata)

def masked_major_axis_angle(mask: np.ndarray) -> tuple[float, float]:
    return _sprite_geometry.masked_major_axis_angle(mask)

def rotate_masked_asset(asset: np.ndarray, mask: np.ndarray, angle: float) -> tuple[np.ndarray, np.ndarray]:
    return _sprite_geometry.rotate_masked_asset(asset, mask, angle)

def restore_object_sprite_source_orientation_for_render(asset: np.ndarray, mask: np.ndarray, sprite_meta: dict[str, Any], *, top_view_pose: bool) -> tuple[np.ndarray, np.ndarray, float, float]:
    return _preview_sprite_renderer.restore_object_sprite_source_orientation_for_render(asset, mask, sprite_meta, top_view_pose=top_view_pose)

def normalize_sprite_upright(asset: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    return _sprite_geometry.normalize_sprite_upright(asset, mask)

def write_clean_sprite(path: Path, asset: np.ndarray, mask: np.ndarray, metadata: dict[str, Any] | None=None) -> dict[str, Any] | None:
    return _sprite_artifact_writer.write_clean_sprite(path, asset, mask, metadata)

def normalize_sprite_family_canvases(generated: list[dict[str, Any]]) -> None:
    return _sprite_canvas_normalizer.normalize_sprite_family_canvases(generated)

def filter_cutout_to_focus_cell(asset: np.ndarray, mask: np.ndarray, focus_bbox: tuple[int, int, int, int]) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    return _crop_selection.filter_cutout_to_focus_cell(asset, mask, focus_bbox)

def usable_object_cutout(cutout: tuple[np.ndarray, np.ndarray] | None, source_shape: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray] | None:
    return _crop_selection.usable_object_cutout(cutout, source_shape)

def cleanup_crop_alpha_components(asset: np.ndarray, alpha: np.ndarray, anchor_xy: tuple[float, float] | None=None, min_area: int=35) -> tuple[np.ndarray, dict[str, Any]]:
    return _crop_selection.cleanup_crop_alpha_components(asset, alpha, anchor_xy, min_area)

def preprocess_object_clean_sprites(item: dict[str, Any], allow_ai_cutout: bool=True, force: bool=False) -> bool:
    return _object_sprite_preprocessor.preprocess_object_clean_sprites(item, allow_ai_cutout, force)

def object_cutout_from_image(image: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray] | None:
    return _cutout_selection.object_cutout_from_image(image, rng)

def rembg_session() -> Any | None:
    return _rembg_runtime.rembg_session()

def ai_background_cutout_with_bbox(image: np.ndarray) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    return _background_cutouts.ai_background_cutout_with_bbox(image)

def ai_background_cutout(image: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    return _cutout_selection.ai_background_cutout(image)

def green_screen_object_cutout_with_bbox(image: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    return _cutout_selection.green_screen_object_cutout_with_bbox(image, rng)

def green_screen_object_cutout(image: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray] | None:
    return _cutout_selection.green_screen_object_cutout(image, rng)

def grid_position_for_center(center: tuple[int, int], roi: tuple[int, int, int, int]=BACKGROUND_ROI_PX) -> str:
    return _pose_grid_policy.grid_position_for_center(center, roi)

def grid_row_col(position: str | None) -> tuple[int, int] | None:
    return _pose_grid_policy.grid_row_col(position)

def grid_position_from_row_col(row: int, col: int) -> str:
    return _pose_grid_policy.grid_position_from_row_col(row, col)

def source_position_for_rotated_target(target_position: str | None, rotation_degrees: float) -> str | None:
    """Pick the source grid cell that rotates into the requested target cell."""
    return _pose_grid_policy.source_position_for_rotated_target(target_position, rotation_degrees)

def source_position_for_render_policy(target_position: str | None, rotation_degrees: float, pose_family: str | None, rng: np.random.Generator) -> str | None:
    return _pose_grid_policy.source_position_for_render_policy(target_position, rotation_degrees, pose_family, rng)

def object_render_pose_policy(pose_family: str | None, rng: np.random.Generator) -> dict[str, Any]:
    return _pose_grid_policy.object_render_pose_policy(pose_family, rng)

def pose_selection_reason(target_position: str | None, source_position: str | None, rotation_degrees: float) -> str:
    return _pose_grid_policy.pose_selection_reason(target_position, source_position, rotation_degrees)

def object_pose_render_size_hint(item: dict[str, Any], pose_family: str | None) -> tuple[int, int]:
    return _pose_candidate_policy.object_pose_render_size_hint(item, pose_family)

def filter_complete_pose_candidates(candidates: list[dict[str, Any]], pose_family: str | None) -> list[dict[str, Any]]:
    return _pose_candidate_policy.filter_complete_pose_candidates(candidates, pose_family)

def choose_object_pose_family(sprites: list[dict[str, Any]], rng: np.random.Generator) -> str | None:
    return _pose_candidate_policy.choose_object_pose_family(sprites, rng)

def load_object_preview_sprite(item: dict[str, Any], rng: np.random.Generator, target_position: str | None=None, pose_family: str | None=None, source_position: str | None=None) -> tuple[np.ndarray, np.ndarray, dict[str, Any]] | None:
    return _preview_sprite_renderer.load_object_preview_sprite(item, rng, target_position, pose_family, source_position)

def paste_masked_asset(canvas: np.ndarray, asset: np.ndarray, mask: np.ndarray, center: tuple[int, int], target_size: tuple[int, int], angle: float, trim_before_paste: bool=True, return_visible_mask: bool=False, resize_to_target: bool=True) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
    return _asset_compositor.paste_masked_asset(canvas, asset, mask, center, target_size, angle, trim_before_paste, return_visible_mask, resize_to_target)

def visible_mask_size_px(mask: np.ndarray) -> list[int]:
    return _sprite_geometry.visible_mask_size_px(mask)

def resize_masked_asset_to_visible_footprint(asset: np.ndarray, mask: np.ndarray, target_size: tuple[int, int], preserve_aspect_ratio: bool=False) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    return _sprite_geometry.resize_masked_asset_to_visible_footprint(asset, mask, target_size, preserve_aspect_ratio)

def paste_physical_object_asset(canvas: np.ndarray, asset: np.ndarray, mask: np.ndarray, center: tuple[int, int], target_long_side_px: int, target_short_side_px: int, angle: float, preserve_aspect_ratio: bool=False) -> dict[str, Any]:
    return _asset_compositor.paste_physical_object_asset(canvas, asset, mask, center, target_long_side_px, target_short_side_px, angle, preserve_aspect_ratio)

def paste_rotated_asset(canvas: np.ndarray, asset: np.ndarray, center: tuple[int, int], target_size: tuple[int, int], angle: float) -> np.ndarray:
    return _asset_compositor.paste_rotated_asset(canvas, asset, center, target_size, angle)

def normalize_accessory_assets(item: dict[str, Any]) -> dict[str, Any]:
    return _accessory_preparation.normalize_accessory_assets(item)

def frame_detail_score(frame: np.ndarray) -> float:
    return _accessory_reference_media.frame_detail_score(frame)

def frame_histogram(frame: np.ndarray) -> np.ndarray:
    return _accessory_reference_media.frame_histogram(frame)

def extract_video_reference_frames(video_path: Path, output_dir: Path, max_frames: int=MAX_VIDEO_REFERENCE_FRAMES) -> list[dict[str, Any]]:
    return _accessory_reference_media.extract_video_reference_frames(video_path, output_dir, max_frames)

def expand_accessory_reference_sources(candidate_id: str, source_files: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    return _accessory_preparation.expand_accessory_reference_sources(candidate_id, source_files)

def write_thumbnail(image: np.ndarray, out_path: Path, angle: float=0.0, size: int=360) -> dict[str, Any]:
    return _accessory_reference_media.write_thumbnail(image, out_path, angle, size)

def pose_collection_dimension_text(item: dict[str, Any]) -> str:
    return _pose_collection_prompts.pose_collection_dimension_text(item)

def tabletop_scene_text(surface_mode: str='white') -> str:
    return _pose_collection_prompts.tabletop_scene_text(surface_mode)

def pose_collection_camera_grid_text(item: dict[str, Any], surface_mode: str='white') -> str:
    return _pose_collection_prompts.pose_collection_camera_grid_text(item, surface_mode)

def pose_collection_position_specs(item: dict[str, Any]) -> dict[str, str]:
    return _pose_collection_prompts.pose_collection_position_specs(item)

def pose_collection_camera_batch_text(item: dict[str, Any], batch_key: str | None, surface_mode: str='white') -> str:
    return _pose_collection_prompts.pose_collection_camera_batch_text(item, batch_key, surface_mode)

def upright_spatial_relation_text() -> str:
    return _pose_collection_prompts.upright_spatial_relation_text()

def build_pose_collection_prompt(item: dict[str, Any], pose_family: str='combined', batch_key: str | None=None, surface_mode: str='reference') -> str:
    return _pose_collection_prompts.build_pose_collection_prompt(item, pose_family, batch_key, surface_mode)

def build_white_table_replacement_prompt(item: dict[str, Any], pose_family: str) -> str:
    return _pose_collection_prompts.build_white_table_replacement_prompt(item, pose_family)

def build_anchor_replacement_pose_prompt(item: dict[str, Any], pose_family: str) -> str:
    return _pose_collection_prompts.build_anchor_replacement_pose_prompt(item, pose_family)

def safe_record_id(value: Any) -> str:
    return _pose_collection_jobs.safe_record_id(value)

def pose_collection_output_dir(item: dict[str, Any]) -> Path:
    return _pose_collection_jobs.pose_collection_output_dir(item)

def pose_collection_output_name(pose_family: str) -> str:
    return _pose_collection_jobs.pose_collection_output_name(pose_family)

def pose_collection_job_id(item: dict[str, Any], pose_family: str) -> str:
    return _pose_collection_jobs.pose_collection_job_id(item, pose_family)

def source_reference_inputs_for_pose_job(item: dict[str, Any], pose_family: str) -> list[str]:
    return _pose_collection_jobs.source_reference_inputs_for_pose_job(item, pose_family)

def make_pose_collection_job(item: dict[str, Any], pose_family: str) -> dict[str, Any]:
    return _pose_collection_jobs.make_pose_collection_job(item, pose_family)

def ensure_pose_collection_image_jobs(item: dict[str, Any]) -> bool:
    return _pose_collection_jobs.ensure_pose_collection_image_jobs(item)

def pending_pose_collection_jobs(item: dict[str, Any]) -> list[dict[str, Any]]:
    return _pose_collection_jobs.pending_pose_collection_jobs(item)

def pose_collection_pending_detail(item: dict[str, Any], pending: list[dict[str, Any]]) -> str:
    return _pose_collection_jobs.pose_collection_pending_detail(item, pending)

def create_accessory_candidate(name: str, material_type: str, training_role: str, source_files: list[str], physical_size: dict[str, Any] | None=None, material_alpha_policy: str | None=None, size_reference: str | None=None) -> dict[str, Any]:
    return _candidate_factory.create_accessory_candidate(name, material_type, training_role, source_files, physical_size, material_alpha_policy, size_reference)

def load_accessory_candidate(candidate_id: str) -> dict[str, Any]:
    return _candidate_repository.load_accessory_candidate(candidate_id)

def save_accessory_candidate(path: Path, candidate: dict[str, Any]) -> None:
    return _candidate_repository.save_accessory_candidate(path, candidate)

def delete_accessory_candidate(candidate_id: str, path: Path | None=None) -> bool:
    return _candidate_repository.delete_accessory_candidate(candidate_id, path)

def cleanup_accessory_candidate_artifacts(candidate: dict[str, Any]) -> list[str]:
    """Remove only directories that are unambiguously owned by a pending candidate."""
    return _candidate_artifacts.cleanup_accessory_candidate_artifacts(candidate)

def accessory_candidate_record_path(candidate: dict[str, Any], fallback_id: str='candidate') -> Path:
    return _candidate_repository.accessory_candidate_record_path(candidate, fallback_id)

def list_accessory_candidate_records(*, reverse: bool=True) -> list[tuple[Path, dict[str, Any]]]:
    return _candidate_repository.list_accessory_candidate_records(reverse=reverse)

def write_accessory_candidate_file(path: Path, candidate: dict[str, Any]) -> None:
    return _candidate_repository.write_accessory_candidate_file(path, candidate)

def mutate_candidate_image_job(path: Path, candidate: dict[str, Any], job: dict[str, Any], updates: dict[str, Any], *, preprocess_clean_sprites: bool=False) -> dict[str, Any]:
    return _image_job_queue.mutate_candidate_image_job(path, candidate, job, updates, preprocess_clean_sprites=preprocess_clean_sprites)

def image_job_prompt(job: dict[str, Any]) -> str:
    return _image_provider_configuration.image_job_prompt(job)

def image_job_is_active(status: str) -> bool:
    return _image_worker_diagnostics.image_job_is_active(status)

def codex_log_has_generated_image(log_path: Path) -> bool:
    return _image_worker_diagnostics.codex_log_has_generated_image(log_path)

def image_job_output_path(job: dict[str, Any], *, for_write: bool=False) -> Path:
    return _image_worker_diagnostics.image_job_output_path(job, for_write=for_write)

def image_job_log_path(job: dict[str, Any]) -> Path:
    return _image_worker_diagnostics.image_job_log_path(job)

def read_image_worker_log_tail(log_path: Path) -> str:
    return _image_worker_diagnostics.read_image_worker_log_tail(log_path)

def classify_image_worker_failure(log_path: Path, return_code: int | None, output_path: Path, *, stale: bool=False) -> str:
    return _image_worker_diagnostics.classify_image_worker_failure(log_path, return_code, output_path, stale=stale)

def image_worker_process_alive(job_id: str) -> bool:
    return _image_worker_diagnostics.image_worker_process_alive(job_id)

def codex_process_has_log_open(log_path: Path) -> bool:
    return _image_worker_diagnostics.codex_process_has_log_open(log_path)

def image_job_has_live_worker(job: dict[str, Any], log_path: Path) -> bool:
    return _image_worker_diagnostics.image_job_has_live_worker(job, log_path)

def running_image_job_is_stale(job: dict[str, Any], log_path: Path) -> bool:
    return _image_worker_diagnostics.running_image_job_is_stale(job, log_path)

def next_queued_image_job() -> tuple[Path, dict[str, Any], dict[str, Any]] | None:
    return _image_job_queue.next_queued_image_job()

def cursor_image_model_score(model_id: str) -> tuple[int, int]:
    return _image_provider_configuration.cursor_image_model_score(model_id)

def inspect_cursor_image_models(agent_config: dict[str, Any]) -> dict[str, Any]:
    return _image_provider_configuration.inspect_cursor_image_models(agent_config)

def cursor_image2_settings() -> dict[str, Any]:
    return _image_provider_configuration.cursor_image2_settings()

def public_cursor_image2_status() -> dict[str, Any]:
    return _image_provider_configuration.public_cursor_image2_status()

def image_file_payload(path: Path) -> dict[str, str]:
    return _image_payload_codec.image_file_payload(path)

def cursor_image2_payload(job: dict[str, Any], input_files: list[str], settings: dict[str, Any]) -> dict[str, Any]:
    return _image_provider_configuration.cursor_image2_payload(job, input_files, settings)

def cursor_image2_response_candidates(payload: Any) -> list[dict[str, Any]]:
    return _image_provider_configuration.cursor_image2_response_candidates(payload)

def extract_cursor_image2_bytes(payload: dict[str, Any], settings: dict[str, Any]) -> bytes:
    return _image_provider_configuration.extract_cursor_image2_bytes(payload, settings)

def windows_worker_image_response_bytes(payload: dict[str, Any]) -> bytes:
    return _image_payload_codec.windows_worker_image_response_bytes(payload)

def run_windows_worker_image_job(path: Path, candidate: dict[str, Any], job: dict[str, Any], *, reason: str) -> bool:
    return _image_job_execution.run_windows_worker_image_job(path, candidate, job, reason=reason)

def run_cursor_image2_job(path: Path, candidate: dict[str, Any], job: dict[str, Any]) -> None:
    return _image_job_execution.run_cursor_image2_job(path, candidate, job)

def run_cos_codex_image_job(path: Path, candidate: dict[str, Any], job: dict[str, Any], runtime) -> None:
    return _image_job_execution.run_cos_codex_image_job(path, candidate, job, runtime)

def run_codex_image_job(path: Path, candidate: dict[str, Any], job: dict[str, Any]) -> None:
    return _image_job_execution.run_codex_image_job(path, candidate, job)

@pinned_model_profiles(resolve_model_profiles, argument=2)
def run_image_generation_job(path: Path, candidate: dict[str, Any], job: dict[str, Any]) -> None:
    return _image_job_execution.run_image_generation_job(path, candidate, job)

def image_worker_loop() -> None:
    return _image_job_queue.image_worker_loop()

def refresh_codex_image_job(job: dict[str, Any]) -> dict[str, Any]:
    return _image_job_management.refresh_codex_image_job(job)

def public_image_job(job: dict[str, Any]) -> dict[str, Any]:
    return _image_job_management.public_image_job(job)

def public_accessory_detail_item(item: dict[str, Any]) -> dict[str, Any]:
    return _accessory_gallery.public_accessory_detail_item(item)

def refreshed_public_codex_jobs_for_record(record: dict[str, Any], *, fallback_path: Path | None=None, job_store: str='candidate') -> tuple[list[dict[str, Any]], bool]:
    return _image_job_management.refreshed_public_codex_jobs_for_record(record, fallback_path=fallback_path, job_store=job_store)

def list_codex_image_jobs(user: dict[str, Any] | None=None, target_user_id: str | None=None) -> list[dict[str, Any]]:
    return _image_job_management.list_codex_image_jobs(user, target_user_id)

def apply_codex_image_job_action(record: dict[str, Any], job: dict[str, Any], lookup_id: str, action: str) -> dict[str, Any]:
    return _image_job_management.apply_codex_image_job_action(record, job, lookup_id, action)

def update_codex_image_job(job_id: str, action: str) -> dict[str, Any]:
    return _image_job_management.update_codex_image_job(job_id, action)

def stop_candidate_image_task(candidate: dict[str, Any]) -> int:
    return _image_job_management.stop_candidate_image_task(candidate)

def update_codex_image_candidate(candidate_id: str, action: str) -> dict[str, Any]:
    return _image_job_management.update_codex_image_candidate(candidate_id, action)

def write_gallery_preview(src: Path, out_path: Path, max_side: int=1200) -> dict[str, Any] | None:
    return _accessory_gallery.write_gallery_preview(src, out_path, max_side)

def existing_source_image_paths(item: dict[str, Any]) -> list[Path]:
    return _candidate_artifacts.existing_source_image_paths(item)

def ensure_default_ai_profile_reference(item: dict[str, Any]) -> bool:
    return _accessory_preparation.ensure_default_ai_profile_reference(item)

def refresh_accessory_assets_after_source_change(item: dict[str, Any], *, force_profile: bool=True) -> None:
    return _accessory_refresh.refresh_accessory_assets_after_source_change(item, force_profile=force_profile)

def accessory_detail_payload(item: dict[str, Any]) -> dict[str, Any]:
    return _accessory_gallery.accessory_detail_payload(item)

def selected_accessories(config: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
    return _accessory_selection.selected_accessories(config, ids)

def physical_render_size_px(item: dict[str, Any], material_type: str) -> tuple[int, int]:
    return _reference_dimensions.physical_render_size_px(item, material_type)

def accessory_lookup_by_id(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _accessory_lookup.accessory_lookup_by_id(config)

def accessory_id_aliases(item: dict[str, Any]) -> list[str]:
    return _accessory_lookup.accessory_id_aliases(item)

def resolve_accessory_id(config: dict[str, Any], accessory_id: str) -> tuple[str, dict[str, Any]] | None:
    return _accessory_selection.resolve_accessory_id(config, accessory_id)

def load_ai_detection_tasks() -> list[dict[str, Any]]:
    return _detection_task_store.load_ai_detection_tasks()

def save_ai_detection_tasks(tasks: list[dict[str, Any]]) -> None:
    return _detection_task_store.save_ai_detection_tasks(tasks)

def find_ai_detection_task(task_id: str) -> dict[str, Any] | None:
    return _detection_task_store.find_ai_detection_task(task_id)

def save_ai_detection_task(task: dict[str, Any], *, prepend: bool=False) -> None:
    return _detection_task_store.save_ai_detection_task(task, prepend=prepend)

def serialize_ai_detection_task(task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return _detection_task_projection.serialize_ai_detection_task(task, config)

def list_ai_detection_task_model_specs(config: dict[str, Any] | None=None, target_user_id: str | None=None) -> list[dict[str, Any]]:
    return _detection_task_catalog.list_ai_detection_task_model_specs(config, target_user_id)

def ai_detection_task_payload_from_request(request: AiDetectionTaskRequest, config: dict[str, Any]) -> dict[str, Any]:
    return _detection_task_projection.ai_detection_task_payload_from_request(request, config)

def ai_detection_tasks_response(config: dict[str, Any], selected_id: str | None=None, *, user: dict[str, Any] | None=None, target_user_id: str | None=None) -> dict[str, Any]:
    return _detection_task_catalog.ai_detection_tasks_response(config, selected_id, user=user, target_user_id=target_user_id)

def list_ai_detection_specialized_model_specs(config: dict[str, Any] | None=None, trained_specs: list[dict[str, Any]] | None=None, target_user_id: str | None=None) -> list[dict[str, Any]]:
    return _detection_task_catalog.list_ai_detection_specialized_model_specs(config, trained_specs, target_user_id)

def model(model_id: str | None=None, config: dict[str, Any] | None=None) -> YOLO:
    return _local_models.model(model_id, config)

def yolo_warmup_configured_model_ids(config: dict[str, Any]) -> list[str]:
    return _warmup_candidates.yolo_warmup_configured_model_ids(config)

def warm_yolo_model_once(model_id: str, config: dict[str, Any]) -> None:
    return _warmup_prediction.warm_yolo_model_once(model_id, config)

def yolo_warmup_status() -> dict[str, Any]:
    return _yolo_warmup_runtime.yolo_warmup_status()

def public_yolo_warmup_status(config: dict[str, Any]) -> dict[str, Any]:
    return _yolo_warmup_runtime.public_yolo_warmup_status(config)

def yolo_warmup_worker(reason: str='startup', model_ids: list[str] | None=None) -> None:
    return _yolo_warmup_runtime.yolo_warmup_worker(reason, model_ids)

def start_yolo_warmup(reason: str='startup', model_ids: list[str] | None=None) -> None:
    return _yolo_warmup_runtime.start_yolo_warmup(reason, model_ids, worker=lambda: yolo_warmup_worker)

def ocr_engine() -> Any:
    return _detection_ocr_engine.get()

def ai_required_accessories(config: dict[str, Any], spec: dict[str, Any]) -> list[tuple[dict[str, Any], int]]:
    return _required_accessories.ai_required_accessories(config, spec)

def ai_detection_task_payload(required_accessories: list[dict[str, Any]]) -> dict[str, Any]:
    return _presence_payload.ai_detection_task_payload(required_accessories)

def ai_presence_failure_payload(required_accessories: list[dict[str, Any]], settings: dict[str, Any], *, reason: str, timed_out: bool=False, latency_ms: int=0) -> dict[str, Any]:
    return _failure_projection.ai_presence_failure_payload(required_accessories, settings, reason=reason, timed_out=timed_out, latency_ms=latency_ms)

def ai_detection_failure_result(request_id: str, spec: dict[str, Any], required_items: list[tuple[dict[str, Any], int]], annotated_url: str, *, reason: str, timed_out: bool=False, latency_ms: int=0) -> dict[str, Any]:
    return _detection_failure_result.ai_detection_failure_result(request_id, spec, required_items, annotated_url, reason=reason, timed_out=timed_out, latency_ms=latency_ms)

def write_ai_original_output(image_bgr: np.ndarray, request_id: str) -> str:
    return _detection_annotation.write_ai_original_output(image_bgr, request_id)

def ai_box_2d_to_pixels(box_2d: Any, image_shape: tuple[int, ...]) -> tuple[int, int, int, int] | None:
    return _detection_annotation.ai_box_2d_to_pixels(box_2d, image_shape)

def draw_ai_detection_boxes(image_bgr: np.ndarray, detections: list[dict[str, Any]], rule: dict[str, Any]) -> np.ndarray | None:
    return _detection_annotation.draw_ai_detection_boxes(image_bgr, detections, rule)

def write_ai_annotated_output(image_bgr: np.ndarray, request_id: str, detections: list[dict[str, Any]], rule: dict[str, Any]) -> str:
    return _detection_annotation.write_ai_annotated_output(image_bgr, request_id, detections, rule)

def ai_model_payload(spec: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    return _failure_projection.ai_model_payload(spec, settings)

def normalize_ai_detection_result(parsed: dict[str, Any], required_accessories: list[dict[str, Any]], latency_ms: int, settings: dict[str, Any]) -> dict[str, Any]:
    return _presence_results.normalize_ai_detection_result(parsed, required_accessories, latency_ms, settings)

@pinned_model_profiles(resolve_model_profiles)
def analyze_bgr_ai_detection(image_bgr: np.ndarray, request_id: str, spec: dict[str, Any], config: dict[str, Any], *, image_path: Path | None=None) -> dict[str, Any]:
    return _ai_detection_analysis.analyze_bgr_ai_detection(image_bgr, request_id, spec, config, image_path=image_path)

def analyze_bgr(image_bgr: np.ndarray, request_id: str, model_id: str | None=None, *, image_path: Path | None=None) -> dict[str, Any]:
    return _detection_analysis.analyze_bgr(image_bgr, request_id, model_id, image_path=image_path)

def delete_ai_detection_task_record(task_id: str, user: dict[str, Any], *, missing_ok: bool=False) -> str | None:
    return _detection_task_requests.delete_ai_detection_task_record(task_id, user, missing_ok=missing_ok)

def video_ai_summary(frames: list[dict[str, Any]]) -> dict[str, Any] | None:
    return _video_summary.video_ai_summary(frames)

def suppress_chroma_spill(image_bgr: np.ndarray, screen: dict[str, Any] | None=None) -> np.ndarray:
    return _chroma_cutouts.suppress_chroma_spill(image_bgr, screen)

def chroma_background_mask(image_bgr: np.ndarray, screen: dict[str, Any] | None=None) -> np.ndarray:
    return _chroma_cutouts.chroma_background_mask(image_bgr, screen)

def chroma_distance_alpha(image_bgr: np.ndarray, screen: dict[str, Any] | None=None) -> np.ndarray:
    return _chroma_cutouts.chroma_distance_alpha(image_bgr, screen)

def chroma_screen_object_cutout(image_bgr: np.ndarray, screen: dict[str, Any] | None=None) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    """Remove a fixed solid chroma tabletop/background and keep the largest object."""
    return _chroma_cutouts.chroma_screen_object_cutout(image_bgr, screen)

def precise_green_plate_cutout(image_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    """High-precision cut-out of the single object on an AI green-conveyor plate
    using the local AI matte (rembg/u2net). Keeps the FULL silhouette (thin ends,
    corrugations, caps — no erosion) and only trims unambiguous bright-green halo
    pixels. Falls back to None when rembg is unavailable so callers can use the
    chroma-key path."""
    return _background_cutouts.precise_green_plate_cutout(image_bgr)

def green_conveyor_object_cutout(image_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    """Chroma-key a single object off an AI-generated green-conveyor plate.
    Removes green (and green-tinted cast-shadow) pixels, keeps the largest
    non-green blob, fills interior holes. Used as the fallback when the AI matte
    is unavailable; tuned to avoid biting into dark object edges or thin features
    (no aggressive open/erode that would shave a thin part's silhouette)."""
    return _chroma_cutouts.green_conveyor_object_cutout(image_bgr)

def build_clean_sprites_from_photo_highlight_masks(task: dict[str, Any], item: dict[str, Any], provider: GeminiAiProvider | AgnesImageProvider, model: str, *, force: bool=False) -> tuple[bool, str]:
    return _photo_highlight_sprite_builder.build_clean_sprites_from_photo_highlight_masks(task, item, provider, model, force=force)

def derive_background_plate_from_accessory(item: dict[str, Any], out_path: Path) -> Path | None:
    """Build an empty background plate from the first accessory's own capture
    environment by segmenting out every foreground object and inpainting the
    holes, leaving only the bare work surface. This guarantees a
    first-accessory-derived task background even when the image model declines to
    synthesize an empty surface. Returns the written plate path or None."""
    return _background_plate_derivation.derive_background_plate_from_accessory(item, out_path)

def background_reference_signatures_from_accessory(item: dict[str, Any]) -> list[dict[str, Any]]:
    return _background_reference_signatures.background_reference_signatures_from_accessory(item)

def background_set_visible_for_owner(meta: dict[str, Any], owner_id: str) -> bool:
    return _background_candidate_catalog.background_set_visible_for_owner(meta, owner_id)

def background_library_image_candidates(owner_id: str) -> list[tuple[str, Path, dict[str, Any]]]:
    return _background_candidate_catalog.background_library_image_candidates(owner_id)

def match_background_library_plate(item: dict[str, Any], owner_id: str) -> dict[str, Any] | None:
    return _background_library_matcher.match_background_library_plate(item, owner_id)
