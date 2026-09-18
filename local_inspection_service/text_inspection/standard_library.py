"""Account-scoped standard queries and evidence retrieval."""
from collections.abc import Callable
from fastapi import HTTPException
from .standard_ports import Record, StandardAccess, StandardRecords


class StandardLibrary:
    def __init__(self, access: StandardAccess, records: StandardRecords,
                 refresh: Callable[[str, str], object], asset_bytes: Callable[[Record, str], bytes]):
        self.access, self.records = access, records
        self.refresh, self.asset_bytes = refresh, asset_bytes

    def list_text_inspection_standards(self) -> Record:
        self.access.require_permission("inspection", detail="没有文字检验权限")
        owner_user_id, _ = self.access.owner()
        items = [self.records.public()(item) for item in self.records.load("standards") if str(item.get("owner_user_id")) == owner_user_id and item.get('status') != 'deleted']
        return {"items": sorted(items, key=lambda item: int(item.get("created_at") or 0), reverse=True)}

    def get_text_inspection_standard(self, standard_id: str) -> Record:
        self.access.require_permission("inspection", detail="没有文字检验权限")
        owner_user_id, _ = self.access.owner()
        standard = self.records.owned("standards", standard_id, owner_user_id)
        if not standard:
            raise HTTPException(status_code=404, detail="标准不存在")
        if standard.get('classification', {}).get('state') == 'processing':
            self.refresh(standard_id, owner_user_id)
            standard = self.records.owned('standards', standard_id, owner_user_id) or standard
        assets = [self.records.public()(item) for item in self.records.load("assets") if item.get("standard_id") == standard_id and item.get("owner_user_id") == owner_user_id]
        return {**self.records.public()(standard), "assets": sorted(assets, key=lambda item: int(item.get("ordinal") or 0))}

    def get_text_inspection_asset_content(self, asset_id: str) -> tuple[bytes, str]:
        self.access.require_permission("inspection", detail="没有文字检验权限")
        owner_user_id, _ = self.access.owner()
        asset = self.records.owned("assets", asset_id, owner_user_id)
        if not asset:
            raise HTTPException(status_code=404, detail="资源不存在")
        if not asset.get("media_path"):
            self.asset_bytes(asset, owner_user_id)
        contents = self.asset_bytes(asset, owner_user_id)
        mime = str(asset.get("mime_type") or ("image/png" if asset.get("asset_kind") == "manual_page" else "application/octet-stream"))
        return contents, mime
