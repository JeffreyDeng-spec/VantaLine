"""Provider configuration policy without application state."""
from typing import Any
from .configuration_ports import JsonDefaults, ImageDefaults

class ProviderDefaults:
    def __init__(self, json: JsonDefaults, image: ImageDefaults) -> None:
        self._json = json
        self._image = image

    def default_ai_model(self, provider: str) -> str:
        return self._json.models().get(provider, self._json.model())

    def default_ai_base_url(self, provider: str) -> str:
        return self._json.base_urls().get(provider, self._json.base_urls()[self._json.provider()])

    def ai_provider_label(self, provider: str) -> str:
        return self._json.labels().get(provider, provider or self._json.provider())

    def default_image_generation_model(self, provider: str) -> str:
        return self._image.models().get(provider, self._image.models()[self._image.provider()])

    def default_image_generation_base_url(self, provider: str) -> str:
        return self._image.base_urls().get(provider, self._image.base_urls()[self._image.provider()])

    def default_image_generation_api_key_env(self, provider: str) -> str:
        return self._image.key_envs().get(provider, self._image.key_env())

    def image_generation_provider_key(self, provider: str) -> str:
        return self._image.provider_keys().get(provider, self._image.provider_keys()[self._image.provider()])

    def image_generation_provider_label(self, provider: str) -> str:
        return self._image.labels().get(provider, provider or self._image.provider())
