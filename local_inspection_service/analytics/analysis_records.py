"""Analysis record normalization; injected metadata rules preserve legacy records."""
from collections.abc import Callable
from dataclasses import dataclass
import re
import time
from typing import Any

Record = dict[str, Any]


@dataclass(frozen=True)
class AnalysisNormalization:
    default_task_id: str
    default_task_label: str
    clean_task_name: Callable[[Any, str], str]
    created_at: Callable[[Record], int]
    updated_at: Callable[[Record], int]
    owner_id: Callable[[Record], str]
    owner_username: Callable[[Record], str]


def sanitize_data_analysis_record_id(value: Any) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip()).strip("_")[:120]


class AnalysisNormalizer:
    def __init__(self, dependencies: AnalysisNormalization):
        self.dependencies = dependencies

    def normalize_data_analysis_record(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        record_id = sanitize_data_analysis_record_id(raw.get("record_id") or raw.get("id"))
        if not record_id:
            return None
        ai_result = raw.get("ai_detection_result") if isinstance(raw.get("ai_detection_result"), dict) else {}
        ai_summary = raw.get("ai_summary") if isinstance(raw.get("ai_summary"), dict) else {}
        source_image = raw.get("source_image") if isinstance(raw.get("source_image"), dict) else {}
        model = ai_result.get("model") if isinstance(ai_result.get("model"), dict) else {}
        task = raw.get("task") if isinstance(raw.get("task"), dict) else {}
        image_processing_items = [item for item in raw.get("image_processing_items", []) if isinstance(item, dict)]
        task_id = str(task.get("id") or raw.get("task_id") or model.get("task_id") or model.get("id") or self.dependencies.default_task_id).strip()
        task_name = self.dependencies.clean_task_name(task.get("name") or raw.get("task_name") or model.get("task_label") or model.get("label"), self.dependencies.default_task_label)
        created_at = self.dependencies.created_at(raw)
        updated_at = self.dependencies.updated_at(raw)
        if not created_at:
            created_at = int(time.time())
        if not updated_at:
            updated_at = created_at
        return {
            "record_id": record_id,
            "owner_user_id": self.dependencies.owner_id(raw),
            "owner_username": self.dependencies.owner_username(raw),
            "created_at": created_at,
            "updated_at": updated_at,
            "task": {
                "id": task_id,
                "name": task_name,
                "type": str(task.get("type") or raw.get("task_type") or "ai_detection"),
                "model_id": str(task.get("model_id") or model.get("id") or ""),
            },
            "source_image": {
                "url": str(source_image.get("url") or raw.get("image_url") or raw.get("annotated_url") or ai_result.get("annotated_url") or ""),
                "path": str(source_image.get("path") or raw.get("source_image_path") or ""),
                "filename": str(source_image.get("filename") or raw.get("source_filename") or ""),
            },
            "image_url": str(raw.get("image_url") or source_image.get("url") or ai_result.get("annotated_url") or ""),
            "ai_detection_result": ai_result,
            "ai_summary": ai_summary,
            "image_processing_items": image_processing_items[-200:],
            "comparison_summary": {},
        }
