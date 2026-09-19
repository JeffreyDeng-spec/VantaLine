"""HTTP error classification with explicit text and exception dependencies."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
import urllib.error
from .errors import AiProviderError

class ProviderErrorFactory(Protocol):
    def __call__(self, message: str, *, http_status: int) -> AiProviderError: ...

@dataclass(frozen=True)
class ProviderErrorTypes:
    error: Callable[[], ProviderErrorFactory]
    auth: Callable[[], ProviderErrorFactory]
    overloaded: Callable[[], ProviderErrorFactory]
    config: Callable[[], ProviderErrorFactory]
    non_retryable: Callable[[], ProviderErrorFactory]

class ProviderHttpErrors:
    def __init__(self, text: Callable[[], Callable[[Any, int], str]], errors: ProviderErrorTypes):
        self.text, self.errors = text, errors

    def provider_http_error(self, message_prefix: str, exc: urllib.error.HTTPError) -> AiProviderError:
        detail = exc.read().decode('utf-8', errors='replace')[:240]
        error_text = f'{message_prefix}: HTTP {exc.code} {self.text()(detail, 180)}'
        if exc.code in {401, 403}:
            return self.errors.auth()(error_text, http_status=exc.code)
        if exc.code in {429, 503}:
            return self.errors.overloaded()(f'AI provider overloaded: HTTP {exc.code} {self.text()(detail, 180)}', http_status=exc.code)
        if exc.code in {400, 404}:
            return self.errors.config()(error_text, http_status=exc.code)
        if exc.code in {408, 500, 502, 504}:
            return self.errors.error()(error_text, http_status=exc.code)
        return self.errors.non_retryable()(error_text, http_status=exc.code)
