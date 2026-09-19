"""Provider business logic with explicit dependencies and original policy."""
from typing import Any
from .errors import AiProviderError
from .gemini_transport import GeminiAiProvider
from .openai_transport import OpenAICompatibleAiProvider
from .agnes_transport import AgnesImageProvider
from .qwen_image_transport import QwenImageProvider
from .orchestration_ports import ProviderFactories, ProviderKeys


class ProviderSelection:
    def __init__(self, factories: ProviderFactories):
        self.factories = factories

    def ai_provider_from_settings(self, settings: dict[str, Any]) -> OpenAICompatibleAiProvider | GeminiAiProvider:
        provider = str(settings.get("provider") or "").strip()
        if provider == "gemini":
            return self.factories.gemini()(settings)
        if provider in {"qwen", "doubao", "openai_compatible"}:
            return self.factories.openai()(settings)
        raise self.factories.config_error()(str(settings.get("message") or f"Unsupported AI provider: {provider or 'missing'}"))

    def ai_provider(self, ) -> OpenAICompatibleAiProvider | GeminiAiProvider:
        return self.factories.json_factory()(self.factories.settings()())

    def image_generation_provider_from_settings(self, settings: dict[str, Any]) -> GeminiAiProvider | AgnesImageProvider | QwenImageProvider:
        provider = str(settings.get("provider") or "").strip()
        if provider == "gemini":
            return self.factories.gemini()(settings)
        if provider == "agnes":
            return self.factories.agnes()(settings)
        if provider == "qwen_image":
            return self.factories.qwen_image()(settings)
        raise self.factories.config_error()(str(settings.get("message") or f"Unsupported image generation provider: {provider or 'missing'}"))

    def ai_settings_match_runtime(self, settings: dict[str, Any]) -> bool:
        if settings.get("profile_id"):
            return False  # Always use the task's frozen object, never the current selection.
        runtime = self.factories.settings()()
        for key in ("provider", "model", "base_url", "api_key", "timeout_seconds", "proxy_url_raw"):
            if settings.get(key) != runtime.get(key):
                return False
        return True


class ProviderKeySelection:
    def __init__(self, keys: ProviderKeys):
        self.keys = keys

    def ai_provider_key_candidates(self, settings: dict[str, Any]) -> list[dict[str, str]]:
        provider = str(settings.get("provider") or "").strip().lower()
        raw_candidates = settings.get("api_key_candidates") if isinstance(settings.get("api_key_candidates"), list) else []
        candidates: list[dict[str, str]] = []
        seen: set[str] = set()

        def add(candidate: dict[str, Any]) -> None:
            key = str(candidate.get("key") or "").strip()
            if not key or key in seen:
                return
            candidate_provider = str(candidate.get("provider") or provider).strip().lower()
            if provider and candidate_provider and candidate_provider != provider:
                return
            seen.add(key)
            candidates.append(
                {
                    "id": str(candidate.get("id") or self.keys.identify()(candidate.get("env") or "", key)),
                    "label": self.keys.text()(candidate.get("label") or candidate.get("env") or "AI API Key", 80),
                    "env": str(candidate.get("env") or ""),
                    "provider": provider,
                    "key": key,
                }
            )

        add(
            {
                "id": settings.get("active_key_id") or "",
                "label": settings.get("key_source_name") or "active",
                "env": settings.get("key_source_name") or "",
                "provider": provider,
                "key": settings.get("api_key") or "",
            }
        )
        for candidate in raw_candidates:
            if isinstance(candidate, dict):
                add(candidate)
        return candidates

    def rotate_ai_provider_key(self, settings: dict[str, Any], used_key_ids: set[str]) -> dict[str, Any] | None:
        candidates = self.keys.candidates()(settings)
        for candidate in candidates:
            candidate_id = str(candidate.get("id") or "")
            if candidate_id and candidate_id in used_key_ids:
                continue
            return {
                **settings,
                "api_key": candidate["key"],
                "active_key_id": candidate_id,
                "key_source": "env",
                "key_source_name": candidate.get("env") or candidate.get("label") or "api_key_candidate",
            }
        return None
