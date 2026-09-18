"""Boxes, segmentation and oriented-box results with explicit label providers."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
import numpy as np

Record = dict[str, Any]


@dataclass(frozen=True)
class DetectionLabels:
    class_names: Callable[[], dict[int, str]]
    class_labels: Callable[[], dict[int, str]]
    generic_names: Callable[[], dict[int, str]]
    generic_labels: Callable[[], dict[int, str]]


class DetectionResults:
    def __init__(self, labels: DetectionLabels,
                 postprocess: Callable[[list[Record], tuple[int, int], Record | None], list[Record]]):
        self.labels, self.postprocess = labels, postprocess

    def names(self, business_cls_id: int, spec: dict[str, Any]) -> tuple[str, str]:
        if spec.get("is_specialized"):
            name = str(spec.get("rule_class_labels", {}).get(business_cls_id) or spec.get("model_class_names", {}).get(business_cls_id, f"class_{business_cls_id}"))
            return name, name
        if spec.get("uses_ocr") and business_cls_id == 1:
            return self.labels.generic_names()[1], self.labels.generic_labels()[1]
        return self.labels.class_names().get(business_cls_id, f"class_{business_cls_id}"), self.labels.class_labels().get(business_cls_id, f"Class {business_cls_id}")

    def parse(self, result: Any, spec: dict[str, Any]) -> list[dict[str, Any]]:
        detections = []
        image_shape = tuple(int(x) for x in result.orig_shape[:2])
        model_to_business = spec["model_to_business_class"]
        model_class_names = spec["model_class_names"]
        model_to_accessory_id = {int(k): str(v) for k, v in (spec.get("model_to_accessory_id") or {}).items()}
        if result.boxes is not None and len(result.boxes) > 0:
            classes = result.boxes.cls.cpu().numpy().astype(int)
            confidences = result.boxes.conf.cpu().numpy()
            if result.masks is not None:
                polygons = list(result.masks.xy)
            else:
                # Detection model (boxes only, no mask): synthesise an axis-aligned
                # rectangle polygon from each xyxy box so the downstream count / OCR /
                # drawing pipeline keeps working unchanged.
                xyxy = result.boxes.xyxy.cpu().numpy()
                polygons = [
                    np.array([[bx1, by1], [bx2, by1], [bx2, by2], [bx1, by2]], dtype=np.float32)
                    for bx1, by1, bx2, by2 in xyxy
                ]
            for model_cls_id, conf, polygon in zip(classes, confidences, polygons):
                business_cls_id = model_to_business.get(int(model_cls_id))
                if business_cls_id is None or len(polygon) < 3:
                    continue
                accessory_id = model_to_accessory_id.get(int(model_cls_id))
                class_name, label = self.names(business_cls_id, spec)
                detections.append(
                    {
                        "class_id": business_cls_id,
                        "accessory_id": accessory_id,
                        "yolo_accessory_id": accessory_id,
                        "resolved_accessory_id": accessory_id,
                        "resolution_source": "yolo",
                        "class_name": class_name,
                        "label": label,
                        "model_class_id": int(model_cls_id),
                        "model_class_name": model_class_names.get(int(model_cls_id), f"class_{int(model_cls_id)}"),
                        "confidence": round(float(conf), 4),
                        "polygon": [[round(float(x), 2), round(float(y), 2)] for x, y in polygon],
                    }
                )
            return self.postprocess(detections, image_shape, spec)

        if result.obb is None or len(result.obb) == 0:
            return []
        polygons = result.obb.xyxyxyxy.cpu().numpy()
        classes = result.obb.cls.cpu().numpy().astype(int)
        confidences = result.obb.conf.cpu().numpy()
        for model_cls_id, conf, polygon in zip(classes, confidences, polygons):
            business_cls_id = model_to_business.get(int(model_cls_id))
            if business_cls_id is None:
                continue
            accessory_id = model_to_accessory_id.get(int(model_cls_id))
            class_name, label = self.names(business_cls_id, spec)
            detections.append(
                {
                    "class_id": business_cls_id,
                    "accessory_id": accessory_id,
                    "yolo_accessory_id": accessory_id,
                    "resolved_accessory_id": accessory_id,
                    "resolution_source": "yolo",
                    "class_name": class_name,
                    "label": label,
                    "model_class_id": int(model_cls_id),
                    "model_class_name": model_class_names.get(int(model_cls_id), f"class_{int(model_cls_id)}"),
                    "confidence": round(float(conf), 4),
                    "polygon": [[round(float(x), 2), round(float(y), 2)] for x, y in polygon],
                }
            )
        return self.postprocess(detections, image_shape, spec)
