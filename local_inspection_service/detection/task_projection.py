"""Detection task HTTP projections and request normalization through narrow ports."""
from collections.abc import Callable
from typing import Any
from fastapi import HTTPException
from ..schemas.detection import AiDetectionTaskRequest
from .task_identity import sanitize_ai_detection_task_id, clean_ai_detection_task_name, normalize_ai_detection_task_counts

Record = dict[str, Any]


class TaskProjection:
    def __init__(self, lookup: Callable[[Record], dict[str, Record]], audit: Callable[[Record], Record],
                 background: Callable[[str], tuple[str, Record]], public_path: Callable[[Record], Record],
                 model_id: Callable[[str], str]):
        self.lookup, self.audit, self.background = lookup, audit, background
        self.public_path, self.model_id = public_path, model_id

    def serialize_ai_detection_task(self, task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        audit = self.audit(task)
        counts = normalize_ai_detection_task_counts(task.get("required_accessory_counts") or {})
        selected_ids = [str(item_id) for item_id in task.get("selected_accessory_ids") or counts.keys() if str(item_id) in counts]
        if not selected_ids:
            selected_ids = list(counts.keys())
        accessories_by_id = self.lookup(config)
        saved_labels = {str(k): str(v) for k, v in (task.get("accessory_labels") or {}).items()}
        accessory_names: list[str] = []
        accessory_labels: dict[str, str] = {}
        missing_accessory_ids: list[str] = []
        for item_id in selected_ids:
            item = accessories_by_id.get(item_id)
            label = str((item or {}).get("name") or (item or {}).get("label") or saved_labels.get(item_id) or item_id)
            accessory_names.append(label)
            accessory_labels[item_id] = label
            if item is None:
                missing_accessory_ids.append(item_id)
        fallback_name = " + ".join(accessory_names) if accessory_names else "AI 检测任务"
        task_id = sanitize_ai_detection_task_id(task.get("id"))
        payload = {
            "id": task_id,
            "name": clean_ai_detection_task_name(task.get("name"), fallback_name),
            "model_id": self.model_id(task_id),
            "selected_accessory_ids": selected_ids,
            "required_accessory_counts": {item_id: counts.get(item_id, 1) for item_id in selected_ids},
            "accessory_names": accessory_names,
            "accessory_labels": accessory_labels,
            "accessory_count": len(selected_ids),
            "missing_accessory_ids": missing_accessory_ids,
            "created_at": audit["created_at"],
            "updated_at": audit["updated_at"],
            "source": str(task.get("source") or "ai_detection_workbench"),
            "owner_user_id": audit["owner_user_id"],
            "owner_username": audit["owner_username"],
        }
        background_set_id, environment_background = self.background(task_id)
        if background_set_id:
            payload["background_set_id"] = background_set_id
            payload["environment_background"] = self.public_path(environment_background)
        return payload

    def ai_detection_task_payload_from_request(self, request: AiDetectionTaskRequest, config: dict[str, Any]) -> dict[str, Any]:
        raw_counts: dict[str, Any] = {}
        for item_id, count in (request.required_accessory_counts or {}).items():
            raw_counts[str(item_id)] = count
        for item in request.accessories or []:
            raw_counts[str(item.accessory_id)] = item.required_count
        counts = normalize_ai_detection_task_counts(raw_counts)
        if not counts:
            raise HTTPException(status_code=400, detail="AI detection task requires at least one accessory")
        accessories_by_id = self.lookup(config)
        unknown = [item_id for item_id in counts if item_id not in accessories_by_id]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown accessory IDs: {unknown}")
        accessory_labels = {
            item_id: str(accessories_by_id[item_id].get("name") or accessories_by_id[item_id].get("label") or item_id)
            for item_id in counts
        }
        fallback_name = " + ".join(accessory_labels.values())
        return {
            "name": clean_ai_detection_task_name(request.name, fallback_name),
            "selected_accessory_ids": list(counts.keys()),
            "required_accessory_counts": counts,
            "accessory_labels": accessory_labels,
            "source": "ai_detection_workbench",
        }

