"""Local warmup prediction parameters, preserving the existing dummy image contract."""
from collections.abc import Callable
from typing import Any, Protocol
import numpy as np

Record = dict[str, Any]


class Predictor(Protocol):
    def predict(self, source: np.ndarray, **kwargs: Any) -> Any: ...


class WarmupPrediction:
    def __init__(self, select: Callable[[str, Record], Record], load: Callable[[], Callable[[str, Record], Predictor]],
                 device: Callable[[], str | int]):
        self.select, self.load, self.device = select, load, device

    def warm_yolo_model_once(self, model_id: str, config: dict[str, Any]) -> None:
        spec = self.select(model_id, config)
        if spec.get("is_ai_detection") or spec.get("is_label_sheet_match"):
            return
        yolo_model = self.load()(str(spec["id"]), config)
        dummy = np.zeros((96, 96, 3), dtype=np.uint8)
        try:
            imgsz = max(320, min(1280, int(config.get("image_size") or 640)))
        except (TypeError, ValueError):
            imgsz = 640
        try:
            confidence_threshold = max(0.001, min(0.99, float(spec.get("confidence_threshold", config.get("confidence_threshold", 0.25)))))
        except (TypeError, ValueError):
            confidence_threshold = 0.25
        yolo_model.predict(
            dummy,
            imgsz=imgsz,
            device=self.device(),
            conf=confidence_threshold,
            verbose=False,
        )

