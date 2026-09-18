"""Narrow capabilities for ordinary and AI detection orchestration."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
from .presence_payload import BoundedText

Record = dict[str, Any]


class AnalysisCall(Protocol):
    def __call__(self, image_bgr: np.ndarray, request_id: str, model_id: str | None = None,
                 *, image_path: Path | None = None) -> Record: ...


class AiAnalysisCall(Protocol):
    def __call__(self, image_bgr: np.ndarray, request_id: str, spec: Record, config: Record,
                 *, image_path: Path | None = None) -> Record: ...


class Predictor(Protocol):
    def predict(self, image: np.ndarray, *, imgsz: int, device: Any, conf: float, verbose: bool) -> Any: ...


class OutputImages(Protocol):
    IMWRITE_JPEG_QUALITY: int
    def imwrite(self, path: str, image: np.ndarray, params: list[int]) -> bool: ...


class DetectionSettings(Protocol):
    def __call__(self, purpose: str = "pipeline") -> Record: ...


class FailureResult(Protocol):
    def __call__(self, request_id: str, spec: Record, required_items: list[tuple[Record, int]],
                 annotated_url: str, *, reason: str) -> Record: ...


class PersistAnalysis(Protocol):
    def __call__(self, result: Record, request_id: str, *, image_path: Path | None = None) -> None: ...


@dataclass(frozen=True)
class AnalysisInput:
    load: Callable[[], Record]
    scope: Callable[[], Callable[[Record], Record]]
    select: Callable[[str | None, Record], Record]
    task_id: Callable[[], Callable[[Any], str]]
    state: Callable[[str], Record]


@dataclass(frozen=True)
class AnalysisRouting:
    analyze: AnalysisCall
    ai: AiAnalysisCall
    retired: Callable[[str], Any]
    text: Callable[[], BoundedText]


@dataclass(frozen=True)
class AnalysisInference:
    model: Callable[[], Callable[[str, Record], Predictor]]
    device: Callable[[], Any]
    parse: Callable[[Any, Record], list[Record]]
    ocr: Callable[[np.ndarray, list[Record], Record, Record], list[Record]]
    rule: Callable[[list[Record], Record, Record], Record]
    draw: Callable[[np.ndarray, list[Record], Record], np.ndarray]


@dataclass(frozen=True)
class AnalysisOutput:
    directory: Callable[[str], Path]
    resize: Callable[[], Callable[[np.ndarray, int], np.ndarray]]
    max_side: Callable[[], int]
    images: Callable[[], OutputImages]
    quality: Callable[[], int]
    url: Callable[[Path], str]


@dataclass(frozen=True)
class AiProfiles:
    required: Callable[[Record, Record], list[tuple[Record, int]]]
    uid: Callable[[Record], str]
    normalize: Callable[[Record, Record], Record]
    references: Callable[[Record], list[Record]]
    payload: Callable[[Record, int, Record | None], Record]
    save: Callable[[Record], None]


@dataclass(frozen=True)
class AiInspectionTools:
    call: Callable[[], Callable[[str, Record], Record]]
    settings: Callable[[], DetectionSettings]
    external: Callable[[], bool]
    image: Callable[[np.ndarray, str], Path]
    references_per_accessory: Callable[[], int]
    reference_max_side: Callable[[], int]
    reference_quality: Callable[[], int]


@dataclass(frozen=True)
class AiAnalysisEvidence:
    original: Callable[[np.ndarray, str], str]
    failure: FailureResult
    model: Callable[[Record, Record], Record]
    persist: PersistAnalysis
