"""Storage capabilities consumed by background-library services."""
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, BinaryIO, Protocol


class ExistingBackgroundFiles(Protocol):
    def exists(self, path: Path) -> bool: ...


class BackgroundDirectoryFiles(ExistingBackgroundFiles, Protocol):
    def is_dir(self, path: Path) -> bool: ...
    def iterdir(self, path: Path) -> Iterable[Path]: ...


class BackgroundImageListingFiles(BackgroundDirectoryFiles, Protocol):
    def is_file(self, path: Path) -> bool: ...


class BackgroundManifestFiles(ExistingBackgroundFiles, Protocol):
    def read_json(self, path: Path) -> Any: ...
    def write_json(self, path: Path, value: Any, *, indent: int) -> Any: ...


class BackgroundSeedFiles(BackgroundDirectoryFiles, Protocol):
    def copy2(self, source: Path, destination: Path, *, local_copy: Callable[..., Any]) -> Any: ...


class BackgroundLibraryFiles(ExistingBackgroundFiles, Protocol):
    def iterdir(self, path: Path) -> Iterable[Path]: ...
    def is_file(self, path: Path) -> bool: ...
    def read_text(self, path: Path, *, encoding: str) -> str: ...


class BackgroundStreamFiles(Protocol):
    def copy_stream(self, destination: Path, source: BinaryIO, local_copy: Callable[..., Any]) -> Any: ...


class BackgroundImageReader(Protocol):
    def imread(self, filename: str, flags: int) -> Any: ...


class BackgroundImageIO(BackgroundImageReader, Protocol):
    def imwrite(self, filename: str, image: Any) -> bool: ...
