import json
import os
import re
import shutil
import time
import uuid
import ctypes
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ultralytics import YOLO


ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
APP_DIR = ROOT / "local_inspection_service"
STATIC_DIR = APP_DIR / "static"
DATA_DIR = APP_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
CONFIG_PATH = DATA_DIR / "config.json"
LEGACY_MODEL_PATH = (
    ROOT
    / "yolo26_seg_2class_visible_polygon_4000_full_rotation_trial"
    / "runs"
    / "yolo26s_seg_2class_visible_polygon_full_rotation_100e_img640_workers0"
    / "weights"
    / "best.pt"
)
REPO_MODEL_PATH = ROOT / "models" / "current_2class_yolo26s_seg_best.pt"
MODEL_PATH = Path(os.environ.get("INSPECTION_MODEL_PATH", REPO_MODEL_PATH if REPO_MODEL_PATH.exists() else LEGACY_MODEL_PATH))
FIVE_CLASS_MODEL_PATH = ROOT / "models" / "current_5class_yolo26s_seg_best.pt"

MODEL_CLASS_NAMES = {
    0: "bottle",
    1: "manual",
}

MODEL_TO_BUSINESS_CLASS = {
    0: 0,
    1: 1,
}

CLASS_NAMES = {
    0: "bottle",
    1: "warranty_service_manual",
    2: "battery_instruction_manual",
    3: "download_service_manual",
    4: "service_qr_manual",
}

CLASS_LABELS = {
    0: "Bottle",
    1: "Warranty Service Manual",
    2: "Battery Instruction Manual",
    3: "Download Service Manual",
    4: "Service QR Manual",
}

GENERIC_DETECTION_CLASS_NAMES = {
    0: "bottle",
    1: "manual",
    99: "manual_unknown",
}

GENERIC_DETECTION_LABELS = {
    0: "Bottle",
    1: "Manual",
    99: "Unknown Manual",
}

DEFAULT_MODEL_ID = "yolo26_2class_ocr"
MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "yolo26_5class_direct": {
        "id": "yolo26_5class_direct",
        "label": "YOLO26",
        "description": "直接检测 Bottle 和四类说明书，不经过 OCR。",
        "path": FIVE_CLASS_MODEL_PATH,
        "uses_ocr": False,
        "model_class_names": CLASS_NAMES,
        "model_to_business_class": {idx: idx for idx in CLASS_NAMES},
    },
    DEFAULT_MODEL_ID: {
        "id": DEFAULT_MODEL_ID,
        "label": "YOLO26 + PaddleOCR",
        "description": "先检测 bottle/manual，再用 PaddleOCR 将说明书分成四类。",
        "path": MODEL_PATH,
        "uses_ocr": True,
        "model_class_names": MODEL_CLASS_NAMES,
        "model_to_business_class": MODEL_TO_BUSINESS_CLASS,
    },
}

DEFAULT_CONFIG: dict[str, Any] = {
    "model_path": str(MODEL_PATH),
    "active_model_id": DEFAULT_MODEL_ID,
    "image_size": 640,
    "confidence_threshold": 0.25,
    "required_classes": [0, 1, 2, 3, 4],
    "min_counts": {"0": 1, "1": 1, "2": 1, "3": 1, "4": 1},
    "ocr": {
        "enabled": True,
        "require_manual_types": False,
        "manual_types": [
            "warranty_service",
            "battery_instruction",
            "download_service",
            "service_qr",
        ],
        "max_texts_per_manual": 16,
        "max_crop_long_side": 750,
        "fallback_min_confidence": 0.55,
    },
    "video": {"sample_every_seconds": 1.0, "max_frames": 80},
    "stream": {"enabled": False, "source": "camera", "url": "", "status": "reserved"},
    "accessories": [
        {"class_id": idx, "name": CLASS_LABELS[idx], "status": "active", "source_files": []}
        for idx in CLASS_NAMES
    ],
    "training": {
        "status": "idle",
        "last_requested_at": None,
        "note": "Prototype hook. Dataset generation and training can be wired to the existing synthetic pipeline.",
    },
}


for path in (UPLOAD_DIR, OUTPUT_DIR, DATA_DIR):
    path.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Assembly Line Local Inspection Service")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

_models: dict[str, YOLO] = {}
_ocr: Any | None = None

MANUAL_TYPE_LABELS = {
    "warranty_service": "Warranty Service Manual",
    "battery_instruction": "Battery Instruction Manual",
    "download_service": "Download Service Manual",
    "service_qr": "Service QR Manual",
}

MANUAL_TYPE_CLASS_IDS = {
    "warranty_service": 1,
    "battery_instruction": 2,
    "download_service": 3,
    "service_qr": 4,
}

MANUAL_TYPE_KEYWORDS: dict[str, list[tuple[str, int]]] = {
    "warranty_service": [
        ("warranty", 8),
        ("service conditions", 8),
        ("garantie", 5),
        ("garantia", 5),
        ("garancija", 5),
        ("garanti", 4),
        ("warunki gwarancji", 5),
        ("servicebetingelser", 5),
        ("condiciones de servicio", 5),
    ],
    "battery_instruction": [
        ("ge-ps", 10),
        ("cordless", 7),
        ("branch chainsaw", 9),
        ("chainsaw", 6),
        ("akku", 6),
        ("battery", 6),
        ("operating instructions", 5),
        ("original operating", 5),
        ("motosega", 5),
        ("potatura", 4),
        ("batteridriven", 5),
        ("podadora", 4),
        ("elagueuse", 4),
    ],
    "download_service": [
        ("download", 10),
        ("downloading", 10),
        ("download bereit", 8),
        ("full operating instructions", 9),
        ("detailed", 7),
        ("detailed instruction", 8),
        ("detailed manual", 8),
        ("telechargeable", 6),
        ("scaricabili", 6),
        ("descargarse", 6),
        ("ladda ned", 6),
        ("allalaadimiseks", 5),
        ("descargat", 5),
    ],
    "service_qr": [
        ("larger format", 10),
        ("larger", 7),
        ("bigger", 7),
        ("einhell service", 9),
        ("eschenstrabe", 10),
        ("eschenstrasse", 10),
        ("landau", 8),
        ("09951", 10),
        ("service-de", 10),
        ("larger instructions", 8),
        ("larger manual", 8),
        ("format plus grand", 6),
        ("grobere anleitung", 8),
        ("gröbere anleitung", 8),
    ],
}


class RuleConfig(BaseModel):
    confidence_threshold: float
    required_classes: list[int]
    min_counts: dict[str, int]


class StreamConfig(BaseModel):
    enabled: bool = False
    source: str = "camera"
    url: str = ""


def ensure_dirs() -> None:
    for path in (UPLOAD_DIR, OUTPUT_DIR, DATA_DIR):
        path.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)


def load_config() -> dict[str, Any]:
    ensure_dirs()
    try:
        current = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        current = {}
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    for key, value in current.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def save_config(config: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def selected_model_spec(model_id: str | None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    requested = model_id or (config or {}).get("active_model_id") or DEFAULT_MODEL_ID
    if requested not in MODEL_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown model_id: {requested}")
    return MODEL_REGISTRY[requested]


def model(model_id: str | None = None, config: dict[str, Any] | None = None) -> YOLO:
    spec = selected_model_spec(model_id, config)
    model_id = str(spec["id"])
    model_path = Path(spec["path"])
    if model_id not in _models:
        if not model_path.exists():
            raise RuntimeError(f"Model file not found: {model_path}")
        _models[model_id] = YOLO(str(model_path))
    return _models[model_id]


def prepare_paddle_runtime() -> None:
    os.environ.setdefault("FLAGS_use_mkldnn", "false")
    os.environ.setdefault("FLAGS_use_onednn", "false")
    os.environ.setdefault("FLAGS_enable_pir_api", "0")
    libgomp = Path("/home/dministrator/.local/lib/python3.12/site-packages/torch/lib/libgomp.so.1")
    if libgomp.exists():
        try:
            ctypes.CDLL(str(libgomp), mode=ctypes.RTLD_GLOBAL)
        except OSError:
            pass


def ocr_engine() -> Any:
    global _ocr
    if _ocr is None:
        prepare_paddle_runtime()
        from paddleocr import PaddleOCR

        _ocr = PaddleOCR(
            lang="en",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=True,
        )
    return _ocr


def safe_name(filename: str) -> str:
    stem = Path(filename).stem.replace(" ", "_")[:80] or "upload"
    suffix = Path(filename).suffix.lower() or ".bin"
    return f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{stem}{suffix}"


def polygon_overlap_ratio(poly_a: list[list[float]], poly_b: list[list[float]]) -> float:
    pts_a = np.array(poly_a, dtype=np.float32)
    pts_b = np.array(poly_b, dtype=np.float32)
    area_a = float(cv2.contourArea(pts_a))
    area_b = float(cv2.contourArea(pts_b))
    if area_a <= 0 or area_b <= 0:
        return 0.0
    intersection_area, _ = cv2.intersectConvexConvex(pts_a, pts_b)
    return float(intersection_area) / min(area_a, area_b)


def polygon_area(poly: list[list[float]]) -> float:
    return abs(float(cv2.contourArea(np.array(poly, dtype=np.float32))))


def polygon_bbox(poly: list[list[float]]) -> tuple[float, float, float, float]:
    pts = np.array(poly, dtype=np.float32)
    xs = pts[:, 0]
    ys = pts[:, 1]
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def bbox_gap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    dx = max(bx1 - ax2, ax1 - bx2, 0)
    dy = max(by1 - ay2, ay1 - by2, 0)
    return float((dx * dx + dy * dy) ** 0.5)


def bbox_overlap_ratio(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(ix2 - ix1, 0), max(iy2 - iy1, 0)
    inter = iw * ih
    area_a = max((ax2 - ax1) * (ay2 - ay1), 1)
    area_b = max((bx2 - bx1) * (by2 - by1), 1)
    return float(inter / min(area_a, area_b))


def normalize_ocr_text(text: str) -> str:
    text = text.lower()
    replacements = {
        "ä": "a",
        "ö": "o",
        "ü": "u",
        "ß": "ss",
        "é": "e",
        "è": "e",
        "ê": "e",
        "á": "a",
        "à": "a",
        "í": "i",
        "ó": "o",
        "ç": "c",
        "ğ": "g",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9@./+ -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def classify_manual_text(texts: list[str]) -> dict[str, Any]:
    joined = normalize_ocr_text(" ".join(texts))
    scores: dict[str, int] = {}
    matches: dict[str, list[str]] = {}
    for manual_type, keywords in MANUAL_TYPE_KEYWORDS.items():
        score = 0
        hit_list = []
        for keyword, weight in keywords:
            key = normalize_ocr_text(keyword)
            if key and key in joined:
                score += weight
                hit_list.append(keyword)
        scores[manual_type] = score
        matches[manual_type] = hit_list

    best_type, best_score = max(scores.items(), key=lambda item: item[1])
    second_score = max((score for key, score in scores.items() if key != best_type), default=0)
    if best_score < 6 or best_score - second_score < 2:
        best_type = "unknown"
    confidence = 0.0 if best_type == "unknown" else min(1.0, best_score / max(best_score + second_score, 1))
    return {
        "manual_type": best_type,
        "manual_label": MANUAL_TYPE_LABELS.get(best_type, "Unknown Manual"),
        "confidence": round(confidence, 4),
        "scores": scores,
        "matches": matches.get(best_type, []),
    }


def rotate_quarter_turn(image_bgr: np.ndarray, angle: int) -> np.ndarray:
    normalized = int(angle) % 360
    if normalized == 0:
        return image_bgr
    if normalized == 90:
        return cv2.rotate(image_bgr, cv2.ROTATE_90_CLOCKWISE)
    if normalized == 180:
        return cv2.rotate(image_bgr, cv2.ROTATE_180)
    if normalized == 270:
        return cv2.rotate(image_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError(f"angle must be a quarter turn, got {angle}")


def resize_for_ocr(crop_bgr: np.ndarray, max_long_side: int) -> np.ndarray:
    if max_long_side <= 0:
        return crop_bgr
    height, width = crop_bgr.shape[:2]
    long_side = max(height, width)
    if long_side <= max_long_side:
        return crop_bgr
    scale = max_long_side / long_side
    return cv2.resize(
        crop_bgr,
        (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA,
    )


def crop_detection_region(
    image_bgr: np.ndarray,
    polygon: list[list[float]],
    padding: int = 20,
    max_long_side: int = 750,
) -> tuple[np.ndarray, dict[str, Any]] | None:
    height, width = image_bgr.shape[:2]
    pts = np.array(polygon, dtype=np.float32)
    if len(pts) < 3:
        return None
    x1 = max(0, int(np.floor(pts[:, 0].min())) - padding)
    y1 = max(0, int(np.floor(pts[:, 1].min())) - padding)
    x2 = min(width, int(np.ceil(pts[:, 0].max())) + padding)
    y2 = min(height, int(np.ceil(pts[:, 1].max())) + padding)
    if x2 <= x1 or y2 <= y1:
        return None
    crop = image_bgr[y1:y2, x1:x2]
    shifted = pts.copy()
    shifted[:, 0] -= x1
    shifted[:, 1] -= y1
    mask = np.zeros(crop.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [np.round(shifted).astype(np.int32)], 255)
    white = np.full_like(crop, 255)
    masked = np.where(mask[:, :, None] > 0, crop, white)

    rect = cv2.minAreaRect(shifted)
    rect_width, rect_height = rect[1]
    long_edge_angle = 0.0
    if rect_width > 0 and rect_height > 0:
        box = cv2.boxPoints(rect)
        edges = []
        for idx in range(4):
            p1 = box[idx]
            p2 = box[(idx + 1) % 4]
            vector = p2 - p1
            length = float(np.linalg.norm(vector))
            angle = float(np.degrees(np.arctan2(vector[1], vector[0])))
            edges.append((length, angle))
        long_edge_angle = max(edges, key=lambda item: item[0])[1]

    # Manuals are portrait documents. Rotate to make the long edge vertical,
    # using only a single quarter-turn before the default OCR pass.
    correction = int(round((90.0 - long_edge_angle) / 90.0) * 90) % 360
    if correction == 0 and 35.0 <= abs(long_edge_angle) <= 75.0:
        correction = 180
    oriented = rotate_quarter_turn(masked, correction)
    oriented = resize_for_ocr(oriented, max_long_side)
    return oriented, {
        "long_edge_angle": round(long_edge_angle, 2),
        "predicted_rotation": correction,
        "fallback_rotations": [(correction + 180) % 360],
    }


def build_ocr_result(result: dict[str, Any], rotation: int) -> dict[str, Any]:
    texts = [str(x) for x in result.get("rec_texts", []) if str(x).strip()]
    rec_scores = [float(x) for x in result.get("rec_scores", [])]
    mean_score = sum(rec_scores) / len(rec_scores) if rec_scores else 0.0
    return {
        "texts": texts,
        "mean_text_score": round(mean_score, 4),
        "rotation": int(rotation) % 360,
        "classification": classify_manual_text(texts),
    }


def score_ocr_variant(crop_bgr: np.ndarray, rotation: int) -> dict[str, Any]:
    try:
        result = ocr_engine().predict(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))[0]
    except Exception:
        result = {}
    return build_ocr_result(result, rotation)


def score_ocr_variants(crops_bgr: list[np.ndarray], rotations: list[int]) -> list[dict[str, Any]]:
    if not crops_bgr:
        return []
    try:
        batch = [cv2.cvtColor(crop, cv2.COLOR_BGR2RGB) for crop in crops_bgr]
        results = ocr_engine().predict(batch)
        return [build_ocr_result(result or {}, rotation) for result, rotation in zip(results, rotations)]
    except Exception:
        return [score_ocr_variant(crop, rotation) for crop, rotation in zip(crops_bgr, rotations)]


def is_confident_manual_classification(ocr_result: dict[str, Any], min_confidence: float) -> bool:
    classification = ocr_result["classification"]
    return classification["manual_type"] != "unknown" and float(classification["confidence"]) >= min_confidence


def better_ocr_result(current: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    current_class_score = max(current["classification"]["scores"].values(), default=0)
    candidate_class_score = max(candidate["classification"]["scores"].values(), default=0)
    if (
        candidate_class_score,
        len(candidate["texts"]),
        candidate["mean_text_score"],
    ) > (
        current_class_score,
        len(current["texts"]),
        current["mean_text_score"],
    ):
        return candidate
    return current


def run_ocr_on_crop(
    crop_bgr: np.ndarray,
    orientation: dict[str, Any],
    fallback_min_confidence: float,
) -> dict[str, Any]:
    best = score_ocr_variant(crop_bgr, int(orientation["predicted_rotation"]))
    fallback_used = False
    if not is_confident_manual_classification(best, fallback_min_confidence):
        for fallback_rotation in orientation.get("fallback_rotations", []):
            fallback_crop = rotate_quarter_turn(crop_bgr, 180)
            candidate = score_ocr_variant(fallback_crop, int(fallback_rotation))
            fallback_used = True
            best = better_ocr_result(best, candidate)
            if is_confident_manual_classification(best, fallback_min_confidence):
                break
    best["fallback_used"] = fallback_used
    best["orientation"] = orientation
    return best


def finalize_ocr_detection(
    det: dict[str, Any],
    ocr_result: dict[str, Any],
    orientation: dict[str, Any],
    max_texts: int,
) -> None:
    classification = ocr_result["classification"]
    det["ocr"] = {
        **classification,
        "best_rotation": ocr_result["rotation"],
        "predicted_rotation": orientation["predicted_rotation"],
        "long_edge_angle": orientation["long_edge_angle"],
        "fallback_used": ocr_result.get("fallback_used", False),
        "mean_text_score": ocr_result["mean_text_score"],
        "texts": ocr_result["texts"][:max_texts],
    }
    if classification["manual_type"] != "unknown":
        manual_type = classification["manual_type"]
        class_id = MANUAL_TYPE_CLASS_IDS[manual_type]
        det["class_id"] = class_id
        det["class_name"] = CLASS_NAMES[class_id]
        det["label"] = CLASS_LABELS[class_id]
        det["manual_type"] = manual_type
        det["manual_label"] = classification["manual_label"]
    else:
        det["class_id"] = 99
        det["class_name"] = GENERIC_DETECTION_CLASS_NAMES[99]
        det["label"] = GENERIC_DETECTION_LABELS[99]


def attach_ocr_results(image_bgr: np.ndarray, detections: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    if not config.get("ocr", {}).get("enabled", True):
        return detections
    ocr_config = config.get("ocr", {})
    max_texts = int(ocr_config.get("max_texts_per_manual", 16))
    max_crop_long_side = int(ocr_config.get("max_crop_long_side", 750))
    fallback_min_confidence = float(ocr_config.get("fallback_min_confidence", 0.55))
    jobs = []
    for det in detections:
        if int(det.get("model_class_id", det["class_id"])) != 1:
            continue
        crop_result = crop_detection_region(
            image_bgr,
            det["polygon"],
            max_long_side=max_crop_long_side,
        )
        if crop_result is None:
            det["ocr"] = {"manual_type": "unknown", "manual_label": "Unknown Manual", "texts": []}
            continue
        crop, orientation = crop_result
        jobs.append({"det": det, "crop": crop, "orientation": orientation})

    default_results = score_ocr_variants(
        [job["crop"] for job in jobs],
        [int(job["orientation"]["predicted_rotation"]) for job in jobs],
    )
    fallback_indexes = [
        idx
        for idx, result in enumerate(default_results)
        if not is_confident_manual_classification(result, fallback_min_confidence)
    ]
    if fallback_indexes:
        fallback_results = score_ocr_variants(
            [rotate_quarter_turn(jobs[idx]["crop"], 180) for idx in fallback_indexes],
            [int(jobs[idx]["orientation"]["fallback_rotations"][0]) for idx in fallback_indexes],
        )
        for idx, fallback_result in zip(fallback_indexes, fallback_results):
            fallback_result["fallback_used"] = True
            default_results[idx] = better_ocr_result(default_results[idx], fallback_result)

    for job, ocr_result in zip(jobs, default_results):
        ocr_result.setdefault("fallback_used", False)
        finalize_ocr_detection(job["det"], ocr_result, job["orientation"], max_texts)
    return detections


def filter_detections(detections: list[dict[str, Any]], image_shape: tuple[int, int]) -> list[dict[str, Any]]:
    height, width = image_shape
    image_area = max(height * width, 1)
    filtered = []
    for det in detections:
        area = polygon_area(det["polygon"])
        det["area_px"] = round(area, 2)
        cls_id = int(det["class_id"])
        confidence = float(det["confidence"])
        area_ratio = area / image_area
        if cls_id == 0 and (
            confidence < 0.55
            or area_ratio < 0.0015
            or (area_ratio < 0.003 and confidence < 0.85)
        ):
            continue
        if cls_id in (1, 2, 3, 4, 99) and (confidence < 0.30 or area_ratio < 0.006):
            continue
        filtered.append(det)
    return filtered


def dedupe_detections(
    detections: list[dict[str, Any]],
    overlap_threshold: float = 0.08,
    adjacent_gap_px: float = 42.0,
    absorb_area_ratio: float = 0.22,
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for det in sorted(detections, key=lambda item: float(item["confidence"]), reverse=True):
        cls_id = int(det["class_id"])
        det_area = polygon_area(det["polygon"])
        det_bbox = polygon_bbox(det["polygon"])
        duplicate = False
        for other in kept:
            if int(other["class_id"]) != cls_id:
                continue
            other_area = polygon_area(other["polygon"])
            other_bbox = polygon_bbox(other["polygon"])
            min_area = max(min(det_area, other_area), 1)
            max_area = max(det_area, other_area, 1)
            overlap = bbox_overlap_ratio(det_bbox, other_bbox)
            close = bbox_gap(det_bbox, other_bbox) <= adjacent_gap_px
            small_fragment = min_area / max_area <= absorb_area_ratio
            near_small_fragment = cls_id == 1 and small_fragment and (overlap >= overlap_threshold or close)
            low_conf_adjacent_manual = (
                cls_id == 1
                and close
                and max(det_area, other_area) < 250000
                and float(det["confidence"]) < 0.55
                and float(other["confidence"]) < 0.55
            )
            near_duplicate = small_fragment and overlap >= 0.65
            if near_small_fragment or low_conf_adjacent_manual or near_duplicate:
                duplicate = True
                break
        if not duplicate:
            kept.append(det)
    return kept


def postprocess_detections(detections: list[dict[str, Any]], image_shape: tuple[int, int]) -> list[dict[str, Any]]:
    return dedupe_detections(filter_detections(detections, image_shape))


def detection_names_for_business_class(business_cls_id: int, spec: dict[str, Any]) -> tuple[str, str]:
    if spec.get("uses_ocr") and business_cls_id == 1:
        return GENERIC_DETECTION_CLASS_NAMES[1], GENERIC_DETECTION_LABELS[1]
    return CLASS_NAMES.get(business_cls_id, f"class_{business_cls_id}"), CLASS_LABELS.get(business_cls_id, f"Class {business_cls_id}")


def parse_detections(result: Any, spec: dict[str, Any]) -> list[dict[str, Any]]:
    detections = []
    image_shape = tuple(int(x) for x in result.orig_shape[:2])
    model_to_business = spec["model_to_business_class"]
    model_class_names = spec["model_class_names"]
    if result.masks is not None and result.boxes is not None and len(result.boxes) > 0:
        classes = result.boxes.cls.cpu().numpy().astype(int)
        confidences = result.boxes.conf.cpu().numpy()
        polygons = result.masks.xy
        for model_cls_id, conf, polygon in zip(classes, confidences, polygons):
            business_cls_id = model_to_business.get(int(model_cls_id))
            if business_cls_id is None or len(polygon) < 3:
                continue
            class_name, label = detection_names_for_business_class(business_cls_id, spec)
            detections.append(
                {
                    "class_id": business_cls_id,
                    "class_name": class_name,
                    "label": label,
                    "model_class_id": int(model_cls_id),
                    "model_class_name": model_class_names.get(int(model_cls_id), f"class_{int(model_cls_id)}"),
                    "confidence": round(float(conf), 4),
                    "polygon": [[round(float(x), 2), round(float(y), 2)] for x, y in polygon],
                }
            )
        return postprocess_detections(detections, image_shape)

    if result.obb is None or len(result.obb) == 0:
        return []
    polygons = result.obb.xyxyxyxy.cpu().numpy()
    classes = result.obb.cls.cpu().numpy().astype(int)
    confidences = result.obb.conf.cpu().numpy()
    for model_cls_id, conf, polygon in zip(classes, confidences, polygons):
        business_cls_id = model_to_business.get(int(model_cls_id))
        if business_cls_id is None:
            continue
        class_name, label = detection_names_for_business_class(business_cls_id, spec)
        detections.append(
            {
                "class_id": business_cls_id,
                "class_name": class_name,
                "label": label,
                "model_class_id": int(model_cls_id),
                "model_class_name": model_class_names.get(int(model_cls_id), f"class_{int(model_cls_id)}"),
                "confidence": round(float(conf), 4),
                "polygon": [[round(float(x), 2), round(float(y), 2)] for x, y in polygon],
            }
        )
    return postprocess_detections(detections, image_shape)


def apply_rule(detections: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    threshold = float(config["confidence_threshold"])
    required = [int(x) for x in config["required_classes"]]
    min_counts = {int(k): int(v) for k, v in config["min_counts"].items()}
    count_by_class: Counter[int] = Counter()
    max_conf_by_class: defaultdict[int, float] = defaultdict(float)
    for det in detections:
        cls_id = int(det["class_id"])
        conf = float(det["confidence"])
        if conf >= threshold:
            count_by_class[cls_id] += 1
            max_conf_by_class[cls_id] = max(max_conf_by_class[cls_id], conf)

    missing = []
    present = []
    for cls_id in required:
        need = min_counts.get(cls_id, 1)
        found = count_by_class.get(cls_id, 0)
        row = {
            "class_id": cls_id,
            "label": CLASS_LABELS.get(cls_id, f"Class {cls_id}"),
            "required": need,
            "found": found,
            "max_confidence": round(max_conf_by_class.get(cls_id, 0.0), 4),
        }
        if found >= need:
            present.append(row)
        else:
            missing.append(row)

    manual_type_counts: Counter[str] = Counter()
    for det in detections:
        if int(det["class_id"]) == 1:
            manual_type = det.get("manual_type") or det.get("ocr", {}).get("manual_type")
            if manual_type and manual_type != "unknown":
                manual_type_counts[str(manual_type)] += 1

    ocr_config = config.get("ocr", {})
    required_manual_types = [str(x) for x in ocr_config.get("manual_types", MANUAL_TYPE_LABELS.keys())]
    manual_type_missing = []
    manual_type_present = []
    if ocr_config.get("enabled", True) and ocr_config.get("require_manual_types", True):
        for manual_type in required_manual_types:
            row = {
                "manual_type": manual_type,
                "label": MANUAL_TYPE_LABELS.get(manual_type, manual_type),
                "required": 1,
                "found": manual_type_counts.get(manual_type, 0),
            }
            if row["found"] >= 1:
                manual_type_present.append(row)
            else:
                manual_type_missing.append(row)

    passed = len(missing) == 0 and len(manual_type_missing) == 0
    return {
        "passed": passed,
        "threshold": threshold,
        "present": present,
        "missing": missing,
        "counts": {CLASS_LABELS.get(k, str(k)): v for k, v in sorted(count_by_class.items())},
        "ocr_enabled": bool(ocr_config.get("enabled", True)),
        "manual_type_counts": {
            MANUAL_TYPE_LABELS.get(k, k): v for k, v in sorted(manual_type_counts.items())
        },
        "manual_type_present": manual_type_present,
        "manual_type_missing": manual_type_missing,
    }


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
    status = "TRUE: required parts present" if rule["passed"] else "FALSE: missing required parts"
    cv2.putText(annotated, status, (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.82, (255, 255, 255), 2)
    return annotated


def analyze_bgr(image_bgr: np.ndarray, request_id: str, model_id: str | None = None) -> dict[str, Any]:
    config = load_config()
    spec = selected_model_spec(model_id, config)
    result = model(str(spec["id"]), config).predict(image_bgr, imgsz=int(config["image_size"]), device=0, verbose=False)[0]
    detections = parse_detections(result, spec)
    if spec.get("uses_ocr", False):
        detections = attach_ocr_results(image_bgr, detections, config)
    rule = apply_rule(detections, config)
    annotated = draw_detections(image_bgr, detections, rule)
    out_name = f"{request_id}_annotated.jpg"
    out_path = OUTPUT_DIR / out_name
    cv2.imwrite(str(out_path), annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    return {
        "request_id": request_id,
        "passed": rule["passed"],
        "model": {
            "id": spec["id"],
            "label": spec["label"],
            "uses_ocr": bool(spec.get("uses_ocr", False)),
        },
        "rule": rule,
        "detections": detections,
        "annotated_url": f"/outputs/{out_name}",
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/api/status")
def status() -> dict[str, Any]:
    config = load_config()
    active_spec = selected_model_spec(None, config)
    available_models = []
    for spec in MODEL_REGISTRY.values():
        path = Path(spec["path"])
        available_models.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "description": spec["description"],
                "uses_ocr": bool(spec.get("uses_ocr", False)),
                "path": str(path),
                "exists": path.exists(),
            }
        )
    return {
        "service": "running",
        "model_exists": Path(active_spec["path"]).exists(),
        "model_path": str(active_spec["path"]),
        "active_model_id": active_spec["id"],
        "available_models": available_models,
        "classes": [{"class_id": k, "name": v, "label": CLASS_LABELS[k]} for k, v in CLASS_NAMES.items()],
        "rule": {
            "confidence_threshold": config["confidence_threshold"],
            "required_classes": config["required_classes"],
            "min_counts": config["min_counts"],
        },
        "ocr": config.get("ocr", {}),
    }


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return load_config()


@app.post("/api/config/rules")
def update_rules(rule: RuleConfig) -> dict[str, Any]:
    if not 0.0 <= rule.confidence_threshold <= 1.0:
        raise HTTPException(status_code=400, detail="confidence_threshold must be between 0 and 1")
    unknown = [cls for cls in rule.required_classes if cls not in CLASS_NAMES]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown class IDs: {unknown}")
    config = load_config()
    config["confidence_threshold"] = rule.confidence_threshold
    config["required_classes"] = rule.required_classes
    config["min_counts"] = {str(k): max(1, int(v)) for k, v in rule.min_counts.items()}
    save_config(config)
    return {"status": "saved", "rule": config}


@app.get("/api/accessories")
def get_accessories() -> dict[str, Any]:
    return {"items": load_config()["accessories"]}


@app.post("/api/accessories")
async def add_accessory(
    name: str = Form(...),
    class_id: int = Form(...),
    files: list[UploadFile] = File(default=[]),
) -> dict[str, Any]:
    if class_id not in CLASS_NAMES:
        raise HTTPException(status_code=400, detail="class_id must match an existing model class in this prototype")
    saved_files = []
    target_dir = UPLOAD_DIR / "accessories" / str(class_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    for upload in files:
        path = target_dir / safe_name(upload.filename)
        with path.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        saved_files.append(str(path))

    config = load_config()
    config["accessories"].append(
        {
            "class_id": class_id,
            "name": name,
            "status": "draft_reference_uploaded",
            "source_files": saved_files,
            "created_at": int(time.time()),
        }
    )
    save_config(config)
    return {"status": "saved", "item": config["accessories"][-1]}


@app.post("/api/analyze/image")
async def analyze_image(file: UploadFile = File(...), model_id: str | None = Form(None)) -> dict[str, Any]:
    ensure_dirs()
    payload = await file.read()
    arr = np.frombuffer(payload, np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Could not decode image")
    request_id = safe_name(file.filename).rsplit(".", 1)[0]
    (UPLOAD_DIR / f"{request_id}{Path(file.filename).suffix.lower() or '.png'}").write_bytes(payload)
    return analyze_bgr(image, request_id, model_id)


@app.post("/api/analyze/video")
async def analyze_video(file: UploadFile = File(...), model_id: str | None = Form(None)) -> dict[str, Any]:
    ensure_dirs()
    upload_name = safe_name(file.filename)
    video_path = UPLOAD_DIR / upload_name
    with video_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    config = load_config()
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise HTTPException(status_code=400, detail="Could not open video")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    stride = max(1, int(fps * float(config["video"]["sample_every_seconds"])))
    max_frames = int(config["video"]["max_frames"])
    frames = []
    idx = 0
    sampled = 0
    first_preview_url = None
    while sampled < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % stride == 0:
            request_id = f"{Path(upload_name).stem}_frame_{idx:06d}"
            result = analyze_bgr(frame, request_id, model_id)
            if first_preview_url is None:
                first_preview_url = result["annotated_url"]
            frames.append(
                {
                    "frame_index": idx,
                    "timestamp_seconds": round(idx / fps, 3),
                    "passed": result["passed"],
                    "missing": result["rule"]["missing"],
                    "detections": len(result["detections"]),
                }
            )
            sampled += 1
        idx += 1
    cap.release()

    passed_frames = sum(1 for frame in frames if frame["passed"])
    overall = len(frames) > 0 and passed_frames == len(frames)
    return {
        "request_id": Path(upload_name).stem,
        "passed": overall,
        "sampled_frames": len(frames),
        "passed_frames": passed_frames,
        "pass_rate": round(passed_frames / len(frames), 4) if frames else 0.0,
        "preview_url": first_preview_url,
        "frames": frames[:200],
    }


@app.post("/api/stream/config")
def update_stream(config_in: StreamConfig) -> dict[str, Any]:
    config = load_config()
    config["stream"] = {
        "enabled": config_in.enabled,
        "source": config_in.source,
        "url": config_in.url,
        "status": "reserved_for_camera_or_rtsp_input",
    }
    save_config(config)
    return {"status": "saved", "stream": config["stream"]}


@app.post("/api/training/start")
def request_training() -> dict[str, Any]:
    config = load_config()
    config["training"] = {
        "status": "requested",
        "last_requested_at": int(time.time()),
        "note": "Prototype only: wire this hook to synthetic data generation and YOLO training when the new accessory pipeline is finalized.",
        "command_preview": "python scripts/build_yolo26_obb_dataset.py && yolo obb train ...",
    }
    save_config(config)
    return config["training"]


@app.get("/api/training/status")
def training_status() -> dict[str, Any]:
    return load_config()["training"]


ensure_dirs()
