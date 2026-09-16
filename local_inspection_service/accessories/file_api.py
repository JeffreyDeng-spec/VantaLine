"""Original file-edit HTTP contracts with explicit service dispatch."""
from collections.abc import Callable, Awaitable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI, File, UploadFile
from ..schemas.accessories import AccessoryTextCropRequest, AccessoryAiReferenceRequest, AccessoryFileDeleteRequest
from .files import AccessoryFiles


@dataclass(frozen=True)
class FileRoutes:
    add_accessory_files: Callable[..., Awaitable[dict[str, Any]]]
    crop_accessory_text_image: Callable[[str, AccessoryTextCropRequest], dict[str, Any]]
    set_accessory_ai_reference: Callable[[str, AccessoryAiReferenceRequest], dict[str, Any]]
    delete_accessory_file: Callable[[str, AccessoryFileDeleteRequest], dict[str, Any]]


def register_file_api(app: FastAPI, service: AccessoryFiles) -> FileRoutes:
    @app.post("/api/accessories/{accessory_id}/files")
    async def add_accessory_files(accessory_id: str, files: list[UploadFile] = File(default=[])) -> dict[str, Any]:
        return await service.add_accessory_files(accessory_id, files)

    @app.post("/api/accessories/{accessory_id}/text-crop")
    def crop_accessory_text_image(accessory_id: str, request: AccessoryTextCropRequest) -> dict[str, Any]:
        return service.crop_accessory_text_image(accessory_id, request)

    @app.post("/api/accessories/{accessory_id}/ai-reference")
    def set_accessory_ai_reference(accessory_id: str, request: AccessoryAiReferenceRequest) -> dict[str, Any]:
        return service.set_accessory_ai_reference(accessory_id, request)

    @app.delete("/api/accessories/{accessory_id}/files")
    def delete_accessory_file(accessory_id: str, request: AccessoryFileDeleteRequest) -> dict[str, Any]:
        return service.delete_accessory_file(accessory_id, request)

    return FileRoutes(add_accessory_files, crop_accessory_text_image, set_accessory_ai_reference, delete_accessory_file)
