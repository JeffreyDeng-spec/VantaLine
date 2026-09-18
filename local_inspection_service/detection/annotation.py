"""Detection box geometry, rendering and output with explicit image/storage capabilities."""
from collections.abc import Callable
from pathlib import Path
import math
from typing import Any, Protocol
import numpy as np
from .presence_payload import BoundedText

Record = dict[str, Any]
PixelBox = tuple[int, int, int, int]
PixelProjection = Callable[[Any, tuple[int, ...]], PixelBox | None]
BoxDrawing = Callable[[np.ndarray, list[Record], Record], np.ndarray | None]


class AnnotationImages(Protocol):
    IMWRITE_JPEG_QUALITY: int
    LINE_AA: int
    FONT_HERSHEY_SIMPLEX: int

    def imwrite(self, path: str, image: np.ndarray, params: list[int]) -> bool: ...
    def rectangle(self, image: np.ndarray, start: tuple[int, int], end: tuple[int, int],
                  color: tuple[int, int, int], thickness: int, line_type: int = 8) -> np.ndarray: ...
    def getTextSize(self, text: str, font: int, scale: float, thickness: int) -> tuple[tuple[int, int], int]: ...
    def putText(self, image: np.ndarray, text: str, origin: tuple[int, int], font: int,
                scale: float, color: tuple[int, int, int], thickness: int, line_type: int) -> np.ndarray: ...
    def addWeighted(self, first: np.ndarray, alpha: float, second: np.ndarray,
                    beta: float, gamma: float) -> np.ndarray: ...


def normalize_ai_box_2d(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    coords: list[float] = []
    for raw in value:
        if type(raw) not in (int, float):
            return None
        coord = float(raw)
        if not math.isfinite(coord):
            return None
        coords.append(max(0.0, min(1000.0, coord)))
    y_min, x_min, y_max, x_max = coords
    if y_max <= y_min or x_max <= x_min:
        return None
    return [round(coord, 2) for coord in coords]



class DetectionAnnotation:
    def __init__(self, normalize: Callable[[Any], list[float] | None], pixels: Callable[[], PixelProjection],
                 text: Callable[[], BoundedText], images: Callable[[], AnnotationImages],
                 directory: Callable[[str], Path], url: Callable[[Path], str],
                 draw: BoxDrawing, original: Callable[[np.ndarray, str], str]):
        self.normalize, self.pixels, self.text, self.images = normalize, pixels, text, images
        self.directory, self.url, self.draw, self.original = directory, url, draw, original

    def ai_box_2d_to_pixels(self, box_2d: Any, image_shape: tuple[int, ...]) -> tuple[int, int, int, int] | None:
        box = self.normalize(box_2d)
        if not box:
            return None
        h, w = image_shape[:2]
        if h <= 1 or w <= 1:
            return None
        y_min, x_min, y_max, x_max = box
        x1 = max(0, min(w - 1, int(math.floor(x_min / 1000.0 * (w - 1)))))
        y1 = max(0, min(h - 1, int(math.floor(y_min / 1000.0 * (h - 1)))))
        x2 = max(0, min(w - 1, int(math.ceil(x_max / 1000.0 * (w - 1)))))
        y2 = max(0, min(h - 1, int(math.ceil(y_max / 1000.0 * (h - 1)))))
        if x2 <= x1 or y2 <= y1:
            return None
        return x1, y1, x2, y2

    def draw_ai_detection_boxes(self, image_bgr: np.ndarray, detections: list[dict[str, Any]], rule: dict[str, Any]) -> np.ndarray | None:
        boxes: list[tuple[dict[str, Any], tuple[int, int, int, int]]] = []
        for det in detections:
            if not isinstance(det, dict):
                continue
            xyxy = self.pixels()(det.get("box_2d"), image_bgr.shape)
            if xyxy:
                boxes.append((det, xyxy))
        if not boxes:
            return None

        annotated = image_bgr.copy()
        overlay = image_bgr.copy()
        color = (32, 196, 92) if bool(rule.get("passed")) else (40, 180, 255)
        thickness = max(2, int(round(min(image_bgr.shape[:2]) / 220)))
        font_scale = max(0.45, min(0.7, min(image_bgr.shape[:2]) / 640.0))
        font_thickness = max(1, thickness - 1)
        for det, (x1, y1, x2, y2) in boxes:
            self.images().rectangle(overlay, (x1, y1), (x2, y2), color, -1)
            self.images().rectangle(annotated, (x1, y1), (x2, y2), color, thickness, self.images().LINE_AA)
            label = self.text()(det.get("label") or det.get("accessory_id") or "AI", 24)
            try:
                confidence = float(det.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            text = f"{label} {confidence:.2f}" if confidence > 0 else label
            (text_w, text_h), baseline = self.images().getTextSize(text, self.images().FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
            label_y1 = max(0, y1 - text_h - baseline - 6)
            label_y2 = min(image_bgr.shape[0] - 1, label_y1 + text_h + baseline + 6)
            label_x2 = min(image_bgr.shape[1] - 1, x1 + text_w + 10)
            self.images().rectangle(annotated, (x1, label_y1), (label_x2, label_y2), color, -1)
            self.images().putText(
                annotated,
                text,
                (x1 + 5, max(text_h + 2, label_y2 - baseline - 3)),
                self.images().FONT_HERSHEY_SIMPLEX,
                font_scale,
                (255, 255, 255),
                font_thickness,
                self.images().LINE_AA,
            )
        return self.images().addWeighted(overlay, 0.10, annotated, 0.90, 0)

    def write_ai_original_output(self, image_bgr: np.ndarray, request_id: str) -> str:
        out_name = f"{request_id}_ai_original.jpg"
        out_path = self.directory("ai_detection") / out_name
        self.images().imwrite(str(out_path), image_bgr, [int(self.images().IMWRITE_JPEG_QUALITY), 92])
        return self.url(out_path)

    def write_ai_annotated_output(self, image_bgr: np.ndarray, request_id: str, detections: list[dict[str, Any]], rule: dict[str, Any]) -> str:
        annotated = self.draw(image_bgr, detections, rule)
        if annotated is None:
            return self.original(image_bgr, request_id)
        out_name = f"{request_id}_ai_annotated.jpg"
        out_path = self.directory("ai_detection") / out_name
        self.images().imwrite(str(out_path), annotated, [int(self.images().IMWRITE_JPEG_QUALITY), 92])
        return self.url(out_path)
