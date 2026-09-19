"""Narrow capabilities for provider key normalization and public projections."""
from collections.abc import Callable, Set
from dataclasses import dataclass
from typing import Any, Protocol


class DefaultEnvironmentName(Protocol):
    def __call__(self, prefix: str, secret: str = "", *, provider: str = "") -> str: ...


@dataclass(frozen=True)
class KeyMaterial:
    environment: Callable[[], Callable[[str], str]]
    identity: Callable[[], Callable[[str, str], str]]
    default_environment: Callable[[], DefaultEnvironmentName]


@dataclass(frozen=True)
class KeyPresentation:
    text: Callable[[], Callable[[Any, int], str]]
    mask: Callable[[], Callable[[str], str]]
    json_label: Callable[[], Callable[[str], str]]
    image_label: Callable[[], Callable[[str], str]]
    agent_label: Callable[[], Callable[[str], str]]


@dataclass(frozen=True)
class JsonKeyPolicy:
    default_provider: Callable[[], str]
    supported: Callable[[], Set[str]]


@dataclass(frozen=True)
class ImageKeyPolicy:
    default_provider: Callable[[], str]
    supported: Callable[[], Set[str]]
    validate: Callable[[], Callable[[Any], str]]


@dataclass(frozen=True)
class AgentKeyPolicy:
    supported: Callable[[], Set[str]]
    normalize: Callable[[], Callable[[Any, str], str]]
