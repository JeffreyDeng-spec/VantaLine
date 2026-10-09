"""App-owned provider classes; transport policy stays in the native providers."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..model_profiles.dependencies import ResolverProvider
from .agnes_transport import AgnesImageProvider as AgnesTransport
from .gemini_ports import GeminiTransportErrors, GeminiTransportIO
from .gemini_transport import GeminiAiProvider as GeminiTransport
from .image_ports import ImageTransportErrors, ImageTransportIO
from .openai_ports import OpenAITransportErrors, OpenAITransportIO
from .openai_transport import OpenAICompatibleAiProvider as OpenAITransport
from .qwen_image_transport import QwenImageProvider as QwenTransport


@dataclass(frozen=True)
class TransportInputs:
    openai_io: Callable[[], OpenAITransportIO]
    openai_errors: Callable[[], OpenAITransportErrors]
    gemini_io: Callable[[], GeminiTransportIO]
    gemini_errors: Callable[[], GeminiTransportErrors]
    image_io: Callable[[], ImageTransportIO]
    image_errors: Callable[[], ImageTransportErrors]
    agnes_image_size: Callable[[], str]
    qwen_image_size: Callable[[], str]
    image_candidates: Callable[[], Callable[[Any], list[dict[str, Any]]]]


class ProviderTransports:
    """One app's provider types and captured resolver, allocated without I/O.

    Port objects are selected when a provider is constructed, as in the entry's
    original subclasses. Their capabilities and image-size values remain lazy.
    The resolver callable and cache TTL are captured at composition time; a
    model snapshot or live resolver service is never acquired here.
    """

    openai: type[OpenAITransport]
    gemini: type[GeminiTransport]
    agnes: type[AgnesTransport]
    qwen: type[QwenTransport]

    def __init__(self, inputs: TransportInputs, resolve: ResolverProvider,
                 *, cache_ttl_seconds: int):
        self.inputs = inputs
        self.openai_resolver = resolve
        self.gemini_resolver = resolve
        self.agnes_resolver = resolve
        self.qwen_resolver = resolve
        owner = self

        class OpenAICompatibleAiProvider(OpenAITransport):
            def __init__(self, settings: dict[str, Any]):
                super().__init__(settings, owner.inputs.openai_io(),
                                 owner.inputs.openai_errors(), owner.openai_resolver)

        class GeminiAiProvider(GeminiTransport):
            def __init__(self, settings: dict[str, Any]):
                super().__init__(settings, owner.inputs.gemini_io(),
                                 owner.inputs.gemini_errors(), owner.gemini_resolver)

            def create_cached_content(
                self, system_prompt: str, user_content: list[dict[str, Any]], *,
                display_name: str, ttl_seconds: int = cache_ttl_seconds,
            ) -> dict[str, Any]:
                return super().create_cached_content(
                    system_prompt, user_content,
                    display_name=display_name, ttl_seconds=ttl_seconds,
                )

        class AgnesImageProvider(AgnesTransport):
            def __init__(self, settings: dict[str, Any]):
                super().__init__(
                    settings, owner.inputs.image_io(), owner.inputs.image_errors(),
                    owner.agnes_resolver, owner.inputs.agnes_image_size,
                    owner.inputs.image_candidates,
                )

        class QwenImageProvider(QwenTransport):
            def __init__(self, settings: dict[str, Any]):
                super().__init__(
                    settings, owner.inputs.image_io(), owner.inputs.image_errors(),
                    owner.qwen_resolver, owner.inputs.qwen_image_size,
                )

        self.openai = OpenAICompatibleAiProvider
        self.gemini = GeminiAiProvider
        self.agnes = AgnesImageProvider
        self.qwen = QwenImageProvider
