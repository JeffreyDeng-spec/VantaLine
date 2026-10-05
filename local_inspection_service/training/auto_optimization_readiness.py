"""Model readiness and capture policy, independent of HTTP and persistence ownership."""
from dataclasses import dataclass
import time
from typing import Any

from .auto_optimization_readiness_ports import AutoOptimizationReadinessPorts


@dataclass(frozen=True)
class AutoOptimizationReadiness:
    ports: AutoOptimizationReadinessPorts

    def auto_optimize_phase_name(self, state: dict[str, Any]) -> str:
        settings = state.get("settings") if isinstance(state.get("settings"), dict) else {}
        if state.get("active_model_id") and settings.get("serving_mode") == "promoted_yolo":
            return "promoted"
        if not settings.get("enabled"):
            return "paused"
        if state.get("candidate_models"):
            return "shadow_compare"
        if state.get("datasets"):
            return "training_candidate"
        samples = state.get("samples") if isinstance(state.get("samples"), list) else []
        if any((sample or {}).get("label_status") in {"trainable", "trainable_bbox_only"} for sample in samples if isinstance(sample, dict)):
            return "weak_labeling"
        return "capture"

    def auto_optimize_completed_model_id(self, state: dict[str, Any]) -> str:
        active_model_id = str(state.get("active_model_id") or "").strip()
        settings = state.get("settings") if isinstance(state.get("settings"), dict) else {}
        if active_model_id and settings.get("serving_mode") == "promoted_yolo":
            return active_model_id
        for candidate in state.get("candidate_models") or []:
            if not isinstance(candidate, dict):
                continue
            model_id = str(candidate.get("model_id") or "").strip()
            if not model_id:
                continue
            task = self.ports.find_training_task()(str(candidate.get("job_id") or ""))
            status = str((task or {}).get("status") or candidate.get("status") or "").strip()
            if status == "completed":
                return model_id
        pipeline_model_id = self.ports.auto_optimize_linked_pipeline_model_id()(state)
        if pipeline_model_id:
            return pipeline_model_id
        return ""

    def auto_optimize_linked_pipeline_model_id(self, state: dict[str, Any]) -> str:
        config = self.ports.load_config()()
        selected_ids = self.ports.canonical_pipeline_accessory_ids()(config, [str(item_id) for item_id in state.get("selected_accessory_ids") or []])
        if not selected_ids:
            return ""
        expected_counts = self.ports.normalize_pipeline_accessory_counts()(config, selected_ids, state.get("required_accessory_counts"))
        expected_key = sorted(selected_ids)
        owner_id = str(state.get("owner_user_id") or "").strip()
        newest_match: tuple[int, str] | None = None
        for task in self.ports.load_pipeline_tasks()():
            if not isinstance(task, dict):
                continue
            task_owner_id = str(task.get("owner_user_id") or "").strip()
            if owner_id and task_owner_id and task_owner_id != owner_id:
                continue
            if str(task.get("stage") or "") != "library" or str(task.get("status") or "") not in {"completed", "已上线"}:
                continue
            if self.ports.normalize_pipeline_detection_method()(str(task.get("detection_method") or "")) not in {"yolo", "yolo_ocr"}:
                continue
            task_ids = self.ports.canonical_pipeline_accessory_ids()(config, [str(item_id) for item_id in task.get("accessory_ids") or []])
            if sorted(task_ids) != expected_key:
                continue
            task_counts = self.ports.normalize_pipeline_accessory_counts()(config, task_ids, task.get("accessory_counts"))
            if {item_id: int(task_counts.get(item_id, 1)) for item_id in task_ids} != {
                item_id: int(expected_counts.get(item_id, 1)) for item_id in selected_ids
            }:
                continue
            if self.ports.pipeline_task_model_status()(task) != "available":
                continue
            model_id = self.ports.pipeline_task_model_id()(task)
            if not model_id:
                continue
            updated_at = int(task.get("updated_at") or task.get("created_at") or 0)
            if newest_match is None or updated_at > newest_match[0]:
                newest_match = (updated_at, model_id)
        return newest_match[1] if newest_match else ""

    def auto_optimize_stop_capture_for_model_locked(self, state: dict[str, Any], model_id: str, *, reason: str) -> bool:
        if not model_id:
            return False
        settings = {**self.ports.default_auto_optimize_settings()(), **(state.get("settings") if isinstance(state.get("settings"), dict) else {})}
        changed = False
        if state.get("active_model_id") != model_id and settings.get("auto_promote", True):
            state["active_model_id"] = model_id
            settings["serving_mode"] = "promoted_yolo"
            state["last_promotion"] = {
                "model_id": model_id,
                "agreement": state.get("last_promotion", {}).get("agreement") if isinstance(state.get("last_promotion"), dict) else None,
                "sample_count": state.get("last_promotion", {}).get("sample_count") if isinstance(state.get("last_promotion"), dict) else 0,
                "promoted_at": int(time.time()),
                "source": reason,
            }
            changed = True
        if settings.get("enabled"):
            settings["enabled"] = False
            state["capture_stopped_at"] = int(time.time())
            state["capture_stop_reason"] = reason
            changed = True
        if changed:
            state["settings"] = settings
        return changed

    def auto_optimize_capture_enabled(self, state: dict[str, Any]) -> bool:
        settings = state.get("settings") if isinstance(state.get("settings"), dict) else {}
        if not settings.get("enabled"):
            return False
        if self.ports.auto_optimize_completed_model_id()(state):
            return False
        return True
