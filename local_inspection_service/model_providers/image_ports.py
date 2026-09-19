"""Explicit capabilities shared by the Agnes and Qwen image transports."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.request import Request
from .errors import AiProviderError

class ResponseReader(Protocol):
    def read(self) -> bytes: ...

class ImageRequest(Protocol):
    def __call__(self, request: Request, settings: dict[str, Any], *, timeout: float) -> AbstractContextManager[ResponseReader]: ...

class DownloadResponse(Protocol):
    content: bytes
    def raise_for_status(self) -> None: ...

class ImageDownload(Protocol):
    def __call__(self, url: str, *, timeout: float) -> DownloadResponse: ...

@dataclass(frozen=True)
class ImageTransportIO:
    open: Callable[[], ImageRequest]
    text: Callable[[], Callable[[Any, int], str]]
    decode: Callable[[], Callable[[Any], bytes | None]]
    mask_url: Callable[[], Callable[[Any], str]]
    download: Callable[[], ImageDownload]

@dataclass(frozen=True)
class ImageTransportErrors:
    config: Callable[[], type[AiProviderError]]
    timeout: Callable[[], type[AiProviderError]]
    error: Callable[[], type[AiProviderError]]
    auth: Callable[[], type[AiProviderError]]
    overloaded: Callable[[], type[AiProviderError]]
    download_error: Callable[[], type[Exception]]
