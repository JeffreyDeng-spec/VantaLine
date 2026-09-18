"""Background HTTP adapters assembled once at their existing route position."""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse
from .background_query import BackgroundQuery
from .background_uploads import BackgroundUpload, BackgroundCapture

Record = dict[str, Any]


@dataclass(frozen=True)
class BackgroundRoutes:
    background_image: Callable[[str, str], FileResponse]
    training_background_sets: Callable[[str | None], Record]
    upload_training_background_set: Callable[[str, UploadFile], Awaitable[Record]]
    upload_ai_task_environment_background: Callable[[str, UploadFile], Awaitable[Record]]


def register(app: FastAPI, query: BackgroundQuery, upload: BackgroundUpload, capture: BackgroundCapture) -> BackgroundRoutes:
    @app.get("/api/backgrounds/{set_id}/{image_name}")
    def background_image(set_id: str, image_name: str) -> FileResponse:
        return query.background_image(set_id, image_name)

    @app.get("/api/training/background-sets")
    def training_background_sets(user_id: str | None = None) -> dict[str, Any]:
        return query.training_background_sets(user_id)

    @app.post("/api/training/background-sets")
    async def upload_training_background_set(
        name: str = Form(""),
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        return await upload.upload_training_background_set(name, file)

    @app.post("/api/ai/tasks/{task_id}/environment-background")
    async def upload_ai_task_environment_background(
        task_id: str,
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        return await capture.upload_ai_task_environment_background(task_id, file)

    return BackgroundRoutes(background_image, training_background_sets, upload_training_background_set, upload_ai_task_environment_background)
