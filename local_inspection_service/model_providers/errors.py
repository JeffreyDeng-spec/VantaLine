"""Shared provider exception types and usage metadata."""
from typing import Any

class AiProviderError(RuntimeError):
    def __init__(
        self,
        message: str = "",
        *,
        usage_metadata: dict[str, Any] | None = None,
        failed_usage_metadata: list[dict[str, Any]] | None = None,
        attempts: int | None = None,
        retry_count: int | None = None,
        previous_errors: list[str] | None = None,
        http_status: int | None = None,
        fallback_model: str = "",
        fallback_reason: str = "",
    ):
        super().__init__(message)
        self.usage_metadata = usage_metadata or {}
        self.failed_usage_metadata = failed_usage_metadata or []
        self.attempts = attempts
        self.retry_count = retry_count
        self.previous_errors = previous_errors or []
        self.http_status = http_status
        self.fallback_model = fallback_model
        self.fallback_reason = fallback_reason

class AiProviderNonRetryableError(AiProviderError):
    pass

class AiProviderConfigError(AiProviderNonRetryableError):
    pass

class AiProviderAuthError(AiProviderNonRetryableError):
    pass

class AiProviderTimeout(AiProviderError):
    pass

class AiProviderOverloaded(AiProviderError):
    pass
