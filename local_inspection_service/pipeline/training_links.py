"""Resolve the first pipeline record linked to a training run."""
from collections.abc import Callable
import re
from typing import Any

Record = dict[str, Any]


class TrainingLinks:
    def __init__(self, tasks: Callable[[], list[Record]], name: Callable[[Record], str]):
        self.tasks, self.name = tasks, name

    def pipeline_task_link_for_training_run(self, run_id: str, tasks: list[dict[str, Any]] | None = None) -> dict[str, str]:
        clean_run_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", re.sub(r"^trained_", "", str(run_id or "")))
        if not clean_run_id:
            return {}
        for task in (tasks if tasks is not None else self.tasks()):
            linked_ids = {
                str(task.get("model_run_id") or ""),
                str(task.get("training_task_id") or ""),
                re.sub(r"^trained_", "", str(task.get("ai_model_id") or "")),
            }
            if clean_run_id not in linked_ids:
                continue
            return {
                "pipeline_task_id": str(task.get("id") or ""),
                "pipeline_task_name": self.name(task),
            }
        return {}

class PipelineTrainedModelLink:
    """Link the first visible trained model without owning task locks or storage."""

    def __init__(self, catalog: Callable[[], Callable[[], list[Record]]]):
        self.catalog = catalog

    def link_pipeline_trained_model(self, task: dict[str, Any]) -> dict[str, Any] | None:
        """Link the freshly trained model to the pipeline task so the model library and\n    detection workbench can use it immediately (transfer-back deployment path)."""
        run_id = str(task.get("training_task_id") or "").strip()
        if not run_id:
            return None
        spec = next((item for item in self.catalog()() if str(item.get("run_id")) == run_id), None)
        if not spec:
            # The model artifact may still be importing (e.g. Windows worker transfer);
            # fall back to the conventional spec id so the UI shows the linkage.
            variant = str((task.get("params") or {}).get("train_mode") or task.get("detection_method") or "yolo")
            task.update(
                {
                    "model_run_id": run_id,
                    "ai_model_id": f"trained_{run_id}__{variant}",
                    "linked_view": "inspect",
                }
            )
            return None
        task.update(
            {
                "model_run_id": run_id,
                "ai_model_id": str(spec.get("id") or ""),
                "model_label": str(spec.get("label") or ""),
                "model_exists": bool(spec.get("path")),
                "linked_view": "inspect",
            }
        )
        return spec