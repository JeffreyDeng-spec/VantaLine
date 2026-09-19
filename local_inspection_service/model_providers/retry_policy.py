"""Provider business logic with explicit dependencies and original policy."""
from typing import Any
from .errors import AiProviderError
from .gemini_transport import GeminiAiProvider
from .openai_transport import OpenAICompatibleAiProvider
from .agnes_transport import AgnesImageProvider
from .qwen_image_transport import QwenImageProvider
from .orchestration_ports import RetryErrors, ImageDelay, FailureEvidence


class ProviderRetryPolicy:
    def __init__(self, errors: RetryErrors, delay: ImageDelay):
        self.errors, self.delay = errors, delay

    def provider_error_is_retryable(self, exc: AiProviderError) -> bool:
        if isinstance(exc, self.errors.non_retryable()):
            return False
        status = getattr(exc, "http_status", None)
        if isinstance(exc, self.errors.overloaded()):
            return status != 429
        if isinstance(exc, self.errors.timeout()):
            return True
        text = str(exc).lower()
        non_retryable_markers = (
            "not configured",
            "missing ai provider api key",
            "missing api key",
            "unsupported ai provider",
            "invalid provider",
            "http 400",
            "http 401",
            "http 403",
            "http 404",
            "http 429",
        )
        return not any(marker in text for marker in non_retryable_markers)

    def image_provider_error_is_retryable(self, exc: AiProviderError) -> bool:
        if isinstance(exc, self.errors.non_retryable()):
            return False
        if isinstance(exc, (self.errors.overloaded(), self.errors.timeout())):
            return True
        status = getattr(exc, "http_status", None)
        if status in {408, 429, 500, 502, 503, 504}:
            return True
        text = str(exc).lower()
        retryable_markers = ("timed out", "timeout", "temporarily", "overloaded", "connection reset", "remote end closed")
        non_retryable_markers = ("not configured", "missing api key", "http 400", "http 401", "http 403", "http 404")
        return any(marker in text for marker in retryable_markers) and not any(marker in text for marker in non_retryable_markers)

    def auto_optimize_retry_delay_seconds(self, attempt: int, exc: AiProviderError | None = None) -> float:
        if self.delay.attempts() <= 1:
            return 0.0
        if (
            isinstance(exc, self.errors.overloaded())
            and (getattr(exc, "http_status", None) == 503 or "HTTP 503" in str(exc))
        ):
            return 3.0
        base = self.delay.base()
        if base <= 0:
            return 0.0
        delay = min(self.delay.cap(), base * (3 ** max(0, attempt - 1)))
        jitter = self.delay.jitter()(0, min(1.0, delay * 0.2))
        return round(delay + jitter, 3)


class ProviderFailureEvidence:
    def __init__(self, evidence: FailureEvidence):
        self.evidence = evidence

    def require_ai_json_object(self, parsed: Any) -> dict[str, Any]:
        if not isinstance(parsed, dict):
            raise self.evidence.error()("AI provider returned non-object JSON")
        return parsed

    def provider_error_needs_repair_prompt(self, exc: AiProviderError) -> bool:
        text = str(exc).lower()
        return "json" in text or "response shape" in text or "non-object" in text

    def provider_failure_usage_metadata(self,
        provider: OpenAICompatibleAiProvider | GeminiAiProvider | None,
        exc: AiProviderError,
    ) -> dict[str, Any]:
        if isinstance(provider, self.evidence.gemini()) and provider.last_usage_metadata:
            return dict(provider.last_usage_metadata)
        return dict(getattr(exc, "usage_metadata", {}) or {})

    def annotate_provider_failure(self,
        exc: AiProviderError,
        *,
        attempt: int,
        errors: list[str],
        failed_usage_metadata: list[dict[str, Any]],
        usage_metadata: dict[str, Any] | None = None,
        fallback_model: str = "",
        fallback_reason: str = "",
    ) -> AiProviderError:
        if usage_metadata and not exc.usage_metadata:
            exc.usage_metadata = usage_metadata
        if failed_usage_metadata:
            exc.failed_usage_metadata = failed_usage_metadata
        exc.attempts = attempt
        exc.retry_count = max(0, attempt - 1)
        exc.previous_errors = errors[-2:]
        if fallback_model:
            exc.fallback_model = fallback_model
        if fallback_reason:
            exc.fallback_reason = fallback_reason
        return exc
