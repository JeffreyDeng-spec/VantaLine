"""Represent AI detection records as stable, in-place pipeline task cards."""
from typing import Any

from .ai_task_sync_ports import PipelineAiAccess, PipelineAiAccessories, PipelineAiIdentity, PipelineAiProjection


class PipelineAiTaskSync:
    def __init__(self, identity: PipelineAiIdentity, accessories: PipelineAiAccessories,
                 access: PipelineAiAccess, projection: PipelineAiProjection):
        self.identity = identity
        self.accessories = accessories
        self.access = access
        self.projection = projection

    def pipeline_ai_task_id(self, ai_task_id: str) -> str:
        return f"pipe_ai_{self.identity.safe_record_id()(self.identity.sanitize_ai_detection_task_id()(ai_task_id))}"

    def pipeline_ai_task_training_route(self, ai_task: dict[str, Any], config: dict[str, Any]) -> str:
        accessories_by_id = self.accessories.accessory_lookup_by_id()(config)
        selected_ids = self.accessories.canonical_pipeline_accessory_ids()(
            config, [str(item_id) for item_id in ai_task.get("selected_accessory_ids") or []]
        )
        for item_id in selected_ids:
            item = accessories_by_id.get(item_id) or {}
            if self.accessories.accessory_material_type()(item) == "text" or str(item.get("training_role") or "") == "detect_then_ocr":
                return "yolo_ocr"
        return "yolo"

    def sync_pipeline_ai_detection_tasks(
        self,
        tasks: list[dict[str, Any]],
        config: dict[str, Any],
        user: dict[str, Any] | None,
        target_user_id: str | None = None,
        *,
        ai_tasks: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Represent AI detection tasks as first-class pipeline tasks.

    These entries let the task pipeline show VLM-first tasks even before a YOLO
    model exists. They do not remove the original AI task; they keep a stable
    pipeline card linked to it so optimization/training state has one task home.
    """
        changed = False
        by_ai_task_id = {str(item.get("ai_task_id") or ""): item for item in tasks if item.get("ai_task_id")}
        by_id = {str(item.get("id") or ""): item for item in tasks}
        now = int(self.projection.now()())
        for ai_task in (ai_tasks if ai_tasks is not None else self.access.load_ai_detection_tasks()()):
            if str(ai_task.get("source") or "") == self.access.source():
                continue
            if not self.access.record_visible_to_user()(ai_task, user, target_user_id):
                continue
            ai_task_id = str(ai_task.get("id") or "")
            if not ai_task_id:
                continue
            accessory_ids = self.accessories.canonical_pipeline_accessory_ids()(
                config, [str(item_id) for item_id in ai_task.get("selected_accessory_ids") or []]
            )
            if not accessory_ids:
                continue
            route = self.projection.training_route()(ai_task, config)
            pipeline_id = self.projection.task_id()(ai_task_id)
            existing = by_ai_task_id.get(ai_task_id) or by_id.get(pipeline_id)
            payload = {
                "id": pipeline_id,
                "name": self.projection.clean_ai_detection_task_name()(ai_task.get("name"), "AI 检测任务"),
                "task_kind": "ai_optimization",
                "accessory_ids": accessory_ids,
                "accessory_counts": self.accessories.normalize_pipeline_accessory_counts()(config, accessory_ids, ai_task.get("required_accessory_counts")),
                "detection_method": "ai",
                "optimization_route": route,
                "stage": "library",
                "status": "completed",
                "progress": 100,
                "params": {"route": "ai", "recommended_train_mode": route},
                "auto_advance": True,
                "ai_task_id": ai_task_id,
                "ai_model_id": self.identity.ai_detection_task_model_id()(ai_task_id),
                "linked_view": "aiInspect",
                "job_note": "AI 检测任务已纳入任务流水线，可持续采集数据并自动优化 YOLO。",
                "last_error": "",
                "created_at": int(float(ai_task.get("created_at") or now)),
                "updated_at": int(float(ai_task.get("updated_at") or now)),
                "owner_user_id": str(ai_task.get("owner_user_id") or ""),
                "owner_username": str(ai_task.get("owner_username") or ""),
                "shared_with_user_ids": ai_task.get("shared_with_user_ids") if isinstance(ai_task.get("shared_with_user_ids"), list) else [],
            }
            if existing:
                existing_paused = bool(existing.get("pause_requested")) or str(existing.get("status") or "") == "stopped"
                keep = {
                    "stage": existing.get("stage") or payload["stage"],
                    "status": existing.get("status") or payload["status"],
                    "progress": existing.get("progress", payload["progress"]),
                    "auto_advance": False if existing_paused else True,
                    "pause_requested": existing.get("pause_requested", False),
                    "agent_mcp": existing.get("agent_mcp"),
                    "datasets": existing.get("datasets"),
                    "candidate_models": existing.get("candidate_models"),
                }
                next_task = {**existing, **payload, **{k: v for k, v in keep.items() if v is not None}}
                if next_task != existing:
                    existing.clear()
                    existing.update(next_task)
                    changed = True
            else:
                tasks.insert(0, payload)
                by_ai_task_id[ai_task_id] = payload
                by_id[pipeline_id] = payload
                changed = True
        return changed
