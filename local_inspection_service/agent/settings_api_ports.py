"""Narrow capabilities for the existing Agent settings HTTP handlers."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from fastapi import HTTPException


class HttpErrorFactory(Protocol):
    def __call__(self, status_code: int, detail: Any = None) -> HTTPException: ...


class PublicSettings(Protocol):
    def __call__(self, config: dict[str, Any] | None = None) -> dict[str, Any]: ...


class SecretEnvironmentName(Protocol):
    def __call__(self, prefix: str, secret: str = '', *, provider: str = '') -> str: ...


@dataclass(frozen=True)
class AgentSettingsHttpAccess:
    admin: Callable[[], Callable[[], dict[str, Any]]]
    http_error: Callable[[], HttpErrorFactory]


@dataclass(frozen=True)
class AgentSettingsProjectionCall:
    public: Callable[[], PublicSettings]


@dataclass(frozen=True)
class AgentRecommendationCall:
    recommend: Callable[[], Callable[[str, list[str], int | None], dict[str, Any]]]


@dataclass(frozen=True)
class AgentLegacySettingsPolicy:
    load: Callable[[], Callable[[], dict[str, Any]]]
    normalize: Callable[[], Callable[[dict[str, Any]], dict[str, Any]]]
    credentials: Callable[[], Callable[[dict[str, Any]], bool]]
    provider: Callable[[], Callable[[str | None, str], str]]
    supported: Callable[[], set[str]]
    cursor: Callable[[], str]
    label: Callable[[], Callable[[str], str]]
    options: Callable[[], Callable[[Any], list[dict[str, str]]]]


@dataclass(frozen=True)
class AgentLegacyKeyPolicy:
    validate: Callable[[], Callable[[Any], str]]
    name: Callable[[], SecretEnvironmentName]
    normalize: Callable[[], Callable[[dict[str, Any]], list[dict[str, str]]]]
    identity: Callable[[], Callable[[str, str], str]]
    for_provider: Callable[[], Callable[[list[dict[str, str]], str], list[dict[str, str]]]]


@dataclass(frozen=True)
class AgentLegacySettingsEffects:
    save: Callable[[], Callable[[dict[str, Any]], None]]
    secret: Callable[[], Callable[[str, str], None]]
    test: Callable[[], Callable[[dict[str, Any]], dict[str, Any]]]
    now: Callable[[], Callable[[], float]]
