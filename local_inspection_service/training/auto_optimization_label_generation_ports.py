"""Per-use artifact, image policy and model dependencies for label generation."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np

from ..model_providers.errors import AiProviderError

Record = dict[str, Any]


class ImageFiles(Protocol):
    def imread(self, path: str, flags: int) -> np.ndarray | None: ...
    def imwrite(self, path: str, image: np.ndarray, params: list[int] = ...) -> bool: ...


class BusinessFiles(Protocol):
    def write_bytes(self, path: Path, data: bytes) -> Any: ...
    def unlink(self, path: Path, *, missing_ok: bool) -> Any: ...


class BoundingBox(Protocol):
    def __call__(self, mask: np.ndarray, *, threshold: int) -> list[int]: ...


class MaskPrompt(Protocol):
    def __call__(self, assignments: list[Record], *, input_w: int, input_h: int) -> str: ...


class SpriteWriter(Protocol):
    def __call__(self, *, image_bgr: np.ndarray, full_mask: np.ndarray, bbox: list[int],
                 sample_id: str, accessory_id: str, label_name: str, artifact_dir: Path,
                 source_image_path: Path) -> Record: ...


@dataclass(frozen=True)
class LabelGenerationArtifacts:
    resolve_service_path: Callable[[], Callable[[Any], Path]]
    _image_files: Callable[[], ImageFiles]
    _business_files: Callable[[], BusinessFiles]
    public_output_url_for_existing: Callable[[], Callable[[Path], str]]
    safe_record_id: Callable[[], Callable[[str], str]]
    auto_optimize_write_sprite_artifact: Callable[[], SpriteWriter]


@dataclass(frozen=True)
class LabelGenerationPolicy:
    photo_highlight_input_data_url: Callable[[], Callable[[np.ndarray], tuple[np.ndarray, str, float, float] | None]]
    auto_optimize_accessory_lookup_for_sample: Callable[[], Callable[[Record], dict[str, Record]]]
    auto_optimize_mask_target_profile: Callable[[], Callable[[Record, dict[str, Record]], Record]]
    AUTO_OPTIMIZE_MASK_PALETTE: Callable[[], list[Record]]
    AUTO_OPTIMIZE_MASK_PROMPT_MODE: Callable[[], str]
    auto_optimize_multicolor_mask_prompt: Callable[[], MaskPrompt]
    bounded_text: Callable[[], Callable[[Any, int], str]]
    decode_multicolor_mask: Callable[[], Callable[[np.ndarray, list[Record]], tuple[dict[str, np.ndarray], Record]]]
    alpha_bbox: Callable[[], BoundingBox]
    validate_auto_optimize_text_mask_region: Callable[[], Callable[[np.ndarray, np.ndarray, list[int], Record, Record], Record]]
    draw_auto_optimize_review_overlay: Callable[[], Callable[[np.ndarray, list[Record], list[Record], Path], tuple[str, Record]]]
    decode_photo_highlight_mask: Callable[[], Callable[[np.ndarray], tuple[np.ndarray, Record]]]
    photo_highlight_auto_roi_mask: Callable[[], Callable[[np.ndarray, np.ndarray], tuple[np.ndarray | None, Record]]]
    photo_highlight_auto_compare: Callable[[], Callable[[np.ndarray, np.ndarray | None], Record]]


@dataclass(frozen=True)
class LabelGenerationModels:
    auto_optimize_generate_image_with_retry: Callable[[], Callable[[Record, str, str, list[Record]], Record]]
    AiProviderError: Callable[[], type[AiProviderError]]
    auto_optimize_generate_label_for_candidate: Callable[[], Callable[[Record, Record, Record, str, Path], tuple[Record | None, Record]]]
    verify_auto_optimize_mask_sample: Callable[[], Callable[[Record, np.ndarray, list[Record]], tuple[list[Record], list[Record], Record]]]
