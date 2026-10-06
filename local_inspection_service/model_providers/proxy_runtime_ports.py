"""Proxy settings, validation and transport capabilities."""
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.request import Request

class Environment(Protocol):
    environ: Mapping[str, str]
class SocketTransport(Protocol):
    def create_connection(self, address: tuple[str, int], *, timeout: float) -> AbstractContextManager[Any]: ...
class UrlOpener(Protocol):
    def open(self, request: Request, *, timeout: float) -> Any: ...
class RequestTransport(Protocol):
    def urlopen(self, request: Request, *, timeout: float) -> Any: ...
    def build_opener(self, *handlers: Any) -> UrlOpener: ...
    def ProxyHandler(self, proxies: Mapping[str, str]) -> Any: ...
class UrlTransport(Protocol):
    request: RequestTransport
@dataclass(frozen=True)
class ProxySettings:
    AI_PROXY_ENV_NAMES: Callable[[], Sequence[str]]
    AI_LOCAL_PROXY_URL: Callable[[], str]
    AI_AUTO_LOCAL_PROXY_ENV: Callable[[], str]
@dataclass(frozen=True)
class ProxyCalls:
    validate_ai_proxy_url: Callable[[], Callable[[str], str]]
    ai_proxy_url_from_environment: Callable[[], Callable[[], tuple[str, str]]]
    env_flag_enabled: Callable[[], Callable[[str, bool], bool]]
    local_proxy_available: Callable[[], Callable[[str], bool]]
@dataclass(frozen=True)
class ProxyTransports:
    os: Callable[[], Environment]
    socket: Callable[[], SocketTransport]
    urllib: Callable[[], UrlTransport]
