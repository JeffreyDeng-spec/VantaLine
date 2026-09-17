"""Process-local warmup status and threads, without importing the application."""
from collections.abc import Callable
from dataclasses import dataclass
import os
import threading
import time
from typing import Any

Record = dict[str, Any]
WarmupWorker = Callable[[str, list[str] | None], None]


@dataclass(frozen=True)
class WarmupOperations:
    enabled: Callable[[], bool]
    config: Callable[[], Record]
    candidates: Callable[[Record], list[str]]
    warm: Callable[[str, Record], None]
    loaded_ids: Callable[[Record], list[str]]
    error_text: Callable[[str, int], str]


class YoloWarmup:
    def __init__(self, operations: WarmupOperations):
        self.operations = operations
        self.lock = threading.RLock()
        self.state: Record = {
            "enabled": True,
            "status": "idle",
            "model_ids": [],
            "completed_model_ids": [],
            "failed_model_ids": [],
            "started_at": 0,
            "completed_at": 0,
            "error": "",
        }

    def yolo_warmup_status(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.state)

    def public_yolo_warmup_status(self, config: dict[str, Any]) -> dict[str, Any]:
        status = self.yolo_warmup_status()
        status["loaded_model_ids"] = self.operations.loaded_ids(config)
        return status

    def yolo_warmup_worker(self, reason: str = "startup", model_ids: list[str] | None = None) -> None:
        if not self.operations.enabled():
            with self.lock:
                self.state.update({"enabled": False, "status": "disabled", "error": ""})
            return
        try:
            delay_seconds = max(0.0, min(30.0, float(os.environ.get("VANTALINE_YOLO_PREWARM_DELAY_SECONDS", "1.5"))))
        except (TypeError, ValueError):
            delay_seconds = 1.5
        time.sleep(delay_seconds)
        config = self.operations.config()
        warmup_ids = model_ids or self.operations.candidates(config)
        started_at = int(time.time())
        with self.lock:
            self.state.update(
                {
                    "enabled": True,
                    "status": "running",
                    "reason": reason,
                    "model_ids": warmup_ids,
                    "completed_model_ids": [],
                    "failed_model_ids": [],
                    "started_at": started_at,
                    "completed_at": 0,
                    "error": "",
                }
            )
        completed: list[str] = []
        failed: list[dict[str, str]] = []
        for model_id in warmup_ids:
            try:
                self.operations.warm(model_id, config)
                completed.append(model_id)
            except Exception as exc:  # noqa: BLE001 - warmup must not block serving
                failed.append({"model_id": model_id, "error": self.operations.error_text(str(exc), 180)})
            with self.lock:
                self.state["completed_model_ids"] = completed
                self.state["failed_model_ids"] = failed
        with self.lock:
            self.state.update(
                {
                    "status": "completed" if not failed else "completed_with_errors",
                    "completed_at": int(time.time()),
                    "error": "; ".join(f"{item['model_id']}: {item['error']}" for item in failed[:3]),
                }
            )

    def start_yolo_warmup(self, reason: str = "startup", model_ids: list[str] | None = None, *, worker: Callable[[], WarmupWorker]) -> None:
        if not self.operations.enabled():
            with self.lock:
                self.state.update({"enabled": False, "status": "disabled", "error": ""})
            return
        thread = threading.Thread(target=worker(), args=(reason, model_ids), name=f"yolo-warmup-{reason}", daemon=True)
        thread.start()

