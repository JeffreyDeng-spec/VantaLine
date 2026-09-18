"""Failure and model projections with explicit formatting and metadata capabilities."""
from collections.abc import Callable
from typing import Any, Protocol

Record = dict[str, Any]
BoundedText = Callable[[Any, int], str]


class FailurePayload(Protocol):
    def __call__(self, required_accessories: list[Record], settings: Record, *, reason: str,
                 timed_out: bool = False, latency_ms: int = 0) -> Record: ...


class FailureProjection:
    def __init__(self, text: Callable[[], BoundedText], provider_meta: Callable[[Record], Record],
                 label: Callable[[], str]):
        self.text, self.provider_meta, self.label = text, provider_meta, label

    def ai_presence_failure_payload(self,
        required_accessories: list[dict[str, Any]],
        settings: dict[str, Any],
        *,
        reason: str,
        timed_out: bool = False,
        latency_ms: int = 0,
    ) -> dict[str, Any]:
        missing_ids = [str(item.get("accessory_id") or "") for item in required_accessories if item.get("accessory_id")]
        detections = [
            {
                "accessory_id": item_id,
                "label": self.text()(required.get("name") or required.get("label") or item_id, 120),
                "present": False,
                "confidence": 0.0,
                "evidence": self.text()(reason, 160),
                "observed_text": [],
            }
            for required in required_accessories
            for item_id in [str(required.get("accessory_id") or "")]
            if item_id
        ]
        provider_meta = self.provider_meta(settings)
        return {
            "tool": "vision.inspect.presence",
            "passed": len(missing_ids) == 0,
            "rule": {
                "match_policy": "ai_presence",
                "label": self.label(),
                "present": [],
                "missing": missing_ids,
                "extra": [],
                "counts": {item_id: 0 for item_id in missing_ids},
            },
            "detections": detections,
            "ai": {
                "latency_ms": latency_ms,
                "timed_out": timed_out,
                "provider_failure": True,
                "failure_reason": self.text()(reason, 240),
                "raw_summary": self.text()(reason, 240),
                "provider_status": settings.get("status") or "",
                "error": self.text()(reason, 240),
                **provider_meta,
            },
        }

    def ai_model_payload(self, spec: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": spec["id"],
            "label": spec.get("label", self.label()),
            "variant": "ai_detection",
            "is_ai_detection": True,
            "provider_model": settings.get("model") or "",
            "uses_ocr": True,
            "task_id": spec.get("task_id") or "",
            "task_label": spec.get("task_label") or "",
            "selected_accessory_ids": spec.get("selected_accessory_ids") or [],
            "required_accessory_counts": spec.get("required_accessory_counts") or {},
            "accessory_names": spec.get("accessory_names") or [],
            "accessory_labels": spec.get("accessory_labels") or {},
        }
