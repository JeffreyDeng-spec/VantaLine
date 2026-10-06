"""Focused access, task storage and pipeline synchronization capabilities."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID
from ..schemas.detection import AiDetectionTaskRequest
Record = dict[str, Any]
class Repository(Protocol):
    def delete_by_primary_key(self, table: str, primary_key: Record) -> Any: ...
class Clock(Protocol):
    def time(self) -> float: ...
class Identifiers(Protocol):
    def uuid4(self) -> UUID: ...
@dataclass(frozen=True)
class TaskRequestAccess:
    current_auth_user: Callable[[], Callable[[], Record]]
    user_is_admin: Callable[[], Callable[[Record], bool]]
    scope_config_for_user: Callable[[], Callable[..., Record]]
    current_owner_fields: Callable[[], Callable[[], Record]]
    resource_owner_id_for_new_record: Callable[[], Callable[[Record], str]]
    record_owner_id: Callable[[], Callable[[Record], str]]
    require_record_access: Callable[[], Callable[..., Any]]
@dataclass(frozen=True)
class TaskRequestPolicy:
    accessory_lookup_by_id: Callable[[], Callable[[Record], dict[str, Record]]]
    DASHBOARD_AI_TASK_NAME: Callable[[], str]
    PIPELINE_DASHBOARD_AI_TASK_SOURCE: Callable[[], str]
    assert_unique_task_name: Callable[[], Callable[..., None]]
    sanitize_ai_detection_task_id: Callable[[], Callable[[str], str]]
    ai_detection_task_payload_from_request: Callable[[], Callable[[AiDetectionTaskRequest, Record], Record]]
    ai_detection_tasks_response: Callable[[], Callable[..., Record]]
    serialize_ai_detection_task: Callable[[], Callable[[Record, Record], Record]]
@dataclass(frozen=True)
class TaskRequestStore:
    load_config: Callable[[], Callable[[], Record]]
    find_ai_detection_task: Callable[[], Callable[[str], Record | None]]
    save_ai_detection_task: Callable[[], Callable[..., None]]
    load_ai_detection_tasks: Callable[[], Callable[[], list[Record]]]
    save_ai_detection_tasks: Callable[[], Callable[[list[Record]], None]]
    runtime_postgres_repository_or_none: Callable[[], Callable[[], Repository | None]]
    store_read_cache_invalidate: Callable[[], Callable[[str], None]]
    delete_ai_detection_task_record: Callable[[], Callable[..., str | None]]
@dataclass(frozen=True)
class TaskPipelineSync:
    _pipeline_tasks_lock: Callable[[], AbstractContextManager]
    load_pipeline_tasks: Callable[[], Callable[[], list[Record]]]
    save_pipeline_tasks: Callable[[], Callable[[list[Record]], None]]
    sync_ready_pipeline_ai_detection_tasks: Callable[[], Callable[..., bool]]
    mark_pipeline_ai_task_deleted: Callable[[], Callable[[str, Record], int]]
@dataclass(frozen=True)
class TaskRequestClock:
    time: Callable[[], Clock]
    uuid: Callable[[], Identifiers]
