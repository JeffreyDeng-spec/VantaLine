"""Late-resolved capabilities for one pipeline task update use case."""
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class TaskUpdateAccess:
    current_user: Callable[[], Callable[[], Any]]
    http_error: Callable[[], Callable[..., Exception]]
    load_config: Callable[[], Callable[[], dict[str, Any]]]
    scope_config: Callable[[], Callable[[dict[str, Any], Any], dict[str, Any]]]
    load_task: Callable[[], Callable[[str], dict[str, Any] | None]]
    require_record_access: Callable[[], Callable[..., Any]]
    require_permission: Callable[[], Callable[..., Any]]
    assert_unique_name: Callable[[], Callable[..., Any]]
    record_owner_id: Callable[[], Callable[[dict[str, Any]], str]]


@dataclass(frozen=True)
class TaskUpdatePolicy:
    canonical_accessory_ids: Callable[[], Callable[..., list[str]]]
    normalize_accessory_counts: Callable[[], Callable[..., dict[str, int]]]
    accessory_snapshot: Callable[[], Callable[..., tuple[dict[str, str], list[str]]]]
    normalize_detection_method: Callable[[], Callable[[str], str]]
    method_uses_training: Callable[[], Callable[[str], bool]]
    detection_methods: Callable[[], Any]
    normalize_expected_count: Callable[[], Callable[[Any], int]]


@dataclass(frozen=True)
class TaskUpdateRuntime:
    lock: Callable[[], AbstractContextManager[Any]]
    now: Callable[[], Callable[[], float]]
    save_task: Callable[[], Callable[[dict[str, Any]], Any]]
    public_task: Callable[[], Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]]
