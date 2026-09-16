"""Persistence capabilities for accessory removal; no live connection is retained."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

Record = dict[str, Any]


class DeleteItem(Protocol):
    def __call__(self, identifier: str, config: Record | None = None) -> bool: ...


@dataclass(frozen=True)
class RemovalStore:
    load: Callable[[], Record]
    postgres_enabled: Callable[[], bool]
    delete: DeleteItem
    save_app_config: Callable[[Record], None]
    scope: Callable[[Record, Record], Record]
