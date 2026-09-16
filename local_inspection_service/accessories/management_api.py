"""Management HTTP contracts, registered at their original positions."""
from collections.abc import Callable, Awaitable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI, File, Form, UploadFile
from .creation import AccessoryCreation
from .confirmation import AccessoryConfirmation
from .removal import AccessoryRemoval


@dataclass(frozen=True)
class ManagementRoutes:
    add_accessory: Callable[..., Awaitable[dict[str, Any]]]
    preview_accessory: Callable[..., Awaitable[dict[str, Any]]]
    confirm_accessory: Callable[[str], dict[str, Any]]


def register_management_api(app: FastAPI, creation: AccessoryCreation,
                            confirmation: AccessoryConfirmation) -> ManagementRoutes:
    @app.post("/api/accessories")
    async def add_accessory(
        name: str = Form(...),
        class_id: int = Form(-1),
        material_type: str = Form("object"),
        material_alpha_policy: str = Form(""),
        training_role: str = Form("detect_and_classify"),
        pipeline_context: str = Form(""),
        paper_preset: str = Form("A4"),
        paper_width_mm: str = Form(""),
        paper_height_mm: str = Form(""),
        object_length_mm: str = Form(""),
        object_width_mm: str = Form(""),
        object_height_mm: str = Form(""),
        size_reference: str = Form(""),
        files: list[UploadFile] = File(default=[]),
    ) -> dict[str, Any]:
        return await creation.add_accessory(name, class_id, material_type, material_alpha_policy, training_role, pipeline_context, paper_preset, paper_width_mm, paper_height_mm, object_length_mm, object_width_mm, object_height_mm, size_reference, files)

    @app.post("/api/accessories/preview")
    async def preview_accessory(
        name: str = Form(...),
        material_type: str = Form("object"),
        material_alpha_policy: str = Form(""),
        training_role: str = Form("detect_and_classify"),
        pipeline_context: str = Form(""),
        paper_preset: str = Form("A4"),
        paper_width_mm: str = Form(""),
        paper_height_mm: str = Form(""),
        object_length_mm: str = Form(""),
        object_width_mm: str = Form(""),
        object_height_mm: str = Form(""),
        size_reference: str = Form(""),
        files: list[UploadFile] = File(default=[]),
    ) -> dict[str, Any]:
        return await creation.preview_accessory(name, material_type, material_alpha_policy, training_role, pipeline_context, paper_preset, paper_width_mm, paper_height_mm, object_length_mm, object_width_mm, object_height_mm, size_reference, files)

    @app.post("/api/accessories/confirm/{candidate_id}")
    def confirm_accessory(candidate_id: str) -> dict[str, Any]:
        return confirmation.confirm_accessory(candidate_id)

    return ManagementRoutes(add_accessory, preview_accessory, confirm_accessory)


def register_removal_api(app: FastAPI, removal: AccessoryRemoval) -> Callable[[str], dict[str, Any]]:
    @app.delete("/api/accessories/{accessory_id}")
    def delete_accessory(accessory_id: str) -> dict[str, Any]:
        return removal.delete_accessory(accessory_id)

    return delete_accessory
