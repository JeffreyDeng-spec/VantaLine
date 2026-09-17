"""Record terminal training candidates under the existing auto-optimization guard."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
import time
from typing import Any, Protocol

Record = dict[str, Any]


class StopCaptureForModel(Protocol):
    def __call__(self, state: Record, model_id: str, *, reason: str) -> bool: ...


@dataclass(frozen=True)
class CandidateTrainingRecords:
    load: Callable[[str], Record]
    save: Callable[[Record], Record]


class TrainingCandidateSync:
    def __init__(self, guard: Callable[[], AbstractContextManager], records: CandidateTrainingRecords,
                 clean_id: Callable[[Any], str], stop_capture: StopCaptureForModel):
        self.guard, self.records, self.clean_id, self.stop_capture = guard, records, clean_id, stop_capture

    def sync_auto_optimize_training_candidate_from_task(self,
        task: dict[str, Any],
        *,
        ai_task_id: str,
        model_id: str,
    ) -> None:
        clean_task_id = self.clean_id(ai_task_id)
        if not clean_task_id:
            return
        job_id = str(task.get("job_id") or task.get("task_id") or "").strip()
        if not job_id:
            return
        status = str(task.get("status") or "").strip()
        if status not in {"completed", "failed", "stopped", "cancelled", "canceled"}:
            return
        with self.guard():
            state = self.records.load(clean_task_id)
            candidates = [item for item in state.get("candidate_models") or [] if isinstance(item, dict)]
            existing = next((item for item in candidates if str(item.get("job_id") or "") == job_id), None)
            candidate = existing or {}
            candidate.update(
                {
                    "job_id": job_id,
                    "status": "completed" if status == "completed" else status,
                    "progress": int(task.get("progress") or 100),
                    "dataset_id": str(task.get("source_dataset_id") or task.get("dataset_id") or ""),
                    "model_id": model_id,
                    "note": str(task.get("note") or task.get("error") or "")[:240],
                    "updated_at": int(time.time()),
                    "training_parameters": {
                        "training_epochs": int(task.get("epochs") or task.get("total_epochs") or 0),
                        "training_image_size": int(task.get("image_size") or 0),
                    },
                }
            )
            if not existing:
                candidate["created_at"] = int(task.get("created_at") or time.time())
                candidates.insert(0, candidate)
            else:
                candidates = [candidate, *[item for item in candidates if item is not candidate]]
            state["candidate_models"] = candidates
            if task.get("pipeline_task_name") and not state.get("task_name"):
                state["task_name"] = str(task.get("pipeline_task_name") or "")
            if task.get("selected_accessory_ids") and not state.get("selected_accessory_ids"):
                state["selected_accessory_ids"] = task.get("selected_accessory_ids") or []
            if status == "completed":
                self.stop_capture(state, model_id, reason="completed_model_ready")
            self.records.save(state)
