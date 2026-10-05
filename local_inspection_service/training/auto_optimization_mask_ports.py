"""Mask prompt/profile and image-adapter capabilities, resolved at each use."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np

Record = dict[str, Any]
TextFormatter = Callable[[Any, int], str]


class MaskProfileBuilder(Protocol):
    def __call__(self, candidate: Record, item: Record, *, bounded_text: TextFormatter,
                 string_list: Callable[[Any], list[str]],
                 accessory_material_type: Callable[[Record], str]) -> Record: ...


class ImageWriter(Protocol):
    def imwrite(self, filename: str, image: np.ndarray, params: list[int]) -> bool: ...


@dataclass(frozen=True)
class AutoOptimizationMaskPromptPorts:
    LEGACY_OWNER_ID: Callable[[], str]
    AUTO_OPTIMIZE_MASK_SYSTEM_PROMPT_VERSION: Callable[[], str]
    bounded_text: Callable[[], TextFormatter]
    string_list: Callable[[], Callable[[Any], list[str]]]
    accessory_material_type: Callable[[], Callable[[Record], str]]
    load_config: Callable[[], Callable[[], Record]]
    scope_config_for_user: Callable[[], Callable[[Record, Record], Record]]
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    build_mask_target_profile: Callable[[], MaskProfileBuilder]
    auto_optimize_mask_owner_user: Callable[[], Callable[[Record], Record]]
    auto_optimize_mask_target_payload: Callable[[], Callable[[Record, int], Record]]


@dataclass(frozen=True)
class AutoOptimizationMaskVisualPorts:
    DOCUMENT_LIKE_TEXT_HINTS: Callable[[], tuple[str, ...]]
    bounded_text: Callable[[], TextFormatter]
    _image_files: Callable[[], ImageWriter]
    public_output_url_for_existing: Callable[[], Callable[[Path], str]]
    auto_optimize_text_mask_requires_document_gate: Callable[[], Callable[[Record, Record], bool]]
