"""Comparison, retained manual tombstones and review HTTP adapters."""
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from typing import Any
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from .comparison_submission import ComparisonSubmission
from .inspection_reviews import InspectionReviews
from .inspection_ports import InspectionAccess


@dataclass(frozen=True)
class InspectionRoutes:
    compare_text_inspection_label: Callable[..., Awaitable[dict[str, Any]]]
    get_text_inspection_v2_evidence: Callable[..., Response]
    create_text_manual_session: Callable[..., Awaitable[dict[str, Any]]]
    inspect_text_manual_page: Callable[..., Awaitable[dict[str, Any]]]
    complete_text_manual_session: Callable[..., dict[str, Any]]
    review_text_inspection_v2: Callable[..., Awaitable[dict[str, Any]]]


def register(app: FastAPI, comparison: ComparisonSubmission, reviews: InspectionReviews,
             access: InspectionAccess) -> InspectionRoutes:
    @app.post("/api/text-inspection/label/compare")
    async def compare_text_inspection_label(
        captured_file: UploadFile | None = File(None), standard_asset_id: str = Form(...),
        comparison_id: str = Form(...), extraction_id: str = Form(""),
    ) -> dict[str, Any]:
        return await comparison.compare_text_inspection_label(captured_file, standard_asset_id, comparison_id, extraction_id)

    @app.get("/api/text-inspection/inspections/{inspection_id}/evidence/{kind}")
    def get_text_inspection_v2_evidence(inspection_id: str, kind: str) -> Response:
        contents, mime = reviews.get_text_inspection_v2_evidence(inspection_id, kind)
        return Response(content=contents, media_type=mime, headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})

    @app.post("/api/text-inspection/manual/sessions")
    async def create_text_manual_session(request: Request) -> dict[str, Any]:
        access.require_permission("inspection", detail="没有文字检验权限")
        raise HTTPException(410, "旧说明书历史仅供查阅，请新建任务导入 PDF")

    @app.post("/api/text-inspection/manual/sessions/{session_id}/pages")
    async def inspect_text_manual_page(
        session_id: str, captured_file: UploadFile = File(...), capture_id: str = Form(...),
        standard_asset_id: str = Form(""),
    ) -> dict[str, Any]:
        access.require_permission("inspection", detail="没有文字检验权限")
        raise HTTPException(410, "旧说明书历史仅供查阅，请新建任务导入 PDF")

    @app.post("/api/text-inspection/manual/sessions/{session_id}/complete")
    def complete_text_manual_session(session_id: str) -> dict[str, Any]:
        access.require_permission("inspection", detail="没有文字检验权限")
        raise HTTPException(410, "旧说明书历史仅供查阅，请新建任务导入 PDF")

    @app.post("/api/text-inspection/inspections/{inspection_id}/review")
    async def review_text_inspection_v2(inspection_id: str, request: Request) -> dict[str, Any]:
        return await reviews.review_text_inspection_v2(inspection_id, lambda: request.json())

    return InspectionRoutes(compare_text_inspection_label, get_text_inspection_v2_evidence,
                            create_text_manual_session, inspect_text_manual_page,
                            complete_text_manual_session, review_text_inspection_v2)
