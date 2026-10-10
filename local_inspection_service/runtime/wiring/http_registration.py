"""Register fresh graph-bound HTTP endpoints and lifetimes in original order.

Native registrars receive the fresh graph; no existing routes are copied or mounted.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import MutableMapping
from typing import Any, Callable
import contextvars
import _thread
from ..application_values import ApplicationValues
from ..http_application import HttpApplication
from local_inspection_service.agent.dependencies import AgentAccess
from local_inspection_service.agent.dependencies import AgentAccounts
from local_inspection_service.schemas.configuration import AgentConfigRequest
from local_inspection_service.schemas.pipeline import AgentRecommendRequest
from local_inspection_service.schemas.configuration import AiConfigRequest
from local_inspection_service.schemas.detection import AiDetectionTaskRequest
from typing import Any
from local_inspection_service.storage.artifacts.http import ArtifactStaticFiles
from local_inspection_service.schemas.training import AutoOptimizeSampleApproveRequest
from local_inspection_service.schemas.training import AutoOptimizeSettingsRequest
from local_inspection_service.text_inspection.beta_api import BetaAccess
from typing import Callable
from local_inspection_service.codex_compare.dependencies import ComparisonAccess
from local_inspection_service.codex_compare.dependencies import DocumentImports
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from local_inspection_service.label_inspection.dependencies import LabelAccess
from local_inspection_service.detection.warmup_requests import ModelWarmupAccess
from local_inspection_service.detection.warmup_requests import ModelWarmupModels
from pathlib import Path
from local_inspection_service.schemas.plc import PlcCaptureSessionHeartbeatRequest
from local_inspection_service.schemas.plc import PlcCaptureSessionRequest
from local_inspection_service.schemas.plc import PlcConfigRequest
from local_inspection_service.schemas.plc import PlcWebSerialAttemptRequest
from local_inspection_service.schemas.plc import PlcWebSerialConfigRequest
from local_inspection_service.schemas.plc import PlcWebSerialDiagnosticConfirmRequest
from local_inspection_service.schemas.plc import PlcWebSerialDiagnosticReceiptRequest
from local_inspection_service.schemas.plc import PlcWebSerialReceiptRequest
from local_inspection_service.schemas.plc import PlcWorkstationLeaseActivateRequest
from local_inspection_service.schemas.plc import PlcWorkstationLeaseHeartbeatRequest
from local_inspection_service.schemas.plc import PlcWorkstationLeaseRebindRequest
from local_inspection_service.schemas.plc import PlcWorkstationLeaseRequest
from local_inspection_service.schemas.plc import PlcWorkstationSelfPairRequest
from local_inspection_service.plc.workstation_self_service import WorkstationSelfService
from local_inspection_service.plc.workstation_self_service_api import register_workstation_self_service
from local_inspection_service.schemas.plc import PlcWorkstationPairRequest
from local_inspection_service.schemas.plc import PlcWorkstationVerifyRequest
from local_inspection_service.model_profiles.dependencies import ProfileApiDependencies
from fastapi import Request
from local_inspection_service.training.resource_api import ResourceReadAccess
from fastapi import Response
from local_inspection_service.detection.rule_request_ports import RuleAccess
from local_inspection_service.detection.rule_request_ports import RulePolicy
from local_inspection_service.detection.rule_request_ports import RuleStore
from local_inspection_service.runtime.shutdown import ShutdownStep
from fastapi.staticfiles import StaticFiles
from local_inspection_service.schemas.configuration import StreamConfig
from fastapi.responses import StreamingResponse
from fastapi import UploadFile
from local_inspection_service.plc_web_serial import WEB_SERIAL_PROTOCOL_VERSION
from ultralytics import YOLO
from local_inspection_service.training.jobs_api import ImageJobActions as _native_ImageJobActions_9269
from local_inspection_service.plc.config_diagnostics_api import register_config_diagnostics_routes as _register_config_diagnostics_routes
from local_inspection_service.plc.connection_lease_api import register_connection_lease_routes as _register_connection_lease_routes
from local_inspection_service.plc.dispatch_diagnostic_api import register_dispatch_diagnostic_routes as _register_dispatch_diagnostic_routes
from local_inspection_service.plc.workstation_management_api import register_workstation_management_routes as _register_workstation_management_routes
from local_inspection_service.training.worker_watcher import start_worker_training_watcher as _retired_worker_watcher_start
from local_inspection_service.training import background_api as _training_background_api
from local_inspection_service.training import jobs_api as _training_jobs_api
from local_inspection_service.training import launch_api as _training_launch_api
from local_inspection_service.training import runpod_transfer_api as _training_transfer_api
from local_inspection_service.analytics.cost_pricing import api_cost_from_usage
from local_inspection_service.detection.warmup_api import bind_warmup_start
from local_inspection_service.detection.rule_api import compose_detection_rule_api
from local_inspection_service.detection.warmup_api import compose_model_warmup_api
from local_inspection_service.model_providers.mcp_runtime import external_ai_mcp_enabled
from local_inspection_service.document_images import extract_doc_images
from local_inspection_service.text_inspection_v2 import extract_docx_candidates
from local_inspection_service.auth.policy import find_user
from local_inspection_service.label_inspection import model as label_inspection_model
from local_inspection_service.model_profiles.snapshots import pinned as pinned_model_profiles
import re
from local_inspection_service.agent_api import register as register_agent_api
from local_inspection_service.analytics.analysis_api import register_analysis_api
from local_inspection_service.text_inspection.beta_api import register as register_beta_comparison
from local_inspection_service.accessories.candidate_api import register_candidate_api
from local_inspection_service.accessories.api import register_catalog_api
from local_inspection_service.codex_compare.api import register as register_codex_compare
from local_inspection_service.analytics.cost_api import register_cost_api
from local_inspection_service.runtime.web_shell import register_entry_routes
from local_inspection_service.accessories.file_api import register_file_api
from local_inspection_service.label_inspection.api import register as register_label_inspection
from local_inspection_service.accessories.management_api import register_management_api
from local_inspection_service.accessories.management_api import register_removal_api
from local_inspection_service.accessories.routing_api import register_routing_api
from local_inspection_service.runtime.web_shell import register_spa
from local_inspection_service.training.preview_api import register as register_training_preview_api
from local_inspection_service.training.resource_api import register as register_training_resource_api
from local_inspection_service.training.resource_api import register_writes as register_training_resource_writes
from local_inspection_service.runtime.shutdown import register_web_shutdown
from local_inspection_service.release_version import release_version_status
from local_inspection_service.retired_features import removed_phase1_feature
import threading
import time
from local_inspection_service.auth.policy import user_is_admin
import local_inspection_service.accessories.api
import local_inspection_service.accessories.candidate_queries
import local_inspection_service.accessories.catalog
import local_inspection_service.accessories.confirmation
import local_inspection_service.accessories.creation
import local_inspection_service.accessories.file_api
import local_inspection_service.accessories.files
import local_inspection_service.accessories.image_job_management
import local_inspection_service.accessories.management_api
import local_inspection_service.accessories.removal
import local_inspection_service.accessories.routing
import local_inspection_service.agent.protocol_policy
import local_inspection_service.agent.settings_api
import local_inspection_service.analytics.analysis_api
import local_inspection_service.analytics.analysis_queries
import local_inspection_service.analytics.costs
import local_inspection_service.auth.access
import local_inspection_service.auth.account_projections
import local_inspection_service.auth.api
import local_inspection_service.auth.http_composition
import local_inspection_service.auth.status
import local_inspection_service.auth.status_requests
import local_inspection_service.codex_compare.dependencies
import local_inspection_service.config.app_store
import local_inspection_service.config.application_composition
import local_inspection_service.config.stream
import local_inspection_service.detection.camera_request
import local_inspection_service.detection.image_upload
import local_inspection_service.detection.local_models
import local_inspection_service.detection.model_selection
import local_inspection_service.detection.rule_requests
import local_inspection_service.detection.task_requests
import local_inspection_service.detection.video_upload
import local_inspection_service.detection.warmup_requests
import local_inspection_service.label_inspection.dependencies
import local_inspection_service.model_profiles.composition
import local_inspection_service.model_providers.configuration_composition
import local_inspection_service.model_providers.mcp_client
import local_inspection_service.pipeline.advance_runtime
import local_inspection_service.pipeline.auto_agent_runtime
import local_inspection_service.pipeline.recommendation_runtime
import local_inspection_service.pipeline.task_composition
import local_inspection_service.plc.config_diagnostics
import local_inspection_service.plc.connection_lease
import local_inspection_service.plc.dispatch_diagnostic
import local_inspection_service.plc.workstation_management
import local_inspection_service.runtime.image_worker
import local_inspection_service.runtime.repository_access
import local_inspection_service.runtime.service_paths
import local_inspection_service.runtime.shutdown
import local_inspection_service.runtime.training_tasks
import local_inspection_service.runtime.web_shell
import local_inspection_service.runtime.yolo_warmup
import local_inspection_service.storage.artifacts.files
import local_inspection_service.text_inspection.beta_comparison
import local_inspection_service.text_inspection.comparison_composition
import local_inspection_service.text_inspection.comparison_runtime
import local_inspection_service.text_inspection.document_jobs
import local_inspection_service.text_inspection.incoming_api
import local_inspection_service.text_inspection.incoming_composition
import local_inspection_service.text_inspection.incoming_retention
import local_inspection_service.text_inspection.inspection_api
import local_inspection_service.text_inspection.preparation_jobs
import local_inspection_service.text_inspection.standard_api
import local_inspection_service.text_inspection.standard_composition
import local_inspection_service.training.auto_optimization_label_processing
import local_inspection_service.training.auto_optimization_requests
import local_inspection_service.training.auto_optimization_shadow_evaluation
import local_inspection_service.training.auto_optimization_training_scheduling
import local_inspection_service.training.background_api
import local_inspection_service.training.background_codex
import local_inspection_service.training.background_query
import local_inspection_service.training.background_uploads
import local_inspection_service.training.dataset_catalog
import local_inspection_service.training.dispatcher_runtime
import local_inspection_service.training.jobs_api
import local_inspection_service.training.jobs_query
import local_inspection_service.training.launch_submission
import local_inspection_service.training.model_catalog
import local_inspection_service.training.preview_api
import local_inspection_service.training.preview_query
import local_inspection_service.training.preview_submission
import local_inspection_service.training.real_photo_api
import local_inspection_service.training.real_photo_composition
import local_inspection_service.training.resource_api
import local_inspection_service.training.resource_mutations
import local_inspection_service.training.resource_queries
import local_inspection_service.training.runpod_transfer
import local_inspection_service.training.runpod_transfer_api
import local_inspection_service.training.status_query
import local_inspection_service.training.task_mutations
import local_inspection_service.training.transfer_progress

@dataclass(frozen=True)
class HttpRegistrationInputs:
    _access_control: Callable[[], local_inspection_service.auth.access.AccessControl]
    _accessory_catalog: Callable[[], local_inspection_service.accessories.catalog.AccessoryCatalog]
    _accessory_confirmation: Callable[[], local_inspection_service.accessories.confirmation.AccessoryConfirmation]
    _accessory_creation: Callable[[], local_inspection_service.accessories.creation.AccessoryCreation]
    _accessory_files: Callable[[], local_inspection_service.accessories.files.AccessoryFiles]
    _accessory_removal: Callable[[], local_inspection_service.accessories.removal.AccessoryRemoval]
    _accessory_routing: Callable[[], local_inspection_service.accessories.routing.AccessoryRouting]
    _account_projections: Callable[[], local_inspection_service.auth.account_projections.AccountProjections]
    _agent_protocol_policy: Callable[[], local_inspection_service.agent.protocol_policy.AgentProtocolPolicy]
    _agent_settings_api: Callable[[], local_inspection_service.agent.settings_api.AgentSettingsApi]
    _ai_mcp_client: Callable[[], local_inspection_service.model_providers.mcp_client.LocalAiMcpClient]
    _analysis_queries: Callable[[], local_inspection_service.analytics.analysis_queries.AnalysisQueries]
    _app_config_store: Callable[[], local_inspection_service.config.app_store.AppConfigStore]
    _app_configuration: Callable[[], local_inspection_service.config.application_composition.ApplicationConfiguration]
    _authentication_http: Callable[[], local_inspection_service.auth.http_composition.AuthenticationHttp]
    _auto_optimization_label_processing: Callable[[], local_inspection_service.training.auto_optimization_label_processing.AutoOptimizationLabelProcessing]
    _auto_optimization_requests: Callable[[], local_inspection_service.training.auto_optimization_requests.AutoOptimizationRequests]
    _auto_optimization_shadow_evaluation: Callable[[], local_inspection_service.training.auto_optimization_shadow_evaluation.AutoOptimizationShadowEvaluation]
    _auto_optimization_training_scheduling: Callable[[], local_inspection_service.training.auto_optimization_training_scheduling.AutoOptimizationTrainingScheduling]
    _background_capture: Callable[[], local_inspection_service.training.background_uploads.BackgroundCapture]
    _background_codex_thread: Callable[[], local_inspection_service.training.background_codex.CodexBackgroundThread]
    _background_query: Callable[[], local_inspection_service.training.background_query.BackgroundQuery]
    _background_upload: Callable[[], local_inspection_service.training.background_uploads.BackgroundUpload]
    _beta_comparison: Callable[[], local_inspection_service.text_inspection.beta_comparison.BetaComparison]
    _business_files: Callable[[], local_inspection_service.storage.artifacts.files.BusinessFiles]
    _camera_detection_request: Callable[[], local_inspection_service.detection.camera_request.CameraDetectionRequest]
    _candidate_queries: Callable[[], local_inspection_service.accessories.candidate_queries.CandidateQueries]
    _codex_media: Callable[[], local_inspection_service.codex_compare.dependencies.ComparisonMedia]
    _codex_standard_library: Callable[[], local_inspection_service.codex_compare.dependencies.StandardLibrary]
    _cost_ledger: Callable[[], local_inspection_service.analytics.costs.CostLedger]
    _dataset_catalog: Callable[[], local_inspection_service.training.dataset_catalog.DatasetCatalog]
    _detection_task_requests: Callable[[], local_inspection_service.detection.task_requests.DetectionTaskRequests]
    _image_job_management: Callable[[], local_inspection_service.accessories.image_job_management.ImageJobManagement]
    _image_upload: Callable[[], local_inspection_service.detection.image_upload.ImageUpload]
    _image_worker_runtime: Callable[[], local_inspection_service.runtime.image_worker.ImageWorkerRuntime]
    _incoming_retention: Callable[[], local_inspection_service.text_inspection.incoming_retention.IncomingRetention]
    _incoming_workflows: Callable[[], local_inspection_service.text_inspection.incoming_composition.IncomingWorkflows]
    _label_imports: Callable[[], local_inspection_service.label_inspection.dependencies.LabelImports]
    _label_repository_lifecycle: Callable[[], local_inspection_service.label_inspection.dependencies.RepositoryLifecycle]
    _local_models: Callable[[], local_inspection_service.detection.local_models.LocalModels]
    _model_profile_configuration: Callable[[], local_inspection_service.model_profiles.composition.ModelConfiguration]
    _model_selection: Callable[[], local_inspection_service.detection.model_selection.ModelSelection]
    _pipeline_advance_runtime: Callable[[], local_inspection_service.pipeline.advance_runtime.PipelineAdvanceRuntime]
    _pipeline_auto_agent_runtime: Callable[[], local_inspection_service.pipeline.auto_agent_runtime.PipelineAutoAgentRuntime]
    _pipeline_recommendation_runtime: Callable[[], local_inspection_service.pipeline.recommendation_runtime.PipelineRecommendationRuntime]
    _pipeline_tasks: Callable[[], local_inspection_service.pipeline.task_composition.PipelineTaskWorkflows]
    _plc_config_diagnostics: Callable[[], local_inspection_service.plc.config_diagnostics.ConfigDiagnostics]
    _plc_connection_lease: Callable[[], local_inspection_service.plc.connection_lease.ConnectionLease]
    _plc_dispatch_diagnostic: Callable[[], local_inspection_service.plc.dispatch_diagnostic.DispatchDiagnostic]
    _plc_workstation_self_service: Callable[[], WorkstationSelfService]
    _plc_workstation_management: Callable[[], local_inspection_service.plc.workstation_management.WorkstationManagement]
    _prepared_comparison_runtime: Callable[[], local_inspection_service.text_inspection.comparison_runtime.ComparisonRuntime]
    _provider_configuration: Callable[[], local_inspection_service.model_providers.configuration_composition.ProviderConfiguration]
    _public_status_projection: Callable[[], local_inspection_service.auth.status.PublicStatusProjection]
    _real_photo_dispatch_runtime: Callable[[], local_inspection_service.training.dispatcher_runtime.DispatcherRuntime]
    _real_photo_workflows: Callable[[], local_inspection_service.training.real_photo_composition.RealPhotoWorkflows]
    _runtime_repository_access: Callable[[], local_inspection_service.runtime.repository_access.RuntimeRepositoryAccess]
    _service_paths: Callable[[], local_inspection_service.runtime.service_paths.ServicePaths]
    _service_status_requests: Callable[[], local_inspection_service.auth.status_requests.ServiceStatusRequests]
    _stream_configuration: Callable[[], local_inspection_service.config.stream.StreamConfiguration]
    _text_comparisons: Callable[[], local_inspection_service.text_inspection.comparison_composition.TextComparisonWorkflows]
    _text_extraction_runtime: Callable[[], local_inspection_service.runtime.training_tasks.TrainingThreadLifecycle]
    _text_standards: Callable[[], local_inspection_service.text_inspection.standard_composition.TextStandardWorkflows]
    _trained_model_catalog: Callable[[], local_inspection_service.training.model_catalog.TrainedModelCatalog]
    _training_jobs_query: Callable[[], local_inspection_service.training.jobs_query.TrainingJobsQuery]
    _training_launch_submission: Callable[[], local_inspection_service.training.launch_submission.TrainingLaunchSubmission]
    _training_plan_query: Callable[[], local_inspection_service.training.preview_query.TrainingPlanQuery]
    _training_preview_submission: Callable[[], local_inspection_service.training.preview_submission.TrainingPreviewSubmission]
    _training_resource_mutations: Callable[[], local_inspection_service.training.resource_mutations.TrainingResourceMutations]
    _training_resources: Callable[[], local_inspection_service.training.resource_queries.TrainingResources]
    _training_status_query: Callable[[], local_inspection_service.training.status_query.TrainingStatusQuery]
    _training_task_mutations: Callable[[], local_inspection_service.training.task_mutations.TrainingTaskMutations]
    _training_task_runtime: Callable[[], local_inspection_service.runtime.training_tasks.TrainingTaskRuntime]
    _training_transfer: Callable[[], local_inspection_service.training.runpod_transfer.RunPodTrainingTransfer]
    _transfer_progress: Callable[[], local_inspection_service.training.transfer_progress.TransferProgress]
    _video_upload: Callable[[], local_inspection_service.detection.video_upload.VideoUpload]
    _web_shell: Callable[[], local_inspection_service.runtime.web_shell.WebShell]
    _yolo_warmup_runtime: Callable[[], local_inspection_service.runtime.yolo_warmup.YoloWarmup]
    current_auth_user: Callable[[], Callable[..., Any]]
    load_auth_store: Callable[[], Callable[..., Any]]
    record_visible_to_user: Callable[[], Callable[..., Any]]
    require_admin_role: Callable[[], Callable[..., Any]]
    require_permission: Callable[[], Callable[..., Any]]
    start_image_worker: Callable[[], Callable[..., Any]]
    warm_ai_mcp_client: Callable[[], Callable[..., Any]]

@dataclass(frozen=True)
class HttpRegistration:
    _accessory_catalog_routes: local_inspection_service.accessories.api.CatalogRoutes
    _accessory_file_routes: local_inspection_service.accessories.file_api.FileRoutes
    _accessory_management_routes: local_inspection_service.accessories.management_api.ManagementRoutes
    _analysis_routes: local_inspection_service.analytics.analysis_api.AnalysisRoutes
    _auth_routes: local_inspection_service.auth.api.AuthRoutes
    _background_routes: local_inspection_service.training.background_api.BackgroundRoutes
    _detection_rule_requests: local_inspection_service.detection.rule_requests.DetectionRules
    _incoming_catalog_routes: local_inspection_service.text_inspection.incoming_api.CatalogRoutes
    _incoming_inspection_routes: local_inspection_service.text_inspection.incoming_api.InspectionRoutes
    _inspection_routes: local_inspection_service.text_inspection.inspection_api.InspectionRoutes
    _model_warmup_requests: local_inspection_service.detection.warmup_requests.ModelWarmupRequests
    _real_photo_feedback: local_inspection_service.training.real_photo_api.FeedbackService
    _standard_routes: local_inspection_service.text_inspection.standard_api.StandardRoutes
    _training_jobs_routes: local_inspection_service.training.jobs_api.JobsRoutes
    _training_preview_routes: local_inspection_service.training.preview_api.PreviewRoutes
    _training_resource_routes: local_inspection_service.training.resource_api.ResourceReadRoutes
    _training_resource_write_routes: local_inspection_service.training.resource_api.ResourceWriteRoutes
    _training_transfer_routes: local_inspection_service.training.runpod_transfer_api.TransferRoutes
    _user_routes: local_inspection_service.auth.api.UserRoutes
    _web_shutdown: local_inspection_service.runtime.shutdown.WebShutdown
    add_accessory: Callable[..., Any]
    add_accessory_files: Callable[..., Any]
    add_label_sheet_reference: Callable[..., Any]
    add_text_inspection_standard_asset: Callable[..., Any]
    agent_recommend: Callable[..., Any]
    analyze_camera_image: Callable[..., Any]
    analyze_image: Callable[..., Any]
    analyze_label_experiment: Callable[..., Any]
    analyze_text_compare_beta: Callable[..., Any]
    analyze_video: Callable[..., Any]
    approve_ai_task_auto_optimize_sample: Callable[..., Any]
    auth_bootstrap: Callable[..., Any]
    auth_login: Callable[..., Any]
    auth_logout: Callable[..., Any]
    auth_status: Callable[..., Any]
    background_image: Callable[..., Any]
    self_pair_plc_workstation: Callable[..., Any]
    self_config_plc_workstation: Callable[..., Any]
    claim_plc_capture_session: Callable[..., Any]
    clone_incoming_text_reference: Callable[..., Any]
    compare_text_inspection_label: Callable[..., Any]
    complete_text_manual_session: Callable[..., Any]
    confirm_accessory: Callable[..., Any]
    confirm_text_inspection_standard: Callable[..., Any]
    create_ai_detection_task: Callable[..., Any]
    create_incoming_text_reference: Callable[..., Any]
    create_pipeline_task: Callable[..., Any]
    create_text_manual_session: Callable[..., Any]
    create_user: Callable[..., Any]
    crop_accessory_text_image: Callable[..., Any]
    delete_accessory: Callable[..., Any]
    delete_accessory_file: Callable[..., Any]
    delete_ai_config_key: Callable[..., Any]
    delete_ai_detection_task: Callable[..., Any]
    delete_ai_task_auto_optimize_sample: Callable[..., Any]
    delete_data_analysis_record_api: Callable[..., Any]
    delete_image_job: Callable[..., Any]
    delete_image_job_candidate: Callable[..., Any]
    delete_pipeline_task: Callable[..., Any]
    delete_training_dataset: Callable[..., Any]
    delete_training_dataset_sample: Callable[..., Any]
    delete_training_model: Callable[..., Any]
    delete_training_task_endpoint: Callable[..., Any]
    delete_user: Callable[..., Any]
    document_import_jobs: local_inspection_service.text_inspection.document_jobs.DocumentJobs
    download_runpod_training_dataset: Callable[..., Any]
    enforce_incoming_text_image_retention: Callable[..., Any]
    get_accessories: Callable[..., Any]
    get_accessory_candidate: Callable[..., Any]
    get_accessory_detail: Callable[..., Any]
    get_agent_config: Callable[..., Any]
    get_ai_config: Callable[..., Any]
    get_ai_detection_tasks: Callable[..., Any]
    get_ai_task_auto_optimize_status: Callable[..., Any]
    get_api_cost_ledger: Callable[..., Any]
    get_config: Callable[..., Any]
    get_config_summary: Callable[..., Any]
    get_data_analysis_record_api: Callable[..., Any]
    get_incoming_text_inspection_evidence: Callable[..., Any]
    get_incoming_text_reference_asset: Callable[..., Any]
    get_incoming_text_task: Callable[..., Any]
    get_label_sheet_references: Callable[..., Any]
    get_locateanything_config: Callable[..., Any]
    get_pipeline_tasks: Callable[..., Any]
    get_release_version: Callable[..., Any]
    get_runtime_store_probe: Callable[..., Any]
    get_task_navigation_preferences: Callable[..., Any]
    get_text_inspection_asset_content: Callable[..., Any]
    get_text_inspection_standard: Callable[..., Any]
    get_text_inspection_v2_evidence: Callable[..., Any]
    get_windows_worker_status: Callable[..., Any]
    get_windows_worker_training_artifacts: Callable[..., Any]
    get_windows_worker_training_job: Callable[..., Any]
    heartbeat_plc_capture_session: Callable[..., Any]
    image_job: Callable[..., Any]
    image_jobs: Callable[..., Any]
    import_text_inspection_standard: Callable[..., Any]
    inspect_incoming_text: Callable[..., Any]
    inspect_text_manual_page: Callable[..., Any]
    list_data_analysis_records_api: Callable[..., Any]
    list_incoming_text_inspections: Callable[..., Any]
    list_text_inspection_standards: Callable[..., Any]
    list_users: Callable[..., Any]
    locateanything_accessories: Callable[..., Any]
    locateanything_inspect: Callable[..., Any]
    locateanything_locate: Callable[..., Any]
    locateanything_runtime_start: Callable[..., Any]
    locateanything_status: Callable[..., Any]
    match_label_sheet_endpoint: Callable[..., Any]
    patch_text_inspection_asset: Callable[..., Any]
    pipeline_agent_chat: Callable[..., Any]
    pipeline_agent_feedback: Callable[..., Any]
    preview_accessory: Callable[..., Any]
    reject_untrusted_cross_origin_writes: Callable[..., Any]
    release_plc_capture_session: Callable[..., Any]
    request_sample_generation: Callable[..., Any]
    request_training: Callable[..., Any]
    reset_user_password: Callable[..., Any]
    resolve_label_extraction: Callable[..., Any]
    resume_image_worker_queue: Callable[..., Any]
    retry_ai_task_auto_optimize_sample: Callable[..., Any]
    retry_image_job: Callable[..., Any]
    review_incoming_text_inspection: Callable[..., Any]
    review_text_inspection_v2: Callable[..., Any]
    run_data_analysis_batch_locate_api: Callable[..., Any]
    run_data_analysis_record_locate_api: Callable[..., Any]
    set_accessory_ai_reference: Callable[..., Any]
    set_accessory_route: Callable[..., Any]
    standard_preparation_jobs: local_inspection_service.text_inspection.preparation_jobs.PreparationJobs
    openapi_schema: Callable[..., Any]
    swagger_ui: Callable[..., Any]
    redoc_ui: Callable[..., Any]
    add_pipeline_accessory: Callable[..., Any]
    remove_pipeline_accessory: Callable[..., Any]
    advance_pipeline_task_endpoint: Callable[..., Any]
    cancel_pipeline_advance_endpoint: Callable[..., Any]
    start_ai_mcp_warmup: Callable[..., Any]
    start_plc_runtime_workers: Callable[..., Any]
    start_real_photo_training_dispatcher: Callable[..., Any]
    start_worker_training_watcher: Callable[..., Any]
    start_yolo_model_warmup: Callable[..., Any]
    status: Callable[..., Any]
    stop_image_job: Callable[..., Any]
    stop_image_job_candidate: Callable[..., Any]
    stop_real_photo_training_dispatcher: Callable[..., Any]
    stream_plc_capture_events: Callable[..., Any]
    test_agent_config: Callable[..., Any]
    training_background_sets: Callable[..., Any]
    training_dataset_detail: Callable[..., Any]
    training_plan: Callable[..., Any]
    training_preview: Callable[..., Any]
    training_resources: Callable[..., Any]
    training_status: Callable[..., Any]
    update_agent_config: Callable[..., Any]
    update_ai_config: Callable[..., Any]
    update_ai_detection_task: Callable[..., Any]
    update_ai_task_auto_optimize_status: Callable[..., Any]
    update_incoming_text_reference_rules: Callable[..., Any]
    update_locateanything_config: Callable[..., Any]
    update_pipeline_task: Callable[..., Any]
    update_rules: Callable[..., Any]
    update_stream: Callable[..., Any]
    update_task_navigation_preferences: Callable[..., Any]
    update_task_rules: Callable[..., Any]
    update_training_dataset: Callable[..., Any]
    update_training_model: Callable[..., Any]
    update_training_task_endpoint: Callable[..., Any]
    update_user: Callable[..., Any]
    upload_ai_task_environment_background: Callable[..., Any]
    upload_runpod_training_artifact: Callable[..., Any]
    upload_training_background_set: Callable[..., Any]
    warmup_detection_model: Callable[..., Any]

def register_http(shell: HttpApplication, values: ApplicationValues, environment: MutableMapping[str, str], ports: HttpRegistrationInputs) -> HttpRegistration:
    _http_application = shell
    app = shell.app
    CORS_ORIGINS = shell.cors_origins
    CORS_ORIGIN_REGEX = shell.cors_origin_regex
    def current_release_version() -> dict[str, Any]:
        return release_version_status(values.ROOT, WEB_SERIAL_PROTOCOL_VERSION)

    def runtime_postgres_repository_or_none() -> Any | None:
        """Return the explicit PostgreSQL repository, or None for JSON runtime."""
        return ports._runtime_repository_access().runtime_postgres_repository_or_none()

    def runtime_store_probe_payload() -> dict[str, Any]:
        """Return a non-secret runtime-store probe for an admin HTTP endpoint."""
        return ports._runtime_repository_access().runtime_store_probe_payload()

    def scope_config_for_user(config: dict[str, Any], user: dict[str, Any] | None=None, target_user_id: str | None=None) -> dict[str, Any]:
        return ports._account_projections().scope_config_for_user(config, user, target_user_id)

    def load_config() -> dict[str, Any]:
        return ports._app_configuration().load_config()

    def save_config(config: dict[str, Any]) -> None:
        return ports._app_configuration().save_config(config)

    def plc_config_response(config: dict[str, Any] | None=None) -> dict[str, Any]:
        return ports._plc_config_diagnostics().response(config)

    def task_rule_id(value: Any) -> str:
        return re.sub('[^a-zA-Z0-9_.@-]+', '_', str(value or '').strip()).strip('_')[:96]

    def public_path_sanitized(value: Any) -> Any:
        return ports._service_paths().public_path_sanitized(value)

    def resolve_model_profiles():
        """Composition-only late binding; domain decorators receive this callable."""
        return ports._model_profile_configuration().resolve_model_profiles()

    def public_ai_detection_status() -> dict[str, Any]:
        return ports._public_status_projection().public_ai_detection_status()

    def list_codex_image_jobs(user: dict[str, Any] | None=None, target_user_id: str | None=None) -> list[dict[str, Any]]:
        return ports._image_job_management().list_codex_image_jobs(user, target_user_id)

    def update_codex_image_job(job_id: str, action: str) -> dict[str, Any]:
        return ports._image_job_management().update_codex_image_job(job_id, action)

    def update_codex_image_candidate(candidate_id: str, action: str) -> dict[str, Any]:
        return ports._image_job_management().update_codex_image_candidate(candidate_id, action)

    def list_trained_model_specs(config: dict[str, Any] | None=None) -> list[dict[str, Any]]:
        return ports._trained_model_catalog().list_trained_model_specs(config)

    def model(model_id: str | None=None, config: dict[str, Any] | None=None) -> YOLO:
        return ports._local_models().model(model_id, config)

    def yolo_warmup_worker(reason: str='startup', model_ids: list[str] | None=None) -> None:
        return ports._yolo_warmup_runtime().yolo_warmup_worker(reason, model_ids)

    def start_yolo_warmup(reason: str='startup', model_ids: list[str] | None=None) -> None:
        return ports._yolo_warmup_runtime().start_yolo_warmup(reason, model_ids, worker=lambda: yolo_warmup_worker)

    def get_plc_config() -> dict[str, Any]:
        return plc_config_response()

    def update_plc_config(request: PlcConfigRequest) -> dict[str, Any]:
        return ports._plc_config_diagnostics().update(request)

    def get_plc_web_serial_workstation(request: Request) -> dict[str, Any]:
        return ports._plc_workstation_management().get(request)

    def list_plc_web_serial_workstations() -> dict[str, Any]:
        return ports._plc_workstation_management().list()

    def pair_plc_web_serial_workstation(request: Request, response: Response, payload: PlcWorkstationPairRequest) -> dict[str, Any]:
        return ports._plc_workstation_management().pair(request, response, payload)

    def update_plc_web_serial_workstation_config(request: Request, payload: PlcWebSerialConfigRequest) -> dict[str, Any]:
        return ports._plc_workstation_management().update_config(request, payload)

    def verify_plc_web_serial_workstation_profile(request: Request, payload: PlcWorkstationVerifyRequest) -> dict[str, Any]:
        return ports._plc_workstation_management().verify_profile(request, payload)

    def claim_plc_web_serial_connection(request: Request, payload: PlcWorkstationLeaseRequest) -> dict[str, Any]:
        return ports._plc_connection_lease().claim(request, payload)

    def activate_plc_web_serial_connection(request: Request, payload: PlcWorkstationLeaseActivateRequest) -> dict[str, Any]:
        return ports._plc_connection_lease().activate(request, payload)

    def heartbeat_plc_web_serial_connection(request: Request, payload: PlcWorkstationLeaseHeartbeatRequest) -> dict[str, Any]:
        return ports._plc_connection_lease().heartbeat(request, payload)

    def rebind_plc_web_serial_connection_model(request: Request, payload: PlcWorkstationLeaseRebindRequest) -> dict[str, Any]:
        return ports._plc_connection_lease().rebind_model(request, payload)

    def disconnect_plc_web_serial_connection(request: Request, payload: PlcWorkstationLeaseHeartbeatRequest) -> dict[str, Any]:
        return ports._plc_connection_lease().disconnect(request, payload)

    def declare_plc_web_serial_attempt(dispatch_id: str, request: Request, payload: PlcWebSerialAttemptRequest) -> dict[str, Any]:
        return ports._plc_dispatch_diagnostic().declare_attempt(dispatch_id, request, payload)

    def create_plc_web_serial_diagnostic_plan(request: Request, payload: PlcWebSerialAttemptRequest) -> dict[str, Any]:
        return ports._plc_dispatch_diagnostic().diagnostic_plan(request, payload)

    def finish_plc_web_serial_diagnostic(request: Request, payload: PlcWebSerialDiagnosticReceiptRequest) -> dict[str, Any]:
        return ports._plc_dispatch_diagnostic().diagnostic_receipt(request, payload)

    def confirm_plc_web_serial_diagnostic(request: Request, payload: PlcWebSerialDiagnosticConfirmRequest) -> dict[str, Any]:
        return ports._plc_dispatch_diagnostic().diagnostic_confirm(request, payload)

    def record_plc_web_serial_receipt_endpoint(dispatch_id: str, request: Request, payload: PlcWebSerialReceiptRequest) -> dict[str, Any]:
        return ports._plc_dispatch_diagnostic().record_receipt(dispatch_id, request, payload)

    def find_dataset_resource(dataset_id: str, user: dict[str, Any] | None=None, *, include_samples: bool=False, write: bool=False) -> tuple[Path | None, dict[str, Any] | None]:
        return ports._dataset_catalog().find_dataset_resource(dataset_id, user, include_samples=include_samples, write=write)

    def training_resources_payload(*, include_samples: bool=False, user: dict[str, Any] | None=None, target_user_id: str | None=None) -> dict[str, Any]:
        return ports._training_resources().training_resources_payload(include_samples=include_samples, user=user, target_user_id=target_user_id)

    def agent_model_options_from_items(items: Any, *, prepend: list[dict[str, str]] | None=None) -> list[dict[str, str]]:
        return ports._provider_configuration().agent_model_options_from_items(items, prepend=prepend)

    def cursor_auth_headers(api_key: str) -> dict[str, str]:
        return ports._agent_protocol_policy().cursor_auth_headers(api_key)

    def cursor_api_url(base_url: str, path: str) -> str:
        return ports._agent_protocol_policy().cursor_api_url(base_url, path)

    def _text_v2_owner() -> tuple[str, str]:
        user = ports.current_auth_user()()
        return (str(user.get('id') or ''), str(user.get('username') or ''))

    def _run_text_compare_beta(user_id: str, clean_id: str, reference_bytes: bytes, captured_bytes: bytes) -> dict[str, Any]:
        return ports._beta_comparison().run(user_id, clean_id, reference_bytes, captured_bytes)

    def purge_expired_incoming_text_evidence() -> dict[str, int]:
        return ports._incoming_retention().purge()

    reject_untrusted_cross_origin_writes = ports._authentication_http().register_security(app)

    app.mount('/static/assets', StaticFiles(directory=values.REACT_PRODUCTION_ASSETS_DIR, check_dir=False), name='react-production-assets')

    app.mount('/static', StaticFiles(directory=values.STATIC_DIR), name='static')

    app.mount('/react-preview/assets', StaticFiles(directory=values.REACT_PREVIEW_ASSETS_DIR, check_dir=False), name='react-preview-assets')

    app.mount('/outputs', ArtifactStaticFiles(directory=values.OUTPUT_DIR, runtime_provider=lambda: ports._business_files().runtime_provider()), name='outputs')

    @app.on_event('startup')
    def start_plc_runtime_workers() -> None:
        return None

    @app.on_event('startup')
    def start_ai_mcp_warmup() -> None:
        if external_ai_mcp_enabled():
            ports._ai_mcp_client().start_warmup(ports.warm_ai_mcp_client(), threads=threading.Thread)

    @app.on_event('startup')
    def start_worker_training_watcher() -> None:
        return _retired_worker_watcher_start()

    @app.on_event('startup')
    def start_yolo_model_warmup() -> None:
        start_yolo_warmup('startup')

    _auth_routes = ports._authentication_http().register_auth(app)

    auth_status = _auth_routes.auth_status

    auth_bootstrap = _auth_routes.auth_bootstrap

    auth_login = _auth_routes.auth_login

    auth_logout = _auth_routes.auth_logout

    get_task_navigation_preferences = _auth_routes.get_task_navigation_preferences

    update_task_navigation_preferences = _auth_routes.update_task_navigation_preferences

    openapi_schema, swagger_ui, redoc_ui = ports._authentication_http().register_documentation(app)

    _user_routes = ports._authentication_http().register_users(app)

    list_users = _user_routes.list_users

    create_user = _user_routes.create_user

    update_user = _user_routes.update_user

    reset_user_password = _user_routes.reset_user_password

    delete_user = _user_routes.delete_user

    register_entry_routes(app, ports._web_shell())

    @app.get('/api/status')
    def status(user_id: str | None=None) -> dict[str, Any]:
        return ports._service_status_requests().status(user_id)

    _model_warmup_requests = compose_model_warmup_api(app, access=ModelWarmupAccess(ports._access_control().current_auth_user, ports._app_config_store().load_config, ports._account_projections().scope_config_for_user), models=ModelWarmupModels(ports._model_selection().selected_model_spec, ports._local_models().yolo_model_ready), status=ports._yolo_warmup_runtime().public_yolo_warmup_status, start=bind_warmup_start(ports._yolo_warmup_runtime()))

    warmup_detection_model = _model_warmup_requests.warmup_detection_model

    @app.get('/api/config')
    def get_config() -> dict[str, Any]:
        return public_path_sanitized(scope_config_for_user(load_config()))

    @app.get('/api/config/summary')
    def get_config_summary(user_id: str | None=None) -> dict[str, Any]:
        return ports._service_status_requests().get_config_summary(user_id)

    _register_config_diagnostics_routes(app, get_config=get_plc_config, update_config=update_plc_config)

    @app.get('/api/version')
    def get_release_version() -> dict[str, Any]:
        return current_release_version()

    _plc_self_service_routes = register_workstation_self_service(app, ports._plc_workstation_self_service())
    self_pair_plc_workstation = _plc_self_service_routes.self_pair_plc_workstation
    self_config_plc_workstation = _plc_self_service_routes.self_config_plc_workstation

    _register_workstation_management_routes(app, get_workstation=get_plc_web_serial_workstation, list_workstations=list_plc_web_serial_workstations, pair_workstation=pair_plc_web_serial_workstation, update_config=update_plc_web_serial_workstation_config, verify_profile=verify_plc_web_serial_workstation_profile)

    _register_connection_lease_routes(app, claim=claim_plc_web_serial_connection, activate=activate_plc_web_serial_connection, heartbeat=heartbeat_plc_web_serial_connection, rebind_model=rebind_plc_web_serial_connection_model, disconnect=disconnect_plc_web_serial_connection)

    _register_dispatch_diagnostic_routes(app, declare_attempt=declare_plc_web_serial_attempt, diagnostic_plan=create_plc_web_serial_diagnostic_plan, diagnostic_receipt=finish_plc_web_serial_diagnostic, diagnostic_confirm=confirm_plc_web_serial_diagnostic, record_receipt=record_plc_web_serial_receipt_endpoint)

    @app.post('/api/plc/capture-sessions/claim')
    def claim_plc_capture_session(request: PlcCaptureSessionRequest) -> dict[str, Any]:
        raise HTTPException(status_code=410, detail='legacy_plc_input_capture_is_read_only')

    @app.post('/api/plc/capture-sessions/heartbeat')
    def heartbeat_plc_capture_session(request: PlcCaptureSessionHeartbeatRequest) -> dict[str, Any]:
        raise HTTPException(status_code=410, detail='legacy_plc_input_capture_is_read_only')

    @app.delete('/api/plc/capture-sessions/{session_id}')
    def release_plc_capture_session(session_id: str) -> dict[str, Any]:
        raise HTTPException(status_code=410, detail='legacy_plc_input_capture_is_read_only')

    @app.get('/api/plc/capture-events/stream')
    def stream_plc_capture_events(session_id: str) -> StreamingResponse:
        raise HTTPException(status_code=410, detail='legacy_plc_input_capture_is_read_only')

    get_api_cost_ledger = register_cost_api(app, ports._access_control().require_admin_role, ports._cost_ledger())

    @app.get('/api/admin/runtime-store/probe')
    def get_runtime_store_probe() -> dict[str, Any]:
        ports.require_admin_role()()
        return runtime_store_probe_payload()

    @app.get('/api/windows-worker/status')
    def get_windows_worker_status(force: bool=False, services: bool=False) -> dict[str, Any]:
        raise HTTPException(status_code=410, detail={'code': 'windows_worker_retired', 'message': 'Windows Worker execution is retired. Production training uses RunPod.'})

    @app.get('/api/windows-worker/training/jobs/{job_id}')
    def get_windows_worker_training_job(job_id: str) -> dict[str, Any]:
        raise HTTPException(status_code=410, detail={'code': 'windows_worker_retired', 'message': 'Windows Worker training refresh is retired. Historical worker tasks are read-only.'})

    @app.get('/api/windows-worker/training/jobs/{job_id}/artifacts')
    def get_windows_worker_training_artifacts(job_id: str) -> dict[str, Any]:
        raise HTTPException(status_code=410, detail={'code': 'windows_worker_retired', 'message': 'Windows Worker artifact import is retired. Production model artifacts are imported from RunPod.'})

    @app.get('/api/ai/config')
    def get_ai_config() -> dict[str, Any]:
        ports.require_admin_role()()
        return public_ai_detection_status()

    @app.post('/api/ai/config')
    def update_ai_config(request: AiConfigRequest) -> dict[str, Any]:
        ports.require_admin_role()()
        raise HTTPException(409, '请使用模型与 API 配置库；旧配置入口已停用')

    @app.get('/api/locateanything/config')
    def get_locateanything_config() -> dict[str, Any]:
        removed_phase1_feature('LocateAnything')

    @app.post('/api/locateanything/config')
    def update_locateanything_config() -> dict[str, Any]:
        removed_phase1_feature('LocateAnything')

    @app.get('/api/locateanything/status')
    def locateanything_status() -> dict[str, Any]:
        removed_phase1_feature('LocateAnything')

    @app.post('/api/locateanything/runtime/start')
    def locateanything_runtime_start() -> dict[str, Any]:
        removed_phase1_feature('LocateAnything')

    @app.get('/api/locateanything/accessories')
    def locateanything_accessories() -> dict[str, Any]:
        removed_phase1_feature('LocateAnything')

    @app.post('/api/locateanything/inspect')
    async def locateanything_inspect() -> dict[str, Any]:
        removed_phase1_feature('LocateAnything')

    @app.post('/api/locateanything/locate')
    async def locateanything_locate() -> dict[str, Any]:
        removed_phase1_feature('LocateAnything')

    _analysis_routes = register_analysis_api(app, lambda: ports.current_auth_user()(), lambda feature: removed_phase1_feature(feature), ports._analysis_queries())

    list_data_analysis_records_api = _analysis_routes.list_records

    get_data_analysis_record_api = _analysis_routes.get_record

    delete_data_analysis_record_api = _analysis_routes.delete_record

    run_data_analysis_record_locate_api = _analysis_routes.locate_record

    run_data_analysis_batch_locate_api = _analysis_routes.locate_batch

    @app.delete('/api/ai/config/key')
    def delete_ai_config_key() -> dict[str, Any]:
        ports.require_admin_role()()
        raise HTTPException(409, '请在模型配置库管理 Key')

    @app.get('/api/ai/tasks')
    def get_ai_detection_tasks(user_id: str | None=None) -> dict[str, Any]:
        return ports._detection_task_requests().get_ai_detection_tasks(user_id)

    @app.post('/api/ai/tasks')
    def create_ai_detection_task(request: AiDetectionTaskRequest) -> dict[str, Any]:
        return ports._detection_task_requests().create_ai_detection_task(request)

    @app.put('/api/ai/tasks/{task_id}')
    def update_ai_detection_task(task_id: str, request: AiDetectionTaskRequest) -> dict[str, Any]:
        return ports._detection_task_requests().update_ai_detection_task(task_id, request)

    @app.delete('/api/ai/tasks/{task_id}')
    def delete_ai_detection_task(task_id: str) -> dict[str, Any]:
        return ports._detection_task_requests().delete_ai_detection_task(task_id)

    @app.get('/api/ai/tasks/{task_id}/auto-optimize')
    def get_ai_task_auto_optimize_status(task_id: str) -> dict[str, Any]:
        return ports._auto_optimization_requests().get_ai_task_auto_optimize_status(task_id)

    @app.patch('/api/ai/tasks/{task_id}/auto-optimize')
    def update_ai_task_auto_optimize_status(task_id: str, request: AutoOptimizeSettingsRequest) -> dict[str, Any]:
        return ports._auto_optimization_requests().update_ai_task_auto_optimize_status(task_id, request)

    @app.delete('/api/ai/tasks/{task_id}/auto-optimize/samples/{sample_id}')
    def delete_ai_task_auto_optimize_sample(task_id: str, sample_id: str) -> dict[str, Any]:
        return ports._auto_optimization_requests().delete_ai_task_auto_optimize_sample(task_id, sample_id)

    @app.post('/api/ai/tasks/{task_id}/auto-optimize/samples/{sample_id}/retry')
    def retry_ai_task_auto_optimize_sample(task_id: str, sample_id: str) -> dict[str, Any]:
        return ports._auto_optimization_requests().retry_ai_task_auto_optimize_sample(task_id, sample_id)

    @app.post('/api/ai/tasks/{task_id}/auto-optimize/samples/{sample_id}/approve')
    def approve_ai_task_auto_optimize_sample(task_id: str, sample_id: str, request: AutoOptimizeSampleApproveRequest | None=None) -> dict[str, Any]:
        return ports._auto_optimization_requests().approve_ai_task_auto_optimize_sample(task_id, sample_id, request)

    _real_photo_feedback = ports._real_photo_workflows().register(app)

    @app.on_event('startup')
    def start_real_photo_training_dispatcher():
        ports._real_photo_workflows().start()

    @app.on_event('shutdown')
    def stop_real_photo_training_dispatcher():
        ports._real_photo_workflows().stop()

    _detection_rule_requests = compose_detection_rule_api(app, policy=RulePolicy(task_rule_id=task_rule_id, CLASS_NAMES=values.CLASS_NAMES), store=RuleStore(load_config=load_config, save_config=save_config, list_trained_model_specs=list_trained_model_specs, time=time), access=RuleAccess(current_auth_user=ports.current_auth_user(), record_visible_to_user=ports.record_visible_to_user()))

    update_rules = _detection_rule_requests.update_rules

    update_task_rules = _detection_rule_requests.update_task_rules

    _accessory_catalog_routes = register_catalog_api(app, ports._accessory_catalog())

    get_accessories = _accessory_catalog_routes.get_accessories

    get_accessory_detail = _accessory_catalog_routes.get_accessory_detail

    get_accessory_candidate = register_candidate_api(app, ports._candidate_queries())

    _training_jobs_routes = _training_jobs_api.register(app, ports._training_jobs_query(), ports._training_task_mutations(), _native_ImageJobActions_9269(lambda job, action: update_codex_image_job(job, action), lambda candidate, action: update_codex_image_candidate(candidate, action)))

    image_jobs = _training_jobs_routes.image_jobs

    image_job = _training_jobs_routes.image_job

    update_training_task_endpoint = _training_jobs_routes.update_training_task_endpoint

    delete_training_task_endpoint = _training_jobs_routes.delete_training_task_endpoint

    stop_image_job = _training_jobs_routes.stop_image_job

    retry_image_job = _training_jobs_routes.retry_image_job

    delete_image_job = _training_jobs_routes.delete_image_job

    stop_image_job_candidate = _training_jobs_routes.stop_image_job_candidate

    delete_image_job_candidate = _training_jobs_routes.delete_image_job_candidate

    _accessory_management_routes = register_management_api(app, ports._accessory_creation(), ports._accessory_confirmation())

    add_accessory = _accessory_management_routes.add_accessory

    preview_accessory = _accessory_management_routes.preview_accessory

    confirm_accessory = _accessory_management_routes.confirm_accessory

    _accessory_file_routes = register_file_api(app, ports._accessory_files())

    add_accessory_files = _accessory_file_routes.add_accessory_files

    crop_accessory_text_image = _accessory_file_routes.crop_accessory_text_image

    set_accessory_ai_reference = _accessory_file_routes.set_accessory_ai_reference

    delete_accessory_file = _accessory_file_routes.delete_accessory_file

    delete_accessory = register_removal_api(app, ports._accessory_removal())

    @app.get('/api/label-sheets/references')
    def get_label_sheet_references() -> dict[str, Any]:
        removed_phase1_feature('Label Sheet')

    @app.post('/api/label-sheets/references')
    async def add_label_sheet_reference() -> dict[str, Any]:
        removed_phase1_feature('Label Sheet')

    @app.post('/api/label-sheets/match')
    async def match_label_sheet_endpoint() -> dict[str, Any]:
        removed_phase1_feature('Label Sheet')

    @app.post('/api/experimental/label-inspector/analyze')
    async def analyze_label_experiment() -> dict[str, Any]:
        removed_phase1_feature('Label Sheet inspector')

    @app.post('/api/analyze/image')
    async def analyze_image(file: UploadFile=File(...), model_id: str | None=Form(None), capture_session_id: str | None=Form(None)) -> dict[str, Any]:
        return await ports._image_upload().analyze_image(file, model_id, capture_session_id)

    @app.post('/api/analyze/camera')
    async def analyze_camera_image(request: Request, file: UploadFile=File(...), model_id: str | None=Form(None), plc_session_id: str=Form(...), camera_request_id: str=Form(...)) -> dict[str, Any]:
        return await ports._camera_detection_request().analyze_camera_image(request, file, model_id, plc_session_id, camera_request_id)

    @app.post('/api/analyze/video')
    @pinned_model_profiles(resolve_model_profiles)
    async def analyze_video(file: UploadFile=File(...), model_id: str | None=Form(None)) -> dict[str, Any]:
        return await ports._video_upload().analyze_video(file, model_id)

    @app.post('/api/stream/config')
    def update_stream(config_in: StreamConfig) -> dict[str, Any]:
        return ports._stream_configuration().update(config_in)

    _background_routes = _training_background_api.register(app, ports._background_query(), ports._background_upload(), ports._background_capture())

    background_image = _background_routes.background_image

    training_background_sets = _background_routes.training_background_sets

    upload_training_background_set = _background_routes.upload_training_background_set

    upload_ai_task_environment_background = _background_routes.upload_ai_task_environment_background

    request_training = _training_launch_api.register_start(app, ports._training_launch_submission())

    _training_transfer_routes = _training_transfer_api.register(app, ports._training_transfer())

    download_runpod_training_dataset = _training_transfer_routes.download_runpod_training_dataset

    upload_runpod_training_artifact = _training_transfer_routes.upload_runpod_training_artifact

    request_sample_generation = _training_launch_api.register_generate(app, ports._training_launch_submission())

    training_status = _training_launch_api.register_status(app, ports._training_status_query())

    _training_resource_routes = register_training_resource_api(app, ResourceReadAccess(lambda: ports.current_auth_user()(), lambda user: user_is_admin(user), lambda record: public_path_sanitized(record)), lambda: training_resources_payload, lambda dataset_id, **options: find_dataset_resource(dataset_id, **options))

    training_resources = _training_resource_routes.training_resources

    training_dataset_detail = _training_resource_routes.training_dataset_detail

    _training_resource_write_routes = register_training_resource_writes(app, ports._training_resource_mutations())

    delete_training_dataset = _training_resource_write_routes.delete_training_dataset

    update_training_dataset = _training_resource_write_routes.update_training_dataset

    delete_training_dataset_sample = _training_resource_write_routes.delete_training_dataset_sample

    delete_training_model = _training_resource_write_routes.delete_training_model

    update_training_model = _training_resource_write_routes.update_training_model

    _training_preview_routes = register_training_preview_api(app, ports._training_plan_query(), ports._training_preview_submission())

    training_plan = _training_preview_routes.training_plan

    training_preview = _training_preview_routes.training_preview

    @app.get('/api/agent/config')
    def get_agent_config() -> dict[str, Any]:
        return ports._agent_settings_api().get_agent_config()

    @app.post('/api/agent/config')
    def update_agent_config(request: AgentConfigRequest) -> dict[str, Any]:
        return ports._agent_settings_api().update_agent_config(request)

    @app.post('/api/agent/config/test')
    def test_agent_config() -> dict[str, Any]:
        return ports._agent_settings_api().test_agent_config()

    @app.post('/api/agent/recommend')
    def agent_recommend(request: AgentRecommendRequest) -> dict[str, Any]:
        return ports._agent_settings_api().agent_recommend(request)

    get_pipeline_tasks = ports._pipeline_tasks().register_task_list(app)

    create_pipeline_task = ports._pipeline_tasks().register_task_create(app)

    update_pipeline_task = ports._pipeline_tasks().register_task_update(app)

    add_pipeline_accessory, remove_pipeline_accessory = ports._pipeline_tasks().register_accessory_routes(app)

    delete_pipeline_task = ports._pipeline_tasks().register_task_delete(app)

    pipeline_agent_feedback = ports._pipeline_tasks().register_agent_feedback(app)

    pipeline_agent_chat = ports._pipeline_tasks().register_agent_chat(app)

    advance_pipeline_task_endpoint, cancel_pipeline_advance_endpoint = ports._pipeline_tasks().register_advance_control(app)

    _standard_routes = ports._text_standards().register_standards(app)

    import_text_inspection_standard = _standard_routes.import_text_inspection_standard

    list_text_inspection_standards = _standard_routes.list_text_inspection_standards

    get_text_inspection_standard = _standard_routes.get_text_inspection_standard

    get_text_inspection_asset_content = _standard_routes.get_text_inspection_asset_content

    add_text_inspection_standard_asset = _standard_routes.add_text_inspection_standard_asset

    patch_text_inspection_asset = _standard_routes.patch_text_inspection_asset

    confirm_text_inspection_standard = _standard_routes.confirm_text_inspection_standard

    document_import_jobs = ports._text_standards().register_documents(app)

    standard_preparation_jobs = ports._text_standards().register_preparation(app)

    ports._text_comparisons().register_history(app)

    resolve_label_extraction = ports._text_comparisons().register_extraction(app)

    register_agent_api(app, AgentAccess(current_user=lambda: ports.current_auth_user()(), require_admin=lambda: ports.require_admin_role()()), AgentAccounts(load=lambda: ports.load_auth_store()(), find=lambda store, identifier: find_user(store, identifier)), repositories=lambda: runtime_postgres_repository_or_none())

    register_codex_compare(app, ComparisonAccess(require_permission=lambda permission: ports.require_permission()(permission), owner=lambda: _text_v2_owner()), repository_factory=lambda: runtime_postgres_repository_or_none(), standards=ports._codex_standard_library(), media_dependencies=ports._codex_media(), documents=DocumentImports(docx=lambda data: extract_docx_candidates(data), doc=lambda data: extract_doc_images(data)), runtime_provider=ports._business_files().runtime_provider, environment=environment)

    register_label_inspection(app, LabelAccess(require_permission=lambda permission: ports.require_permission()(permission), require_admin=lambda: ports.require_admin_role()(), owner=lambda: _text_v2_owner()), ports._label_repository_lifecycle(), ports._label_imports(), models=lambda: resolve_model_profiles(), configuration=lambda: label_inspection_model.settings(lambda: resolve_model_profiles()), runtime_provider=ports._business_files().runtime_provider)

    _inspection_routes = ports._text_comparisons().register_inspections(app)

    compare_text_inspection_label = _inspection_routes.compare_text_inspection_label

    get_text_inspection_v2_evidence = _inspection_routes.get_text_inspection_v2_evidence

    create_text_manual_session = _inspection_routes.create_text_manual_session

    inspect_text_manual_page = _inspection_routes.inspect_text_manual_page

    complete_text_manual_session = _inspection_routes.complete_text_manual_session

    review_text_inspection_v2 = _inspection_routes.review_text_inspection_v2

    _incoming_catalog_routes = ports._incoming_workflows().register_catalog(app)

    get_incoming_text_task = _incoming_catalog_routes.get_incoming_text_task

    get_incoming_text_reference_asset = _incoming_catalog_routes.get_incoming_text_reference_asset

    create_incoming_text_reference = _incoming_catalog_routes.create_incoming_text_reference

    update_incoming_text_reference_rules = _incoming_catalog_routes.update_incoming_text_reference_rules

    clone_incoming_text_reference = _incoming_catalog_routes.clone_incoming_text_reference

    analyze_text_compare_beta = register_beta_comparison(app, BetaAccess(require_permission=lambda permission, **kwargs: ports.require_permission()(permission, **kwargs), current_user=lambda: ports.current_auth_user()()), max_bytes=lambda: values.TEXT_COMPARE_BETA_MAX_BYTES, run_provider=lambda: _run_text_compare_beta)

    _incoming_inspection_routes = ports._incoming_workflows().register_inspections(app)

    inspect_incoming_text = _incoming_inspection_routes.inspect_incoming_text

    get_incoming_text_inspection_evidence = _incoming_inspection_routes.get_incoming_text_inspection_evidence

    review_incoming_text_inspection = _incoming_inspection_routes.review_incoming_text_inspection

    list_incoming_text_inspections = _incoming_inspection_routes.list_incoming_text_inspections

    set_accessory_route = register_routing_api(app, ports._accessory_routing())

    ports._model_profile_configuration().register(app, ProfileApiDependencies(require_admin=lambda: ports.require_admin_role()(), cost_from_usage=lambda model, usage: api_cost_from_usage(model, usage), cursor_api_url=lambda base, path: cursor_api_url(base, path), cursor_auth_headers=lambda key: cursor_auth_headers(key), model_options_from_items=lambda items, **kwargs: agent_model_options_from_items(items, **kwargs), codex_compare_model=lambda: environment.get('VANTALINE_CODEX_COMPARE_MODEL', '')))

    register_spa(app, ports._web_shell())

    @app.on_event('startup')
    def resume_image_worker_queue() -> None:
        list_codex_image_jobs()
        if environment.get('LOCAL_INSPECTION_AUTO_RESUME_WORKER') == '1':
            ports.start_image_worker()()

    @app.on_event('startup')
    def enforce_incoming_text_image_retention() -> None:
        try:
            purge_expired_incoming_text_evidence()
        except Exception as exc:
            print(f'[incoming-text.retention] skipped: {type(exc).__name__}', flush=True)

    _web_shutdown = register_web_shutdown(app, (ShutdownStep('real-photo-dispatch', ports._real_photo_dispatch_runtime().close), ShutdownStep('pdf-import', app.state.label_pdf_import.close), ShutdownStep('pipeline-auto-agent', ports._pipeline_auto_agent_runtime().close), ShutdownStep('pipeline-advance', ports._pipeline_advance_runtime().close), ShutdownStep('pipeline-recommendation', ports._pipeline_recommendation_runtime().close), ShutdownStep('auto-label', ports._auto_optimization_label_processing().close), ShutdownStep('auto-shadow', ports._auto_optimization_shadow_evaluation().close), ShutdownStep('auto-training-check', ports._auto_optimization_training_scheduling().close), ShutdownStep('training', ports._training_task_runtime().close), ShutdownStep('background-codex', ports._background_codex_thread().close), ShutdownStep('image-worker', ports._image_worker_runtime().close), ShutdownStep('document-import', document_import_jobs.close), ShutdownStep('prepared-comparison', ports._prepared_comparison_runtime().close), ShutdownStep('standard-preparation', standard_preparation_jobs.close), ShutdownStep('text-extraction', ports._text_extraction_runtime().close), ShutdownStep('transfer-progress', ports._transfer_progress().close), ShutdownStep('yolo-warmup', ports._yolo_warmup_runtime().close), ShutdownStep('model-mcp', ports._ai_mcp_client().shutdown)))

    return HttpRegistration(
        _accessory_catalog_routes=_accessory_catalog_routes,
        _accessory_file_routes=_accessory_file_routes,
        _accessory_management_routes=_accessory_management_routes,
        _analysis_routes=_analysis_routes,
        _auth_routes=_auth_routes,
        _background_routes=_background_routes,
        _detection_rule_requests=_detection_rule_requests,
        _incoming_catalog_routes=_incoming_catalog_routes,
        _incoming_inspection_routes=_incoming_inspection_routes,
        _inspection_routes=_inspection_routes,
        _model_warmup_requests=_model_warmup_requests,
        _real_photo_feedback=_real_photo_feedback,
        _standard_routes=_standard_routes,
        _training_jobs_routes=_training_jobs_routes,
        _training_preview_routes=_training_preview_routes,
        _training_resource_routes=_training_resource_routes,
        _training_resource_write_routes=_training_resource_write_routes,
        _training_transfer_routes=_training_transfer_routes,
        _user_routes=_user_routes,
        _web_shutdown=_web_shutdown,
        add_accessory=add_accessory,
        add_accessory_files=add_accessory_files,
        add_label_sheet_reference=add_label_sheet_reference,
        add_text_inspection_standard_asset=add_text_inspection_standard_asset,
        agent_recommend=agent_recommend,
        analyze_camera_image=analyze_camera_image,
        analyze_image=analyze_image,
        analyze_label_experiment=analyze_label_experiment,
        analyze_text_compare_beta=analyze_text_compare_beta,
        analyze_video=analyze_video,
        approve_ai_task_auto_optimize_sample=approve_ai_task_auto_optimize_sample,
        auth_bootstrap=auth_bootstrap,
        auth_login=auth_login,
        auth_logout=auth_logout,
        auth_status=auth_status,
        background_image=background_image,
        self_pair_plc_workstation=self_pair_plc_workstation,
        self_config_plc_workstation=self_config_plc_workstation,
        claim_plc_capture_session=claim_plc_capture_session,
        clone_incoming_text_reference=clone_incoming_text_reference,
        compare_text_inspection_label=compare_text_inspection_label,
        complete_text_manual_session=complete_text_manual_session,
        confirm_accessory=confirm_accessory,
        confirm_text_inspection_standard=confirm_text_inspection_standard,
        create_ai_detection_task=create_ai_detection_task,
        create_incoming_text_reference=create_incoming_text_reference,
        create_pipeline_task=create_pipeline_task,
        create_text_manual_session=create_text_manual_session,
        create_user=create_user,
        crop_accessory_text_image=crop_accessory_text_image,
        delete_accessory=delete_accessory,
        delete_accessory_file=delete_accessory_file,
        delete_ai_config_key=delete_ai_config_key,
        delete_ai_detection_task=delete_ai_detection_task,
        delete_ai_task_auto_optimize_sample=delete_ai_task_auto_optimize_sample,
        delete_data_analysis_record_api=delete_data_analysis_record_api,
        delete_image_job=delete_image_job,
        delete_image_job_candidate=delete_image_job_candidate,
        delete_pipeline_task=delete_pipeline_task,
        delete_training_dataset=delete_training_dataset,
        delete_training_dataset_sample=delete_training_dataset_sample,
        delete_training_model=delete_training_model,
        delete_training_task_endpoint=delete_training_task_endpoint,
        delete_user=delete_user,
        document_import_jobs=document_import_jobs,
        download_runpod_training_dataset=download_runpod_training_dataset,
        enforce_incoming_text_image_retention=enforce_incoming_text_image_retention,
        get_accessories=get_accessories,
        get_accessory_candidate=get_accessory_candidate,
        get_accessory_detail=get_accessory_detail,
        get_agent_config=get_agent_config,
        get_ai_config=get_ai_config,
        get_ai_detection_tasks=get_ai_detection_tasks,
        get_ai_task_auto_optimize_status=get_ai_task_auto_optimize_status,
        get_api_cost_ledger=get_api_cost_ledger,
        get_config=get_config,
        get_config_summary=get_config_summary,
        get_data_analysis_record_api=get_data_analysis_record_api,
        get_incoming_text_inspection_evidence=get_incoming_text_inspection_evidence,
        get_incoming_text_reference_asset=get_incoming_text_reference_asset,
        get_incoming_text_task=get_incoming_text_task,
        get_label_sheet_references=get_label_sheet_references,
        get_locateanything_config=get_locateanything_config,
        get_pipeline_tasks=get_pipeline_tasks,
        get_release_version=get_release_version,
        get_runtime_store_probe=get_runtime_store_probe,
        get_task_navigation_preferences=get_task_navigation_preferences,
        get_text_inspection_asset_content=get_text_inspection_asset_content,
        get_text_inspection_standard=get_text_inspection_standard,
        get_text_inspection_v2_evidence=get_text_inspection_v2_evidence,
        get_windows_worker_status=get_windows_worker_status,
        get_windows_worker_training_artifacts=get_windows_worker_training_artifacts,
        get_windows_worker_training_job=get_windows_worker_training_job,
        heartbeat_plc_capture_session=heartbeat_plc_capture_session,
        image_job=image_job,
        image_jobs=image_jobs,
        import_text_inspection_standard=import_text_inspection_standard,
        inspect_incoming_text=inspect_incoming_text,
        inspect_text_manual_page=inspect_text_manual_page,
        list_data_analysis_records_api=list_data_analysis_records_api,
        list_incoming_text_inspections=list_incoming_text_inspections,
        list_text_inspection_standards=list_text_inspection_standards,
        list_users=list_users,
        locateanything_accessories=locateanything_accessories,
        locateanything_inspect=locateanything_inspect,
        locateanything_locate=locateanything_locate,
        locateanything_runtime_start=locateanything_runtime_start,
        locateanything_status=locateanything_status,
        match_label_sheet_endpoint=match_label_sheet_endpoint,
        patch_text_inspection_asset=patch_text_inspection_asset,
        pipeline_agent_chat=pipeline_agent_chat,
        pipeline_agent_feedback=pipeline_agent_feedback,
        preview_accessory=preview_accessory,
        reject_untrusted_cross_origin_writes=reject_untrusted_cross_origin_writes,
        release_plc_capture_session=release_plc_capture_session,
        request_sample_generation=request_sample_generation,
        request_training=request_training,
        reset_user_password=reset_user_password,
        resolve_label_extraction=resolve_label_extraction,
        resume_image_worker_queue=resume_image_worker_queue,
        retry_ai_task_auto_optimize_sample=retry_ai_task_auto_optimize_sample,
        retry_image_job=retry_image_job,
        review_incoming_text_inspection=review_incoming_text_inspection,
        review_text_inspection_v2=review_text_inspection_v2,
        run_data_analysis_batch_locate_api=run_data_analysis_batch_locate_api,
        run_data_analysis_record_locate_api=run_data_analysis_record_locate_api,
        set_accessory_ai_reference=set_accessory_ai_reference,
        set_accessory_route=set_accessory_route,
        standard_preparation_jobs=standard_preparation_jobs,
        openapi_schema=openapi_schema,
        swagger_ui=swagger_ui,
        redoc_ui=redoc_ui,
        add_pipeline_accessory=add_pipeline_accessory,
        remove_pipeline_accessory=remove_pipeline_accessory,
        advance_pipeline_task_endpoint=advance_pipeline_task_endpoint,
        cancel_pipeline_advance_endpoint=cancel_pipeline_advance_endpoint,
        start_ai_mcp_warmup=start_ai_mcp_warmup,
        start_plc_runtime_workers=start_plc_runtime_workers,
        start_real_photo_training_dispatcher=start_real_photo_training_dispatcher,
        start_worker_training_watcher=start_worker_training_watcher,
        start_yolo_model_warmup=start_yolo_model_warmup,
        status=status,
        stop_image_job=stop_image_job,
        stop_image_job_candidate=stop_image_job_candidate,
        stop_real_photo_training_dispatcher=stop_real_photo_training_dispatcher,
        stream_plc_capture_events=stream_plc_capture_events,
        test_agent_config=test_agent_config,
        training_background_sets=training_background_sets,
        training_dataset_detail=training_dataset_detail,
        training_plan=training_plan,
        training_preview=training_preview,
        training_resources=training_resources,
        training_status=training_status,
        update_agent_config=update_agent_config,
        update_ai_config=update_ai_config,
        update_ai_detection_task=update_ai_detection_task,
        update_ai_task_auto_optimize_status=update_ai_task_auto_optimize_status,
        update_incoming_text_reference_rules=update_incoming_text_reference_rules,
        update_locateanything_config=update_locateanything_config,
        update_pipeline_task=update_pipeline_task,
        update_rules=update_rules,
        update_stream=update_stream,
        update_task_navigation_preferences=update_task_navigation_preferences,
        update_task_rules=update_task_rules,
        update_training_dataset=update_training_dataset,
        update_training_model=update_training_model,
        update_training_task_endpoint=update_training_task_endpoint,
        update_user=update_user,
        upload_ai_task_environment_background=upload_ai_task_environment_background,
        upload_runpod_training_artifact=upload_runpod_training_artifact,
        upload_training_background_set=upload_training_background_set,
        warmup_detection_model=warmup_detection_model,
    )
