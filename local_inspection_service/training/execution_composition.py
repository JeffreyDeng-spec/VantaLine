"""Auto-optimization initialization, label generation and training execution graph.

The supplied core/settings/shared state are separate owners. Constructors perform no I/O.
Existing native lifecycle owners remain explicit; public compatibility decorators stay external.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from pathlib import Path
import numpy as np
from ..runtime.training_tasks import TrainingThreadLifecycle
from ..model_profiles.dependencies import ResolverProvider
from ..model_profiles.snapshots import pinned
from .auto_optimization_runtime_state import AutoOptimizationRuntimeState
from .auto_optimization_settings import AutoOptimizationSettings
from .core_composition import AutoOptimizationCore
from ..schemas.training import AutoOptimizeSampleApproveRequest
from ..schemas.training import AutoOptimizeSettingsRequest
from .auto_optimization_initialization import AutoOptimizationInitialization
from .auto_optimization_initialization_ports import AutoOptimizationAdvisorPorts
from .auto_optimization_initialization_ports import AutoOptimizationTaskInitializationPorts
from .auto_optimization_mask_prompts import AutoOptimizationMaskPrompts
from .auto_optimization_mask_ports import AutoOptimizationMaskPromptPorts
from .auto_optimization_mask_visuals import AutoOptimizationMaskVisuals
from .auto_optimization_mask_ports import AutoOptimizationMaskVisualPorts
from .auto_optimization_mask_verification import AutoOptimizationMaskVerification
from .auto_optimization_mask_verification_ports import AutoOptimizationMaskVerificationPorts
from .auto_optimization_sprite_publication import AutoOptimizationSpritePublication
from .auto_optimization_sprite_publication_ports import SpritePublication
from .auto_optimization_label_generation import AutoOptimizationLabelGeneration
from .auto_optimization_label_generation_ports import LabelGenerationArtifacts
from .auto_optimization_label_generation_ports import LabelGenerationPolicy
from .auto_optimization_label_generation_ports import LabelGenerationModels
from .auto_optimization_label_processing import AutoOptimizationLabelProcessing
from .auto_optimization_label_processing_ports import ProcessingState
from .auto_optimization_label_processing_ports import ProcessingArtifacts
from .auto_optimization_label_processing_ports import ProcessingExecution
from .auto_optimization_training_scheduling import AutoOptimizationTrainingScheduling
from .auto_optimization_training_scheduling_ports import SchedulingPolicy
from .auto_optimization_training_scheduling_ports import SchedulingSubmission
from .auto_optimization_training_scheduling_ports import SchedulingState
from .auto_optimization_sprites import AutoOptimizationSprites
from .auto_optimization_sprites_ports import SpriteFiles
from .auto_optimization_sprites_ports import SpriteGeometry
from .auto_optimization_rendering import AutoOptimizationRendering
from .auto_optimization_rendering_ports import SyntheticGeometry
from .auto_optimization_rendering_ports import SyntheticPublication
from .auto_optimization_synthetic_batch import AutoOptimizationSyntheticBatch
from .auto_optimization_synthetic_batch_ports import SyntheticBatchConfiguration
from .auto_optimization_synthetic_batch_ports import SyntheticBatchSprites
from .auto_optimization_synthetic_batch_ports import SyntheticBatchPublication
from .auto_optimization_dataset import AutoOptimizationDataset
from .auto_optimization_dataset_ports import DatasetConfiguration
from .auto_optimization_dataset_ports import DatasetSources
from .auto_optimization_dataset_ports import DatasetPublication
from .auto_optimization_dataset_ports import DatasetLayout
from .auto_optimization_requests import AutoOptimizationRequests
from .auto_optimization_requests_ports import RequestAccess
from .auto_optimization_requests_ports import RequestState
from .auto_optimization_requests_ports import RequestActions
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future
from contextvars import ContextVar
Record = dict[str, Any]
from .auto_optimization_dataset_ports import DatasetFiles as DatasetDatasetFiles
from .auto_optimization_dataset_ports import ImageFiles as DatasetImageFiles
from .auto_optimization_dataset_ports import YoloLabel as DatasetYoloLabel
from .auto_optimization_initialization_ports import GenerateInitializationJson as InitializationGenerateInitializationJson
from .auto_optimization_label_generation_ports import AiProviderError as LabelGenerationAiProviderError
from .auto_optimization_label_generation_ports import BoundingBox as LabelGenerationBoundingBox
from .auto_optimization_label_generation_ports import BusinessFiles as LabelGenerationBusinessFiles
from .auto_optimization_label_generation_ports import ImageFiles as LabelGenerationImageFiles
from .auto_optimization_label_processing_ports import ExecutorFactory as LabelProcessingExecutorFactory
from .auto_optimization_mask_ports import ImageWriter as MaskImageWriter
from .auto_optimization_mask_ports import MaskProfileBuilder as MaskMaskProfileBuilder
from .auto_optimization_mask_ports import TextFormatter as MaskTextFormatter
from .auto_optimization_mask_verification_ports import AiProviderError as MaskVerificationAiProviderError
from .auto_optimization_mask_verification_ports import ImageEncoder as MaskVerificationImageEncoder
from .auto_optimization_mask_verification_ports import JsonProvider as MaskVerificationJsonProvider
from .auto_optimization_mask_verification_ports import StringList as MaskVerificationStringList
from .auto_optimization_rendering_ports import BoundingBox as RenderingBoundingBox
from .auto_optimization_rendering_ports import ImageFiles as RenderingImageFiles
from .auto_optimization_rendering_ports import PasteAsset as RenderingPasteAsset
from .auto_optimization_rendering_ports import TextFiles as RenderingTextFiles
from .auto_optimization_rendering_ports import YoloLabel as RenderingYoloLabel
from .auto_optimization_requests_ports import Access as RequestsAccess
from .auto_optimization_requests_ports import Analyze as RequestsAnalyze
from .auto_optimization_requests_ports import HttpError as RequestsHttpError
from .auto_optimization_requests_ports import ImageFiles as RequestsImageFiles
from .auto_optimization_requests_ports import SourceFiles as RequestsSourceFiles
from .auto_optimization_sprite_publication_ports import CleanSprite as SpritePublicationCleanSprite
from .auto_optimization_sprite_publication_ports import ImageFiles as SpritePublicationImageFiles
from .auto_optimization_sprite_publication_ports import SpriteFiles as SpritePublicationSpriteFiles
from .auto_optimization_sprites_ports import BoundingBox as SpritesBoundingBox
from .auto_optimization_sprites_ports import ImageFiles as SpritesImageFiles
from .auto_optimization_training_scheduling_ports import RequestFactory as TrainingSchedulingRequestFactory
from .auto_optimization_training_scheduling_ports import TrainingQueue as TrainingSchedulingTrainingQueue

@dataclass(frozen=True)
class ExternalAutoOptimizationAdvisorPorts:
    ai_detection_settings: Callable[[], Callable[[str], Record]]
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    accessory_material_type: Callable[[], Callable[[Record], str]]
    bounded_text: Callable[[], Callable[[Any, int], str]]
    generate_provider_json_with_fallback: Callable[[], InitializationGenerateInitializationJson]

@dataclass(frozen=True)
class ExternalAutoOptimizationTaskInitializationPorts:
    sanitize_ai_detection_task_id: Callable[[], Callable[[Any], str]]
    canonical_pipeline_accessory_ids: Callable[[], Callable[[Record, list[str]], list[str]]]

@dataclass(frozen=True)
class ExternalAutoOptimizationMaskPromptPorts:
    LEGACY_OWNER_ID: Callable[[], str]
    AUTO_OPTIMIZE_MASK_SYSTEM_PROMPT_VERSION: Callable[[], str]
    bounded_text: Callable[[], MaskTextFormatter]
    string_list: Callable[[], Callable[[Any], list[str]]]
    accessory_material_type: Callable[[], Callable[[Record], str]]
    load_config: Callable[[], Callable[[], Record]]
    scope_config_for_user: Callable[[], Callable[[Record, Record], Record]]
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    build_mask_target_profile: Callable[[], MaskMaskProfileBuilder]

@dataclass(frozen=True)
class ExternalAutoOptimizationMaskVisualPorts:
    DOCUMENT_LIKE_TEXT_HINTS: Callable[[], tuple[str, ...]]
    bounded_text: Callable[[], MaskTextFormatter]
    _image_files: Callable[[], MaskImageWriter]
    public_output_url_for_existing: Callable[[], Callable[[Path], str]]

@dataclass(frozen=True)
class ExternalAutoOptimizationMaskVerificationPorts:
    ai_detection_settings: Callable[[], Callable[[str], Record]]
    bounded_text: Callable[[], Callable[[Any, int], str]]
    string_list: Callable[[], MaskVerificationStringList]
    image_bgr_data_url: Callable[[], MaskVerificationImageEncoder]
    generate_provider_json_with_fallback: Callable[[], MaskVerificationJsonProvider]
    MASK_VERIFIER_SYSTEM_PROMPT: Callable[[], str]
    AiProviderError: Callable[[], type[MaskVerificationAiProviderError]]

@dataclass(frozen=True)
class ExternalSpritePublication:
    safe_record_id: Callable[[], Callable[[str], str]]
    _image_files: Callable[[], SpritePublicationImageFiles]
    write_clean_sprite: Callable[[], SpritePublicationCleanSprite]
    resolve_service_path: Callable[[], Callable[[Any], Path]]
    _business_files: Callable[[], SpritePublicationSpriteFiles]
    public_output_url_for_existing: Callable[[], Callable[[Path], str]]
    public_path_sanitized: Callable[[], Callable[[Any], Any]]

@dataclass(frozen=True)
class ExternalLabelGenerationArtifacts:
    resolve_service_path: Callable[[], Callable[[Any], Path]]
    _image_files: Callable[[], LabelGenerationImageFiles]
    _business_files: Callable[[], LabelGenerationBusinessFiles]
    public_output_url_for_existing: Callable[[], Callable[[Path], str]]
    safe_record_id: Callable[[], Callable[[str], str]]

@dataclass(frozen=True)
class ExternalLabelGenerationPolicy:
    photo_highlight_input_data_url: Callable[[], Callable[[np.ndarray], tuple[np.ndarray, str, float, float] | None]]
    AUTO_OPTIMIZE_MASK_PALETTE: Callable[[], list[Record]]
    AUTO_OPTIMIZE_MASK_PROMPT_MODE: Callable[[], str]
    bounded_text: Callable[[], Callable[[Any, int], str]]
    alpha_bbox: Callable[[], LabelGenerationBoundingBox]
    decode_photo_highlight_mask: Callable[[], Callable[[np.ndarray], tuple[np.ndarray, Record]]]
    photo_highlight_auto_roi_mask: Callable[[], Callable[[np.ndarray, np.ndarray], tuple[np.ndarray | None, Record]]]
    photo_highlight_auto_compare: Callable[[], Callable[[np.ndarray, np.ndarray | None], Record]]

@dataclass(frozen=True)
class ExternalLabelGenerationModels:
    auto_optimize_generate_image_with_retry: Callable[[], Callable[[Record, str, str, list[Record]], Record]]
    AiProviderError: Callable[[], type[LabelGenerationAiProviderError]]

@dataclass(frozen=True)
class ExternalProcessingState:
    sanitize_ai_detection_task_id: Callable[[], Callable[[str], str]]

@dataclass(frozen=True)
class ExternalProcessingArtifacts:
    output_write_dir_for_owner: Callable[[], Callable[[str, str], Path]]
    safe_record_id: Callable[[], Callable[[str], str]]
    bounded_text: Callable[[], Callable[[Any, int], str]]

@dataclass(frozen=True)
class ExternalProcessingExecution:
    image_generation_settings: Callable[[], Callable[[], Record]]
    AUTO_OPTIMIZE_MASK_MAX_PARALLEL: Callable[[], int]
    ThreadPoolExecutor: Callable[[], LabelProcessingExecutorFactory]
    as_completed: Callable[[], Callable[[Iterable[Future[Record]]], Iterator[Future[Record]]]]

@dataclass(frozen=True)
class ExternalSchedulingPolicy:
    AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT: Callable[[], int]

@dataclass(frozen=True)
class ExternalSchedulingSubmission:
    LEGACY_OWNER_ID: Callable[[], str]
    _request_user: Callable[[], ContextVar[Record | None]]
    scope_config_for_user: Callable[[], Callable[[Record, Record], Record]]
    load_config: Callable[[], Callable[[], Record]]
    selected_accessories: Callable[[], Callable[[Record, list[str]], list[Record]]]
    TrainingStartRequest: Callable[[], TrainingSchedulingRequestFactory]
    pipeline_ai_task_id: Callable[[], Callable[[str], str]]
    enqueue_training_task: Callable[[], TrainingSchedulingTrainingQueue]

@dataclass(frozen=True)
class ExternalSchedulingState:
    sanitize_ai_detection_task_id: Callable[[], Callable[[str], str]]
    bounded_text: Callable[[], Callable[[Any, int], str]]

@dataclass(frozen=True)
class ExternalSpriteFiles:
    resolve_service_path: Callable[[], Callable[[Any], Path]]
    _image_files: Callable[[], SpritesImageFiles]
    OUTPUT_DIR: Callable[[], Path]
    STATIC_DIR: Callable[[], Path]
    output_write_dir_for_owner: Callable[[], Callable[[str, str], Path]]
    safe_record_id: Callable[[], Callable[[str], str]]
    public_path_sanitized: Callable[[], Callable[[Record], Record]]

@dataclass(frozen=True)
class ExternalSpriteGeometry:
    alpha_bbox: Callable[[], SpritesBoundingBox]
    AUTO_OPTIMIZE_SYNTHETIC_CANVAS_SIZE: Callable[[], tuple[int, int]]
    AUTO_OPTIMIZE_SYNTHETIC_MAX_UPSCALE: Callable[[], float]

@dataclass(frozen=True)
class ExternalSyntheticGeometry:
    choose_object_center_inside_background: Callable[[], Callable[[np.random.Generator, tuple[int, int], float, list[Record]], tuple[tuple[int, int], Record]]]
    paste_masked_asset: Callable[[], RenderingPasteAsset]
    alpha_bbox: Callable[[], RenderingBoundingBox]
    rotated_rect_tuple: Callable[[], Callable[[tuple[int, int], tuple[int, int], float], tuple[Any, ...]]]
    AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY: Callable[[], str]

@dataclass(frozen=True)
class ExternalSyntheticPublication:
    safe_background_set_id: Callable[[], Callable[[str], str]]
    render_training_background: Callable[[], Callable[[np.random.Generator, str, str], tuple[np.ndarray, Record]]]
    _image_files: Callable[[], RenderingImageFiles]
    yolo_detection_label_line: Callable[[], RenderingYoloLabel]
    _business_files: Callable[[], RenderingTextFiles]
    write_training_annotation_preview: Callable[[], Callable[[Path, list[Record], Path], str]]
    public_training_output_url: Callable[[], Callable[[Path], str]]

@dataclass(frozen=True)
class ExternalSyntheticBatchConfiguration:
    safe_background_set_id: Callable[[], Callable[[str], str]]
    AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY: Callable[[], str]
    _request_user: Callable[[], ContextVar[Record | None]]
    LEGACY_OWNER_ID: Callable[[], str]
    scope_config_for_user: Callable[[], Callable[[Record, Record], Record]]
    load_config: Callable[[], Callable[[], Record]]
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]

@dataclass(frozen=True)
class ExternalSyntheticBatchPublication:
    safe_record_id: Callable[[], Callable[[str], str]]
    output_write_dir_for_owner: Callable[[], Callable[[str, str], Path]]

@dataclass(frozen=True)
class ExternalDatasetConfiguration:
    _request_user: Callable[[], ContextVar[Record | None]]
    load_config: Callable[[], Callable[[], Record]]
    scope_config_for_user: Callable[[], Callable[[Record, Record], Record]]
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]

@dataclass(frozen=True)
class ExternalDatasetSources:
    AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT: Callable[[], int]

@dataclass(frozen=True)
class ExternalDatasetPublication:
    safe_record_id: Callable[[], Callable[[str], str]]
    output_write_dir_for_owner: Callable[[], Callable[[str, str], Path]]
    resolve_service_path: Callable[[], Callable[[Any], Path]]
    _image_files: Callable[[], DatasetImageFiles]
    _business_files: Callable[[], DatasetDatasetFiles]

@dataclass(frozen=True)
class ExternalDatasetLayout:
    safe_background_set_id: Callable[[], Callable[[str], str]]
    split_counts: Callable[[], Callable[[int], dict[str, int]]]
    render_training_background: Callable[[], Callable[[np.random.Generator, str, str], tuple[np.ndarray, Record]]]
    yolo_detection_label_line: Callable[[], DatasetYoloLabel]
    write_training_annotation_preview: Callable[[], Callable[[Path, list[Record], Path], str]]
    public_training_output_url: Callable[[], Callable[[Path], str]]
    write_dataset_yaml: Callable[[], Callable[[Path, Path, list[str]], Any]]

@dataclass(frozen=True)
class ExternalRequestAccess:
    sanitize_ai_detection_task_id: Callable[[], Callable[[str], str]]
    safe_record_id: Callable[[], Callable[[str], str]]
    current_auth_user: Callable[[], Callable[[], Record | None]]
    load_ai_detection_tasks: Callable[[], Callable[[], list[Record]]]
    require_record_access: Callable[[], RequestsAccess]
    HTTPException: Callable[[], RequestsHttpError]

@dataclass(frozen=True)
class ExternalRequestActions:
    resolve_service_path: Callable[[], Callable[[Any], Path]]
    _business_files: Callable[[], RequestsSourceFiles]
    _image_files: Callable[[], RequestsImageFiles]
    analyze_bgr: Callable[[], RequestsAnalyze]
    AI_DETECTION_TASK_PREFIX: Callable[[], str]

class AutoOptimizationExecution:

    def __init__(self, *, core: AutoOptimizationCore, settings: AutoOptimizationSettings, runtime: AutoOptimizationRuntimeState, negative_samples_default: int, model_resolver: ResolverProvider, label_runtime: TrainingThreadLifecycle, scheduling_runtime: TrainingThreadLifecycle, external_AutoOptimizationAdvisorPorts: ExternalAutoOptimizationAdvisorPorts, external_AutoOptimizationTaskInitializationPorts: ExternalAutoOptimizationTaskInitializationPorts, external_AutoOptimizationMaskPromptPorts: ExternalAutoOptimizationMaskPromptPorts, external_AutoOptimizationMaskVisualPorts: ExternalAutoOptimizationMaskVisualPorts, external_AutoOptimizationMaskVerificationPorts: ExternalAutoOptimizationMaskVerificationPorts, external_SpritePublication: ExternalSpritePublication, external_LabelGenerationArtifacts: ExternalLabelGenerationArtifacts, external_LabelGenerationPolicy: ExternalLabelGenerationPolicy, external_LabelGenerationModels: ExternalLabelGenerationModels, external_ProcessingState: ExternalProcessingState, external_ProcessingArtifacts: ExternalProcessingArtifacts, external_ProcessingExecution: ExternalProcessingExecution, external_SchedulingPolicy: ExternalSchedulingPolicy, external_SchedulingSubmission: ExternalSchedulingSubmission, external_SchedulingState: ExternalSchedulingState, external_SpriteFiles: ExternalSpriteFiles, external_SpriteGeometry: ExternalSpriteGeometry, external_SyntheticGeometry: ExternalSyntheticGeometry, external_SyntheticPublication: ExternalSyntheticPublication, external_SyntheticBatchConfiguration: ExternalSyntheticBatchConfiguration, external_SyntheticBatchPublication: ExternalSyntheticBatchPublication, external_DatasetConfiguration: ExternalDatasetConfiguration, external_DatasetSources: ExternalDatasetSources, external_DatasetPublication: ExternalDatasetPublication, external_DatasetLayout: ExternalDatasetLayout, external_RequestAccess: ExternalRequestAccess, external_RequestActions: ExternalRequestActions):
        self.core = core
        self.settings = settings
        self.runtime = runtime
        self.initialization = AutoOptimizationInitialization(
            negative_samples_default=negative_samples_default,
            advisor=AutoOptimizationAdvisorPorts(
                ai_detection_settings=external_AutoOptimizationAdvisorPorts.ai_detection_settings,
                accessory_lookup_by_id=external_AutoOptimizationAdvisorPorts.accessory_lookup_by_id,
                accessory_material_type=external_AutoOptimizationAdvisorPorts.accessory_material_type,
                bounded_text=external_AutoOptimizationAdvisorPorts.bounded_text,
                generate_provider_json_with_fallback=external_AutoOptimizationAdvisorPorts.generate_provider_json_with_fallback,
                clamp_auto_optimize_initialization_recommendation=lambda: self.clamp_auto_optimize_initialization_recommendation,
            ),
            task=AutoOptimizationTaskInitializationPorts(
                sanitize_ai_detection_task_id=external_AutoOptimizationTaskInitializationPorts.sanitize_ai_detection_task_id,
                canonical_pipeline_accessory_ids=external_AutoOptimizationTaskInitializationPorts.canonical_pipeline_accessory_ids,
                auto_optimize_complexity_rule_recommendation=lambda: self.auto_optimize_complexity_rule_recommendation,
                agent_auto_optimize_initialization_recommendation=lambda: self.agent_auto_optimize_initialization_recommendation,
                _auto_optimize_lock=lambda: self.runtime.lock,
                load_auto_optimize_state=lambda: self.load_auto_optimize_state,
                default_auto_optimize_settings=self.settings.default_auto_optimize_settings,
                save_auto_optimize_state=lambda: self.save_auto_optimize_state,
                start_auto_optimize_label_worker=lambda: self.start_auto_optimize_label_worker,
            ),
        )
        self.mask_prompts = AutoOptimizationMaskPrompts(
            AutoOptimizationMaskPromptPorts(
                LEGACY_OWNER_ID=external_AutoOptimizationMaskPromptPorts.LEGACY_OWNER_ID,
                AUTO_OPTIMIZE_MASK_SYSTEM_PROMPT_VERSION=external_AutoOptimizationMaskPromptPorts.AUTO_OPTIMIZE_MASK_SYSTEM_PROMPT_VERSION,
                bounded_text=external_AutoOptimizationMaskPromptPorts.bounded_text,
                string_list=external_AutoOptimizationMaskPromptPorts.string_list,
                accessory_material_type=external_AutoOptimizationMaskPromptPorts.accessory_material_type,
                load_config=external_AutoOptimizationMaskPromptPorts.load_config,
                scope_config_for_user=external_AutoOptimizationMaskPromptPorts.scope_config_for_user,
                accessory_lookup_by_id=external_AutoOptimizationMaskPromptPorts.accessory_lookup_by_id,
                build_mask_target_profile=external_AutoOptimizationMaskPromptPorts.build_mask_target_profile,
                auto_optimize_mask_owner_user=lambda: self.auto_optimize_mask_owner_user,
                auto_optimize_mask_target_payload=lambda: self.auto_optimize_mask_target_payload,
            ),
        )
        self.mask_visuals = AutoOptimizationMaskVisuals(
            AutoOptimizationMaskVisualPorts(
                DOCUMENT_LIKE_TEXT_HINTS=external_AutoOptimizationMaskVisualPorts.DOCUMENT_LIKE_TEXT_HINTS,
                bounded_text=external_AutoOptimizationMaskVisualPorts.bounded_text,
                _image_files=external_AutoOptimizationMaskVisualPorts._image_files,
                public_output_url_for_existing=external_AutoOptimizationMaskVisualPorts.public_output_url_for_existing,
                auto_optimize_text_mask_requires_document_gate=lambda: self.auto_optimize_text_mask_requires_document_gate,
            ),
        )
        self.mask_verification = AutoOptimizationMaskVerification(
            AutoOptimizationMaskVerificationPorts(
                ai_detection_settings=external_AutoOptimizationMaskVerificationPorts.ai_detection_settings,
                bounded_text=external_AutoOptimizationMaskVerificationPorts.bounded_text,
                string_list=external_AutoOptimizationMaskVerificationPorts.string_list,
                image_bgr_data_url=external_AutoOptimizationMaskVerificationPorts.image_bgr_data_url,
                auto_optimize_mask_verifier_overlay=lambda: self.auto_optimize_mask_verifier_overlay,
                auto_optimize_mask_verifier_crop=lambda: self.auto_optimize_mask_verifier_crop,
                generate_provider_json_with_fallback=external_AutoOptimizationMaskVerificationPorts.generate_provider_json_with_fallback,
                MASK_VERIFIER_SYSTEM_PROMPT=external_AutoOptimizationMaskVerificationPorts.MASK_VERIFIER_SYSTEM_PROMPT,
                AiProviderError=external_AutoOptimizationMaskVerificationPorts.AiProviderError,
                clamp_unit_score=lambda: self.clamp_unit_score,
            ),
        )
        self.sprite_publication = AutoOptimizationSpritePublication(
            publication=SpritePublication(
                safe_record_id=external_SpritePublication.safe_record_id,
                _image_files=external_SpritePublication._image_files,
                write_clean_sprite=external_SpritePublication.write_clean_sprite,
                resolve_service_path=external_SpritePublication.resolve_service_path,
                _business_files=external_SpritePublication._business_files,
                public_output_url_for_existing=external_SpritePublication.public_output_url_for_existing,
                public_path_sanitized=external_SpritePublication.public_path_sanitized,
            ),
        )
        self.label_generation = AutoOptimizationLabelGeneration(
            LabelGenerationArtifacts(
                resolve_service_path=external_LabelGenerationArtifacts.resolve_service_path,
                _image_files=external_LabelGenerationArtifacts._image_files,
                _business_files=external_LabelGenerationArtifacts._business_files,
                public_output_url_for_existing=external_LabelGenerationArtifacts.public_output_url_for_existing,
                safe_record_id=external_LabelGenerationArtifacts.safe_record_id,
                auto_optimize_write_sprite_artifact=lambda: self.auto_optimize_write_sprite_artifact,
            ),
            LabelGenerationPolicy(
                photo_highlight_input_data_url=external_LabelGenerationPolicy.photo_highlight_input_data_url,
                auto_optimize_accessory_lookup_for_sample=lambda: self.auto_optimize_accessory_lookup_for_sample,
                auto_optimize_mask_target_profile=lambda: self.auto_optimize_mask_target_profile,
                AUTO_OPTIMIZE_MASK_PALETTE=external_LabelGenerationPolicy.AUTO_OPTIMIZE_MASK_PALETTE,
                AUTO_OPTIMIZE_MASK_PROMPT_MODE=external_LabelGenerationPolicy.AUTO_OPTIMIZE_MASK_PROMPT_MODE,
                auto_optimize_multicolor_mask_prompt=lambda: self.auto_optimize_multicolor_mask_prompt,
                bounded_text=external_LabelGenerationPolicy.bounded_text,
                decode_multicolor_mask=lambda: self.decode_multicolor_mask,
                alpha_bbox=external_LabelGenerationPolicy.alpha_bbox,
                validate_auto_optimize_text_mask_region=lambda: self.validate_auto_optimize_text_mask_region,
                draw_auto_optimize_review_overlay=lambda: self.draw_auto_optimize_review_overlay,
                decode_photo_highlight_mask=external_LabelGenerationPolicy.decode_photo_highlight_mask,
                photo_highlight_auto_roi_mask=external_LabelGenerationPolicy.photo_highlight_auto_roi_mask,
                photo_highlight_auto_compare=external_LabelGenerationPolicy.photo_highlight_auto_compare,
            ),
            LabelGenerationModels(
                auto_optimize_generate_image_with_retry=external_LabelGenerationModels.auto_optimize_generate_image_with_retry,
                AiProviderError=external_LabelGenerationModels.AiProviderError,
                auto_optimize_generate_label_for_candidate=lambda: self.auto_optimize_generate_label_for_candidate,
                verify_auto_optimize_mask_sample=lambda: self.verify_auto_optimize_mask_sample,
            ),
        )
        self.label_processing = AutoOptimizationLabelProcessing(
            state=ProcessingState(
                sanitize_ai_detection_task_id=external_ProcessingState.sanitize_ai_detection_task_id,
                _auto_optimize_lock=lambda: self.runtime.lock,
                _auto_optimize_label_threads=lambda: self.runtime.label_threads,
                auto_optimize_label_worker=lambda: self.pinned_label_worker,
                load_auto_optimize_state=lambda: self.load_auto_optimize_state,
                save_auto_optimize_state=lambda: self.save_auto_optimize_state,
                auto_optimize_completed_model_id=lambda: self.auto_optimize_completed_model_id,
                auto_optimize_stop_capture_for_model_locked=lambda: self.auto_optimize_stop_capture_for_model_locked,
                default_auto_optimize_settings=self.settings.default_auto_optimize_settings,
                maybe_start_auto_optimize_training_locked=lambda: self.maybe_start_auto_optimize_training_locked,
            ),
            artifacts=ProcessingArtifacts(
                output_write_dir_for_owner=external_ProcessingArtifacts.output_write_dir_for_owner,
                safe_record_id=external_ProcessingArtifacts.safe_record_id,
                auto_optimize_generate_labels_for_sample=lambda: self.auto_optimize_generate_labels_for_sample,
                bounded_text=external_ProcessingArtifacts.bounded_text,
                auto_optimize_generate_synthetic_batch_for_sample=lambda: self.auto_optimize_generate_synthetic_batch_for_sample,
            ),
            execution=ProcessingExecution(
                image_generation_settings=external_ProcessingExecution.image_generation_settings,
                AUTO_OPTIMIZE_MASK_MAX_PARALLEL=external_ProcessingExecution.AUTO_OPTIMIZE_MASK_MAX_PARALLEL,
                ThreadPoolExecutor=external_ProcessingExecution.ThreadPoolExecutor,
                as_completed=external_ProcessingExecution.as_completed,
                auto_optimize_process_label_sample=lambda: self.auto_optimize_process_label_sample,
            ),
            runtime=label_runtime,
            model_resolver=model_resolver,
        )
        self.training_scheduling = AutoOptimizationTrainingScheduling(
            policy=SchedulingPolicy(
                auto_optimize_completed_model_id=lambda: self.auto_optimize_completed_model_id,
                auto_optimize_stop_capture_for_model_locked=lambda: self.auto_optimize_stop_capture_for_model_locked,
                default_auto_optimize_settings=self.settings.default_auto_optimize_settings,
                auto_optimize_training_requirements=self.settings.auto_optimize_training_requirements,
                auto_optimize_samples_per_real_image=self.settings.auto_optimize_samples_per_real_image,
                auto_optimize_positive_derivatives_per_real_image=self.settings.auto_optimize_positive_derivatives_per_real_image,
                auto_optimize_negative_samples_per_real_image=self.settings.auto_optimize_negative_samples_per_real_image,
                AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT=external_SchedulingPolicy.AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT,
                auto_optimize_training_parameters=self.settings.auto_optimize_training_parameters,
            ),
            submission=SchedulingSubmission(
                build_auto_optimize_dataset=lambda: self.build_auto_optimize_dataset,
                LEGACY_OWNER_ID=external_SchedulingSubmission.LEGACY_OWNER_ID,
                _request_user=external_SchedulingSubmission._request_user,
                scope_config_for_user=external_SchedulingSubmission.scope_config_for_user,
                load_config=external_SchedulingSubmission.load_config,
                selected_accessories=external_SchedulingSubmission.selected_accessories,
                TrainingStartRequest=external_SchedulingSubmission.TrainingStartRequest,
                pipeline_ai_task_id=external_SchedulingSubmission.pipeline_ai_task_id,
                enqueue_training_task=external_SchedulingSubmission.enqueue_training_task,
            ),
            state=SchedulingState(
                sanitize_ai_detection_task_id=external_SchedulingState.sanitize_ai_detection_task_id,
                _auto_optimize_lock=lambda: self.runtime.lock,
                load_auto_optimize_state=lambda: self.load_auto_optimize_state,
                save_auto_optimize_state=lambda: self.save_auto_optimize_state,
                maybe_start_auto_optimize_training_locked=lambda: self.maybe_start_auto_optimize_training_locked,
                bounded_text=external_SchedulingState.bounded_text,
                auto_optimize_training_check_worker=lambda: self.pinned_check_worker,
            ),
            runtime=scheduling_runtime,
        )
        self.sprites = AutoOptimizationSprites(
            SpriteFiles(
                resolve_service_path=external_SpriteFiles.resolve_service_path,
                _image_files=external_SpriteFiles._image_files,
                OUTPUT_DIR=external_SpriteFiles.OUTPUT_DIR,
                STATIC_DIR=external_SpriteFiles.STATIC_DIR,
                output_write_dir_for_owner=external_SpriteFiles.output_write_dir_for_owner,
                safe_record_id=external_SpriteFiles.safe_record_id,
                auto_optimize_write_sprite_artifact=lambda: self.auto_optimize_write_sprite_artifact,
                public_path_sanitized=external_SpriteFiles.public_path_sanitized,
                auto_optimize_resolve_artifact_path=lambda: self.auto_optimize_resolve_artifact_path,
            ),
            SpriteGeometry(
                alpha_bbox=external_SpriteGeometry.alpha_bbox,
                AUTO_OPTIMIZE_SYNTHETIC_CANVAS_SIZE=external_SpriteGeometry.AUTO_OPTIMIZE_SYNTHETIC_CANVAS_SIZE,
                AUTO_OPTIMIZE_SYNTHETIC_MAX_UPSCALE=external_SpriteGeometry.AUTO_OPTIMIZE_SYNTHETIC_MAX_UPSCALE,
                auto_optimize_sprite_records_for_sample=lambda: self.auto_optimize_sprite_records_for_sample,
                auto_optimize_load_sprite=lambda: self.auto_optimize_load_sprite,
                auto_optimize_sprite_visible_size=lambda: self.auto_optimize_sprite_visible_size,
                auto_optimize_source_to_canvas_scale=lambda: self.auto_optimize_source_to_canvas_scale,
            ),
        )
        self.rendering = AutoOptimizationRendering(
            geometry=SyntheticGeometry(
                auto_optimize_load_sprite=lambda: self.auto_optimize_load_sprite,
                auto_optimize_sprite_target_size=lambda: self.auto_optimize_sprite_target_size,
                choose_object_center_inside_background=external_SyntheticGeometry.choose_object_center_inside_background,
                paste_masked_asset=external_SyntheticGeometry.paste_masked_asset,
                alpha_bbox=external_SyntheticGeometry.alpha_bbox,
                rotated_rect_tuple=external_SyntheticGeometry.rotated_rect_tuple,
                AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY=external_SyntheticGeometry.AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY,
            ),
            publication=SyntheticPublication(
                safe_background_set_id=external_SyntheticPublication.safe_background_set_id,
                render_training_background=external_SyntheticPublication.render_training_background,
                _image_files=external_SyntheticPublication._image_files,
                yolo_detection_label_line=external_SyntheticPublication.yolo_detection_label_line,
                _business_files=external_SyntheticPublication._business_files,
                write_training_annotation_preview=external_SyntheticPublication.write_training_annotation_preview,
                public_training_output_url=external_SyntheticPublication.public_training_output_url,
            ),
        )
        self.synthetic_batch = AutoOptimizationSyntheticBatch(
            configuration=SyntheticBatchConfiguration(
                safe_background_set_id=external_SyntheticBatchConfiguration.safe_background_set_id,
                default_auto_optimize_settings=self.settings.default_auto_optimize_settings,
                auto_optimize_positive_derivatives_per_real_image=self.settings.auto_optimize_positive_derivatives_per_real_image,
                AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY=external_SyntheticBatchConfiguration.AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY,
                _request_user=external_SyntheticBatchConfiguration._request_user,
                LEGACY_OWNER_ID=external_SyntheticBatchConfiguration.LEGACY_OWNER_ID,
                scope_config_for_user=external_SyntheticBatchConfiguration.scope_config_for_user,
                load_config=external_SyntheticBatchConfiguration.load_config,
                accessory_lookup_by_id=external_SyntheticBatchConfiguration.accessory_lookup_by_id,
            ),
            sprites=SyntheticBatchSprites(
                auto_optimize_backfill_missing_sprites_for_sample=lambda: self.auto_optimize_backfill_missing_sprites_for_sample,
                auto_optimize_sprite_records_for_sample=lambda: self.auto_optimize_sprite_records_for_sample,
                auto_optimize_canonical_sprite_sizes=lambda: self.auto_optimize_canonical_sprite_sizes,
            ),
            publication=SyntheticBatchPublication(
                safe_record_id=external_SyntheticBatchPublication.safe_record_id,
                output_write_dir_for_owner=external_SyntheticBatchPublication.output_write_dir_for_owner,
                auto_optimize_render_synthetic_sample=lambda: self.auto_optimize_render_synthetic_sample,
            ),
        )
        self.dataset = AutoOptimizationDataset(
            configuration=DatasetConfiguration(
                _request_user=external_DatasetConfiguration._request_user,
                load_config=external_DatasetConfiguration.load_config,
                scope_config_for_user=external_DatasetConfiguration.scope_config_for_user,
                accessory_lookup_by_id=external_DatasetConfiguration.accessory_lookup_by_id,
                default_auto_optimize_settings=self.settings.default_auto_optimize_settings,
                auto_optimize_samples_per_real_image=self.settings.auto_optimize_samples_per_real_image,
                auto_optimize_positive_derivatives_per_real_image=self.settings.auto_optimize_positive_derivatives_per_real_image,
                auto_optimize_negative_samples_per_real_image=self.settings.auto_optimize_negative_samples_per_real_image,
                auto_optimize_training_requirements=self.settings.auto_optimize_training_requirements,
            ),
            sources=DatasetSources(
                auto_optimize_generate_synthetic_batch_for_sample=lambda: self.auto_optimize_generate_synthetic_batch_for_sample,
                auto_optimize_bbox_training_entries=lambda: self.auto_optimize_bbox_training_entries,
                AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT=external_DatasetSources.AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT,
            ),
            publication=DatasetPublication(
                safe_record_id=external_DatasetPublication.safe_record_id,
                output_write_dir_for_owner=external_DatasetPublication.output_write_dir_for_owner,
                resolve_service_path=external_DatasetPublication.resolve_service_path,
                _image_files=external_DatasetPublication._image_files,
                _business_files=external_DatasetPublication._business_files,
            ),
            layout=DatasetLayout(
                safe_background_set_id=external_DatasetLayout.safe_background_set_id,
                split_counts=external_DatasetLayout.split_counts,
                render_training_background=external_DatasetLayout.render_training_background,
                yolo_detection_label_line=external_DatasetLayout.yolo_detection_label_line,
                write_training_annotation_preview=external_DatasetLayout.write_training_annotation_preview,
                public_training_output_url=external_DatasetLayout.public_training_output_url,
                write_dataset_yaml=external_DatasetLayout.write_dataset_yaml,
            ),
        )
        self.requests = AutoOptimizationRequests(
            access=RequestAccess(
                sanitize_ai_detection_task_id=external_RequestAccess.sanitize_ai_detection_task_id,
                safe_record_id=external_RequestAccess.safe_record_id,
                current_auth_user=external_RequestAccess.current_auth_user,
                load_ai_detection_tasks=external_RequestAccess.load_ai_detection_tasks,
                require_record_access=external_RequestAccess.require_record_access,
                HTTPException=external_RequestAccess.HTTPException,
            ),
            state=RequestState(
                _auto_optimize_lock=lambda: self.runtime.lock,
                load_auto_optimize_state=lambda: self.load_auto_optimize_state,
                save_auto_optimize_state=lambda: self.save_auto_optimize_state,
                public_auto_optimize_state=lambda: self.public_auto_optimize_state,
                auto_optimize_update_settings=lambda: self.auto_optimize_update_settings,
            ),
            actions=RequestActions(
                resolve_service_path=external_RequestActions.resolve_service_path,
                _business_files=external_RequestActions._business_files,
                _image_files=external_RequestActions._image_files,
                analyze_bgr=external_RequestActions.analyze_bgr,
                AI_DETECTION_TASK_PREFIX=external_RequestActions.AI_DETECTION_TASK_PREFIX,
                auto_optimize_bbox_training_entries=lambda: self.auto_optimize_bbox_training_entries,
                start_auto_optimize_training_check_worker=lambda: self.start_auto_optimize_training_check_worker,
            ),
        )
        self.pinned_label_worker = pinned(model_resolver, lambda identity: self.load_auto_optimize_state(identity))(self.auto_optimize_label_worker)
        self.pinned_check_worker = pinned(model_resolver, lambda identity: self.load_auto_optimize_state(identity))(self.auto_optimize_training_check_worker)

    def agent_auto_optimize_initialization_recommendation(self, config: dict[str, Any], accessory_ids: list[str], expected_production_count: int, fallback: dict[str, Any]) -> dict[str, Any]:
        return self.initialization.agent_auto_optimize_initialization_recommendation(config, accessory_ids, expected_production_count, fallback)

    def initialize_auto_optimize_for_pipeline_task(self, task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        return self.initialization.initialize_auto_optimize_for_pipeline_task(task, config)

    def auto_optimize_mask_system_prompt(self) -> str:
        return self.mask_prompts.auto_optimize_mask_system_prompt()

    def auto_optimize_mask_owner_user(self, sample: dict[str, Any]) -> dict[str, Any]:
        return self.mask_prompts.auto_optimize_mask_owner_user(sample)

    def auto_optimize_accessory_lookup_for_sample(self, sample: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return self.mask_prompts.auto_optimize_accessory_lookup_for_sample(sample)

    def auto_optimize_mask_target_profile(self, candidate: dict[str, Any], accessories_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return self.mask_prompts.auto_optimize_mask_target_profile(candidate, accessories_by_id)

    def auto_optimize_mask_target_payload(self, item: dict[str, Any], index: int) -> dict[str, Any]:
        return self.mask_prompts.auto_optimize_mask_target_payload(item, index)

    def auto_optimize_mask_user_prompt(self, assignments: list[dict[str, Any]], *, input_w: int, input_h: int, task_type: str='multi_class_segmentation_mask') -> str:
        return self.mask_prompts.auto_optimize_mask_user_prompt(assignments, input_w=input_w, input_h=input_h, task_type=task_type)

    def auto_optimize_multicolor_mask_prompt(self, assignments: list[dict[str, Any]], *, input_w: int=0, input_h: int=0) -> str:
        return self.mask_prompts.auto_optimize_multicolor_mask_prompt(assignments, input_w=input_w, input_h=input_h)

    def decode_multicolor_mask(self, mask_bgr: np.ndarray, assignments: list[dict[str, Any]]) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
        return self.mask_visuals.decode_multicolor_mask(mask_bgr, assignments)

    def draw_auto_optimize_review_overlay(self, image_bgr: np.ndarray, labels: list[dict[str, Any]], failures: list[dict[str, Any]], output_path: Path) -> tuple[str, dict[str, Any]]:
        return self.mask_visuals.draw_auto_optimize_review_overlay(image_bgr, labels, failures, output_path)

    def auto_optimize_text_mask_requires_document_gate(self, candidate: dict[str, Any], profile: dict[str, Any]) -> bool:
        return self.mask_visuals.auto_optimize_text_mask_requires_document_gate(candidate, profile)

    def validate_auto_optimize_text_mask_region(self, image_bgr: np.ndarray, full_mask: np.ndarray, bbox: list[int], candidate: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        return self.mask_visuals.validate_auto_optimize_text_mask_region(image_bgr, full_mask, bbox, candidate, profile)

    def auto_optimize_mask_verifier_overlay(self, image_bgr: np.ndarray, labels: list[dict[str, Any]]) -> np.ndarray:
        return self.mask_visuals.auto_optimize_mask_verifier_overlay(image_bgr, labels)

    def auto_optimize_mask_verifier_crop(self, image_bgr: np.ndarray, label: dict[str, Any]) -> np.ndarray | None:
        return self.mask_visuals.auto_optimize_mask_verifier_crop(image_bgr, label)

    def clamp_unit_score(self, value: Any, default: float=0.0) -> float:
        return self.mask_visuals.clamp_unit_score(value, default)

    def verify_auto_optimize_mask_sample(self, sample: dict[str, Any], image_bgr: np.ndarray, labels: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        return self.mask_verification.verify_auto_optimize_mask_sample(sample, image_bgr, labels)

    def auto_optimize_write_sprite_artifact(self, *, image_bgr: np.ndarray, full_mask: np.ndarray, bbox: list[int], sample_id: str, accessory_id: str, label_name: str, artifact_dir: Path, source_image_path: Path) -> dict[str, Any]:
        return self.sprite_publication.auto_optimize_write_sprite_artifact(image_bgr=image_bgr, full_mask=full_mask, bbox=bbox, sample_id=sample_id, accessory_id=accessory_id, label_name=label_name, artifact_dir=artifact_dir, source_image_path=source_image_path)

    def auto_optimize_generate_labels_for_sample(self, sample: dict[str, Any], provider_settings: dict[str, Any], model: str, artifact_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        return self.label_generation.auto_optimize_generate_labels_for_sample(sample, provider_settings, model, artifact_dir)

    def auto_optimize_generate_label_for_candidate(self, sample: dict[str, Any], candidate: dict[str, Any], provider_settings: dict[str, Any], model: str, artifact_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        return self.label_generation.auto_optimize_generate_label_for_candidate(sample, candidate, provider_settings, model, artifact_dir)

    def start_auto_optimize_label_worker(self, task_id: str) -> None:
        return self.label_processing.start_auto_optimize_label_worker(task_id)

    def auto_optimize_process_label_sample(self, task_id: str, pending: dict[str, Any], provider_settings: dict[str, Any], model: str) -> dict[str, Any]:
        return self.label_processing.auto_optimize_process_label_sample(task_id, pending, provider_settings, model)

    def auto_optimize_label_worker(self, task_id: str) -> None:
        return self.label_processing.auto_optimize_label_worker(task_id)

    def maybe_start_auto_optimize_training_locked(self, state: dict[str, Any]) -> None:
        return self.training_scheduling.maybe_start_auto_optimize_training_locked(state)

    def auto_optimize_training_check_worker(self, task_id: str, delay_seconds: float=0.0) -> None:
        return self.training_scheduling.auto_optimize_training_check_worker(task_id, delay_seconds)

    def start_auto_optimize_training_check_worker(self, task_id: str, delay_seconds: float=0.0) -> None:
        return self.training_scheduling.start_auto_optimize_training_check_worker(task_id, delay_seconds)

    def auto_optimize_load_sprite(self, sprite: dict[str, Any]) -> tuple[np.ndarray, np.ndarray] | None:
        return self.sprites.auto_optimize_load_sprite(sprite)

    def auto_optimize_sprite_records_for_sample(self, sample: dict[str, Any]) -> list[dict[str, Any]]:
        return self.sprites.auto_optimize_sprite_records_for_sample(sample)

    def auto_optimize_resolve_artifact_path(self, value: Any) -> Path:
        return self.sprites.auto_optimize_resolve_artifact_path(value)

    def auto_optimize_backfill_missing_sprites_for_sample(self, task_id: str, state: dict[str, Any], sample: dict[str, Any]) -> int:
        return self.sprites.auto_optimize_backfill_missing_sprites_for_sample(task_id, state, sample)

    def auto_optimize_public_sprite_pool(self, state: dict[str, Any], limit: int=80) -> list[dict[str, Any]]:
        return self.sprites.auto_optimize_public_sprite_pool(state, limit)

    def auto_optimize_sprite_visible_size(self, sprite_mask: np.ndarray) -> tuple[int, int] | None:
        return self.sprites.auto_optimize_sprite_visible_size(sprite_mask)

    def auto_optimize_source_to_canvas_scale(self, source_path_value: Any, cache: dict[str, float]) -> float:
        return self.sprites.auto_optimize_source_to_canvas_scale(source_path_value, cache)

    def auto_optimize_canonical_sprite_sizes(self, state: dict[str, Any], extra_sprites: list[dict[str, Any]] | None=None) -> dict[str, dict[str, int]]:
        return self.sprites.auto_optimize_canonical_sprite_sizes(state, extra_sprites)

    def auto_optimize_sprite_target_size(self, sprite_mask: np.ndarray, canonical_size: dict[str, int] | None=None) -> tuple[int, int]:
        return self.sprites.auto_optimize_sprite_target_size(sprite_mask, canonical_size)

    def auto_optimize_render_synthetic_sample(self, *, sprites: list[dict[str, Any]], class_index: dict[str, int], accessories_by_id: dict[str, dict[str, Any]], output_path: Path, label_path: Path, annotated_path: Path, split: str, rng: np.random.Generator, canonical_sizes: dict[str, dict[str, int]] | None=None, background_set_id: str | None=None) -> dict[str, Any] | None:
        return self.rendering.auto_optimize_render_synthetic_sample(sprites=sprites, class_index=class_index, accessories_by_id=accessories_by_id, output_path=output_path, label_path=label_path, annotated_path=annotated_path, split=split, rng=rng, canonical_sizes=canonical_sizes, background_set_id=background_set_id)

    def auto_optimize_generate_synthetic_batch_for_sample(self, task_id: str, state: dict[str, Any], sample: dict[str, Any]) -> list[dict[str, Any]]:
        return self.synthetic_batch.auto_optimize_generate_synthetic_batch_for_sample(task_id, state, sample)

    def auto_optimize_bbox_training_entries(self, sample: dict[str, Any]) -> list[dict[str, Any]]:
        return self.dataset.auto_optimize_bbox_training_entries(sample)

    def build_auto_optimize_dataset(self, task_id: str, state: dict[str, Any], samples: list[dict[str, Any]]) -> dict[str, Any] | None:
        return self.dataset.build_auto_optimize_dataset(task_id, state, samples)

    def get_ai_task_auto_optimize_status(self, task_id: str) -> dict[str, Any]:
        return self.requests.get_ai_task_auto_optimize_status(task_id)

    def update_ai_task_auto_optimize_status(self, task_id: str, request: AutoOptimizeSettingsRequest) -> dict[str, Any]:
        return self.requests.update_ai_task_auto_optimize_status(task_id, request)

    def delete_ai_task_auto_optimize_sample(self, task_id: str, sample_id: str) -> dict[str, Any]:
        return self.requests.delete_ai_task_auto_optimize_sample(task_id, sample_id)

    def retry_ai_task_auto_optimize_sample(self, task_id: str, sample_id: str) -> dict[str, Any]:
        return self.requests.retry_ai_task_auto_optimize_sample(task_id, sample_id)

    def approve_ai_task_auto_optimize_sample(self, task_id: str, sample_id: str, request: AutoOptimizeSampleApproveRequest | None=None) -> dict[str, Any]:
        return self.requests.approve_ai_task_auto_optimize_sample(task_id, sample_id, request)

    def auto_optimize_task_path(self, task_id: str) -> Path:
        return self.core.store.auto_optimize_task_path(task_id)

    def auto_optimize_complexity_rule_recommendation(self, config: dict[str, Any], accessory_ids: list[str], expected_production_count: int) -> dict[str, Any]:
        return self.core.recommendations.auto_optimize_complexity_rule_recommendation(config, accessory_ids, expected_production_count)

    def clamp_auto_optimize_initialization_recommendation(self, raw: dict[str, Any], fallback: dict[str, Any], expected_production_count: int) -> dict[str, Any]:
        return self.core.recommendations.clamp_auto_optimize_initialization_recommendation(raw, fallback, expected_production_count)

    def public_auto_optimize_initialization_payload(self, state: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        return self.core.recommendations.public_auto_optimize_initialization_payload(state, settings)

    def load_auto_optimize_state(self, task_id: str) -> dict[str, Any]:
        return self.core.store.load_auto_optimize_state(task_id)

    def save_auto_optimize_state(self, state: dict[str, Any]) -> dict[str, Any]:
        return self.core.store.save_auto_optimize_state(state)

    def list_auto_optimize_states(self) -> list[dict[str, Any]]:
        return self.core.store.list_auto_optimize_states()

    def public_auto_optimize_state(self, task_id: str, *, user: dict[str, Any] | None=None) -> dict[str, Any]:
        return self.core.status.public_auto_optimize_state(task_id, user=user)

    def auto_optimize_phase_name(self, state: dict[str, Any]) -> str:
        return self.core.readiness.auto_optimize_phase_name(state)

    def auto_optimize_completed_model_id(self, state: dict[str, Any]) -> str:
        return self.core.readiness.auto_optimize_completed_model_id(state)

    def auto_optimize_linked_pipeline_model_id(self, state: dict[str, Any]) -> str:
        return self.core.readiness.auto_optimize_linked_pipeline_model_id(state)

    def auto_optimize_stop_capture_for_model_locked(self, state: dict[str, Any], model_id: str, *, reason: str) -> bool:
        return self.core.readiness.auto_optimize_stop_capture_for_model_locked(state, model_id, reason=reason)

    def auto_optimize_capture_enabled(self, state: dict[str, Any]) -> bool:
        return self.core.readiness.auto_optimize_capture_enabled(state)

    def auto_optimize_update_settings(self, task_id: str, request: Any) -> dict[str, Any]:
        return self.core.status.auto_optimize_update_settings(task_id, request)
