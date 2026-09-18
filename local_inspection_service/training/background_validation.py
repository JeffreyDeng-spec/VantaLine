"""Single-call empty-background validation with explicit model analysis and formatting dependencies."""
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID
import cv2
import numpy as np
from fastapi import HTTPException

Record = dict[str, Any]


class BackgroundAnalysis(Protocol):
    def __call__(self, image_bgr: np.ndarray, request_id: str, model_id: str | None = None,
                 *, image_path: Path | None = None) -> Record: ...


class BackgroundValidation:
    def __init__(self, sanitize: Callable[[str], str], prefix: Callable[[], str], clock: Callable[[], float],
                 uuid: Callable[[], UUID], analyze: BackgroundAnalysis, text: Callable[[], Callable[[Any, int], str]]):
        self.sanitize, self.prefix, self.clock = sanitize, prefix, clock
        self.uuid, self.analyze, self.text = uuid, analyze, text

    def validate_task_environment_background_image(self, task_id: str, task: dict[str, Any], source_path: Path) -> dict[str, Any]:
        """Reject task empty-background captures that still contain required parts."""
        clean_task_id = self.sanitize(task_id)
        if not clean_task_id:
            raise HTTPException(status_code=404, detail="AI detection task not found")
        image_bgr = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
        if image_bgr is None:
            raise HTTPException(status_code=400, detail="无法读取背景图片，请重新上传。")
        model_id = f"{self.prefix()}{clean_task_id}"
        request_id = f"background_probe_{clean_task_id}_{int(self.clock())}_{self.uuid().hex[:6]}"
        try:
            result = self.analyze(image_bgr, request_id, model_id, image_path=source_path)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"背景图验收失败：AI 检测暂不可用（{self.text()(str(exc), 120)}）。请稍后重试。",
            ) from exc
        ai_meta = result.get("ai") if isinstance(result.get("ai"), dict) else {}
        if ai_meta.get("provider_failure") is True:
            reason = self.text()(ai_meta.get("failure_reason") or ai_meta.get("error") or "AI provider unavailable", 120)
            raise HTTPException(status_code=503, detail=f"背景图验收失败：AI 检测不可用（{reason}）。请稍后重试。")
        labels = task.get("accessory_labels") if isinstance(task.get("accessory_labels"), dict) else {}
        detected: list[str] = []
        detections = result.get("detections") if isinstance(result.get("detections"), list) else []
        for item in detections:
            if not isinstance(item, dict):
                continue
            try:
                count = int(item.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            if item.get("present") is True or count > 0:
                accessory_id = str(item.get("accessory_id") or "")
                label = self.text()(item.get("label") or labels.get(accessory_id) or accessory_id or "目标配件", 80)
                if label and label not in detected:
                    detected.append(label)
        rule = result.get("rule") if isinstance(result.get("rule"), dict) else {}
        counts = rule.get("counts") if isinstance(rule.get("counts"), dict) else {}
        for accessory_id, raw_count in counts.items():
            try:
                count = int(raw_count or 0)
            except (TypeError, ValueError):
                count = 0
            if count <= 0:
                continue
            item_id = str(accessory_id)
            label = self.text()(labels.get(item_id) or item_id or "目标配件", 80)
            if label and label not in detected:
                detected.append(label)
        if detected:
            raise HTTPException(
                status_code=409,
                detail=f"背景图检测到目标配件：{'、'.join(detected)}。请清空画面后重新拍摄空背景。",
            )
        return {
            "status": "accepted",
            "request_id": result.get("request_id") or request_id,
            "latency_ms": ai_meta.get("latency_ms") or 0,
            "provider_model": (result.get("model") if isinstance(result.get("model"), dict) else {}).get("provider_model") or "",
        }
