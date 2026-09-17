"""Legacy reference decoding and OCR evidence with explicit process state."""
import json
import threading
from collections.abc import Callable
from typing import Any
import cv2
import numpy as np
from fastapi import HTTPException
from ..incoming_text_inspection import TextObservation, observations_for_rule, local_visual_similarity, comparison_text


def decode_reference(contents: bytes, filename: str) -> tuple[np.ndarray, str]:
    if not contents or len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="标准稿必须为 20MB 以内的单页 PDF/PNG/JPG")
    lower_name = filename.lower()
    if contents.startswith(b"%PDF-"):
        try:
            import fitz
        except ImportError:
            raise HTTPException(status_code=503, detail="PDF 渲染组件尚未安装") from None
        try:
            document = fitz.open(stream=contents, filetype="pdf")
            if document.page_count != 1:
                raise HTTPException(status_code=400, detail="标准稿 PDF 必须只有一页")
            pixmap = document[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = cv2.imdecode(np.frombuffer(pixmap.tobytes("png"), dtype=np.uint8), cv2.IMREAD_COLOR)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="无法解析标准稿 PDF") from None
        return image, ".pdf"
    if not (lower_name.endswith((".png", ".jpg", ".jpeg")) or contents[:8] == b"\x89PNG\r\n\x1a\n" or contents[:2] == b"\xff\xd8"):
        raise HTTPException(status_code=400, detail="标准稿仅支持单页 PDF、PNG 或 JPG")
    image = cv2.imdecode(np.frombuffer(contents, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="标准稿图片解码失败")
    height, width = image.shape[:2]
    if width * height > 40_000_000 or min(width, height) < 200:
        raise HTTPException(status_code=400, detail="标准稿尺寸不符合要求")
    return image, ".png" if contents[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"


def create_paddle_ocr() -> Any:
    from paddleocr import PaddleOCR
    return PaddleOCR(
        # Production is pinned to PaddleOCR/PaddleX 3.7, where the
        # PP-OCRv6 medium profile is registered and preloaded alongside
        # the legacy v6-small path. Geometry is
        # normalized exactly once by rectify_label above so OCR boxes
        # stay in the same canonical coordinate space as field ROIs.
        text_detection_model_name="PP-OCRv6_medium_det",
        text_recognition_model_name="PP-OCRv6_medium_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=True,
    )


class IncomingOCREngine:
    def __init__(self, prepare_runtime: Callable[[], None], factory: Callable[[], Any] = create_paddle_ocr):
        self.prepare_runtime, self.factory = prepare_runtime, factory
        self.lock = threading.RLock()
        self.instance: Any | None = None

    def get(self) -> Any:
        with self.lock:
            if self.instance is None:
                self.prepare_runtime()
                self.instance = self.factory()
            return self.instance


def result_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raw = getattr(value, "json", None)
    if callable(raw):
        raw = raw()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = None
    if isinstance(raw, dict):
        return raw.get("res") if isinstance(raw.get("res"), dict) else raw
    return {}


def observations(image: np.ndarray, engine: Callable[[], Any]) -> list[TextObservation]:
    result_items = engine().predict(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    result = result_mapping(result_items[0] if result_items else {})
    texts = list(result.get("rec_texts") or [])
    scores = list(result.get("rec_scores") or [])
    polygons = list(result.get("rec_polys") or result.get("dt_polys") or [])
    observations: list[TextObservation] = []
    for index, text_value in enumerate(texts):
        text_value = str(text_value)
        if not text_value:
            continue
        polygon_value = polygons[index] if index < len(polygons) else []
        try:
            polygon = tuple((float(point[0]), float(point[1])) for point in polygon_value)
        except (TypeError, ValueError, IndexError):
            polygon = ()
        confidence = float(scores[index]) if index < len(scores) else 0.0
        observations.append(TextObservation(text=text_value, confidence=confidence, polygon=polygon))
    return observations


def corroboration(
    image: np.ndarray, rules: list[dict[str, Any]], observe: Callable[[np.ndarray], list[TextObservation]]
) -> dict[str, list[TextObservation]]:
    """Run the second OCR pass only on critical ROIs and restore global coords."""
    height, width = image.shape[:2]
    by_field: dict[str, list[TextObservation]] = {}
    for rule in rules:
        if rule.get("importance") != "critical":
            continue
        region = rule["region_normalized"]
        padding_x = max(4, int(width * 0.008))
        padding_y = max(4, int(height * 0.008))
        x1 = max(0, int(region["x"] * width) - padding_x)
        y1 = max(0, int(region["y"] * height) - padding_y)
        x2 = min(width, int((region["x"] + region["width"]) * width) + padding_x)
        y2 = min(height, int((region["y"] + region["height"]) * height) + padding_y)
        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            by_field[str(rule["field_id"])] = []
            continue
        translated = []
        for observation in observe(crop):
            translated.append(
                TextObservation(
                    text=observation.text,
                    confidence=observation.confidence,
                    polygon=tuple((x + x1, y + y1) for x, y in observation.polygon),
                )
            )
        by_field[str(rule["field_id"])] = translated
    return by_field


def field_observation(
    rule: dict[str, Any], first: list[TextObservation], second: list[TextObservation], image: np.ndarray, reference_image: np.ndarray
) -> TextObservation | None:
    image_size = (image.shape[1], image.shape[0])
    first_items = observations_for_rule(rule, first, image_size)
    second_items = observations_for_rule(rule, second, image_size)
    first_text = " ".join(item.text for item in first_items)
    second_text = " ".join(item.text for item in second_items)
    if not first_items and not second_items:
        region = rule["region_normalized"]
        x1, y1 = int(region["x"] * image.shape[1]), int(region["y"] * image.shape[0])
        x2 = int((region["x"] + region["width"]) * image.shape[1])
        y2 = int((region["y"] + region["height"]) * image.shape[0])
        roi = image[y1:y2, x1:x2]
        reference_roi = reference_image[y1:y2, x1:x2]
        similarity = local_visual_similarity(reference_image, image, region)
        roi_sharpness = float(cv2.Laplacian(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()) if roi.size else 0.0
        reference_sharpness = float(cv2.Laplacian(cv2.cvtColor(reference_roi, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()) if reference_roi.size else 0.0
        # Absence is automatic only with two successful empty OCR passes plus
        # clear, aligned ROI evidence on both the approved artwork and capture.
        if roi.size and reference_roi.size and roi_sharpness >= 85 and reference_sharpness >= 85 and similarity is not None and similarity < 0.42:
            return TextObservation(text="", confidence=1.0, corroborated=True)
        return None
    confidence = min(
        sum(item.confidence for item in first_items) / max(len(first_items), 1),
        sum(item.confidence for item in second_items) / max(len(second_items), 1),
    )
    polygon = tuple(point for item in first_items for point in item.polygon)
    return TextObservation(
        text=first_text,
        confidence=confidence,
        polygon=polygon,
        corroborated=bool(
            first_items
            and second_items
            and comparison_text(first_text, rule) == comparison_text(second_text, rule)
        ),
    )
