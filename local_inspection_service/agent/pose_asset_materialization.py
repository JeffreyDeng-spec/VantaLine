"""Explicit pose asset materialization service without application imports."""
from typing import Any
from .pose_materialization_ports import PoseChromaSources, PoseMaterializationState, PoseAssetMedia, PoseMaterializationSprites


class PoseAssetMaterialization:
    def __init__(self, chroma: PoseChromaSources, state: PoseMaterializationState, media: PoseAssetMedia, sprites: PoseMaterializationSprites) -> None:
        self._chroma = chroma
        self._state = state
        self._media = media
        self._sprites = sprites

    def materialize_agent_mcp_pose_assets(self, task: dict[str, Any], config: dict[str, Any]) -> bool:
        orchestration = self._state.current()(task)
        if isinstance(orchestration.get("photo_highlight_sprite_policy"), dict):
            return False
        completed_calls = [
            call
            for call in orchestration.get("tool_calls") or []
            if call.get("tool") == self._state.tool() and call.get("status") == "completed"
        ]
        if not completed_calls:
            return False
        accessories_by_id = self._state.lookup()(config)
        changed = False
        touched_items: dict[str, dict[str, Any]] = {}
        now = self._state.now()()
        for call in completed_calls:
            accessory_id = str(call.get("accessory_id") or "")
            item = accessories_by_id.get(accessory_id)
            if not item:
                continue
            output_path = self._media.resolve()(call.get("output_path"))
            if not output_path.exists() or output_path.suffix.lower() not in self._media.suffixes():
                continue
            normalized_assets = item.setdefault("normalized_assets", [])
            if not any(
                isinstance(asset, dict)
                and asset.get("kind") == "agent_mcp_pose_reference"
                and self._media.resolve()(asset.get("path")) == output_path
                for asset in normalized_assets
            ):
                normalized_assets.append(
                    {
                        "kind": "agent_mcp_pose_reference",
                        "path": str(output_path),
                        "url": self._media.public_url()(output_path),
                        "method": "provider_pose_image",
                        "task_id": task.get("id"),
                        "call_id": call.get("call_id"),
                        "pose_id": call.get("pose_id"),
                        "chroma_screen": self._chroma.screen()(call.get("chroma_screen")),
                        "provider": call.get("provider") or "gemini_native_image_generation",
                        "model": call.get("model") or "",
                        "sha256": call.get("sha256") or self._media.digest()(output_path),
                        "metadata_path": call.get("metadata_path") or "",
                        "created_at": now,
                    }
                )
                changed = True
            touched_items[accessory_id] = item
        # Segment the freshly stored standard pose images into clean object sprites
        # (idempotent: rebuilds only when sprites are missing or incomplete).
        for item in touched_items.values():
            if self._sprites.ready()(item, self._sprites.sources()(item)):
                continue
            if self._sprites.build()(item, force=False):
                changed = True
        if changed:
            orchestration["materialized_pose_assets_at"] = now
            orchestration["updated_at"] = now
        return changed
