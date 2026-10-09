"""Own model configuration, snapshot resolution and HTTP registration for one app."""
from collections.abc import Callable
from typing import Any

from .api import register
from .dependencies import ProfileApiDependencies, ProfileDependencies, require_resolver
from .service import Service

Record = dict[str, Any]


class ModelConfiguration:
    """Allocate an inert profile owner with operation-time external capabilities.

    The agent defaults supplier is consulted after profile resolution, matching
    the existing settings projection. No user, connection, legacy configuration
    or secret is acquired while constructing the owner.
    """

    def __init__(self, dependencies: ProfileDependencies, *, agent_defaults: Callable[[], Record]):
        self.service = Service(dependencies)
        self.agent_defaults = agent_defaults

    def resolve_model_profiles(self) -> Service:
        require_resolver(lambda: self.service)
        return self.service

    def ai_detection_settings(self, purpose: str = "pipeline") -> Record:
        return self.resolve_model_profiles().resolve(purpose)

    def image_generation_settings(self) -> Record:
        return self.resolve_model_profiles().resolve("image")

    def load_agent_config(self) -> Record:
        value = self.resolve_model_profiles().resolve("training_assistant")
        return {**self.agent_defaults(), **value, "enabled": value.get("configured", False)}

    def register(self, app, dependencies: ProfileApiDependencies) -> None:
        register(app, self.resolve_model_profiles(), dependencies)
