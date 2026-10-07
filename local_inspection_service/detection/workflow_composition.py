"""One detection, analysis publication and automatic capture ownership graph."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import numpy as np
from ..analytics.analysis_composition import AnalysisServices, AnalysisStorage
from ..analytics.analysis_records import AnalysisNormalization
from ..analytics.analysis_service import AnalysisAccess
from ..analytics.analysis_processing import ProcessingDependencies
from ..analytics.analysis_scope import ScopeDependencies
from ..analytics.analysis_projection import ProjectionDependencies
from ..analytics.analysis_publication import PublicationDependencies, StringList
from ..training.auto_optimization_capture import AutoOptimizationCapture
from ..training.auto_optimization_capture_ports import AutoOptimizationCapturePorts, StopCapture
from ..model_profiles.dependencies import ResolverProvider
from ..model_profiles.snapshots import pinned
from ..storage.artifacts.runtime import ArtifactRuntime
from .analysis import DetectionAnalysis
from .ai_analysis import AiDetectionAnalysis
from .analysis_ports import (AnalysisInput, AnalysisRouting, AnalysisInference, AnalysisOutput,
                             AiProfiles, AiInspectionTools, AiAnalysisEvidence, FailureResult)
from .presence_payload import BoundedText

Record = dict[str, Any]

@dataclass(frozen=True)
class AnalysisPublication:
    current_user: Callable[[], Record | None]
    owner_fields: Callable[[], Record]
    owner_id: Callable[[Record], str]
    owner_username: Callable[[Record], str]
    default_task_id: str
    default_task_label: str
    clean_task_name: Callable[[Any, str], str]
    string_list: StringList
    resolve_path: Callable[[Any], Path]
    safe_name: Callable[[str], str]
    output_url: Callable[[Path], str]

@dataclass(frozen=True)
class CaptureAdmission:
    _auto_optimize_lock: Callable[[], AbstractContextManager[Any]]
    load_auto_optimize_state: Callable[[], Callable[[str], Record]]
    save_auto_optimize_state: Callable[[], Callable[[Record], None]]
    sanitize_ai_detection_task_id: Callable[[], Callable[[Any], str]]
    auto_optimize_completed_model_id: Callable[[], Callable[[Record], str]]
    auto_optimize_stop_capture_for_model_locked: Callable[[], StopCapture]
    auto_optimize_capture_enabled: Callable[[], Callable[[Record], bool]]
    resolve_service_path: Callable[[], Callable[[Path], Path]]
    bounded_text: Callable[[], Callable[[Any, int], str]]
    current_owner_fields: Callable[[], Callable[[], Record]]
    start_auto_optimize_label_worker: Callable[[], Callable[[str], None]]
    start_auto_optimize_shadow_worker: Callable[[], Callable[[str, str], None]]

@dataclass(frozen=True)
class InspectionEvidence:
    original: Callable[[np.ndarray, str], str]
    failure: FailureResult
    model: Callable[[Record, Record], Record]

@dataclass(frozen=True)
class AnalysisAssembly:
    normalization: AnalysisNormalization
    storage: AnalysisStorage
    access: AnalysisAccess
    processing: ProcessingDependencies
    scope: ScopeDependencies
    projection: ProjectionDependencies
    publication: AnalysisPublication
    cache_scope: Callable[[], AbstractContextManager]
    batch_limit: int


@dataclass(frozen=True)
class DetectionPolicy:
    retired: Callable[[str], Any]
    text: Callable[[], BoundedText]


class DetectionWorkflows:
    def __init__(self, *, analysis: AnalysisAssembly, capture: CaptureAdmission,
                 profiles: AiProfiles, tools: AiInspectionTools, evidence: InspectionEvidence,
                 inputs: AnalysisInput, policy: DetectionPolicy, inference: AnalysisInference,
                 output: AnalysisOutput, runtime_provider: Callable[[], ArtifactRuntime | None],
                 resolver: ResolverProvider):
        self.capture = AutoOptimizationCapture(AutoOptimizationCapturePorts(
            _auto_optimize_lock=capture._auto_optimize_lock,
            load_auto_optimize_state=capture.load_auto_optimize_state,
            save_auto_optimize_state=capture.save_auto_optimize_state,
            sanitize_ai_detection_task_id=capture.sanitize_ai_detection_task_id,
            auto_optimize_completed_model_id=capture.auto_optimize_completed_model_id,
            auto_optimize_stop_capture_for_model_locked=capture.auto_optimize_stop_capture_for_model_locked,
            auto_optimize_capture_enabled=capture.auto_optimize_capture_enabled,
            resolve_service_path=capture.resolve_service_path,
            bounded_text=capture.bounded_text,
            current_owner_fields=capture.current_owner_fields,
            start_auto_optimize_label_worker=capture.start_auto_optimize_label_worker,
            start_auto_optimize_shadow_worker=capture.start_auto_optimize_shadow_worker,
            auto_optimize_detection_candidates=lambda: self.capture.auto_optimize_detection_candidates,
        ))
        self.analysis = AnalysisServices(
            normalization=analysis.normalization,
            storage=analysis.storage,
            access=analysis.access,
            processing=analysis.processing,
            scope=analysis.scope,
            projection=analysis.projection,
            publication=PublicationDependencies(
                current_user=analysis.publication.current_user,
                owner_fields=analysis.publication.owner_fields,
                owner_id=analysis.publication.owner_id,
                owner_username=analysis.publication.owner_username,
                default_task_id=analysis.publication.default_task_id,
                default_task_label=analysis.publication.default_task_label,
                clean_task_name=analysis.publication.clean_task_name,
                string_list=analysis.publication.string_list,
                resolve_path=analysis.publication.resolve_path,
                safe_name=analysis.publication.safe_name,
                output_url=analysis.publication.output_url,
                capture=lambda record, result, request_id, path: self.record_capture(record, result, request_id, path),
            ),
            cache_scope=analysis.cache_scope, batch_limit=analysis.batch_limit,
        )
        self.ai = AiDetectionAnalysis(profiles, tools, AiAnalysisEvidence(
            original=evidence.original, failure=evidence.failure, model=evidence.model,
            persist=lambda result, request_id, *, image_path=None: self.persist_analysis(result, request_id, image_path=image_path),
        ))
        self.pinned_ai = pinned(resolver)(self.analyze_bgr_ai_detection)
        self.detection = DetectionAnalysis(inputs, AnalysisRouting(
            lambda image, request_id, model_id=None, *, image_path=None: self.analyze_bgr(image, request_id, model_id, image_path=image_path),
            lambda image, request_id, spec, config, *, image_path=None: self.pinned_ai(image, request_id, spec, config, image_path=image_path),
            policy.retired, policy.text,
        ), inference, output, runtime_provider=runtime_provider)

    def record_capture(self, record: Record | None, result: Record, request_id: str, image_path: Path | None) -> None:
        return self.capture.record_auto_optimize_capture(record, result, request_id, image_path)

    def persist_analysis(self, result: Record, request_id: str, *, image_path: Path | None = None) -> Record | None:
        return self.analysis.publisher.persist_data_analysis_record_for_ai_detection(result, request_id, image_path=image_path)

    def analyze_bgr_ai_detection(self, image_bgr: np.ndarray, request_id: str, spec: Record, config: Record,
                                 *, image_path: Path | None = None) -> Record:
        return self.ai.analyze_bgr_ai_detection(image_bgr, request_id, spec, config, image_path=image_path)

    def analyze_bgr(self, image_bgr: np.ndarray, request_id: str, model_id: str | None = None,
                    *, image_path: Path | None = None) -> Record:
        return self.detection.analyze_bgr(image_bgr, request_id, model_id, image_path=image_path)
