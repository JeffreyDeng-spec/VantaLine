"""Late-resolved capabilities for the pipeline Agent chat request."""
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class AgentChatAccess:
    current_user: Callable[[], Callable[[], Any]]
    load_config: Callable[[], Callable[[], dict[str, Any]]]
    scope_config: Callable[[], Callable[..., dict[str, Any]]]
    bounded_text: Callable[[], Callable[[Any, int], str]]
    load_task: Callable[[], Callable[[str], dict[str, Any] | None]]
    require_record_access: Callable[[], Callable[..., Any]]
    http_error: Callable[[], Callable[..., Exception]]


@dataclass(frozen=True)
class AgentChatRuntime:
    task_lock: Callable[[], AbstractContextManager[Any]]
    normalize_method: Callable[[], Callable[[str], str]]
    uses_training: Callable[[], Callable[[str], bool]]
    deepcopy: Callable[[], Callable[[Any], Any]]
    decide: Callable[[], Callable[..., Any]]
    commit_turn: Callable[[], Callable[..., Any]]
    save_task: Callable[[], Callable[[dict[str, Any]], Any]]
    public_task: Callable[[], Callable[..., dict[str, Any]]]
    schedule_advance: Callable[[], Callable[..., Any]]