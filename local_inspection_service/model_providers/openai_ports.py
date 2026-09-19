"""Narrow capabilities for the OpenAI-compatible transport."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import Request
from .errors import AiProviderError

class ResponseReader(Protocol):
    def read(self) -> bytes: ...

class OpenAIRequest(Protocol):
    def __call__(self, request: Request, settings: dict[str, Any], *, timeout: float) -> AbstractContextManager[ResponseReader]: ...

@dataclass(frozen=True)
class OpenAITransportIO:
    open: Callable[[], OpenAIRequest]
    parse: Callable[[], Callable[[str], dict[str, Any]]]
    text: Callable[[], Callable[[Any, int], str]]
    digest: Callable[[], Callable[[bytes], str]]
    http_error: Callable[[], Callable[[str, HTTPError], AiProviderError]]

@dataclass(frozen=True)
class OpenAITransportErrors:
    config: Callable[[], type[AiProviderError]]
    timeout: Callable[[], type[AiProviderError]]
    error: Callable[[], type[AiProviderError]]
