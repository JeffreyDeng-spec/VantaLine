"""Narrow provider defaults, validation and public URL capabilities."""
from collections.abc import Callable, Mapping, Set
from dataclasses import dataclass
from typing import Any
from urllib.parse import SplitResult
from fastapi import HTTPException
@dataclass(frozen=True)
class JsonDefaults:
    models: Callable[[], Mapping[str, str]]
    model: Callable[[], str]
    base_urls: Callable[[], Mapping[str, str]]
    provider: Callable[[], str]
    labels: Callable[[], Mapping[str, str]]
@dataclass(frozen=True)
class ImageDefaults:
    models: Callable[[], Mapping[str, str]]
    base_urls: Callable[[], Mapping[str, str]]
    provider: Callable[[], str]
    key_envs: Callable[[], Mapping[str, str]]
    key_env: Callable[[], str]
    provider_keys: Callable[[], Mapping[str, str]]
    labels: Callable[[], Mapping[str, str]]
@dataclass(frozen=True)
class ValidationCapabilities:
    json_providers: Callable[[], Set[str]]
    image_providers: Callable[[], Set[str]]
    http_error: Callable[[], type[HTTPException]]
    fullmatch: Callable[[], Callable[[str, str], Any]]
    split_url: Callable[[], Callable[[str], SplitResult]]
@dataclass(frozen=True)
class PublicUrlCapabilities:
    split_url: Callable[[], Callable[[str], SplitResult]]
    join_url: Callable[[], Callable[[tuple[str, str, str, str, str]], str]]
    text: Callable[[], Callable[[Any, int], str]]
