"""Narrow Agent settings policy, presentation and persistence capabilities."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import SplitResult


class JsonEncoder(Protocol):
    def __call__(self, value: Any, *, indent: int) -> str: ...


@dataclass(frozen=True)
class AgentSettingsDefaults:
    cursor: Callable[[], str]
    openai: Callable[[], str]
    config: Callable[[], dict[str, Any]]
    cursor_url: Callable[[], str]
    statuses: Callable[[], set[str]]


@dataclass(frozen=True)
class AgentProviderPolicy:
    split_url: Callable[[], Callable[[str], SplitResult]]
    host: Callable[[], Callable[[str], str]]
    is_cursor: Callable[[], Callable[[str], bool]]
    detect: Callable[[], Callable[[str], str]]
    normalize: Callable[[], Callable[[str | None, str], str]]
    options: Callable[[], Callable[[Any], list[dict[str, str]]]]


@dataclass(frozen=True)
class AgentSettingsKeys:
    validate_environment: Callable[[], Callable[[Any], str]]
    normalize: Callable[[], Callable[[dict[str, Any]], list[dict[str, str]]]]
    for_provider: Callable[[], Callable[[list[dict[str, str]], str], list[dict[str, str]]]]
    environment_value: Callable[[], Callable[[str], str]]


@dataclass(frozen=True)
class AgentSettingsAccess:
    required: Callable[[], Callable[[dict[str, Any]], bool]]
    credentials: Callable[[], Callable[[dict[str, Any]], bool]]
    connected: Callable[[], Callable[[dict[str, Any]], bool]]
    recommendation: Callable[[], Callable[[dict[str, Any]], bool]]
    load: Callable[[], Callable[[], dict[str, Any]]]


@dataclass(frozen=True)
class AgentSettingsAuthorization:
    is_admin: Callable[[], Callable[[dict[str, Any] | None], bool]]
    current_user: Callable[[], Callable[[], dict[str, Any] | None]]


@dataclass(frozen=True)
class AgentSettingsPresentation:
    provider_label: Callable[[], Callable[[str], str]]
    public_keys: Callable[[], Callable[[list[dict[str, str]]], list[dict[str, Any]]]]
    mask: Callable[[], Callable[[str], str]]


@dataclass(frozen=True)
class AgentSettingsPaths:
    file: Callable[[], Path]
    directory: Callable[[], Path]


@dataclass(frozen=True)
class AgentSettingsCodec:
    loads: Callable[[], Callable[[str], Any]]
    dumps: Callable[[], JsonEncoder]
    decode_error: Callable[[], type[ValueError]]


@dataclass(frozen=True)
class AgentSettingsFiles:
    replace: Callable[[], Callable[[Path, Path], None]]
    chmod: Callable[[], Callable[[Path, int], None]]


@dataclass(frozen=True)
class AgentSettingsPersistence:
    normalize: Callable[[], Callable[[dict[str, Any]], dict[str, Any]]]
    keys: Callable[[], Callable[[dict[str, Any]], list[dict[str, str]]]]
    persist: Callable[[], Callable[[list[dict[str, str]], str], list[dict[str, str]]]]
