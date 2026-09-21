"""Narrow capabilities for accessory profile generation."""
from dataclasses import dataclass
from typing import Any, Callable, Protocol
Record = dict[str, Any]
class GenerateProfile(Protocol):
    def __call__(self, item: Record, *, allow_provider: bool = True) -> Record: ...
@dataclass(frozen=True)
class GenerationProfiles:
    fallback: Callable[[], Callable[[Record], Record]]
    normalize: Callable[[], Callable[[Any, Record], Record]]
    prompt: Callable[[], Callable[[Record], Record]]
    generate: Callable[[], GenerateProfile]
@dataclass(frozen=True)
class GenerationCalls:
    settings: Callable[[], Callable[[str], Record]]
    status: Callable[[], Callable[[Record], Record]]
    invoke: Callable[[], Callable[[str, Record], Record]]
@dataclass(frozen=True)
class GenerationReferences:
    contexts: Callable[[], Callable[[Record], list[Record]]]
    limit: Callable[[], int]
    max_side: Callable[[], int]
    quality: Callable[[], int]
@dataclass(frozen=True)
class GenerationUpdates:
    uid: Callable[[], Callable[[Record], str]]
    rename: Callable[[], Callable[[Record], bool]]
    dimensions: Callable[[], Callable[[Record, Any], bool]]
