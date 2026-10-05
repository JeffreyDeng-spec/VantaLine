"""A complete proven native history represented by its count and latest row."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RunHistorySummary:
    count: int
    latest: dict[str, Any]
