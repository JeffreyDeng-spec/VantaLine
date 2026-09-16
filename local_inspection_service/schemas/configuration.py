"""Configuration request shapes; defaults and coercion match the existing API."""
from pydantic import BaseModel


class StreamConfig(BaseModel):
    enabled: bool = False
    source: str = "camera"
    url: str = ""


class AiConfigRequest(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    proxy_url: str | None = None
    auto_local_proxy: bool | None = None
    api_key: str | None = None
    active_key_id: str | None = None
    api_key_env: str | None = None
    timeout: float | None = None
    timeout_seconds: float | None = None
    image_provider: str | None = None
    image_model: str | None = None
    image_base_url: str | None = None
    image_timeout_seconds: float | None = None
    image_api_key: str | None = None
    image_active_key_id: str | None = None
    image_api_key_env: str | None = None


class AgentConfigRequest(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    api_key: str | None = None
    active_key_id: str | None = None
    model: str | None = None
    timeout_seconds: float | None = None
    auto_advance_default: bool | None = None
