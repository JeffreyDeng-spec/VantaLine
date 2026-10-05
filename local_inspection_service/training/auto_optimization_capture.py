"""Capture workflow: preserve admission, state writes and background launch order."""
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any
import uuid

from .auto_optimization_capture_ports import AutoOptimizationCapturePorts


@dataclass(frozen=True)
class AutoOptimizationCapture:
    ports: AutoOptimizationCapturePorts

    def auto_optimize_detection_candidates(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        detections = result.get("detections") if isinstance(result.get("detections"), list) else []
        candidates: list[dict[str, Any]] = []
        for det in detections:
            if not isinstance(det, dict) or det.get("present") is not True:
                continue
            try:
                confidence = float(det.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence <= 0.0:
                continue
            count = det.get("count")
            if count is not None and type(count) is int and count != 1:
                continue
            candidates.append(
                {
                    "accessory_id": str(det.get("accessory_id") or ""),
                    "label": str(det.get("label") or det.get("accessory_id") or ""),
                    "confidence": round(max(0.0, min(1.0, confidence)), 4),
                    "evidence": self.ports.bounded_text()(det.get("evidence") or "", 180),
                }
            )
        return [item for item in candidates if item["accessory_id"]]

    def record_auto_optimize_capture(self, record: dict[str, Any] | None, result: dict[str, Any], request_id: str, image_path: Path | None) -> None:
        if not record:
            return
        model_payload = result.get("model") if isinstance(result.get("model"), dict) else {}
        if not model_payload.get("is_ai_detection"):
            return
        task_id = self.ports.sanitize_ai_detection_task_id()(model_payload.get("task_id") or model_payload.get("run_id") or "")
        if not task_id:
            return
        with self.ports._auto_optimize_lock():
            state = self.ports.load_auto_optimize_state()(task_id)
            completed_model_id = self.ports.auto_optimize_completed_model_id()(state)
            if completed_model_id:
                self.ports.auto_optimize_stop_capture_for_model_locked()(state, completed_model_id, reason="completed_model_ready")
                self.ports.save_auto_optimize_state()(state)
            enabled = self.ports.auto_optimize_capture_enabled()(state)
        if not enabled:
            return
        source_path = str(self.ports.resolve_service_path()(image_path)) if image_path else str((record.get("source_image") or {}).get("path") or "")
        if not source_path:
            return
        candidates = self.ports.auto_optimize_detection_candidates()(result)
        ai_payload = result.get("ai") if isinstance(result.get("ai"), dict) else {}
        ai_detection_passed = bool(result.get("passed"))
        provider_failure = bool(
            ai_payload.get("error")
            or ai_payload.get("overloaded")
            or ai_payload.get("timed_out")
            or str(ai_payload.get("provider_status") or "").lower() in {"failed", "error", "overloaded", "timeout"}
        )
        if provider_failure:
            label_status = "failed"
            sample_type = "provider_failure"
            label_reject_reason = "ai_detection_provider_failed"
        elif not ai_detection_passed:
            label_status = "failed"
            sample_type = "failed_detection"
            label_reject_reason = "ai_detection_not_passed"
        elif candidates:
            label_status = "pending"
            sample_type = "positive_candidate"
            label_reject_reason = ""
        else:
            label_status = "failed"
            sample_type = "failed_detection"
            label_reject_reason = "ai_detection_no_positive_candidates"
        now = int(time.time())
        sample = {
            "sample_id": f"autoopt_{now}_{uuid.uuid4().hex[:8]}",
            "record_id": record.get("record_id") or "",
            "request_id": request_id,
            "task_id": task_id,
            **self.ports.current_owner_fields()(),
            "created_at": now,
            "source_image": {
                "path": source_path,
                "url": (record.get("source_image") or {}).get("url") or record.get("image_url") or result.get("annotated_url") or "",
                "filename": Path(source_path).name,
            },
            "ai_result": {
                "passed": bool(result.get("passed")),
                "rule": result.get("rule") if isinstance(result.get("rule"), dict) else {},
                "detections": result.get("detections") if isinstance(result.get("detections"), list) else [],
                "model": model_payload,
                "provider_model": ai_payload.get("provider_model") or "",
                "provider_failure": provider_failure,
                "provider_error": self.ports.bounded_text()(ai_payload.get("error") or "", 240),
            },
            "candidate_accessories": candidates,
            "labels": [],
            "sample_type": sample_type,
            "label_status": label_status,
            "label_reject_reason": label_reject_reason,
            "shadow_status": "pending",
        }
        with self.ports._auto_optimize_lock():
            state = self.ports.load_auto_optimize_state()(task_id)
            state["task_name"] = model_payload.get("task_label") or model_payload.get("label") or ""
            state["owner_user_id"] = sample.get("owner_user_id") or state.get("owner_user_id") or ""
            state["owner_username"] = sample.get("owner_username") or state.get("owner_username") or ""
            state["selected_accessory_ids"] = model_payload.get("selected_accessory_ids") or state.get("selected_accessory_ids") or []
            state["required_accessory_counts"] = model_payload.get("required_accessory_counts") or state.get("required_accessory_counts") or {}
            state.setdefault("samples", [])
            state["samples"].insert(0, sample)
            state["samples"] = state["samples"][:10000]
            self.ports.save_auto_optimize_state()(state)
        if label_status == "pending":
            self.ports.start_auto_optimize_label_worker()(task_id)
        if label_status == "pending":
            self.ports.start_auto_optimize_shadow_worker()(task_id, sample["sample_id"])
