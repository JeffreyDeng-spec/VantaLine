"""Detection/image processing record publication with explicit ownership and persistence."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Protocol
import uuid
from .analysis_records import sanitize_data_analysis_record_id
from .analysis_repository import AnalysisRepository
from .analysis_processing import ProcessingProjection

Record = dict[str, Any]


class StringList(Protocol):
    def __call__(self, value: Any, *, max_items: int, max_len: int) -> list[str]: ...


@dataclass(frozen=True)
class PublicationDependencies:
    current_user: Callable[[], Record | None]
    owner_fields: Callable[[], Record]
    owner_id: Callable[[Record], str]
    owner_username: Callable[[Record], str]
    default_task_id: str
    default_task_label: str
    clean_task_name: Callable[[Any, str], str]
    string_list: StringList
    resolve_path: Callable[[Any], Path]
    safe_name: Callable[[str], str]
    output_url: Callable[[Path], str]
    capture: Callable[[Record, Record, str, Path | None], Any]


class AnalysisPublisher:
    def __init__(self, dependencies: PublicationDependencies, repository: AnalysisRepository,
                 processing: ProcessingProjection):
        self.dependencies = dependencies
        self.repository = repository
        self.processing = processing

    def ai_detection_summary_for_analysis(self, result: dict[str, Any]) -> dict[str, Any]:
        rule = result.get("rule") if isinstance(result.get("rule"), dict) else {}
        detections = result.get("detections") if isinstance(result.get("detections"), list) else []
        counts = rule.get("counts") if isinstance(rule.get("counts"), dict) else {}
        missing = self.dependencies.string_list(rule.get("missing"), max_items=50, max_len=120)
        extra = self.dependencies.string_list(rule.get("extra"), max_items=50, max_len=120)
        mismatches = rule.get("count_mismatches") if isinstance(rule.get("count_mismatches"), dict) else {}
        present_count = sum(1 for item in detections if isinstance(item, dict) and item.get("present") is True)
        return {
            "passed": bool(result.get("passed")),
            "detection_count": len([item for item in detections if isinstance(item, dict)]),
            "present_count": present_count,
            "missing_count": len(missing),
            "extra_count": len(extra),
            "count_mismatch_count": len(mismatches),
            "counts": {str(k): int(v) for k, v in counts.items() if type(v) is int},
            "missing": missing,
            "extra": extra,
            "provider_status": str((result.get("ai") or {}).get("provider_status") or "") if isinstance(result.get("ai"), dict) else "",
            "latency_ms": int((result.get("ai") or {}).get("latency_ms") or 0) if isinstance(result.get("ai"), dict) else 0,
        }

    def persist_data_analysis_record_for_ai_detection(self,
        result: dict[str, Any],
        request_id: str,
        *,
        image_path: Path | None = None,
    ) -> dict[str, Any] | None:
        user = self.dependencies.current_user()
        if not user:
            return None
        model_payload = result.get("model") if isinstance(result.get("model"), dict) else {}
        task_id = str(model_payload.get("task_id") or model_payload.get("id") or self.dependencies.default_task_id).strip() or self.dependencies.default_task_id
        task_name = self.dependencies.clean_task_name(model_payload.get("task_label") or model_payload.get("label"), self.dependencies.default_task_label)
        now = int(time.time())
        source_path = str(self.dependencies.resolve_path(image_path)) if image_path else ""
        image_url = str(result.get("annotated_url") or "")
        record = {
            "record_id": f"analysis_{now}_{uuid.uuid4().hex[:10]}",
            **self.dependencies.owner_fields(),
            "created_at": now,
            "updated_at": now,
            "task": {
                "id": task_id,
                "name": task_name,
                "type": "ai_detection",
                "model_id": str(model_payload.get("id") or ""),
            },
            "source_image": {
                "url": image_url,
                "path": source_path,
                "filename": Path(source_path).name if source_path else self.dependencies.safe_name(f"{request_id}.jpg"),
            },
            "image_url": image_url,
            "ai_detection_result": result,
            "ai_summary": self.ai_detection_summary_for_analysis(result),
            "comparison_summary": {},
        }
        self.repository.save_data_analysis_record(record, prepend=True)
        self.dependencies.capture(record, result, request_id, image_path)
        return record

    def upsert_data_analysis_image_processing_record(self,
        *,
        record_id: str,
        task: dict[str, Any],
        source_path: Path,
        items: list[dict[str, Any]],
        accessory: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_record_id = sanitize_data_analysis_record_id(record_id)
        if not clean_record_id:
            return {}
        now = int(time.time())
        owner_user_id = str(task.get("owner_user_id") or self.dependencies.owner_id(accessory or {}) or "")
        owner_username = str(task.get("owner_username") or self.dependencies.owner_username(accessory or {}) or owner_user_id or "")
        task_id = str(task.get("id") or "image_processing")
        task_name = str(task.get("name") or task.get("label") or "图片处理")
        source_url = self.dependencies.output_url(source_path)
        with self.repository.dependencies.lock():
            record = self.repository.load_data_analysis_record(clean_record_id)
            if record is None:
                record = {
                    "record_id": clean_record_id,
                    "owner_user_id": owner_user_id,
                    "owner_username": owner_username,
                    "created_at": now,
                    "updated_at": now,
                    "task": {
                        "id": task_id,
                        "name": task_name,
                        "type": "image_processing",
                        "model_id": "",
                    },
                    "source_image": {
                        "url": source_url,
                        "path": str(source_path),
                        "filename": source_path.name,
                    },
                    "image_url": source_url,
                    "ai_detection_result": {},
                    "ai_summary": {},
                    "comparison_summary": {},
                    "image_processing_items": [],
                }
            record["owner_user_id"] = record.get("owner_user_id") or owner_user_id
            record["owner_username"] = record.get("owner_username") or owner_username
            record["updated_at"] = now
            record["task"] = {
                **(record.get("task") if isinstance(record.get("task"), dict) else {}),
                "id": task_id,
                "name": task_name,
                "type": "image_processing",
            }
            record["source_image"] = {
                **(record.get("source_image") if isinstance(record.get("source_image"), dict) else {}),
                "url": source_url,
                "path": str(source_path),
                "filename": source_path.name,
            }
            if source_url:
                record["image_url"] = source_url
            record["image_processing_items"] = self.processing.merge_image_processing_items(
                [entry for entry in record.get("image_processing_items") or [] if isinstance(entry, dict)],
                items,
            )
            self.repository.save_data_analysis_record(record, prepend=True)
            return record
