"""Provider business logic with explicit dependencies and original policy."""
from typing import Any
from .errors import AiProviderError
from .gemini_transport import GeminiAiProvider
from .openai_transport import OpenAICompatibleAiProvider
from .agnes_transport import AgnesImageProvider
from .qwen_image_transport import QwenImageProvider
from .orchestration_ports import JsonProviderSelection, JsonRetryEvidence, RetryErrors, JsonRetryTiming, ImageRetryCalls, ImageRetryTiming


class JsonRetryFlow:
    def __init__(self, providers: JsonProviderSelection, evidence: JsonRetryEvidence, errors: RetryErrors, timing: JsonRetryTiming):
        self.providers, self.evidence, self.errors, self.timing = providers, evidence, errors, timing

    def generate_provider_json_with_fallback(self,
        settings: dict[str, Any],
        system_prompt: str,
        user_content: list[dict[str, Any]],
        *,
        max_tokens: int,
        cached_content: str = "",
        max_attempts: int | None = None,
        overloaded_retry_delay_seconds: float | None = None,
        allow_overloaded_model_fallback: bool = True,
    ) -> tuple[dict[str, Any], int, dict[str, Any]]:
        attempts = self.timing.attempts()
        if max_attempts is not None:
            attempts = max(1, min(self.timing.attempts(), int(max_attempts)))
        total_latency_ms = 0
        errors: list[str] = []
        failed_usage_metadata: list[dict[str, Any]] = []
        attempt_settings = dict(settings)
        used_key_ids: set[str] = set()
        repair_next_attempt = False
        fallback_model = ""
        fallback_reason = ""
        fallback_key_id = ""
        fallback_key_label = ""
        retry_delay_seconds: float | None = None
        for attempt in range(1, attempts + 1):
            retry_delay_seconds = None
            current_key_id = str(attempt_settings.get("active_key_id") or "")
            if current_key_id:
                used_key_ids.add(current_key_id)
            attempt_user_content = user_content
            if repair_next_attempt:
                attempt_user_content = [
                    *user_content,
                    {
                        "type": "text",
                        "text": (
                            "RETRY_REPAIR: the previous provider response was not a valid JSON object. "
                            "Return only the compact JSON object matching the schema; no markdown, prose, or code fences."
                        ),
                    },
                ]
            provider: OpenAICompatibleAiProvider | GeminiAiProvider | None = None
            try:
                provider = self.providers.current()() if self.providers.matches()(attempt_settings) else self.providers.factory()(attempt_settings)
                if isinstance(provider, self.providers.gemini()):
                    parsed, latency_ms = provider.generate_json(
                        system_prompt,
                        attempt_user_content,
                        max_tokens=max_tokens,
                        cached_content=cached_content,
                    )
                    usage_metadata = dict(provider.last_usage_metadata)
                else:
                    parsed, latency_ms = provider.generate_json(system_prompt, attempt_user_content, max_tokens=max_tokens)
                    usage_metadata = dict(getattr(provider, "last_usage_metadata", {}) or {})
                parsed = self.evidence.require_object()(parsed)
                total_latency_ms += latency_ms
                retry_meta = {"attempts": attempt, "retry_count": attempt - 1}
                if current_key_id:
                    retry_meta["provider_key_id"] = current_key_id
                if fallback_model:
                    retry_meta["fallback_model"] = fallback_model
                if fallback_reason:
                    retry_meta["fallback_reason"] = fallback_reason
                if fallback_key_id:
                    retry_meta["fallback_key_id"] = fallback_key_id
                if fallback_key_label:
                    retry_meta["fallback_key_label"] = fallback_key_label
                if usage_metadata:
                    retry_meta["usage_metadata"] = usage_metadata
                if failed_usage_metadata:
                    retry_meta["failed_usage_metadata"] = failed_usage_metadata
                if errors:
                    retry_meta["previous_errors"] = errors[-2:]
                return parsed, total_latency_ms, retry_meta
            except self.errors.error() as exc:
                usage_metadata = self.evidence.failure_usage()(provider, exc)
                if usage_metadata:
                    failed_usage_metadata.append(usage_metadata)
                errors.append(self.evidence.text()(str(exc), 180))
                retryable = self.evidence.retryable()(exc)
                can_retry = retryable and attempt < attempts
                repair_next_attempt = self.evidence.needs_repair()(exc)
                if (
                    can_retry
                    and isinstance(exc, self.errors.overloaded())
                    and (getattr(exc, "http_status", None) == 503 or "HTTP 503" in str(exc))
                    and attempt_settings.get("provider") == "gemini"
                    and attempt_settings.get("model") != "gemini-2.5-flash-lite"
                    and not cached_content
                    and allow_overloaded_model_fallback
                    and not settings.get("profile_id")
                ):
                    fallback_model = "gemini-2.5-flash-lite"
                    fallback_reason = "provider_overloaded"
                    attempt_settings = {**attempt_settings, "model": fallback_model}
                elif (
                    can_retry
                    and overloaded_retry_delay_seconds is not None
                    and isinstance(exc, self.errors.overloaded())
                    and (getattr(exc, "http_status", None) == 503 or "HTTP 503" in str(exc))
                ):
                    retry_delay_seconds = max(0.0, float(overloaded_retry_delay_seconds))
                elif can_retry and not repair_next_attempt:
                    rotated_settings = self.providers.rotate()({**settings, "model": attempt_settings.get("model") or settings.get("model")}, used_key_ids)
                    if rotated_settings:
                        next_key_id = str(rotated_settings.get("active_key_id") or "")
                        attempt_settings = rotated_settings
                        if next_key_id:
                            used_key_ids.add(next_key_id)
                            fallback_key_id = next_key_id
                        fallback_key_label = str(rotated_settings.get("key_source_name") or "")
                if not can_retry:
                    self.evidence.annotate()(
                        exc,
                        attempt=attempt,
                        errors=errors,
                        failed_usage_metadata=failed_usage_metadata,
                        usage_metadata=usage_metadata,
                        fallback_model=fallback_model,
                        fallback_reason=fallback_reason,
                    )
                    raise
            if retry_delay_seconds is not None:
                self.timing.sleep()(retry_delay_seconds)
            elif self.timing.backoff() > 0:
                jitter = self.timing.jitter()(0, min(0.4, self.timing.backoff()))
                self.timing.sleep()((self.timing.backoff() * attempt) + jitter)
        raise self.errors.error()(
            errors[-1] if errors else "AI provider failed",
            failed_usage_metadata=failed_usage_metadata,
            attempts=attempts,
            retry_count=max(0, attempts - 1),
            previous_errors=errors[-2:],
            fallback_model=fallback_model,
            fallback_reason=fallback_reason,
        )


class ImageRetryFlow:
    def __init__(self, calls: ImageRetryCalls, errors: RetryErrors, timing: ImageRetryTiming):
        self.calls, self.errors, self.timing = calls, errors, timing

    def auto_optimize_generate_image_with_retry(self,
        settings: dict[str, Any],
        model: str,
        prompt: str,
        user_content: list[dict[str, Any]],
        *,
        system_prompt: str = "",
    ) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []
        last_exc: AiProviderError | None = None
        for attempt in range(1, self.timing.attempts() + 1):
            try:
                provider = self.calls.factory()(settings)
                with self.calls.gate():
                    result = provider.generate_image(prompt, user_content, model=model, system_prompt=system_prompt)
                result["attempts"] = attempt
                result["retry_count"] = max(0, attempt - 1)
                result["previous_errors"] = errors[-3:]
                return result
            except self.errors.error() as exc:
                last_exc = exc
                error_item = {
                    "attempt": attempt,
                    "http_status": getattr(exc, "http_status", None),
                    "retryable": self.calls.retryable()(exc),
                    "message": self.calls.text()(str(exc), 220),
                    "created_at": int(self.timing.now()()),
                }
                errors.append(error_item)
                if not error_item["retryable"] or attempt >= self.timing.attempts():
                    exc.attempts = attempt
                    exc.retry_count = max(0, attempt - 1)
                    exc.previous_errors = [str(item.get("message") or "") for item in errors[-3:]]
                    raise
                self.timing.sleep()(self.calls.delay()(attempt, exc))
        if last_exc:
            raise last_exc
        raise self.errors.error()("Image provider failed without an explicit error")
