"""Typed file and geometry capabilities for automatic training sprites."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import numpy as np

from .auto_optimization_label_generation_ports import ImageFiles, SpriteWriter, BoundingBox

Record = dict[str, Any]


@dataclass(frozen=True)
class SpriteFiles:
    resolve_service_path: Callable[[], Callable[[Any], Path]]
    _image_files: Callable[[], ImageFiles]
    OUTPUT_DIR: Callable[[], Path]
    STATIC_DIR: Callable[[], Path]
    output_write_dir_for_owner: Callable[[], Callable[[str, str], Path]]
    safe_record_id: Callable[[], Callable[[str], str]]
    auto_optimize_write_sprite_artifact: Callable[[], SpriteWriter]
    public_path_sanitized: Callable[[], Callable[[Record], Record]]
    auto_optimize_resolve_artifact_path: Callable[[], Callable[[Any], Path]]


@dataclass(frozen=True)
class SpriteGeometry:
    alpha_bbox: Callable[[], BoundingBox]
    AUTO_OPTIMIZE_SYNTHETIC_CANVAS_SIZE: Callable[[], tuple[int, int]]
    AUTO_OPTIMIZE_SYNTHETIC_MAX_UPSCALE: Callable[[], float]
    auto_optimize_sprite_records_for_sample: Callable[[], Callable[[Record], list[Record]]]
    auto_optimize_load_sprite: Callable[[], Callable[[Record], tuple[np.ndarray, np.ndarray] | None]]
    auto_optimize_sprite_visible_size: Callable[[], Callable[[np.ndarray], tuple[int, int] | None]]
    auto_optimize_source_to_canvas_scale: Callable[[], Callable[[Any, dict[str, float]], float]]
