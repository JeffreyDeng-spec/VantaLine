"""Explicit identity, account-store and per-thread repository providers."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository

Record = dict[str, Any]
RepositoryFactory = Callable[[], PostgresRuntimeRepository | None]


@dataclass(frozen=True)
class AgentAccess:
    current_user: Callable[[], Record]
    require_admin: Callable[[], Any]


@dataclass(frozen=True)
class AgentAccounts:
    load: Callable[[], Record]
    find: Callable[[Record, str], Record | None]
