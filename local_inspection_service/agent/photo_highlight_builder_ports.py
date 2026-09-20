"""Proposed narrow capabilities for the photo-highlight sprite coordinator."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
from .photo_highlight_ports import PhotoSourcePaths
from .photo_highlight_image_ports import PhotoMaskBounds
from .pose_execution_ports import PoseImageProvider
from .pose_materialization_ports import PoseSpriteMetadata
Record = dict[str, Any]

class PhotoProcessingItem(Protocol):
    def __call__(self, *, item_id: str, item_type: str, status: Any, label: str = '', url: Any = '', created_at: Any = 0, updated_at: Any = 0, reason: str = '', metrics: Record | None = None, sample_id: str = '', accessory_id: str = '', record_id: str = '', task_id: str = '') -> Record: ...
class PhotoProcessingPublisher(Protocol):
    def __call__(self, *, record_id: str, task: Record, source_path: Path, items: list[Record], accessory: Record | None = None) -> Record: ...

@dataclass(frozen=True)
class PhotoBuildPolicy:
    material: Callable[[], Callable[[Record], str]]
    sources: Callable[[], PhotoSourcePaths]
    ready: Callable[[], Callable[[Record, list[Path]], bool]]
    alpha: Callable[[], Callable[[Record], str]]
    complete: Callable[[], Callable[[Record, list[Record]], bool]]
    minimum: Callable[[], int]

@dataclass(frozen=True)
class PhotoBuildRuntime:
    identifier: Callable[[], Callable[[Record], str]]
    root: Callable[[], Path]
    output: Callable[[], Callable[[str, str], Path]]
    safe_id: Callable[[], Callable[[Any], str]]
    now: Callable[[], Callable[[], float]]
    bounded: Callable[[], Callable[[Any, int], str]]

@dataclass(frozen=True)
class PhotoBuildMasks:
    prompt: Callable[[], Callable[[Record], str]]
    input: Callable[[], Callable[[np.ndarray], tuple[np.ndarray, str, float, float] | None]]
    decode: Callable[[], Callable[[np.ndarray], tuple[np.ndarray, Record]]]
    bounds: Callable[[], PhotoMaskBounds]
    roi: Callable[[], Callable[[np.ndarray, np.ndarray], tuple[np.ndarray | None, Record]]]
    compare: Callable[[], Callable[[np.ndarray, np.ndarray | None], Record]]

@dataclass(frozen=True)
class PhotoBuildModelPolicy:
    attempts: Callable[[], int]
    error: Callable[[], type[Exception]]
    pose_version: Callable[[], int]
    photo_version: Callable[[], int]

@dataclass(frozen=True)
class PhotoBuildPublication:
    sanitize: Callable[[], Callable[[Any], str]]
    item: Callable[[], PhotoProcessingItem]
    publish: Callable[[], PhotoProcessingPublisher]

@dataclass(frozen=True)
class PhotoBuildArtifacts:
    write: Callable[[], Callable[[Path, np.ndarray, np.ndarray, Record], Record | None]]
    public_url: Callable[[], Callable[[Path], str]]
