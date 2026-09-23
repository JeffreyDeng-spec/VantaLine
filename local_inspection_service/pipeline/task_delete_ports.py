"""Late-resolved capabilities for the pipeline task deletion use case."""
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class TaskDeleteAccess:
    current_user: Callable[[], Callable[[], Any]]
    load_task: Callable[[], Callable[[str], dict[str, Any] | None]]
    require_record_access: Callable[[], Callable[..., Any]]
    http_error: Callable[[], Callable[..., Exception]]


@dataclass(frozen=True)
class TaskDeleteRuntime:
    cancel_advance: Callable[[], Callable[[str], Any]]
    lock: Callable[[], AbstractContextManager[Any]]
    delete_task_row: Callable[[], Callable[[str], bool]]


@dataclass(frozen=True)
class TaskDeleteCleanup:
    delete_dataset: Callable[[], Callable[..., Any]]
    delete_model: Callable[[], Callable[..., Any]]
    delete_training_job: Callable[[], Callable[..., Any]]
    delete_ai_task: Callable[[], Callable[..., Any]]
