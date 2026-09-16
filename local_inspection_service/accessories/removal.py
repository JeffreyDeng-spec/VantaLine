"""Existing accessory removal ordering, including legacy JSON behavior."""
from collections.abc import Callable
from typing import Any
from fastapi import HTTPException
from .file_ports import FileAccess
from .removal_ports import RemovalStore
from .policy import accessory_uid
from .projection import AccessoryProjection


class AccessoryRemoval:
    def __init__(self, access: FileAccess, store: RemovalStore,
                 remove_from_pipeline: Callable[[str], Any], projection: AccessoryProjection):
        self.access, self.store = access, store
        self.remove_from_pipeline, self.projection = remove_from_pipeline, projection

    def delete_accessory(self, accessory_id: str) -> dict[str, Any]:
        user = self.access.current_user()
        config = self.store.load()
        target = next((item for item in config.get("accessories", []) if accessory_uid(item) == accessory_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="Accessory not found")
        self.access.require_access(target, user, write=True)
        before = len(config.get("accessories", []))
        config["accessories"] = [item for item in config.get("accessories", []) if accessory_uid(item) != accessory_id]
        if len(config["accessories"]) == before:
            raise HTTPException(status_code=404, detail="Accessory not found")
        selected = config.get("training", {}).get("selected_accessory_ids", [])
        config["training"]["selected_accessory_ids"] = [item_id for item_id in selected if item_id != accessory_id]
        if self.store.postgres_enabled():
            if not self.store.delete(accessory_id):
                raise HTTPException(status_code=404, detail="Accessory not found")
            self.store.save_app_config(config)
        elif not self.store.delete(accessory_id, config):
            raise HTTPException(status_code=404, detail="Accessory not found")
        self.remove_from_pipeline(accessory_id)
        return {"status": "deleted", "accessory_id": accessory_id, "items": self.projection.serialize_accessory_items(self.store.scope(config, user)["accessories"])}
