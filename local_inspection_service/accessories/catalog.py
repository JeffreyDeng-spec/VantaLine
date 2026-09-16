"""Accessory listing and authorized detail orchestration."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from fastapi import HTTPException
from ..auth.policy import user_is_admin
from .policy import accessory_uid
from .projection import AccessoryProjection

Record = dict[str, Any]


class RecordGuard(Protocol):
    def __call__(self, record: Record, user: Record | None = None, *, write: bool = False) -> None: ...


@dataclass(frozen=True)
class CatalogDependencies:
    current_user: Callable[[], Record]
    load_config: Callable[[], Record]
    scope_config: Callable[[Record, Record, str | None], Record]
    require_access: RecordGuard
    detail: Callable[[Record], Record]


class AccessoryCatalog:
    def __init__(self, dependencies: CatalogDependencies, projection: AccessoryProjection):
        self.dependencies = dependencies
        self.projection = projection

    def get_accessories(self, view: str = "summary", summary: bool = True, user_id: str | None = None) -> dict[str, Any]:
        user = self.dependencies.current_user()
        full_config = self.dependencies.load_config()
        config = self.dependencies.scope_config(full_config, user, user_id if user_is_admin(user) else None)
        use_summary = summary and str(view or "summary").strip().lower() not in {"full", "detail", "all"}
        return {"items": self.projection.serialize_accessory_items(config["accessories"], summary=use_summary)}

    def get_accessory_detail(self, accessory_id: str) -> dict[str, Any]:
        user = self.dependencies.current_user()
        config = self.dependencies.load_config()
        for item in config.get("accessories", []):
            if accessory_uid(item) == accessory_id:
                self.dependencies.require_access(item, user)
                # Viewing does not request clean sprites; generation stays with
                # existing task normalization / agent-MCP pose workflows.
                return self.dependencies.detail(item)
        raise HTTPException(status_code=404, detail="Accessory not found")
