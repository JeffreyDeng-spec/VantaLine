"""Narrow capabilities for accessory profile projection."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
Record = dict[str, Any]
class StringList(Protocol):
    def __call__(self, value: Any, fallback: list[str] | None = None, *, max_items: int = 12, max_len: int = 96) -> list[str]: ...
class CompactName(Protocol):
    def __call__(self, value: Any, *, max_words: int = 6) -> str: ...
class FallbackProfile(Protocol):
    def __call__(self, item: Record, reference_images: list[Record] | None = None) -> Record: ...
@dataclass(frozen=True)
class ProfileIdentity:
    uid: Callable[[], Callable[[Record], str]]
    material: Callable[[], Callable[[Record], str]]
    alpha: Callable[[], Callable[[Record], str]]
@dataclass(frozen=True)
class ProfileText:
    bounded: Callable[[], Callable[[Any, int], str]]
    strings: Callable[[], StringList]
    preferred: Callable[[], Callable[[Record], str]]
    compact: Callable[[], CompactName]
    size: Callable[[], Callable[[Record | None], str]]
@dataclass(frozen=True)
class ProfileDimensions:
    physical: Callable[[], Callable[[Record], Record]]
    normalize: Callable[[], Callable[[Any, Record], Record]]
    ratio: Callable[[], Callable[[Record], float]]
    number: Callable[[], Callable[[Any], float | None]]
@dataclass(frozen=True)
class ProfileReferences:
    contexts: Callable[[], Callable[[Record], list[Record]]]
    fallback: Callable[[], FallbackProfile]
    limit: Callable[[], int]
