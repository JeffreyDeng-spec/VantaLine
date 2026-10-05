"""Pipeline task progress and linked-resource invalidation storage ports."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any
Record = dict[str, Any]

@dataclass(frozen=True)
class MutationStorage:
    runtime_postgres_repository_or_none: Callable[[], Callable[[], Any]]
    save_pipeline_task: Callable[[], Callable[[Record], Record | None]]
    save_pipeline_tasks: Callable[[], Callable[[list[Record]], None]]
    _pipeline_tasks_lock: Callable[[], AbstractContextManager[Any]]
    load_pipeline_tasks: Callable[[], Callable[[], list[Record]]]
    load_pipeline_task: Callable[[], Callable[[str], Record | None]]
    save_pipeline_task_batch_changes: Callable[[], Callable[[list[Record], list[Record]], None]]

@dataclass(frozen=True)
class MutationAccess:
    sanitize_ai_detection_task_id: Callable[[], Callable[[str], str]]
    record_mutable_by_user: Callable[[], Callable[[Record, Record], bool]]
