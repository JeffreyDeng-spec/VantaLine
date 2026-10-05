"""Typed per-call capabilities for account scoping and response projection."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
Record = dict[str, Any]
@dataclass(frozen=True)
class AccountAccess:
    current_auth_user: Callable[[], Callable[[], Record]]
    user_is_admin: Callable[[], Callable[[Record], bool]]
    user_has_permission: Callable[[], Callable[[Record, str], bool]]
    include_internal_runtime_details: Callable[[], Callable[[Record], bool]]
    record_mutable_by_user: Callable[[], Callable[[Record, Record], bool]]
    record_visible_to_user: Callable[[], Callable[[Record, Record, str | None], bool]]
@dataclass(frozen=True)
class AccountConfig:
    accessory_uid: Callable[[], Callable[[Record], str]]
    training_state_for_user: Callable[[], Callable[[Record, Record, set[str], str | None], Record]]
    PLC_CAPTURE_RESULTS_KEY: Callable[[], str]
    scope_config_for_user: Callable[[], Callable[..., Record]]
    load_config: Callable[[], Callable[[], Record]]
@dataclass(frozen=True)
class AccountModels:
    selected_model_spec: Callable[[], Callable[[str | None, Record], Record]]
    public_ai_detection_status_for_user: Callable[[], Callable[[Record], Record]]
@dataclass(frozen=True)
class AccountMedia:
    OUTPUT_DIR: Callable[[], Path]
