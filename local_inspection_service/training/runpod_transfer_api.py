"""RunPod transfer routes at their original position; streaming remains lazy in the store."""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from .runpod_transfer import RunPodTrainingTransfer

Record = dict[str, Any]


@dataclass(frozen=True)
class TransferRoutes:
    download_runpod_training_dataset: Callable[[str, str], FileResponse]
    upload_runpod_training_artifact: Callable[[str, str, Request], Awaitable[Record]]


def register(app: FastAPI, transfer: RunPodTrainingTransfer) -> TransferRoutes:
    @app.get("/api/training/runpod/datasets/{job_id}/{token}/dataset.zip")
    def download_runpod_training_dataset(job_id: str, token: str) -> FileResponse:
        return transfer.download_runpod_training_dataset(job_id, token)

    @app.put("/api/training/runpod/artifacts/{job_id}/{token}/run.zip")
    async def upload_runpod_training_artifact(job_id: str, token: str, request: Request) -> dict[str, Any]:
        return await transfer.upload_runpod_training_artifact(job_id, token, request)

    return TransferRoutes(download_runpod_training_dataset, upload_runpod_training_artifact)
