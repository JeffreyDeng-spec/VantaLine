"""Explicit document geometry, source policy and image I/O capabilities."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from fastapi import HTTPException
import numpy as np
Record = dict[str, Any]

class RatioClose(Protocol):
    def __call__(self, value: float, target: float, tolerance: float = 0.08) -> bool: ...

class ImageFiles(Protocol):
    def imread(self, filename: str) -> np.ndarray | None: ...
    def imwrite(self, filename: str, image: np.ndarray) -> bool: ...

@dataclass(frozen=True)
class TextGeometry:
    order_points: Callable[[], Callable[[np.ndarray], np.ndarray]]
    ratio_close: Callable[[], RatioClose]
    quad_is_axis_aligned: Callable[[], Callable[[np.ndarray, tuple[int, ...]], bool]]
    best_document_quad: Callable[[], Callable[[np.ndarray, float | None], np.ndarray | None]]
    target_paper_pixel_size: Callable[[], Callable[[Record | None], tuple[int, int]]]
    detect_document_quad: Callable[[], Callable[[np.ndarray, float | None], np.ndarray | None]]
    document_quad_mean_size: Callable[[], Callable[[np.ndarray], tuple[float, float]]]
    resize_document_to_paper: Callable[[], Callable[[np.ndarray, int, int], np.ndarray]]

@dataclass(frozen=True)
class TextSources:
    is_text_rectified_path: Callable[[], Callable[[Path | str], bool]]
    stable_text_crop_stem: Callable[[], Callable[[Path | str], str]]
    text_raw_crop_prefix: Callable[[], Callable[[Path | str], str]]
    text_image_paths_for_upload_limit: Callable[[], Callable[[Record], list[Path]]]
    IMAGE_REFERENCE_SUFFIXES: Callable[[], set[str]]
    MAX_TEXT_ACCESSORY_IMAGES: Callable[[], int]
    HTTPException: Callable[[], type[HTTPException]]

@dataclass(frozen=True)
class TextMedia:
    optional_float: Callable[[], Callable[[Any], float | None]]
    STANDARD_PAPER_SIZES_MM: Callable[[], dict[str, tuple[float, float]]]
    _image_files: Callable[[], ImageFiles]
