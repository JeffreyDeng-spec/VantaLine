"""Pipeline accessory add/remove request orchestration."""
from typing import Any
from .accessory_routes_ports import PipelineAccessoryAccess, PipelineAccessoryCatalog


class PipelineAccessoryRoutes:
    def __init__(self, access: PipelineAccessoryAccess, catalog: PipelineAccessoryCatalog):
        self.access = access
        self.catalog = catalog

    def add(self, accessory_id: str) -> dict[str, Any]:
        user = self.access.current_user()()
        config = self.access.scope_config()(self.access.load_config()(), user)
        resolved = self.catalog.resolve()(config, accessory_id)
        if not resolved:
            raise self.access.http_error()(status_code=404, detail="配件不存在")
        canonical_id, _ = resolved
        self.catalog.add_id()(canonical_id)
        return {"status": "added", "accessory_id": canonical_id, **self.catalog.public_payload()(config, user)}

    def remove(self, accessory_id: str) -> dict[str, Any]:
        user = self.access.current_user()()
        config = self.access.scope_config()(self.access.load_config()(), user)
        resolved = self.catalog.resolve()(config, accessory_id)
        if not resolved:
            raise self.access.http_error()(status_code=404, detail="配件不存在")
        canonical_id, item = resolved
        for item_id in self.catalog.aliases()(item):
            self.catalog.remove_id()(item_id)
        return {"status": "removed", "accessory_id": canonical_id, **self.catalog.public_payload()(config, user)}