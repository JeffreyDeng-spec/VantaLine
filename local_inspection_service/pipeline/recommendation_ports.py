"""Late-resolved collaborators for pipeline recommendation cache policy."""
from dataclasses import dataclass
from typing import Any, Callable

Record = dict[str, Any]


@dataclass(frozen=True)
class PipelineRecommendationMethodPolicy:
    normalize: Callable[[], Callable[[str], str]]
    uses_training: Callable[[], Callable[[str], bool]]


@dataclass(frozen=True)
class PipelineRecommendationLinks:
    signature: Callable[[], Callable[[Record, str], str]]
    next_stage: Callable[[], Callable[[Record], str]]
    ready: Callable[[], Callable[[Record, str], bool]]
