"""Typed task-list and projection capabilities shared by the jobs read/write surfaces."""
from typing import Any, Protocol

Record = dict[str, Any]


class ListJobs(Protocol):
    def __call__(self, user: Record | None = None, target_user_id: str | None = None) -> list[Record]: ...


class RefreshTrainingJob(Protocol):
    def __call__(self, task: Record, *, allow_remote_refresh: bool = False) -> Record: ...
