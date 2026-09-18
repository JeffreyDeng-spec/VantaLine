"""Jobs HTTP adapters; image controls retain their existing delegated permission checks."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI
from ..schemas.training import TrainingTaskUpdateRequest
from .jobs_query import TrainingJobsQuery
from .task_mutations import TrainingTaskMutations

Record = dict[str, Any]


@dataclass(frozen=True)
class ImageJobActions:
    job: Callable[[str, str], Record]
    candidate: Callable[[str, str], Record]


@dataclass(frozen=True)
class JobsRoutes:
    image_jobs: Callable[[str | None], Record]
    image_job: Callable[[str], Record]
    update_training_task_endpoint: Callable[[str, TrainingTaskUpdateRequest], Record]
    delete_training_task_endpoint: Callable[[str], Record]
    stop_image_job: Callable[[str], Record]
    retry_image_job: Callable[[str], Record]
    delete_image_job: Callable[[str], Record]
    stop_image_job_candidate: Callable[[str], Record]
    delete_image_job_candidate: Callable[[str], Record]


def register(app: FastAPI, query: TrainingJobsQuery, mutations: TrainingTaskMutations, actions: ImageJobActions) -> JobsRoutes:
    @app.get("/api/image-jobs")
    def image_jobs(user_id: str | None = None) -> dict[str, Any]:
        return query.image_jobs(user_id)

    @app.get("/api/image-jobs/{job_id}")
    def image_job(job_id: str) -> dict[str, Any]:
        return query.image_job(job_id)

    @app.patch("/api/training/tasks/{job_id}")
    def update_training_task_endpoint(job_id: str, request: TrainingTaskUpdateRequest) -> dict[str, Any]:
        return mutations.update_training_task_endpoint(job_id, request)

    @app.delete("/api/training/tasks/{job_id}")
    def delete_training_task_endpoint(job_id: str) -> dict[str, Any]:
        return mutations.delete_training_task_endpoint(job_id)

    @app.post("/api/image-jobs/{job_id}/stop")
    def stop_image_job(job_id: str) -> dict[str, Any]:
        return actions.job(job_id, "stop")

    @app.post("/api/image-jobs/{job_id}/retry")
    def retry_image_job(job_id: str) -> dict[str, Any]:
        return actions.job(job_id, "retry")

    @app.delete("/api/image-jobs/{job_id}")
    def delete_image_job(job_id: str) -> dict[str, Any]:
        return actions.job(job_id, "delete")

    @app.post("/api/image-job-candidates/{candidate_id}/stop")
    def stop_image_job_candidate(candidate_id: str) -> dict[str, Any]:
        return actions.candidate(candidate_id, "stop")

    @app.delete("/api/image-job-candidates/{candidate_id}")
    def delete_image_job_candidate(candidate_id: str) -> dict[str, Any]:
        return actions.candidate(candidate_id, "delete")

    return JobsRoutes(image_jobs, image_job, update_training_task_endpoint, delete_training_task_endpoint, stop_image_job, retry_image_job, delete_image_job, stop_image_job_candidate, delete_image_job_candidate)
