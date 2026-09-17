"""Legacy incoming HTTP adapters in the original two route groups."""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse
from ..schemas.text_inspection import IncomingTextRulesRequest, IncomingTextReviewRequest
from .incoming_catalog import IncomingCatalog
from .incoming_execution import IncomingExecution
from .incoming_reviews import IncomingReviews


@dataclass(frozen=True)
class CatalogRoutes:
    get_incoming_text_task: Callable[..., dict[str, Any]]
    get_incoming_text_reference_asset: Callable[..., FileResponse]
    create_incoming_text_reference: Callable[..., Awaitable[dict[str, Any]]]
    update_incoming_text_reference_rules: Callable[..., dict[str, Any]]
    clone_incoming_text_reference: Callable[..., dict[str, Any]]


def register_catalog(app: FastAPI, catalog: IncomingCatalog) -> CatalogRoutes:
    @app.get("/api/incoming-text/tasks/{task_id}")
    def get_incoming_text_task(task_id: str) -> dict[str, Any]:
        return catalog.get_incoming_text_task(task_id)

    @app.get("/api/incoming-text/references/{reference_id}/asset/{asset_kind}")
    def get_incoming_text_reference_asset(reference_id: str, asset_kind: str) -> FileResponse:
        return FileResponse(catalog.get_incoming_text_reference_asset(reference_id, asset_kind))

    @app.post("/api/incoming-text/tasks/{task_id}/references")
    async def create_incoming_text_reference(
        task_id: str,
        file: UploadFile = File(...),
        version_label: str = Form(...),
    ) -> dict[str, Any]:
        return await catalog.create_incoming_text_reference(task_id, file, version_label)

    @app.put("/api/incoming-text/references/{reference_id}/rules")
    def update_incoming_text_reference_rules(reference_id: str, request: IncomingTextRulesRequest) -> dict[str, Any]:
        return catalog.update_incoming_text_reference_rules(reference_id, request)

    @app.post("/api/incoming-text/references/{reference_id}/clone")
    def clone_incoming_text_reference(reference_id: str, version_label: str = Form(...)) -> dict[str, Any]:
        return catalog.clone_incoming_text_reference(reference_id, version_label)

    return CatalogRoutes(get_incoming_text_task, get_incoming_text_reference_asset, create_incoming_text_reference, update_incoming_text_reference_rules, clone_incoming_text_reference)


@dataclass(frozen=True)
class InspectionRoutes:
    inspect_incoming_text: Callable[..., Awaitable[dict[str, Any]]]
    get_incoming_text_inspection_evidence: Callable[..., FileResponse]
    review_incoming_text_inspection: Callable[..., dict[str, Any]]
    list_incoming_text_inspections: Callable[..., dict[str, Any]]


def register_inspections(app: FastAPI, execution: IncomingExecution, reviews: IncomingReviews) -> InspectionRoutes:
    @app.post("/api/incoming-text/tasks/{task_id}/inspect")
    async def inspect_incoming_text(
        task_id: str,
        file: UploadFile = File(...),
        capture_id: str = Form(...),
    ) -> dict[str, Any]:
        return await execution.inspect_incoming_text(task_id, file, capture_id)

    @app.get("/api/incoming-text/inspections/{inspection_id}/evidence/{asset_kind}")
    def get_incoming_text_inspection_evidence(inspection_id: str, asset_kind: str) -> FileResponse:
        return FileResponse(reviews.get_incoming_text_inspection_evidence(inspection_id, asset_kind))

    @app.post("/api/incoming-text/inspections/{inspection_id}/review")
    def review_incoming_text_inspection(inspection_id: str, request: IncomingTextReviewRequest) -> dict[str, Any]:
        return reviews.review_incoming_text_inspection(inspection_id, request)

    @app.get("/api/incoming-text/inspections")
    def list_incoming_text_inspections(
        task_id: str | None = None,
        material_code: str | None = None,
        decision: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        return reviews.list_incoming_text_inspections(task_id, material_code, decision, limit)

    return InspectionRoutes(inspect_incoming_text, get_incoming_text_inspection_evidence, review_incoming_text_inspection, list_incoming_text_inspections)
