"""Training task edit/delete orchestration preserving mutation and persistence order."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from fastapi import HTTPException
from ..schemas.training import TrainingTaskUpdateRequest
from .jobs_ports import ListJobs
from .task_lifecycle import RequireTrainingAccess

Record = dict[str, Any]


@dataclass(frozen=True)
class TaskMutationRecords:
    find: Callable[[str], Record | None]
    save: Callable[[Record], None]
    public: Callable[[Record], Record]
    delete: Callable[[str, Record], Record | None]
    list: ListJobs


class TrainingTaskMutations:
    def __init__(self, current: Callable[[], Record], require: RequireTrainingAccess,
                 records: TaskMutationRecords, clock: Callable[[], float]):
        self.current, self.require, self.records, self.clock = current, require, records, clock

    def update_training_task_endpoint(self, job_id: str, request: TrainingTaskUpdateRequest) -> dict[str, Any]:
        user = self.current()
        task = self.records.find(job_id)
        if not task:
            raise HTTPException(status_code=404, detail="Training task not found")
        self.require(task, user, write=True)
        if request.label is not None:
            task["label"] = request.label.strip() or task.get("label") or "训练任务"
            task["candidate_name"] = task["label"]
        if request.note is not None:
            task["note"] = request.note.strip()
        task["updated_at"] = int(self.clock())
        self.records.save(task)
        return self.records.public(task)

    def delete_training_task_endpoint(self, job_id: str) -> dict[str, Any]:
        user = self.current()
        self.records.delete(job_id, user)
        return {"status": "deleted", "job_id": job_id, "items": self.records.list(user=user)}
