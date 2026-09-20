"""Draft narrow capabilities for Agent pose configuration, content and artifacts."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

Record = dict[str, Any]

class PoseReferenceContexts(Protocol):
    def __call__(self, item: Record, *, max_images: int) -> list[Record]: ...

class PoseArtifactPath(Protocol):
    def __call__(self, task: Record, accessory_id: str, pose_id: str, mime_type: str) -> Path: ...

class PoseMetadataSerializer(Protocol):
    def __call__(self, value: Any, /, *, ensure_ascii: bool = True, indent: int | None = None) -> str: ...

@dataclass(frozen=True)
class PoseRenderConfigurationSources:
    settings: Callable[[], Callable[[], Record]]
    provider_key: Callable[[], Callable[[str], str]]
    provider_label: Callable[[], Callable[[str], str]]
    model: Callable[[], Callable[[str], str]]
    base_url: Callable[[], Callable[[str], str]]
    key_environment: Callable[[], Callable[[str], str]]

@dataclass(frozen=True)
class PoseRenderConfigurationDefaults:
    provider: Callable[[], str]
    timeout: Callable[[], float]
    key_environment: Callable[[], str]
    model_environment: Callable[[], str]
    timeout_environment: Callable[[], str]
    high_fidelity_model: Callable[[], str]
    legacy_model_environment: Callable[[], str]
    legacy_timeout_environment: Callable[[], str]

@dataclass(frozen=True)
class PoseRenderReferences:
    contexts: Callable[[], PoseReferenceContexts]
    resolve: Callable[[], Callable[[Any], Path]]
    mime: Callable[[], Callable[[str], tuple[str | None, str | None]]]
    encode: Callable[[], Callable[[bytes], bytes]]
    public_url: Callable[[], Callable[[Path], str]]
    digest: Callable[[], Callable[[Path], str | None]]

@dataclass(frozen=True)
class PoseRenderPresentation:
    screen: Callable[[], Callable[[Any], Record]]

@dataclass(frozen=True)
class PoseRenderPaths:
    owner_root: Callable[[], Callable[[str, str], Path]]
    sanitize: Callable[[], Callable[[str], str]]

@dataclass(frozen=True)
class PoseRenderArtifacts:
    output: Callable[[], PoseArtifactPath]
    digest: Callable[[], Callable[[Path], str | None]]
    public_url: Callable[[], Callable[[Path], str]]
    bounded: Callable[[], Callable[[Any, int], str]]
    now: Callable[[], Callable[[], int]]
    dumps: Callable[[], PoseMetadataSerializer]
