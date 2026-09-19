"""Narrow Gemini request, payload and error capabilities."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import Request
from .errors import AiProviderError

class ResponseReader(Protocol):
    def read(self) -> bytes: ...

class GeminiRequest(Protocol):
    def __call__(self, request: Request, settings: dict[str, Any], *, timeout: float) -> AbstractContextManager[ResponseReader]: ...

class Quote(Protocol):
    def __call__(self, text: str, *, safe: str) -> str: ...

@dataclass(frozen=True)
class GeminiTransportIO:
    open: Callable[[], GeminiRequest]
    parse: Callable[[], Callable[[str], dict[str, Any]]]
    text: Callable[[], Callable[[Any, int], str]]
    data_url: Callable[[], Callable[[str], tuple[str, str]]]
    decode: Callable[[], Callable[[Any], bytes | None]]
    mask_url: Callable[[], Callable[[Any], str]]
    quote: Callable[[], Quote]
    http_error: Callable[[], Callable[[str, HTTPError], AiProviderError]]

@dataclass(frozen=True)
class GeminiTransportErrors:
    config: Callable[[], type[AiProviderError]]
    timeout: Callable[[], type[AiProviderError]]
    error: Callable[[], type[AiProviderError]]
    auth: Callable[[], type[AiProviderError]]
    overloaded: Callable[[], type[AiProviderError]]
