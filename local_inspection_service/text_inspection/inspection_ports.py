"""Capabilities for label submission, evidence reads and human review."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from .standard_ports import Upload, SaveRecord
from .preparation_ports import Permission, ReadVerified
from .comparison_ports import ComparisonMedia

Record = dict[str, Any]


class CaptureUpload(Upload, Protocol):
    content_type: str | None


class PrepareImage(Protocol):
    def __call__(self, contents: bytes, *, max_bytes: int = 10*1024*1024) -> tuple[bytes, str, str, str]: ...


class ImageDiagnostic(Protocol):
    def __call__(self, contents: bytes, *, source_format: str, mime_type: str) -> Record: ...


class DiagnosticEvent(Protocol):
    def __call__(self, diagnostics: Record, stage: str, status: str, *, details: Record | None = None) -> None: ...


class PreparedSubmit(Protocol):
    def __call__(self, owner: str, username: str, standard: Record, asset: Record,
                 snapshot: Record, captured: bytes, comparison_id: str, extraction: Record | None) -> Record: ...


@dataclass(frozen=True)
class InspectionAccess:
    require_permission: Permission
    owner: Callable[[], tuple[str, str]]


@dataclass(frozen=True)
class InspectionRecords:
    owned: Callable[[str, str, str], Record | None]
    save: SaveRecord
    public: Callable[[Record], Record]


@dataclass(frozen=True)
class SubmissionPolicy:
    timeout: Callable[[], float]
    prompt_version: Callable[[], str]
    external_enabled: Callable[[], bool]
    automatic_match_verified: Callable[[], bool]
    qwen_enabled: Callable[[str], bool]


@dataclass(frozen=True)
class SubmissionImages:
    prepare: PrepareImage
    provider_copy: Callable[[bytes, str], tuple[bytes, str, str]]
    asset_bytes: Callable[[Record, str], bytes]
    annotate: Callable[[bytes, list[Record]], bytes]
    data_url: Callable[[bytes, str], str]


@dataclass(frozen=True)
class SubmissionModels:
    settings: Callable[[str], Record]
    call: Callable[[str, Record], Record]
    prompt: Callable[[], str]
    normalize: Callable[[Any, str], Record]
    validate: Callable[[Record], Record]


@dataclass(frozen=True)
class SubmissionDiagnostics:
    image: ImageDiagnostic
    event: DiagnosticEvent
    provider: Callable[[Record, Record], Record]
    value: Callable[[Any], Any]
    write: Callable[[Record], None]
