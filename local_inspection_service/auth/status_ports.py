"""Explicit capabilities for public status projections."""
from collections.abc import Callable, Set
from dataclasses import dataclass
from typing import Any
Record = dict[str, Any]
User = Record | None
@dataclass(frozen=True)
class StatusPolicy:
    admin: Callable[[], Callable[[User], bool]]
    permission: Callable[[], Callable[[User, str], bool]]
    model_fields: Callable[[], Set[str]]
    sanitize: Callable[[], Callable[[Record], Record]]
@dataclass(frozen=True)
class StatusSources:
    ai: Callable[[], Callable[[], Record]]
    image: Callable[[], Callable[[], Record]]
@dataclass(frozen=True)
class StatusProjectionCalls:
    ai: Callable[[], Callable[[], Record]]
    image: Callable[[], Callable[[], Record]]
    model: Callable[[], Callable[[Record, User], Record]]
    ai_for_user: Callable[[], Callable[[User], Record]]
