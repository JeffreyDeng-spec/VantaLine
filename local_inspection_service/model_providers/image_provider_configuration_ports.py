"""Image model selection, explicit endpoint settings and payload capabilities."""
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
Record = dict[str, Any]

@dataclass(frozen=True)
class ImageProviderSelection:
    CURSOR_IMAGE_MODEL_PRIORITY: Callable[[], Sequence[str]]
    CURSOR_IMAGE_MODEL_KEYWORDS: Callable[[], Sequence[str]]
    normalize_agent_model_options: Callable[[], Callable[[Any], list[Record]]]
    cursor_image_model_score: Callable[[], Callable[[str], tuple[int, int]]]
    normalize_agent_provider: Callable[[], Callable[..., str]]
    AGENT_PROVIDER_CURSOR: Callable[[], str]
    agent_connected: Callable[[], Callable[[Record], bool]]

@dataclass(frozen=True)
class ImageProviderSettings:
    load_agent_config: Callable[[], Callable[[], Record]]
    inspect_cursor_image_models: Callable[[], Callable[[Record], Record]]
    CURSOR_IMAGE2_BASE_URL_ENV: Callable[[], str]
    AGENT_CURSOR_DEFAULT_BASE_URL: Callable[[], str]
    CURSOR_IMAGE2_ENDPOINT_ENV: Callable[[], str]
    CURSOR_IMAGE2_API_KEY_ENV: Callable[[], str]
    CURSOR_IMAGE2_MODEL_ENV: Callable[[], str]
    CURSOR_IMAGE2_DEFAULT_MODEL: Callable[[], str]
    masked_url_for_status: Callable[[], Callable[[str], str]]
    cursor_image2_settings: Callable[[], Callable[[], Record]]
    LOCAL_CODEX_IMAGE_PROVIDER: Callable[[], str]
    CURSOR_IMAGE2_PROVIDER: Callable[[], str]

@dataclass(frozen=True)
class ImageProviderPayload:
    image_job_prompt: Callable[[], Callable[[Record], str]]
    image_file_payload: Callable[[], Callable[[Path], Record]]
    MAX_IMAGE_WORKER_INPUTS: Callable[[], int]
    cursor_image2_response_candidates: Callable[[], Callable[[Any], list[Record]]]
    decode_b64_image: Callable[[], Callable[[Any], bytes | None]]
