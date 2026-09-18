"""Explicit image, generation, result and policy capabilities for presence inspection."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import numpy as np
from .failure_projection import FailurePayload

Record = dict[str, Any]


class EncodePath(Protocol):
    def __call__(self, path: Path, max_side: int = 1024, quality: int = 78) -> str | None: ...


class EncodeArray(Protocol):
    def __call__(self, image_bgr: np.ndarray, max_side: int = 1280, quality: int = 82) -> str: ...


@dataclass(frozen=True)
class PresenceInput:
    settings: Callable[[], Record]
    resolve: Callable[[], Callable[[list[Any]], list[Record]]]
    path: Callable[[], EncodePath]
    image: Callable[[], EncodeArray]


@dataclass(frozen=True)
class PresenceGeneration:
    task: Callable[[list[Record]], Record]
    cache: Callable[[list[Record], Record], Record]
    tokens: Callable[[], Callable[[int, Record], int]]
    call: Callable[[], Callable[[str, Record], Record]]
    covers: Callable[[], Callable[[Any, set[str]], bool]]


@dataclass(frozen=True)
class PresenceOutput:
    failure: Callable[[], FailurePayload]
    normalize: Callable[[], Callable[[Record, list[Record], int, Record], Record]]


@dataclass(frozen=True)
class PresencePolicy:
    max_side: Callable[[], int]
    quality: Callable[[], int]
    max_attempts: Callable[[], int]
    references: Callable[[], int]
    prompt: Callable[[], str]
    schema: Callable[[], Record]
