"""Explicit photo highlight workflow service without application imports."""
from typing import Any
from .photo_highlight_ports import PhotoWorkflowObjects, PhotoSpriteLimits, PhotoWorkflowState, PhotoWorkflowModels


class PhotoHighlightWorkflow:
    def __init__(self, objects: PhotoWorkflowObjects, limits: PhotoSpriteLimits, state: PhotoWorkflowState, models: PhotoWorkflowModels) -> None:
        self._objects = objects
        self._limits = limits
        self._state = state
        self._models = models

    def mark_legacy_pose_flow_skipped_for_photo_highlight(self,
        task: dict[str, Any], config: dict[str, Any], orchestration: dict[str, Any]
    ) -> dict[str, Any]:
        object_items = self._objects.items()(task, config)
        if not object_items:
            return orchestration
        orchestration["pose_plan"] = {
            "agent": "real_photo_highlight_sprite_flow",
            "task_id": task.get("id"),
            "accessories": [
                {
                    "accessory_id": self._objects.identifier()(item),
                    "name": item.get("name") or self._objects.identifier()(item),
                    "source_image_count": len(self._objects.sources()(item)),
                    "method": "real_photo_highlight_mask_sprite",
                }
                for item in object_items
            ],
            "pose_count": 0,
            "policy": "skip_legacy_ai_pose_images_for_training",
            "created_at": self._state.now()(),
        }
        orchestration["skip_pose_image_generation"] = True
        orchestration.setdefault(
            "photo_highlight_sprite_policy",
            {
                "method": "real_photo_highlight_mask_sprite",
                "min_reference_images": self._limits.minimum(),
                "training_label_policy": "bbox_from_photo_highlight_mask",
                "legacy_pose_generation": "disabled",
                "updated_at": self._state.now()(),
            },
        )
        for call in orchestration.get("tool_calls") or []:
            if call.get("tool") == self._state.tool() and call.get("status") not in {"completed", "skipped"}:
                call.update({"status": "skipped", "error": "", "updated_at": self._state.now()()})
        self._state.stage()(
            orchestration,
            "agent_pose_planning",
            "skipped",
            100,
            detail="Real-photo photo-highlight flow does not use legacy pose planning.",
        )
        return orchestration

    def prepare_photo_highlight_sprites_for_task(self, task: dict[str, Any], config: dict[str, Any], orchestration: dict[str, Any]) -> tuple[bool, bool]:
        object_items = self._objects.items()(task, config)
        if not object_items:
            return True, False
        self._state.skip_legacy()(task, config, orchestration)
        tool_config = self._models.configuration()()
        if not tool_config.get("configured"):
            reason = tool_config.get("message") or "Image generation is not configured; cannot build photo-highlight sprites."
            self._state.pause()(task, orchestration, stage="pose_image_generation", reason=reason, suggested_actions=["configure_image_generation", "cancel"])
            self._state.stage()(orchestration, "pose_image_generation", "needs_user_action", 0, detail=reason)
            return False, False
        settings = self._models.settings()()
        settings["model"] = tool_config["model"]
        settings["timeout_seconds"] = tool_config["timeout_seconds"]
        provider = self._models.provider()(settings)
        changed = False
        total = len(object_items)
        self._state.stage()(orchestration, "pose_image_generation", "running", 5, detail=f"Preparing photo-highlight sprites for {total} object accessories.")
        for index, item in enumerate(object_items, start=1):
            sources = self._objects.sources()(item)
            if len(sources) < self._limits.minimum():
                reason = f"配件 {item.get('name') or self._objects.identifier()(item)} 至少需要 {self._limits.minimum()} 张不同角度实拍图。"
                self._state.pause()(task, orchestration, stage="pose_image_generation", reason=reason, suggested_actions=["upload_more_reference_photos", "cancel"])
                self._state.stage()(orchestration, "pose_image_generation", "needs_user_action", 0, detail=reason)
                return False, changed
            before_signature = self._objects.signature()(item)
            ok, error = self._models.build_sprites()(task, item, provider, str(tool_config["model"] or ""))
            after_signature = self._objects.signature()(item)
            changed = changed or before_signature != after_signature
            if not ok:
                reason = error or f"配件 {item.get('name') or self._objects.identifier()(item)} 的实拍高亮抠图失败。"
                self._state.pause()(task, orchestration, stage="pose_image_generation", reason=reason[:240], suggested_actions=["retry_pose_image_generation", "upload_more_reference_photos", "cancel"])
                self._state.stage()(orchestration, "pose_image_generation", "needs_user_action", int(index * 100 / max(total, 1)), detail=reason[:240])
                return False, changed
            self._state.stage()(orchestration, "pose_image_generation", "running", min(99, int(index * 100 / max(total, 1))), detail=f"{index}/{total} photo-highlight sprite sets ready.")
        orchestration["state"] = "photo_highlight_sprites_completed"
        orchestration["active_stage"] = "sample_generation"
        orchestration["pause"] = None
        orchestration["photo_highlight_sprite_policy"] = {
            "method": "real_photo_highlight_mask_sprite",
            "min_reference_images": self._limits.minimum(),
            "training_label_policy": "bbox_from_photo_highlight_mask",
            "updated_at": self._state.now()(),
        }
        self._state.stage()(orchestration, "pose_image_generation", "completed", 100, detail="Photo-highlight sprites generated from real photos; legacy AI pose images skipped.")
        return True, changed

    def ensure_agent_mcp_pose_plan(self, task: dict[str, Any], config: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
        orchestration = self._state.current()(task)
        if self._state.photo_flow()(task, config):
            return self._state.skip_legacy()(task, config, orchestration)
        if force or not isinstance(orchestration.get("pose_plan"), dict):
            orchestration["pose_plan"] = self._state.build_plan()(task, config)
            orchestration["state"] = "agent_pose_planning"
            orchestration["active_stage"] = "agent_pose_planning"
            self._state.stage()(orchestration, "agent_pose_planning", "completed", 100, detail="Structured pose plan persisted.")
        return orchestration
