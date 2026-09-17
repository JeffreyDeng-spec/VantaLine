"""Single-flight Beta comparison cache and unchanged OCR failure policy."""
import hashlib
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
import cv2
import numpy as np
from fastapi import HTTPException
from ..incoming_text_inspection import TextObservation


@dataclass(frozen=True)
class BetaPolicy:
    ttl_seconds: Callable[[], int]
    max_pixels: Callable[[], int]
    max_cache_bytes: Callable[[], int]


class BetaComparison:
    def __init__(self, policy: BetaPolicy, observer: Callable[[], Callable[[np.ndarray], list[TextObservation]]]):
        self.policy, self.observer = policy, observer
        self.lock = threading.RLock()
        self.cache: dict[tuple[str, str], dict[str, Any]] = {}

    def run(self, user_id: str, clean_id: str, reference_bytes: bytes, captured_bytes: bytes) -> dict[str, Any]:
        reference_hash = hashlib.sha256(reference_bytes).hexdigest()
        captured_hash = hashlib.sha256(captured_bytes).hexdigest()
        fingerprint = hashlib.sha256(f"{len(reference_bytes)}:{reference_hash}:{len(captured_bytes)}:{captured_hash}".encode("ascii")).hexdigest()
        key = (user_id, clean_id)
        # The lock intentionally spans OCR. Beta is capped at one OCR comparison at
        # a time, keeping the API event loop responsive and making same-ID retries
        # true single-flight operations.
        with self.lock:
            now = time.monotonic()
            for cached_key, cached in list(self.cache.items()):
                if now - float(cached.get("created_at") or 0) > self.policy.ttl_seconds():
                    self.cache.pop(cached_key, None)
            cached = self.cache.get(key)
            if cached:
                if cached["fingerprint"] != fingerprint:
                    raise HTTPException(status_code=409, detail="同一 comparison_id 对应了不同图片")
                return cached["result"]
            reference = cv2.imdecode(np.frombuffer(reference_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            captured = cv2.imdecode(np.frombuffer(captured_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if reference is None or captured is None:
                raise HTTPException(status_code=400, detail="图片解码失败，请使用 PNG 或 JPG 图片")
            for image in (reference, captured):
                if image.shape[0] * image.shape[1] > self.policy.max_pixels() or min(image.shape[:2]) < 300:
                    raise HTTPException(status_code=400, detail="图片尺寸不符合要求，单张不能超过 1600 万像素")
            try:
                from local_inspection_service.text_compare_beta import compare_images

                result = compare_images(reference, captured, clean_id, self.observer())
            except Exception as exc:
                result = {
                    "comparison_id": clean_id,
                    "decision": "REVIEW_REQUIRED",
                    "message": "文字识别服务暂时无法完成对比，请人工确认或稍后重试。",
                    "differences": [],
                    "error_code": type(exc).__name__,
                }
            result_size = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
            self.cache[key] = {
                "fingerprint": fingerprint,
                "result": result,
                "created_at": now,
                "size": result_size,
            }
            while sum(int(item.get("size") or 0) for item in self.cache.values()) > self.policy.max_cache_bytes():
                oldest = min(self.cache, key=lambda item: float(self.cache[item].get("created_at") or 0))
                self.cache.pop(oldest, None)
            return result
