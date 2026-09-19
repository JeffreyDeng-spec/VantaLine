"""Explicit capabilities for legacy model-profile migration settings."""
from collections.abc import Callable, Mapping, Set
from dataclasses import dataclass
from typing import Any
Record = dict[str, Any]
@dataclass(frozen=True)
class LegacySettingsIO:
    load: Callable[[], Callable[[], Record]]
    environment: Callable[[], Mapping[str, str]]
    proxy: Callable[[], Callable[[Record, str], tuple[str, str, bool]]]
    validate_base: Callable[[], Callable[[str], Any]]
    http_error: Callable[[], type[Exception]]
@dataclass(frozen=True)
class LegacyPresentation:
    public_keys: Callable[[], Callable[[list[Record]], list[Record]]]
    mask_secret: Callable[[], Callable[[str], str]]
    public_base: Callable[[], Callable[[str], str]]
    mask_url: Callable[[], Callable[[str], str]]
@dataclass(frozen=True)
class LegacyJsonPolicy:
    provider: Callable[[], str]
    model: Callable[[], str]
    timeout: Callable[[], float]
    models: Callable[[], Any]
    supported: Callable[[], Set[str]]
    proxy_flag: Callable[[], str]
@dataclass(frozen=True)
class LegacyJsonCallbacks:
    default_base: Callable[[], Callable[[str], str]]
    validate_timeout: Callable[[], Callable[[Any], float]]
    normalize_keys: Callable[[], Callable[[Record, str], list[Record]]]
    select_keys: Callable[[], Callable[[list[Record], str], list[Record]]]
    key_id: Callable[[], Callable[[str, str], str]]
    text: Callable[[], Callable[[Any, int], str]]
    label: Callable[[], Callable[[str], str]]
    flag: Callable[[], Callable[[str, bool], bool]]
@dataclass(frozen=True)
class LegacyImagePolicy:
    provider: Callable[[], str]
    timeout: Callable[[], float]
    models: Callable[[], Any]
    supported: Callable[[], Set[str]]
@dataclass(frozen=True)
class LegacyImageEnvironment:
    provider: Callable[[], str]
    model: Callable[[], str]
    base: Callable[[], str]
    timeout: Callable[[], str]
    named_key: Callable[[], str]
    direct_key: Callable[[], str]
    gemini_model: Callable[[], str]
    gemini_timeout: Callable[[], str]
@dataclass(frozen=True)
class LegacyImageCallbacks:
    default_model: Callable[[], Callable[[str], str]]
    default_base: Callable[[], Callable[[str], str]]
    default_key_env: Callable[[], Callable[[str], str]]
    validate_timeout: Callable[[], Callable[[Any], float]]
    normalize_keys: Callable[[], Callable[[Record, str], list[Record]]]
    select_keys: Callable[[], Callable[[list[Record], str], list[Record]]]
    label: Callable[[], Callable[[str], str]]
    provider_key: Callable[[], Callable[[str], str]]
