"""Local model configuration file, validation and key-selection dependencies."""
from collections.abc import Callable, Set
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from fastapi import HTTPException
Record = dict[str, Any]
class ModelConfigFiles(Protocol):
    def exists(self, path: Path) -> bool: ...
    def read_text(self, path: Path, *, encoding: str) -> str: ...
    def write_text(self, path: Path, value: str, *, encoding: str) -> Any: ...
@dataclass(frozen=True)
class LocalModelConfigFiles:
    ensure_dirs: Callable[[], Callable[[], None]]
    _business_files: Callable[[], ModelConfigFiles]
    AI_LOCAL_CONFIG_PATH: Callable[[], Path]
    DATA_DIR: Callable[[], Path]
    ai_local_config_temp_path: Callable[[], Callable[[], Path]]
    DEFAULT_AI_CONFIG: Callable[[], Record]
    HTTPException: Callable[[], type[HTTPException]]
@dataclass(frozen=True)
class LocalJsonModelPolicy:
    AI_DEFAULT_PROVIDER: Callable[[], str]
    AI_SUPPORTED_PROVIDERS: Callable[[], Set[str]]
    AI_DEFAULT_TIMEOUT_SECONDS: Callable[[], int | float]
    default_ai_model: Callable[[], Callable[[str], str]]
    default_ai_base_url: Callable[[], Callable[[str], str]]
    validate_ai_proxy_url: Callable[[], Callable[[Any], str]]
    validate_ai_timeout: Callable[[], Callable[[Any], int | float]]
    normalize_ai_key_items: Callable[[], Callable[[Record, str], list[Record]]]
    ai_keys_for_provider: Callable[[], Callable[[list[Record], str], list[Record]]]
@dataclass(frozen=True)
class LocalImageModelPolicy:
    IMAGE_GENERATION_DEFAULT_PROVIDER: Callable[[], str]
    IMAGE_GENERATION_SUPPORTED_PROVIDERS: Callable[[], Set[str]]
    IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS: Callable[[], int | float]
    default_image_generation_model: Callable[[], Callable[[str], str]]
    default_image_generation_base_url: Callable[[], Callable[[str], str]]
    validate_ai_base_url: Callable[[], Callable[[Any], str]]
    validate_image_generation_timeout: Callable[[], Callable[[Any], int | float]]
    normalize_image_key_items: Callable[[], Callable[[Record, str], list[Record]]]
    image_keys_for_provider: Callable[[], Callable[[list[Record], str], list[Record]]]
