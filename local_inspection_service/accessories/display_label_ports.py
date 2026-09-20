"""Narrow policy and text capabilities for accessory display labels."""
from collections.abc import Callable, Container, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
Record = dict[str, Any]
class StringList(Protocol):
    def __call__(self, value: Any, fallback: list[str] | None = None, *, max_items: int = 12, max_len: int = 96) -> list[str]: ...
class CompactName(Protocol):
    def __call__(self, value: Any, *, max_words: int = 6) -> str: ...
@dataclass(frozen=True)
class DisplayLabelPolicy:
    generic_tokens: Callable[[], Container[str]]
    fields: Callable[[], Sequence[str]]
    fallbacks: Callable[[], Mapping[str, str]]
    phrases: Callable[[], Sequence[tuple[str, str]]]
@dataclass(frozen=True)
class DisplayLabelText:
    bounded: Callable[[], Callable[[Any, int], str]]
    strings: Callable[[], StringList]
    compact: Callable[[], CompactName]
    preferred: Callable[[], Callable[[Record], str]]
