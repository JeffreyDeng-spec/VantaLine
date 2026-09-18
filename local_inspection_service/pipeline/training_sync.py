"""Propagate terminal training outcomes to pipeline records, then candidate state."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
import time
from typing import Any, Protocol

Record = dict[str, Any]


class TrainingCandidateSink(Protocol):
    def __call__(self, task: Record, *, ai_task_id: str, model_id: str) -> None: ...


@dataclass(frozen=True)
class PipelineTrainingRecords:
    load: Callable[[str], Record | None]
    save: Callable[[Record], Record | None]


@dataclass(frozen=True)
class PipelineTrainingModels:
    resolve: Callable[[Record, str], str]
    link: Callable[[Record], Record | None]


class PipelineTrainingSync:
    def __init__(self, guard: Callable[[], AbstractContextManager], records: PipelineTrainingRecords,
                 models: PipelineTrainingModels, normalize_method: Callable[[], Callable[[str | None], str]],
                 clean_id: Callable[[], Callable[[Any], str]], sync_candidate: TrainingCandidateSink):
        self.guard, self.records, self.models = guard, records, models
        self.normalize_method, self.clean_id, self.sync_candidate = normalize_method, clean_id, sync_candidate

    def auto_optimize_task_id_from_pipeline_task(self, pipeline_task_id: str, pipeline_task: dict[str, Any] | None = None) -> str:
        if pipeline_task:
            direct = self.clean_id()(pipeline_task.get("ai_task_id") or "")
            if direct:
                return direct
        clean_pipeline_id = str(pipeline_task_id or "").strip()
        prefix = "pipe_ai_"
        if clean_pipeline_id.startswith(prefix):
            return self.clean_id()(clean_pipeline_id[len(prefix):])
        return ""

    def sync_pipeline_training_state_from_task(self, task: dict[str, Any]) -> None:
        job_id = str(task.get("job_id") or task.get("task_id") or "").strip()
        pipeline_task_id = str(task.get("pipeline_task_id") or "").strip()
        if not job_id or not pipeline_task_id:
            return
        status = str(task.get("status") or "").strip()
        if status not in {"completed", "failed", "stopped", "cancelled", "canceled"}:
            return
        model_id = self.models.resolve(task, job_id)
        with self.guard():
            pipeline_task = self.records.load(pipeline_task_id)
            ai_task_id = self.auto_optimize_task_id_from_pipeline_task(pipeline_task_id, pipeline_task)
            if pipeline_task:
                method = self.normalize_method()(
                    str(
                        pipeline_task.get("detection_method")
                        or (pipeline_task.get("params") or {}).get("train_mode")
                        or (pipeline_task.get("params") or {}).get("route")
                        or ""
                    )
                )
                if method in {"yolo", "yolo_ocr"}:
                    if status == "completed":
                        pipeline_task.update(
                            {
                                "stage": "library",
                                "status": "completed",
                                "progress": 100,
                                "training_task_id": job_id,
                                "model_run_id": job_id,
                                "ai_model_id": model_id,
                                "model_status": "available",
                                "model_exists": True,
                                "linked_view": "inspect",
                                "last_error": "",
                                "job_note": str(task.get("note") or "模型训练已完成。")[:200],
                            }
                        )
                        self.models.link(pipeline_task)
                    else:
                        pipeline_task.update(
                            {
                                "stage": "training",
                                "status": "failed" if status == "failed" else "stopped",
                                "progress": 100,
                                "training_task_id": job_id,
                                "last_error": str(task.get("error") or task.get("note") or "")[:240],
                                "job_note": str(task.get("note") or "")[:200],
                            }
                        )
                    pipeline_task["updated_at"] = int(time.time())
                    self.records.save(pipeline_task)
                elif method == "ai" and status == "completed":
                    pipeline_task.update(
                        {
                            "stage": "library",
                            "status": "completed",
                            "progress": 100,
                            "last_error": "",
                            "job_note": "YOLO 接管模型已训练完成，自动优化采集已停止。",
                            "updated_at": int(time.time()),
                        }
                    )
                    self.records.save(pipeline_task)
        if ai_task_id:
            self.sync_candidate(task, ai_task_id=ai_task_id, model_id=model_id)
