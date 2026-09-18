"""Detection failure assembly preserving payload evaluation order and shared fields."""
from collections.abc import Callable
from typing import Any
from .failure_projection import FailurePayload

Record = dict[str, Any]


class DetectionFailureResult:
    def __init__(self, settings: Callable[[], Record], profile: Callable[[Record, int], Record],
                 failure: FailurePayload, model: Callable[[Record, Record], Record]):
        self.settings, self.profile, self.failure, self.model = settings, profile, failure, model

    def ai_detection_failure_result(self,
        request_id: str,
        spec: dict[str, Any],
        required_items: list[tuple[dict[str, Any], int]],
        annotated_url: str,
        *,
        reason: str,
        timed_out: bool = False,
        latency_ms: int = 0,
    ) -> dict[str, Any]:
        settings = self.settings()
        required_accessories = [self.profile(item, expected_count) for item, expected_count in required_items]
        payload = self.failure(required_accessories, settings, reason=reason, timed_out=timed_out, latency_ms=latency_ms)
        return {
            "request_id": request_id,
            "passed": payload["passed"],
            "model": self.model(spec, settings),
            "rule": payload["rule"],
            "detections": payload["detections"],
            "annotated_url": annotated_url,
            "ai": payload["ai"],
        }
