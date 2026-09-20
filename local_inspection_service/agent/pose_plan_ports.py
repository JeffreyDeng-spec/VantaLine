"""Narrow capabilities for unchanged pose planning policy and execution."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Pattern, Protocol
Record = dict[str, Any]
class PlanStrings(Protocol):
    def __call__(self, value: Any, fallback: list[str] | None = None, *, max_items: int = 12, max_len: int = 96) -> list[str]: ...
class PlanEncoder(Protocol):
    def __call__(self, path: Path, max_side: int = 1024, quality: int = 78) -> str | None: ...
class PlanSerializer(Protocol):
    def __call__(self, value: Record, /, *, ensure_ascii: bool = True) -> str: ...
class GeneratePosePlan(Protocol):
    def __call__(self, item: Record, *, allow_provider: bool = True, force: bool = False) -> Record | None: ...
class EnsurePosePlan(Protocol):
    def __call__(self, item: Record, *, force: bool = False) -> Record | None: ...
@dataclass(frozen=True)
class PosePlanIdentity:
    uid: Callable[[], Callable[[Record], str]]
    material: Callable[[], Callable[[Record], str]]
    kind: Callable[[], Callable[[Record], str]]
    sanitize: Callable[[], Callable[[str], str]]
@dataclass(frozen=True)
class PosePlanContent:
    size: Callable[[], Callable[[Record | None], tuple[float, float, float]]]
    sprites: Callable[[], Callable[[Record], list[Record]]]
    bounded: Callable[[], Callable[[Any, int], str]]
    optional_number: Callable[[], Callable[[Any], float | None]]
    strings: Callable[[], PlanStrings]
    compile: Callable[[], Callable[[str], Pattern[str]]]
@dataclass(frozen=True)
class PosePlanRuntime:
    now: Callable[[], Callable[[], int]]
    clock: Callable[[], Callable[[], float]]
    version: Callable[[], int]
    max_poses: Callable[[], int]
    min_confidence: Callable[[], float]
@dataclass(frozen=True)
class PosePlanTemplates:
    request: Callable[[], Callable[[], Record]]
    poses: Callable[[], Callable[[str, str], list[Record]]]
    fallback: Callable[[], Callable[[Record], Record]]
@dataclass(frozen=True)
class PosePlanProvider:
    settings: Callable[[], Callable[[str], Record]]
    call: Callable[[], Callable[[str, Record], Record]]
    dumps: Callable[[], PlanSerializer]
@dataclass(frozen=True)
class PosePlanMedia:
    path: Callable[[], Callable[[Any], Path]]
    encode: Callable[[], PlanEncoder]
    max_side: Callable[[], int]
    quality: Callable[[], int]
@dataclass(frozen=True)
class PosePlanCalls:
    payload: Callable[[], Callable[[Record], Record]]
    prompt: Callable[[], Callable[[], str]]
    normalize: Callable[[], Callable[[Record, Record], Record]]
    generate: Callable[[], GeneratePosePlan]
@dataclass(frozen=True)
class PosePlanCatalog:
    lookup: Callable[[], Callable[[Record], dict[str, Record]]]
    counts: Callable[[], Callable[[Record, list[str], Any], dict[str, int]]]
    canonical_ids: Callable[[], Callable[[Record, list[str]], list[str]]]
    ensure: Callable[[], EnsurePosePlan]
