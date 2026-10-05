"""Create/update AI detection tasks and activate their pipeline representation."""
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any
from .ai_activation_ports import ActivationPolicy, ActivationStorage

@dataclass(frozen=True)
class PipelineAiActivation:
    policy: ActivationPolicy
    storage: ActivationStorage

    def upsert_pipeline_ai_detection_task(self, task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        accessory_ids = self.policy.canonical_pipeline_accessory_ids()(config, [str(item_id) for item_id in task.get("accessory_ids") or []])
        if not accessory_ids:
            raise self.policy.HTTPException()(status_code=400, detail="AI 检测任务还没有选择配件")
        accessories_by_id = self.policy.accessory_lookup_by_id()(config)
        counts = self.policy.normalize_pipeline_accessory_counts()(config, accessory_ids, task.get("accessory_counts"))
        labels = {item_id: str(accessories_by_id[item_id].get("name") or item_id) for item_id in accessory_ids}
        payload = {
            "name": self.policy.clean_ai_detection_task_name()(task.get("name"), "流水线 AI 检测任务"),
            "selected_accessory_ids": accessory_ids,
            "required_accessory_counts": counts,
            "accessory_labels": labels,
            "source": "pipeline",
        }
        task_id = self.policy.sanitize_ai_detection_task_id()(task.get("ai_task_id"))
        now = time.time()
        owner_fields = {
            "owner_user_id": str(task.get("owner_user_id") or ""),
            "owner_username": str(task.get("owner_username") or ""),
            "shared_with_user_ids": task.get("shared_with_user_ids") if isinstance(task.get("shared_with_user_ids"), list) else [],
        }
        if not owner_fields["owner_user_id"]:
            owner_fields = self.storage.current_owner_fields()()
        existing = self.storage.find_ai_detection_task()(task_id) if task_id else None
        if existing:
            updated = {**existing, **payload, "id": task_id, "created_at": float(existing.get("created_at") or now), "updated_at": now}
            if owner_fields:
                updated["owner_user_id"] = updated.get("owner_user_id") or owner_fields["owner_user_id"]
                updated["owner_username"] = updated.get("owner_username") or owner_fields.get("owner_username", "")
            self.storage.save_ai_detection_task()(updated)
            return self.storage.serialize_ai_detection_task()(updated, config)
        created = {"id": f"aitask_{uuid.uuid4().hex[:10]}", "created_at": now, "updated_at": now, **owner_fields, **payload}
        self.storage.save_ai_detection_task()(created, prepend=True)
        return self.storage.serialize_ai_detection_task()(created, config)


    def activate_pipeline_ai_detection_task(self, task: dict[str, Any], config: dict[str, Any]) -> bool:
        detection_method = self.policy.normalize_pipeline_detection_method()(str(task.get("detection_method") or (task.get("params") or {}).get("route") or ""))
        if detection_method != "ai":
            return False
        if not task.get("accessory_ids"):
            return False
        ai_task = self.storage.upsert_pipeline_ai_detection_task()(task, config)
        params = dict(task.get("params") or {})
        params["route"] = "ai"
        params.pop("train_mode", None)
        before = json.dumps(task, sort_keys=True, ensure_ascii=False, default=str)
        task.update(
            {
                "detection_method": "ai",
                "stage": "library",
                "status": "completed",
                "progress": 100,
                "params": params,
                "ai_task_id": ai_task["id"],
                "ai_model_id": ai_task["model_id"],
                "linked_view": "aiInspect",
                "last_error": "",
                "job_note": "AI 检测任务已创建，可在检测中心直接使用。",
                "updated_at": int(time.time()),
            }
        )
        after = json.dumps(task, sort_keys=True, ensure_ascii=False, default=str)
        return before != after
