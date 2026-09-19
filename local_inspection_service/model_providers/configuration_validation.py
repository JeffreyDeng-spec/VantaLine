"""Provider configuration policy without application state."""
from typing import Any
from .configuration_ports import ValidationCapabilities

class ProviderValidation:
    def __init__(self, capabilities: ValidationCapabilities) -> None:
        self._capabilities = capabilities

    def validate_ai_provider(self, value: Any) -> str:
        provider = str(value or "").strip().lower()
        if provider not in self._capabilities.json_providers():
            raise self._capabilities.http_error()(status_code=400, detail=f"Unsupported AI provider: {provider or '(empty)'}")
        return provider

    def validate_image_generation_provider(self, value: Any) -> str:
        provider = str(value or "").strip().lower()
        if provider not in self._capabilities.image_providers():
            raise self._capabilities.http_error()(status_code=400, detail=f"Unsupported image generation provider: {provider or '(empty)'}")
        return provider

    def validate_ai_model(self, value: Any) -> str:
        model = str(value or "").strip()
        if not model:
            raise self._capabilities.http_error()(status_code=400, detail="AI model is required")
        if len(model) > 160 or not self._capabilities.fullmatch()(r"[A-Za-z0-9._:/@+\-]+", model):
            raise self._capabilities.http_error()(status_code=400, detail="AI model contains unsupported characters")
        return model

    def validate_ai_base_url(self, value: Any) -> str:
        base_url = str(value or "").strip()
        parsed = self._capabilities.split_url()(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise self._capabilities.http_error()(status_code=400, detail="AI base_url must be an http(s) URL")
        if parsed.username or parsed.password:
            raise self._capabilities.http_error()(status_code=400, detail="AI base_url must not include credentials")
        if parsed.query or parsed.fragment:
            raise self._capabilities.http_error()(status_code=400, detail="AI base_url must not include query strings or fragments")
        host = parsed.hostname or ""
        if parsed.scheme == "http" and host not in {"localhost", "127.0.0.1", "::1"}:
            raise self._capabilities.http_error()(status_code=400, detail="AI base_url must use https unless it targets localhost")
        return base_url

    def validate_ai_proxy_url(self, value: Any) -> str:
        proxy_url = str(value or "").strip()
        if not proxy_url:
            return ""
        parsed = self._capabilities.split_url()(proxy_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise self._capabilities.http_error()(status_code=400, detail="AI proxy URL must be an http(s) URL")
        if parsed.query or parsed.fragment:
            raise self._capabilities.http_error()(status_code=400, detail="AI proxy URL must not include query strings or fragments")
        return proxy_url

    def validate_ai_timeout(self, value: Any) -> float:
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            raise self._capabilities.http_error()(status_code=400, detail="AI timeout must be a number") from None
        if not 0.5 <= timeout <= 30.0:
            raise self._capabilities.http_error()(status_code=400, detail="AI timeout must be between 0.5 and 30 seconds")
        return round(timeout, 3)

    def validate_image_generation_timeout(self, value: Any) -> float:
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            raise self._capabilities.http_error()(status_code=400, detail="Image generation timeout must be a number") from None
        if not 10.0 <= timeout <= 300.0:
            raise self._capabilities.http_error()(status_code=400, detail="Image generation timeout must be between 10 and 300 seconds")
        return round(timeout, 3)

    def validate_ai_key_env(self, value: Any) -> str:
        key_env = str(value or "").strip()
        if key_env and not self._capabilities.fullmatch()(r"[A-Za-z_][A-Za-z0-9_]*", key_env):
            raise self._capabilities.http_error()(status_code=400, detail="AI api_key_env must be a valid environment variable name")
        return key_env
