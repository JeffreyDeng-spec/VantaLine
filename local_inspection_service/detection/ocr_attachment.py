"""OCR job selection and original in-place detection enrichment."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
import numpy as np
from .ocr_images import rotate_quarter_turn
from .ocr_scoring import is_confident_manual_classification, better_ocr_result

Record = dict[str, Any]


class Crop(Protocol):
    def __call__(self, image_bgr: np.ndarray, polygon: list[list[float]], padding: int = 20,
                 max_long_side: int = 750) -> tuple[np.ndarray, Record] | None: ...


@dataclass(frozen=True)
class AttachmentDependencies:
    crop: Crop
    score: Callable[[list[np.ndarray], list[int]], list[Record]]
    match: Callable[[list[str], float, Record], Record]
    finalize: Callable[[Record, Record, Record, int], None]


class OCRAttachment:
    def __init__(self, dependencies: AttachmentDependencies):
        self.dependencies = dependencies

    def attach(self, image_bgr: np.ndarray, detections: list[dict[str, Any]], config: dict[str, Any], spec: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if not config.get("ocr", {}).get("enabled", True):
            return detections
        spec = spec or {}
        ocr_config = config.get("ocr", {})
        max_texts = int(ocr_config.get("max_texts_per_manual", 16))
        max_crop_long_side = int(ocr_config.get("max_crop_long_side", 750))
        fallback_min_confidence = float(ocr_config.get("fallback_min_confidence", 0.55))
        if spec.get("is_specialized"):
            ocr_model_class_ids = {int(x) for x in spec.get("ocr_model_class_ids") or []}
        else:
            ocr_model_class_ids = {1}
        jobs = []
        for det in detections:
            if int(det.get("model_class_id", det["class_id"])) not in ocr_model_class_ids:
                continue
            crop_result = self.dependencies.crop(
                image_bgr,
                det["polygon"],
                max_long_side=max_crop_long_side,
            )
            if crop_result is None:
                det["ocr"] = {"manual_type": "unknown", "manual_label": "Unknown Manual", "texts": []}
                continue
            crop, orientation = crop_result
            jobs.append({"det": det, "crop": crop, "orientation": orientation})

        if not jobs:
            return detections

        default_results = self.dependencies.score(
            [job["crop"] for job in jobs],
            [int(job["orientation"]["predicted_rotation"]) for job in jobs],
        )
        fallback_indexes = [
            idx
            for idx, result in enumerate(default_results)
            if not is_confident_manual_classification(result, fallback_min_confidence)
        ]
        if fallback_indexes:
            fallback_results = self.dependencies.score(
                [rotate_quarter_turn(jobs[idx]["crop"], 180) for idx in fallback_indexes],
                [int(jobs[idx]["orientation"]["fallback_rotations"][0]) for idx in fallback_indexes],
            )
            for idx, fallback_result in zip(fallback_indexes, fallback_results):
                fallback_result["fallback_used"] = True
                default_results[idx] = better_ocr_result(default_results[idx], fallback_result)

        for job, ocr_result in zip(jobs, default_results):
            ocr_result.setdefault("fallback_used", False)
            if spec.get("is_specialized"):
                classification = ocr_result["classification"]
                accessory_match = self.dependencies.match(ocr_result["texts"], float(ocr_result["mean_text_score"]), spec)
                job["det"]["ocr"] = {
                    **classification,
                    "best_rotation": ocr_result["rotation"],
                    "orientation": job["orientation"],
                    "fallback_used": ocr_result.get("fallback_used", False),
                    "mean_text_score": ocr_result["mean_text_score"],
                    "texts": ocr_result["texts"][:max_texts],
                    "accessory_match": accessory_match,
                }
                job["det"]["manual_type"] = classification["manual_type"]
                job["det"]["manual_label"] = classification["manual_label"]
                job["det"].setdefault("yolo_accessory_id", job["det"].get("accessory_id"))
                if accessory_match.get("accepted") and accessory_match.get("accessory_id"):
                    resolved_id = str(accessory_match["accessory_id"])
                    label = str(accessory_match.get("label") or spec.get("accessory_labels", {}).get(resolved_id) or resolved_id)
                    job["det"]["resolved_accessory_id"] = resolved_id
                    job["det"]["accessory_id"] = resolved_id
                    job["det"]["label"] = label
                    job["det"]["class_name"] = label
                    job["det"]["resolution_source"] = "ocr"
                else:
                    fallback_id = str(job["det"].get("yolo_accessory_id") or job["det"].get("accessory_id") or "")
                    job["det"]["resolved_accessory_id"] = fallback_id
                    job["det"]["resolution_source"] = f"yolo_fallback_{accessory_match.get('reason') or 'ocr_rejected'}"
            else:
                self.dependencies.finalize(job["det"], ocr_result, job["orientation"], max_texts)
        return detections
