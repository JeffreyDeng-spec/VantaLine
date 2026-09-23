"""Narrow dependencies for the pipeline background publication workflow."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol
Record = dict[str, Any]

class BackgroundReferenceContent(Protocol):
    def __call__(self, item: Record, *, max_images: int) -> tuple[list[Record], list[Record]]: ...

class BackgroundVariants(Protocol):
    def __call__(self, source: Path, directory: Path, *, count: int) -> list[Path]: ...

class BackgroundImageProvider(Protocol):
    def generate_image(self, prompt: str, reference_content: list[Record], *, model: str) -> Record: ...

@dataclass(frozen=True)
class BackgroundPublicationTasks:
    state: Callable[[], Callable[[Record], Record]]
    ids: Callable[[], Callable[[Record, list[str]], list[str]]]
    lookup: Callable[[], Callable[[Record], dict[str, Record]]]

@dataclass(frozen=True)
class BackgroundPublicationPaths:
    output: Callable[[], Callable[[str, str], Path]]
    record_id: Callable[[], Callable[[Any], str]]
    set_id: Callable[[], Callable[[str | None], str]]
    resolve: Callable[[], Callable[[Any], Path]]
    sets_directory: Callable[[], Path]

@dataclass(frozen=True)
class BackgroundPublicationSelection:
    prompt: Callable[[], Callable[[Record], str]]
    match: Callable[[], Callable[[Record, str], Record | None]]
    derive: Callable[[], Callable[[Record, Path], Path | None]]

@dataclass(frozen=True)
class BackgroundPublicationProviders:
    config: Callable[[], Callable[[], Record]]
    references: Callable[[], BackgroundReferenceContent]
    settings: Callable[[], Callable[[], Record]]
    create: Callable[[], Callable[[Record], BackgroundImageProvider]]
    error_type: Callable[[], type[Exception]]

@dataclass(frozen=True)
class BackgroundPublicationCatalog:
    images: Callable[[], Callable[[Path], list[Path]]]
    variants: Callable[[], BackgroundVariants]
    manifest: Callable[[], Callable[[], Record]]
    publish: Callable[[], Callable[[Record], None]]

@dataclass(frozen=True)
class BackgroundPublicationProjection:
    bounded: Callable[[], Callable[[Any, int], str]]
    url: Callable[[], Callable[[Path], str]]
    digest: Callable[[], Callable[[Path], str]]
    now: Callable[[], Callable[[], int]]
    legacy_owner: Callable[[], str]
