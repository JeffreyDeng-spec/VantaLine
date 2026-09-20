"""Draft narrow Agent pose workflow capabilities."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TextIO
Record = dict[str, Any]

class PoseStage(Protocol):
    def __call__(self, orchestration: Record, key: str, status: str, progress: int, **extra: Any) -> None: ...
class PosePause(Protocol):
    def __call__(self, task: Record, orchestration: Record, *, stage: str, reason: str, suggested_actions: list[str]) -> None: ...
class PoseReferenceContent(Protocol):
    def __call__(self, item: Record, *, max_images: int) -> tuple[list[Record], list[Record]]: ...
class PoseArtifactWriter(Protocol):
    def __call__(self, task: Record, call: Record, result: Record, *, prompt: str, reference_assets: list[Record]) -> Record: ...
class PoseImageProvider(Protocol):
    def generate_image(self, prompt: str, reference_content: list[Record], *, model: str) -> Record: ...
class PoseTracePrinter(Protocol):
    def __call__(self, *, file: TextIO) -> None: ...

@dataclass(frozen=True)
class PoseWorkflowState:
    plan: Callable[[], Callable[[Record, Record], Record]]
    current: Callable[[], Callable[[Record], Record]]
    photo_flow: Callable[[], Callable[[Record, Record], bool]]
    skip_legacy: Callable[[], Callable[[Record, Record, Record], Record]]
    stage: Callable[[], PoseStage]
    pause: Callable[[], PosePause]

@dataclass(frozen=True)
class PoseWorkflowModels:
    configuration: Callable[[], Callable[[], Record]]
    settings: Callable[[], Callable[[], Record]]
    provider: Callable[[], Callable[[Record], PoseImageProvider]]
    error: Callable[[], type[Exception]]

@dataclass(frozen=True)
class PoseCallRegistry:
    lookup: Callable[[], Callable[[Record], dict[str, Record]]]
    cached: Callable[[], Callable[[Record], bool]]
    identifier: Callable[[], Callable[[str, str, str, str], str]]
    tool: Callable[[], str]
    upsert: Callable[[], Callable[[Record, Record], Record]]

@dataclass(frozen=True)
class PoseCallContent:
    references: Callable[[], PoseReferenceContent]
    chroma: Callable[[], Callable[[Record], Record]]
    prompt: Callable[[], Callable[[Record, Record, Record, Record], str]]
    artifact: Callable[[], PoseArtifactWriter]

@dataclass(frozen=True)
class PoseCallPresentation:
    now: Callable[[], Callable[[], int]]
    bounded: Callable[[], Callable[[Any, int], str]]

@dataclass(frozen=True)
class PoseSampleSteps:
    background: Callable[[], Callable[[Record, Record], str | None]]
    photos: Callable[[], Callable[[Record, Record, Record], tuple[bool, bool]]]
    register: Callable[[], Callable[[Record, Record], Record]]
    execute: Callable[[], Callable[[Record, Record], bool]]
    materialize: Callable[[], Callable[[Record, Record], bool]]
    missing: Callable[[], Callable[[Record, Record, Record], list[str]]]
    save: Callable[[], Callable[[Record], None]]

@dataclass(frozen=True)
class PoseWorkflowDiagnostics:
    print_exception: Callable[[], PoseTracePrinter]
    stderr: Callable[[], TextIO]
