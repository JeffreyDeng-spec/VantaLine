"""Static application wiring; original narrow business ports remain the boundary.

Only the canonical assembler consumes this result. Business components receive
their existing narrow ports; no application-entry callback is used.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import MutableMapping
from typing import Any, Callable
import contextvars
import _thread
from ..application_values import ApplicationValues
from typing import Any
from local_inspection_service.text_inspection.beta_comparison import BetaComparison
from local_inspection_service.text_inspection.beta_comparison import BetaPolicy
from typing import Callable
from local_inspection_service.text_inspection.comparison_composition import ComparisonAudit
from local_inspection_service.text_inspection.comparison_composition import ComparisonImages
from local_inspection_service.codex_compare.dependencies import ComparisonMedia
from local_inspection_service.text_inspection.comparison_ports import ComparisonModels
from local_inspection_service.text_inspection.document_ports import DocumentModels
from local_inspection_service.text_inspection.extraction_ports import ExtractionModels
from local_inspection_service.text_inspection.incoming_ports import IncomingAccess
from local_inspection_service.text_inspection.incoming_retention import IncomingCapacity
from local_inspection_service.text_inspection.incoming_ports import IncomingImaging
from local_inspection_service.text_inspection.incoming_ports import IncomingMedia
from local_inspection_service.text_inspection.incoming_ports import IncomingOCR
from local_inspection_service.text_inspection.incoming_analysis import IncomingOCREngine
from local_inspection_service.text_inspection.incoming_store import IncomingPaths
from local_inspection_service.text_inspection.incoming_store import IncomingRows
from local_inspection_service.text_inspection.incoming_access import IncomingTaskAccess
from local_inspection_service.text_inspection.incoming_ports import IncomingTasks
from local_inspection_service.text_inspection.incoming_composition import IncomingWorkflows
from local_inspection_service.text_inspection.inspection_ports import InspectionAccess
from local_inspection_service.label_inspection.dependencies import LabelImports
from pathlib import Path
from local_inspection_service.text_inspection.preparation_ports import PreparationModels
from local_inspection_service.label_inspection.dependencies import RepositoryLifecycle
from local_inspection_service.text_inspection.standard_ports import StandardAccess
from local_inspection_service.codex_compare.dependencies import StandardLibrary
from local_inspection_service.text_inspection.standard_composition import StandardMediaStorage
from local_inspection_service.text_inspection.standard_ports import StandardParsers
from local_inspection_service.text_inspection.standard_composition import StandardPolicy
from local_inspection_service.text_inspection.standard_composition import StandardThreadScope
from local_inspection_service.text_inspection.inspection_ports import SubmissionDiagnostics
from local_inspection_service.text_inspection.inspection_ports import SubmissionModels
from local_inspection_service.text_inspection.inspection_ports import SubmissionPolicy
from local_inspection_service.text_inspection.record_store import TEXT_INSPECTION_TABLES
from local_inspection_service.text_inspection.comparison_composition import TextComparisonWorkflows
from local_inspection_service.text_inspection.diagnostics import TextDiagnostics
from local_inspection_service.incoming_text_inspection import TextObservation
from local_inspection_service.text_inspection.standard_composition import TextStandardWorkflows
from local_inspection_service.text_inspection.storage_composition import TextStorage
from local_inspection_service.text_inspection.storage_composition import TextStorageJSON
from local_inspection_service.text_inspection.storage_composition import TextStoragePaths
from local_inspection_service.text_inspection.incoming_analysis import field_observation as _field_observation
from local_inspection_service.text_inspection.incoming_analysis import corroboration as _incoming_corroboration
from local_inspection_service.text_inspection.incoming_analysis import observations as _incoming_observations
from local_inspection_service.text_inspection.incoming_access import public_record as _incoming_public_record
from local_inspection_service.text_inspection.incoming_access import task_access_allowed as _incoming_task_access_allowed
from local_inspection_service.runtime.json_records import read_json_list as _incoming_text_json_list
from local_inspection_service.text_inspection.incoming_analysis import result_mapping as _ocr_result_mapping
from local_inspection_service.text_inspection.images import prepare_provider_image as _prepare_text_provider_image
from local_inspection_service import qwen_evidence_jobs as _qwen_evidence_policy
from local_inspection_service.runtime.json_records import write_json_list as _save_incoming_text_json_list
from local_inspection_service.text_inspection import preparation_policy as _standard_preparation_policy
from local_inspection_service.text_inspection.images import annotate as _text_v2_annotate
from local_inspection_service.text_inspection.revisions import confirmed_snapshot as _text_v2_confirmed_snapshot
from local_inspection_service.text_inspection.images import data_url as _text_v2_data_url
from local_inspection_service.text_inspection.diagnostics import diagnostic_event as _text_v2_diagnostic_event
from local_inspection_service.text_inspection.diagnostics import diagnostic_value as _text_v2_diagnostic_value
from local_inspection_service.text_inspection.revisions import expected_revision as _text_v2_expected_revision
from local_inspection_service.text_inspection.images import prepare_image as _text_v2_prepare_image
from local_inspection_service.text_inspection.diagnostics import provider_diagnostics as _text_v2_provider_diagnostics
from local_inspection_service.text_inspection.projection import public_record as _text_v2_public
from local_inspection_service.incoming_text_inspection import annotate_inspection
from local_inspection_service.incoming_text_inspection import assess_image_quality
from local_inspection_service.storage.runtime_records import audit_event_row
from local_inspection_service.runtime.text_policy import bounded_text
from local_inspection_service.text_inspection.incoming_analysis import decode_reference as decode_incoming_reference
from local_inspection_service.document_images import extract_doc_images
from local_inspection_service.text_inspection_v2 import extract_docx_candidates
from local_inspection_service.storage.runtime_records import incoming_text_inspection_row
from local_inspection_service.storage.runtime_records import incoming_text_reference_row
from local_inspection_service.text_inspection_v2 import inspect_pdf
from local_inspection_service.incoming_text_inspection import local_visual_similarity
from local_inspection_service.text_inspection_v2 import normalize_vlm_provider_result
import numpy as np
import os
from local_inspection_service.runtime.paddle import prepare_runtime as prepare_paddle_runtime
from local_inspection_service.incoming_text_inspection import rectify_label
from local_inspection_service.storage.runtime_records import row_raw_json_list
from local_inspection_service.text_inspection_v2 import sha256_bytes
from local_inspection_service.text_inspection_v2 import strict_compare_prompt
import urllib.error
import urllib.request
from local_inspection_service.auth.policy import user_is_admin
from local_inspection_service.text_inspection_v2 import validate_vlm_result
import local_inspection_service.auth.account_projections
import local_inspection_service.codex_compare.dependencies
import local_inspection_service.config.application_composition
import local_inspection_service.label_inspection.dependencies
import local_inspection_service.model_profiles.composition
import local_inspection_service.model_providers.agnes_transport
import local_inspection_service.model_providers.configuration_composition
import local_inspection_service.model_providers.gemini_transport
import local_inspection_service.model_providers.qwen_image_transport
import local_inspection_service.model_providers.selection
import local_inspection_service.model_providers.tool_dispatch
import local_inspection_service.pipeline.task_projection
import local_inspection_service.pipeline.task_store
import local_inspection_service.runtime.connections
import local_inspection_service.runtime.repository_access
import local_inspection_service.runtime.service_paths
import local_inspection_service.runtime.training_tasks
import local_inspection_service.storage.artifacts.files
import local_inspection_service.storage.artifacts.images
import local_inspection_service.text_inspection.beta_comparison
import local_inspection_service.text_inspection.comparison_composition
import local_inspection_service.text_inspection.comparison_runtime
import local_inspection_service.text_inspection.comparison_submission
import local_inspection_service.text_inspection.diagnostics
import local_inspection_service.text_inspection.document_ports
import local_inspection_service.text_inspection.extraction_ports
import local_inspection_service.text_inspection.history_ports
import local_inspection_service.text_inspection.incoming_access
import local_inspection_service.text_inspection.incoming_analysis
import local_inspection_service.text_inspection.incoming_catalog
import local_inspection_service.text_inspection.incoming_composition
import local_inspection_service.text_inspection.incoming_execution
import local_inspection_service.text_inspection.incoming_ports
import local_inspection_service.text_inspection.incoming_retention
import local_inspection_service.text_inspection.incoming_reviews
import local_inspection_service.text_inspection.incoming_store
import local_inspection_service.text_inspection.inspection_ports
import local_inspection_service.text_inspection.inspection_reviews
import local_inspection_service.text_inspection.media
import local_inspection_service.text_inspection.preparation_ports
import local_inspection_service.text_inspection.record_store
import local_inspection_service.text_inspection.revisions
import local_inspection_service.text_inspection.standard_composition
import local_inspection_service.text_inspection.standard_edits
import local_inspection_service.text_inspection.standard_imports
import local_inspection_service.text_inspection.standard_library
import local_inspection_service.text_inspection.standard_ports
import local_inspection_service.text_inspection.storage_composition

@dataclass(frozen=True)
class TextWiringInputs:
    AgnesImageProvider: Callable[[], type[local_inspection_service.model_providers.agnes_transport.AgnesImageProvider]]
    GeminiAiProvider: Callable[[], type[local_inspection_service.model_providers.gemini_transport.GeminiAiProvider]]
    QwenImageProvider: Callable[[], type[local_inspection_service.model_providers.qwen_image_transport.QwenImageProvider]]
    _account_projections: Callable[[], local_inspection_service.auth.account_projections.AccountProjections]
    _app_configuration: Callable[[], local_inspection_service.config.application_composition.ApplicationConfiguration]
    _business_files: Callable[[], local_inspection_service.storage.artifacts.files.BusinessFiles]
    _incoming_image_files: Callable[[], local_inspection_service.storage.artifacts.images.ImageFiles]
    _model_profile_configuration: Callable[[], local_inspection_service.model_profiles.composition.ModelConfiguration]
    _model_tool_dispatch: Callable[[], local_inspection_service.model_providers.tool_dispatch.ModelToolDispatch]
    _pipeline_task_store: Callable[[], local_inspection_service.pipeline.task_store.PipelineTaskStore]
    _provider_configuration: Callable[[], local_inspection_service.model_providers.configuration_composition.ProviderConfiguration]
    _provider_selection: Callable[[], local_inspection_service.model_providers.selection.ProviderSelection]
    _runtime_repositories: Callable[[], local_inspection_service.runtime.connections.ThreadRepositoryFactory]
    _runtime_repository_access: Callable[[], local_inspection_service.runtime.repository_access.RuntimeRepositoryAccess]
    _service_paths: Callable[[], local_inspection_service.runtime.service_paths.ServicePaths]
    _task_projection: Callable[[], local_inspection_service.pipeline.task_projection.PipelineTaskProjection]
    current_auth_user: Callable[[], Callable[..., Any]]
    record_owner_id: Callable[[], Callable[..., Any]]
    require_permission: Callable[[], Callable[..., Any]]
    require_record_access: Callable[[], Callable[..., Any]]

@dataclass(frozen=True)
class TextAssembly:
    _beta_comparison: local_inspection_service.text_inspection.beta_comparison.BetaComparison
    _codex_media: local_inspection_service.codex_compare.dependencies.ComparisonMedia
    _codex_standard_library: local_inspection_service.codex_compare.dependencies.StandardLibrary
    _comparison_submission: local_inspection_service.text_inspection.comparison_submission.ComparisonSubmission
    _document_models: local_inspection_service.text_inspection.document_ports.DocumentModels
    _document_records: local_inspection_service.text_inspection.document_ports.DocumentRecords
    _extraction_media: local_inspection_service.text_inspection.extraction_ports.ExtractionMedia
    _extraction_models: local_inspection_service.text_inspection.extraction_ports.ExtractionModels
    _extraction_records: local_inspection_service.text_inspection.extraction_ports.ExtractionRecords
    _history_media: local_inspection_service.text_inspection.history_ports.HistoryMedia
    _history_records: local_inspection_service.text_inspection.history_ports.HistoryRecords
    _incoming_access: local_inspection_service.text_inspection.incoming_ports.IncomingAccess
    _incoming_capacity: local_inspection_service.text_inspection.incoming_retention.IncomingCapacity
    _incoming_catalog: local_inspection_service.text_inspection.incoming_catalog.IncomingCatalog
    _incoming_execution: local_inspection_service.text_inspection.incoming_execution.IncomingExecution
    _incoming_inspections: local_inspection_service.text_inspection.incoming_ports.IncomingInspections
    _incoming_json: local_inspection_service.text_inspection.incoming_ports.IncomingJSON
    _incoming_media: local_inspection_service.text_inspection.incoming_ports.IncomingMedia
    _incoming_ocr_engine: local_inspection_service.text_inspection.incoming_analysis.IncomingOCREngine
    _incoming_references: local_inspection_service.text_inspection.incoming_ports.IncomingReferences
    _incoming_retention: local_inspection_service.text_inspection.incoming_retention.IncomingRetention
    _incoming_reviews: local_inspection_service.text_inspection.incoming_reviews.IncomingReviews
    _incoming_task_access: local_inspection_service.text_inspection.incoming_access.IncomingTaskAccess
    _incoming_tasks: local_inspection_service.text_inspection.incoming_ports.IncomingTasks
    _incoming_text_ocr_lock: _thread.RLock
    _incoming_text_store: local_inspection_service.text_inspection.incoming_store.IncomingTextStore
    _incoming_text_store_lock: _thread.RLock
    _incoming_workflows: local_inspection_service.text_inspection.incoming_composition.IncomingWorkflows
    _incoming_writes: local_inspection_service.text_inspection.incoming_ports.IncomingWrites
    _inspection_access: local_inspection_service.text_inspection.inspection_ports.InspectionAccess
    _inspection_records: local_inspection_service.text_inspection.inspection_ports.InspectionRecords
    _inspection_reviews: local_inspection_service.text_inspection.inspection_reviews.InspectionReviews
    _label_imports: local_inspection_service.label_inspection.dependencies.LabelImports
    _label_repository_lifecycle: local_inspection_service.label_inspection.dependencies.RepositoryLifecycle
    _preparation_media: local_inspection_service.text_inspection.preparation_ports.PreparationMedia
    _preparation_models: local_inspection_service.text_inspection.preparation_ports.PreparationModels
    _preparation_records: local_inspection_service.text_inspection.preparation_ports.PreparationRecords
    _prepared_comparison_runtime: local_inspection_service.text_inspection.comparison_runtime.ComparisonRuntime
    _standard_access: local_inspection_service.text_inspection.standard_ports.StandardAccess
    _standard_edits: local_inspection_service.text_inspection.standard_edits.StandardEdits
    _standard_imports: local_inspection_service.text_inspection.standard_imports.StandardImports
    _standard_library: local_inspection_service.text_inspection.standard_library.StandardLibrary
    _standard_media: local_inspection_service.text_inspection.standard_ports.StandardMedia
    _standard_records: local_inspection_service.text_inspection.standard_ports.StandardRecords
    _text_compare_beta_cache: dict[str, Any]
    _text_compare_beta_cache_lock: _thread.RLock
    _text_comparisons: local_inspection_service.text_inspection.comparison_composition.TextComparisonWorkflows
    _text_diagnostics: local_inspection_service.text_inspection.diagnostics.TextDiagnostics
    _text_extraction_runtime: local_inspection_service.runtime.training_tasks.TrainingThreadLifecycle
    _text_media: local_inspection_service.text_inspection.media.TextMedia
    _text_records: local_inspection_service.text_inspection.record_store.TextRecordStore
    _text_revisions: local_inspection_service.text_inspection.revisions.TextRevisions
    _text_standards: local_inspection_service.text_inspection.standard_composition.TextStandardWorkflows
    _text_storage: local_inspection_service.text_inspection.storage_composition.TextStorage

def assemble_text(values: ApplicationValues, environment: MutableMapping[str, str], ports: TextWiringInputs) -> TextAssembly:
    def clear_thread_runtime_repository_selection() -> None:
        ports._runtime_repositories().clear()

    def runtime_postgres_repository_or_none() -> Any | None:
        """Return the explicit PostgreSQL repository, or None for JSON runtime."""
        return ports._runtime_repository_access().runtime_postgres_repository_or_none()

    def scope_config_for_user(config: dict[str, Any], user: dict[str, Any] | None=None, target_user_id: str | None=None) -> dict[str, Any]:
        return ports._account_projections().scope_config_for_user(config, user, target_user_id)

    def load_config() -> dict[str, Any]:
        return ports._app_configuration().load_config()

    def public_path_sanitized(value: Any) -> Any:
        return ports._service_paths().public_path_sanitized(value)

    def path_is_under(path: Path, root: Path) -> bool:
        return ports._service_paths().path_is_under(path, root)

    def output_write_dir_for_owner(kind: str='', owner_user_id: str='') -> Path:
        return ports._service_paths().output_write_dir_for_owner(kind, owner_user_id)

    def resolve_model_profiles():
        """Composition-only late binding; domain decorators receive this callable."""
        return ports._model_profile_configuration().resolve_model_profiles()

    def record_model_call(settings, elapsed_ms, ok, usage):
        return resolve_model_profiles().record_call(settings, elapsed_ms, ok, usage)

    def ai_urlopen(request: urllib.request.Request, settings: dict[str, Any], *, timeout: float):
        return ports._provider_configuration().ai_urlopen(request, settings, timeout=timeout)

    def ai_detection_settings(purpose: str='pipeline') -> dict[str, Any]:
        return ports._model_profile_configuration().ai_detection_settings(purpose)

    def image_generation_settings() -> dict[str, Any]:
        return ports._model_profile_configuration().image_generation_settings()

    def image_generation_provider_from_settings(settings: dict[str, Any]) -> GeminiAiProvider | AgnesImageProvider | QwenImageProvider:
        return ports._provider_selection().image_generation_provider_from_settings(settings)

    def call_ai_mcp_tool(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        return ports._model_tool_dispatch().call_ai_mcp_tool(tool_name, payload)

    def load_pipeline_tasks() -> list[dict[str, Any]]:
        return ports._pipeline_task_store().load_pipeline_tasks()

    def load_pipeline_task(task_id: str) -> dict[str, Any] | None:
        return ports._pipeline_task_store().load_pipeline_task(task_id)

    def save_pipeline_task(task: dict[str, Any]) -> dict[str, Any] | None:
        return ports._pipeline_task_store().save_pipeline_task(task)

    def pipeline_task_public(task: dict[str, Any], config: dict[str, Any], *, ai_task_ids: set[str] | None=None, trained_model_specs: list[dict[str, Any]] | None=None, auto_optimize_states: list[dict[str, Any]] | None=None, auto_optimize_states_by_id: dict[str, dict[str, Any]] | None=None, sanitize: bool=True) -> dict[str, Any]:
        return ports._task_projection().pipeline_task_public(task, config, ai_task_ids=ai_task_ids, trained_model_specs=trained_model_specs, auto_optimize_states=auto_optimize_states, auto_optimize_states_by_id=auto_optimize_states_by_id, sanitize=sanitize)

    def _text_v2_load(kind: str) -> list[dict[str, Any]]:
        return _text_records.load(kind)

    def _text_v2_save(kind: str, value: dict[str, Any], *, insert_only: bool=False) -> bool:
        return _text_records.save(kind, value, insert_only=insert_only)

    def _text_v2_owned(kind: str, record_id: str, owner_user_id: str) -> dict[str, Any] | None:
        return _text_records.owned(kind, record_id, owner_user_id)

    def _text_v2_owner() -> tuple[str, str]:
        user = ports.current_auth_user()()
        return (str(user.get('id') or ''), str(user.get('username') or ''))

    def _text_v2_media_path(owner_user_id: str, standard_id: str, filename: str) -> Path:
        return _text_media.media_path(owner_user_id, standard_id, filename)

    def _text_v2_write(path: Path, contents: bytes) -> None:
        return _text_media.write(path, contents)

    def _text_v2_read_verified(path_value: str, owner_user_id: str, standard_id: str, *, expected_sha256: str='', max_bytes: int=120 * 1024 * 1024) -> bytes:
        return _text_media.read_verified(path_value, owner_user_id, standard_id, expected_sha256=expected_sha256, max_bytes=max_bytes)

    def _text_v2_asset_bytes(asset: dict[str, Any], owner_user_id: str) -> bytes:
        return _text_media.asset_bytes(asset, owner_user_id)

    def _text_v2_image_diagnostics(contents: bytes, *, source_format: str, mime_type: str) -> dict[str, Any]:
        return _text_diagnostics.image_diagnostics(contents, source_format=source_format, mime_type=mime_type)

    def _text_v2_write_server_diagnostic(record: dict[str, Any]) -> None:
        return _text_diagnostics.write_server_diagnostic(record)

    def _text_v2_prepare_provider_image(contents: bytes, mime_type: str) -> tuple[bytes, str, str]:
        return _prepare_text_provider_image(contents, mime_type, max_side=lambda: values.TEXT_INSPECTION_PROVIDER_IMAGE_MAX_SIDE, jpeg_quality=lambda: values.TEXT_INSPECTION_PROVIDER_IMAGE_JPEG_QUALITY)

    def append_incoming_text_audit(event: dict[str, Any]) -> None:
        return _incoming_text_store.append_incoming_text_audit(event)

    def incoming_text_public(record: dict[str, Any]) -> dict[str, Any]:
        return _incoming_public_record(record, sanitize=lambda value: public_path_sanitized(value))

    def incoming_text_task_access_allowed(task: dict[str, Any], user: dict[str, Any]) -> bool:
        return _incoming_task_access_allowed(task, user, is_admin=lambda value: user_is_admin(value), owner=lambda value: ports.record_owner_id()(value))

    def require_incoming_text_task(task_id: str, *, write: bool=False) -> dict[str, Any]:
        return _incoming_task_access.require(task_id, write=write)

    def incoming_text_ocr_engine() -> Any:
        return _incoming_ocr_engine.get()

    def incoming_text_ocr_observations(image: np.ndarray) -> list[TextObservation]:
        return _incoming_observations(image, engine=lambda: incoming_text_ocr_engine(), mapping_provider=lambda: _ocr_result_mapping)

    def incoming_text_corroboration_observations(image: np.ndarray, rules: list[dict[str, Any]]) -> dict[str, list[TextObservation]]:
        return _incoming_corroboration(image, rules, observe=lambda crop: incoming_text_ocr_observations(crop))

    def require_incoming_text_storage_capacity(upload_bytes: int) -> None:
        return _incoming_capacity.require(upload_bytes)

    _text_storage = TextStorage(repository=lambda: runtime_postgres_repository_or_none(), paths=TextStoragePaths(records=lambda: values.TEXT_INSPECTION_JSON_DIR, incoming=IncomingPaths(references=lambda: values.INCOMING_TEXT_REFERENCES_PATH, inspections=lambda: values.INCOMING_TEXT_INSPECTIONS_PATH, audit=lambda: values.INCOMING_TEXT_AUDIT_PATH)), rows=IncomingRows(reference=lambda record: incoming_text_reference_row(record), inspection=lambda record: incoming_text_inspection_row(record), audit=lambda event: audit_event_row(event), decode=lambda: row_raw_json_list), json_io=TextStorageJSON(reader=lambda: _incoming_text_json_list, writer=lambda: _save_incoming_text_json_list), tables=lambda: TEXT_INSPECTION_TABLES)
    _incoming_text_store_lock = _text_storage.lock
    _text_records = _text_storage.records
    _text_standards = TextStandardWorkflows(records=_text_storage.records, access=StandardAccess(require_permission=lambda permission, **kwargs: ports.require_permission()(permission, **kwargs), owner=lambda: _text_v2_owner()), media=StandardMediaStorage(directory=lambda: values.TEXT_INSPECTION_MEDIA_DIR, digest=lambda contents: sha256_bytes(contents), data_url=lambda data, mime: _text_v2_data_url(data, mime), runtime_provider=ports._business_files().runtime_provider, files=ports._business_files()), policy=StandardPolicy(public=lambda: _text_v2_public, snapshot=lambda assets: _text_v2_confirmed_snapshot(assets), expected=lambda: _text_v2_expected_revision, bounded_text=lambda: bounded_text, prepare_image=lambda contents: _text_v2_prepare_image(contents), preparation_enabled=lambda owner: _standard_preparation_policy.enabled(owner)), parsers=StandardParsers(doc=lambda: extract_doc_images, docx=lambda data: extract_docx_candidates(data), pdf=lambda data: inspect_pdf(data)), documents=DocumentModels(external_enabled=lambda: values.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED, settings=lambda purpose: ai_detection_settings(purpose), transport=lambda request, settings, **kwargs: ai_urlopen(request, settings, **kwargs), record_usage=lambda settings, elapsed, ok, usage: record_model_call(settings, elapsed, ok, usage)), preparation=PreparationModels(settings=lambda purpose: ai_detection_settings(purpose), external_enabled=lambda: values.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED, call_tool=lambda name, payload: call_ai_mcp_tool(name, payload), diagnostics=lambda provider, settings: _text_v2_provider_diagnostics(provider, settings)), runtime=StandardThreadScope(scope=ports._runtime_repositories().thread_scope, clear_repository=lambda: clear_thread_runtime_repository_selection()), raw_rows=lambda rows: row_raw_json_list(rows))
    _text_media = _text_standards.media
    _text_revisions = _text_standards.revisions
    _standard_access = _text_standards.access
    _standard_records = _text_standards.standard_records
    _standard_media = _text_standards.standard_media
    _standard_imports = _text_standards.imports
    _standard_library = _text_standards.library
    _standard_edits = _text_standards.edits
    _text_diagnostics = TextDiagnostics(digest=lambda: sha256_bytes, logger=lambda: values.TEXT_INSPECTION_DIAGNOSTIC_LOGGER)
    _document_records = _text_standards.document_records
    _document_models = _text_standards.document_models
    _preparation_records = _text_standards.preparation_records
    _preparation_media = _text_standards.preparation_media
    _preparation_models = _text_standards.preparation_models
    _text_comparisons = TextComparisonWorkflows(standards=_text_standards, access=InspectionAccess(require_permission=lambda permission, **kwargs: ports.require_permission()(permission, **kwargs), owner=lambda: _text_v2_owner()), images=ComparisonImages(prepare=lambda: _text_v2_prepare_image, provider_copy=lambda data, mime: _text_v2_prepare_provider_image(data, mime), annotate=lambda: _text_v2_annotate, data_url=lambda data, mime: _text_v2_data_url(data, mime)), models=SubmissionModels(settings=lambda purpose: ai_detection_settings(purpose), call=lambda: call_ai_mcp_tool, prompt=lambda: strict_compare_prompt(), normalize=lambda: normalize_vlm_provider_result, validate=lambda value: validate_vlm_result(value)), policy=SubmissionPolicy(timeout=lambda: values.TEXT_INSPECTION_PROVIDER_TIMEOUT_SECONDS, prompt_version=lambda: values.TEXT_INSPECTION_PROMPT_VERSION, external_enabled=lambda: values.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED, automatic_match_verified=lambda: values.TEXT_INSPECTION_AUTOMATIC_MATCH_VERIFIED, qwen_enabled=lambda owner: _qwen_evidence_policy.enabled(owner)), diagnostics=SubmissionDiagnostics(image=lambda data, **kwargs: _text_v2_image_diagnostics(data, **kwargs), event=lambda: _text_v2_diagnostic_event, provider=lambda provider, settings: _text_v2_provider_diagnostics(provider, settings), value=lambda value: _text_v2_diagnostic_value(value), write=lambda record: _text_v2_write_server_diagnostic(record)), extraction=ExtractionModels(image_settings=lambda: image_generation_settings(), detection_settings=lambda purpose: ai_detection_settings(purpose), image_provider=lambda settings: image_generation_provider_from_settings(settings), transport=lambda request, settings, **kwargs: ai_urlopen(request, settings, **kwargs), diagnostic_value=lambda value: _text_v2_diagnostic_value(value), external_enabled=lambda: values.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED), prepared_models=lambda: ComparisonModels(ai_detection_settings, values.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED, record_model_call), digest=lambda: sha256_bytes, environment=lambda: lambda name, default, environment=os: environment.getenv(name, default), prepared_cleanup=lambda: clear_thread_runtime_repository_selection, audit=ComparisonAudit(append=lambda: append_incoming_text_audit, bounded_text=lambda: bounded_text), runtime=StandardThreadScope(scope=ports._runtime_repositories().thread_scope, clear_repository=lambda: clear_thread_runtime_repository_selection()), files=ports._business_files())
    _history_records = _text_comparisons.history_records
    _history_media = _text_comparisons.history_media
    _extraction_records = _text_comparisons.extraction_records
    _extraction_media = _text_comparisons.extraction_media
    _extraction_models = _text_comparisons.extraction_models
    _text_extraction_runtime = _text_comparisons.extraction_runtime
    _codex_standard_library = StandardLibrary(owned=lambda kind, identifier, owner: _text_v2_owned(kind, identifier, owner), load=lambda kind: _text_v2_load(kind), save=lambda kind, value, **kwargs: _text_v2_save(kind, value, **kwargs))
    _codex_media = ComparisonMedia(data_directory=lambda: values.DATA_DIR, asset_bytes=lambda asset, owner: _text_v2_asset_bytes(asset, owner), media_path=lambda owner, standard, name: _text_v2_media_path(owner, standard, name), write=lambda path, data: _text_v2_write(path, data))
    _label_repository_lifecycle = RepositoryLifecycle(repository=lambda: runtime_postgres_repository_or_none(), clear=lambda: clear_thread_runtime_repository_selection())
    _label_imports = LabelImports(data_directory=lambda: values.DATA_DIR, extract_docx=lambda data, **kwargs: extract_docx_candidates(data, **kwargs), extract_doc=lambda data: extract_doc_images(data), asset_bytes=lambda asset, owner: _text_v2_asset_bytes(asset, owner), read_verified=lambda path, owner, standard, **kwargs: _text_v2_read_verified(path, owner, standard, **kwargs))
    _prepared_comparison_runtime = _text_comparisons.comparison_runtime
    _inspection_access = _text_comparisons.access
    _inspection_records = _text_comparisons.inspection_records
    _comparison_submission = _text_comparisons.submission
    _inspection_reviews = _text_comparisons.reviews
    _incoming_text_store = _text_storage.incoming
    _incoming_task_access = IncomingTaskAccess(load=lambda task_id: load_pipeline_task(task_id), user=lambda: ports.current_auth_user()(), allowed=lambda: incoming_text_task_access_allowed)
    _incoming_ocr_engine = IncomingOCREngine(prepare_runtime=lambda: prepare_paddle_runtime())
    _incoming_text_ocr_lock = _incoming_ocr_engine.lock
    _incoming_access = IncomingAccess(permission=lambda permission, **kwargs: ports.require_permission()(permission, **kwargs), user=lambda: ports.current_auth_user()(), task=lambda: require_incoming_text_task, record=lambda: ports.require_record_access(), owner=lambda record: ports.record_owner_id()(record), task_allowed=lambda task, user: incoming_text_task_access_allowed(task, user))
    _incoming_tasks = IncomingTasks(all=lambda: load_pipeline_tasks(), save=lambda task: save_pipeline_task(task), public=lambda: pipeline_task_public, config=lambda: scope_config_for_user(load_config()))
    _incoming_media = IncomingMedia(output=lambda: output_write_dir_for_owner, root=lambda: values.OUTPUT_DIR, under=lambda path, root: path_is_under(path, root), decode=lambda: decode_incoming_reference)
    _incoming_capacity = IncomingCapacity(data_dir=lambda: values.DATA_DIR, minimum_free=lambda: values.INCOMING_TEXT_MIN_FREE_BYTES)
    _incoming_workflows = IncomingWorkflows(storage=_text_storage, access=_incoming_access, tasks=_incoming_tasks, media=_incoming_media, ocr=IncomingOCR(observe=lambda image: incoming_text_ocr_observations(image), corroborate=lambda image, rules: incoming_text_corroboration_observations(image, rules), field=lambda: _field_observation), imaging=IncomingImaging(quality=lambda image: assess_image_quality(image), rectify=lambda: rectify_label, similarity=lambda: local_visual_similarity, annotate=lambda: annotate_inspection), capacity=lambda: require_incoming_text_storage_capacity, verified=lambda: values.INCOMING_TEXT_AUTOMATIC_DECISIONS_VERIFIED, public=lambda record: incoming_text_public(record), decode_rows=lambda: row_raw_json_list, audit=lambda: append_incoming_text_audit, system_owner=lambda: values.SYSTEM_OWNER_ID, files=ports._business_files(), images=ports._incoming_image_files())
    _incoming_references = _incoming_workflows.references
    _incoming_inspections = _incoming_workflows.inspections
    _incoming_writes = _incoming_workflows.writes
    _incoming_json = _incoming_workflows.json
    _incoming_catalog = _incoming_workflows.catalog
    _incoming_reviews = _incoming_workflows.reviews
    _incoming_execution = _incoming_workflows.execution
    _incoming_retention = _incoming_workflows.retention
    _beta_comparison = BetaComparison(BetaPolicy(ttl_seconds=lambda: values.TEXT_COMPARE_BETA_CACHE_TTL_SECONDS, max_pixels=lambda: values.TEXT_COMPARE_BETA_MAX_PIXELS, max_cache_bytes=lambda: values.TEXT_COMPARE_BETA_CACHE_MAX_BYTES), observer=lambda: incoming_text_ocr_observations)
    _text_compare_beta_cache_lock = _beta_comparison.lock
    _text_compare_beta_cache = _beta_comparison.cache
    return TextAssembly(
        _beta_comparison=_beta_comparison,
        _codex_media=_codex_media,
        _codex_standard_library=_codex_standard_library,
        _comparison_submission=_comparison_submission,
        _document_models=_document_models,
        _document_records=_document_records,
        _extraction_media=_extraction_media,
        _extraction_models=_extraction_models,
        _extraction_records=_extraction_records,
        _history_media=_history_media,
        _history_records=_history_records,
        _incoming_access=_incoming_access,
        _incoming_capacity=_incoming_capacity,
        _incoming_catalog=_incoming_catalog,
        _incoming_execution=_incoming_execution,
        _incoming_inspections=_incoming_inspections,
        _incoming_json=_incoming_json,
        _incoming_media=_incoming_media,
        _incoming_ocr_engine=_incoming_ocr_engine,
        _incoming_references=_incoming_references,
        _incoming_retention=_incoming_retention,
        _incoming_reviews=_incoming_reviews,
        _incoming_task_access=_incoming_task_access,
        _incoming_tasks=_incoming_tasks,
        _incoming_text_ocr_lock=_incoming_text_ocr_lock,
        _incoming_text_store=_incoming_text_store,
        _incoming_text_store_lock=_incoming_text_store_lock,
        _incoming_workflows=_incoming_workflows,
        _incoming_writes=_incoming_writes,
        _inspection_access=_inspection_access,
        _inspection_records=_inspection_records,
        _inspection_reviews=_inspection_reviews,
        _label_imports=_label_imports,
        _label_repository_lifecycle=_label_repository_lifecycle,
        _preparation_media=_preparation_media,
        _preparation_models=_preparation_models,
        _preparation_records=_preparation_records,
        _prepared_comparison_runtime=_prepared_comparison_runtime,
        _standard_access=_standard_access,
        _standard_edits=_standard_edits,
        _standard_imports=_standard_imports,
        _standard_library=_standard_library,
        _standard_media=_standard_media,
        _standard_records=_standard_records,
        _text_compare_beta_cache=_text_compare_beta_cache,
        _text_compare_beta_cache_lock=_text_compare_beta_cache_lock,
        _text_comparisons=_text_comparisons,
        _text_diagnostics=_text_diagnostics,
        _text_extraction_runtime=_text_extraction_runtime,
        _text_media=_text_media,
        _text_records=_text_records,
        _text_revisions=_text_revisions,
        _text_standards=_text_standards,
        _text_storage=_text_storage,
    )
