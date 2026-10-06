"""Per-use settings, source, file and layout capabilities for dataset materialization."""
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
from .auto_optimization_label_generation_ports import ImageFiles
from .auto_optimization_rendering_ports import YoloLabel
Record = dict[str, Any]

class TrainingRequirements(Protocol):
    def __call__(self, settings: Record, *, real_positive_source_count: int = 0) -> dict[str, int]: ...

class DatasetFiles(Protocol):
    def exists(self, path: Path) -> bool: ...
    def write_text(self, path: Path, text: str, *, encoding: str) -> Any: ...
    def copy2(self, source: Path, target: Path, *, local_copy: Callable[[Path, Path], Any]) -> Any: ...

@dataclass(frozen=True)
class DatasetConfiguration:
    _request_user: Callable[[], ContextVar[Record | None]]
    load_config: Callable[[], Callable[[], Record]]
    scope_config_for_user: Callable[[], Callable[[Record, Record], Record]]
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    default_auto_optimize_settings: Callable[[], Record]
    auto_optimize_samples_per_real_image: Callable[[Record], int]
    auto_optimize_positive_derivatives_per_real_image: Callable[[Record], int]
    auto_optimize_negative_samples_per_real_image: Callable[[Record], int]
    auto_optimize_training_requirements: TrainingRequirements

@dataclass(frozen=True)
class DatasetSources:
    auto_optimize_generate_synthetic_batch_for_sample: Callable[[], Callable[[str, Record, Record], list[Record]]]
    auto_optimize_bbox_training_entries: Callable[[], Callable[[Record], list[Record]]]
    AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT: Callable[[], int]

@dataclass(frozen=True)
class DatasetPublication:
    safe_record_id: Callable[[], Callable[[str], str]]
    output_write_dir_for_owner: Callable[[], Callable[[str, str], Path]]
    resolve_service_path: Callable[[], Callable[[Any], Path]]
    _image_files: Callable[[], ImageFiles]
    _business_files: Callable[[], DatasetFiles]

@dataclass(frozen=True)
class DatasetLayout:
    safe_background_set_id: Callable[[], Callable[[str], str]]
    split_counts: Callable[[], Callable[[int], dict[str, int]]]
    render_training_background: Callable[[], Callable[[np.random.Generator, str, str], tuple[np.ndarray, Record]]]
    yolo_detection_label_line: Callable[[], YoloLabel]
    write_training_annotation_preview: Callable[[], Callable[[Path, list[Record], Path], str]]
    public_training_output_url: Callable[[], Callable[[Path], str]]
    write_dataset_yaml: Callable[[], Callable[[Path, Path, list[str]], Any]]
