"""A complete proven native history represented by its count and latest row."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RunHistorySummary:
    count: int
    latest: dict[str, Any]


@dataclass(frozen=True)
class BetaHistoryRead:
    """Decoded list evidence and counts from the same owner-bound SELECT row."""
    payload: Any
    reference_count: int | None
    label_count: int | None


def count_or_length(value: Any, count: int | None) -> int:
    """Preserve evaluation and len errors when SQL cannot prove a container."""
    return len(value) if count is None else count
