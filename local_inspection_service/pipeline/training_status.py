"""Project training jobs into pipeline task status without owning persistence or locks."""
from pathlib import Path
from typing import Any, Callable

from .training_status_ports import TrainingJobLookup, TrainingStatusEffects


class PipelineTrainingStatus:
    def __init__(self, lookup: TrainingJobLookup, effects: TrainingStatusEffects):
        self.lookup = lookup
        self.effects = effects

    def linked_training_job(
        self,
        task: dict[str, Any],
        load_task: Callable[[Path], dict[str, Any] | None] | None = None,
    ) -> dict[str, Any] | None:
        job_id = task.get("training_task_id") if task.get("stage") == "training" else task.get("samples_task_id")
        if not job_id:
            return None
        job = (load_task or self.lookup.load())(self.lookup.path()(str(job_id)))
        # Remote refresh is handled by the watcher; local interruption projection
        # may still settle and persist an inactive local training task.
        return self.lookup.public()(job) if job else None

    def sync_pipeline_task(
        self,
        task: dict[str, Any],
        load_task: Callable[[Path], dict[str, Any] | None] | None = None,
    ) -> bool:
        if task.get("stage") not in {"samples", "training"}:
            return False
        if task.get("status") in {"completed", "failed", "stopped"}:
            return False
        job = self.lookup.linked()(task, load_task)
        if not job:
            return False
        changed = False
        status = str(job.get("status") or "")
        mapped = "completed" if status == "completed" else "failed" if status == "failed" else "stopped" if status == "stopped" else "running"
        progress = int(job.get("progress") or 0)
        if task.get("status") != mapped or task.get("progress") != progress:
            task["status"] = mapped
            task["progress"] = progress
            task["job_note"] = str(job.get("note") or "")[:200]
            if job.get("current_epoch") is not None:
                task["current_epoch"] = job.get("current_epoch")
                task["total_epochs"] = job.get("total_epochs") or job.get("epochs") or 0
            if task.get("agent_mcp"):
                orchestration = self.effects.orchestration()(task)
                if task.get("stage") == "samples":
                    self.effects.set_stage()(orchestration, "sample_generation", mapped, 100 if mapped in {"completed", "failed", "stopped"} else progress)
                    if mapped == "completed":
                        orchestration["state"] = "sample_generation_completed"
                elif task.get("stage") == "training":
                    self.effects.set_stage()(orchestration, "model_training", mapped, 100 if mapped in {"completed", "failed", "stopped"} else progress)
                    if mapped == "completed":
                        orchestration["state"] = "completed"
            changed = True
        return changed