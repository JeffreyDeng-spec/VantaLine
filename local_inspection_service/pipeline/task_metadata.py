"""Pipeline method, count normalization and snapshot-only accessory reconstruction."""
import re
import time
from dataclasses import dataclass
from typing import Any
from .task_metadata_ports import MetadataPolicy, MetadataSnapshots

@dataclass(frozen=True)
class PipelineTaskMetadata:
    policy: MetadataPolicy
    snapshots: MetadataSnapshots

    def pipeline_task_model_id(self, task: dict[str, Any]) -> str:
        model_id = str(task.get("ai_model_id") or "").strip()
        if model_id:
            return model_id
        run_id = str(task.get("model_run_id") or task.get("training_task_id") or "").strip()
        if not run_id:
            return ""
        clean_run_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", re.sub(r"^trained_", "", run_id))
        method = self.policy.normalize_pipeline_detection_method()(str(task.get("detection_method") or ""))
        variant = "yolo_ocr" if method == "yolo_ocr" else "yolo"
        return f"trained_{clean_run_id}__{variant}"


    def normalize_pipeline_detection_method(self, value: str | None) -> str:
        method = str(value or "").strip().lower()
        if method in {"ai_detection", "ai_inspect", "gemini"}:
            return "ai"
        return method if method in self.policy.PIPELINE_DETECTION_METHODS() else "yolo_ocr"


    def pipeline_method_uses_training(self, method: str | None) -> bool:
        return self.policy.normalize_pipeline_detection_method()(method) in self.policy.PIPELINE_TRAINING_METHODS()


    def ensure_pipeline_task_accessory_objects(self, config: dict[str, Any], tasks: list[dict[str, Any]]) -> bool:
        accessories = config.setdefault("accessories", [])
        accessories_by_id = self.snapshots.accessory_lookup_by_id()(config)
        changed = False
        now = int(time.time())
        for task in tasks:
            raw_ids = [str(item_id) for item_id in task.get("accessory_ids") or [] if str(item_id).strip()]
            if not raw_ids:
                continue
            labels = self.snapshots.pipeline_task_label_snapshot()(task)
            raw_names = [str(item) for item in task.get("accessory_names") or [] if str(item).strip()]
            for index, item_id in enumerate(dict.fromkeys(raw_ids)):
                if item_id in accessories_by_id:
                    continue
                label = labels.get(item_id) or (raw_names[index] if index < len(raw_names) else "") or item_id
                item = {
                    "id": item_id,
                    "name": label,
                    "label": label,
                    "material_type": "object",
                    "status": "archived",
                    "source": "task_snapshot",
                    "task_snapshot_only": True,
                    "archived_from_task_id": str(task.get("id") or ""),
                    "source_files": [],
                    "original_source_files": [],
                    "normalized_assets": [],
                    "detection_route": str(task.get("detection_method") or "ai"),
                    "training_role": "detect_and_classify",
                    "created_at": int(task.get("created_at") or now),
                    "updated_at": now,
                    "owner_user_id": str(task.get("owner_user_id") or self.snapshots.LEGACY_OWNER_ID()),
                    "owner_username": str(task.get("owner_username") or self.snapshots.record_owner_username()(task)),
                }
                accessories.append(item)
                accessories_by_id[item_id] = item
                changed = True
        return changed


    def normalize_pipeline_accessory_counts(self, config: dict[str, Any], accessory_ids: list[str], raw_counts: Any = None) -> dict[str, int]:
        raw = raw_counts if isinstance(raw_counts, dict) else {}
        accessories_by_id = self.snapshots.accessory_lookup_by_id()(config)
        result: dict[str, int] = {}
        for item_id in accessory_ids:
            item = accessories_by_id.get(item_id)
            aliases = self.snapshots.accessory_id_aliases()(item) if item else [item_id]
            count_value = next((raw.get(alias) for alias in aliases if alias in raw), raw.get(item_id, 1))
            try:
                count = max(1, min(99, int(count_value or 1)))
            except (TypeError, ValueError):
                count = 1
            result[item_id] = count
        return result


    def normalize_pipeline_task_auto_advance_defaults(self, tasks: list[dict[str, Any]]) -> bool:
        changed = False
        for task in tasks:
            detection_method = self.policy.normalize_pipeline_detection_method()(
                str(task.get("detection_method") or (task.get("params") or {}).get("train_mode") or (task.get("params") or {}).get("route") or "")
            )
            if detection_method != "ai":
                continue
            if task.get("auto_advance") is not False:
                task["auto_advance"] = False
                task["updated_at"] = int(time.time())
                changed = True
        return changed
