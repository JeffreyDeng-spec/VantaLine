"""Accessory detection-route selection; preserves partial provider/save effects."""
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any
from fastapi import HTTPException
from ..retired_features import removed_phase1_feature
from ..schemas.accessories import AccessoryRouteRequest
from .file_ports import FileAccess
from .policy import accessory_uid

Record = dict[str, Any]


@dataclass(frozen=True)
class RouteStore:
    load_config: Callable[[], Record]
    save_item: Callable[[Record, Record], Record | None]


@dataclass(frozen=True)
class RouteActions:
    ensure_profile: Callable[[Record], bool]
    upsert_task: Callable[[str, Record], Record]
    serialize: Callable[[Record], Record]


class AccessoryRouting:
    def __init__(self, access: FileAccess, store: RouteStore, actions: RouteActions,
                 allowed_routes: Callable[[], Collection[str]]):
        self.access, self.store, self.actions = access, store, actions
        self.allowed_routes = allowed_routes

    def set_accessory_route(self, accessory_id: str, request: AccessoryRouteRequest) -> dict[str, Any]:
        user = self.access.current_user()
        route = str(request.route or "").strip()
        if route == "locate":
            removed_phase1_feature("LocateAnything accessory route")
        if route not in self.allowed_routes():
            raise HTTPException(status_code=400, detail=f"未知的检测路线:{route}")
        config = self.store.load_config()
        item = next((entry for entry in config.get("accessories", []) if accessory_uid(entry) == accessory_id), None)
        if not item:
            raise HTTPException(status_code=404, detail="配件不存在")
        self.access.require_access(item, user, write=True)
        item["detection_route"] = route
        result: dict[str, Any] = {"accessory_id": accessory_id, "route": route}
        if route == "ai" and request.apply:
            try:
                self.actions.ensure_profile(item)
                result["profile_status"] = "ready"
            except Exception as exc:  # noqa: BLE001 - 画像生成失败不应阻塞路线切换
                result["profile_status"] = "failed"
                result["profile_error"] = str(exc)[:200]
            self.store.save_item(item, config)
            result["ai_task"] = self.actions.upsert_task(accessory_id, config)
        else:
            self.store.save_item(item, config)
        result["accessory"] = self.actions.serialize(item)
        return result
