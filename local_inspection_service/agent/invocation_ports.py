"""Narrow capabilities for Agent protocol, invocation and recommendation services."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Match, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request
from fastapi import HTTPException

Record = dict[str, Any]

class ResponseBody(Protocol):
    def read(self) -> bytes: ...

class RequestFactory(Protocol):
    def __call__(self, url: str, /, data: bytes | None = None, *, headers: dict[str, str], method: str) -> Request: ...

class OpenRequest(Protocol):
    def __call__(self, request: Request, *, timeout: float) -> AbstractContextManager[ResponseBody]: ...

class EncodeJson(Protocol):
    def __call__(self, value: Any, /, *, ensure_ascii: bool = True) -> str: ...

class LegacyChat(Protocol):
    def __call__(self, messages: list[dict[str, str]], config: Record | None = None, *, require_connected: bool = True) -> str: ...

class GenerateJson(Protocol):
    def __call__(self, settings: Record, system_prompt: str, user_content: list[Record], *, max_tokens: int, max_attempts: int) -> tuple[Record, int, Record]: ...

class ModelOptions(Protocol):
    def __call__(self, items: Any, *, prepend: list[dict[str, str]] | None = None) -> list[dict[str, str]]: ...

class SearchResponse(Protocol):
    def __call__(self, pattern: str, text: str, /, *, flags: int) -> Match[str] | None: ...

@dataclass(frozen=True)
class AgentProtocolRuntime:
    base64_encode: Callable[[], Callable[[bytes], bytes]]
    cursor_base_url: Callable[[], str]

@dataclass(frozen=True)
class AgentInvocationSettings:
    load: Callable[[], Callable[[], Record]]
    normalize_provider: Callable[[], Callable[[str | None, str], str]]
    openai_provider: Callable[[], str]
    cursor_provider: Callable[[], str]
    cursor_message: Callable[[], str]
    is_cursor_url: Callable[[], Callable[[str], bool]]
    required: Callable[[], Callable[[Record], bool]]
    connected: Callable[[], Callable[[Record], bool]]
    recommended: Callable[[], Callable[[Record], bool]]

@dataclass(frozen=True)
class AgentHttpIO:
    request: Callable[[], RequestFactory]
    open: Callable[[], OpenRequest]
    http_error: Callable[[], type[HTTPError]]
    url_error: Callable[[], type[URLError]]
    error_message: Callable[[], Callable[[str, HTTPError], str]]
    text: Callable[[], Callable[[Any, int], str]]

@dataclass(frozen=True)
class AgentInvocationCodec:
    loads: Callable[[], Callable[[str], Any]]
    dumps: Callable[[], EncodeJson]

@dataclass(frozen=True)
class AgentChatCalls:
    chat_url: Callable[[], Callable[[str], str]]
    legacy_chat: Callable[[], LegacyChat]
    generate: Callable[[], GenerateJson]

@dataclass(frozen=True)
class AgentModelCalls:
    models_url: Callable[[], Callable[[str], str]]
    auth_headers: Callable[[], Callable[[str], dict[str, str]]]
    cursor_url: Callable[[], Callable[[str, str], str]]
    options: Callable[[], ModelOptions]
    available: Callable[[], Callable[[str, list[Record]], bool]]
    fetch: Callable[[], Callable[[Record], list[dict[str, str]]]]
    cursor_test: Callable[[], Callable[[Record], Record]]
    openai_test: Callable[[], Callable[[Record], Record]]
    legacy_chat: Callable[[], LegacyChat]

@dataclass(frozen=True)
class AgentResponseParsing:
    substitute: Callable[[], Callable[[str, str, str], str]]
    search: Callable[[], SearchResponse]
    dotall: Callable[[], int]

@dataclass(frozen=True)
class AgentRecommendationInputs:
    config: Callable[[], Callable[[], Record]]
    selected: Callable[[], Callable[[Record, list[str]], list[Record]]]
    material: Callable[[], Callable[[Record], str]]
    background: Callable[[], Callable[[str | None, Record | None], str]]
    current_user: Callable[[], Callable[[], Record | None]]
    selection_error: Callable[[], type[HTTPException]]

@dataclass(frozen=True)
class AgentRecommendationCalls:
    rule: Callable[[], Callable[[str, list[Record], int | None], Record]]
    chat: Callable[[], Callable[[list[dict[str, str]], Record | None], str]]
    parse: Callable[[], Callable[[str], Record]]
    clamp: Callable[[], Callable[[str, Record, Record], Record]]
