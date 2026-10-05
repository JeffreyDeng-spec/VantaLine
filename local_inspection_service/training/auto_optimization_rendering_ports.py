"""Per-use geometry and publication capabilities for synthetic training images."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
from .auto_optimization_label_generation_ports import ImageFiles, BoundingBox

Record = dict[str, Any]

class PasteAsset(Protocol):
    def __call__(self, canvas: np.ndarray, asset: np.ndarray, mask: np.ndarray,
                 center: tuple[int, int], target_size: tuple[int, int], angle: float,
                 *, return_visible_mask: bool) -> np.ndarray | tuple[np.ndarray, np.ndarray]: ...

class YoloLabel(Protocol):
    def __call__(self, class_id: int, bbox: list[int] | None,
                 *, width: int, height: int) -> str: ...

class TextFiles(Protocol):
    def write_text(self, path: Path, text: str, *, encoding: str) -> Any: ...

@dataclass(frozen=True)
class SyntheticGeometry:
    auto_optimize_load_sprite: Callable[[], Callable[[Record], tuple[np.ndarray, np.ndarray] | None]]
    auto_optimize_sprite_target_size: Callable[[], Callable[[np.ndarray, Record | None], tuple[int, int]]]
    choose_object_center_inside_background: Callable[[], Callable[[np.random.Generator, tuple[int, int], float, list[Record]], tuple[tuple[int, int], Record]]]
    paste_masked_asset: Callable[[], PasteAsset]
    alpha_bbox: Callable[[], BoundingBox]
    rotated_rect_tuple: Callable[[], Callable[[tuple[int, int], tuple[int, int], float], tuple[Any, ...]]]
    AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY: Callable[[], str]

@dataclass(frozen=True)
class SyntheticPublication:
    safe_background_set_id: Callable[[], Callable[[str], str]]
    render_training_background: Callable[[], Callable[[np.random.Generator, str, str], tuple[np.ndarray, Record]]]
    _image_files: Callable[[], ImageFiles]
    yolo_detection_label_line: Callable[[], YoloLabel]
    _business_files: Callable[[], TextFiles]
    write_training_annotation_preview: Callable[[], Callable[[Path, list[Record], Path], str]]
    public_training_output_url: Callable[[], Callable[[Path], str]]
