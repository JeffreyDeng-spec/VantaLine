"""Detection overlays and exact-count banners; always copy the input image."""
from typing import Any
import cv2
import numpy as np


def draw_detections(image_bgr: np.ndarray, detections: list[dict[str, Any]], rule: dict[str, Any]) -> np.ndarray:
    annotated = image_bgr.copy()
    overlay = image_bgr.copy()
    palette = {
        0: (38, 82, 255),
        1: (255, 120, 30),
    }
    for det in detections:
        cls_id = int(det["class_id"])
        color = palette.get(cls_id, (255, 255, 255))
        pts = np.array(det["polygon"], dtype=np.int32)
        cv2.fillPoly(overlay, [pts], color)
        cv2.polylines(annotated, [pts], isClosed=True, color=color, thickness=3, lineType=cv2.LINE_AA)
        x, y = pts[0]
        display_label = det.get("manual_label", det["label"])
        text = f"{display_label} {det['confidence']:.2f}"
        cv2.putText(annotated, text, (int(x), max(int(y) - 8, 22)), cv2.FONT_HERSHEY_SIMPLEX, 0.62, color, 2)

    annotated = cv2.addWeighted(overlay, 0.16, annotated, 0.84, 0)
    banner_color = (42, 150, 75) if rule["passed"] else (48, 60, 220)
    cv2.rectangle(annotated, (0, 0), (annotated.shape[1], 48), banner_color, -1)
    status = "TRUE: exact parts match" if rule["passed"] else "FALSE: count mismatch"
    cv2.putText(annotated, status, (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.82, (255, 255, 255), 2)
    return annotated
