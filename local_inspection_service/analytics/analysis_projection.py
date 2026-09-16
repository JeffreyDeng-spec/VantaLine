"""Public analysis views and source-image lookup, independent of HTTP handlers."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from fastapi import HTTPException
from .analysis_processing import ProcessingProjection, image_processing_summary
from .analysis_scope import AnalysisScope

Record = dict[str, Any]


@dataclass(frozen=True)
class ProjectionDependencies:
    created_at: Callable[[Record], int]
    updated_at: Callable[[Record], int]
    owner_id: Callable[[Record], str]
    owner_username: Callable[[Record], str]
    default_task_label: str
    output_directory: Callable[[], Path]
    resolve_path: Callable[[Any], Path]
    path_is_under: Callable[[Path, Path], bool]


def public_data_analysis_ai_result(record: dict[str, Any], *, include_debug: bool = False) -> dict[str, Any]:
    result = record.get("ai_detection_result") if isinstance(record.get("ai_detection_result"), dict) else {}
    if include_debug:
        return result
    model = result.get("model") if isinstance(result.get("model"), dict) else {}
    return {
        "request_id": result.get("request_id") or "",
        "passed": bool(result.get("passed")),
        "annotated_url": result.get("annotated_url") or "",
        "preview_url": result.get("preview_url") or "",
        "output_url": result.get("output_url") or "",
        "model": {
            "id": model.get("id") or "",
            "label": model.get("label") or "",
            "task_id": model.get("task_id") or "",
            "task_label": model.get("task_label") or "",
            "is_ai_detection": bool(model.get("is_ai_detection")),
        },
    }


class AnalysisProjection:
    def __init__(self, dependencies: ProjectionDependencies, processing: ProcessingProjection, scope: AnalysisScope):
        self.dependencies = dependencies
        self.processing = processing
        self.scope = scope

    def public_data_analysis_record(self,
        record: dict[str, Any],
        *,
        detail: bool = False,
        include_debug: bool = False,
        include_auto_optimize: bool = True,
        include_scope: bool = True,
        processing_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if processing_items is None:
            processing_items = self.processing.data_analysis_image_processing_items(record, include_auto_optimize=include_auto_optimize)
        ai_summary = (
            self.scope.data_analysis_scoped_ai_summary(record)
            if include_scope
            else record.get("ai_summary") if isinstance(record.get("ai_summary"), dict) else {}
        )
        required_scope = self.scope.public_data_analysis_scope_payload(record) if include_scope else {}
        payload = {
            "record_id": record.get("record_id") or "",
            "owner_user_id": self.dependencies.owner_id(record),
            "owner_username": self.dependencies.owner_username(record),
            "created_at": self.dependencies.created_at(record),
            "updated_at": self.dependencies.updated_at(record),
            "task": record.get("task") if isinstance(record.get("task"), dict) else {},
            "source_image": record.get("source_image") if isinstance(record.get("source_image"), dict) else {},
            "image_url": record.get("image_url") or "",
            "ai_summary": ai_summary,
            "required_accessory_scope": required_scope,
            "comparison_summary": {},
            "image_processing_summary": image_processing_summary(processing_items),
            "image_processing_items": processing_items[:40],
        }
        if detail:
            payload["ai_detection_result"] = public_data_analysis_ai_result(record, include_debug=include_debug)
            payload["image_processing_items"] = processing_items
            payload["debug_available"] = include_debug
        return payload

    def data_analysis_task_groups(self, records: list[dict[str, Any]], *, include_auto_optimize: bool = True) -> list[dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        for record in records:
            task = record.get("task") if isinstance(record.get("task"), dict) else {}
            task_id = str(task.get("id") or "ai_detection")
            group = groups.setdefault(
                task_id,
                {
                    "id": task_id,
                    "name": str(task.get("name") or self.dependencies.default_task_label),
                    "type": str(task.get("type") or "ai_detection"),
                    "count": 0,
                    "latest_at": 0,
                    "image_processing_summary": image_processing_summary([]),
                },
            )
            group["count"] += 1
            group["latest_at"] = max(int(group["latest_at"]), self.dependencies.updated_at(record))
            record_summary = image_processing_summary(self.processing.data_analysis_image_processing_items(record, include_auto_optimize=include_auto_optimize))
            group_summary = group["image_processing_summary"]
            for key in ("total", "queued", "running", "completed", "rejected", "failed", "active"):
                group_summary[key] = int(group_summary.get(key) or 0) + int(record_summary.get(key) or 0)
            by_status = group_summary.setdefault("by_status", {})
            for status, count in (record_summary.get("by_status") or {}).items():
                by_status[str(status)] = int(by_status.get(str(status), 0)) + int(count or 0)
        return sorted(groups.values(), key=lambda item: (int(item["latest_at"]), str(item["id"])), reverse=True)

    def data_analysis_record_image_path(self, record: dict[str, Any]) -> Path:
        source = record.get("source_image") if isinstance(record.get("source_image"), dict) else {}
        for raw_url in (source.get("url"), record.get("image_url")):
            url = str(raw_url or "").split("?", 1)[0]
            if not url.startswith("/outputs/"):
                continue
            candidate = (self.dependencies.output_directory() / PurePosixPath(url.removeprefix("/outputs/").lstrip("/"))).resolve()
            if candidate.exists() and self.dependencies.path_is_under(candidate, self.dependencies.output_directory()):
                return candidate
        raw_path = str(source.get("path") or "").strip()
        if raw_path:
            candidate = self.dependencies.resolve_path(raw_path)
            if candidate.exists():
                return candidate
        raise HTTPException(status_code=404, detail="Analysis record image is not available")
