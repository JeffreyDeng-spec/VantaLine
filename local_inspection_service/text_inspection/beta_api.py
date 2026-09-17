"""Beta upload validation and asynchronous thread-pool handoff."""
import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from .preparation_ports import Permission

RunComparison = Callable[[str, str, bytes, bytes], dict[str, Any]]


@dataclass(frozen=True)
class BetaAccess:
    require_permission: Permission
    current_user: Callable[[], dict[str, Any]]


def register(app: FastAPI, access: BetaAccess, max_bytes: Callable[[], int], run_provider: Callable[[], RunComparison]):
    @app.post("/api/text-compare-beta/analyze")
    async def analyze_text_compare_beta(
        reference_file: UploadFile = File(...), captured_file: UploadFile = File(...),
        comparison_id: str = Form(...),
    ) -> dict[str, Any]:
        access.require_permission("inspection", detail="没有文字对比权限")
        clean_id = comparison_id.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{8,128}", clean_id):
            raise HTTPException(status_code=400, detail="comparison_id 格式错误")
        allowed_types = {"image/png", "image/jpeg", "image/webp"}
        if reference_file.content_type not in allowed_types or captured_file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="仅支持 PNG、JPG 或 WEBP 图片")
        reference_bytes, captured_bytes = await reference_file.read(), await captured_file.read()
        if (
            not reference_bytes
            or not captured_bytes
            or len(reference_bytes) > max_bytes()
            or len(captured_bytes) > max_bytes()
        ):
            raise HTTPException(status_code=400, detail="标准图和实物图必须存在，且单张不超过 10MB")
        user_id = str(access.current_user().get("id") or "")
        return await asyncio.to_thread(run_provider(), user_id, clean_id, reference_bytes, captured_bytes)

    return analyze_text_compare_beta
