"""Model and image capabilities for the existing mask-verification workflow."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
import numpy as np

from ..model_providers.errors import AiProviderError

Record = dict[str, Any]


class ImageEncoder(Protocol):
    def __call__(self, image: np.ndarray, *, max_side: int, quality: int) -> str: ...


class StringList(Protocol):
    def __call__(self, value: Any, *, max_items: int, max_len: int) -> list[str]: ...


class JsonProvider(Protocol):
    def __call__(self, settings: Record, system_prompt: str, user_content: list[Record], *,
                 max_tokens: int, max_attempts: int, overloaded_retry_delay_seconds: float,
                 allow_overloaded_model_fallback: bool) -> tuple[Record, int, Record]: ...


@dataclass(frozen=True)
class AutoOptimizationMaskVerificationPorts:
    ai_detection_settings: Callable[[], Callable[[str], Record]]
    bounded_text: Callable[[], Callable[[Any, int], str]]
    string_list: Callable[[], StringList]
    image_bgr_data_url: Callable[[], ImageEncoder]
    auto_optimize_mask_verifier_overlay: Callable[[], Callable[[np.ndarray, list[Record]], np.ndarray]]
    auto_optimize_mask_verifier_crop: Callable[[], Callable[[np.ndarray, Record], np.ndarray | None]]
    generate_provider_json_with_fallback: Callable[[], JsonProvider]
    MASK_VERIFIER_SYSTEM_PROMPT: Callable[[], str]
    AiProviderError: Callable[[], type[AiProviderError]]
    clamp_unit_score: Callable[[], Callable[[Any], float]]
