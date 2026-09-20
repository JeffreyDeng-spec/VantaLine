"""Explicit pose assets service without application imports."""
from typing import Any
from .pose_asset_ports import PoseAssetPaths, PoseAssetMaterial, PoseAssetSprites, PoseAssetCalls, PoseAssetCatalog


class AgentPoseAssets:
    def __init__(self, paths: PoseAssetPaths, material: PoseAssetMaterial, sprites: PoseAssetSprites, calls: PoseAssetCalls, catalog: PoseAssetCatalog) -> None:
        self._paths = paths
        self._material = material
        self._sprites = sprites
        self._calls = calls
        self._catalog = catalog

    def agent_mcp_pose_reference_assets(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        assets = []
        for asset in item.get("normalized_assets", []):
            if asset.get("kind") != "agent_mcp_pose_reference":
                continue
            path = self._paths.resolve()(asset.get("path"))
            if not path.exists() or path.suffix.lower() not in self._paths.suffixes():
                continue
            asset["path"] = str(path)
            assets.append(asset)
        return assets

    def agent_mcp_accessory_pose_images_exist(self, item: dict[str, Any]) -> bool:
        """True once an accessory already carries its AI standard pose images (or, for
    text parts, its canonical text assets). Used to skip a SECOND round of image
    generation: per the one-set policy, the pipeline generates an accessory's pose
    images on the first task and reuses them forever after."""
        if not isinstance(item, dict):
            return False
        if self._material.kind()(item) == "text":
            return bool(self._material.text_assets()(item))
        source_paths = self._sprites.source_paths()(item)
        if self._sprites.highlight_ready()(item, source_paths):
            return True
        return bool(self._calls.references()(item))

    def agent_mcp_accessory_standard_images_ready(self, item: dict[str, Any]) -> bool:
        """A "YOLO/OCR-ready" accessory already carries its standard images and the
    clean sprites cut from them. When true, a later task reuses these cached
    assets instead of regenerating standard images for this accessory."""
        if not isinstance(item, dict):
            return False
        if self._material.kind()(item) == "text":
            text_assets = self._material.text_assets()(item)
            return bool(text_assets) and self._material.text_complete()(item, text_assets)
        source_paths = self._sprites.source_paths()(item)
        if self._sprites.highlight_ready()(item, source_paths):
            return True
        if not self._calls.references()(item):
            return False
        sprites = self._sprites.assets()(item)
        return bool(sprites) and self._sprites.complete()(item, sprites) and not self._calls.rebuild()(item)

    def agent_mcp_clean_sprites_need_rebuild(self, item: dict[str, Any]) -> bool:
        """True when an accessory's cached clean sprites were cut from AI pose images
    but still carry the legacy grid metadata (a real grid job id and/or a raw
    pose-id family). Such sprites are NOT selectable by the top-view compositor
    and render as black placeholder boxes, so they must be rebuilt with the
    non-grid sentinel + top-view family."""
        if self._material.kind()(item) == "text":
            return False
        if not self._calls.references()(item):
            return False
        for asset in self._sprites.assets()(item):
            if not (asset.get("agent_mcp_pose_reference_path") or asset.get("agent_mcp_pose_call_id")):
                continue
            if int(asset.get("agent_mcp_sprite_build") or 0) < self._sprites.version():
                return True
            if str(asset.get("source_pose_collection_job_id") or "") != "legacy_clean_sprite":
                return True
            if self._sprites.family()(asset.get("source_pose_family") or asset.get("pose_family")) not in {"upright", "lying"}:
                return True
        return False

    def agent_mcp_accessory_has_existing_or_pose_asset(self, item: dict[str, Any], orchestration: dict[str, Any]) -> bool:
        if self._material.kind()(item) == "text":
            return self._material.text_complete()(item)
        if self._sprites.assets()(item):
            return True
        accessory_id = self._catalog.uid()(item)
        for call in orchestration.get("tool_calls") or []:
            if call.get("tool") != self._catalog.pose_tool() or call.get("status") != "completed":
                continue
            if str(call.get("accessory_id") or "") != accessory_id:
                continue
            output_path = self._paths.resolve()(call.get("output_path"))
            if output_path.exists() and output_path.suffix.lower() in self._paths.suffixes():
                return True
        return False

    def agent_mcp_missing_existing_asset_names(self, task: dict[str, Any], config: dict[str, Any], orchestration: dict[str, Any]) -> list[str]:
        accessories_by_id = self._catalog.lookup()(config)
        missing: list[str] = []
        for item_id in self._catalog.canonical_ids()(config, [str(item_id) for item_id in task.get("accessory_ids") or []]):
            item = accessories_by_id.get(item_id)
            if not item:
                continue
            if not self._catalog.has_asset()(item, orchestration):
                missing.append(str(item.get("name") or item_id))
        return missing
