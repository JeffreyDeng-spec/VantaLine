"""Typed dependencies for provider selection, retry policy and orchestration."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol
from .errors import AiProviderError
from .gemini_transport import GeminiAiProvider
from .openai_transport import OpenAICompatibleAiProvider
from .agnes_transport import AgnesImageProvider
from .qwen_image_transport import QwenImageProvider

Record = dict[str, Any]
JsonProvider = OpenAICompatibleAiProvider | GeminiAiProvider
ImageProvider = GeminiAiProvider | AgnesImageProvider | QwenImageProvider

class AnnotateFailure(Protocol):
    def __call__(self, exc: AiProviderError, *, attempt: int, errors: list[str],
                 failed_usage_metadata: list[Record], usage_metadata: Record | None = None,
                 fallback_model: str = '', fallback_reason: str = '') -> AiProviderError: ...

@dataclass(frozen=True)
class ProviderFactories:
    gemini: Callable[[], type[GeminiAiProvider]]
    openai: Callable[[], type[OpenAICompatibleAiProvider]]
    agnes: Callable[[], type[AgnesImageProvider]]
    qwen_image: Callable[[], type[QwenImageProvider]]
    config_error: Callable[[], type[AiProviderError]]
    settings: Callable[[], Callable[[], Record]]
    json_factory: Callable[[], Callable[[Record], JsonProvider]]

@dataclass(frozen=True)
class ProviderKeys:
    identify: Callable[[], Callable[[Any, str], str]]
    text: Callable[[], Callable[[Any, int], str]]
    candidates: Callable[[], Callable[[Record], list[dict[str, str]]]]

@dataclass(frozen=True)
class RetryErrors:
    error: Callable[[], type[AiProviderError]]
    non_retryable: Callable[[], type[AiProviderError]]
    overloaded: Callable[[], type[AiProviderError]]
    timeout: Callable[[], type[AiProviderError]]

@dataclass(frozen=True)
class ImageDelay:
    attempts: Callable[[], int]
    base: Callable[[], float]
    cap: Callable[[], float]
    jitter: Callable[[], Callable[[float, float], float]]

@dataclass(frozen=True)
class FailureEvidence:
    error: Callable[[], type[AiProviderError]]
    gemini: Callable[[], type[GeminiAiProvider]]

@dataclass(frozen=True)
class JsonProviderSelection:
    matches: Callable[[], Callable[[Record], bool]]
    current: Callable[[], Callable[[], JsonProvider]]
    factory: Callable[[], Callable[[Record], JsonProvider]]
    gemini: Callable[[], type[GeminiAiProvider]]
    rotate: Callable[[], Callable[[Record, set[str]], Record | None]]

@dataclass(frozen=True)
class JsonRetryEvidence:
    require_object: Callable[[], Callable[[Any], Record]]
    failure_usage: Callable[[], Callable[[JsonProvider | None, AiProviderError], Record]]
    retryable: Callable[[], Callable[[AiProviderError], bool]]
    needs_repair: Callable[[], Callable[[AiProviderError], bool]]
    annotate: Callable[[], AnnotateFailure]
    text: Callable[[], Callable[[Any, int], str]]

@dataclass(frozen=True)
class JsonRetryTiming:
    attempts: Callable[[], int]
    backoff: Callable[[], float]
    jitter: Callable[[], Callable[[float, float], float]]
    sleep: Callable[[], Callable[[float], None]]

@dataclass(frozen=True)
class ImageRetryCalls:
    factory: Callable[[], Callable[[Record], ImageProvider]]
    gate: Callable[[], AbstractContextManager[Any]]
    retryable: Callable[[], Callable[[AiProviderError], bool]]
    text: Callable[[], Callable[[Any, int], str]]
    delay: Callable[[], Callable[[int, AiProviderError | None], float]]

@dataclass(frozen=True)
class ImageRetryTiming:
    attempts: Callable[[], int]
    now: Callable[[], Callable[[], float]]
    sleep: Callable[[], Callable[[float], None]]
