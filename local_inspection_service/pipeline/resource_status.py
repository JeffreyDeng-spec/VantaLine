"""Dataset and model availability projection for pipeline tasks."""
from pathlib import Path
import re
from typing import Any

from .resource_status_ports import PipelineResourceStatusLinks


class PipelineResourceStatus:
    def __init__(self, links: PipelineResourceStatusLinks):
        self.links = links

    def pipeline_task_dataset_status(self, task: dict[str, Any]) -> str:
        dataset_id = str(task.get("dataset_id") or task.get("samples_task_id") or "").strip()
        if not dataset_id:
            return "none"
        if str(task.get("dataset_status") or "") == "deleted":
            return "deleted"
        dataset_dir, _ = self.links.find_dataset()(dataset_id)
        if dataset_dir and dataset_dir.exists():
            return "available"
        if task.get("stage") == "samples" and str(task.get("status") or "") in {"running", "queued", "pending"}:
            return "pending"
        return "missing"

    def pipeline_task_model_status(
        self,
        task: dict[str, Any],
        *,
        ai_task_ids: set[str] | None = None,
        trained_model_specs: list[dict[str, Any]] | None = None,
    ) -> str:
        if str(task.get("model_status") or "") == "deleted":
            return "deleted"
        if str(task.get("detection_method") or "") == "ai" and str(task.get("ai_task_id") or "").strip():
            ai_task_id = str(task.get("ai_task_id") or "").strip()
            if ai_task_ids is not None:
                return "available" if ai_task_id in ai_task_ids else "missing"
            if any(str(item.get("id") or "") == ai_task_id for item in self.links.load_ai_tasks()()):
                return "available"
            return "missing"
        run_id = str(task.get("model_run_id") or task.get("training_task_id") or "").strip()
        if not run_id:
            return "none"
        clean_run_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", re.sub(r"^trained_", "", run_id))
        specs = trained_model_specs if trained_model_specs is not None else self.links.list_trained_specs()()
        spec = next((item for item in specs if str(item.get("run_id")) == clean_run_id), None)
        model_path = str((spec or {}).get("path") or "")
        if spec and model_path and Path(model_path).exists():
            return "available"
        if task.get("stage") == "training" and str(task.get("status") or "") in {"running", "queued", "pending"}:
            return "pending"
        return "missing"