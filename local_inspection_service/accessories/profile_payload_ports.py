"""Typed identity, profile projection and catalog dependencies for accessory payloads."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
Record = dict[str, Any]
class FallbackProfile(Protocol):
    def __call__(self, item: Record, reference_images: list[Record] | None = None) -> Record: ...
class RequiredProfile(Protocol):
    def __call__(self, item: Record, expected_count: int, profile: Record | None = None) -> Record: ...
class BoundedText(Protocol):
    def __call__(self, value: Any, limit: int = 240) -> str: ...
@dataclass(frozen=True)
class PayloadIdentity:
    uid: Callable[[], Callable[[Record], str]]
    material: Callable[[], Callable[[Record], str]]
@dataclass(frozen=True)
class PayloadProfiles:
    fallback: Callable[[], FallbackProfile]
    normalize: Callable[[], Callable[[Any, Record], Record]]
    required: Callable[[], RequiredProfile]
    reference: Callable[[], Callable[[Any], Record | None]]
@dataclass(frozen=True)
class PayloadCatalog:
    config: Callable[[], Callable[[], Record]]
    text: Callable[[], BoundedText]
