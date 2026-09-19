"""Narrow key identity and local secret-file capabilities."""
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Match, Protocol
from .key_registry_ports import DefaultEnvironmentName


class Digest(Protocol):
    def hexdigest(self) -> str: ...


@dataclass(frozen=True)
class KeyIdentityRuntime:
    sha256: Callable[[], Callable[[bytes], Digest]]
    time_ns: Callable[[], Callable[[], int]]
    substitute: Callable[[], Callable[[str, str, str], str]]
    fullmatch: Callable[[], Callable[[str, str], Match[str] | None]]
    key_id: Callable[[], Callable[[str], str]]


@dataclass(frozen=True)
class SecretPaths:
    directory: Callable[[], Path]
    file: Callable[[], Path]


@dataclass(frozen=True)
class SecretCodec:
    loads: Callable[[], Callable[[str], Any]]
    dumps: Callable[[], Callable[[Any], str]]
    decode_error: Callable[[], type[ValueError]]


@dataclass(frozen=True)
class SecretFileOperations:
    chmod: Callable[[], Callable[[Path, int], None]]
    replace: Callable[[], Callable[[Path, Path], None]]


@dataclass(frozen=True)
class SecretEnvironment:
    values: Callable[[], MutableMapping[str, str]]


@dataclass(frozen=True)
class SecretPolicy:
    fullmatch: Callable[[], Callable[[str, str], Match[str] | None]]
    validate: Callable[[], Callable[[Any], str]]
    default_environment: Callable[[], DefaultEnvironmentName]
    identity: Callable[[], Callable[[str, str], str]]
    text: Callable[[], Callable[[Any, int], str]]


@dataclass(frozen=True)
class SecretStoreAccess:
    load: Callable[[], Callable[[], dict[str, str]]]
    save: Callable[[], Callable[[dict[str, str]], None]]
    set: Callable[[], Callable[[str, str], None]]
