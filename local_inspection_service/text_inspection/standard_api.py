"""HTTP adapters for standards, registered together in their original route order."""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from .standard_imports import StandardImports
from .standard_library import StandardLibrary
from .standard_edits import StandardEdits


@dataclass(frozen=True)
class StandardRoutes:
    import_text_inspection_standard: Callable[..., Awaitable[dict[str, Any]]]
    list_text_inspection_standards: Callable[..., dict[str, Any]]
    get_text_inspection_standard: Callable[..., dict[str, Any]]
    get_text_inspection_asset_content: Callable[..., Response]
    add_text_inspection_standard_asset: Callable[..., Awaitable[dict[str, Any]]]
    patch_text_inspection_asset: Callable[..., Awaitable[dict[str, Any]]]
    confirm_text_inspection_standard: Callable[..., dict[str, Any]]


def register(app: FastAPI, imports: StandardImports, library: StandardLibrary, edits: StandardEdits) -> StandardRoutes:
    @app.post("/api/text-inspection/standards/import")
    async def import_text_inspection_standard(
        file: UploadFile = File(...), name: str = Form(...),
        material_code: str = Form(...), version_label: str = Form(...),
    ) -> dict[str, Any]:
        return await imports.import_text_inspection_standard(file, name, material_code, version_label)

    @app.get("/api/text-inspection/standards")
    def list_text_inspection_standards() -> dict[str, Any]:
        return library.list_text_inspection_standards()

    @app.get("/api/text-inspection/standards/{standard_id}")
    def get_text_inspection_standard(standard_id: str) -> dict[str, Any]:
        return library.get_text_inspection_standard(standard_id)

    @app.get("/api/text-inspection/assets/{asset_id}/content")
    def get_text_inspection_asset_content(asset_id: str) -> Response:
        contents, mime = library.get_text_inspection_asset_content(asset_id)
        return Response(content=contents, media_type=mime, headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})

    @app.post("/api/text-inspection/standards/{standard_id}/assets")
    async def add_text_inspection_standard_asset(
        standard_id: str, file: UploadFile = File(...), expected_revision: str = Form(""),
    ) -> dict[str, Any]:
        return await edits.add_text_inspection_standard_asset(standard_id, file, expected_revision)

    @app.patch("/api/text-inspection/standards/{standard_id}/assets/{asset_id}")
    async def patch_text_inspection_asset(standard_id: str, asset_id: str, request: Request) -> dict[str, Any]:
        return await edits.patch_text_inspection_asset(standard_id, asset_id, lambda: request.json())

    @app.post("/api/text-inspection/standards/{standard_id}/confirm")
    def confirm_text_inspection_standard(standard_id: str) -> dict[str, Any]:
        return edits.confirm_text_inspection_standard(standard_id)

    return StandardRoutes(import_text_inspection_standard, list_text_inspection_standards,
                          get_text_inspection_standard, get_text_inspection_asset_content,
                          add_text_inspection_standard_asset, patch_text_inspection_asset,
                          confirm_text_inspection_standard)
