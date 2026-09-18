"""Video frame projections and aggregated AI evidence."""
from collections.abc import Callable
from typing import Any
from .presence_payload import StringList

def video_frame_result_payload(result: dict[str, Any], frame_index: int, fps: float) -> dict[str, Any]:
    rule = result.get("rule") if isinstance(result.get("rule"), dict) else {}
    detections = result.get("detections") if isinstance(result.get("detections"), list) else []
    frame_payload: dict[str, Any] = {
        "frame_index": frame_index,
        "timestamp_seconds": round(frame_index / fps, 3),
        "passed": bool(result.get("passed")),
        "missing": rule.get("missing") if isinstance(rule.get("missing"), list) else [],
        "detections": len(detections),
    }
    model_payload = result.get("model") if isinstance(result.get("model"), dict) else {}
    ai_payload = result.get("ai") if isinstance(result.get("ai"), dict) else None
    if ai_payload or model_payload.get("is_ai_detection"):
        frame_payload.update(
            {
                "model": model_payload,
                "rule": rule,
                "ai": ai_payload or {},
                "detection_items": detections,
                "annotated_url": result.get("annotated_url") or "",
            }
        )
    return frame_payload


class VideoSummary:
    def __init__(self, strings: Callable[[], StringList]):
        self.strings = strings

    def video_ai_summary(self, frames: list[dict[str, Any]]) -> dict[str, Any] | None:
        ai_frames = [frame for frame in frames if isinstance(frame.get('ai'), dict)]
        if not ai_frames:
            return None
        errors = self.strings()([str(frame.get('ai', {}).get('error') or '') for frame in ai_frames if frame.get('ai', {}).get('error')], max_items=8, max_len=180)
        first_error_frame = next((frame for frame in ai_frames if frame.get('ai', {}).get('error') or frame.get('ai', {}).get('timed_out')), None)
        return {'frame_count': len(ai_frames), 'timed_out': any((bool(frame.get('ai', {}).get('timed_out')) for frame in ai_frames)), 'errors': errors, 'first_error': (first_error_frame or {}).get('ai', {}).get('error') if first_error_frame else '', 'first_error_frame_index': (first_error_frame or {}).get('frame_index') if first_error_frame else None, 'provider_status': next((frame.get('ai', {}).get('provider_status') for frame in ai_frames if frame.get('ai', {}).get('provider_status')), ''), 'total_latency_ms': sum((int(frame.get('ai', {}).get('latency_ms') or 0) for frame in ai_frames))}
