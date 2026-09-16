"""Existing row writes and JSON fallbacks with lazy repository/lock factories."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any
from ..storage.postgres_runtime_repository import PostgresRuntimeRepository
from ..storage.runtime_records import accessory_row
from .policy import accessory_uid

Record = dict[str, Any]


@dataclass(frozen=True)
class AccessoryStoreDependencies:
    runtime_repository: Callable[[], PostgresRuntimeRepository | None]
    lock: Callable[[], AbstractContextManager]
    load_config: Callable[[], Record]
    save_config: Callable[[Record], None]


class AccessoryRepository:
    def __init__(self, dependencies: AccessoryStoreDependencies):
        self.dependencies = dependencies

    def save_accessory_item(self, item: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        row = accessory_row(item)
        if not row:
            return None
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            with self.dependencies.lock():
                repository.upsert_row("accessories", row)
            return dict(item)
        next_config = config if isinstance(config, dict) else self.dependencies.load_config()
        accessories = next_config.setdefault("accessories", [])
        row_id = str(row["id"])
        for index, existing in enumerate(accessories):
            if accessory_uid(existing) == row_id:
                accessories[index] = dict(item)
                self.dependencies.save_config(next_config)
                return dict(item)
        accessories.append(dict(item))
        self.dependencies.save_config(next_config)
        return dict(item)

    def delete_accessory_item(self, accessory_id: str, config: dict[str, Any] | None = None) -> bool:
        clean_id = str(accessory_id or "").strip()
        if not clean_id:
            return False
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            with self.dependencies.lock():
                if repository.fetch_by_primary_key("accessories", {"id": clean_id}) is None:
                    return False
                repository.delete_by_primary_key("accessories", {"id": clean_id})
            return True
        next_config = config if isinstance(config, dict) else self.dependencies.load_config()
        accessories = next_config.get("accessories") if isinstance(next_config.get("accessories"), list) else []
        remaining = [item for item in accessories if accessory_uid(item) != clean_id]
        if len(remaining) == len(accessories):
            return False
        next_config["accessories"] = remaining
        self.dependencies.save_config(next_config)
        return True
