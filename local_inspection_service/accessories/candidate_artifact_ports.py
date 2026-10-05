"""File ownership and record lookup dependencies for candidate artifact cleanup."""
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

Record = dict[str, Any]

class CandidateFiles(Protocol):
    def exists(self, path: Path) -> bool: ...
    def is_file(self, path: Path) -> bool: ...
    def glob(self, path: Path, pattern: str, *, recursive: bool = False) -> Iterable[Path]: ...
    def rmtree(self, path: Path) -> None: ...

@dataclass(frozen=True)
class CandidateArtifactFiles:
    _business_files: Callable[[], CandidateFiles]
    UPLOAD_DIR: Callable[[], Path]
    output_write_dir: Callable[[], Callable[[str], Path]]
    IMAGE_REFERENCE_SUFFIXES: Callable[[], set[str] | frozenset[str]]

@dataclass(frozen=True)
class CandidateArtifactRecords:
    safe_record_id: Callable[[], Callable[[str], str]]
    load_config: Callable[[], Callable[[], Record]]
    list_accessory_candidate_records: Callable[[], Callable[..., Iterable[tuple[Path, Record]]]]
