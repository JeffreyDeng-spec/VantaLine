"""Ordered training/image job catalog and permission-first single-job projection."""
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any
from fastapi import HTTPException
from .jobs_ports import ListJobs, RefreshTrainingJob
from .task_lifecycle import RequireTrainingAccess

Record = dict[str, Any]


@dataclass(frozen=True)
class JobsReadAccess:
    current: Callable[[], Record]
    is_admin: Callable[[Record], bool]
    require: RequireTrainingAccess


@dataclass(frozen=True)
class JobsTraining:
    find: Callable[[str], Record | None]
    uses_worker: Callable[[Record], bool]
    public: Callable[[Record], Record]
    refresh: RefreshTrainingJob


class TrainingJobsQuery:
    def __init__(self, access: JobsReadAccess, training: JobsTraining, training_list: ListJobs,
                 image_list: ListJobs, active: Callable[[], Collection[str]]):
        self.access, self.training = access, training
        self.training_list, self.image_list, self.active = training_list, image_list, active

    def image_jobs(self, user_id: str | None = None) -> dict[str, Any]:
        user = self.access.current()
        target_user_id = user_id if self.access.is_admin(user) else None
        jobs = self.training_list(user=user, target_user_id=target_user_id) + self.image_list(user=user, target_user_id=target_user_id)
        return {
            "items": jobs,
            "active": [job for job in jobs if job.get("status") in self.active()],
            "completed": [job for job in jobs if job.get("status") == "completed"],
        }

    def image_job(self, job_id: str) -> dict[str, Any]:
        user = self.access.current()
        training_task = self.training.find(job_id)
        if training_task:
            self.access.require(training_task, user)
            if self.training.uses_worker(training_task):
                return self.training.refresh(training_task, allow_remote_refresh=False)
            return self.training.public(training_task)
        for job in self.image_list(user=user):
            if job.get("job_id") == job_id or job.get("task_id") == job_id:
                return job
        raise HTTPException(status_code=404, detail="Image job not found")
