import json
import math
import os
import re
import signal
import hashlib
import shutil
import subprocess
import threading
import time
import uuid
import ctypes
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

os.environ.setdefault("NUMBA_NUM_THREADS", "1")

import cv2
import numpy as np

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ultralytics import YOLO


ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
APP_DIR = ROOT / "local_inspection_service"
STATIC_DIR = APP_DIR / "static"
DATA_DIR = APP_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
NORMALIZED_DIR = DATA_DIR / "normalized_assets"
TRAINING_JOBS_DIR = DATA_DIR / "training_jobs"
TRAINING_TASKS_DIR = DATA_DIR / "training_tasks"
ACCESSORY_CANDIDATES_DIR = DATA_DIR / "accessory_candidates"
IMAGE_WORKER_LOG_DIR = DATA_DIR / "image_worker_logs"
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


def legacy_model_specs() -> list[dict[str, Any]]:
    return [{**spec, "is_legacy": True, "variant": "yolo_ocr" if spec.get("uses_ocr") else "yolo"} for spec in MODEL_REGISTRY.values()]

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
        "selected_accessory_ids": [],
        "sample_count": 4000,
        "mode": "yolo_ocr",
        "preview_urls": [],
    },
}


for path in (UPLOAD_DIR, OUTPUT_DIR, DATA_DIR, NORMALIZED_DIR, TRAINING_JOBS_DIR, TRAINING_TASKS_DIR, ACCESSORY_CANDIDATES_DIR, IMAGE_WORKER_LOG_DIR):
    path.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Assembly Line Local Inspection Service")

LOCAL_CORS_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$"
LAN_CORS_ORIGIN_REGEX = (
    r"^https?://("
    r"10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}|"
    r"[^/:]+\.local"
    r")(?::\d+)?$"
)
CORS_ORIGIN_REGEX = os.environ.get(
    "INSPECTION_CORS_ORIGIN_REGEX",
    LAN_CORS_ORIGIN_REGEX if os.environ.get("INSPECTION_ENABLE_LAN_CORS") == "1" else LOCAL_CORS_ORIGIN_REGEX,
)
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("INSPECTION_CORS_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


def normalize_origin(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return ""
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return ""
    port = parsed.port
    default_port = 443 if scheme == "https" else 80
    netloc = hostname if port in (None, default_port) else f"{hostname}:{port}"
    return f"{scheme}://{netloc}"


def same_origin(origin: str, host: str) -> bool:
    parsed_origin = urlsplit(origin)
    if not parsed_origin.scheme or not parsed_origin.netloc:
        return False
    parsed_host = urlsplit(f"{parsed_origin.scheme}://{host}")
    return (parsed_origin.hostname or "").lower() == (parsed_host.hostname or "").lower() and (
        parsed_origin.port or (443 if parsed_origin.scheme == "https" else 80)
    ) == (parsed_host.port or (443 if parsed_origin.scheme == "https" else 80))


def cors_origin_allowed(origin: str) -> bool:
    normalized = normalize_origin(origin)
    if not normalized:
        return False
    if normalized in {normalize_origin(item) for item in CORS_ORIGINS}:
        return True
    return re.match(CORS_ORIGIN_REGEX, normalized) is not None


@app.middleware("http")
async def reject_untrusted_cross_origin_writes(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        host = request.headers.get("host", "")
        if origin and not same_origin(origin, host) and not cors_origin_allowed(origin):
            return PlainTextResponse("Untrusted cross-origin write request", status_code=403)
    return await call_next(request)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

_models: dict[str, YOLO] = {}
_ocr: Any | None = None
_rembg_session: Any | None = None
_rembg_lock = threading.RLock()
_image_worker_lock = threading.Lock()
_candidate_store_lock = threading.RLock()
_training_task_lock = threading.RLock()
_image_worker_thread: threading.Thread | None = None
_image_worker_processes: dict[str, subprocess.Popen] = {}
_training_task_threads: dict[str, threading.Thread] = {}
MAX_PARALLEL_IMAGE_WORKERS = 2
IMAGE_REFERENCE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_REFERENCE_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
MAX_IMAGE_WORKER_INPUTS = 10
MAX_VIDEO_REFERENCE_FRAMES = 6
PREVIEW_CACHE_SCHEMA_VERSION = "preview-cache-v4-object-overlap-material-alpha-scale"
ANCHOR_POLICY_VERSION = "anchor-replacement-2026-05-27"
TRANSPARENT_OBJECT_KEYWORDS = (
    "glass",
    "transparent",
    "translucent",
    "bottle",
    "jar",
    "vial",
    "玻璃",
    "透明",
    "透光",
    "瓶",
)
POSE_ANCHOR_DIR = DATA_DIR / "anchor_pose_guides"
POSE_ANCHOR_IMAGES = {
    "upright": POSE_ANCHOR_DIR / "endface_9bar_anchor.png",
    "lying": POSE_ANCHOR_DIR / "flat_9bar_anchor.png",
}

POSE_COLLECTION_BATCHES: list[tuple[str, str, list[str]]] = [
    ("top_row", "上排三视角", ["top-left", "top-center", "top-right"]),
    ("middle_row", "中排三视角", ["middle-left", "center", "middle-right"]),
    ("bottom_row", "下排三视角", ["bottom-left", "bottom-center", "bottom-right"]),
]

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


class TrainingPreviewRequest(BaseModel):
    selected_accessory_ids: list[str]
    sample_count: int = 4000
    train_mode: str = "yolo_ocr"
    preview_count: int = 5
    preview_pose_family_policy: str = "auto"
    background_set_id: str | None = None
    force_refresh: bool = True


class TrainingStartRequest(BaseModel):
    selected_accessory_ids: list[str]
    sample_count: int = 4000
    train_mode: str = "yolo_ocr"
    approved_preview_id: str | None = None
    dataset_id: str | None = None
    epochs: int = 80
    image_size: int = 640
    background_set_id: str | None = None


class TrainingTaskUpdateRequest(BaseModel):
    label: str | None = None
    note: str | None = None


class TrainingResourceUpdateRequest(BaseModel):
    display_name: str | None = None
    note: str | None = None


STANDARD_PAPER_SIZES_MM = {
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "A6": (105.0, 148.0),
}

MM_TO_PREVIEW_PX = 1.43
# Default object size is calibrated to the real reference photo ratio:
# bottle long side ~= 0.55-0.60 of an A4 manual long side in the 1280x900 preview.
DEFAULT_OBJECT_SIZE_MM = {"length_mm": 170.0, "width_mm": 38.0, "height_mm": 38.0}
UPRIGHT_SCALE_CORRECTION_MIN_RATIO = 1.01
UPRIGHT_SCALE_CORRECTION_MAX_RATIO = 3.25
UPRIGHT_SCALE_VISUAL_ADJUSTMENT = 0.8
BACKGROUND_ROI_PX = (70, 100, 1210, 800)
BACKGROUND_DIR = ROOT / "backgrounds"
BACKGROUND_SETS_DIR = BACKGROUND_DIR / "sets"
BACKGROUND_SETS_MANIFEST = BACKGROUND_DIR / "background_sets.json"
DEFAULT_BACKGROUND_IMAGE = BACKGROUND_DIR / "conveyor_surface_topdown_ai_reference5.png"
BACKGROUND_SIZE_MM = {
    "width_mm": round((BACKGROUND_ROI_PX[2] - BACKGROUND_ROI_PX[0]) / MM_TO_PREVIEW_PX, 2),
    "height_mm": round((BACKGROUND_ROI_PX[3] - BACKGROUND_ROI_PX[1]) / MM_TO_PREVIEW_PX, 2),
    "mm_per_px": round(1 / MM_TO_PREVIEW_PX, 4),
    "px_per_mm": MM_TO_PREVIEW_PX,
}


def optional_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def physical_size_payload(
    material_type: str,
    paper_preset: str = "A4",
    paper_width_mm: Any = None,
    paper_height_mm: Any = None,
    object_length_mm: Any = None,
    object_width_mm: Any = None,
    object_height_mm: Any = None,
) -> dict[str, Any]:
    if material_type == "text":
        preset = paper_preset if paper_preset in STANDARD_PAPER_SIZES_MM else "custom"
        default_w, default_h = STANDARD_PAPER_SIZES_MM.get(preset, STANDARD_PAPER_SIZES_MM["A4"])
        if preset in STANDARD_PAPER_SIZES_MM:
            width_mm, height_mm = default_w, default_h
        else:
            width_mm = optional_float(paper_width_mm) or default_w
            height_mm = optional_float(paper_height_mm) or default_h
        return {
            "kind": "paper",
            "preset": preset,
            "width_mm": width_mm,
            "height_mm": height_mm,
        }
    return {
        "kind": "object",
        "length_mm": optional_float(object_length_mm) or DEFAULT_OBJECT_SIZE_MM["length_mm"],
        "width_mm": optional_float(object_width_mm) or DEFAULT_OBJECT_SIZE_MM["width_mm"],
        "height_mm": optional_float(object_height_mm) or DEFAULT_OBJECT_SIZE_MM["height_mm"],
    }


def ensure_dirs() -> None:
    for path in (
        UPLOAD_DIR,
        OUTPUT_DIR,
        DATA_DIR,
        NORMALIZED_DIR,
        TRAINING_JOBS_DIR,
        TRAINING_TASKS_DIR,
        ACCESSORY_CANDIDATES_DIR,
        IMAGE_WORKER_LOG_DIR,
        BACKGROUND_DIR,
        BACKGROUND_SETS_DIR,
    ):
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


def accessory_uid(item: dict[str, Any]) -> str:
    if item.get("id"):
        return str(item["id"])
    raw = f"{item.get('class_id', 'x')}_{item.get('name', 'accessory')}"
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", raw).strip("_").lower()


def serialize_accessory(item: dict[str, Any]) -> dict[str, Any]:
    copy = dict(item)
    copy["id"] = accessory_uid(item)
    material_type = copy.setdefault("material_type", "object" if int(copy.get("class_id", 0)) == 0 else "text")
    copy.setdefault("physical_size", physical_size_payload(str(material_type)))
    if str(material_type) == "object":
        copy.setdefault("material_alpha_policy", object_alpha_material_policy(item))
    copy.setdefault("source_files", [])
    copy.setdefault("normalized_assets", [])
    copy.setdefault("training_role", "detect_and_classify")
    return copy


def accessory_material_type(item: dict[str, Any]) -> str:
    return str(item.get("material_type") or ("object" if int(item.get("class_id", 0)) == 0 else "text"))


def normalize_object_alpha_material_policy(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"transparent", "glass", "translucent", "preserve_transparency", "preserve_glass"}:
        return "transparent"
    if normalized in {"opaque", "solid", "foreground_opaque", "solid_foreground"}:
        return "opaque"
    return None


def object_alpha_material_policy(item: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> str:
    source = metadata or {}
    explicit = (
        source.get("material_alpha_policy")
        or source.get("alpha_policy")
        or (item or {}).get("material_alpha_policy")
        or (item or {}).get("alpha_policy")
        or (item or {}).get("object_alpha_policy")
    )
    explicit_policy = normalize_object_alpha_material_policy(explicit)
    if explicit_policy:
        return explicit_policy
    haystack = " ".join(
        str(value or "")
        for value in (
            (item or {}).get("name"),
            source.get("name"),
            (item or {}).get("material"),
            (item or {}).get("description"),
            source.get("source_pose_collection"),
        )
    ).lower()
    return "transparent" if any(keyword in haystack for keyword in TRANSPARENT_OBJECT_KEYWORDS) else "opaque"


def object_alpha_policy_label(policy: str) -> str:
    return "透明" if policy == "transparent" else "不透明"


def public_output_url(path: Path) -> str:
    return f"/outputs/{path.relative_to(OUTPUT_DIR).as_posix()}"


def order_points(points: np.ndarray) -> np.ndarray:
    pts = points.reshape(4, 2).astype("float32")
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    ordered = np.zeros((4, 2), dtype="float32")
    ordered[0] = pts[np.argmin(s)]
    ordered[2] = pts[np.argmax(s)]
    ordered[1] = pts[np.argmin(diff)]
    ordered[3] = pts[np.argmax(diff)]
    return ordered


def target_paper_pixel_size(physical_size: dict[str, Any] | None) -> tuple[int, int]:
    size = physical_size or {}
    width_mm = optional_float(size.get("width_mm")) or STANDARD_PAPER_SIZES_MM["A4"][0]
    height_mm = optional_float(size.get("height_mm")) or STANDARD_PAPER_SIZES_MM["A4"][1]
    if width_mm > height_mm:
        long_px = 1200
        return long_px, max(1, int(round(long_px * height_mm / width_mm)))
    long_px = 1200
    return max(1, int(round(long_px * width_mm / height_mm))), long_px


def ratio_close(value: float, target: float, tolerance: float = 0.08) -> bool:
    if value <= 0 or target <= 0:
        return False
    return abs(value - target) / target <= tolerance


def quad_is_axis_aligned(rect: np.ndarray, image_shape: tuple[int, ...]) -> bool:
    h, w = image_shape[:2]
    horizontal_tilt = max(abs(float(rect[0][1] - rect[1][1])), abs(float(rect[2][1] - rect[3][1]))) / max(1, h)
    vertical_tilt = max(abs(float(rect[1][0] - rect[2][0])), abs(float(rect[0][0] - rect[3][0]))) / max(1, w)
    return horizontal_tilt < 0.02 and vertical_tilt < 0.02


def best_document_quad(image: np.ndarray, target_aspect: float | None = None) -> np.ndarray | None:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 160)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_area = image.shape[0] * image.shape[1]
    image_aspect = image.shape[1] / max(1, image.shape[0])
    image_already_paper_ratio = bool(target_aspect and ratio_close(image_aspect, target_aspect))
    best: tuple[float, np.ndarray] | None = None
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:16]:
        area = float(cv2.contourArea(contour))
        if area < image_area * 0.05:
            continue
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        used_rect_fallback = len(approx) != 4
        if used_rect_fallback:
            if area < image_area * 0.20:
                continue
            rect = cv2.boxPoints(cv2.minAreaRect(contour)).reshape(4, 1, 2)
            approx = rect.astype(np.float32)
        rect = order_points(approx)
        quad_area = float(cv2.contourArea(rect.astype(np.float32)))
        if quad_area <= 0:
            continue
        quad_area_ratio = quad_area / max(1, image_area)
        if image_already_paper_ratio and quad_area_ratio < 0.82 and quad_is_axis_aligned(rect, image.shape):
            continue
        fill = area / quad_area
        min_fill = 0.82 if used_rect_fallback else 0.65
        if fill < min_fill:
            continue
        if used_rect_fallback:
            x, y, w, h = cv2.boundingRect(rect.astype(np.float32))
            touches_frame = x <= 2 or y <= 2 or x + w >= image.shape[1] - 2 or y + h >= image.shape[0] - 2
            if touches_frame:
                continue
        score = quad_area * min(fill, 1.0)
        if best is None or score > best[0]:
            best = (score, rect)
    return best[1] if best else None


def normalize_text_image(src: Path, target_dir: Path, physical_size: dict[str, Any] | None = None) -> dict[str, Any] | None:
    image = cv2.imread(str(src))
    if image is None:
        return None
    warped = None
    method = "resize_fallback"
    is_manual_rectified = src.stem.endswith("_rectified")
    if is_manual_rectified:
        target_w, target_h = int(image.shape[1]), int(image.shape[0])
    else:
        target_w, target_h = target_paper_pixel_size(physical_size)
    target_aspect = target_w / max(1, target_h)
    rect = None if is_manual_rectified else best_document_quad(image, target_aspect)
    if rect is not None:
        dst = np.array([[0, 0], [target_w - 1, 0], [target_w - 1, target_h - 1], [0, target_h - 1]], dtype="float32")
        matrix = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(image, matrix, (target_w, target_h))
        method = "paper_quad_perspective"
    if warped is None:
        warped = cv2.resize(image, (target_w, target_h), interpolation=cv2.INTER_AREA)
        method = "manual_quad_perspective" if is_manual_rectified else "paper_resize_fallback"
    out = target_dir / f"{src.stem}_canonical.png"
    cv2.imwrite(str(out), warped)
    return {
        "kind": "canonical_text_image",
        "path": str(out),
        "method": method,
        "paper_size": physical_size or {},
        "width": int(warped.shape[1]),
        "height": int(warped.shape[0]),
        "workflow": ["crop", "perspective_correction", "ocr_keyword_capture"],
    }


def build_object_view_plan(name: str) -> list[dict[str, Any]]:
    return [
        {"view": "front", "angle": 0, "scale": "1.00x"},
        {"view": "left_oblique", "angle": -45, "scale": "0.90x"},
        {"view": "right_oblique", "angle": 45, "scale": "1.10x"},
        {"view": "top", "angle": 90, "scale": "0.85x"},
        {"view": "lying_horizontal", "angle": 180, "scale": "1.00x"},
        {"view": "standing", "angle": "cap diameter calibrated", "scale": "matched_to_proxy_length"},
    ]


def default_asset_for_accessory(item: dict[str, Any]) -> Path | None:
    name = str(item.get("name", "")).lower()
    if "warranty" in name:
        return ROOT / "standardized_manuals" / "manual_from_2_warranty_service_precise_1240x1754.png"
    if "battery" in name:
        return ROOT / "standardized_manuals" / "manual_from_3_battery_instruction_precise_1240x1754.png"
    if "download" in name:
        return ROOT / "standardized_manuals" / "manual_from_4_download_service_precise_1240x1754.png"
    if "qr" in name or "service" in name:
        return ROOT / "standardized_manuals" / "manual_from_6_service_qr_precise_1240x1754.png"
    if "bottle" in name:
        return ROOT / "generated_bottle_pose_collection" / "overhead_bottle_pose_collection_image2.png"
    return None


def load_preview_asset_with_metadata(item: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]] | None:
    for asset in item.get("normalized_assets", []):
        path = Path(str(asset.get("path", "")))
        if path.exists() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is not None:
                return image, {
                    "asset_path": str(path),
                    "asset_kind": asset.get("kind"),
                    "asset_method": asset.get("method"),
                    "asset_source": "normalized_assets",
                    "source_image_size_px": [int(image.shape[1]), int(image.shape[0])],
                    "canonical_asset_dimensions_px": [int(asset.get("width") or image.shape[1]), int(asset.get("height") or image.shape[0])],
                }
    for path_str in item.get("source_files", []):
        path = Path(path_str)
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"} and path.exists():
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is not None:
                return image, {
                    "asset_path": str(path),
                    "asset_kind": "source_image",
                    "asset_method": "source_file_direct",
                    "asset_source": "source_files",
                    "source_image_size_px": [int(image.shape[1]), int(image.shape[0])],
                    "canonical_asset_dimensions_px": [int(image.shape[1]), int(image.shape[0])],
                }
    default_path = default_asset_for_accessory(item)
    if default_path and default_path.exists():
        image = cv2.imread(str(default_path), cv2.IMREAD_COLOR)
        if image is not None:
            return image, {
                "asset_path": str(default_path),
                "asset_kind": "default_image",
                "asset_method": "default_asset_direct",
                "asset_source": "default_asset",
                "source_image_size_px": [int(image.shape[1]), int(image.shape[0])],
                "canonical_asset_dimensions_px": [int(image.shape[1]), int(image.shape[0])],
            }
    return None


def load_rectified_document_asset_with_metadata(item: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]] | None:
    for asset in item.get("normalized_assets", []):
        path = Path(str(asset.get("path", "")))
        if path.exists() and path.suffix.lower() in IMAGE_REFERENCE_SUFFIXES:
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is not None:
                return image, {
                    "asset_path": str(path),
                    "asset_kind": asset.get("kind"),
                    "asset_method": asset.get("method"),
                    "asset_source": "normalized_assets",
                    "source_image_size_px": [int(image.shape[1]), int(image.shape[0])],
                    "canonical_asset_dimensions_px": [int(asset.get("width") or image.shape[1]), int(asset.get("height") or image.shape[0])],
                }
    for path_str in item.get("source_files", []):
        path = Path(path_str)
        if not path.stem.endswith("_rectified"):
            continue
        if path.suffix.lower() in IMAGE_REFERENCE_SUFFIXES and path.exists():
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is not None:
                return image, {
                    "asset_path": str(path),
                    "asset_kind": "rectified_source_image",
                    "asset_method": "manual_rectified_source_direct",
                    "asset_source": "source_files_rectified",
                    "source_image_size_px": [int(image.shape[1]), int(image.shape[0])],
                    "canonical_asset_dimensions_px": [int(image.shape[1]), int(image.shape[0])],
                }
    default_path = default_asset_for_accessory(item)
    if default_path and default_path.exists() and default_path.parent.name == "standardized_manuals":
        image = cv2.imread(str(default_path), cv2.IMREAD_COLOR)
        if image is not None:
            return image, {
                "asset_path": str(default_path),
                "asset_kind": "standardized_document_default",
                "asset_method": "standardized_rectified_default_direct",
                "asset_source": "standardized_default_asset",
                "source_image_size_px": [int(image.shape[1]), int(image.shape[0])],
                "canonical_asset_dimensions_px": [int(image.shape[1]), int(image.shape[0])],
            }
    return None


def load_preview_asset(item: dict[str, Any]) -> np.ndarray | None:
    loaded = load_preview_asset_with_metadata(item)
    return loaded[0] if loaded else None


def candidate_image_jobs(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = candidate.get("codex_image_jobs")
    if isinstance(jobs, list) and jobs:
        return [job for job in jobs if isinstance(job, dict)]
    job = candidate.get("codex_image_job")
    return [job] if isinstance(job, dict) and job else []


def deterministic_task_id(candidate: dict[str, Any], job: dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(job.get("job_id") or ""),
            str(candidate.get("id") or job.get("candidate_id") or ""),
            str(job.get("pose_family") or ""),
            str(job.get("created_at") or candidate.get("created_at") or ""),
            str(job.get("output_path") or ""),
        ]
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"task_{digest}"


def ensure_image_job_task_id(candidate: dict[str, Any], job: dict[str, Any]) -> bool:
    changed = False
    if not job.get("job_id"):
        job["job_id"] = f"imgjob_{candidate.get('id', deterministic_task_id(candidate, job))}"
        changed = True
    if not job.get("candidate_id") and candidate.get("id"):
        job["candidate_id"] = candidate.get("id")
        changed = True
    if not job.get("task_id"):
        job["task_id"] = deterministic_task_id(candidate, job)
        changed = True
    return changed


def image_job_matches(candidate: dict[str, Any], job: dict[str, Any], lookup_id: str) -> bool:
    ensure_image_job_task_id(candidate, job)
    return lookup_id in {str(job.get("job_id") or ""), str(job.get("task_id") or "")}


def file_sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def ensure_anchor_image_provenance(job: dict[str, Any]) -> bool:
    if job.get("generation_step") != "anchor_replacement":
        return False
    changed = False
    anchor_path = Path(str(job.get("anchor_image_path") or ""))
    if anchor_path.name and not job.get("anchor_image_basename"):
        job["anchor_image_basename"] = anchor_path.name
        changed = True
    if "anchor_image_sha256" not in job:
        output_path = Path(str(job.get("output_path") or ""))
        output_predates_anchor = False
        try:
            output_predates_anchor = output_path.exists() and anchor_path.exists() and output_path.stat().st_mtime < anchor_path.stat().st_mtime
        except OSError:
            output_predates_anchor = False
        if job.get("status") == "completed" or output_predates_anchor:
            job["anchor_image_sha256"] = None
            job["anchor_provenance"] = "legacy_path_only"
        else:
            job["anchor_image_sha256"] = file_sha256(anchor_path)
            job["anchor_policy_version"] = ANCHOR_POLICY_VERSION
            job["anchor_provenance"] = "sha256"
        changed = True
    elif job.get("anchor_image_sha256"):
        if not job.get("anchor_policy_version"):
            job["anchor_policy_version"] = ANCHOR_POLICY_VERSION
            changed = True
        if not job.get("anchor_provenance"):
            job["anchor_provenance"] = "sha256"
            changed = True
    elif not job.get("anchor_provenance"):
        job["anchor_provenance"] = "legacy_path_only"
        changed = True
    return changed


def ensure_candidate_image_job_task_ids(candidate: dict[str, Any]) -> bool:
    changed = False
    jobs = candidate_image_jobs(candidate)
    for job in jobs:
        changed = ensure_image_job_task_id(candidate, job) or changed
        changed = ensure_anchor_image_provenance(job) or changed
    if jobs:
        candidate["codex_image_jobs"] = jobs
        candidate["codex_image_job"] = jobs[0]
    return changed


def store_candidate_image_job(candidate: dict[str, Any], updated_job: dict[str, Any]) -> None:
    ensure_image_job_task_id(candidate, updated_job)
    ensure_anchor_image_provenance(updated_job)
    job_id = str(updated_job.get("job_id", ""))
    jobs = candidate_image_jobs(candidate)
    replaced = False
    next_jobs = []
    for job in jobs:
        ensure_image_job_task_id(candidate, job)
        if str(job.get("job_id", "")) == job_id:
            next_jobs.append(updated_job)
            replaced = True
        else:
            next_jobs.append(job)
    if not replaced:
        next_jobs.append(updated_job)
    candidate["codex_image_jobs"] = next_jobs
    candidate["codex_image_job"] = next_jobs[0] if next_jobs else None


def accessory_image_paths(item: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for job in candidate_image_jobs(item):
        if job.get("intermediate"):
            continue
        output_path = Path(str(job.get("output_path", "")))
        if output_path.exists():
            paths.append(output_path)
    for asset in item.get("normalized_assets", []):
        path = Path(str(asset.get("path", "")))
        if path.exists():
            paths.append(path)
    for path_str in item.get("source_files", []):
        path = Path(path_str)
        if path.exists() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            paths.append(path)
    default_path = default_asset_for_accessory(item)
    if default_path and default_path.exists():
        paths.append(default_path)
    unique = []
    seen = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            unique.append(path)
            seen.add(key)
    return unique


def clean_sprite_assets(item: dict[str, Any]) -> list[dict[str, Any]]:
    assets = []
    for asset in item.get("normalized_assets", []):
        if asset.get("kind") != "clean_object_sprite":
            continue
        path = Path(str(asset.get("path", "")))
        if not path.exists() or path.suffix.lower() != ".png":
            continue
        if not asset.get("width") or not asset.get("height"):
            image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if image is not None:
                asset.setdefault("width", int(image.shape[1]))
                asset.setdefault("height", int(image.shape[0]))
        if not asset.get("source_object_size_px") and asset.get("width") and asset.get("height"):
            asset["source_object_size_px"] = [int(asset.get("width")), int(asset.get("height"))]
        if not asset.get("source_pose_family") and not asset.get("pose_family"):
            source_size = asset.get("source_object_size_px") or [int(asset.get("width") or 1), int(asset.get("height") or 1)]
            asset["pose_family"] = "upright" if pose_family_is_top_view("", source_size) else "lying"
            asset["source_pose_family"] = asset["pose_family"]
        if asset.get("source_pose_family") and not asset.get("pose_family"):
            asset["pose_family"] = asset.get("source_pose_family")
        if asset.get("pose_position") and not asset.get("source_position"):
            asset["source_position"] = asset.get("pose_position")
        if not asset.get("pose_position"):
            asset["pose_position"] = "center"
        if not asset.get("source_position"):
            asset["source_position"] = asset.get("pose_position")
        if not asset.get("source_image_size_px") and asset.get("source_image_width") and asset.get("source_image_height"):
            asset["source_image_size_px"] = [int(asset.get("source_image_width")), int(asset.get("source_image_height"))]
        if not asset.get("source_image_size_px") and asset.get("source_object_size_px"):
            asset["source_image_size_px"] = list(asset.get("source_object_size_px"))
            asset["source_image_width"] = int(asset["source_image_size_px"][0])
            asset["source_image_height"] = int(asset["source_image_size_px"][1])
        if not asset.get("physical_size_mm") and isinstance(item.get("physical_size"), dict):
            asset["physical_size_mm"] = item.get("physical_size")
        if asset.get("source_object_size_px"):
            pose_family = str(asset.get("source_pose_family") or asset.get("pose_family") or "")
            physical_size = asset.get("physical_size_mm") if isinstance(asset.get("physical_size_mm"), dict) else item.get("physical_size")
            asset.update(pose_render_footprint_metadata(pose_family, asset.get("source_object_size_px"), physical_size))
        if asset.get("render_footprint_px") and not asset.get("render_size_hint_px"):
            asset["render_size_hint_px"] = asset.get("render_footprint_px")
        asset.setdefault("task_id", "legacy_clean_sprite")
        asset.setdefault("source_pose_collection_job_id", "legacy_clean_sprite")
        assets.append(asset)
    apply_upright_scale_correction_metadata(assets, item.get("physical_size"))
    apply_laying_standard_render_size_hints(assets)
    return assets


def clean_sprite_metadata_complete(asset: dict[str, Any]) -> bool:
    required_keys = [
        "task_id",
        "source_pose_collection_job_id",
        "pose_family",
        "source_pose_family",
        "pose_position",
        "source_position",
        "original_orientation_angle",
        "original_orientation_angle_degrees",
        "rotation_degrees_applied",
        "rotation_degrees_applied_to_upright",
        "source_restore_rotation_degrees",
        "normalized_axis_target_degrees",
        "source_region_bbox_xyxy",
        "source_object_bbox_xyxy",
        "source_object_center_xy",
        "source_object_size_px",
        "normalized_asset_size_px",
        "normalized_asset_dimensions_px",
        "normalized_bbox_xyxy",
        "pre_rotation_safety_margin_px",
        "post_rotation_safety_margin_px",
        "edge_alpha_max",
        "edge_alpha_pass",
        "mask_strategy",
        "foreground_component_bbox_xyxy",
        "removed_stray_component_count",
        "removed_stray_component_area_px",
        "alpha_edge_stats",
        "transparent_alpha_policy",
        "material_alpha_policy",
        "object_alpha_material_policy",
        "render_scale_basis",
        "render_footprint_mm",
        "render_footprint_px",
        "canonical_width_px",
        "canonical_height_px",
        "physical_footprint_basis",
    ]
    return all(asset.get(key) is not None for key in required_keys)


def clean_sprite_material_policy_matches(item: dict[str, Any], asset: dict[str, Any]) -> bool:
    expected = object_alpha_material_policy(item)
    asset_policy = normalize_object_alpha_material_policy(asset.get("material_alpha_policy"))
    return bool(asset_policy and asset_policy == expected)


def clean_sprites_policy_complete(item: dict[str, Any], assets: list[dict[str, Any]] | None = None) -> bool:
    sprites = assets if assets is not None else clean_sprite_assets(item)
    return bool(sprites) and all(clean_sprite_metadata_complete(asset) and clean_sprite_material_policy_matches(item, asset) for asset in sprites)


def accessory_sprite_version(item: dict[str, Any]) -> str:
    sprites = clean_sprite_assets(item)
    parts = [
        PREVIEW_CACHE_SCHEMA_VERSION,
        str(accessory_uid(item)),
        str(accessory_material_type(item)),
        str(object_alpha_material_policy(item)) if accessory_material_type(item) == "object" else "",
        json.dumps(item.get("physical_size") or {}, sort_keys=True, separators=(",", ":")),
        str(item.get("clean_sprite_status") or ""),
        str(item.get("clean_sprite_preprocessed_at") or 0),
        str(item.get("clean_sprite_count") or len(sprites)),
        str(item.get("clean_sprite_expected_count") or ""),
    ]
    for idx, asset in enumerate(sprites):
        path = Path(str(asset.get("path", "")))
        try:
            stat = path.stat()
            mtime_ns = stat.st_mtime_ns
            size = stat.st_size
        except OSError:
            mtime_ns = 0
            size = 0
        parts.extend(
            [
                str(idx + 1),
                str(path),
                str(mtime_ns),
                str(size),
                str(asset.get("task_id") or ""),
                str(asset.get("source_position") or asset.get("pose_position") or ""),
                str(asset.get("source_pose_family") or asset.get("pose_family") or ""),
                str(asset.get("material_alpha_policy") or ""),
                str(asset.get("object_alpha_material_policy") or ""),
                json.dumps(asset.get("physical_size_mm") or {}, sort_keys=True, separators=(",", ":")),
                json.dumps(asset.get("source_object_bbox_xyxy") or [], separators=(",", ":")),
                json.dumps(asset.get("source_object_size_px") or [], separators=(",", ":")),
                json.dumps(asset.get("normalized_bbox_xyxy") or [], separators=(",", ":")),
                json.dumps(asset.get("render_footprint_px") or [], separators=(",", ":")),
                json.dumps(asset.get("render_footprint_mm") or [], separators=(",", ":")),
                json.dumps(asset.get("render_size_hint_px") or [], separators=(",", ":")),
            ]
        )
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def preview_cache_key(selected: list[dict[str, Any]]) -> str:
    raw = "|".join(f"{accessory_uid(item)}:{accessory_sprite_version(item)}" for item in selected)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def training_preview_metadata_missing(training: dict[str, Any], selected: list[dict[str, Any]]) -> bool:
    has_object = any(accessory_material_type(item) == "object" for item in selected)
    has_preview_state = bool(training.get("preview_urls") or training.get("previews") or training.get("last_preview_id"))
    if not has_object or not has_preview_state:
        return False
    if not training.get("preview_cache_key"):
        return True
    sprite_versions = training.get("preview_sprite_versions")
    return not isinstance(sprite_versions, dict) or not sprite_versions


def available_object_pose_families(item: dict[str, Any]) -> list[str]:
    families = sorted({sprite_pose_family(asset) for asset in clean_sprite_assets(item) if sprite_pose_family(asset)})
    return families


def canonical_pose_family_name(pose_family: str | None) -> str | None:
    family = str(pose_family or "").strip().lower()
    if family in {"lying", "flat", "side", "side-facing"}:
        return "lying"
    if family in {"upright", "standing", "top", "top-view", "top_view", "cap", "endface", "end-face", "top-facing"}:
        return "upright"
    return family or None


def normalize_preview_pose_family_policy(value: str | None) -> str:
    policy = str(value or "auto").strip().lower()
    aliases = {
        "": "auto",
        "controlled": "auto",
        "default": "auto",
        "lying_only": "lying",
        "flat": "lying",
        "side": "lying",
        "side-facing": "lying",
        "upright_only": "upright",
        "top": "upright",
        "top-view": "upright",
        "top_view": "upright",
    }
    policy = aliases.get(policy, policy)
    if policy not in {"auto", "lying", "upright"}:
        raise HTTPException(status_code=400, detail=f"Unknown preview_pose_family_policy: {value}")
    return policy


def preview_pose_family_for_policy(accessories: list[dict[str, Any]], policy: str) -> str | None:
    families = preview_pose_families_for_policy(accessories, policy)
    return families[0] if families else None


def preview_pose_families_for_policy(accessories: list[dict[str, Any]], policy: str) -> list[str]:
    object_families = [
        available_object_pose_families(item)
        for item in accessories
        if accessory_material_type(item) == "object"
    ]
    common = set(object_families[0]) if object_families else set()
    for families in object_families[1:]:
        common &= set(families)
    if not common:
        return None
    if policy == "lying":
        ordered = [family for family in ("lying", "flat", "side", "side-facing") if family in common]
    elif policy == "upright":
        ordered = [family for family in ("upright", "top", "top-view") if family in common]
    else:
        ordered = [family for family in ("lying", "flat", "side", "side-facing", "upright", "top", "top-view") if family in common]
        ordered.extend(sorted(common - set(ordered)))
    if not ordered:
        raise HTTPException(status_code=400, detail=f"No clean sprites available for preview pose policy: {policy}")
    if policy == "auto":
        canonical_seen: set[str] = set()
        mixed: list[str] = []
        for family in ordered:
            canonical = canonical_pose_family_name(family)
            if canonical in {"lying", "upright"} and canonical not in canonical_seen:
                mixed.append(family)
                canonical_seen.add(canonical)
        if len(mixed) >= 2:
            return mixed
    return [ordered[0]]


def preview_pose_family_sequence(accessories: list[dict[str, Any]], count: int, policy: str = "auto") -> list[str | None]:
    normalized_policy = normalize_preview_pose_family_policy(policy)
    selected_families = preview_pose_families_for_policy(accessories, normalized_policy)
    if not selected_families:
        return [None] * count
    if normalized_policy == "auto" and len(selected_families) > 1:
        return [selected_families[idx % len(selected_families)] for idx in range(count)]
    return [selected_families[0]] * count


def preview_pose_family_sequence_label(sequence: list[str | None]) -> str | None:
    families = [canonical_pose_family_name(family) for family in sequence if family]
    unique = [family for family in ("lying", "upright") if family in families]
    if len(unique) > 1:
        return "mixed"
    return unique[0] if unique else (str(sequence[0]) if sequence else None)


def load_clean_sprite(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        return None
    if image.ndim != 3 or image.shape[2] < 4:
        return None
    alpha = image[:, :, 3]
    if int((alpha > 8).sum()) < 240:
        return None
    bgr = image[:, :, :3]
    return bgr.copy(), alpha.copy()


def object_physical_size_mm(size: dict[str, Any] | None) -> tuple[float, float, float]:
    size = size or {}
    return (
        float(size.get("length_mm") or DEFAULT_OBJECT_SIZE_MM["length_mm"]),
        float(size.get("width_mm") or DEFAULT_OBJECT_SIZE_MM["width_mm"]),
        float(size.get("height_mm") or DEFAULT_OBJECT_SIZE_MM["height_mm"]),
    )


def pose_family_is_top_view(pose_family: str, source_size_px: list[int] | tuple[int, int] | None = None) -> bool:
    family = canonical_pose_family_name(pose_family)
    if family == "upright":
        return True
    if family == "lying":
        return False
    if source_size_px and len(source_size_px) >= 2:
        w, h = max(1, int(source_size_px[0])), max(1, int(source_size_px[1]))
        return max(w, h) / max(1, min(w, h)) < 1.35
    return False


def pose_render_footprint_metadata(
    pose_family: str,
    source_size_px: list[int] | tuple[int, int],
    physical_size: dict[str, Any] | None,
) -> dict[str, Any]:
    source_w = max(1, int(source_size_px[0] if source_size_px else 1))
    source_h = max(1, int(source_size_px[1] if source_size_px else 1))
    length_mm, width_mm, height_mm = object_physical_size_mm(physical_size)
    source_aspect = source_w / max(1, source_h)
    length_to_cross_section = length_mm / max(width_mm, height_mm, 1.0)
    if length_to_cross_section <= 2.0:
        footprint_w_mm = length_mm
        footprint_h_mm = max(width_mm, height_mm)
        basis = "shared_length_width_physical_footprint"
    elif pose_family_is_top_view(pose_family, [source_w, source_h]):
            diameter_mm = max(width_mm, height_mm)
            footprint_w_mm = diameter_mm
            footprint_h_mm = diameter_mm
            basis = "cap_outer_edge_diameter_mm"
    else:
        visible_side_mm = max(width_mm, height_mm * 0.72)
        footprint_w_mm = visible_side_mm
        footprint_h_mm = length_mm
        basis = "side_major_axis_length_mm"
    footprint_px = [
        max(16, int(round(footprint_w_mm * MM_TO_PREVIEW_PX))),
        max(16, int(round(footprint_h_mm * MM_TO_PREVIEW_PX))),
    ]
    return {
        "render_scale_basis": basis,
        "render_footprint_mm": [round(float(footprint_w_mm), 2), round(float(footprint_h_mm), 2)],
        "render_footprint_px": footprint_px,
        "render_size_hint_px": footprint_px,
        "canonical_width_px": footprint_px[0],
        "canonical_height_px": footprint_px[1],
        "physical_footprint_basis": basis,
    }


def median_source_major_axis_px(assets: list[dict[str, Any]], canonical_family: str) -> float | None:
    values: list[int] = []
    for asset in assets:
        if canonical_pose_family_name(asset.get("source_pose_family") or asset.get("pose_family")) != canonical_family:
            continue
        size = asset.get("source_object_size_px")
        if not isinstance(size, list) or len(size) < 2:
            continue
        try:
            values.append(max(1, max(int(size[0]), int(size[1]))))
        except (TypeError, ValueError):
            continue
    if not values:
        return None
    return float(np.median(values))


def upright_scale_correction_for_assets(
    assets: list[dict[str, Any]],
    physical_size: dict[str, Any] | None,
) -> dict[str, Any]:
    lying_major = median_source_major_axis_px(assets, "lying")
    upright_major = median_source_major_axis_px(assets, "upright")
    length_mm, width_mm, height_mm = object_physical_size_mm(physical_size)
    physical_ratio = length_mm / max(width_mm, height_mm, 1.0)
    if lying_major and upright_major:
        raw_ratio = lying_major / max(upright_major, 1.0)
        physical_min = max(UPRIGHT_SCALE_CORRECTION_MIN_RATIO, physical_ratio * 0.75)
        physical_max = min(UPRIGHT_SCALE_CORRECTION_MAX_RATIO, physical_ratio * 1.25)
        if physical_min > physical_max:
            physical_min, physical_max = UPRIGHT_SCALE_CORRECTION_MIN_RATIO, UPRIGHT_SCALE_CORRECTION_MAX_RATIO
        base_ratio = min(max(raw_ratio, physical_min), physical_max)
        ratio = min(
            max(base_ratio * UPRIGHT_SCALE_VISUAL_ADJUSTMENT, UPRIGHT_SCALE_CORRECTION_MIN_RATIO),
            UPRIGHT_SCALE_CORRECTION_MAX_RATIO,
        )
        basis = "pose_collection_source_major_axis_ratio_clamped_to_physical_ratio"
        source_dimensions = {
            "lying_source_major_axis_px_median": round(float(lying_major), 3),
            "upright_source_major_axis_px_median": round(float(upright_major), 3),
            "physical_ratio_min": round(float(physical_min), 3),
            "physical_ratio_max": round(float(physical_max), 3),
        }
    else:
        raw_ratio = physical_ratio
        base_ratio = min(max(raw_ratio, 1.0), UPRIGHT_SCALE_CORRECTION_MAX_RATIO)
        ratio = min(
            max(base_ratio * UPRIGHT_SCALE_VISUAL_ADJUSTMENT, UPRIGHT_SCALE_CORRECTION_MIN_RATIO),
            UPRIGHT_SCALE_CORRECTION_MAX_RATIO,
        )
        basis = "canonical_physical_length_to_diameter_ratio"
        source_dimensions = {
            "length_mm": round(float(length_mm), 3),
            "diameter_mm": round(float(max(width_mm, height_mm)), 3),
        }
    return {
        "upright_scale_correction": round(float(ratio), 6),
        "upright_scale_correction_raw": round(float(raw_ratio), 6),
        "upright_scale_correction_before_visual_adjustment": round(float(base_ratio), 6),
        "upright_scale_visual_adjustment": round(float(UPRIGHT_SCALE_VISUAL_ADJUSTMENT), 6),
        "upright_scale_adjustment_percent": round(float((UPRIGHT_SCALE_VISUAL_ADJUSTMENT - 1.0) * 100.0), 2),
        "upright_scale_adjustment_reason": "owner_followup_reduce_upright_top_view_10_to_20_percent",
        "upright_scale_visually_adjusted": bool(abs(float(UPRIGHT_SCALE_VISUAL_ADJUSTMENT) - 1.0) > 0.0005),
        "upright_scale_correction_basis": basis,
        "upright_scale_correction_source_dimensions": source_dimensions,
        "upright_scale_correction_physical_ratio": round(float(physical_ratio), 6),
        "upright_scale_correction_clamped": bool(abs(float(raw_ratio) - float(base_ratio)) > 0.0005),
    }


def apply_upright_scale_correction_metadata(assets: list[dict[str, Any]], physical_size: dict[str, Any] | None) -> None:
    correction = upright_scale_correction_for_assets(assets, physical_size)
    ratio = float(correction["upright_scale_correction"])
    for asset in assets:
        if canonical_pose_family_name(asset.get("source_pose_family") or asset.get("pose_family")) != "upright":
            asset.setdefault("upright_scale_correction", 1.0)
            continue
        before = asset.get("render_footprint_px")
        if not (isinstance(before, list) and len(before) >= 2):
            continue
        try:
            before_px = [max(1, int(before[0])), max(1, int(before[1]))]
        except (TypeError, ValueError):
            continue
        basis_before = str(asset.get("render_scale_basis") or "cap_outer_edge_diameter_mm")
        if basis_before in {"top_view_length_width_physical_footprint", "shared_length_width_physical_footprint"}:
            asset.update(
                {
                    "render_footprint_px_before_correction": before_px,
                    "render_footprint_px_after_correction": before_px,
                    "render_size_hint_px_before_correction": before_px,
                    "render_size_hint_px": before_px,
                    "render_footprint_px": before_px,
                    "canonical_width_px": before_px[0],
                    "canonical_height_px": before_px[1],
                    "render_scale_basis_before_correction": basis_before,
                    "render_scale_basis": basis_before,
                    "upright_scale_correction": 1.0,
                    "upright_scale_correction_raw": correction["upright_scale_correction_raw"],
                    "upright_scale_correction_before_visual_adjustment": 1.0,
                    "upright_scale_visual_adjustment": 1.0,
                    "upright_scale_adjustment_percent": 0.0,
                    "upright_scale_adjustment_reason": "non_cylindrical_top_view_uses_physical_length_width_no_visual_adjustment",
                    "upright_scale_visually_adjusted": False,
                    "upright_scale_correction_basis": "physical_length_width_top_view",
                    "upright_scale_correction_source_dimensions": correction["upright_scale_correction_source_dimensions"],
                    "upright_scale_correction_physical_ratio": correction["upright_scale_correction_physical_ratio"],
                    "upright_scale_correction_clamped": False,
                }
            )
            continue
        after_px = [max(16, int(round(before_px[0] * ratio))), max(16, int(round(before_px[1] * ratio)))]
        asset.update(correction)
        asset.update(
            {
                "render_footprint_px_before_correction": before_px,
                "render_footprint_px_after_correction": after_px,
                "render_size_hint_px_before_correction": before_px,
                "render_size_hint_px": after_px,
                "render_footprint_px": after_px,
                "canonical_width_px": after_px[0],
                "canonical_height_px": after_px[1],
                "render_scale_basis_before_correction": basis_before,
                "render_scale_basis": f"{basis_before}_scaled_by_{correction['upright_scale_correction_basis']}",
            }
        )


def asset_visible_shape_px(asset: dict[str, Any]) -> tuple[int, int] | None:
    for width_key, height_key in (
        ("visible_width_px", "visible_height_px"),
        ("canonical_visible_width_px", "canonical_visible_height_px"),
    ):
        try:
            width = int(asset.get(width_key) or 0)
            height = int(asset.get(height_key) or 0)
        except (TypeError, ValueError):
            width, height = 0, 0
        if width > 0 and height > 0:
            return width, height
    bbox = asset.get("normalized_bbox_xyxy")
    if isinstance(bbox, list) and len(bbox) >= 4:
        try:
            width = int(bbox[2]) - int(bbox[0])
            height = int(bbox[3]) - int(bbox[1])
            if width > 0 and height > 0:
                return width, height
        except (TypeError, ValueError):
            pass
    path = Path(str(asset.get("path") or ""))
    if path.exists():
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is not None and image.ndim == 3 and image.shape[2] >= 4:
            bbox = alpha_bbox(image[:, :, 3])
            width = int(bbox[2] - bbox[0])
            height = int(bbox[3] - bbox[1])
            if width > 0 and height > 0:
                return width, height
    size = asset.get("source_object_size_px")
    if isinstance(size, list) and len(size) >= 2:
        try:
            width = int(size[0])
            height = int(size[1])
            if width > 0 and height > 0:
                return width, height
        except (TypeError, ValueError):
            pass
    return None


def apply_laying_standard_render_size_hints(assets: list[dict[str, Any]]) -> None:
    lying_shapes = [
        shape
        for asset in assets
        if canonical_pose_family_name(asset.get("source_pose_family") or asset.get("pose_family")) == "lying"
        for shape in [asset_visible_shape_px(asset)]
        if shape is not None
    ]
    reference_shapes = lying_shapes or [shape for asset in assets for shape in [asset_visible_shape_px(asset)] if shape is not None]
    if not reference_shapes:
        return
    median_w = float(np.median([shape[0] for shape in reference_shapes]))
    median_h = float(np.median([shape[1] for shape in reference_shapes]))
    long_axis = "height" if median_h >= median_w else "width"
    for asset in assets:
        footprint = asset.get("render_footprint_px") or asset.get("render_size_hint_px")
        if not (isinstance(footprint, list) and len(footprint) >= 2):
            continue
        try:
            first = max(1, int(footprint[0]))
            second = max(1, int(footprint[1]))
        except (TypeError, ValueError):
            continue
        long_side = max(first, second)
        short_side = min(first, second)
        oriented = [long_side, short_side] if long_axis == "width" else [short_side, long_side]
        asset.update(
            {
                "render_footprint_px_unoriented_long_short": [int(long_side), int(short_side)],
                "render_footprint_px_before_laying_standard_orientation": [int(first), int(second)],
                "render_footprint_px": oriented,
                "render_size_hint_px": oriented,
                "canonical_width_px": oriented[0],
                "canonical_height_px": oriented[1],
                "render_long_short_orientation_basis": "lying_pose_collection_visible_bbox",
                "render_long_edge_axis": long_axis,
                "render_laying_standard_reference_visible_size_px": [round(median_w, 3), round(median_h, 3)],
            }
        )


def sprite_render_size_px(item: dict[str, Any], sprite_meta: dict[str, Any] | None, material_type: str) -> tuple[int, int]:
    if material_type == "text":
        return physical_render_size_px(item, material_type)
    meta = sprite_meta or {}
    hint = meta.get("render_size_hint_px") or meta.get("render_footprint_px")
    if isinstance(hint, list) and len(hint) >= 2:
        try:
            return max(16, int(hint[0])), max(16, int(hint[1]))
        except (TypeError, ValueError):
            pass
    source_size = meta.get("source_object_size_px") or [int(meta.get("width") or 1), int(meta.get("height") or 1)]
    footprint = pose_render_footprint_metadata(str(meta.get("source_pose_family") or meta.get("pose_family") or ""), source_size, item.get("physical_size"))
    return int(footprint["render_footprint_px"][0]), int(footprint["render_footprint_px"][1])


def canonical_sprite_canvas_size_px(asset: dict[str, Any]) -> tuple[int, int] | None:
    value = asset.get("canonical_asset_dimensions_px") or asset.get("canonical_canvas_size_px")
    if isinstance(value, list) and len(value) >= 2:
        try:
            return max(1, int(value[0])), max(1, int(value[1]))
        except (TypeError, ValueError):
            return None
    return None


def transparent_object_alpha(asset: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    stats = {
        "transparent_alpha_policy": "preserve_glass_body_weak_alpha",
        "glass_fraction": 0.0,
        "opaque_anchor_fraction": 0.0,
        "edge_fraction": 0.0,
        "transparent_alpha_applied": False,
    }
    if asset.size == 0 or mask.size == 0:
        return mask, stats
    hsv = cv2.cvtColor(asset, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(asset, cv2.COLOR_BGR2GRAY)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    edges = cv2.dilate(cv2.Canny(gray, 36, 116), np.ones((3, 3), np.uint8), iterations=1) > 0
    dark_or_colored = ((val < 118) & (sat > 24)) | (sat > 92)
    glass_body = (mask > 20) & (sat < 72) & (val > 108) & ~edges & ~dark_or_colored
    masked_pixels = max(1, int((mask > 20).sum()))
    opaque_anchor_fraction = float((dark_or_colored & (mask > 20)).sum()) / masked_pixels
    edge_fraction = float((edges & (mask > 20)).sum()) / masked_pixels
    glass_fraction = float(glass_body.sum()) / masked_pixels
    stats.update(
        {
            "glass_fraction": round(float(glass_fraction), 5),
            "opaque_anchor_fraction": round(float(opaque_anchor_fraction), 5),
            "edge_fraction": round(float(edge_fraction), 5),
        }
    )
    has_transparency_evidence = (
        glass_fraction > 0.12
        and opaque_anchor_fraction < 0.55
        and (opaque_anchor_fraction > 0.006 or edge_fraction > 0.025)
    )
    adjusted = mask.copy()
    if has_transparency_evidence and int(glass_body.sum()) > 80:
        adjusted[glass_body] = np.minimum(adjusted[glass_body], 92)
        highlight = (mask > 20) & (sat < 62) & (val > 185)
        adjusted[highlight] = np.maximum(adjusted[highlight], 126)
        adjusted[edges | dark_or_colored] = np.maximum(adjusted[edges | dark_or_colored], mask[edges | dark_or_colored])
        stats["transparent_alpha_applied"] = True
    return cv2.GaussianBlur(adjusted, (3, 3), 0), stats


def solid_object_alpha(mask: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    stats = {
        "transparent_alpha_policy": "solid_foreground_opaque_mask",
        "glass_fraction": 0.0,
        "opaque_anchor_fraction": 1.0,
        "edge_fraction": 0.0,
        "transparent_alpha_applied": False,
        "solid_alpha_applied": True,
    }
    if mask.size == 0:
        return mask, stats
    binary = (mask > 20).astype(np.uint8) * 255
    if int((binary > 0).sum()) == 0:
        return mask, stats
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    softened = cv2.GaussianBlur(binary, (3, 3), 0)
    softened[binary == 255] = 255
    return softened, stats


def material_aware_object_alpha(
    asset: np.ndarray,
    mask: np.ndarray,
    metadata: dict[str, Any] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    policy = object_alpha_material_policy(None, metadata)
    if policy == "transparent":
        adjusted, stats = transparent_object_alpha(asset, mask)
        stats["object_alpha_material_policy"] = "transparent"
        return adjusted, stats
    adjusted, stats = solid_object_alpha(mask)
    stats["object_alpha_material_policy"] = "opaque"
    return adjusted, stats


def normalize_angle_180(angle: float) -> float:
    normalized = (float(angle) + 90.0) % 180.0 - 90.0
    return 90.0 if normalized <= -89.999 else normalized


def masked_major_axis_angle(mask: np.ndarray) -> tuple[float, float]:
    ys, xs = np.where(mask > 8)
    if len(xs) < 24:
        return 0.0, 1.0
    points = np.column_stack([xs.astype(np.float32), ys.astype(np.float32)])
    centered = points - points.mean(axis=0)
    cov = np.cov(centered, rowvar=False)
    values, vectors = np.linalg.eigh(cov)
    order = np.argsort(values)[::-1]
    major = vectors[:, order[0]]
    angle = normalize_angle_180(math.degrees(math.atan2(float(major[1]), float(major[0]))))
    ratio = float(values[order[0]] / max(values[order[1]], 1e-6)) if len(values) >= 2 else 1.0
    return angle, ratio


def rotate_masked_asset(
    asset: np.ndarray,
    mask: np.ndarray,
    angle: float,
) -> tuple[np.ndarray, np.ndarray]:
    h, w = asset.shape[:2]
    safety_pad = max(10, int(round(max(w, h) * 0.08)))
    asset, mask = add_sprite_safety_margin(asset, mask, safety_pad)
    h, w = asset.shape[:2]
    if abs(angle) < 0.05:
        return trim_masked_asset(asset, mask, pad=safety_pad)
    radians = math.radians(abs(angle))
    new_w = max(1, int(math.ceil(w * math.cos(radians) + h * math.sin(radians)))) + safety_pad * 2
    new_h = max(1, int(math.ceil(w * math.sin(radians) + h * math.cos(radians)))) + safety_pad * 2
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    matrix[0, 2] += (new_w - w) / 2
    matrix[1, 2] += (new_h - h) / 2
    rotated_asset = cv2.warpAffine(
        asset,
        matrix,
        (new_w, new_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    rotated_mask = cv2.warpAffine(
        mask,
        matrix,
        (new_w, new_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    return trim_masked_asset(rotated_asset, rotated_mask, pad=safety_pad)


def alpha_bbox(mask: np.ndarray, threshold: int = 8) -> list[int]:
    ys, xs = np.where(mask > threshold)
    if len(xs) == 0 or len(ys) == 0:
        return [0, 0, 0, 0]
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def alpha_edge_max(mask: np.ndarray) -> int:
    if mask.size == 0:
        return 0
    edge = np.concatenate([mask[0, :], mask[-1, :], mask[:, 0], mask[:, -1]])
    return int(edge.max()) if edge.size else 0


def alpha_edge_stats(mask: np.ndarray) -> dict[str, Any]:
    if mask.size == 0:
        return {"max": 0, "nonzero_px": 0, "mean": 0.0}
    edge = np.concatenate([mask[0, :], mask[-1, :], mask[:, 0], mask[:, -1]])
    if edge.size == 0:
        return {"max": 0, "nonzero_px": 0, "mean": 0.0}
    return {
        "max": int(edge.max()),
        "nonzero_px": int((edge > 0).sum()),
        "mean": round(float(edge.mean()), 4),
    }


def alpha_component_count(mask: np.ndarray) -> int:
    if mask.size == 0:
        return 0
    num, _, stats, _ = cv2.connectedComponentsWithStats((mask > 12).astype(np.uint8), connectivity=8)
    if num <= 1:
        return 0
    image_area = mask.shape[0] * mask.shape[1]
    return sum(1 for idx in range(1, num) if stats[idx, cv2.CC_STAT_AREA] >= max(24, image_area * 0.00008))


def add_sprite_safety_margin(asset: np.ndarray, mask: np.ndarray, margin: int = 10) -> tuple[np.ndarray, np.ndarray]:
    if asset.size == 0 or mask.size == 0:
        return asset, mask
    return (
        cv2.copyMakeBorder(asset, margin, margin, margin, margin, cv2.BORDER_CONSTANT, value=(0, 0, 0)),
        cv2.copyMakeBorder(mask, margin, margin, margin, margin, cv2.BORDER_CONSTANT, value=0),
    )


def normalize_sprite_upright(asset: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    trimmed_asset, trimmed_mask = trim_masked_asset(asset, mask, pad=8)
    original_h, original_w = trimmed_asset.shape[:2]
    orientation_angle, axis_ratio = masked_major_axis_angle(trimmed_mask)
    target_axis = 90.0
    correction = normalize_angle_180(orientation_angle - target_axis)
    if axis_ratio < 1.18:
        correction = 0.0
    pre_rotation_margin = max(18, int(round(max(original_w, original_h) * 0.14)))
    padded_asset, padded_mask = add_sprite_safety_margin(trimmed_asset, trimmed_mask, pre_rotation_margin)
    upright_asset, upright_mask = rotate_masked_asset(padded_asset, padded_mask, correction)
    return upright_asset, upright_mask, {
        "original_angle_degrees": round(float(orientation_angle), 3),
        "rotation_degrees": round(float(correction), 3),
        "original_orientation_angle": round(float(orientation_angle), 3),
        "original_orientation_angle_degrees": round(float(orientation_angle), 3),
        "rotation_degrees_applied": round(float(correction), 3),
        "rotation_degrees_applied_to_upright": round(float(correction), 3),
        "source_restore_rotation_degrees": round(float(-correction), 3),
        "normalized_axis_target_degrees": round(float(target_axis), 3),
        "orientation_axis_ratio": round(float(axis_ratio), 4),
        "pre_normalized_asset_size_px": [int(original_w), int(original_h)],
        "pre_rotation_safety_margin_px": int(pre_rotation_margin),
        "upright_normalized": True,
    }


def write_clean_sprite(path: Path, asset: np.ndarray, mask: np.ndarray, metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
    asset, mask, orientation_metadata = normalize_sprite_upright(asset, mask)
    if asset.size == 0 or mask.size == 0 or int((mask > 8).sum()) < 240:
        return None
    mask, alpha_policy_stats = material_aware_object_alpha(asset, mask, metadata)
    post_rotation_margin = max(18, int(round(max(asset.shape[:2]) * 0.08)))
    asset, mask = add_sprite_safety_margin(asset, mask, post_rotation_margin)
    bbox = alpha_bbox(mask)
    edge_max = alpha_edge_max(mask)
    edge_stats = alpha_edge_stats(mask)
    if edge_max > 12:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    rgba = cv2.cvtColor(asset, cv2.COLOR_BGR2BGRA)
    rgba[:, :, 3] = mask
    if not cv2.imwrite(str(path), rgba):
        return None
    payload = {
        "kind": "clean_object_sprite",
        "path": str(path),
        "method": "preprocessed_alpha_sprite",
        "width": int(asset.shape[1]),
        "height": int(asset.shape[0]),
        "normalized_asset_size_px": [int(asset.shape[1]), int(asset.shape[0])],
        "normalized_asset_dimensions_px": [int(asset.shape[1]), int(asset.shape[0])],
        "normalized_bbox_xyxy": bbox,
        "post_rotation_safety_margin_px": int(post_rotation_margin),
        "edge_alpha_max": edge_max,
        "edge_alpha_pass": True,
        "alpha_edge_stats": edge_stats,
        "mask_strategy": "provided_alpha_mask",
        "foreground_component_bbox_xyxy": bbox,
        "removed_stray_component_count": 0,
        "removed_stray_component_area_px": 0,
    }
    if metadata:
        payload.update(metadata)
    payload.update(alpha_policy_stats)
    payload.update(orientation_metadata)
    if (
        metadata
        and isinstance(metadata.get("physical_size_mm"), dict)
        and (not payload.get("render_footprint_px") or not payload.get("render_footprint_mm") or not payload.get("render_scale_basis"))
    ):
        pose_family = str(metadata.get("source_pose_family") or metadata.get("pose_family") or "")
        source_size = metadata.get("source_object_size_px") or payload["normalized_asset_size_px"]
        payload.update(pose_render_footprint_metadata(pose_family, source_size, metadata.get("physical_size_mm")))
    return payload


def normalize_sprite_family_canvases(generated: list[dict[str, Any]]) -> None:
    groups: dict[str, list[dict[str, Any]]] = {"all_pose_families": generated}
    for family_assets in groups.values():
        loaded: list[tuple[dict[str, Any], np.ndarray, np.ndarray]] = []
        visible_major_axes = []
        for asset in family_assets:
            image = cv2.imread(str(Path(str(asset.get("path", "")))), cv2.IMREAD_UNCHANGED)
            if image is None or image.ndim != 3 or image.shape[2] < 4:
                continue
            alpha = image[:, :, 3]
            bbox = alpha_bbox(alpha)
            visible_w = int(bbox[2] - bbox[0])
            visible_h = int(bbox[3] - bbox[1])
            visible_major = max(visible_w, visible_h)
            if visible_major <= 0:
                continue
            visible_major_axes.append(visible_major)
            loaded.append((asset, image[:, :, :3], alpha))
        if not loaded:
            continue
        canonical_visible_major_axis = max(visible_major_axes)
        for asset, bgr, alpha in loaded:
            asset_bgr, asset_alpha = trim_masked_asset(bgr, alpha, pad=8)
            for _ in range(3):
                bbox = alpha_bbox(asset_alpha)
                visible_w = max(1, int(bbox[2] - bbox[0]))
                visible_h = max(1, int(bbox[3] - bbox[1]))
                visible_major = max(visible_w, visible_h)
                scale = canonical_visible_major_axis / visible_major
                if abs(scale - 1.0) <= 0.006:
                    break
                resized_size = (
                    max(1, int(round(asset_bgr.shape[1] * scale))),
                    max(1, int(round(asset_bgr.shape[0] * scale))),
                )
                asset_bgr = cv2.resize(asset_bgr, resized_size, interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)
                asset_alpha = cv2.resize(asset_alpha, resized_size, interpolation=cv2.INTER_LINEAR)
            margin = max(18, int(round(max(asset_bgr.shape[:2]) * 0.08)))
            asset_bgr, asset_alpha = add_sprite_safety_margin(asset_bgr, asset_alpha, margin)
            bbox = alpha_bbox(asset_alpha)
            rgba = cv2.cvtColor(asset_bgr, cv2.COLOR_BGR2BGRA)
            rgba[:, :, 3] = asset_alpha
            cv2.imwrite(str(Path(str(asset.get("path", "")))), rgba)
            edge_max = alpha_edge_max(asset_alpha)
            asset.update(
                {
                    "width": int(asset_bgr.shape[1]),
                    "height": int(asset_bgr.shape[0]),
                    "normalized_asset_size_px": [int(asset_bgr.shape[1]), int(asset_bgr.shape[0])],
                    "normalized_asset_dimensions_px": [int(asset_bgr.shape[1]), int(asset_bgr.shape[0])],
                    "canonical_asset_dimensions_px": [int(asset_bgr.shape[1]), int(asset_bgr.shape[0])],
                    "canonical_canvas_size_px": [int(asset_bgr.shape[1]), int(asset_bgr.shape[0])],
                    "normalized_bbox_xyxy": bbox,
                    "canonical_visible_width_px": int(bbox[2] - bbox[0]),
                    "canonical_visible_major_axis_px": int(canonical_visible_major_axis),
                    "visible_width_px": int(bbox[2] - bbox[0]),
                    "visible_height_px": int(bbox[3] - bbox[1]),
                    "canonical_family_width_normalized": True,
                    "canonical_all_pose_family_size_normalized": True,
                    "post_rotation_safety_margin_px": int(margin),
                    "edge_alpha_max": edge_max,
                    "edge_alpha_pass": edge_max <= 12,
                    "alpha_edge_stats": alpha_edge_stats(asset_alpha),
                }
            )


def alpha_component_cutouts(image: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    if image.ndim != 3 or image.shape[2] < 4:
        return []
    bgr = image[:, :, :3]
    alpha = image[:, :, 3]
    binary = (alpha > 12).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    image_area = alpha.shape[0] * alpha.shape[1]
    cutouts: list[tuple[np.ndarray, np.ndarray]] = []
    for idx in range(1, num):
        x, y, w, h, area = stats[idx]
        if area < max(240, image_area * 0.0005) or w < 8 or h < 8:
            continue
        pad = max(4, int(max(w, h) * 0.04))
        x1, y1 = max(0, x - pad), max(0, y - pad)
        x2, y2 = min(alpha.shape[1], x + w + pad), min(alpha.shape[0], y + h + pad)
        cutouts.append((bgr[y1:y2, x1:x2].copy(), alpha[y1:y2, x1:x2].copy()))
    return sorted(cutouts, key=lambda item: int((item[1] > 12).sum()), reverse=True)[:12]


def filter_cutout_to_focus_cell(
    asset: np.ndarray,
    mask: np.ndarray,
    focus_bbox: tuple[int, int, int, int],
) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    if asset.size == 0 or mask.size == 0:
        return None
    binary = (mask > 12).astype(np.uint8)
    num, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if num <= 1:
        return None
    fx1, fy1, fx2, fy2 = focus_bbox
    focus_w = max(1, fx2 - fx1)
    focus_h = max(1, fy2 - fy1)
    margin_x = max(6, int(round(focus_w * 0.08)))
    margin_y = max(6, int(round(focus_h * 0.08)))
    keep_x1, keep_y1 = fx1 - margin_x, fy1 - margin_y
    keep_x2, keep_y2 = fx2 + margin_x, fy2 + margin_y
    focus_cx = (fx1 + fx2) / 2.0
    focus_cy = (fy1 + fy2) / 2.0
    max_center_distance = math.hypot(focus_w, focus_h) * 0.58
    kept = np.zeros_like(mask)
    mask_area = mask.shape[0] * mask.shape[1]
    for idx in range(1, num):
        x, y, w, h, area = stats[idx]
        if area < max(24, mask_area * 0.00008):
            continue
        cx, cy = centroids[idx]
        component_x2 = x + w
        component_y2 = y + h
        overlap_w = max(0, min(component_x2, fx2) - max(x, fx1))
        overlap_h = max(0, min(component_y2, fy2) - max(y, fy1))
        overlap_area = overlap_w * overlap_h
        center_in_focus = keep_x1 <= cx <= keep_x2 and keep_y1 <= cy <= keep_y2
        center_near_focus = math.hypot(float(cx - focus_cx), float(cy - focus_cy)) <= max_center_distance
        overlaps_focus = overlap_area >= max(12, area * 0.18)
        if center_in_focus or (center_near_focus and overlaps_focus):
            kept[labels == idx] = mask[labels == idx]
    if int((kept > 8).sum()) < 240:
        return None
    bbox = alpha_bbox(kept)
    x1, y1, x2, y2 = bbox
    pad = max(4, int(round(max(x2 - x1, y2 - y1) * 0.025)))
    x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
    x2, y2 = min(mask.shape[1], x2 + pad), min(mask.shape[0], y2 + pad)
    return asset[y1:y2, x1:x2].copy(), kept[y1:y2, x1:x2].copy(), (int(x1), int(y1), int(x2), int(y2))


def usable_object_cutout(cutout: tuple[np.ndarray, np.ndarray] | None, source_shape: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray] | None:
    if not cutout:
        return None
    cut_asset, cut_mask = trim_masked_asset(cutout[0], cutout[1], pad=2)
    source_h, source_w = source_shape[:2]
    cut_h, cut_w = cut_asset.shape[:2]
    mask_fill = float((cut_mask > 8).sum()) / max(1, cut_mask.shape[0] * cut_mask.shape[1])
    if cut_w > source_w * 0.82 and cut_h > source_h * 0.82 and mask_fill > 0.72:
        return None
    return cut_asset, cut_mask


def cleanup_crop_alpha_components(
    asset: np.ndarray,
    alpha: np.ndarray,
    anchor_xy: tuple[float, float] | None = None,
    min_area: int = 35,
) -> tuple[np.ndarray, dict[str, Any]]:
    if asset.size == 0 or alpha.size == 0:
        return alpha, {
            "mask_strategy": "crop_local_component_cleanup_empty",
            "foreground_component_bbox_xyxy": [0, 0, 0, 0],
            "removed_stray_component_count": 0,
            "removed_stray_component_area_px": 0,
        }
    binary = (alpha > 28).astype(np.uint8)
    num, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    crop_area = alpha.shape[0] * alpha.shape[1]
    components = []
    for idx in range(1, num):
        x, y, w, h, area = stats[idx]
        if area < max(min_area, int(crop_area * 0.002)):
            continue
        cx, cy = centroids[idx]
        components.append(
            {
                "idx": int(idx),
                "bbox": [int(x), int(y), int(x + w), int(y + h)],
                "area": int(area),
                "center": [float(cx), float(cy)],
            }
        )
    if not components:
        return alpha, {
            "mask_strategy": "crop_local_component_cleanup_no_components",
            "foreground_component_bbox_xyxy": alpha_bbox(alpha),
            "removed_stray_component_count": 0,
            "removed_stray_component_area_px": 0,
        }
    if anchor_xy is None:
        anchor_xy = (asset.shape[1] / 2.0, asset.shape[0] / 2.0)
    ax, ay = anchor_xy
    diagonal = max(1.0, math.hypot(asset.shape[1], asset.shape[0]))

    def score(component: dict[str, Any]) -> float:
        x1, y1, x2, y2 = component["bbox"]
        cx, cy = component["center"]
        contains_anchor = x1 <= ax <= x2 and y1 <= ay <= y2
        distance = math.hypot(float(cx) - ax, float(cy) - ay) / diagonal
        return (2.4 if contains_anchor else 0.0) + math.log1p(float(component["area"])) - distance * 5.0

    selected = max(components, key=score)
    sx1, sy1, sx2, sy2 = selected["bbox"]
    selected_w = max(1, sx2 - sx1)
    selected_h = max(1, sy2 - sy1)
    selected_diag = max(1.0, math.hypot(selected_w, selected_h))
    support_gap_limit = max(10.0, min(selected_w, selected_h) * 0.42)

    def interval_overlap_ratio(a1: int, a2: int, b1: int, b2: int) -> float:
        overlap = max(0, min(a2, b2) - max(a1, b1))
        return overlap / max(1, min(a2 - a1, b2 - b1))

    def bbox_gap(bbox: list[int]) -> float:
        x1, y1, x2, y2 = bbox
        gap_x = max(0, max(sx1, x1) - min(sx2, x2))
        gap_y = max(0, max(sy1, y1) - min(sy2, y2))
        return math.hypot(float(gap_x), float(gap_y))

    keep_components = [selected]
    for component in components:
        if component["idx"] == selected["idx"]:
            continue
        x1, y1, x2, y2 = component["bbox"]
        cx, cy = component["center"]
        area_ratio = float(component["area"]) / max(1.0, float(selected["area"]))
        gap = bbox_gap(component["bbox"])
        horizontal_overlap = interval_overlap_ratio(x1, x2, sx1, sx2)
        vertical_overlap = interval_overlap_ratio(y1, y2, sy1, sy2)
        center_distance = math.hypot(float(cx) - ax, float(cy) - ay)
        close_projected_detail = (
            gap <= support_gap_limit
            and area_ratio <= 0.42
            and max(horizontal_overlap, vertical_overlap) >= 0.42
        )
        anchored_detail = (
            center_distance <= selected_diag * 0.72
            and gap <= support_gap_limit * 1.25
            and area_ratio <= 0.24
            and (horizontal_overlap >= 0.22 or vertical_overlap >= 0.22)
        )
        if close_projected_detail or anchored_detail:
            keep_components.append(component)

    keep = np.zeros_like(alpha)
    for component in keep_components:
        keep[labels == component["idx"]] = 255
    cleaned = cv2.bitwise_and(alpha, keep)
    kept_indexes = {component["idx"] for component in keep_components}
    removed = [component for component in components if component["idx"] not in kept_indexes]
    kept_bbox = alpha_bbox(cleaned)
    return cleaned, {
        "mask_strategy": "crop_local_alpha_center_anchored_components",
        "foreground_component_bbox_xyxy": kept_bbox,
        "foreground_component_area_px": int(sum(component["area"] for component in keep_components)),
        "foreground_component_anchor_xy": [round(float(ax), 2), round(float(ay), 2)],
        "removed_stray_component_count": int(len(removed)),
        "removed_stray_component_area_px": int(sum(component["area"] for component in removed)),
        "candidate_component_count": int(len(components)),
        "kept_component_count": int(len(keep_components)),
    }


def alpha_component_summary(alpha: np.ndarray, threshold: int = 28) -> tuple[int, int]:
    if alpha.size == 0:
        return 0, 0
    num, _, stats, _ = cv2.connectedComponentsWithStats((alpha > threshold).astype(np.uint8), connectivity=8)
    min_area = max(35, int(alpha.shape[0] * alpha.shape[1] * 0.002))
    count = 0
    area_sum = 0
    for idx in range(1, num):
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        count += 1
        area_sum += area
    return count, area_sum


def preprocess_object_clean_sprites(item: dict[str, Any], allow_ai_cutout: bool = True, force: bool = False) -> bool:
    if accessory_material_type(item) == "text":
        return False
    item["material_alpha_policy"] = object_alpha_material_policy(item)
    pose_jobs = [
        job
        for job in candidate_image_jobs(item)
        if Path(str(job.get("output_path", ""))).exists() and not job.get("intermediate")
    ]
    expected_pose_sprite_count = len(pose_jobs) * len(POSE_COLLECTION_GRID_POSITIONS)
    existing = clean_sprite_assets(item)
    existing_complete = clean_sprites_policy_complete(item, existing)
    expected_existing_count = min(18, expected_pose_sprite_count) if expected_pose_sprite_count else len(existing)
    if existing and not force and existing_complete and len(existing) >= expected_existing_count:
        return False

    uid = accessory_uid(item)
    sprite_dir = NORMALIZED_DIR / uid / "clean_sprites"
    generated: list[dict[str, Any]] = []
    rng = np.random.default_rng(int(item.get("created_at") or time.time()))
    physical_size = item.get("physical_size") if isinstance(item.get("physical_size"), dict) else {}
    alpha_policy = object_alpha_material_policy(item)

    failed_cells: list[dict[str, Any]] = []

    def add_cutout(
        cutout: tuple[np.ndarray, np.ndarray] | None,
        source_shape: tuple[int, ...],
        method: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        usable = usable_object_cutout(cutout, source_shape)
        if not usable:
            return False
        out_path = sprite_dir / f"sprite_{len(generated) + 1:02d}.png"
        asset = write_clean_sprite(out_path, usable[0], usable[1], metadata)
        if asset:
            asset["method"] = method
            generated.append(asset)
            return True
        return False

    pose_paths = [Path(str(job.get("output_path", ""))) for job in pose_jobs]
    for job in pose_jobs:
        pose_path = Path(str(job.get("output_path", "")))
        if not pose_path.exists():
            continue
        pose_family = str(job.get("pose_family") or "")
        pose = cv2.imread(str(pose_path), cv2.IMREAD_COLOR)
        if pose is not None:
            base_regions = pose_collection_regions(pose, padded=False)
            for idx, (x1, y1, x2, y2) in enumerate(pose_collection_regions(pose, padded=True)):
                tile = pose[y1:y2, x1:x2].copy()
                pose_position = POSE_COLLECTION_GRID_POSITIONS[idx] if idx < len(POSE_COLLECTION_GRID_POSITIONS) else str(idx)
                local_bbox = None
                cutout = None
                method = "pose_collection_lightweight_cutout"
                base_region = base_regions[idx] if idx < len(base_regions) else (x1, y1, x2, y2)
                focus_bbox = (
                    max(0, int(base_region[0] - x1)),
                    max(0, int(base_region[1] - y1)),
                    min(tile.shape[1], int(base_region[2] - x1)),
                    min(tile.shape[0], int(base_region[3] - y1)),
                )
                target_center_xy = ((focus_bbox[0] + focus_bbox[2]) / 2.0, (focus_bbox[1] + focus_bbox[3]) / 2.0)
                mask_diagnostics: dict[str, Any] = {}

                def apply_crop_component_cleanup(
                    crop_asset: np.ndarray,
                    crop_alpha: np.ndarray,
                    bbox: tuple[int, int, int, int],
                    source_alpha: np.ndarray | None = None,
                ) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]]:
                    source_count, source_area = alpha_component_summary(source_alpha if source_alpha is not None else crop_alpha)
                    bx1, by1, _, _ = bbox
                    local_anchor = (target_center_xy[0] - bx1, target_center_xy[1] - by1)
                    cleaned_alpha, diagnostics = cleanup_crop_alpha_components(crop_asset, crop_alpha, local_anchor)
                    kept_count, kept_area = alpha_component_summary(cleaned_alpha)
                    diagnostics["removed_stray_component_count"] = max(
                        int(diagnostics.get("removed_stray_component_count") or 0),
                        max(0, source_count - kept_count),
                    )
                    diagnostics["removed_stray_component_area_px"] = max(
                        int(diagnostics.get("removed_stray_component_area_px") or 0),
                        max(0, source_area - kept_area),
                    )
                    cleaned_bbox = alpha_bbox(cleaned_alpha)
                    updated_bbox = (
                        int(bx1 + cleaned_bbox[0]),
                        int(by1 + cleaned_bbox[1]),
                        int(bx1 + cleaned_bbox[2]),
                        int(by1 + cleaned_bbox[3]),
                    )
                    mask_diagnostics.update(diagnostics)
                    return crop_asset, cleaned_alpha, updated_bbox

                if allow_ai_cutout:
                    ai_cutout = ai_background_cutout_with_bbox(tile)
                    if ai_cutout:
                        full_alpha = np.zeros(tile.shape[:2], dtype=np.uint8)
                        bx1, by1, bx2, by2 = ai_cutout[2]
                        full_alpha[by1:by2, bx1:bx2] = ai_cutout[1]
                        focused = filter_cutout_to_focus_cell(tile, full_alpha, focus_bbox)
                        if focused:
                            crop_asset, crop_alpha, local_bbox = apply_crop_component_cleanup(
                                focused[0], focused[1], focused[2], full_alpha
                            )
                            cutout = (crop_asset, crop_alpha)
                            method = "pose_collection_crop_stage_alpha_cutout"
                if cutout is None:
                    fallback_cutout = green_screen_object_cutout_with_bbox(tile, rng)
                    if fallback_cutout:
                        full_alpha = np.zeros(tile.shape[:2], dtype=np.uint8)
                        bx1, by1, bx2, by2 = fallback_cutout[2]
                        full_alpha[by1:by2, bx1:bx2] = fallback_cutout[1]
                        focused = filter_cutout_to_focus_cell(tile, full_alpha, focus_bbox)
                        if focused:
                            crop_asset, crop_alpha, local_bbox = apply_crop_component_cleanup(
                                focused[0], focused[1], focused[2], full_alpha
                            )
                            cutout = (crop_asset, crop_alpha)
                            method = "pose_collection_crop_stage_alpha_fallback"
                        else:
                            crop_asset, crop_alpha, local_bbox = apply_crop_component_cleanup(
                                fallback_cutout[0], fallback_cutout[1], fallback_cutout[2], full_alpha
                            )
                            cutout = (crop_asset, crop_alpha)
                if local_bbox is None:
                    local_bbox = (0, 0, tile.shape[1], tile.shape[0])
                bx1, by1, bx2, by2 = local_bbox
                source_bbox = [int(x1 + bx1), int(y1 + by1), int(x1 + bx2), int(y1 + by2)]
                source_size_px = [int(source_bbox[2] - source_bbox[0]), int(source_bbox[3] - source_bbox[1])]
                metadata = {
                    "task_id": str(job.get("task_id") or deterministic_task_id(item, job)),
                    "source_pose_collection_job_id": str(job.get("job_id") or ""),
                    "source_pose_collection": str(pose_path),
                    "pose_family": pose_family,
                    "source_pose_family": pose_family,
                    "pose_index": idx,
                    "pose_position": pose_position,
                    "source_position": pose_position,
                    "source_image_size_px": [int(pose.shape[1]), int(pose.shape[0])],
                    "source_image_width": int(pose.shape[1]),
                    "source_image_height": int(pose.shape[0]),
                    "source_region_bbox_xyxy": [int(x1), int(y1), int(x2), int(y2)],
                    "source_region_core_bbox_xyxy": [int(base_region[0]), int(base_region[1]), int(base_region[2]), int(base_region[3])],
                    "source_region_target_center_xy": [
                        int(round(x1 + target_center_xy[0])),
                        int(round(y1 + target_center_xy[1])),
                    ],
                    "source_object_bbox_xyxy": source_bbox,
                    "source_object_center_xy": [
                            int(round((source_bbox[0] + source_bbox[2]) / 2)),
                            int(round((source_bbox[1] + source_bbox[3]) / 2)),
                    ],
                    "source_object_size_px": source_size_px,
                    "physical_size_mm": physical_size,
                    "material_alpha_policy": alpha_policy,
                }
                metadata.update(mask_diagnostics)
                metadata.update(pose_render_footprint_metadata(pose_family, source_size_px, physical_size))
                if not add_cutout(cutout, tile.shape, method, metadata):
                    failed_cells.append(
                        {
                            "pose_family": pose_family,
                            "source_pose_family": pose_family,
                            "pose_index": idx,
                            "pose_position": metadata["pose_position"],
                            "source_position": metadata["source_position"],
                            "source_region_bbox_xyxy": metadata["source_region_bbox_xyxy"],
                            "source_object_bbox_xyxy": source_bbox,
                            "source_object_size_px": source_size_px,
                            "reason": "no usable object cutout",
                        }
                    )

    if not generated and existing:
        for asset_meta in existing[:18]:
            path = Path(str(asset_meta.get("path", "")))
            image_any = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if image_any is None or image_any.ndim != 3 or image_any.shape[2] < 4:
                continue
            alpha = image_any[:, :, 3]
            if int((alpha > 8).sum()) < 240:
                continue
            bbox = alpha_bbox(alpha)
            source_size_px = [max(1, int(bbox[2] - bbox[0])), max(1, int(bbox[3] - bbox[1]))]
            pose_family = str(asset_meta.get("source_pose_family") or asset_meta.get("pose_family") or "")
            metadata = dict(asset_meta)
            metadata.update(
                {
                    "task_id": str(asset_meta.get("task_id") or "legacy_clean_sprite"),
                    "source_pose_collection_job_id": str(asset_meta.get("source_pose_collection_job_id") or "legacy_clean_sprite"),
                    "pose_family": pose_family or ("upright" if pose_family_is_top_view("", source_size_px) else "lying"),
                    "source_pose_family": pose_family or ("upright" if pose_family_is_top_view("", source_size_px) else "lying"),
                    "pose_position": str(asset_meta.get("pose_position") or asset_meta.get("source_position") or "center"),
                    "source_position": str(asset_meta.get("source_position") or asset_meta.get("pose_position") or "center"),
                    "source_image_size_px": [int(image_any.shape[1]), int(image_any.shape[0])],
                    "source_image_width": int(image_any.shape[1]),
                    "source_image_height": int(image_any.shape[0]),
                    "source_region_bbox_xyxy": asset_meta.get("source_region_bbox_xyxy") or bbox,
                    "source_object_bbox_xyxy": asset_meta.get("source_object_bbox_xyxy") or bbox,
                    "source_object_center_xy": asset_meta.get("source_object_center_xy")
                    or [int(round((bbox[0] + bbox[2]) / 2)), int(round((bbox[1] + bbox[3]) / 2))],
                    "source_object_size_px": asset_meta.get("source_object_size_px") or source_size_px,
                    "physical_size_mm": physical_size,
                    "material_alpha_policy": alpha_policy,
                    "legacy_sprite_policy_rebuild_source_path": str(path),
                }
            )
            metadata.update(pose_render_footprint_metadata(metadata["source_pose_family"], metadata["source_object_size_px"], physical_size))
            add_cutout((image_any[:, :, :3].copy(), alpha.copy()), image_any.shape, "legacy_clean_sprite_policy_rebuild", metadata)

    if not generated:
        for path in accessory_image_paths(item):
            if path in pose_paths:
                continue
            image_any = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if image_any is not None and image_any.ndim == 3 and image_any.shape[2] >= 4:
                for cutout in alpha_component_cutouts(image_any):
                    add_cutout(cutout, image_any.shape, "source_png_alpha", {"physical_size_mm": physical_size, "material_alpha_policy": alpha_policy})
            if generated:
                break
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None:
                continue
            if allow_ai_cutout:
                add_cutout(ai_background_cutout(image), image.shape, "source_one_time_ai_cutout", {"physical_size_mm": physical_size, "material_alpha_policy": alpha_policy})
            if not generated:
                add_cutout(object_cutout_from_image(image, rng), image.shape, "source_lightweight_cutout", {"physical_size_mm": physical_size, "material_alpha_policy": alpha_policy})
            if generated:
                break

    if not generated:
        return False

    retained = [
        asset
        for asset in item.get("normalized_assets", [])
        if asset.get("kind") != "clean_object_sprite"
    ]
    generated = generated[:18]
    normalize_sprite_family_canvases(generated)
    apply_upright_scale_correction_metadata(generated, physical_size)
    apply_laying_standard_render_size_hints(generated)
    item["normalized_assets"] = retained + generated
    expected_pose_sprite_count = len(pose_jobs) * len(POSE_COLLECTION_GRID_POSITIONS)
    expected_clean_count = min(18, expected_pose_sprite_count) if expected_pose_sprite_count else len(generated)
    metadata_complete = clean_sprites_policy_complete(item, generated)
    item["clean_sprite_status"] = "ready" if (not expected_clean_count or len(generated) >= expected_clean_count) and not failed_cells and metadata_complete else "partial"
    item["clean_sprite_count"] = len(generated)
    item["clean_sprite_expected_count"] = expected_clean_count
    item["clean_sprite_failed_cells"] = failed_cells
    item["clean_sprite_preprocessed_at"] = int(time.time())
    if failed_cells:
        item["preprocess"] = f"系统已预处理 {len(generated)}/{item['clean_sprite_expected_count']} 个无背景单体素材；失败格子已记录。"
    elif item["clean_sprite_status"] != "ready":
        item["preprocess"] = f"系统已预处理 {len(generated)}/{item['clean_sprite_expected_count']} 个无背景单体素材；元数据未完整，未标记 ready。"
    else:
        item["preprocess"] = "系统已预处理无背景单体素材，并记录原图坐标与物理尺寸；训练预览直接复用。"
    return True


def foreground_mask(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    border = np.concatenate(
        [
            image[: max(3, h // 20), :, :].reshape(-1, 3),
            image[-max(3, h // 20) :, :, :].reshape(-1, 3),
            image[:, : max(3, w // 20), :].reshape(-1, 3),
            image[:, -max(3, w // 20) :, :].reshape(-1, 3),
        ],
        axis=0,
    )
    bg = np.median(border, axis=0).astype(np.float32)
    diff = np.linalg.norm(image.astype(np.float32) - bg, axis=2)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    green_bg = (hue > 30) & (hue < 100) & (sat > 24) & (val > 35)
    red = ((hue < 14) | (hue > 165)) & (sat > 70)
    dark = val < 78
    bright_glass = (sat < 62) & (val > 128) & (diff > 10)
    mask = ((~green_bg & (diff > 18)) | red | dark | bright_glass).astype(np.uint8) * 255
    edges = cv2.Canny(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 45, 140)
    mask = cv2.bitwise_or(mask, cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((17, 17), np.uint8), iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    return mask


def object_cutout_from_image(image: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray] | None:
    mask = foreground_mask(image)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    components = []
    image_area = image.shape[0] * image.shape[1]
    for idx in range(1, num):
        x, y, w, h, area = stats[idx]
        if area < max(500, image_area * 0.001) or area > image_area * 0.55:
            continue
        if w < 8 or h < 8:
            continue
        components.append((x, y, w, h, area))
    if not components:
        return None
    components = sorted(components, key=lambda item: item[4], reverse=True)[:8]
    weights = np.array([item[4] for item in components], dtype=float)
    weights = weights / weights.sum()
    x, y, w, h, _ = components[int(rng.choice(len(components), p=weights))]
    pad = max(8, int(max(w, h) * 0.18))
    x1, y1 = max(0, x - pad), max(0, y - pad)
    x2, y2 = min(image.shape[1], x + w + pad), min(image.shape[0], y + h + pad)
    crop = image[y1:y2, x1:x2].copy()
    crop_mask = mask[y1:y2, x1:x2].copy()
    crop_mask = cv2.GaussianBlur(crop_mask, (5, 5), 0)
    return crop, crop_mask


def rembg_session() -> Any | None:
    global _rembg_session
    with _rembg_lock:
        if _rembg_session is not None:
            return _rembg_session
        try:
            from rembg import new_session

            _rembg_session = new_session("u2net")
            return _rembg_session
        except Exception:
            _rembg_session = None
            return None


def ai_background_cutout_with_bbox(image: np.ndarray) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    session = rembg_session()
    if session is None:
        return None
    try:
        from PIL import Image
        from rembg import remove

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        with _rembg_lock:
            result = remove(
                Image.fromarray(rgb),
                session=session,
                alpha_matting=True,
                alpha_matting_foreground_threshold=240,
                alpha_matting_background_threshold=12,
                alpha_matting_erode_size=8,
            )
        rgba = np.array(result.convert("RGBA"))
        alpha = rgba[:, :, 3]
        ys, xs = np.where(alpha > 12)
        if len(xs) == 0 or len(ys) == 0:
            return None
        x1, x2 = max(0, xs.min() - 4), min(alpha.shape[1], xs.max() + 5)
        y1, y2 = max(0, ys.min() - 4), min(alpha.shape[0], ys.max() + 5)
        if (x2 - x1) * (y2 - y1) < 240:
            return None
        crop_rgb = rgba[y1:y2, x1:x2, :3]
        crop_alpha = alpha[y1:y2, x1:x2]
        crop_bgr = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2BGR)
        return crop_bgr, crop_alpha, (int(x1), int(y1), int(x2), int(y2))
    except Exception:
        return None


def ai_background_cutout(image: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    result = ai_background_cutout_with_bbox(image)
    if not result:
        return None
    return result[0], result[1]


def green_screen_object_cutout_with_bbox(image: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    red = (((hue < 14) | (hue > 165)) & (sat > 70)).astype(np.uint8) * 255
    dark = ((val < 92) & (sat > 25)).astype(np.uint8) * 255
    glass_highlight = ((sat < 80) & (val > 125)).astype(np.uint8) * 255
    edges = cv2.Canny(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 45, 135)
    seed = cv2.bitwise_or(cv2.bitwise_or(red, dark), cv2.bitwise_or(glass_highlight, edges))
    seed = cv2.morphologyEx(seed, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    joined = cv2.dilate(seed, np.ones((29, 29), np.uint8), iterations=1)
    joined = cv2.morphologyEx(joined, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8), iterations=1)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    components = []
    image_area = image.shape[0] * image.shape[1]
    for idx in range(1, num):
        x, y, w, h, area = stats[idx]
        if area < max(650, image_area * 0.002) or area > image_area * 0.45:
            continue
        if w < 18 or h < 18:
            continue
        anchor = int(red[y : y + h, x : x + w].sum() // 255) + int(dark[y : y + h, x : x + w].sum() // 255)
        highlight = int(glass_highlight[y : y + h, x : x + w].sum() // 255)
        components.append((x, y, w, h, area, anchor, highlight))
    if not components:
        fallback = object_cutout_from_image(image, rng)
        if not fallback:
            return None
        return fallback[0], fallback[1], (0, 0, fallback[0].shape[1], fallback[0].shape[0])
    anchored = [item for item in components if item[5] > 25]
    components = sorted(anchored or components, key=lambda item: item[5] * 12 + item[6] * 0.2 + item[4] * 0.02, reverse=True)[:5]
    x, y, w, h, *_ = components[0]
    pad = max(10, int(max(w, h) * 0.08))
    x1, y1 = max(0, x - pad), max(0, y - pad)
    x2, y2 = min(image.shape[1], x + w + pad), min(image.shape[0], y + h + pad)
    crop = image[y1:y2, x1:x2].copy()
    crop_hsv = hsv[y1:y2, x1:x2]
    crop_seed = seed[y1:y2, x1:x2]
    crop_joined = joined[y1:y2, x1:x2]
    ch, cs, cv = crop_hsv[:, :, 0], crop_hsv[:, :, 1], crop_hsv[:, :, 2]
    crop_red = (((ch < 14) | (ch > 165)) & (cs > 70))
    crop_dark = (cv < 92) & (cs > 25)
    crop_highlight = (cs < 80) & (cv > 125)
    alpha = np.zeros(crop.shape[:2], dtype=np.uint8)
    alpha[crop_highlight | (crop_seed > 0)] = 178
    alpha[crop_red | crop_dark] = 255
    alpha = cv2.dilate(alpha, np.ones((3, 3), np.uint8), iterations=1)
    alpha = cv2.GaussianBlur(alpha, (5, 5), 0)
    keep = np.zeros_like(alpha)
    num, labels, stats, _ = cv2.connectedComponentsWithStats((alpha > 28).astype(np.uint8), connectivity=8)
    alpha_area = alpha.shape[0] * alpha.shape[1]
    components = []
    for idx in range(1, num):
        x, y, w, h, area = stats[idx]
        if area < max(35, alpha_area * 0.002):
            continue
        components.append((idx, area))
    for idx, _ in sorted(components, key=lambda item: item[1], reverse=True)[:2]:
        keep[labels == idx] = 255
    if components:
        alpha = cv2.bitwise_and(alpha, keep)
    # Treat green spill in glass as transparency, not white material.
    green_tint = (ch > 30) & (ch < 100) & (cs > 22)
    alpha[green_tint & (alpha > 0) & ~(crop_red | crop_dark)] = np.minimum(alpha[green_tint & (alpha > 0) & ~(crop_red | crop_dark)], 82)
    return crop, alpha, (int(x1), int(y1), int(x2), int(y2))


def green_screen_object_cutout(image: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray] | None:
    result = green_screen_object_cutout_with_bbox(image, rng)
    if not result:
        return None
    return result[0], result[1]


POSE_COLLECTION_GRID_POSITIONS = [
    "top-left",
    "top-center",
    "top-right",
    "middle-left",
    "center",
    "middle-right",
    "bottom-left",
    "bottom-center",
    "bottom-right",
]
UPRIGHT_TOP_VIEW_SOURCE_POSITIONS = ("center", "bottom-center")


def pose_collection_regions(image: np.ndarray, padded: bool = True) -> list[tuple[int, int, int, int]]:
    h, w = image.shape[:2]
    regions = []
    pad_x = int(round(w * 0.075)) if padded else 0
    pad_y = int(round(h * 0.075)) if padded else 0
    for row in range(3):
        for col in range(3):
            x1 = max(0, int(round(col * w / 3)) - pad_x)
            y1 = max(0, int(round(row * h / 3)) - pad_y)
            x2 = min(w, int(round((col + 1) * w / 3)) + pad_x)
            y2 = min(h, int(round((row + 1) * h / 3)) + pad_y)
            regions.append((x1, y1, x2, y2))
    return regions


def grid_position_for_center(center: tuple[int, int], roi: tuple[int, int, int, int] = BACKGROUND_ROI_PX) -> str:
    x1, y1, x2, y2 = roi
    x, y = center
    col = int(np.clip(np.floor(((x - x1) / max(1, x2 - x1)) * 3), 0, 2))
    row = int(np.clip(np.floor(((y - y1) / max(1, y2 - y1)) * 3), 0, 2))
    return POSE_COLLECTION_GRID_POSITIONS[row * 3 + col]


def grid_row_col(position: str | None) -> tuple[int, int] | None:
    if position not in POSE_COLLECTION_GRID_POSITIONS:
        return None
    idx = POSE_COLLECTION_GRID_POSITIONS.index(position)
    return idx // 3, idx % 3


def grid_position_from_row_col(row: int, col: int) -> str:
    row = int(np.clip(row, 0, 2))
    col = int(np.clip(col, 0, 2))
    return POSE_COLLECTION_GRID_POSITIONS[row * 3 + col]


def normalize_cardinal_rotation_degrees(angle: float) -> int:
    return int(round(float(angle) / 90.0) * 90) % 360


def source_position_for_rotated_target(target_position: str | None, rotation_degrees: float) -> str | None:
    """Pick the source grid cell that rotates into the requested target cell."""
    row_col = grid_row_col(target_position)
    if row_col is None:
        return target_position
    row, col = row_col
    x = col - 1
    y = row - 1
    rotation = normalize_cardinal_rotation_degrees(rotation_degrees)
    if rotation == 0:
        sx, sy = x, y
    elif rotation == 90:
        sx, sy = -y, x
    elif rotation == 180:
        sx, sy = -x, -y
    else:
        sx, sy = y, -x
    return grid_position_from_row_col(sy + 1, sx + 1)


def source_position_for_render_policy(
    target_position: str | None,
    rotation_degrees: float,
    pose_family: str | None,
    rng: np.random.Generator,
) -> str | None:
    if pose_family_is_top_view(pose_family or ""):
        return UPRIGHT_TOP_VIEW_SOURCE_POSITIONS[int(rng.integers(0, len(UPRIGHT_TOP_VIEW_SOURCE_POSITIONS)))]
    return source_position_for_rotated_target(target_position, rotation_degrees)


def object_render_pose_policy(pose_family: str | None, rng: np.random.Generator) -> dict[str, Any]:
    rotation = float(rng.uniform(-180.0, 180.0))
    if pose_family_is_top_view(pose_family or ""):
        return {
            "render_pose_policy": "upright_random_planar_rotation",
            "perspective_rotation_degrees": rotation,
            "placement_angle_degrees": rotation,
            "desired_lie_direction": None,
            "desired_facing_direction": f"upright_top_down_{rotation:.1f}deg",
            "source_selection_rule": "upright_center_or_bottom_center_random_rotation",
        }
    normalized = normalize_cardinal_rotation_degrees(rotation)
    lie_direction = "horizontal" if normalized in {90, 270} else "vertical"
    return {
        "render_pose_policy": "lying_random_planar_rotation",
        "perspective_rotation_degrees": rotation,
        "placement_angle_degrees": rotation,
        "desired_lie_direction": lie_direction,
        "desired_facing_direction": f"lying_{lie_direction}_{rotation:.1f}deg",
        "source_selection_rule": "inverse_grid_position_for_random_planar_rotation",
    }


def pose_selection_reason(target_position: str | None, source_position: str | None, rotation_degrees: float) -> str:
    rotation = normalize_cardinal_rotation_degrees(rotation_degrees)
    if not target_position or not source_position:
        return "position_unavailable"
    if rotation == 0 and source_position in UPRIGHT_TOP_VIEW_SOURCE_POSITIONS:
        return "upright_restricted_center_or_bottom_center"
    if rotation == 0:
        return "same_position_0" if source_position == target_position else "unrotated_position_remap"
    if rotation == 180:
        return "opposite_position_180" if source_position != target_position else "center_180_no_opposite"
    return f"inverse_position_{rotation}"


def object_pose_render_size_hint(item: dict[str, Any], pose_family: str | None) -> tuple[int, int]:
    canonical = canonical_pose_family_name(pose_family)
    for asset in clean_sprite_assets(item):
        if canonical and canonical_pose_family_name(asset.get("source_pose_family") or asset.get("pose_family")) != canonical:
            continue
        hint = asset.get("render_size_hint_px") or asset.get("render_footprint_px")
        if isinstance(hint, list) and len(hint) >= 2:
            try:
                return max(16, int(hint[0])), max(16, int(hint[1]))
            except (TypeError, ValueError):
                continue
    metadata = pose_render_footprint_metadata(str(pose_family or ""), [1, 1], item.get("physical_size"))
    return int(metadata["render_footprint_px"][0]), int(metadata["render_footprint_px"][1])


def source_object_major_axis_px(asset: dict[str, Any]) -> int | None:
    size = asset.get("source_object_size_px")
    if not isinstance(size, list) or len(size) < 2:
        return None
    try:
        return max(int(size[0]), int(size[1]))
    except (TypeError, ValueError):
        return None


def filter_complete_pose_candidates(candidates: list[dict[str, Any]], pose_family: str | None) -> list[dict[str, Any]]:
    if str(pose_family or "").lower() not in {"lying", "flat", "side", "side-facing"}:
        return candidates
    lengths = [value for value in (source_object_major_axis_px(asset) for asset in candidates) if value]
    if len(lengths) < 4:
        return candidates
    median_length = float(np.median(lengths))
    min_length = median_length * 0.85
    filtered = [asset for asset in candidates if (source_object_major_axis_px(asset) or median_length) >= min_length]
    return filtered or candidates


def sprite_pose_family(asset: dict[str, Any]) -> str:
    return str(asset.get("source_pose_family") or asset.get("pose_family") or "")


def choose_object_pose_family(sprites: list[dict[str, Any]], rng: np.random.Generator) -> str | None:
    families = sorted({sprite_pose_family(asset) for asset in sprites if sprite_pose_family(asset)})
    if not families:
        return None
    return families[int(rng.integers(0, len(families)))]


def load_object_preview_sprite(
    item: dict[str, Any],
    rng: np.random.Generator,
    target_position: str | None = None,
    pose_family: str | None = None,
    source_position: str | None = None,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]] | None:
    sprites = clean_sprite_assets(item)
    if not sprites:
        preprocess_object_clean_sprites(item, allow_ai_cutout=False)
        sprites = clean_sprite_assets(item)
    if sprites:
        candidates = sprites
        if pose_family:
            requested_canonical = canonical_pose_family_name(pose_family)
            family_candidates = [
                asset
                for asset in candidates
                if (
                    sprite_pose_family(asset) == pose_family
                    or (
                        requested_canonical in {"lying", "upright"}
                        and canonical_pose_family_name(sprite_pose_family(asset)) == requested_canonical
                    )
                )
            ]
            if family_candidates:
                candidates = family_candidates
        if pose_family_is_top_view(pose_family or ""):
            upright_candidates = [
                asset
                for asset in candidates
                if (asset.get("source_position") or asset.get("pose_position")) in UPRIGHT_TOP_VIEW_SOURCE_POSITIONS
            ]
            if not upright_candidates:
                return None
            candidates = upright_candidates
        candidates = filter_complete_pose_candidates(candidates, pose_family)
        wanted_position = source_position or target_position
        if wanted_position:
            position_candidates = [
                asset
                for asset in candidates
                if (asset.get("source_position") or asset.get("pose_position")) == wanted_position
            ]
            if (
                source_position
                and not position_candidates
                and not any(asset.get("source_pose_collection_job_id") == "legacy_clean_sprite" for asset in candidates)
            ):
                return None
            if position_candidates:
                candidates = position_candidates
        elif target_position:
            position_candidates = [asset for asset in candidates if asset.get("pose_position") == target_position]
            if position_candidates:
                candidates = position_candidates
        if not candidates:
            candidates = sprites
        asset = candidates[int(rng.integers(0, len(candidates)))]
        sprite = load_clean_sprite(Path(str(asset.get("path", ""))))
        if sprite:
            meta = dict(asset)
            all_sprites = clean_sprite_assets(item)
            meta["sprite_index"] = next(
                (
                    idx + 1
                    for idx, candidate in enumerate(all_sprites)
                    if str(candidate.get("path", "")) == str(asset.get("path", ""))
                ),
                None,
            )
            meta["sprite_path"] = str(asset.get("path", ""))
            meta["clean_sprite_preprocessed_at"] = item.get("clean_sprite_preprocessed_at")
            meta["clean_sprite_version"] = accessory_sprite_version(item)
            return sprite[0], sprite[1], meta
    return None


def trim_masked_asset(asset: np.ndarray, mask: np.ndarray, pad: int = 4) -> tuple[np.ndarray, np.ndarray]:
    ys, xs = np.where(mask > 8)
    if len(xs) == 0 or len(ys) == 0:
        return asset, mask
    x1, x2 = max(0, int(xs.min()) - pad), min(mask.shape[1], int(xs.max()) + pad + 1)
    y1, y2 = max(0, int(ys.min()) - pad), min(mask.shape[0], int(ys.max()) + pad + 1)
    return asset[y1:y2, x1:x2].copy(), mask[y1:y2, x1:x2].copy()


def physical_mask_for_rect_asset(asset: np.ndarray) -> np.ndarray:
    return np.full(asset.shape[:2], 255, dtype=np.uint8)


def trim_rect_asset(asset: np.ndarray, pad: int = 0) -> np.ndarray:
    gray = cv2.cvtColor(asset, cv2.COLOR_BGR2GRAY)
    border = np.concatenate([gray[:5, :].reshape(-1), gray[-5:, :].reshape(-1), gray[:, :5].reshape(-1), gray[:, -5:].reshape(-1)])
    bg = float(np.median(border))
    diff = np.abs(gray.astype(np.float32) - bg)
    mask = (diff > 8).astype(np.uint8) * 255
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if num <= 1:
        return asset
    areas = stats[1:, cv2.CC_STAT_AREA]
    idx = int(np.argmax(areas)) + 1
    x, y, w, h, _ = stats[idx]
    if w * h < asset.shape[0] * asset.shape[1] * 0.2:
        return asset
    x1, y1 = max(0, x - pad), max(0, y - pad)
    x2, y2 = min(asset.shape[1], x + w + pad), min(asset.shape[0], y + h + pad)
    return asset[y1:y2, x1:x2].copy()


def paste_masked_asset(
    canvas: np.ndarray,
    asset: np.ndarray,
    mask: np.ndarray,
    center: tuple[int, int],
    target_size: tuple[int, int],
    angle: float,
    trim_before_paste: bool = True,
    return_visible_mask: bool = False,
) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
    if trim_before_paste:
        asset, mask = trim_masked_asset(asset, mask)
    visible_mask = np.zeros(canvas.shape[:2], dtype=np.uint8) if return_visible_mask else None
    target_w, target_h = target_size
    h, w = asset.shape[:2]
    scale = min(target_w / max(w, 1), target_h / max(h, 1))
    resized = cv2.resize(asset, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    resized_mask = cv2.resize(mask, (resized.shape[1], resized.shape[0]), interpolation=cv2.INTER_LINEAR)
    rh, rw = resized.shape[:2]
    diagonal = int(np.ceil(np.sqrt(rw * rw + rh * rh))) + 8
    patch = np.zeros((diagonal, diagonal, 3), dtype=np.uint8)
    patch_mask = np.zeros((diagonal, diagonal), dtype=np.uint8)
    x0 = (diagonal - rw) // 2
    y0 = (diagonal - rh) // 2
    patch[y0 : y0 + rh, x0 : x0 + rw] = resized
    patch_mask[y0 : y0 + rh, x0 : x0 + rw] = resized_mask
    matrix = cv2.getRotationMatrix2D((diagonal / 2, diagonal / 2), angle, 1.0)
    rotated = cv2.warpAffine(patch, matrix, (diagonal, diagonal), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))
    rotated_mask = cv2.warpAffine(patch_mask, matrix, (diagonal, diagonal), flags=cv2.INTER_LINEAR, borderValue=0)
    cx, cy = center
    dest_x = cx - diagonal // 2
    dest_y = cy - diagonal // 2
    x1, y1 = max(0, dest_x), max(0, dest_y)
    x2, y2 = min(canvas.shape[1], dest_x + diagonal), min(canvas.shape[0], dest_y + diagonal)
    sx1, sy1 = x1 - dest_x, y1 - dest_y
    sx2, sy2 = sx1 + (x2 - x1), sy1 + (y2 - y1)
    if x2 <= x1 or y2 <= y1:
        return (canvas, visible_mask) if return_visible_mask else canvas
    roi = canvas[y1:y2, x1:x2]
    pasted_mask = rotated_mask[sy1:sy2, sx1:sx2]
    alpha = (pasted_mask.astype(float) / 255.0)[..., None]
    roi[:] = (rotated[sy1:sy2, sx1:sx2] * alpha + roi * (1 - alpha)).astype(np.uint8)
    if visible_mask is not None:
        visible_mask[y1:y2, x1:x2] = pasted_mask
        return canvas, visible_mask
    return canvas


def visible_mask_size_px(mask: np.ndarray) -> list[int]:
    bbox = alpha_bbox(mask)
    return [max(0, int(bbox[2] - bbox[0])), max(0, int(bbox[3] - bbox[1]))]


def resize_masked_asset_to_visible_footprint(
    asset: np.ndarray,
    mask: np.ndarray,
    target_size: tuple[int, int],
    preserve_aspect_ratio: bool = False,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    target_w, target_h = max(1, int(target_size[0])), max(1, int(target_size[1]))
    source_visible = visible_mask_size_px(mask)
    if asset.size == 0 or mask.size == 0:
        return asset, mask, {
            "render_box_px": [target_w, target_h],
            "render_visible_footprint_px": [0, 0],
            "render_resize_policy": (
                "alpha_visible_bbox_fit_physical_footprint_preserve_aspect"
                if preserve_aspect_ratio
                else "alpha_visible_bbox_exact_physical_footprint"
            ),
            "source_visible_footprint_px": source_visible,
            "non_uniform_scaling_applied": False,
            "render_scale_x": None,
            "render_scale_y": None,
        }
    source_w = max(1, int(asset.shape[1]))
    source_h = max(1, int(asset.shape[0]))
    visible_w, visible_h = max(1, int(source_visible[0])), max(1, int(source_visible[1]))
    if preserve_aspect_ratio:
        scale = min(target_w / visible_w, target_h / visible_h)
        resized_w = max(1, int(round(source_w * scale)))
        resized_h = max(1, int(round(source_h * scale)))
        render_policy = "alpha_visible_bbox_fit_physical_footprint_preserve_aspect"
        scale_x = scale
        scale_y = scale
    else:
        scale_x = target_w / visible_w
        scale_y = target_h / visible_h
        resized_w = max(1, int(round(source_w * scale_x)))
        resized_h = max(1, int(round(source_h * scale_y)))
        render_policy = "alpha_visible_bbox_exact_physical_footprint"
    resized = cv2.resize(asset, (resized_w, resized_h), interpolation=cv2.INTER_AREA if max(asset.shape[:2]) > max(resized_h, resized_w) else cv2.INTER_CUBIC)
    resized_mask = cv2.resize(mask, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)
    return resized, resized_mask, {
        "render_box_px": [target_w, target_h],
        "render_visible_footprint_px": visible_mask_size_px(resized_mask),
        "render_resize_policy": render_policy,
        "source_visible_footprint_px": source_visible,
        "non_uniform_scaling_applied": bool(abs(scale_x - scale_y) > 0.0005),
        "render_scale_x": round(float(scale_x), 6),
        "render_scale_y": round(float(scale_y), 6),
    }


def paste_physical_object_asset(
    canvas: np.ndarray,
    asset: np.ndarray,
    mask: np.ndarray,
    center: tuple[int, int],
    target_long_side_px: int,
    target_short_side_px: int,
    angle: float,
    preserve_aspect_ratio: bool = False,
) -> dict[str, Any]:
    target_size = (max(1, int(target_long_side_px)), max(1, int(target_short_side_px)))
    resized, resized_mask, render_meta = resize_masked_asset_to_visible_footprint(asset, mask, target_size, preserve_aspect_ratio)
    _, visible_mask = paste_masked_asset(
        canvas,
        resized,
        resized_mask,
        center,
        target_size,
        angle,
        trim_before_paste=False,
        return_visible_mask=True,
    )
    render_meta["_visible_mask_canvas"] = visible_mask
    return render_meta


def paste_rectified_document_asset(
    canvas: np.ndarray,
    asset: np.ndarray,
    center: tuple[int, int],
    target_size: tuple[int, int],
    angle: float,
) -> dict[str, Any]:
    target_w, target_h = max(1, int(target_size[0])), max(1, int(target_size[1]))
    source_h, source_w = asset.shape[:2]
    resized = cv2.resize(
        asset,
        (target_w, target_h),
        interpolation=cv2.INTER_AREA if max(source_h, source_w) > max(target_h, target_w) else cv2.INTER_CUBIC,
    )
    diagonal = int(np.ceil(np.sqrt(target_w * target_w + target_h * target_h))) + 8
    patch = np.zeros((diagonal, diagonal, 3), dtype=np.uint8)
    patch_mask = np.zeros((diagonal, diagonal), dtype=np.uint8)
    x0 = (diagonal - target_w) // 2
    y0 = (diagonal - target_h) // 2
    patch[y0 : y0 + target_h, x0 : x0 + target_w] = resized
    patch_mask[y0 : y0 + target_h, x0 : x0 + target_w] = 255
    matrix = cv2.getRotationMatrix2D((diagonal / 2, diagonal / 2), angle, 1.0)
    rotated = cv2.warpAffine(patch, matrix, (diagonal, diagonal), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))
    rotated_mask = cv2.warpAffine(patch_mask, matrix, (diagonal, diagonal), flags=cv2.INTER_LINEAR, borderValue=0)
    cx, cy = center
    dest_x = cx - diagonal // 2
    dest_y = cy - diagonal // 2
    x1, y1 = max(0, dest_x), max(0, dest_y)
    x2, y2 = min(canvas.shape[1], dest_x + diagonal), min(canvas.shape[0], dest_y + diagonal)
    sx1, sy1 = x1 - dest_x, y1 - dest_y
    sx2, sy2 = sx1 + (x2 - x1), sy1 + (y2 - y1)
    if x2 > x1 and y2 > y1:
        roi = canvas[y1:y2, x1:x2]
        pasted_mask = rotated_mask[sy1:sy2, sx1:sx2]
        alpha = (pasted_mask.astype(float) / 255.0)[..., None]
        roi[:] = (rotated[sy1:sy2, sx1:sx2] * alpha + roi * (1 - alpha)).astype(np.uint8)
        visible_mask = np.zeros(canvas.shape[:2], dtype=np.uint8)
        visible_mask[y1:y2, x1:x2] = pasted_mask
    else:
        visible_mask = np.zeros(canvas.shape[:2], dtype=np.uint8)
    return {
        "document_mask_crop_bypassed": True,
        "object_alpha_pipeline_bypassed": True,
        "document_full_asset_pasted": True,
        "document_asset_policy": "full_rectified_asset_direct_physical_size",
        "document_physical_scale_basis": "paper_width_height_mm_to_background_px",
        "render_box_px": [target_w, target_h],
        "render_visible_footprint_px": [target_w, target_h],
        "render_resize_policy": "document_rectified_full_canvas_exact_physical_size",
        "source_visible_footprint_px": [int(source_w), int(source_h)],
        "non_uniform_scaling_applied": bool(abs((target_w / max(1, source_w)) - (target_h / max(1, source_h))) > 0.0005),
        "render_scale_x": round(float(target_w / max(1, source_w)), 6),
        "render_scale_y": round(float(target_h / max(1, source_h)), 6),
        "_visible_mask_canvas": visible_mask,
    }


def paste_rotated_asset(canvas: np.ndarray, asset: np.ndarray, center: tuple[int, int], target_size: tuple[int, int], angle: float) -> np.ndarray:
    asset = trim_rect_asset(asset)
    return paste_masked_asset(canvas, asset, physical_mask_for_rect_asset(asset), center, target_size, angle)


def normalize_accessory_assets(item: dict[str, Any]) -> dict[str, Any]:
    normalized_dir = NORMALIZED_DIR / accessory_uid(item)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    source_files = [Path(path) for path in item.get("source_files", [])]
    image_sources = [path for path in source_files if path.suffix.lower() in IMAGE_REFERENCE_SUFFIXES]
    material_type = accessory_material_type(item)
    if material_type == "text":
        assets = []
        physical_size = item.get("physical_size") if isinstance(item.get("physical_size"), dict) else {}
        for src in image_sources[:4]:
            normalized = normalize_text_image(src, normalized_dir, physical_size)
            if normalized:
                assets.append(normalized)
        return {
            "status": "normalized_text_ready" if assets else "needs_crop",
            "normalized_assets": assets,
            "preprocess": "用户裁剪包含完整文字的文档图像，系统进行透视校正并生成规整说明书图。",
        }
    prompt = (
        f"Image-to-image asset expansion for '{item.get('name', 'accessory')}'. "
        "Generate clean isolated product views with consistent material, multiple angles, "
        "standing/lying poses when applicable, calibrated size variants, object-only framing, "
        "no background/backing/surface/shadows, and transparent PNG alpha when supported."
    )
    return {
        "status": "image_tool_plan_ready",
        "normalized_assets": [
            {
                "kind": "object_view_plan",
                "source_files": [str(path) for path in image_sources],
                "image_tool_prompt": prompt,
                "view_plan": build_object_view_plan(str(item.get("name", "accessory"))),
            }
        ],
        "preprocess": "系统记录 Image tool 扩展计划，用于生成多视角、多尺寸辅助素材。",
    }


def frame_detail_score(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    hist = cv2.calcHist([gray], [0], None, [64], [0, 256]).reshape(-1)
    hist = hist / max(float(hist.sum()), 1.0)
    entropy = float(-(hist * np.log2(hist + 1e-9)).sum())
    mean = float(gray.mean())
    exposure_penalty = abs(mean - 135.0) * 2.0
    return blur_score + entropy * 80.0 - exposure_penalty


def frame_histogram(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256]).reshape(-1)
    hist = hist / max(float(hist.sum()), 1.0)
    return hist.astype(np.float32)


def extract_video_reference_frames(video_path: Path, output_dir: Path, max_frames: int = MAX_VIDEO_REFERENCE_FRAMES) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = frame_count / fps if frame_count > 0 and fps > 0 else 0.0
        target_samples = 72
        stride = max(1, frame_count // target_samples) if frame_count > 0 else max(1, int(fps // 2) or 1)
        candidates: list[dict[str, Any]] = []
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % stride == 0:
                score = frame_detail_score(frame)
                hist = frame_histogram(frame)
                candidates.append(
                    {
                        "frame_index": idx,
                        "time_seconds": idx / fps if fps > 0 else 0.0,
                        "score": score,
                        "hist": hist,
                        "frame": frame.copy(),
                    }
                )
            idx += 1
            if frame_count <= 0 and idx > 1800:
                break
        if not candidates:
            return []

        candidates.sort(key=lambda item: item["score"], reverse=True)
        pool = candidates[: min(len(candidates), 36)]
        selected: list[dict[str, Any]] = []
        min_time_gap = max(duration / (max_frames * 2), 0.35) if duration else 0.35
        while pool and len(selected) < max_frames:
            best_item = None
            best_value = -1e18
            for item in pool:
                if not selected:
                    value = float(item["score"])
                else:
                    time_gap = min(abs(float(item["time_seconds"]) - float(other["time_seconds"])) for other in selected)
                    if time_gap < min_time_gap and len(pool) > max_frames:
                        continue
                    hist_gap = min(float(cv2.compareHist(item["hist"], other["hist"], cv2.HISTCMP_BHATTACHARYYA)) for other in selected)
                    value = float(item["score"]) + hist_gap * 550.0 + time_gap * 12.0
                if value > best_value:
                    best_item = item
                    best_value = value
            if best_item is None:
                best_item = pool[0]
            selected.append(best_item)
            pool = [item for item in pool if item is not best_item]

        selected.sort(key=lambda item: int(item["frame_index"]))
        extracted = []
        for out_idx, item in enumerate(selected, start=1):
            out_path = output_dir / f"{video_path.stem}_reference_frame_{out_idx:02d}.jpg"
            cv2.imwrite(str(out_path), item["frame"], [int(cv2.IMWRITE_JPEG_QUALITY), 94])
            extracted.append(
                {
                    "path": str(out_path),
                    "source_video": str(video_path),
                    "frame_index": int(item["frame_index"]),
                    "time_seconds": round(float(item["time_seconds"]), 3),
                    "detail_score": round(float(item["score"]), 3),
                }
            )
        return extracted
    finally:
        cap.release()


def expand_accessory_reference_sources(candidate_id: str, source_files: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    expanded = list(source_files)
    extracted_frames: list[dict[str, Any]] = []
    frame_dir = UPLOAD_DIR / "accessory_candidates" / candidate_id / "video_reference_frames"
    for path_str in source_files:
        path = Path(path_str)
        if path.suffix.lower() not in VIDEO_REFERENCE_SUFFIXES:
            continue
        frames = extract_video_reference_frames(path, frame_dir)
        extracted_frames.extend(frames)
        expanded.extend(frame["path"] for frame in frames)
    return expanded, extracted_frames


def write_thumbnail(image: np.ndarray, out_path: Path, angle: float = 0.0, size: int = 360) -> dict[str, Any]:
    h, w = image.shape[:2]
    scale = min(size / max(h, w), 1.0)
    resized = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    rh, rw = resized.shape[:2]
    canvas = np.full((size, size, 3), (238, 240, 242), dtype=np.uint8)
    patch = np.full((size, size, 3), (238, 240, 242), dtype=np.uint8)
    x = (size - rw) // 2
    y = (size - rh) // 2
    patch[y : y + rh, x : x + rw] = resized
    matrix = cv2.getRotationMatrix2D((size / 2, size / 2), angle, 1.0)
    rotated = cv2.warpAffine(patch, matrix, (size, size), flags=cv2.INTER_LINEAR, borderValue=(238, 240, 242))
    canvas[:] = rotated
    cv2.imwrite(str(out_path), canvas)
    return {"url": public_output_url(out_path), "angle": angle, "width": size, "height": size}


def pose_collection_dimension_text(item: dict[str, Any]) -> str:
    physical = item.get("physical_size") or {}
    length = physical.get("length_mm")
    width = physical.get("width_mm")
    height = physical.get("height_mm")
    if length and width and height:
        return (
            f"Use these physical dimensions to infer the 3D form and perspective: "
            f"length {length} mm, width {width} mm, height {height} mm. "
        )
    return "Infer the object's approximate 3D form and proportions from the reference image. "


def tabletop_scene_text(surface_mode: str = "white") -> str:
    if surface_mode == "reference":
        return (
            "Render the scene as one overhead photograph of nine real objects physically placed on the same tabletop/background "
            "material visible in the reference images. Preserve that reference table material, color, lighting, texture, and "
            "surface context, for example a green tabletop if the reference image uses a green tabletop. "
        )
    if surface_mode == "pure_white":
        return (
            "Render the scene as one overhead photograph of nine real objects physically placed on a 100% pure white tabletop. "
            "The tabletop must be flat, uniform white, textureless, shadow-free, and free of stains, gradients, color casts, or "
            "material patterns. "
        )
    return "Render the scene as one overhead photograph of nine real objects physically placed on a clean white tabletop. "


def pose_collection_camera_grid_text(item: dict[str, Any], surface_mode: str = "white") -> str:
    physical = item.get("physical_size") or {}
    length = float(physical.get("length_mm") or 170.0)
    grid_pitch = max(40.0, length)
    camera_height = max(300.0, length * 5.0)
    axis_tilt = math.degrees(math.atan(grid_pitch / camera_height))
    corner_tilt = math.degrees(math.atan((grid_pitch * math.sqrt(2)) / camera_height))
    return (
        "Use this fixed camera geometry and write it visually into the 3x3 grid. "
        f"{tabletop_scene_text(surface_mode)}"
        "The nine objects form a regular 3x3 square grid with equal X spacing and equal Y spacing, like a neat tic-tac-toe/田字 layout. "
        f"Assume the real inspection camera is mounted {camera_height:.0f} mm above the conveyor/table plane. "
        f"The nine object positions are spaced {grid_pitch:.0f} mm apart in X/Y around the center. "
        "Use one physically consistent object scale across all nine positions; apparent size changes may come only from "
        "the specified camera perspective and must not be arbitrary resizing. "
        "The camera is above the 3x3 arrangement and looks downward. Use exactly two view-axis angles, not three object "
        "rotation angles: azimuth_xy is the direction angle in the horizontal X/Y plane, and tilt_from_z is the small "
        "angle between the camera ray and the vertical Z axis. These are camera/view-axis parameters, not bottle rotation. "
        "The bottle yaw/object orientation is fixed and identical in every cell; do not rotate the bottles themselves. "
        "Use this mandatory 3D view table: "
        f"top-left: azimuth_xy=135 deg, tilt_from_z={corner_tilt:.1f} deg; "
        f"top-center: azimuth_xy=90 deg, tilt_from_z={axis_tilt:.1f} deg; "
        f"top-right: azimuth_xy=45 deg, tilt_from_z={corner_tilt:.1f} deg; "
        f"middle-left: azimuth_xy=180 deg, tilt_from_z={axis_tilt:.1f} deg; "
        "center: azimuth_xy=none, tilt_from_z=0.0 deg, perfectly vertical optical-axis view; "
        f"middle-right: azimuth_xy=0 deg, tilt_from_z={axis_tilt:.1f} deg; "
        f"bottom-left: azimuth_xy=-135 deg, tilt_from_z={corner_tilt:.1f} deg; "
        f"bottom-center: azimuth_xy=-90 deg, tilt_from_z={axis_tilt:.1f} deg; "
        f"bottom-right: azimuth_xy=-45 deg, tilt_from_z={corner_tilt:.1f} deg. "
        "Because the camera is high, all non-center tilt_from_z values are intentionally small. These angle values are "
        "mandatory; do not invent a different camera layout and do not rotate the bottles."
    )


def pose_collection_position_specs(item: dict[str, Any]) -> dict[str, str]:
    physical = item.get("physical_size") or {}
    length = float(physical.get("length_mm") or 170.0)
    grid_pitch = max(40.0, length)
    camera_height = max(300.0, length * 5.0)
    axis_tilt = math.degrees(math.atan(grid_pitch / camera_height))
    corner_tilt = math.degrees(math.atan((grid_pitch * math.sqrt(2)) / camera_height))
    return {
        "top-left": f"top-left: azimuth_xy=135 deg, tilt_from_z={corner_tilt:.1f} deg, camera shifted top/back + left, looking diagonally inward",
        "top-center": f"top-center: azimuth_xy=90 deg, tilt_from_z={axis_tilt:.1f} deg, camera shifted top/back, looking diagonally inward",
        "top-right": f"top-right: azimuth_xy=45 deg, tilt_from_z={corner_tilt:.1f} deg, camera shifted top/back + right, looking diagonally inward",
        "middle-left": f"middle-left: azimuth_xy=180 deg, tilt_from_z={axis_tilt:.1f} deg, camera shifted left, looking diagonally inward",
        "center": "center: azimuth_xy=none, tilt_from_z=0.0 deg, perfectly vertical optical-axis view with no perspective bias",
        "middle-right": f"middle-right: azimuth_xy=0 deg, tilt_from_z={axis_tilt:.1f} deg, camera shifted right, looking diagonally inward",
        "bottom-left": f"bottom-left: azimuth_xy=-135 deg, tilt_from_z={corner_tilt:.1f} deg, camera shifted bottom/front + left, looking diagonally inward",
        "bottom-center": f"bottom-center: azimuth_xy=-90 deg, tilt_from_z={axis_tilt:.1f} deg, camera shifted bottom/front, looking diagonally inward",
        "bottom-right": f"bottom-right: azimuth_xy=-45 deg, tilt_from_z={corner_tilt:.1f} deg, camera shifted bottom/front + right, looking diagonally inward",
    }


def pose_collection_camera_batch_text(item: dict[str, Any], batch_key: str | None, surface_mode: str = "white") -> str:
    if not batch_key:
        return pose_collection_camera_grid_text(item, surface_mode)
    batch = next((entry for entry in POSE_COLLECTION_BATCHES if entry[0] == batch_key), None)
    if not batch:
        return pose_collection_camera_grid_text(item, surface_mode)
    _, batch_label, positions = batch
    physical = item.get("physical_size") or {}
    length = float(physical.get("length_mm") or 170.0)
    grid_pitch = max(40.0, length)
    camera_height = max(300.0, length * 5.0)
    specs = pose_collection_position_specs(item)
    spec_text = "; ".join(specs[position] for position in positions)
    return (
        f"This image is only the {batch_label} batch of the original 3x3 camera grid. "
        "Generate exactly three separated object cutouts, arranged left-to-right in this exact order: "
        f"{', '.join(positions)}. Do not generate the other six positions in this file. "
        f"Assume the real inspection camera is mounted {camera_height:.0f} mm above the conveyor/table plane. "
        f"{tabletop_scene_text(surface_mode)}"
        f"The nine original object positions are spaced {grid_pitch:.0f} mm apart in X/Y around the center; this file "
        "contains only the three listed positions from that grid. Use exactly two view-axis angles, not object rotation "
        "angles. Use one physically consistent object scale across all requested positions; apparent size changes may "
        "come only from the specified camera perspective and must not be arbitrary resizing. "
        "azimuth_xy is the direction angle in the horizontal X/Y plane, and tilt_from_z is the small angle between "
        "the camera ray and the vertical Z axis. These are camera/view-axis parameters, not bottle rotation. The bottle "
        "yaw/object orientation is fixed and identical in all three cutouts; do not rotate the bottles themselves. "
        f"Mandatory camera/view parameters for this file: {spec_text}. "
        "Because the camera is high, all non-center tilt_from_z values are intentionally small. These angle values are "
        "mandatory; do not invent a different camera layout and do not rotate the bottles."
    )


def upright_spatial_relation_text() -> str:
    return (
        "Mandatory upright spatial-occlusion rule: imagine all nine upright bottles are physically standing on one flat "
        "table, evenly spaced, and one real camera is mounted above the center cell looking downward. The center bottle is "
        "directly under the optical axis, so it must show only the top/cap/nozzle and a nearly symmetrical bottle rim; it "
        "must not show a side-biased bottle body. For all surrounding bottles, the visible body must appear on the side "
        "toward the optical-axis center of the 3x3 grid, because the cap/rim occludes the far side. This is a parallax/"
        "occlusion relationship, not bottle rotation. Use this mandatory visual table: top-left bottle = body visible "
        "mostly down-right from the cap; top-center bottle = body visible mostly downward from the cap; top-right bottle = "
        "body visible mostly down-left from the cap; middle-left bottle = body visible mostly right of the cap; center "
        "bottle = top-only cap/nozzle/rim, no side bias; middle-right bottle = body visible mostly left of the cap; "
        "bottom-left bottle = body visible mostly up-right from the cap; bottom-center bottle = body visible mostly "
        "upward/front-side from the cap; bottom-right bottle = body visible mostly up-left from the cap. The black cap and "
        "red nozzle remain centered on the top of each bottle; only the visible bottle body/rim shifts according to the "
        "camera parallax. Do not make all nine bottles share the same side-body direction, and do not rotate the nozzle/"
        "cap mark to fake the effect."
    )


def build_pose_collection_prompt(
    item: dict[str, Any],
    pose_family: str = "combined",
    batch_key: str | None = None,
    surface_mode: str = "reference",
) -> str:
    dimension_text = pose_collection_dimension_text(item)
    camera_grid_text = pose_collection_camera_batch_text(item, batch_key, surface_mode)
    batch = next((entry for entry in POSE_COLLECTION_BATCHES if entry[0] == batch_key), None)
    batch_label = batch[1] if batch else "完整九视角"
    positions = batch[2] if batch else ["top-left", "top-center", "top-right", "middle-left", "center", "middle-right", "bottom-left", "bottom-center", "bottom-right"]
    position_count = len(positions)
    arrangement_text = (
        f"Create exactly {position_count} separated object cutouts in this single image, arranged left-to-right as: "
        f"{', '.join(positions)}. "
        if batch
        else "Create exactly nine separated object cutouts in a 3x3 collection sheet: top-left, top-center, top-right, middle-left, center, middle-right, bottom-left, bottom-center, bottom-right. "
    )
    source_summary = (
        "Use all attached reference images together. Some attached images may be frames automatically extracted from an "
        "uploaded rotation/flip video; treat them as multi-view evidence of the same physical object. Fuse visible details "
        "from every reference image to infer the object's 3D structure: front/back, left/right sides, top/bottom, cap/nozzle "
        "shape, transparent wall thickness, ridges, seams, and material highlights. Do not copy one reference frame blindly; "
        "use the full reference set to reconstruct a consistent object identity. "
    )
    surface_sentence = (
        "All requested objects must be visibly resting on the same reference tabletop/background from the input images, "
        "with equal spacing and a stable regular grid arrangement. The reference tabletop/background is intentional in "
        "this Step 1 image; it will be replaced in Step 2. "
        if surface_mode == "reference"
        else "All requested objects must be visibly resting on the same clean pure-white tabletop, with equal spacing and a stable regular grid arrangement. "
    )
    background_sentence = (
        "Use only the reference tabletop/background material from the input images as the scene background. Do not add unrelated "
        "props, labels, arrows, captions, borders, measurement marks, or decorative graphics. Natural lighting and contact shadows "
        "from the reference tabletop are acceptable in this Step 1 image. "
        if surface_mode == "reference"
        else "Use only a 100% pure white tabletop as the background. Do not add conveyor, floor, props, colored backing, green-screen, "
        "black matte, labels, arrows, captions, borders, measurement marks, decorative graphics, shadows, texture, stains, gradients, "
        "or color casts. "
    )
    if pose_family == "lying":
        title = (
            f"Generate LYING-FLAT Pose Collection batch '{batch_label}'"
            if batch
            else "Generate LYING-FLAT Pose Collection"
        )
        return (
            f"{title} for accessory '{item.get('name', 'accessory')}'. "
            "This prompt is complete and self-contained; do not borrow requirements from another prompt. "
            f"{source_summary}"
            "This is an image-to-image photorealistic product cutout task, not an illustration task. "
            "The attached real reference images are the visual source of truth. "
            "The object must look like the same real "
            "photographed item from the reference, with the same transparent glass/plastic body, cap ridges, red nozzle "
            "geometry, black collar, edge softness, refraction, specular highlights, surface noise, seams, dirt, and "
            f"manufacturing imperfections. {dimension_text}"
            "The pose in this file is LYING-FLAT ONLY: the object is lying flat on its side on an imaginary table. "
            "Do not include any upright, standing, front-elevation, or tall-side-view pose in this image. "
            f"{arrangement_text}"
            f"{surface_sentence}"
            "All requested objects have the same physical pose and the same world yaw/orientation: the cap/nozzle points in "
            "the same world direction in every requested cutout, and the bottle itself is not rotated between cutouts. "
            "The only thing that changes between cutouts is the camera/view-axis direction. "
            f"{camera_grid_text} "
            "If this batch contains the center cutout, render it as a true straight-down overhead view of the lying bottle "
            "with zero perspective bias. For non-center cutouts, render natural top-down camera-offset views: left cells look from "
            "the left, right cells look from the right, top cells look from the top/back, bottom cells look from the "
            "bottom/front, and corner cells combine both offsets. The non-center cutouts must visibly differ through "
            "real perspective distortion, foreshortening, ellipse/rim changes, and side-edge visibility, but they must "
            "not become different object rotations. Do not copy-paste the same sprite across the cutouts. "
            f"{background_sentence}"
            "Because the object is transparent, preserve "
            "clean glass/plastic highlights and contours without green/cyan spill, matte halos, or colored background residue. "
            "Keep each object fully visible, sharply bounded, separated from the others, and easy to segment later."
        )
    elif pose_family == "upright":
        title = (
            f"Generate UPRIGHT/STANDING Pose Collection batch '{batch_label}'"
            if batch
            else "Generate UPRIGHT/STANDING Pose Collection"
        )
        return (
            f"{title} for accessory '{item.get('name', 'accessory')}'. "
            "This prompt is complete and self-contained; do not borrow requirements from another prompt. "
            f"{source_summary}"
            "This is an image-to-image photorealistic product cutout task, not an illustration task. "
            "The attached real reference images are the visual source of truth. "
            "The object must look like the same real "
            "photographed item from the reference, with the same transparent glass/plastic body, cap ridges, red nozzle "
            "geometry, black collar, edge softness, refraction, specular highlights, surface noise, seams, dirt, and "
            f"manufacturing imperfections. {dimension_text}"
            "The pose in this file is UPRIGHT/STANDING ONLY: the object is vertical, standing on its base on an imaginary "
            "table, while the camera is mounted above the 3x3 arrangement and looks downward. Do not include any lying-flat "
            "pose in this image. This must be an overhead/top-down standing view, not a front elevation and not a tall "
            "side view of the whole bottle. The dominant visible feature should be the cap/nozzle/top opening, with only "
            "a partial rim/edge of the bottle body visible around it. "
            f"{arrangement_text}"
            f"{surface_sentence}"
            "All requested objects have the same physical pose and the same world yaw/orientation: the nozzle/cap mark points "
            "in the same world direction in every requested cutout, and the bottle itself is not rotated between cutouts. "
            "The only thing that changes between cutouts is the camera/view-axis direction. "
            f"{camera_grid_text} "
            f"{upright_spatial_relation_text()} "
            "If this batch contains the center cutout, render it as a true straight-down optical-axis view of the upright "
            "bottle: mostly cap/nozzle/top opening, symmetrical rim, no side bias, no front elevation. For non-center cutouts, render "
            "natural overhead camera-offset views: left cells look from the left, right cells look from the right, top "
            "cells look from the top/back, bottom cells look from the bottom/front, and corner cells combine both offsets. "
            "The non-center cutouts must visibly differ through cap ellipse changes, rim perspective, side-edge visibility, "
            "and foreshortening, but they must not become different object rotations. Do not copy-paste the same sprite "
            "across the cutouts. "
            f"{background_sentence}"
            "Because the object is transparent, preserve "
            "clean glass/plastic highlights and contours without green/cyan spill, matte halos, or colored background residue. "
            "Keep each object fully visible, sharply bounded, separated from the others, and easy to segment later."
        )
    else:
        return (
            f"Create one object-only Pose Collection image for the accessory '{item.get('name', 'accessory')}' "
            "using the uploaded reference photo as the visual source of truth. Generate both physical pose families: "
            "lying flat on the side and upright standing on the base. Cover meaningfully different camera positions, "
            "not only planar rotations."
        )


def build_white_table_replacement_prompt(item: dict[str, Any], pose_family: str) -> str:
    pose_text = "UPRIGHT/STANDING" if pose_family == "upright" else "LYING-FLAT"
    return (
        f"Step 2 cleanup for the {pose_text} Pose Collection of accessory '{item.get('name', 'accessory')}'. "
        "Use the attached Step 1 pose-collection image as the main source. Keep every object exactly the same: same nine "
        "object identities, same positions, same 3x3 spacing, same perspective/parallax, same object size, same cap/nozzle "
        "orientation, same transparent material details, same edges, and same visible body/rim geometry. Do not redraw, "
        "rotate, move, resize, replace, simplify, or stylize any object. "
        "Only replace the tabletop/background material. Convert the entire table/background into a 100% pure white surface "
        "with RGB #FFFFFF appearance: no texture, no grain, no green tint, no stains, no gradients, no shadows, no contact "
        "shadows, no reflection, no color spill, and no checkerboard/alpha pattern. The final image should look like the "
        "same overhead photograph after the table material was changed to perfectly clean flat white. "
        "Preserve clean segmentation-friendly object boundaries. Do not add labels, arrows, captions, borders, extra props, "
        "or any unrelated scene elements."
    )


def build_anchor_replacement_pose_prompt(item: dict[str, Any], pose_family: str) -> str:
    if pose_family == "upright":
        return (
            "Priority camera-facing rule: the object's top must face the camera, and the visible top is the part we "
            "should see. "
            "The first attached image is the anchor image. It contains nine metal bars. Replace each metal bar with the "
            "object from the other attached reference image(s). For every replacement, copy the matched bar's center "
            "position, long-axis direction, end-face direction, visible footprint, size, and perspective. The object's "
            "main axis must follow the bar's main axis, and the object's end-facing part must sit where that bar's "
            "square end face appears. "
            "Keep the anchor image's 3x3 layout, spacing, tabletop, background, camera angle, and framing unchanged. "
            "Remove all metal bars from the final image. Do not add anything else."
        )
    return (
        "Priority camera-facing rule: the object's side must face the camera, and the visible side surface is the part "
        "we should see. "
        "The first attached image is the anchor image. It contains nine horizontal metal bars. Replace each metal bar "
        "with the object from the other attached reference image(s). A horizontal metal bar means the replacement object "
        "must also be horizontal. Keep each replacement object's position, size, direction, footprint, and perspective "
        "matched to the metal bar it replaces. "
        "Keep the anchor image's 3x3 layout, spacing, tabletop, background, camera angle, and framing unchanged. "
        "Remove all metal bars from the final image. Do not add anything else."
    )


def create_accessory_candidate(
    name: str,
    material_type: str,
    training_role: str,
    source_files: list[str],
    physical_size: dict[str, Any] | None = None,
    material_alpha_policy: str | None = None,
) -> dict[str, Any]:
    candidate_id = f"cand_{uuid.uuid4().hex[:10]}"
    expanded_source_files, extracted_video_frames = expand_accessory_reference_sources(candidate_id, source_files)
    thumb_dir = OUTPUT_DIR / "accessory_candidates" / candidate_id
    thumb_dir.mkdir(parents=True, exist_ok=True)
    alpha_policy = normalize_object_alpha_material_policy(material_alpha_policy) if material_type == "object" else None
    if material_type == "object" and not alpha_policy:
        raise HTTPException(status_code=400, detail="material_alpha_policy must be transparent or opaque for object accessories")
    item = {
        "id": candidate_id,
        "class_id": -1,
        "name": name,
        "material_type": material_type,
        "training_role": training_role,
        "physical_size": physical_size or physical_size_payload(material_type),
        "status": "candidate_review",
        "source_files": expanded_source_files,
        "original_source_files": source_files,
        "video_reference_frames": extracted_video_frames,
        "created_at": int(time.time()),
    }
    if alpha_policy:
        item["material_alpha_policy"] = alpha_policy
        item["object_alpha_policy_label"] = object_alpha_policy_label(alpha_policy)
    normalized = normalize_accessory_assets(item)
    item.update(normalized)
    thumbnails = []
    image_sources = [Path(path) for path in expanded_source_files if Path(path).suffix.lower() in IMAGE_REFERENCE_SUFFIXES]
    for idx, src in enumerate(image_sources[:8]):
        image = cv2.imread(str(src), cv2.IMREAD_COLOR)
        if image is not None:
            thumbnails.append(write_thumbnail(image, thumb_dir / f"source_{idx + 1:02d}.png", 0))
    if not thumbnails and item.get("normalized_assets"):
        for idx, asset in enumerate(item["normalized_assets"][:6]):
            path = Path(asset.get("path", ""))
            image = cv2.imread(str(path), cv2.IMREAD_COLOR) if path.exists() else None
            if image is not None:
                thumbnails.append(write_thumbnail(image, thumb_dir / f"normalized_{idx + 1:02d}.png", 0))
    item["thumbnails"] = thumbnails[:8]
    item["ai_generation_required"] = material_type == "object" and len(image_sources) >= 1
    item["pose_collection_prompt"] = build_pose_collection_prompt(item) if item["ai_generation_required"] else ""
    if item["ai_generation_required"]:
        item["pose_collection_prompts"] = {
            "upright": build_anchor_replacement_pose_prompt(item, "upright"),
            "lying": build_anchor_replacement_pose_prompt(item, "lying"),
        }
        jobs = []
        for pose_family in ("upright", "lying"):
            label_prefix = "正立" if pose_family == "upright" else "平躺"
            anchor_path = POSE_ANCHOR_IMAGES[pose_family]
            output_name = "pose_collection_endface.png" if pose_family == "upright" else "pose_collection_flat.png"
            final_output_path = OUTPUT_DIR / "accessory_pose_collections" / candidate_id / output_name
            anchor_sha256 = file_sha256(anchor_path)
            jobs.append(
                {
                    "job_id": f"imgjob_{candidate_id}_{pose_family}_anchor_replacement",
                    "candidate_id": candidate_id,
                    "pose_family": pose_family,
                    "generation_step": "anchor_replacement",
                    "label": f"{label_prefix} Pose Collection",
                    "status": "queued_for_codex_image_worker",
                    "mode": "anchor_image_replacement",
                    "anchor_image_path": str(anchor_path),
                    "anchor_image_basename": anchor_path.name,
                    "anchor_image_sha256": anchor_sha256,
                    "anchor_policy_version": ANCHOR_POLICY_VERSION,
                    "anchor_provenance": "sha256",
                    "input_files": [str(anchor_path), *[str(path) for path in image_sources[: max(0, MAX_IMAGE_WORKER_INPUTS - 1)]]],
                    "input_video_files": [str(path) for path in source_files if Path(path).suffix.lower() in VIDEO_REFERENCE_SUFFIXES],
                    "video_reference_frames": extracted_video_frames,
                    "prompt": item["pose_collection_prompts"][pose_family],
                    "output_path": str(final_output_path),
                    "output_url": public_output_url(final_output_path),
                    "progress": 0,
                    "created_at": int(time.time()),
                    "note": "One-step generation: replace the nine square metal bars in the hidden anchor image with the accessory.",
                }
            )
        item["codex_image_jobs"] = jobs
        for job in item["codex_image_jobs"]:
            ensure_image_job_task_id(item, job)
        item["codex_image_job"] = jobs[0]
    save_accessory_candidate(ACCESSORY_CANDIDATES_DIR / f"{candidate_id}.json", item)
    return item


def load_accessory_candidate(candidate_id: str) -> dict[str, Any]:
    path = ACCESSORY_CANDIDATES_DIR / f"{candidate_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Accessory candidate not found")
    with _candidate_store_lock:
        candidate = json.loads(path.read_text(encoding="utf-8"))
        if ensure_candidate_image_job_task_ids(candidate):
            save_accessory_candidate(path, candidate)
        return candidate


def save_accessory_candidate(path: Path, candidate: dict[str, Any]) -> None:
    with _candidate_store_lock:
        write_accessory_candidate_file(path, candidate)


def write_accessory_candidate_file(path: Path, candidate: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def mutate_candidate_image_job(
    path: Path,
    candidate: dict[str, Any],
    job: dict[str, Any],
    updates: dict[str, Any],
    *,
    preprocess_clean_sprites: bool = False,
) -> dict[str, Any]:
    ensure_image_job_task_id(candidate, job)
    job_id = str(job.get("job_id", ""))
    with _candidate_store_lock:
        if not path.exists():
            return job
        try:
            latest = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            latest = candidate
        ensure_candidate_image_job_task_ids(latest)
        latest_job = next(
            (item for item in candidate_image_jobs(latest) if str(item.get("job_id", "")) == job_id),
            dict(job),
        )
        if latest_job.get("status") == "stopped" and updates.get("status") != "stopped":
            return latest_job
        latest_job.update(updates)
        store_candidate_image_job(latest, latest_job)
        if preprocess_clean_sprites:
            preprocess_object_clean_sprites(latest, allow_ai_cutout=True)
        write_accessory_candidate_file(path, latest)
        return latest_job


def candidate_has_active_image_jobs(candidate: dict[str, Any]) -> bool:
    active_statuses = {"queued_for_codex_image_worker", "queued", "running"}
    return any(str(job.get("status", "")) in active_statuses for job in candidate_image_jobs(candidate))


def image_job_prompt(job: dict[str, Any]) -> str:
    output_path = str(job.get("output_path", ""))
    pose_family = str(job.get("pose_family") or "combined")
    generation_step = str(job.get("generation_step") or "")
    input_count = len(job.get("input_files", []) or [])
    video_frame_count = len(job.get("video_reference_frames", []) or [])
    mode_hint = (
        "The first attached image is a hidden backend anchor image. Use it only for layout, pose, scale, camera, and table/background."
        if generation_step == "anchor_replacement"
        else "Follow the core prompt exactly."
    )
    pose_hint = {
        "upright": "Final image must contain exactly nine replacement objects matched to the nine anchor bars.",
        "lying": "Final image must contain exactly nine horizontal replacement objects.",
    }.get(pose_family, "Final image must follow the requested pose collection.")
    return f"""
You are the ImageWorker for the local assembly-line inspection service.

Use all {input_count} attached images. {video_frame_count} may be frames extracted from a user video.
{mode_hint}

Core prompt:
{job.get("prompt", "")}

- Generate a realistic PNG with AI image generation; do not satisfy this with local drawing or script-only image editing.
- {pose_hint}
- Save the final PNG exactly here:
  {output_path}
""".strip()


def image_job_is_active(status: str) -> bool:
    return status in {"queued_for_codex_image_worker", "queued", "running"}


def codex_log_has_generated_image(log_path: Path) -> bool:
    if not log_path.exists():
        return False
    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "/.codex/generated_images/" in text or "/home/dministrator/.codex/generated_images/" in text


def next_queued_image_job() -> tuple[Path, dict[str, Any], dict[str, Any]] | None:
    for path in sorted(ACCESSORY_CANDIDATES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime):
        with _candidate_store_lock:
            try:
                candidate = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            for job in candidate_image_jobs(candidate):
                changed = ensure_image_job_task_id(candidate, job)
                if changed:
                    store_candidate_image_job(candidate, job)
                status = str(job.get("status", ""))
                if status not in {"queued_for_codex_image_worker", "queued"}:
                    if changed:
                        save_accessory_candidate(path, candidate)
                    continue
                depends_on_output = str(job.get("depends_on_output_path") or "")
                if depends_on_output and not Path(depends_on_output).exists():
                    if changed:
                        save_accessory_candidate(path, candidate)
                    continue
                output_path = Path(str(job.get("output_path", "")))
                if output_path.exists():
                    job["status"] = "completed"
                    job["progress"] = 100
                    job["output_url"] = public_output_url(output_path)
                    job["completed_at"] = int(output_path.stat().st_mtime)
                    store_candidate_image_job(candidate, job)
                    preprocess_object_clean_sprites(candidate, allow_ai_cutout=True)
                    save_accessory_candidate(path, candidate)
                    continue
                if changed:
                    save_accessory_candidate(path, candidate)
                return path, candidate, job
    return None


def update_image_worker_status(path: Path, candidate: dict[str, Any], job: dict[str, Any], **fields: Any) -> None:
    updated_job = mutate_candidate_image_job(path, candidate, job, fields)
    job.update(updated_job)


def run_codex_image_job(path: Path, candidate: dict[str, Any], job: dict[str, Any]) -> None:
    job_id = str(job.get("job_id") or f"imgjob_{candidate.get('id')}")
    output_path = Path(str(job.get("output_path", "")))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    IMAGE_WORKER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = IMAGE_WORKER_LOG_DIR / f"{safe_name(job_id)}.log"
    input_files = [str(Path(item)) for item in job.get("input_files", []) if Path(str(item)).exists()]

    if not shutil.which("codex"):
        update_image_worker_status(
            path,
            candidate,
            job,
            status="failed",
            progress=100,
            failed_at=int(time.time()),
            error="codex CLI was not found on PATH.",
            log_path=str(log_path),
        )
        return
    if not input_files:
        update_image_worker_status(
            path,
            candidate,
            job,
            status="failed",
            progress=100,
            failed_at=int(time.time()),
            error="没有找到可用于生成的有效输入图片。",
            log_path=str(log_path),
        )
        return

    command = [
        "codex",
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "-C",
        str(ROOT),
    ]
    for input_file in input_files[:MAX_IMAGE_WORKER_INPUTS]:
        command.extend(["-i", input_file])
    command.append("-")

    update_image_worker_status(
        path,
        candidate,
        job,
        status="running",
        progress=max(int(job.get("progress", 0) or 0), 12),
        started_at=int(time.time()),
        log_path=str(log_path),
        note="系统正在处理这个图像生成任务。",
    )

    process: subprocess.Popen | None = None
    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            log.write(f"$ {' '.join(command)}\n\n")
            log.flush()
            process = subprocess.Popen(
                command,
                cwd=str(ROOT),
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            _image_worker_processes[job_id] = process
            process.communicate(image_job_prompt(job) + "\n", timeout=900)
            return_code = process.returncode
    except subprocess.TimeoutExpired:
        if process:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)
        update_image_worker_status(
            path,
            candidate,
            job,
            status="failed",
            progress=100,
            failed_at=int(time.time()),
            error="图像生成超过 900 秒未完成。",
            log_path=str(log_path),
        )
        return
    except Exception as exc:
        update_image_worker_status(
            path,
            candidate,
            job,
            status="failed",
            progress=100,
            failed_at=int(time.time()),
            error=str(exc),
            log_path=str(log_path),
        )
        return
    finally:
        _image_worker_processes.pop(job_id, None)

    if return_code == 0 and output_path.exists() and not codex_log_has_generated_image(log_path):
        updated_job = mutate_candidate_image_job(
            path,
            candidate,
            job,
            {
                "status": "failed",
                "progress": 100,
                "failed_at": int(time.time()),
                "error": "生成结束但没有可用的图像结果；已拒绝非生成输出。",
                "log_path": str(log_path),
            },
        )
        if updated_job.get("status") == "failed":
            try:
                output_path.unlink()
            except OSError:
                pass
    elif return_code == 0 and output_path.exists():
        mutate_candidate_image_job(
            path,
            candidate,
            job,
            {
                "status": "completed",
                "progress": 100,
                "output_url": public_output_url(output_path),
                "completed_at": int(time.time()),
                "log_path": str(log_path),
                "note": "本地生成任务已完成。",
            },
            preprocess_clean_sprites=True,
        )
    else:
        mutate_candidate_image_job(
            path,
            candidate,
            job,
            {
                "status": "failed",
                "progress": 100,
                "failed_at": int(time.time()),
                "error": f"生成任务退出码 {return_code}，但没有在 {output_path} 找到输出文件。",
                "log_path": str(log_path),
            },
        )


def image_worker_loop() -> None:
    workers: list[threading.Thread] = []
    while True:
        workers = [worker for worker in workers if worker.is_alive()]
        launched = False
        while len(workers) < MAX_PARALLEL_IMAGE_WORKERS:
            queued = next_queued_image_job()
            if not queued:
                break
            path, candidate, job = queued
            update_image_worker_status(
                path,
                candidate,
                job,
                status="running",
                progress=max(int(job.get("progress", 0) or 0), 12),
                started_at=int(time.time()),
                note="系统正在处理这个图像生成任务。",
            )
            worker = threading.Thread(
                target=run_codex_image_job,
                args=(path, candidate, job),
                name=f"codex-image-worker-{job.get('job_id', 'job')}",
                daemon=True,
            )
            worker.start()
            workers.append(worker)
            launched = True
        if not workers and not launched:
            return
        time.sleep(2)


def start_image_worker() -> bool:
    global _image_worker_thread
    with _image_worker_lock:
        if _image_worker_thread and _image_worker_thread.is_alive():
            return False
        _image_worker_thread = threading.Thread(target=image_worker_loop, name="codex-image-worker", daemon=True)
        _image_worker_thread.start()
        return True


def refresh_codex_image_job(job: dict[str, Any]) -> dict[str, Any]:
    copy = dict(job)
    output_path = Path(str(copy.get("output_path", "")))
    status = str(copy.get("status"))
    if status in {"failed", "stopped"}:
        copy["progress"] = int(copy.get("progress", 100))
        copy.setdefault("output_url", public_output_url(output_path) if str(output_path).startswith(str(OUTPUT_DIR)) and output_path.exists() else "")
    elif output_path.exists():
        copy["status"] = "completed"
        copy["progress"] = 100
        copy["output_url"] = public_output_url(output_path)
        copy["completed_at"] = int(output_path.stat().st_mtime)
    elif status == "running":
        started_at = int(copy.get("started_at") or copy.get("created_at") or time.time())
        elapsed = max(0, int(time.time()) - started_at)
        copy["progress"] = min(95, max(int(copy.get("progress", 0)), 18 + elapsed // 8))
        copy.setdefault("output_url", public_output_url(output_path) if str(output_path).startswith(str(OUTPUT_DIR)) else "")
    else:
        copy["progress"] = int(copy.get("progress", 0))
        copy.setdefault("output_url", public_output_url(output_path) if str(output_path).startswith(str(OUTPUT_DIR)) else "")
    return copy


def public_text(value: Any) -> str:
    return (
        str(value)
        .replace("Pose Collection", "多角度视图")
        .replace("ImageWorker", "生成任务")
        .replace("Image worker", "生成任务")
        .replace("Codex CLI", "本地生成")
        .replace("Image tool", "生成工具")
    )


def public_image_job(job: dict[str, Any]) -> dict[str, Any]:
    copy = dict(job)
    note = str(copy.get("note") or "")
    if "processing this image-to-image task" in note:
        copy["note"] = "系统正在处理这个图像生成任务。"
    elif "Generated by local" in note:
        copy["note"] = "本地生成任务已完成。"
    for key in ("label", "note", "error"):
        if copy.get(key):
            copy[key] = public_text(copy[key])
    return copy


def public_accessory_detail_item(item: dict[str, Any]) -> dict[str, Any]:
    copy = serialize_accessory(item)
    for key in list(copy):
        if key.startswith("codex_image") or key.startswith("pose_collection_prompt"):
            copy.pop(key, None)
    if copy.get("preprocess"):
        copy["preprocess"] = public_text(copy["preprocess"])
    return copy


def list_codex_image_jobs() -> list[dict[str, Any]]:
    jobs = []
    for path in sorted(ACCESSORY_CANDIDATES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        with _candidate_store_lock:
            try:
                candidate = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            changed = False
            changed = ensure_candidate_image_job_task_ids(candidate) or changed
            for job in candidate_image_jobs(candidate):
                changed = ensure_image_job_task_id(candidate, job) or changed
                refreshed = refresh_codex_image_job(job)
                refreshed["candidate_name"] = candidate.get("name", "Accessory")
                refreshed["candidate_id"] = candidate.get("id", refreshed.get("candidate_id"))
                refreshed["job_id"] = refreshed.get("job_id") or f"imgjob_{refreshed['candidate_id']}"
                refreshed["task_id"] = refreshed.get("task_id") or deterministic_task_id(candidate, refreshed)
                if refreshed.get("status") != job.get("status") or refreshed.get("completed_at") != job.get("completed_at"):
                    store_candidate_image_job(candidate, refreshed)
                    changed = True
                jobs.append(public_image_job(refreshed))
            if changed:
                save_accessory_candidate(path, candidate)
    return jobs


def training_task_path(task_id: str) -> Path:
    safe_task_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(task_id)).strip("._") or "training_task"
    return TRAINING_TASKS_DIR / f"{safe_task_id}.json"


def save_training_task(task: dict[str, Any]) -> None:
    with _training_task_lock:
        training_task_path(str(task["job_id"])).write_text(json.dumps(task, indent=2), encoding="utf-8")


def load_training_task(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_training_tasks() -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for path in sorted(TRAINING_TASKS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        task = load_training_task(path)
        if not task:
            continue
        tasks.append(public_training_task(task))
    return tasks


def public_training_task(task: dict[str, Any]) -> dict[str, Any]:
    copy = dict(task)
    command = copy.get("training_command") if isinstance(copy.get("training_command"), list) else []
    if not copy.get("epochs"):
        epoch_arg = next((str(item).split("=", 1)[1] for item in command if str(item).startswith("epochs=")), None)
        if epoch_arg:
            try:
                copy["epochs"] = int(epoch_arg)
            except ValueError:
                pass
    if not copy.get("image_size"):
        image_size_arg = next((str(item).split("=", 1)[1] for item in command if str(item).startswith("imgsz=")), None)
        if image_size_arg:
            try:
                copy["image_size"] = int(image_size_arg)
            except ValueError:
                pass
    copy.setdefault("candidate_id", copy.get("job_id"))
    copy.setdefault("candidate_name", copy.get("label") or "训练任务")
    copy.setdefault("task_id", copy.get("job_id"))
    copy.setdefault("progress", 0)
    copy.setdefault("total_epochs", copy.get("epochs") or 0)
    copy.setdefault("current_epoch", copy.get("epochs") if copy.get("status") == "completed" and copy.get("action") == "train_model" else 0)
    copy.setdefault("label", copy.get("label") or "训练任务")
    copy["queue_kind"] = "training"
    return copy


def parse_yolo_epoch_progress(log_path: Path, total_epochs: int) -> tuple[int, int] | None:
    if not log_path.exists():
        return None
    try:
        with log_path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 131072), os.SEEK_SET)
            text = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    matches = re.findall(r"(?:^|\s)(\d{1,4})/(\d{1,4})(?=\s)", text, flags=re.MULTILINE)
    parsed: list[tuple[int, int]] = []
    for current_raw, total_raw in matches:
        current, total = int(current_raw), int(total_raw)
        if current <= 0 or total <= 0:
            continue
        if total_epochs and total != total_epochs:
            continue
        parsed.append((current, total))
    return parsed[-1] if parsed else None


def update_training_task(job_id: str, **updates: Any) -> dict[str, Any]:
    path = training_task_path(job_id)
    with _training_task_lock:
        task = load_training_task(path) or {"job_id": job_id, "created_at": int(time.time())}
        task.update(updates)
        save_training_task(task)
        return task


def update_codex_image_job(job_id: str, action: str) -> dict[str, Any]:
    for path in ACCESSORY_CANDIDATES_DIR.glob("*.json"):
        with _candidate_store_lock:
            try:
                candidate = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            changed = ensure_candidate_image_job_task_ids(candidate)
            jobs = candidate_image_jobs(candidate)
            for item in jobs:
                changed = ensure_image_job_task_id(candidate, item) or changed
            job = next((item for item in jobs if image_job_matches(candidate, item, job_id)), None)
            if changed and job is None:
                save_accessory_candidate(path, candidate)
            if job is None:
                continue
            candidate_job_id = str(job.get("job_id") or f"imgjob_{candidate.get('id')}")
            if action == "stop":
                process = _image_worker_processes.get(candidate_job_id)
                if process and process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                job["job_id"] = candidate_job_id
                job["status"] = "stopped"
                job["progress"] = 100
                job["stopped_at"] = int(time.time())
                job["note"] = "Stopped by user from local service queue."
                store_candidate_image_job(candidate, job)
            elif action == "delete":
                remaining = [item for item in jobs if not image_job_matches(candidate, item, job_id)]
                candidate["codex_image_jobs"] = remaining
                candidate["codex_image_job"] = remaining[0] if remaining else None
            else:
                raise HTTPException(status_code=400, detail="Unknown job action")
            save_accessory_candidate(path, candidate)
            return {"status": action, "job_id": candidate_job_id, "task_id": job.get("task_id")}
    raise HTTPException(status_code=404, detail="Image job not found")


def stop_candidate_image_task(candidate: dict[str, Any]) -> int:
    stopped = 0
    for job in candidate_image_jobs(candidate):
        ensure_image_job_task_id(candidate, job)
        job_id = str(job.get("job_id") or "")
        process = _image_worker_processes.get(job_id)
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                stopped += 1
            except ProcessLookupError:
                pass
        if str(job.get("status", "")) in {"queued_for_codex_image_worker", "queued", "running"}:
            job["status"] = "stopped"
            job["progress"] = 100
            job["stopped_at"] = int(time.time())
            job["note"] = "Stopped as part of deleting the whole image task."
            stopped += 1
    return stopped


def update_codex_image_candidate(candidate_id: str, action: str) -> dict[str, Any]:
    for path in ACCESSORY_CANDIDATES_DIR.glob("*.json"):
        with _candidate_store_lock:
            try:
                candidate = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if str(candidate.get("id", "")) != candidate_id:
                continue
            if action == "stop":
                stopped = stop_candidate_image_task(candidate)
                save_accessory_candidate(path, candidate)
                return {"status": "stopped", "candidate_id": candidate_id, "stopped": stopped}
            if action == "delete":
                stopped = stop_candidate_image_task(candidate)
                try:
                    path.unlink()
                except OSError as exc:
                    raise HTTPException(status_code=500, detail=f"Failed to delete image task: {exc}") from exc
                return {"status": "deleted", "candidate_id": candidate_id, "stopped": stopped}
            raise HTTPException(status_code=400, detail="Unknown candidate action")
    raise HTTPException(status_code=404, detail="Image task not found")


def write_gallery_preview(src: Path, out_path: Path, max_side: int = 1200) -> dict[str, Any] | None:
    raw = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
    if raw is None:
        return None
    if raw.ndim == 3 and raw.shape[2] >= 4:
        alpha = (raw[:, :, 3].astype(np.float32) / 255.0)[..., None]
        bgr = raw[:, :, :3].astype(np.float32)
        background = np.full_like(bgr, 245.0)
        image = (bgr * alpha + background * (1.0 - alpha)).astype(np.uint8)
    else:
        image = raw if raw.ndim == 3 else cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
    if image is None:
        return None
    h, w = image.shape[:2]
    scale = min(max_side / max(h, w), 1.0)
    preview = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), preview)
    return {"url": public_output_url(out_path), "width": int(preview.shape[1]), "height": int(preview.shape[0])}


def accessory_detail_payload(item: dict[str, Any]) -> dict[str, Any]:
    uid = accessory_uid(item)
    gallery_dir = OUTPUT_DIR / "accessory_gallery" / uid
    gallery: list[dict[str, Any]] = []
    material_type = accessory_material_type(item)
    pose_output_paths = []
    clean_sprites = clean_sprite_assets(item)[:18]
    for job in candidate_image_jobs(item):
        output_path = Path(str(job.get("output_path", "")))
        if material_type == "object" and output_path.exists() and str(output_path).startswith(str(OUTPUT_DIR)):
            pose_output_paths.append(output_path)
            gallery.append(
                {
                    "label": public_text(job.get("label") or "多角度视图"),
                    "kind": "pose_collection",
                    "url": public_output_url(output_path),
                    "source_path": str(output_path),
                }
            )
    for idx, asset in enumerate(clean_sprites):
        path = Path(str(asset.get("path", "")))
        preview = write_gallery_preview(path, gallery_dir / f"clean_sprite_{idx + 1:02d}.png")
        if preview:
            gallery.append(
                {
                    "label": f"无背景 sprite {idx + 1}",
                    "kind": "clean_object_sprite",
                    "source_path": str(path),
                    "pose_family": asset.get("pose_family") or asset.get("source_pose_family"),
                    "pose_position": asset.get("pose_position"),
                    "source_position": asset.get("source_position") or asset.get("pose_position"),
                    "source_object_bbox_xyxy": asset.get("source_object_bbox_xyxy"),
                    "source_object_center_xy": asset.get("source_object_center_xy"),
                    "source_object_size_px": asset.get("source_object_size_px"),
                    "task_id": asset.get("task_id"),
                    "source_pose_collection_job_id": asset.get("source_pose_collection_job_id"),
                    "rotation_degrees_applied": asset.get("rotation_degrees_applied"),
                    "rotation_degrees_applied_to_upright": asset.get("rotation_degrees_applied_to_upright"),
                    "original_orientation_angle": asset.get("original_orientation_angle"),
                    "original_orientation_angle_degrees": asset.get("original_orientation_angle_degrees"),
                    "source_restore_rotation_degrees": asset.get("source_restore_rotation_degrees"),
                    "normalized_asset_size_px": asset.get("normalized_asset_size_px"),
                    "normalized_asset_dimensions_px": asset.get("normalized_asset_dimensions_px"),
                    "normalized_bbox_xyxy": asset.get("normalized_bbox_xyxy"),
                    "edge_alpha_max": asset.get("edge_alpha_max"),
                    "edge_alpha_pass": asset.get("edge_alpha_pass"),
                    "pre_rotation_safety_margin_px": asset.get("pre_rotation_safety_margin_px"),
                    "post_rotation_safety_margin_px": asset.get("post_rotation_safety_margin_px"),
                    "physical_size_mm": asset.get("physical_size_mm"),
                    "material_alpha_policy": asset.get("material_alpha_policy"),
                    "object_alpha_material_policy": asset.get("object_alpha_material_policy"),
                    "transparent_alpha_policy": asset.get("transparent_alpha_policy"),
                    "render_scale_basis": asset.get("render_scale_basis"),
                    "render_footprint_mm": asset.get("render_footprint_mm"),
                    "render_footprint_px": asset.get("render_footprint_px"),
                    **preview,
                }
            )
    if gallery and material_type == "object":
        return {"item": public_accessory_detail_item(item), "gallery": gallery}
    source_index = 1
    for path in accessory_image_paths(item):
        if path in pose_output_paths:
            continue
        preview = write_gallery_preview(path, gallery_dir / f"asset_{source_index:02d}.png")
        if preview:
            gallery.append(
                {
                    "label": "文档图片" if material_type == "text" else "素材图片",
                    "kind": "source",
                    "source_path": str(path),
                    **preview,
                }
            )
            break
    return {"item": public_accessory_detail_item(item), "gallery": gallery}


def selected_accessories(config: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
    indexed = {accessory_uid(item): serialize_accessory(item) for item in config.get("accessories", [])}
    selected = [indexed[item_id] for item_id in ids if item_id in indexed]
    if not selected:
        selected = [serialize_accessory(item) for item in config.get("accessories", [])]
    return selected


def ensure_object_clean_sprites_for_selection(config: dict[str, Any], ids: list[str]) -> bool:
    wanted = set(ids)
    changed = False
    for item in config.get("accessories", []):
        uid = accessory_uid(item)
        if wanted and uid not in wanted:
            continue
        if accessory_material_type(item) == "text":
            continue
        sprites = clean_sprite_assets(item)
        pose_jobs = [
            job
            for job in candidate_image_jobs(item)
            if Path(str(job.get("output_path", ""))).exists() and not job.get("intermediate")
        ]
        expected_count = min(18, len(pose_jobs) * len(POSE_COLLECTION_GRID_POSITIONS)) if pose_jobs else len(sprites)
        if sprites and len(sprites) >= expected_count and clean_sprites_policy_complete(item, sprites):
            continue
        changed = preprocess_object_clean_sprites(item, allow_ai_cutout=True, force=bool(sprites and pose_jobs)) or changed
    return changed


def physical_render_size_px(item: dict[str, Any], material_type: str) -> tuple[int, int]:
    size = item.get("physical_size") or {}
    if material_type == "text":
        width_mm = float(size.get("width_mm") or 210.0)
        height_mm = float(size.get("height_mm") or 297.0)
        return (
            max(70, int(round(width_mm * MM_TO_PREVIEW_PX))),
            max(90, int(round(height_mm * MM_TO_PREVIEW_PX))),
        )
    length_mm = float(size.get("length_mm") or DEFAULT_OBJECT_SIZE_MM["length_mm"])
    width_mm = float(size.get("width_mm") or DEFAULT_OBJECT_SIZE_MM["width_mm"])
    height_mm = float(size.get("height_mm") or DEFAULT_OBJECT_SIZE_MM["height_mm"])
    visible_width_mm = max(width_mm, height_mm * 0.72)
    return (
        max(34, int(round(length_mm * MM_TO_PREVIEW_PX))),
        max(16, int(round(visible_width_mm * MM_TO_PREVIEW_PX))),
    )


def physical_render_size_for_sprite(item: dict[str, Any], material_type: str, sprite_meta: dict[str, Any] | None = None) -> tuple[int, int]:
    return sprite_render_size_px(item, sprite_meta, material_type)


def random_center_inside_background(
    rng: np.random.Generator,
    target_size: tuple[int, int],
    angle: float,
    roi: tuple[int, int, int, int] = BACKGROUND_ROI_PX,
) -> tuple[int, int]:
    target_w, target_h = target_size
    radians = np.deg2rad(angle)
    cos_a = abs(float(np.cos(radians)))
    sin_a = abs(float(np.sin(radians)))
    half_w = int(np.ceil((target_w * cos_a + target_h * sin_a) / 2)) + 12
    half_h = int(np.ceil((target_w * sin_a + target_h * cos_a) / 2)) + 12
    x1, y1, x2, y2 = roi
    min_x, max_x = x1 + half_w, x2 - half_w
    min_y, max_y = y1 + half_h, y2 - half_h
    if min_x >= max_x:
        min_x, max_x = x1 + 20, x2 - 20
    if min_y >= max_y:
        min_y, max_y = y1 + 20, y2 - 20
    return (int(rng.integers(min_x, max_x + 1)), int(rng.integers(min_y, max_y + 1)))


def rotated_rect_tuple(
    center: tuple[int, int],
    target_size: tuple[int, int],
    angle: float,
) -> tuple[tuple[float, float], tuple[float, float], float]:
    return (
        (float(center[0]), float(center[1])),
        (max(1.0, float(target_size[0])), max(1.0, float(target_size[1]))),
        float(angle),
    )


def rotated_rect_overlap_area(
    a: tuple[tuple[float, float], tuple[float, float], float],
    b: tuple[tuple[float, float], tuple[float, float], float],
) -> float:
    status, points = cv2.rotatedRectangleIntersection(a, b)
    if status == cv2.INTERSECT_NONE or points is None:
        return 0.0
    return abs(float(cv2.contourArea(points)))


def object_placement_overlap_area(
    center: tuple[int, int],
    target_size: tuple[int, int],
    angle: float,
    placed_objects: list[dict[str, Any]],
) -> float:
    candidate = rotated_rect_tuple(center, target_size, angle)
    total = 0.0
    for placed in placed_objects:
        total += rotated_rect_overlap_area(candidate, placed["rect"])
    return total


def choose_object_center_inside_background(
    rng: np.random.Generator,
    target_size: tuple[int, int],
    angle: float,
    placed_objects: list[dict[str, Any]],
    roi: tuple[int, int, int, int] = BACKGROUND_ROI_PX,
) -> tuple[tuple[int, int], dict[str, Any]]:
    best_center = random_center_inside_background(rng, target_size, angle, roi)
    best_overlap = object_placement_overlap_area(best_center, target_size, angle, placed_objects)
    attempts = 1
    if best_overlap <= 0.5:
        return best_center, {"object_non_overlap_attempts": attempts, "object_overlap_area_px": 0.0, "object_non_overlap_pass": True}
    for attempts in range(2, 181):
        center = random_center_inside_background(rng, target_size, angle, roi)
        overlap = object_placement_overlap_area(center, target_size, angle, placed_objects)
        if overlap < best_overlap:
            best_center = center
            best_overlap = overlap
        if overlap <= 0.5:
            return center, {"object_non_overlap_attempts": attempts, "object_overlap_area_px": 0.0, "object_non_overlap_pass": True}
    return best_center, {
        "object_non_overlap_attempts": attempts,
        "object_overlap_area_px": round(float(best_overlap), 3),
        "object_non_overlap_pass": bool(best_overlap <= 0.5),
    }


def placement_box_points(center: tuple[int, int], target_size: tuple[int, int], angle: float) -> list[list[int]]:
    points = cv2.boxPoints(rotated_rect_tuple(center, target_size, angle))
    return [[int(round(x)), int(round(y))] for x, y in points.tolist()]


def mask_from_polygon(shape: tuple[int, int], polygon: list[list[int]]) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    points = np.array(polygon or [], dtype=np.int32)
    if len(points) >= 3:
        cv2.fillPoly(mask, [points], 255)
    return mask


def contour_to_polygon(contour: np.ndarray, shape: tuple[int, int], epsilon_ratio: float = 0.0035) -> list[list[int]]:
    epsilon = max(1.0, cv2.arcLength(contour, True) * epsilon_ratio)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    if len(approx) < 3:
        rect = cv2.minAreaRect(contour)
        approx = cv2.boxPoints(rect).astype(np.int32).reshape(-1, 1, 2)
    height, width = shape[:2]
    points: list[list[int]] = []
    for point in approx.reshape(-1, 2):
        x = int(np.clip(point[0], 0, width - 1))
        y = int(np.clip(point[1], 0, height - 1))
        if not points or points[-1] != [x, y]:
            points.append([x, y])
    if len(points) > 2 and points[0] == points[-1]:
        points.pop()
    return points if len(points) >= 3 else []


def visible_polygons_from_mask(mask: np.ndarray, epsilon_ratio: float = 0.0035) -> list[list[list[int]]]:
    if mask is None or mask.size == 0:
        return []
    binary = (mask > 24).astype(np.uint8) * 255
    if int(cv2.countNonZero(binary)) < 12:
        return []
    kernel = np.ones((3, 3), dtype=np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    max_area = max(float(cv2.contourArea(contour)) for contour in contours)
    polygons = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 12 or area < max_area * 0.015:
            continue
        polygon = contour_to_polygon(contour, binary.shape, epsilon_ratio)
        if polygon:
            polygons.append(polygon)
    return polygons


def visible_polygon_from_mask(mask: np.ndarray, epsilon_ratio: float = 0.0035) -> list[list[int]]:
    polygons = visible_polygons_from_mask(mask, epsilon_ratio)
    return polygons[0] if polygons else []


def load_training_background_manifest() -> dict[str, Any]:
    manifest_path = BACKGROUND_DIR / "background_manifest.json"
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    except json.JSONDecodeError:
        return {}


def safe_background_set_id(value: str | None) -> str:
    raw = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "").strip()).strip("_")
    return raw or "green_conveyor"


def load_background_sets_manifest() -> dict[str, Any]:
    try:
        return json.loads(BACKGROUND_SETS_MANIFEST.read_text(encoding="utf-8")) if BACKGROUND_SETS_MANIFEST.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_background_sets_manifest(manifest: dict[str, Any]) -> None:
    BACKGROUND_DIR.mkdir(parents=True, exist_ok=True)
    BACKGROUND_SETS_MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def image_file_list(path: Path) -> list[Path]:
    if not path.exists() or not path.is_dir():
        return []
    return sorted(
        item
        for item in path.iterdir()
        if item.is_file() and item.suffix.lower() in IMAGE_REFERENCE_SUFFIXES
    )


def seed_default_background_set() -> None:
    if not DEFAULT_BACKGROUND_IMAGE.exists():
        return
    manifest = load_background_sets_manifest()
    sets = manifest.get("sets") if isinstance(manifest.get("sets"), dict) else {}
    default_id = "green_conveyor"
    set_dir = BACKGROUND_SETS_DIR / default_id
    set_dir.mkdir(parents=True, exist_ok=True)
    original_target = set_dir / DEFAULT_BACKGROUND_IMAGE.name
    if not original_target.exists():
        shutil.copy2(DEFAULT_BACKGROUND_IMAGE, original_target)
    ensure_background_set_minimum_images(default_id)
    sets.setdefault(
        default_id,
        {
            "id": default_id,
            "name": "绿色传送带",
            "description": "同一生产环境的绿色传送带背景集",
            "source": str(DEFAULT_BACKGROUND_IMAGE),
            "created_at": int(time.time()),
            "generation_method": "seeded_from_existing_background",
        },
    )
    manifest["sets"] = sets
    manifest.setdefault("default_set_id", default_id)
    write_background_sets_manifest(manifest)


def background_set_dirs() -> list[Path]:
    seed_default_background_set()
    dirs = [path for path in BACKGROUND_SETS_DIR.iterdir() if path.is_dir()] if BACKGROUND_SETS_DIR.exists() else []
    return sorted(dirs, key=lambda path: path.name)


def background_set_payload(set_id: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    clean_id = safe_background_set_id(set_id)
    set_dir = BACKGROUND_SETS_DIR / clean_id
    images = image_file_list(set_dir)
    meta = meta or {}
    return {
        "id": clean_id,
        "name": meta.get("name") or clean_id.replace("_", " "),
        "description": meta.get("description") or "",
        "source": meta.get("source") or "",
        "created_at": int(meta.get("created_at") or (set_dir.stat().st_mtime if set_dir.exists() else time.time())),
        "generation_method": meta.get("generation_method") or "",
        "status": meta.get("status") or ("ready" if images else "empty"),
        "image_count": len(images),
        "images": [
            {
                "name": path.name,
                "path": str(path),
                "url": public_output_url(path) if str(path).startswith(str(OUTPUT_DIR)) else f"/api/backgrounds/{clean_id}/{path.name}",
            }
            for path in images
        ],
    }


def list_background_sets() -> list[dict[str, Any]]:
    manifest = load_background_sets_manifest()
    meta_sets = manifest.get("sets") if isinstance(manifest.get("sets"), dict) else {}
    ids = {path.name for path in background_set_dirs()} | {safe_background_set_id(item) for item in meta_sets.keys()}
    return [
        background_set_payload(set_id, meta_sets.get(set_id) or meta_sets.get(safe_background_set_id(set_id)) or {})
        for set_id in sorted(ids)
    ]


def selected_background_set_id(background_set_id: str | None) -> str | None:
    requested = safe_background_set_id(background_set_id)
    available = {
        item["id"]
        for item in list_background_sets()
        if item.get("image_count", 0) > 0 and str(item.get("status") or "ready") == "ready"
    }
    if requested in available:
        return requested
    manifest = load_background_sets_manifest()
    default_id = safe_background_set_id(manifest.get("default_set_id") or "green_conveyor")
    return default_id if default_id in available else (sorted(available)[0] if available else None)


def background_set_image_files(background_set_id: str | None) -> list[Path]:
    selected_id = selected_background_set_id(background_set_id)
    if not selected_id:
        return []
    return image_file_list(BACKGROUND_SETS_DIR / selected_id)


def create_background_variants_from_source(source_path: Path, set_dir: Path, count: int = 5) -> list[Path]:
    image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
    if image is None:
        return []
    set_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    rng = np.random.default_rng(int(time.time() * 1000) % (2**32 - 1))
    h, w = image.shape[:2]
    for idx in range(1, count + 1):
        variant = image.astype(np.float32)
        contrast = float(rng.uniform(0.94, 1.08))
        brightness = float(rng.uniform(-10, 10))
        variant = variant * contrast + brightness
        if float(rng.random()) < 0.8:
            variant += rng.normal(0, float(rng.uniform(1.0, 3.2)), size=variant.shape).astype(np.float32)
        variant = np.clip(variant, 0, 255).astype(np.uint8)
        scale = float(rng.uniform(1.0, 1.045))
        crop_w = max(1, int(w / scale))
        crop_h = max(1, int(h / scale))
        x = int(rng.integers(0, max(1, w - crop_w + 1)))
        y = int(rng.integers(0, max(1, h - crop_h + 1)))
        variant = cv2.resize(variant[y : y + crop_h, x : x + crop_w], (w, h), interpolation=cv2.INTER_AREA)
        overlay = variant.copy()
        for _ in range(int(rng.integers(5, 14))):
            x1 = int(rng.integers(0, w))
            y1 = int(rng.integers(0, h))
            x2 = int(np.clip(x1 + rng.normal(0, w * 0.2), 0, w - 1))
            y2 = int(np.clip(y1 + rng.normal(0, h * 0.025), 0, h - 1))
            shade = int(rng.integers(45, 210))
            cv2.line(overlay, (x1, y1), (x2, y2), (shade, shade, shade), 1, cv2.LINE_AA)
        alpha = float(rng.uniform(0.025, 0.06))
        variant = cv2.addWeighted(overlay, alpha, variant, 1.0 - alpha, 0)
        output = set_dir / f"{source_path.stem}_variant_{idx:02d}.png"
        cv2.imwrite(str(output), variant)
        created.append(output)
    return created


def run_codex_background_generation(source_path: Path, set_dir: Path, set_id: str, count: int = 5) -> list[Path]:
    if not shutil.which("codex") or not source_path.exists():
        return []
    set_dir.mkdir(parents=True, exist_ok=True)
    log_path = IMAGE_WORKER_LOG_DIR / f"background_{safe_name(set_id)}_codexcli.log"
    outputs = [set_dir / f"codex_{safe_name(set_id)}_{idx:02d}.png" for idx in range(1, count + 1)]
    prompt = "\n".join(
        [
            "You are the ImageWorker for the local assembly-line inspection service.",
            "",
            "Use the attached reference image as the source environment. Generate realistic, empty, overhead-view background PNGs of the same surface type and same environment. Keep camera geometry, material texture, scratches, dust, lighting, rails/edges if present, and mild natural variation. Do not add objects, text, labels, watermarks, hands, people, manuals, bottles, tools, or parts.",
            "",
            "Save the final PNG files exactly here:",
            *[str(path) for path in outputs],
        ]
    )
    command = [
        "codex",
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "-C",
        str(ROOT),
        "-i",
        str(source_path),
        "-",
    ]
    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            process = subprocess.Popen(command, cwd=str(ROOT), stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, text=True)
            process.communicate(prompt + "\n", timeout=900)
    except subprocess.TimeoutExpired:
        try:
            process.kill()  # type: ignore[name-defined]
        except Exception:
            pass
        return [path for path in outputs if path.exists()]
    except Exception:
        return []
    return [path for path in outputs if path.exists()]


def start_codex_background_generation(source_path: Path, set_dir: Path, set_id: str, count: int = 5) -> None:
    thread = threading.Thread(
        target=run_codex_background_generation,
        args=(source_path, set_dir, set_id, count),
        name=f"codex-background-worker-{safe_name(set_id)}",
        daemon=True,
    )
    thread.start()


def ensure_background_set_minimum_images(set_id: str, min_count: int = 6) -> None:
    clean_id = safe_background_set_id(set_id)
    set_dir = BACKGROUND_SETS_DIR / clean_id
    images = image_file_list(set_dir)
    if len(images) >= min_count or not images:
        return
    create_background_variants_from_source(images[0], set_dir, max(0, min_count - len(images)))


def unique_background_set_id(base_id: str) -> str:
    clean_id = safe_background_set_id(base_id)
    manifest = load_background_sets_manifest()
    sets = manifest.get("sets") if isinstance(manifest.get("sets"), dict) else {}
    if clean_id not in sets and not (BACKGROUND_SETS_DIR / clean_id).exists():
        return clean_id
    for _ in range(50):
        candidate = f"{clean_id}_{uuid.uuid4().hex[:6]}"
        if candidate not in sets and not (BACKGROUND_SETS_DIR / candidate).exists():
            return candidate
    return f"{clean_id}_{int(time.time())}"


def update_background_set_manifest(set_id: str, **updates: Any) -> dict[str, Any]:
    manifest = load_background_sets_manifest()
    sets = manifest.get("sets") if isinstance(manifest.get("sets"), dict) else {}
    current = sets.get(set_id, {"id": set_id, "name": set_id.replace("_", " ")})
    current.update(updates)
    sets[set_id] = current
    manifest["sets"] = sets
    manifest.setdefault("default_set_id", "green_conveyor")
    write_background_sets_manifest(manifest)
    return current


def run_background_set_task(job_id: str) -> None:
    task = load_training_task(training_task_path(job_id))
    if not task:
        return
    set_id = str(task.get("background_set_id") or "")
    source_path = Path(str(task.get("source_path") or ""))
    set_dir = BACKGROUND_SETS_DIR / safe_background_set_id(set_id)
    try:
        if not source_path.exists():
            raise RuntimeError("上传的背景源图不存在。")
        update_training_task(job_id, status="running", progress=8, started_at=int(time.time()), note="背景任务已启动，正在准备源图。")
        update_background_set_manifest(set_id, status="generating", updated_at=int(time.time()))
        local_variants = create_background_variants_from_source(source_path, set_dir, 5)
        if len(local_variants) < 5:
            raise RuntimeError(f"本地背景变体生成不足：{len(local_variants)}/5。")
        update_training_task(
            job_id,
            status="running",
            progress=42,
            generated_image_count=1 + len(local_variants),
            note=f"本地背景变体已生成 {len(local_variants)}/5，正在等待 AI 背景生成。",
        )
        codex_outputs = run_codex_background_generation(source_path, set_dir, set_id, 5)
        if len(codex_outputs) < 5:
            raise RuntimeError(f"AI 背景生成不足：{len(codex_outputs)}/5。")
        image_count = len(image_file_list(set_dir))
        update_background_set_manifest(
            set_id,
            status="ready",
            generation_method="queued_codexcli_imgworker_plus_local_same_environment_fallback",
            image_count=image_count,
            completed_at=int(time.time()),
            updated_at=int(time.time()),
        )
        update_training_task(
            job_id,
            status="completed",
            progress=100,
            completed_at=int(time.time()),
            generated_image_count=image_count,
            note=f"背景集已生成完成，共 {image_count} 张。",
        )
    except Exception as exc:
        update_background_set_manifest(set_id, status="failed", error=str(exc), updated_at=int(time.time()))
        update_training_task(job_id, status="failed", progress=100, completed_at=int(time.time()), error=str(exc), note=f"背景生成失败：{exc}")


def enqueue_background_set_task(set_id: str, name: str, source_path: Path) -> dict[str, Any]:
    job_id = f"background_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    task = {
        "job_id": job_id,
        "task_id": job_id,
        "candidate_id": job_id,
        "candidate_name": name or set_id.replace("_", " "),
        "label": f"添加背景：{name or set_id.replace('_', ' ')}",
        "queue_kind": "training",
        "action": "generate_background_set",
        "status": "queued",
        "progress": 0,
        "created_at": int(time.time()),
        "background_set_id": set_id,
        "source_path": str(source_path),
        "sample_count": 0,
        "estimated_minutes": 10,
        "note": "背景生成任务已加入队列；完成前该背景集不会进入可选列表。",
    }
    save_training_task(task)
    thread = threading.Thread(target=run_background_set_task, args=(job_id,), daemon=True, name=f"background-set-task-{job_id}")
    _training_task_threads[job_id] = thread
    thread.start()
    return public_training_task(task)


def training_background_library(background_set_id: str | None = None) -> list[dict[str, Any]]:
    manifest = load_training_background_manifest()
    set_id = selected_background_set_id(background_set_id)
    files = background_set_image_files(set_id)
    if not files:
        files = sorted(
            path
            for path in BACKGROUND_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_REFERENCE_SUFFIXES
        ) if BACKGROUND_DIR.exists() else []
        if DEFAULT_BACKGROUND_IMAGE.exists() and DEFAULT_BACKGROUND_IMAGE not in files:
            files.insert(0, DEFAULT_BACKGROUND_IMAGE)
    elif set_id == "green_conveyor" and DEFAULT_BACKGROUND_IMAGE.exists() and DEFAULT_BACKGROUND_IMAGE not in files:
        files.insert(0, DEFAULT_BACKGROUND_IMAGE)
    library: list[dict[str, Any]] = []
    for index, path in enumerate(files):
        background_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", path.stem).strip("_") or f"background_{index + 1}"
        source = str(path)
        if path.name == manifest.get("asset"):
            source = str(manifest.get("reference_photo") or manifest.get("workspace_path") or path)
        library.append(
            {
                "id": background_id,
                "path": path,
                "source": source,
                "source_asset": path.name,
                "background_set_id": set_id,
                "library_index": index,
                "library_size": len(files),
            }
        )
    return library


def background_candidates_for_split(library: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    if len(library) >= 3:
        if split == "val":
            return [library[-2]]
        if split == "test":
            return [library[-1]]
        return library[:-2]
    if len(library) == 2:
        return [library[1]] if split in {"val", "test"} else [library[0]]
    return library


def synthetic_training_background(rng: np.random.Generator) -> tuple[np.ndarray, dict[str, Any]]:
    canvas = np.full((900, 1280, 3), (232, 234, 235), dtype=np.uint8)
    base_color = np.array((87, 116, 98), dtype=np.float32)
    jitter = rng.normal(0, 6, size=3)
    color = tuple(int(np.clip(value, 0, 255)) for value in base_color + jitter)
    cv2.rectangle(canvas, (70, 100), (1210, 800), color, -1)
    for _ in range(18):
        x1 = int(rng.integers(70, 1210))
        y1 = int(rng.integers(100, 800))
        x2 = int(np.clip(x1 + rng.normal(0, 220), 70, 1210))
        y2 = int(np.clip(y1 + rng.normal(0, 36), 100, 800))
        shade = int(rng.integers(70, 135))
        cv2.line(canvas, (x1, y1), (x2, y2), (shade, shade, shade), 1, cv2.LINE_AA)
    return canvas, {
        "background_id": "synthetic_conveyor_fallback",
        "background_source": "generated_same_environment_fallback",
        "background_source_asset": None,
        "background_library_size": 0,
        "background_split_pool_size": 0,
        "background_split_pool_isolated": False,
    }


def fit_training_background_to_canvas(
    image: np.ndarray,
    rng: np.random.Generator,
    target_size: tuple[int, int] = (1280, 900),
) -> tuple[np.ndarray, dict[str, Any]]:
    target_w, target_h = target_size
    source_h, source_w = image.shape[:2]
    crop_scale = float(rng.uniform(1.0, 1.08))
    crop_w = int(round(target_w * crop_scale))
    crop_h = int(round(target_h * crop_scale))
    resize_ratio = max(crop_w / max(1, source_w), crop_h / max(1, source_h))
    resized_w = max(crop_w, int(math.ceil(source_w * resize_ratio)))
    resized_h = max(crop_h, int(math.ceil(source_h * resize_ratio)))
    resized = cv2.resize(image, (resized_w, resized_h), interpolation=cv2.INTER_AREA)
    max_x = max(0, resized_w - crop_w)
    max_y = max(0, resized_h - crop_h)
    crop_x = int(rng.integers(0, max_x + 1)) if max_x else 0
    crop_y = int(rng.integers(0, max_y + 1)) if max_y else 0
    crop = resized[crop_y : crop_y + crop_h, crop_x : crop_x + crop_w]
    canvas = cv2.resize(crop, (target_w, target_h), interpolation=cv2.INTER_AREA)
    return canvas, {
        "background_crop_scale": round(crop_scale, 4),
        "background_crop_xywh": [crop_x, crop_y, crop_w, crop_h],
        "background_resized_size_px": [resized_w, resized_h],
        "background_original_size_px": [source_w, source_h],
    }


def augment_training_background(canvas: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, dict[str, Any]]:
    image = canvas.astype(np.float32)
    contrast = float(rng.uniform(0.92, 1.1))
    brightness = float(rng.uniform(-14.0, 14.0))
    image = image * contrast + brightness
    noise_std = float(rng.uniform(1.0, 4.5))
    image += rng.normal(0.0, noise_std, size=image.shape).astype(np.float32)
    image = np.clip(image, 0, 255).astype(np.uint8)
    blur_kernel = 0
    if float(rng.random()) < 0.35:
        blur_kernel = int(rng.choice([3, 5]))
        image = cv2.GaussianBlur(image, (blur_kernel, blur_kernel), 0)
    glare_applied = False
    glare_alpha = 0.0
    texture_lines = int(rng.integers(6, 18))
    overlay = image.copy()
    for _ in range(texture_lines):
        x1 = int(rng.integers(70, 1210))
        y1 = int(rng.integers(100, 800))
        x2 = int(np.clip(x1 + rng.normal(0, 260), 70, 1210))
        y2 = int(np.clip(y1 + rng.normal(0, 28), 100, 800))
        shade = int(rng.integers(42, 210))
        cv2.line(overlay, (x1, y1), (x2, y2), (shade, shade, shade), 1, cv2.LINE_AA)
    alpha = max(glare_alpha, 0.03)
    image = cv2.addWeighted(overlay, alpha, image, 1.0 - alpha, 0)
    return image, {
        "background_augmentation": {
            "crop_shift": True,
            "brightness_delta": round(brightness, 3),
            "contrast": round(contrast, 4),
            "noise_std": round(noise_std, 3),
            "blur_kernel": blur_kernel,
            "glare_applied": glare_applied,
            "glare_alpha": round(glare_alpha, 4),
            "texture_lines": texture_lines,
        }
    }


def render_training_background(
    rng: np.random.Generator,
    split: str | None = None,
    background_set_id: str | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    split_name = split if split in {"train", "val", "test"} else "preview"
    library = training_background_library(background_set_id)
    candidates = background_candidates_for_split(library, split_name)
    if not candidates:
        canvas, meta = synthetic_training_background(rng)
    else:
        item = candidates[int(rng.integers(0, len(candidates)))]
        background = cv2.imread(str(item["path"]), cv2.IMREAD_COLOR)
        if background is None:
            canvas, meta = synthetic_training_background(rng)
            meta["background_source_error"] = f"unreadable_background:{item['path']}"
        else:
            canvas, crop_meta = fit_training_background_to_canvas(background, rng)
            meta = {
                "background_id": item["id"],
                "background_source": item["source"],
                "background_source_asset": item["source_asset"],
                "background_set_id": item.get("background_set_id"),
                "background_library_size": item["library_size"],
                "background_split_pool_size": len(candidates),
                "background_split_pool_isolated": bool(len(library) > 1 and set(item["id"] for item in candidates) != set(item["id"] for item in library)),
                **crop_meta,
            }
    canvas, augmentation_meta = augment_training_background(canvas, rng)
    meta.update(augmentation_meta)
    meta["background_split"] = split_name
    meta["background_policy"] = "same_environment_library_with_per_sample_crop_shift_photometric_noise_texture_no_glare"
    return canvas, meta


def draw_training_preview(
    accessories: list[dict[str, Any]],
    output_path: Path,
    seed: int,
    pose_family_policy: str | None = None,
    split: str | None = None,
    background_set_id: str | None = None,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    canvas, background_meta = render_training_background(rng, split, background_set_id)
    cv2.rectangle(canvas, (70, 100), (1210, 800), (49, 72, 60), 2)
    labels = []
    placed_objects: list[dict[str, Any]] = []
    visible_label_records: list[dict[str, Any]] = []
    render_accessories = sorted(accessories, key=lambda entry: 0 if accessory_material_type(entry) == "text" else 1)
    for idx, item in enumerate(render_accessories):
        material_type = accessory_material_type(item)
        angle = float(rng.uniform(-175, 175)) if material_type == "text" else 0.0
        final_render_angle = angle
        perspective_rotation = 0.0
        source_restore_rotation = 0.0
        size = physical_render_size_px(item, material_type)
        center = random_center_inside_background(rng, size, angle)
        loaded_asset = (
            load_rectified_document_asset_with_metadata(item)
            if material_type == "text"
            else load_preview_asset_with_metadata(item)
        )
        asset = loaded_asset[0] if loaded_asset else None
        sprite_meta: dict[str, Any] = {}
        if material_type == "text":
            if asset is not None:
                sprite_meta.update(loaded_asset[1] if loaded_asset else {})
                sprite_meta.update(paste_rectified_document_asset(canvas, asset, center, size, angle))
            else:
                rect = (center, size, angle)
                box = cv2.boxPoints(rect).astype(np.int32)
                cv2.fillConvexPoly(canvas, box, (245, 246, 246))
                cv2.polylines(canvas, [box], True, (25, 27, 29), 2)
                fallback_visible_mask = mask_from_polygon(canvas.shape[:2], box.tolist())
                sprite_meta = {
                    "source_fallback_error": "document_rectified_asset_not_available",
                    "document_mask_crop_bypassed": True,
                    "object_alpha_pipeline_bypassed": True,
                    "render_resize_policy": "document_placeholder_physical_size",
                    "render_box_px": [int(size[0]), int(size[1])],
                    "render_visible_footprint_px": [int(size[0]), int(size[1])],
                    "_visible_mask_canvas": fallback_visible_mask,
                }
        else:
            sprites = clean_sprite_assets(item)
            pose_family = pose_family_policy if pose_family_policy in available_object_pose_families(item) else choose_object_pose_family(sprites, rng)
            render_policy = object_render_pose_policy(pose_family, rng)
            perspective_rotation = float(render_policy["perspective_rotation_degrees"])
            angle = float(render_policy["placement_angle_degrees"])
            top_view_pose = pose_family_is_top_view(pose_family or "")
            size = object_pose_render_size_hint(item, pose_family)
            center, placement_meta = choose_object_center_inside_background(rng, size, angle, placed_objects)
            target_position = grid_position_for_center(center)
            selected_source_position = source_position_for_render_policy(target_position, perspective_rotation, pose_family, rng)
            sprite = load_object_preview_sprite(
                item,
                rng,
                target_position,
                pose_family=pose_family,
                source_position=selected_source_position,
            )
            if sprite is not None:
                sprite_image, sprite_mask, sprite_meta = sprite
                sprite_meta = dict(sprite_meta)
                top_view_pose = pose_family_is_top_view(
                    str(sprite_meta.get("source_pose_family") or sprite_meta.get("pose_family") or ""),
                    sprite_meta.get("source_object_size_px"),
                )
                sprite_size = object_pose_render_size_hint(
                    item,
                    str(sprite_meta.get("source_pose_family") or sprite_meta.get("pose_family") or pose_family or ""),
                )
                sprite_size = physical_render_size_for_sprite(item, material_type, sprite_meta)
                size = sprite_size
                ignored_source_restore_rotation = float(sprite_meta.get("source_restore_rotation_degrees") or 0.0)
                source_restore_rotation = 0.0
                final_render_angle = perspective_rotation
                current_source_position = sprite_meta.get("source_position") or sprite_meta.get("pose_position")
                if selected_source_position and current_source_position != selected_source_position:
                    rematched = load_object_preview_sprite(
                        item,
                        rng,
                        target_position,
                        pose_family=str(sprite_meta.get("source_pose_family") or sprite_meta.get("pose_family") or pose_family or ""),
                        source_position=selected_source_position,
                    )
                    if rematched is not None:
                        sprite_image, sprite_mask, sprite_meta = rematched
                        sprite_meta = dict(sprite_meta)
                        top_view_pose = pose_family_is_top_view(
                            str(sprite_meta.get("source_pose_family") or sprite_meta.get("pose_family") or ""),
                            sprite_meta.get("source_object_size_px"),
                        )
                        ignored_source_restore_rotation = float(sprite_meta.get("source_restore_rotation_degrees") or 0.0)
                        source_restore_rotation = 0.0
                        final_render_angle = perspective_rotation
                        sprite_size = object_pose_render_size_hint(
                            item,
                            str(sprite_meta.get("source_pose_family") or sprite_meta.get("pose_family") or pose_family or ""),
                        )
                        sprite_size = physical_render_size_for_sprite(item, material_type, sprite_meta)
                        size = sprite_size
                actual_source_position = sprite_meta.get("source_position") or sprite_meta.get("pose_position")
                sprite_meta["target_position"] = target_position
                sprite_meta["selected_source_position"] = selected_source_position
                sprite_meta["actual_source_position"] = actual_source_position
                sprite_meta["source_selection_rule"] = render_policy["source_selection_rule"]
                sprite_meta["source_selection_reason"] = pose_selection_reason(
                    target_position,
                    selected_source_position,
                    perspective_rotation,
                )
                sprite_meta["desired_lie_direction"] = render_policy.get("desired_lie_direction")
                sprite_meta["desired_facing_direction"] = render_policy["desired_facing_direction"]
                sprite_meta["perspective_rotation_degrees"] = round(float(perspective_rotation), 2)
                sprite_meta["placement_angle_degrees"] = round(float(angle), 2)
                sprite_meta["final_render_angle_degrees"] = round(float(final_render_angle), 2)
                sprite_meta["source_rotation_correction_degrees"] = round(float(source_restore_rotation), 2)
                sprite_meta["ignored_source_restore_rotation_degrees"] = round(float(ignored_source_restore_rotation), 2)
                sprite_meta["render_pose_policy"] = render_policy["render_pose_policy"]
                sprite_meta["upright_pose_no_rotation"] = False
                sprite_meta["upright_pose_random_rotation"] = bool(top_view_pose)
                sprite_meta.update(placement_meta)
                sprite_meta.update(
                    paste_physical_object_asset(
                        canvas,
                        sprite_image,
                        sprite_mask,
                        center,
                        sprite_size[0],
                        sprite_size[1],
                        final_render_angle,
                        preserve_aspect_ratio=top_view_pose and object_alpha_material_policy(item) == "transparent",
                    )
                )
            else:
                sprite_meta = {
                    "method": "missing_clean_object_sprite",
                    "source_fallback_error": "clean_object_sprite_not_available",
                    "render_pose_policy": render_policy["render_pose_policy"],
                    "target_position": target_position,
                    "selected_source_position": selected_source_position,
                    "actual_source_position": None,
                    "source_selection_rule": render_policy["source_selection_rule"],
                    "source_selection_reason": pose_selection_reason(
                        target_position,
                        selected_source_position,
                        perspective_rotation,
                    ),
                    "desired_lie_direction": render_policy.get("desired_lie_direction"),
                    "desired_facing_direction": render_policy["desired_facing_direction"],
                    "perspective_rotation_degrees": round(float(perspective_rotation), 2),
                    "placement_angle_degrees": round(float(angle), 2),
                    "final_render_angle_degrees": round(float(angle), 2),
                }
                sprite_meta.update(placement_meta)
                final_render_angle = angle
                rect = (center, size, angle)
                box = cv2.boxPoints(rect).astype(np.int32)
                cv2.fillConvexPoly(canvas, box, (34, 36, 38))
                cv2.polylines(canvas, [box], True, (7, 8, 9), 2)
                cv2.circle(canvas, tuple(box[0]), 18, (128, 37, 31), -1)
                sprite_meta["_visible_mask_canvas"] = mask_from_polygon(canvas.shape[:2], box.tolist())
        current_visible_mask = sprite_meta.pop("_visible_mask_canvas", None)
        placement_polygon = placement_box_points(center, size, final_render_angle)
        if material_type == "object":
            placed_objects.append(
                {
                    "id": item["id"],
                    "rect": rotated_rect_tuple(center, size, final_render_angle),
                    "polygon": placement_polygon,
                }
            )
        label_entry = {
                "id": item["id"],
                "name": item["name"],
                "angle": round(final_render_angle, 2),
                "placement_angle_degrees": round(angle, 2),
                "final_render_angle_degrees": round(final_render_angle, 2),
                "z_index": idx + 1,
                "material_type": material_type,
                "physical_size": item.get("physical_size"),
                "center_xy": [int(center[0]), int(center[1])],
                "render_size_px": physical_render_size_for_sprite(item, material_type, sprite_meta),
                "render_policy": (
                    str(sprite_meta.get("render_scale_basis") or "object_side_major_axis_equals_physical_length")
                    if material_type == "object"
                    else "paper_width_height_equals_physical_size"
                ),
                "pose_position": grid_position_for_center(center) if material_type == "object" else None,
                "target_position": sprite_meta.get("target_position") if material_type == "object" else None,
                "selected_source_position": sprite_meta.get("selected_source_position") if material_type == "object" else None,
                "actual_source_position": sprite_meta.get("actual_source_position") if material_type == "object" else None,
                "source_selection_rule": sprite_meta.get("source_selection_rule") if material_type == "object" else None,
                "source_selection_reason": sprite_meta.get("source_selection_reason") if material_type == "object" else None,
                "desired_lie_direction": sprite_meta.get("desired_lie_direction") if material_type == "object" else None,
                "desired_facing_direction": sprite_meta.get("desired_facing_direction") if material_type == "object" else None,
                "perspective_rotation_degrees": sprite_meta.get("perspective_rotation_degrees") if material_type == "object" else None,
                "render_pose_policy": sprite_meta.get("render_pose_policy") if material_type == "object" else None,
                "preview_pose_family_policy": pose_family_policy if material_type == "object" else None,
                "sprite_index": sprite_meta.get("sprite_index") if material_type == "object" else None,
                "sprite_path": sprite_meta.get("sprite_path") if material_type == "object" else None,
                "clean_sprite_preprocessed_at": sprite_meta.get("clean_sprite_preprocessed_at") if material_type == "object" else None,
                "clean_sprite_version": sprite_meta.get("clean_sprite_version") if material_type == "object" else None,
                "sprite_source_method": sprite_meta.get("method") if material_type == "object" else None,
                "source_fallback_error": sprite_meta.get("source_fallback_error") if material_type == "object" else None,
                "task_id": sprite_meta.get("task_id") if material_type == "object" else None,
                "source_pose_collection_job_id": sprite_meta.get("source_pose_collection_job_id") if material_type == "object" else None,
                "pose_source_position": sprite_meta.get("pose_position") if material_type == "object" else None,
                "source_position": sprite_meta.get("source_position") if material_type == "object" else None,
                "source_image_size_px": sprite_meta.get("source_image_size_px"),
                "source_image_width": sprite_meta.get("source_image_width") if material_type == "object" else (sprite_meta.get("source_image_size_px") or [None, None])[0],
                "source_image_height": sprite_meta.get("source_image_height") if material_type == "object" else (sprite_meta.get("source_image_size_px") or [None, None])[1],
                "target_source_position_match": (
                    sprite_meta.get("actual_source_position") == sprite_meta.get("selected_source_position")
                    if material_type == "object" and sprite_meta.get("selected_source_position")
                    else None
                ),
                "pose_source_family": (sprite_meta.get("pose_family") or sprite_meta.get("source_pose_family")) if material_type == "object" else None,
                "pose_source_bbox_xyxy": sprite_meta.get("source_object_bbox_xyxy") if material_type == "object" else None,
                "pose_source_footprint_px": sprite_meta.get("source_object_size_px") if material_type == "object" else None,
                "render_footprint_mm": sprite_meta.get("render_footprint_mm") if material_type == "object" else None,
                "render_footprint_px": sprite_meta.get("render_footprint_px") if material_type == "object" else sprite_meta.get("render_visible_footprint_px"),
                "render_box_px": sprite_meta.get("render_box_px"),
                "render_visible_footprint_px": sprite_meta.get("render_visible_footprint_px"),
                "source_visible_footprint_px": sprite_meta.get("source_visible_footprint_px"),
                "render_resize_policy": sprite_meta.get("render_resize_policy"),
                "non_uniform_scaling_applied": sprite_meta.get("non_uniform_scaling_applied"),
                "render_scale_x": sprite_meta.get("render_scale_x"),
                "render_scale_y": sprite_meta.get("render_scale_y"),
                "render_scale_basis": sprite_meta.get("render_scale_basis") if material_type == "object" else None,
                "material_alpha_policy": item.get("material_alpha_policy") if material_type == "object" else None,
                "object_alpha_material_policy": sprite_meta.get("object_alpha_material_policy") if material_type == "object" else None,
                "transparent_alpha_policy": sprite_meta.get("transparent_alpha_policy") if material_type == "object" else None,
                "placement_polygon_xy": placement_polygon,
                "object_non_overlap_attempts": sprite_meta.get("object_non_overlap_attempts") if material_type == "object" else None,
                "object_overlap_area_px": sprite_meta.get("object_overlap_area_px") if material_type == "object" else None,
                "object_non_overlap_pass": sprite_meta.get("object_non_overlap_pass") if material_type == "object" else None,
                "render_scale_basis_before_correction": sprite_meta.get("render_scale_basis_before_correction") if material_type == "object" else None,
                "render_footprint_px_before_correction": sprite_meta.get("render_footprint_px_before_correction") if material_type == "object" else None,
                "render_footprint_px_after_correction": sprite_meta.get("render_footprint_px_after_correction") if material_type == "object" else None,
                "upright_scale_correction": sprite_meta.get("upright_scale_correction") if material_type == "object" else None,
                "upright_scale_correction_raw": sprite_meta.get("upright_scale_correction_raw") if material_type == "object" else None,
                "upright_scale_correction_before_visual_adjustment": sprite_meta.get("upright_scale_correction_before_visual_adjustment") if material_type == "object" else None,
                "upright_scale_visual_adjustment": sprite_meta.get("upright_scale_visual_adjustment") if material_type == "object" else None,
                "upright_scale_adjustment_percent": sprite_meta.get("upright_scale_adjustment_percent") if material_type == "object" else None,
                "upright_scale_adjustment_reason": sprite_meta.get("upright_scale_adjustment_reason") if material_type == "object" else None,
                "upright_scale_visually_adjusted": sprite_meta.get("upright_scale_visually_adjusted") if material_type == "object" else None,
                "upright_scale_correction_basis": sprite_meta.get("upright_scale_correction_basis") if material_type == "object" else None,
                "upright_scale_correction_source_dimensions": sprite_meta.get("upright_scale_correction_source_dimensions") if material_type == "object" else None,
                "upright_scale_correction_physical_ratio": sprite_meta.get("upright_scale_correction_physical_ratio") if material_type == "object" else None,
                "upright_scale_correction_clamped": sprite_meta.get("upright_scale_correction_clamped") if material_type == "object" else None,
                "original_orientation_angle": sprite_meta.get("original_orientation_angle") if material_type == "object" else None,
                "rotation_degrees_applied": sprite_meta.get("rotation_degrees_applied") if material_type == "object" else None,
                "source_restore_rotation_degrees": round(source_restore_rotation, 2) if material_type == "object" else None,
                "source_rotation_correction_degrees": sprite_meta.get("source_rotation_correction_degrees") if material_type == "object" else None,
                "upright_pose_no_rotation": sprite_meta.get("upright_pose_no_rotation") if material_type == "object" else None,
                "upright_pose_random_rotation": sprite_meta.get("upright_pose_random_rotation") if material_type == "object" else None,
                "canonical_asset_dimensions_px": sprite_meta.get("canonical_asset_dimensions_px"),
                "canonical_width_px": sprite_meta.get("canonical_width_px") if material_type == "object" else (sprite_meta.get("canonical_asset_dimensions_px") or [None, None])[0],
                "canonical_height_px": sprite_meta.get("canonical_height_px") if material_type == "object" else (sprite_meta.get("canonical_asset_dimensions_px") or [None, None])[1],
                "normalized_asset_dimensions_px": sprite_meta.get("normalized_asset_dimensions_px") if material_type == "object" else sprite_meta.get("canonical_asset_dimensions_px"),
                "document_asset_path": sprite_meta.get("asset_path") if material_type == "text" else None,
                "document_asset_source": sprite_meta.get("asset_source") if material_type == "text" else None,
                "document_asset_method": sprite_meta.get("asset_method") if material_type == "text" else None,
                "document_mask_crop_bypassed": sprite_meta.get("document_mask_crop_bypassed") if material_type == "text" else None,
                "object_alpha_pipeline_bypassed": sprite_meta.get("object_alpha_pipeline_bypassed") if material_type == "text" else None,
                "document_full_asset_pasted": sprite_meta.get("document_full_asset_pasted") if material_type == "text" else None,
                "document_asset_policy": sprite_meta.get("document_asset_policy") if material_type == "text" else None,
                "document_physical_scale_basis": sprite_meta.get("document_physical_scale_basis") if material_type == "text" else None,
            }
        labels.append(label_entry)
        if isinstance(current_visible_mask, np.ndarray):
            current_visible_mask = current_visible_mask.copy()
            for record in visible_label_records:
                record["mask"][current_visible_mask > 24] = 0
            visible_label_records.append({"label": label_entry, "mask": current_visible_mask})
    for record in visible_label_records:
        visible_polygon = visible_polygon_from_mask(record["mask"])
        if visible_polygon:
            record["label"]["visible_polygon_xy"] = visible_polygon
            record["label"]["visible_polygons_xy"] = [visible_polygon]
            record["label"]["placement_polygon_xy"] = visible_polygon
    cv2.imwrite(str(output_path), canvas)
    return {
        "url": public_output_url(output_path),
        "pose_family_policy": pose_family_policy,
        "render_policy_note": (
            "controlled_pose_family_per_preview_card; upright uses no rotation; lying uses cardinal rotation with inverse source-position mapping"
        ),
        "background": background_meta,
        "labels": labels,
    }


def training_estimate(
    sample_count: int,
    include_training: bool = False,
    include_generation: bool = True,
    epochs: int = 80,
    image_size: int = 640,
    selected_count: int = 1,
    train_mode: str = "yolo",
) -> dict[str, Any]:
    sample_count = max(1, min(20000, int(sample_count)))
    selected_count = max(1, min(100, int(selected_count or 1)))
    epochs = max(1, min(500, int(epochs or 1)))
    image_size = max(320, min(1280, int(image_size or 640)))
    generate_seconds = 8 + sample_count * (0.12 + selected_count * 0.025 + 0.018) if include_generation else 0
    train_seconds = 0.0
    if include_training:
        size_factor = (image_size / 640.0) ** 2
        mode_factor = 1.03 if train_mode == "yolo_ocr" else 1.0
        train_seconds = 75 + epochs * 7 + sample_count * epochs * 0.085 * size_factor * mode_factor
    generate_minutes = max(0, int(math.ceil(generate_seconds / 60.0)))
    train_minutes = max(0, int(math.ceil(train_seconds / 60.0)))
    return {
        "sample_count": sample_count,
        "estimated_minutes": max(1, generate_minutes + train_minutes),
        "estimated_generate_minutes": generate_minutes,
        "estimated_train_minutes": train_minutes,
        "estimated_gb": round(sample_count * 1.8 / 1024, 2),
        "estimate_formula_version": "gpu-cache-autobatch-v3",
    }


def yolo_label_line(class_index: int, polygon: list[list[int]], width: int = 1280, height: int = 900) -> str | None:
    if not polygon or len(polygon) < 3:
        return None
    values = [str(class_index)]
    for x, y in polygon:
        nx = min(1.0, max(0.0, float(x) / float(width)))
        ny = min(1.0, max(0.0, float(y) / float(height)))
        values.extend([f"{nx:.6f}", f"{ny:.6f}"])
    return " ".join(values)


def write_dataset_yaml(path: Path, dataset_dir: Path, names: list[str]) -> None:
    safe_names = [
        re.sub(r"[^a-zA-Z0-9_]+", "_", str(name or f"class_{idx}")).strip("_") or f"class_{idx}"
        for idx, name in enumerate(names)
    ]
    body = [
        f"path: {dataset_dir.as_posix()}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "names:",
    ]
    body.extend([f"  {idx}: {name}" for idx, name in enumerate(safe_names)])
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


def split_counts(total: int) -> dict[str, int]:
    total = max(1, int(total))
    if total < 3:
        return {"train": total, "val": 0, "test": 0}
    val = max(1, int(round(total * 0.1)))
    test = max(1, int(round(total * 0.1)))
    train = max(1, total - val - test)
    while train + val + test > total:
        if train >= val and train >= test and train > 1:
            train -= 1
        elif val >= test and val > 1:
            val -= 1
        else:
            test -= 1
    while train + val + test < total:
        train += 1
    return {"train": train, "val": val, "test": test}


def missing_count_for_false_sample(accessory_count: int, rng: np.random.Generator) -> int:
    accessory_count = max(1, int(accessory_count))
    if accessory_count == 1 or rng.random() < 0.95:
        return 1
    candidates = list(range(2, accessory_count + 1))
    weights = np.array([0.5 ** (value - 2) for value in candidates], dtype=np.float64)
    weights = weights / weights.sum()
    return int(rng.choice(candidates, p=weights))


def build_training_sample_plan(
    selected: list[dict[str, Any]],
    sample_count: int,
    seed: int,
    pose_policy: str,
) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed)
    selected_ids = [str(item["id"]) for item in selected]
    counts = split_counts(sample_count)
    plan: list[dict[str, Any]] = []
    pose_sequence = preview_pose_family_sequence(selected, sample_count, pose_policy)
    true_target = sample_count // 2
    true_counts = {split: count // 2 for split, count in counts.items()}
    remaining_true = true_target - sum(true_counts.values())
    for split in sorted(counts, key=lambda key: counts[key], reverse=True):
        if remaining_true <= 0:
            break
        capacity = counts[split] - true_counts[split]
        add = min(capacity, remaining_true)
        true_counts[split] += add
        remaining_true -= add
    sample_index = 0
    for split, count in counts.items():
        true_count = true_counts[split]
        false_count = count - true_count
        split_items: list[dict[str, Any]] = []
        for _ in range(true_count):
            split_items.append({"is_true": True, "missing_ids": [], "extra_ids": []})
        false_items: list[dict[str, Any]] = []
        for _ in range(false_count):
            missing_count = missing_count_for_false_sample(len(selected_ids), rng)
            missing_ids = [str(item) for item in rng.choice(selected_ids, size=missing_count, replace=False).tolist()]
            false_items.append({"is_true": False, "missing_ids": missing_ids, "extra_ids": []})
        split_items.extend(false_items)
        rng.shuffle(split_items)
        for item in split_items:
            present_ids = [item_id for item_id in selected_ids if item_id not in set(item["missing_ids"])]
            present_ids.extend(item.get("extra_ids") or [])
            plan.append(
                {
                    "index": sample_index,
                    "split": split,
                    "is_true": bool(item["is_true"]),
                    "required_accessory_ids": selected_ids,
                    "present_accessory_ids": present_ids,
                    "missing_accessory_ids": item["missing_ids"],
                    "extra_accessory_ids": item.get("extra_ids") or [],
                    "missing_count": len(item["missing_ids"]),
                    "extra_count": len(item.get("extra_ids") or []),
                    "false_reason": (
                        "extra_one_accessory"
                        if item.get("extra_ids")
                        else ("missing_accessory" if item.get("missing_ids") else None)
                    ),
                    "pose_family_policy": pose_sequence[sample_index] if sample_index < len(pose_sequence) else None,
                }
            )
            sample_index += 1
    missing_one_indexes = [
        idx
        for idx, item in enumerate(plan)
        if not item.get("is_true") and len(item.get("missing_accessory_ids") or []) == 1 and not item.get("extra_accessory_ids")
    ]
    extra_target = int(math.floor(len(missing_one_indexes) * 0.10 + 0.5))
    if extra_target > 0:
        for idx in rng.choice(missing_one_indexes, size=extra_target, replace=False).tolist():
            missing_id = str(plan[idx]["missing_accessory_ids"][0])
            present_ids = list(plan[idx]["required_accessory_ids"])
            present_ids.append(missing_id)
            plan[idx]["present_accessory_ids"] = present_ids
            plan[idx]["missing_accessory_ids"] = []
            plan[idx]["extra_accessory_ids"] = [missing_id]
            plan[idx]["missing_count"] = 0
            plan[idx]["extra_count"] = 1
            plan[idx]["false_reason"] = "extra_one_accessory"
    return plan


def public_training_output_url(path: Path) -> str:
    if str(path).startswith(str(OUTPUT_DIR)):
        return public_output_url(path)
    return ""


def write_training_annotation_preview(image_path: Path, labels: list[dict[str, Any]], out_path: Path) -> str:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        return ""
    palette = [(0, 210, 60), (45, 125, 255), (250, 170, 35), (210, 65, 210), (60, 220, 220)]
    for idx, label in enumerate(labels):
        polygons = label.get("visible_polygons_xy") or [label.get("visible_polygon_xy") or label.get("placement_polygon_xy") or []]
        valid_polygons = [np.array(polygon, dtype=np.int32) for polygon in polygons if polygon and len(polygon) >= 3]
        if not valid_polygons:
            continue
        color = palette[idx % len(palette)]
        cv2.polylines(image, valid_polygons, True, color, 3)
        all_points = np.concatenate(valid_polygons, axis=0)
        x = int(np.min(all_points[:, 0]))
        y = max(24, int(np.min(all_points[:, 1])) - 8)
        cv2.putText(image, str(label.get("name") or label.get("id") or "part"), (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    return public_training_output_url(out_path)


def generate_training_dataset(task: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    selected = selected_accessories(config, list(task.get("selected_accessory_ids") or []))
    sample_count = max(1, min(20000, int(task.get("sample_count") or 100)))
    pose_policy = normalize_preview_pose_family_policy(task.get("preview_pose_family_policy") or "auto")
    background_set_id = selected_background_set_id(task.get("background_set_id"))
    seed_base = int(task.get("seed") or time.time() * 1000)
    sample_plan = build_training_sample_plan(selected, sample_count, seed_base, pose_policy)
    dataset_dir = OUTPUT_DIR / "training_datasets" / str(task["job_id"])
    class_names = [str(item.get("name") or item.get("id") or f"class_{idx}") for idx, item in enumerate(selected)]
    class_index = {str(item.get("id")): idx for idx, item in enumerate(selected)}
    for split in ("train", "val", "test"):
        (dataset_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (dataset_dir / "labels" / split).mkdir(parents=True, exist_ok=True)
    preview_dir = dataset_dir / "previews"
    samples = []
    for plan_item in sample_plan:
        idx = int(plan_item["index"])
        split = str(plan_item["split"])
        selected_by_id = {str(item.get("id")): item for item in selected}
        render_selected = [selected_by_id[item_id] for item_id in plan_item["present_accessory_ids"] if item_id in selected_by_id]
        image_path = dataset_dir / "images" / split / f"sample_{idx + 1:06d}.png"
        rendered = draw_training_preview(
            render_selected,
            image_path,
            seed=seed_base + idx,
            pose_family_policy=plan_item.get("pose_family_policy"),
            split=split,
            background_set_id=background_set_id,
        )
        label_path = dataset_dir / "labels" / split / f"sample_{idx + 1:06d}.txt"
        lines = []
        for label in rendered.get("labels", []):
            polygons = label.get("visible_polygons_xy") or [label.get("visible_polygon_xy") or label.get("placement_polygon_xy") or []]
            for polygon in polygons:
                line = yolo_label_line(class_index.get(str(label.get("id") or ""), 0), polygon or [])
                if line:
                    lines.append(line)
        label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        annotated_path = preview_dir / split / f"sample_{idx + 1:06d}_boxed.jpg"
        annotated_url = write_training_annotation_preview(image_path, rendered.get("labels", []), annotated_path)
        samples.append(
            {
                "image": str(image_path),
                "labels": str(label_path),
                "url": rendered.get("url"),
                "annotated_url": annotated_url,
                "split": split,
                "is_true": plan_item["is_true"],
                "pass_fail_rule": "exact_count_match_required",
                "required_accessory_ids": plan_item["required_accessory_ids"],
                "present_accessory_ids": plan_item["present_accessory_ids"],
                "missing_accessory_ids": plan_item["missing_accessory_ids"],
                "extra_accessory_ids": plan_item.get("extra_accessory_ids") or [],
                "missing_count": plan_item["missing_count"],
                "extra_count": plan_item.get("extra_count") or 0,
                "false_reason": plan_item.get("false_reason"),
                "background_id": (rendered.get("background") or {}).get("background_id"),
                "background_set_id": (rendered.get("background") or {}).get("background_set_id") or background_set_id,
                "background_source": (rendered.get("background") or {}).get("background_source"),
                "background": rendered.get("background") or {},
            }
        )
        if idx == 0 or (idx + 1) % max(1, sample_count // 40) == 0 or idx + 1 == sample_count:
            update_training_task(
                str(task["job_id"]),
                status="running",
                progress=min(72, 8 + int(((idx + 1) / sample_count) * 64)),
                completed_samples=idx + 1,
                note=f"正在生成训练样本：{idx + 1}/{sample_count}",
            )
    yaml_path = dataset_dir / "dataset.yaml"
    write_dataset_yaml(yaml_path, dataset_dir, class_names)
    manifest = {
        "id": task["job_id"],
        "task_id": task["job_id"],
        "created_at": int(time.time()),
        "mode": task.get("mode"),
        "model_variant": task.get("mode") or "yolo",
        "background_set_id": background_set_id,
        "sample_count": sample_count,
        "selected_accessory_ids": [item.get("id") for item in selected],
        "required_accessory_counts": {str(item.get("id")): 1 for item in selected},
        "accessory_class_map": {str(idx): str(item.get("id")) for idx, item in enumerate(selected)},
        "class_accessory_map": {str(item.get("id")): idx for idx, item in enumerate(selected)},
        "ocr_accessory_ids": [str(item.get("id")) for item in selected if accessory_material_type(item) == "text"],
        "class_names": class_names,
        "dataset_yaml": str(yaml_path),
        "pass_fail_rule": "exact_count_match_required",
        "split_counts": Counter(sample["split"] for sample in samples),
        "true_count": sum(1 for sample in samples if sample.get("is_true")),
        "false_count": sum(1 for sample in samples if not sample.get("is_true")),
        "false_missing_count_distribution": Counter(str(sample.get("missing_count") or 0) for sample in samples if not sample.get("is_true")),
        "false_extra_count_distribution": Counter(str(sample.get("extra_count") or 0) for sample in samples if not sample.get("is_true")),
        "false_reason_distribution": Counter(str(sample.get("false_reason") or "none") for sample in samples if not sample.get("is_true")),
        "background_set_id_distribution": Counter(str(sample.get("background_set_id") or "unknown") for sample in samples),
        "background_id_distribution": Counter(str(sample.get("background_id") or "unknown") for sample in samples),
        "background_source_distribution": Counter(str(sample.get("background_source") or "unknown") for sample in samples),
        "sample_generation_policy": {
            "true_false_ratio": "1:1 per split when possible",
            "split_ratio": "train/val/test ~= 80/10/10",
            "false_class_missing_distribution": "missing_one remains the dominant false class; 10% of missing-one cases are replaced by extra_one_accessory",
            "false_class_extra_distribution": "extra_one_accessory ~= 10% of the missing-one false bucket",
            "pass_fail_rule": "exact_count_match_required; extra objects are false; true samples contain exact required counts for every task class",
            "background_policy": "random same-environment background library item per sample with crop/shift, brightness, contrast, mild blur/noise, and texture variation; glare ellipse disabled",
            "background_split_policy": "train/val/test use separate background pools when at least two same-environment assets are available; otherwise per-sample augmentations prevent exact duplicates",
            "training_images_are_clean": True,
            "annotated_previews": True,
            "label_shape": "visible_object_mask_polygon",
            "occlusion_policy": "later pasted objects subtract from earlier visible masks; each physical object keeps one primary visible contour label",
            "rotation_policy": "objects use continuous random planar rotation sampled uniformly from -180 to 180 degrees; not limited to cardinal angles",
            "format_reference": "Ultralytics YOLO segmentation dataset.yaml with train/val/test and per-image polygon txt labels",
        },
        "samples": samples,
    }
    manifest_path = dataset_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"dataset_dir": str(dataset_dir), "dataset_yaml": str(yaml_path), "manifest_path": str(manifest_path)}


def run_training_task(job_id: str) -> None:
    task = load_training_task(training_task_path(job_id))
    if not task:
        return
    try:
        update_training_task(job_id, status="running", progress=5, started_at=int(time.time()), note="任务已启动。")
        if task.get("dataset_yaml") and Path(str(task.get("dataset_yaml"))).exists():
            dataset = {
                "dataset_dir": str(task.get("dataset_dir") or Path(str(task["dataset_yaml"])).parent),
                "dataset_yaml": str(task["dataset_yaml"]),
                "manifest_path": str(task.get("manifest_path") or ""),
            }
            update_training_task(job_id, status="running", progress=74, note="已选择样本集，正在启动 YOLO 训练。", **dataset)
        else:
            dataset = generate_training_dataset(task)
        if task.get("action") == "generate_samples":
            update_training_task(job_id, status="completed", progress=100, completed_at=int(time.time()), note="训练样本已生成完成。", **dataset)
            return
        update_training_task(job_id, status="running", progress=76, note="样本已生成，正在启动 YOLO 训练。", **dataset)
        run_dir = OUTPUT_DIR / "training_runs"
        model_path = str(MODEL_PATH if MODEL_PATH.exists() else REPO_MODEL_PATH)
        epochs = max(1, min(500, int(task.get("epochs") or 1)))
        image_size = max(320, min(1280, int(task.get("image_size") or 640)))
        command = [
            "yolo",
            "segment",
            "train",
            f"model={model_path}",
            f"data={dataset['dataset_yaml']}",
            f"imgsz={image_size}",
            f"epochs={epochs}",
            "batch=0.72",
            "device=0",
            "cache=ram",
            "workers=0",
            "amp=True",
            "patience=25",
            "optimizer=auto",
            "mosaic=0.0",
            "mixup=0.0",
            "copy_paste=0.0",
            f"project={run_dir}",
            f"name={job_id}",
            "exist_ok=True",
        ]
        log_path = TRAINING_TASKS_DIR / f"{job_id}.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(command, cwd=str(APP_DIR), stdout=log, stderr=subprocess.STDOUT, text=True)
            update_training_task(
                job_id,
                training_command=command,
                training_log_path=str(log_path),
                training_pid=process.pid,
                current_epoch=0,
                total_epochs=epochs,
                progress=82,
                note=f"YOLO 训练已启动：Epoch 0/{epochs}。",
            )
            last_epoch = 0
            while process.poll() is None:
                parsed_epoch = parse_yolo_epoch_progress(log_path, epochs)
                if parsed_epoch and parsed_epoch[0] != last_epoch:
                    last_epoch = parsed_epoch[0]
                    epoch_progress = min(98, 82 + int((last_epoch / max(1, epochs)) * 16))
                    update_training_task(
                        job_id,
                        status="running",
                        progress=epoch_progress,
                        current_epoch=last_epoch,
                        total_epochs=parsed_epoch[1],
                        note=f"YOLO 训练中：Epoch {last_epoch}/{parsed_epoch[1]}。",
                    )
                time.sleep(5)
            return_code = process.returncode
            parsed_epoch = parse_yolo_epoch_progress(log_path, epochs)
            if parsed_epoch:
                last_epoch = max(last_epoch, parsed_epoch[0])
        update_training_task(
            job_id,
            status="completed" if return_code == 0 else "failed",
            progress=100,
            completed_at=int(time.time()),
            return_code=return_code,
            current_epoch=epochs if return_code == 0 else last_epoch,
            total_epochs=epochs,
            training_run_dir=str(run_dir / job_id),
            note="模型训练已完成。" if return_code == 0 else "模型训练失败，请查看训练日志。",
        )
    except Exception as exc:
        update_training_task(job_id, status="failed", progress=100, completed_at=int(time.time()), error=str(exc), note=f"任务失败：{exc}")


def enqueue_training_task(
    request: TrainingStartRequest,
    selected: list[dict[str, Any]],
    action: str,
    dataset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sample_count = max(1, min(20000, int(dataset.get("sample_count") if dataset else request.sample_count)))
    epochs = max(1, min(500, int(request.epochs)))
    image_size = max(320, min(1280, int(request.image_size)))
    estimate = training_estimate(
        sample_count,
        include_training=action == "train_model",
        include_generation=action == "generate_samples" or (action == "train_model" and not dataset),
        epochs=epochs,
        image_size=image_size,
        selected_count=len(selected),
        train_mode=request.train_mode,
    )
    job_id = f"{'train' if action == 'train_model' else 'samples'}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    task = {
        "job_id": job_id,
        "task_id": job_id,
        "candidate_id": job_id,
        "candidate_name": "训练模型" if action == "train_model" else "生成训练样本",
        "label": "训练模型" if action == "train_model" else "生成训练样本",
        "queue_kind": "training",
        "action": action,
        "status": "queued",
        "progress": 0,
        "created_at": int(time.time()),
        "selected_accessory_ids": [item["id"] for item in selected],
        "required_accessory_counts": {str(item["id"]): 1 for item in selected},
        "accessory_class_map": {str(idx): str(item["id"]) for idx, item in enumerate(selected)},
        "class_accessory_map": {str(item["id"]): idx for idx, item in enumerate(selected)},
        "ocr_accessory_ids": [str(item["id"]) for item in selected if accessory_material_type(item) == "text"],
        "model_variant": request.train_mode,
        "sample_count": sample_count,
        "mode": request.train_mode,
        "epochs": epochs,
        "image_size": image_size,
        "background_set_id": selected_background_set_id(request.background_set_id),
        "approved_preview_id": request.approved_preview_id,
        "preview_pose_family_policy": "auto",
        "note": "任务已加入队列。",
        **estimate,
    }
    if dataset:
        task.update(
            {
                "source_dataset_id": dataset["id"],
                "dataset_dir": dataset["dataset_dir"],
                "dataset_yaml": dataset["dataset_yaml"],
                "manifest_path": dataset["manifest_path"],
                "label": dataset.get("display_name") or task["label"],
                "candidate_name": dataset.get("display_name") or task["candidate_name"],
            }
        )
    save_training_task(task)
    thread = threading.Thread(target=run_training_task, args=(job_id,), name=f"training-task-{job_id}", daemon=True)
    _training_task_threads[job_id] = thread
    thread.start()
    return public_training_task(task)


def list_trained_model_specs() -> list[dict[str, Any]]:
    models = []
    runs_dir = OUTPUT_DIR / "training_runs"
    if not runs_dir.exists():
        return models
    config = load_config()
    accessories_by_id = {
        str(item.get("id") or accessory_uid(item)): serialize_accessory(item)
        for item in config.get("accessories", [])
    }
    for run_dir in sorted([p for p in runs_dir.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True):
        weights = run_dir / "weights" / "best.pt"
        meta_path = run_dir / "library_metadata.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        except json.JSONDecodeError:
            meta = {}
        task = load_training_task(training_task_path(run_dir.name)) or {}
        manifest_path = OUTPUT_DIR / "training_datasets" / run_dir.name / "manifest.json"
        if task.get("manifest_path"):
            manifest_path = Path(str(task["manifest_path"]))
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        except json.JSONDecodeError:
            manifest = {}
        if task.get("action") != "train_model":
            continue
        raw_class_names = [str(name or f"class_{idx}") for idx, name in enumerate(manifest.get("class_names") or ["accessory"])]
        variant = str(task.get("model_variant") or task.get("mode") or manifest.get("model_variant") or manifest.get("mode") or "yolo")
        uses_ocr = variant == "yolo_ocr"
        selected_accessory_ids = list(task.get("selected_accessory_ids") or manifest.get("selected_accessory_ids") or [])
        required_accessory_counts = {
            str(k): max(0, int(v))
            for k, v in (task.get("required_accessory_counts") or manifest.get("required_accessory_counts") or {}).items()
        }
        if not required_accessory_counts:
            required_accessory_counts = {str(item_id): 1 for item_id in selected_accessory_ids}
        accessory_class_map = {
            int(k): str(v)
            for k, v in (task.get("accessory_class_map") or manifest.get("accessory_class_map") or {}).items()
            if str(k).lstrip("-").isdigit()
        }
        if not accessory_class_map:
            accessory_class_map = {idx: str(item_id) for idx, item_id in enumerate(selected_accessory_ids)}
        accessory_names = [
            str((accessories_by_id.get(str(item_id)) or {}).get("name") or (accessories_by_id.get(str(item_id)) or {}).get("label") or item_id)
            for item_id in selected_accessory_ids
        ]
        if len(accessory_names) != len(raw_class_names):
            accessory_names = raw_class_names
        class_names = {idx: accessory_names[idx] if idx < len(accessory_names) else raw_class_names[idx] for idx in range(len(raw_class_names))}
        accessory_labels = {
            str(accessory_id): class_names.get(model_cls_id, str(accessory_id))
            for model_cls_id, accessory_id in accessory_class_map.items()
        }
        ocr_accessory_ids = {
            str(item_id)
            for item_id in (task.get("ocr_accessory_ids") or manifest.get("ocr_accessory_ids") or [])
        }
        if uses_ocr and not ocr_accessory_ids:
            ocr_accessory_ids = {
                str(item_id)
                for item_id in selected_accessory_ids
                if accessory_material_type(accessories_by_id.get(str(item_id), {})) == "text"
            }
        ocr_model_class_ids = sorted(
            model_cls_id for model_cls_id, accessory_id in accessory_class_map.items() if str(accessory_id) in ocr_accessory_ids
        )
        models.append(
            {
                "id": f"trained_{run_dir.name}__{variant}",
                "run_id": run_dir.name,
                "task_id": str(task.get("task_id") or manifest.get("task_id") or run_dir.name),
                "variant": variant,
                "label": meta.get("display_name") or f"{run_dir.name} · {variant.upper()}",
                "description": "由训练库生成的任务模型。",
                "note": meta.get("note") or "",
                "path": weights,
                "artifact_path": str(weights),
                "metadata_path": str(manifest_path),
                "uses_ocr": uses_ocr,
                "is_specialized": True,
                "selected_accessory_ids": selected_accessory_ids,
                "required_accessory_counts": required_accessory_counts,
                "accessory_class_map": {str(k): v for k, v in accessory_class_map.items()},
                "class_accessory_map": {v: k for k, v in accessory_class_map.items()},
                "ocr_accessory_ids": sorted(ocr_accessory_ids),
                "ocr_model_class_ids": ocr_model_class_ids,
                "accessory_names": accessory_names,
                "accessory_labels": accessory_labels,
                "model_class_names": class_names,
                "model_to_business_class": {idx: idx for idx in class_names},
                "model_to_accessory_id": accessory_class_map,
                "rule_required_accessory_ids": list(required_accessory_counts.keys()),
                "rule_required_classes": list(class_names.keys()),
                "rule_min_counts": {str(idx): 1 for idx in class_names},
                "rule_class_labels": class_names,
            }
        )
    return models


def selected_model_spec(model_id: str | None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    requested = model_id or (config or {}).get("active_model_id") or DEFAULT_MODEL_ID
    for spec in list_trained_model_specs():
        if spec["id"] == requested:
            return spec
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


def attach_ocr_results(
    image_bgr: np.ndarray,
    detections: list[dict[str, Any]],
    config: dict[str, Any],
    spec: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
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

    if not jobs:
        return detections

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
        if spec.get("is_specialized"):
            classification = ocr_result["classification"]
            job["det"]["ocr"] = {
                **classification,
                "best_rotation": ocr_result["rotation"],
                "orientation": job["orientation"],
                "fallback_used": ocr_result.get("fallback_used", False),
                "mean_text_score": ocr_result["mean_text_score"],
                "texts": ocr_result["texts"][:max_texts],
            }
            job["det"]["manual_type"] = classification["manual_type"]
            job["det"]["manual_label"] = classification["manual_label"]
        else:
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
    if spec.get("is_specialized"):
        name = str(spec.get("rule_class_labels", {}).get(business_cls_id) or spec.get("model_class_names", {}).get(business_cls_id, f"class_{business_cls_id}"))
        return name, name
    if spec.get("uses_ocr") and business_cls_id == 1:
        return GENERIC_DETECTION_CLASS_NAMES[1], GENERIC_DETECTION_LABELS[1]
    return CLASS_NAMES.get(business_cls_id, f"class_{business_cls_id}"), CLASS_LABELS.get(business_cls_id, f"Class {business_cls_id}")


def parse_detections(result: Any, spec: dict[str, Any]) -> list[dict[str, Any]]:
    detections = []
    image_shape = tuple(int(x) for x in result.orig_shape[:2])
    model_to_business = spec["model_to_business_class"]
    model_class_names = spec["model_class_names"]
    model_to_accessory_id = {int(k): str(v) for k, v in (spec.get("model_to_accessory_id") or {}).items()}
    if result.masks is not None and result.boxes is not None and len(result.boxes) > 0:
        classes = result.boxes.cls.cpu().numpy().astype(int)
        confidences = result.boxes.conf.cpu().numpy()
        polygons = result.masks.xy
        for model_cls_id, conf, polygon in zip(classes, confidences, polygons):
            business_cls_id = model_to_business.get(int(model_cls_id))
            if business_cls_id is None or len(polygon) < 3:
                continue
            accessory_id = model_to_accessory_id.get(int(model_cls_id))
            class_name, label = detection_names_for_business_class(business_cls_id, spec)
            detections.append(
                {
                    "class_id": business_cls_id,
                    "accessory_id": accessory_id,
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
        accessory_id = model_to_accessory_id.get(int(model_cls_id))
        class_name, label = detection_names_for_business_class(business_cls_id, spec)
        detections.append(
            {
                "class_id": business_cls_id,
                "accessory_id": accessory_id,
                "class_name": class_name,
                "label": label,
                "model_class_id": int(model_cls_id),
                "model_class_name": model_class_names.get(int(model_cls_id), f"class_{int(model_cls_id)}"),
                "confidence": round(float(conf), 4),
                "polygon": [[round(float(x), 2), round(float(y), 2)] for x, y in polygon],
            }
        )
    return postprocess_detections(detections, image_shape)


def apply_rule(detections: list[dict[str, Any]], config: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    threshold = float(config["confidence_threshold"])
    if spec.get("is_specialized"):
        required_accessory_counts = {
            str(k): max(0, int(v))
            for k, v in (spec.get("required_accessory_counts") or {}).items()
        }
        if not required_accessory_counts:
            required_accessory_counts = {str(item_id): 1 for item_id in spec.get("selected_accessory_ids") or []}
        required_keys = list(required_accessory_counts.keys())
        class_labels = {str(k): str(v) for k, v in (spec.get("accessory_labels") or {}).items()}
        rule_source = "task"
        rule_task_id = spec.get("task_id")
        rule_label = " + ".join(str(x) for x in spec.get("accessory_names") or []) or str(spec.get("label") or "")
    else:
        required_keys = [int(x) for x in config["required_classes"]]
        required_accessory_counts = {}
        min_counts = {int(k): int(v) for k, v in config["min_counts"].items()}
        class_labels = {int(k): str(v) for k, v in CLASS_LABELS.items()}
        rule_source = "global"
        rule_task_id = None
        rule_label = "通用规则"
    count_by_rule_key: Counter[Any] = Counter()
    max_conf_by_rule_key: defaultdict[Any, float] = defaultdict(float)
    for det in detections:
        conf = float(det["confidence"])
        if conf >= threshold:
            rule_key: Any = str(det.get("accessory_id")) if spec.get("is_specialized") else int(det["class_id"])
            if spec.get("is_specialized") and (not rule_key or rule_key == "None"):
                continue
            count_by_rule_key[rule_key] += 1
            max_conf_by_rule_key[rule_key] = max(max_conf_by_rule_key[rule_key], conf)

    missing = []
    present = []
    extra = []
    for rule_key in required_keys:
        need = required_accessory_counts.get(str(rule_key), min_counts.get(rule_key, 1) if not spec.get("is_specialized") else 1)
        found = count_by_rule_key.get(rule_key, 0)
        row = {
            "class_id": rule_key,
            "label": class_labels.get(rule_key, f"Class {rule_key}"),
            "required": need,
            "found": found,
            "max_confidence": round(max_conf_by_rule_key.get(rule_key, 0.0), 4),
        }
        if spec.get("is_specialized"):
            row["accessory_id"] = str(rule_key)
        if found == need:
            present.append(row)
        elif found > need:
            row["issue"] = "extra"
            extra.append(row)
            missing.append(row)
        else:
            row["issue"] = "missing"
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
    if not spec.get("is_specialized") and ocr_config.get("enabled", True) and ocr_config.get("require_manual_types", True):
        for manual_type in required_manual_types:
            row = {
                "manual_type": manual_type,
                "label": MANUAL_TYPE_LABELS.get(manual_type, manual_type),
                "required": 1,
                "found": manual_type_counts.get(manual_type, 0),
            }
            if row["found"] == 1:
                manual_type_present.append(row)
            else:
                row["issue"] = "extra" if row["found"] > 1 else "missing"
                manual_type_missing.append(row)

    passed = len(missing) == 0 and len(manual_type_missing) == 0
    return {
        "passed": passed,
        "threshold": threshold,
        "match_policy": "exact_count",
        "source": rule_source,
        "task_id": rule_task_id,
        "label": rule_label,
        "present": present,
        "missing": missing,
        "extra": extra,
        "counts": {class_labels.get(k, str(k)): v for k, v in sorted(count_by_rule_key.items(), key=lambda item: str(item[0]))},
        "ocr_enabled": bool(spec.get("uses_ocr", False) and ocr_config.get("enabled", True)),
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
    status = "TRUE: exact parts match" if rule["passed"] else "FALSE: count mismatch"
    cv2.putText(annotated, status, (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.82, (255, 255, 255), 2)
    return annotated


def analyze_bgr(image_bgr: np.ndarray, request_id: str, model_id: str | None = None) -> dict[str, Any]:
    config = load_config()
    spec = selected_model_spec(model_id, config)
    result = model(str(spec["id"]), config).predict(image_bgr, imgsz=int(config["image_size"]), device=0, verbose=False)[0]
    detections = parse_detections(result, spec)
    if spec.get("uses_ocr", False):
        detections = attach_ocr_results(image_bgr, detections, config, spec)
    rule = apply_rule(detections, config, spec)
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
    accessory_names_by_id = {
        str(item.get("id") or accessory_uid(item)): str(item.get("name") or item.get("label") or accessory_uid(item))
        for item in config.get("accessories", [])
    }
    training_tasks = list_training_tasks()

    def task_accessory_names(task: dict[str, Any]) -> list[str]:
        names = [accessory_names_by_id.get(str(item_id), str(item_id)) for item_id in task.get("selected_accessory_ids") or []]
        return [name for name in names if name]

    available_models = []
    for spec in legacy_model_specs():
        path = Path(spec["path"])
        available_models.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "description": spec["description"],
                "variant": spec.get("variant"),
                "uses_ocr": bool(spec.get("uses_ocr", False)),
                "is_legacy": bool(spec.get("is_legacy", False)),
                "path": str(path),
                "exists": path.exists(),
            }
        )
    specialized_models = [
        {
            "id": spec["id"],
            "run_id": spec["run_id"],
            "task_id": spec["task_id"],
            "variant": spec["variant"],
            "label": spec["label"],
            "description": spec["description"],
            "uses_ocr": bool(spec.get("uses_ocr", False)),
            "required_accessory_counts": spec.get("required_accessory_counts") or {},
            "accessory_class_map": spec.get("accessory_class_map") or {},
            "ocr_accessory_ids": spec.get("ocr_accessory_ids") or [],
            "artifact_path": str(spec.get("artifact_path") or spec["path"]),
            "metadata_path": str(spec.get("metadata_path") or ""),
            "path": str(spec["path"]),
            "exists": Path(spec["path"]).exists(),
            "accessory_names": spec.get("accessory_names") or [],
            "selected_accessory_ids": spec.get("selected_accessory_ids") or [],
        }
        for spec in list_trained_model_specs()
    ]
    task_labels = {
        str(task.get("job_id")): str(task.get("label") or task.get("candidate_name") or task.get("job_id"))
        for task in training_tasks
    }
    task_accessories = {
        str(task.get("job_id")): task_accessory_names(task)
        for task in training_tasks
    }
    specialized_model_tasks: dict[str, dict[str, Any]] = {}
    for spec in specialized_models:
        task_id = str(spec.get("task_id") or spec.get("run_id"))
        accessory_names = task_accessories.get(task_id) or spec.get("accessory_names") or []
        task = specialized_model_tasks.setdefault(
            task_id,
            {
                "task_id": task_id,
                "label": " + ".join(accessory_names) if accessory_names else task_labels.get(task_id, task_id),
                "accessory_names": accessory_names,
                "models": [],
            },
        )
        if accessory_names and not task.get("accessory_names"):
            task["accessory_names"] = accessory_names
            task["label"] = " + ".join(accessory_names)
        task["models"].append(spec)
    return {
        "service": "running",
        "model_exists": Path(active_spec["path"]).exists(),
        "model_path": str(active_spec["path"]),
        "active_model_id": active_spec["id"],
        "available_models": available_models,
        "specialized_models": specialized_models,
        "specialized_model_tasks": list(specialized_model_tasks.values()),
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
    return {"items": [serialize_accessory(item) for item in load_config()["accessories"]]}


@app.get("/api/accessories/{accessory_id}/detail")
def get_accessory_detail(accessory_id: str) -> dict[str, Any]:
    config = load_config()
    for item in config.get("accessories", []):
        if accessory_uid(item) == accessory_id:
            if accessory_material_type(item) != "text":
                sprites = clean_sprite_assets(item)
                if not sprites or not clean_sprites_policy_complete(item, sprites):
                    if preprocess_object_clean_sprites(item, allow_ai_cutout=True, force=bool(sprites)):
                        save_config(config)
            return accessory_detail_payload(item)
    raise HTTPException(status_code=404, detail="Accessory not found")


@app.get("/api/accessories/candidates/{candidate_id}")
def get_accessory_candidate(candidate_id: str) -> dict[str, Any]:
    path = ACCESSORY_CANDIDATES_DIR / f"{candidate_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Accessory candidate not found")
    with _candidate_store_lock:
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail="Accessory candidate metadata is unreadable") from exc
        changed = False
        changed = ensure_candidate_image_job_task_ids(candidate) or changed
        for job in candidate_image_jobs(candidate):
            changed = ensure_image_job_task_id(candidate, job) or changed
            refreshed = refresh_codex_image_job(job)
            store_candidate_image_job(candidate, refreshed)
            changed = True
            if refreshed.get("status") == "completed":
                preprocess_object_clean_sprites(candidate, allow_ai_cutout=True)
                changed = True
        if changed:
            save_accessory_candidate(path, candidate)
    return {"status": "candidate_ready", "candidate": candidate}


@app.get("/api/image-jobs")
def image_jobs() -> dict[str, Any]:
    jobs = list_training_tasks() + list_codex_image_jobs()
    active_statuses = {"queued_for_codex_image_worker", "queued", "running"}
    return {
        "items": jobs,
        "active": [job for job in jobs if job.get("status") in active_statuses],
        "completed": [job for job in jobs if job.get("status") == "completed"],
    }


@app.get("/api/image-jobs/{job_id}")
def image_job(job_id: str) -> dict[str, Any]:
    for job in list_training_tasks():
        if job.get("job_id") == job_id or job.get("task_id") == job_id:
            return job
    for job in list_codex_image_jobs():
        if job.get("job_id") == job_id or job.get("task_id") == job_id:
            return job
    raise HTTPException(status_code=404, detail="Image job not found")


@app.patch("/api/training/tasks/{job_id}")
def update_training_task_endpoint(job_id: str, request: TrainingTaskUpdateRequest) -> dict[str, Any]:
    path = training_task_path(job_id)
    task = load_training_task(path)
    if not task:
        raise HTTPException(status_code=404, detail="Training task not found")
    if request.label is not None:
        task["label"] = request.label.strip() or task.get("label") or "训练任务"
        task["candidate_name"] = task["label"]
    if request.note is not None:
        task["note"] = request.note.strip()
    task["updated_at"] = int(time.time())
    save_training_task(task)
    return public_training_task(task)


@app.delete("/api/training/tasks/{job_id}")
def delete_training_task_endpoint(job_id: str) -> dict[str, Any]:
    path = training_task_path(job_id)
    task = load_training_task(path)
    if not task:
        raise HTTPException(status_code=404, detail="Training task not found")
    pid = task.get("training_pid")
    if task.get("status") == "running" and pid:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except (OSError, ValueError):
            pass
    try:
        path.unlink()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete task: {exc}") from exc
    return {"status": "deleted", "job_id": job_id, "items": list_training_tasks()}


@app.post("/api/image-jobs/{job_id}/stop")
def stop_image_job(job_id: str) -> dict[str, Any]:
    return update_codex_image_job(job_id, "stop")


@app.delete("/api/image-jobs/{job_id}")
def delete_image_job(job_id: str) -> dict[str, Any]:
    return update_codex_image_job(job_id, "delete")


@app.post("/api/image-job-candidates/{candidate_id}/stop")
def stop_image_job_candidate(candidate_id: str) -> dict[str, Any]:
    return update_codex_image_candidate(candidate_id, "stop")


@app.delete("/api/image-job-candidates/{candidate_id}")
def delete_image_job_candidate(candidate_id: str) -> dict[str, Any]:
    return update_codex_image_candidate(candidate_id, "delete")


@app.post("/api/accessories")
async def add_accessory(
    name: str = Form(...),
    class_id: int = Form(-1),
    material_type: str = Form("object"),
    material_alpha_policy: str = Form(""),
    training_role: str = Form("detect_and_classify"),
    paper_preset: str = Form("A4"),
    paper_width_mm: str = Form(""),
    paper_height_mm: str = Form(""),
    object_length_mm: str = Form(""),
    object_width_mm: str = Form(""),
    object_height_mm: str = Form(""),
    files: list[UploadFile] = File(default=[]),
) -> dict[str, Any]:
    if material_type not in {"text", "object"}:
        raise HTTPException(status_code=400, detail="material_type must be text or object")
    alpha_policy = normalize_object_alpha_material_policy(material_alpha_policy) if material_type == "object" else None
    if material_type == "object" and not alpha_policy:
        raise HTTPException(status_code=400, detail="请选择物品透明或不透明")
    config = load_config()
    if class_id < 0:
        existing_ids = [int(item.get("class_id", -1)) for item in config.get("accessories", [])]
        class_id = max(existing_ids + list(CLASS_NAMES.keys())) + 1
    saved_files = []
    accessory_id = f"acc_{uuid.uuid4().hex[:10]}"
    target_dir = UPLOAD_DIR / "accessories" / accessory_id
    target_dir.mkdir(parents=True, exist_ok=True)
    for upload in files:
        path = target_dir / safe_name(upload.filename)
        with path.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        saved_files.append(str(path))

    item = {
        "id": accessory_id,
        "class_id": class_id,
        "name": name,
        "material_type": material_type,
        "training_role": training_role,
        "physical_size": physical_size_payload(
            material_type,
            paper_preset,
            paper_width_mm,
            paper_height_mm,
            object_length_mm,
            object_width_mm,
            object_height_mm,
        ),
        "status": "reference_uploaded",
        "source_files": saved_files,
        "created_at": int(time.time()),
    }
    if alpha_policy:
        item["material_alpha_policy"] = alpha_policy
        item["object_alpha_policy_label"] = object_alpha_policy_label(alpha_policy)
    normalized = normalize_accessory_assets(item)
    item.update(normalized)
    config["accessories"].append(item)
    save_config(config)
    return {"status": "saved", "item": serialize_accessory(config["accessories"][-1])}


@app.post("/api/accessories/preview")
async def preview_accessory(
    name: str = Form(...),
    material_type: str = Form("object"),
    material_alpha_policy: str = Form(""),
    training_role: str = Form("detect_and_classify"),
    paper_preset: str = Form("A4"),
    paper_width_mm: str = Form(""),
    paper_height_mm: str = Form(""),
    object_length_mm: str = Form(""),
    object_width_mm: str = Form(""),
    object_height_mm: str = Form(""),
    files: list[UploadFile] = File(default=[]),
) -> dict[str, Any]:
    if material_type not in {"text", "object"}:
        raise HTTPException(status_code=400, detail="material_type must be text or object")
    alpha_policy = normalize_object_alpha_material_policy(material_alpha_policy) if material_type == "object" else None
    if material_type == "object" and not alpha_policy:
        raise HTTPException(status_code=400, detail="请选择物品透明或不透明")
    candidate_source_dir = UPLOAD_DIR / "accessory_candidates" / f"src_{uuid.uuid4().hex[:10]}"
    candidate_source_dir.mkdir(parents=True, exist_ok=True)
    saved_files = []
    for upload in files:
        path = candidate_source_dir / safe_name(upload.filename)
        with path.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        saved_files.append(str(path))
    physical_size = physical_size_payload(
        material_type,
        paper_preset,
        paper_width_mm,
        paper_height_mm,
        object_length_mm,
        object_width_mm,
        object_height_mm,
    )
    candidate = create_accessory_candidate(name, material_type, training_role, saved_files, physical_size, alpha_policy)
    if candidate.get("codex_image_job"):
        start_image_worker()
    return {"status": "candidate_ready", "candidate": candidate}


@app.post("/api/accessories/confirm/{candidate_id}")
def confirm_accessory(candidate_id: str) -> dict[str, Any]:
    path = ACCESSORY_CANDIDATES_DIR / f"{candidate_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Accessory candidate not found")
    with _candidate_store_lock:
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail="Accessory candidate metadata is unreadable") from exc
        if accessory_material_type(candidate) == "object" and not normalize_object_alpha_material_policy(candidate.get("material_alpha_policy")):
            raise HTTPException(status_code=400, detail="确认前必须选择物品透明或不透明")
        if accessory_material_type(candidate) == "object":
            candidate["material_alpha_policy"] = object_alpha_material_policy(candidate)
            candidate["object_alpha_policy_label"] = object_alpha_policy_label(candidate["material_alpha_policy"])
        if ensure_candidate_image_job_task_ids(candidate):
            save_accessory_candidate(path, candidate)
        refreshed_jobs = []
        changed = False
        for job in candidate_image_jobs(candidate):
            refreshed = refresh_codex_image_job(job)
            store_candidate_image_job(candidate, refreshed)
            refreshed_jobs.append(refreshed)
            changed = changed or refreshed.get("status") != job.get("status") or refreshed.get("completed_at") != job.get("completed_at")
        if changed:
            save_accessory_candidate(path, candidate)
        if any(str(job.get("status", "")) in {"queued_for_codex_image_worker", "queued", "running"} for job in refreshed_jobs):
            raise HTTPException(status_code=409, detail="Image generation is still running. Confirm after all pose jobs complete.")

        preprocess_object_clean_sprites(candidate, allow_ai_cutout=True, force=True)
        sprites = clean_sprite_assets(candidate)
        expected_count = int(candidate.get("clean_sprite_expected_count") or 0)
        actual_count = int(candidate.get("clean_sprite_count") or 0)
        metadata_complete = clean_sprites_policy_complete(candidate, sprites)
        extraction_incomplete = (
            bool(expected_count and actual_count < expected_count)
            or bool(candidate.get("clean_sprite_failed_cells"))
            or bool(expected_count and len(sprites) < expected_count)
            or not metadata_complete
        )
        if extraction_incomplete:
            candidate["id"] = candidate_id
            candidate["status"] = "candidate_review"
            candidate["clean_sprite_status"] = "incomplete"
            save_accessory_candidate(path, candidate)
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "多角度素材切分未完成",
                    "saved_count": actual_count,
                    "expected_count": expected_count,
                    "failed_cells": candidate.get("clean_sprite_failed_cells") or [],
                    "metadata_complete": metadata_complete,
                },
            )

        config = load_config()
        existing_ids = [int(item.get("class_id", -1)) for item in config.get("accessories", [])]
        candidate["class_id"] = max(existing_ids + list(CLASS_NAMES.keys())) + 1
        candidate["id"] = f"acc_{uuid.uuid4().hex[:10]}"
        candidate["status"] = candidate.get("status", "candidate_review").replace("candidate_review", "active")
        candidate["confirmed_at"] = int(time.time())
        config["accessories"].append(candidate)
        save_config(config)
        return {"status": "saved", "item": serialize_accessory(candidate), "items": [serialize_accessory(item) for item in config["accessories"]]}


@app.delete("/api/accessories/{accessory_id}")
def delete_accessory(accessory_id: str) -> dict[str, Any]:
    config = load_config()
    before = len(config.get("accessories", []))
    config["accessories"] = [item for item in config.get("accessories", []) if accessory_uid(item) != accessory_id]
    if len(config["accessories"]) == before:
        raise HTTPException(status_code=404, detail="Accessory not found")
    selected = config.get("training", {}).get("selected_accessory_ids", [])
    config["training"]["selected_accessory_ids"] = [item_id for item_id in selected if item_id != accessory_id]
    save_config(config)
    return {"status": "deleted", "accessory_id": accessory_id, "items": [serialize_accessory(item) for item in config["accessories"]]}


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


@app.get("/api/backgrounds/{set_id}/{image_name}")
def background_image(set_id: str, image_name: str) -> FileResponse:
    clean_id = safe_background_set_id(set_id)
    clean_name = Path(image_name).name
    path = BACKGROUND_SETS_DIR / clean_id / clean_name
    if not path.exists() or path.suffix.lower() not in IMAGE_REFERENCE_SUFFIXES:
        raise HTTPException(status_code=404, detail="Background image not found")
    return FileResponse(path)


@app.get("/api/training/background-sets")
def training_background_sets() -> dict[str, Any]:
    sets = list_background_sets()
    manifest = load_background_sets_manifest()
    default_id = selected_background_set_id(manifest.get("default_set_id") or None)
    return {"background_sets": sets, "default_set_id": default_id}


@app.post("/api/training/background-sets")
async def upload_training_background_set(
    name: str = Form(""),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in IMAGE_REFERENCE_SUFFIXES:
        raise HTTPException(status_code=400, detail="Only image background files are supported")
    display_name = name.strip() or Path(file.filename or "background").stem
    set_id = unique_background_set_id(display_name)
    set_dir = BACKGROUND_SETS_DIR / set_id
    set_dir.mkdir(parents=True, exist_ok=True)
    source_path = set_dir / f"source{suffix or '.png'}"
    with source_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    meta = update_background_set_manifest(
        set_id,
        id=set_id,
        name=display_name,
        description="用户上传背景生成的同环境背景集",
        source=str(source_path),
        created_at=int(time.time()),
        generation_method="queued_codexcli_imgworker",
        status="queued",
    )
    task = enqueue_background_set_task(set_id, display_name, source_path)
    return {
        "status": "queued",
        "task": task,
        "task_id": task["job_id"],
        "background_set": background_set_payload(set_id, meta),
        **training_background_sets(),
    }


@app.post("/api/training/start")
def request_training(request: TrainingStartRequest) -> dict[str, Any]:
    config = load_config()
    dataset = None
    if request.dataset_id:
        dataset = dataset_for_training(request.dataset_id)
        selected = selected_accessories(config, dataset.get("selected_accessory_ids") or request.selected_accessory_ids)
    else:
        selected = selected_accessories(config, request.selected_accessory_ids)
        validate_approved_preview(config, request, selected)
    task = enqueue_training_task(request, selected, "train_model", dataset=dataset)
    config["training"] = {
        "status": "queued",
        "last_requested_at": int(time.time()),
        "selected_accessory_ids": [item["id"] for item in selected],
        "sample_count": task["sample_count"],
        "mode": request.train_mode,
        "epochs": task["epochs"],
        "image_size": task["image_size"],
        "background_set_id": task.get("background_set_id"),
        "approved_preview_id": request.approved_preview_id,
        "active_training_task_id": task["job_id"],
        "note": task["note"],
        "estimated_minutes": task["estimated_minutes"],
    }
    save_config(config)
    return task


@app.post("/api/training/generate")
def request_sample_generation(request: TrainingStartRequest) -> dict[str, Any]:
    config = load_config()
    selected = selected_accessories(config, request.selected_accessory_ids)
    validate_approved_preview(config, request, selected)
    task = enqueue_training_task(request, selected, "generate_samples")
    config["training"] = {
        "status": "queued",
        "last_requested_at": int(time.time()),
        "selected_accessory_ids": [item["id"] for item in selected],
        "sample_count": task["sample_count"],
        "mode": request.train_mode,
        "background_set_id": task.get("background_set_id"),
        "approved_preview_id": request.approved_preview_id,
        "preview_urls": [],
        "previews": [],
        "preview_cache_key": None,
        "preview_sprite_versions": {},
        "render_policy": {
            "background_physical_size": BACKGROUND_SIZE_MM,
            "physical_size_rule": "Object samples use clean alpha sprites scaled by physical_size; document samples paste the saved rectified full document directly at paper physical_size.",
            "pose_collection_rule": "Pose Collection provides pose only; physical_size is applied only during preview and dataset rendering.",
        },
        "active_training_task_id": task["job_id"],
        "note": task["note"],
        "estimated_minutes": task["estimated_minutes"],
        "estimated_gb": task["estimated_gb"],
    }
    save_config(config)
    return task


def dataset_for_training(dataset_id: str) -> dict[str, Any]:
    dataset_dir = OUTPUT_DIR / "training_datasets" / re.sub(r"[^a-zA-Z0-9_.-]+", "_", dataset_id)
    manifest_path = dataset_dir / "manifest.json"
    dataset_yaml = dataset_dir / "dataset.yaml"
    if not dataset_dir.exists() or not manifest_path.exists() or not dataset_yaml.exists():
        raise HTTPException(status_code=404, detail="Training dataset not found")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Training dataset manifest is unreadable") from exc
    samples = manifest.get("samples") if isinstance(manifest.get("samples"), list) else []
    sample_count = len(samples) or int(manifest.get("sample_count") or 0)
    if sample_count <= 0:
        raise HTTPException(status_code=409, detail="Training dataset has no samples")
    return {
        "id": dataset_dir.name,
        "dataset_dir": str(dataset_dir),
        "dataset_yaml": str(dataset_yaml),
        "manifest_path": str(manifest_path),
        "sample_count": sample_count,
        "selected_accessory_ids": manifest.get("selected_accessory_ids") or [],
        "background_set_id": manifest.get("background_set_id") or "",
        "display_name": manifest.get("display_name") or dataset_dir.name,
    }


@app.get("/api/training/status")
def training_status() -> dict[str, Any]:
    config = load_config()
    return filtered_training_state(config)


def validate_approved_preview(config: dict[str, Any], request: TrainingStartRequest, selected: list[dict[str, Any]]) -> None:
    if not request.approved_preview_id:
        return
    preview_path = TRAINING_JOBS_DIR / f"{request.approved_preview_id}.json"
    if not preview_path.exists():
        raise HTTPException(status_code=409, detail="Approved preview is no longer available. Generate a fresh preview.")
    try:
        preview = json.loads(preview_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=409, detail="Approved preview metadata is unreadable. Generate a fresh preview.") from exc

    selected_ids = [item["id"] for item in selected]
    preview_ids = [item.get("id") for item in preview.get("selected_accessories", []) if isinstance(item, dict)]
    if preview_ids != selected_ids:
        raise HTTPException(status_code=409, detail="Approved preview does not match the selected accessories.")
    requested_background_set_id = selected_background_set_id(request.background_set_id)
    if preview.get("background_set_id") != requested_background_set_id:
        raise HTTPException(status_code=409, detail="Approved preview does not match the selected background set. Generate a fresh preview.")

    current_cache_key = preview_cache_key(selected) if selected else None
    if preview.get("preview_cache_key") != current_cache_key:
        config["training"].update(
            {
                "preview_urls": [],
                "previews": [],
                "preview_stale_reason": "clean_sprite_version_changed",
                "current_preview_cache_key": current_cache_key,
            }
        )
        save_config(config)
        raise HTTPException(status_code=409, detail="Approved preview is stale. Generate a fresh preview.")


def filtered_training_state(config: dict[str, Any]) -> dict[str, Any]:
    training = config["training"]
    selected = selected_accessories(config, training.get("selected_accessory_ids", []))
    current_cache_key = preview_cache_key(selected) if selected else None
    stale_reason = None
    if training_preview_metadata_missing(training, selected):
        stale_reason = "missing_preview_sprite_version"
    elif training.get("preview_cache_key") and current_cache_key and training.get("preview_cache_key") != current_cache_key:
        stale_reason = "clean_sprite_version_changed"
    if stale_reason:
        training = dict(training)
        training.update(
            {
                "preview_urls": [],
                "previews": [],
                "preview_stale_reason": stale_reason,
                "current_preview_cache_key": current_cache_key,
            }
        )
    return training


def dataset_resource_item(dataset_dir: Path) -> dict[str, Any] | None:
    manifest_path = dataset_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    samples = manifest.get("samples") if isinstance(manifest.get("samples"), list) else []
    return {
        "id": dataset_dir.name,
        "kind": "dataset",
        "display_name": manifest.get("display_name") or dataset_dir.name,
        "note": manifest.get("note") or "",
        "path": str(dataset_dir),
        "manifest_path": str(manifest_path),
        "sample_count": len(samples) or manifest.get("sample_count") or 0,
        "created_at": manifest.get("created_at") or int(dataset_dir.stat().st_mtime),
        "selected_accessory_ids": manifest.get("selected_accessory_ids") or [],
        "background_set_id": manifest.get("background_set_id") or "",
        "samples": samples,
    }


def training_resources_payload() -> dict[str, Any]:
    datasets_dir = OUTPUT_DIR / "training_datasets"
    datasets = []
    if datasets_dir.exists():
        for dataset_dir in sorted([p for p in datasets_dir.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True):
            item = dataset_resource_item(dataset_dir)
            if item:
                datasets.append(item)
    task_items = list_training_tasks()
    dataset_ids = {item["id"] for item in datasets}
    for task in task_items:
        dataset_dir_value = task.get("dataset_dir")
        if task.get("action") not in {"generate_samples", "train_model"} or not dataset_dir_value:
            continue
        dataset_id = Path(str(dataset_dir_value)).name
        if dataset_id in dataset_ids:
            continue
        datasets.append(
            {
                "id": dataset_id,
                "kind": "dataset",
                "display_name": task.get("label") or dataset_id,
                "note": "样本文件缺失或已被删除；这是任务记录中的历史资源。",
                "path": str(dataset_dir_value),
                "manifest_path": str(task.get("manifest_path") or ""),
                "sample_count": int(task.get("completed_samples") or task.get("sample_count") or 0),
                "created_at": int(task.get("created_at") or 0),
                "selected_accessory_ids": task.get("selected_accessory_ids") or [],
                "background_set_id": task.get("background_set_id") or "",
                "samples": [],
                "missing_files": True,
            }
        )
        dataset_ids.add(dataset_id)
    specs = list_trained_model_specs()
    models = []
    for spec in specs:
        model_path = Path(spec["path"])
        run_id = str(spec["run_id"])
        run_dir = OUTPUT_DIR / "training_runs" / run_id
        timestamp_path = model_path if model_path.exists() else run_dir
        models.append(
            {
                "id": spec["id"],
                "run_id": run_id,
                "task_id": spec["task_id"],
                "variant": spec["variant"],
                "kind": "model",
                "label": spec["label"],
                "note": spec.get("note") or "",
                "path": str(model_path),
                "exists": model_path.exists(),
                "uses_ocr": bool(spec.get("uses_ocr", False)),
                "created_at": int(timestamp_path.stat().st_mtime) if timestamp_path.exists() else 0,
                "accessory_names": spec.get("accessory_names") or [],
                "selected_accessory_ids": spec.get("selected_accessory_ids") or [],
            }
        )
    completed_tasks = []
    for task in list_training_tasks():
        if task.get("action") not in {"generate_samples", "train_model"}:
            continue
        task_id = str(task.get("job_id") or "")
        completed_tasks.append(
            {
                **task,
                "dataset": next((item for item in datasets if item["id"] == task_id), None),
                "models": [item for item in models if item.get("task_id") == task_id],
            }
        )
    return {"datasets": datasets, "models": models, "tasks": task_items, "training_tasks": completed_tasks}


@app.get("/api/training/resources")
def training_resources() -> dict[str, Any]:
    return training_resources_payload()


@app.delete("/api/training/resources/datasets/{dataset_id}")
def delete_training_dataset(dataset_id: str) -> dict[str, Any]:
    dataset_dir = OUTPUT_DIR / "training_datasets" / re.sub(r"[^a-zA-Z0-9_.-]+", "_", dataset_id)
    if not dataset_dir.exists() or not dataset_dir.is_dir():
        raise HTTPException(status_code=404, detail="Dataset not found")
    shutil.rmtree(dataset_dir)
    return {"status": "deleted", "dataset_id": dataset_id, **training_resources_payload()}


@app.patch("/api/training/resources/datasets/{dataset_id}")
def update_training_dataset(dataset_id: str, request: TrainingResourceUpdateRequest) -> dict[str, Any]:
    dataset_dir = OUTPUT_DIR / "training_datasets" / re.sub(r"[^a-zA-Z0-9_.-]+", "_", dataset_id)
    manifest_path = dataset_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Dataset manifest is unreadable") from exc
    if request.display_name is not None:
        manifest["display_name"] = request.display_name.strip() or dataset_id
    if request.note is not None:
        manifest["note"] = request.note.strip()
    manifest["updated_at"] = int(time.time())
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"status": "updated", "dataset_id": dataset_id, **training_resources_payload()}


@app.delete("/api/training/resources/datasets/{dataset_id}/samples/{sample_name}")
def delete_training_dataset_sample(dataset_id: str, sample_name: str) -> dict[str, Any]:
    dataset_dir = OUTPUT_DIR / "training_datasets" / re.sub(r"[^a-zA-Z0-9_.-]+", "_", dataset_id)
    if not dataset_dir.exists() or not dataset_dir.is_dir():
        raise HTTPException(status_code=404, detail="Dataset not found")
    sample_stem = Path(sample_name).stem
    removed = 0
    for split in ("train", "val", "test"):
        for path in (
            dataset_dir / "images" / split / f"{sample_stem}.png",
            dataset_dir / "labels" / split / f"{sample_stem}.txt",
            dataset_dir / "previews" / split / f"{sample_stem}_boxed.jpg",
        ):
            if path.exists():
                path.unlink()
                removed += 1
    manifest_path = dataset_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["samples"] = [
                item
                for item in manifest.get("samples", [])
                if Path(str(item.get("image") or "")).stem != sample_stem
            ]
            manifest["sample_count"] = len(manifest["samples"])
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass
    if removed == 0:
        raise HTTPException(status_code=404, detail="Sample not found")
    return {"status": "deleted", "dataset_id": dataset_id, "sample": sample_name, **training_resources_payload()}


@app.delete("/api/training/resources/models/{run_id}")
def delete_training_model(run_id: str) -> dict[str, Any]:
    clean_id = re.sub(r"^trained_", "", run_id)
    run_dir = OUTPUT_DIR / "training_runs" / re.sub(r"[^a-zA-Z0-9_.-]+", "_", clean_id)
    if not run_dir.exists() or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="Model run not found")
    shutil.rmtree(run_dir)
    return {"status": "deleted", "run_id": run_id, **training_resources_payload()}


@app.patch("/api/training/resources/models/{run_id}")
def update_training_model(run_id: str, request: TrainingResourceUpdateRequest) -> dict[str, Any]:
    clean_id = re.sub(r"^trained_", "", run_id)
    run_dir = OUTPUT_DIR / "training_runs" / re.sub(r"[^a-zA-Z0-9_.-]+", "_", clean_id)
    if not run_dir.exists() or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="Model run not found")
    meta_path = run_dir / "library_metadata.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    except json.JSONDecodeError:
        meta = {}
    if request.display_name is not None:
        meta["display_name"] = request.display_name.strip() or clean_id
    if request.note is not None:
        meta["note"] = request.note.strip()
    meta["updated_at"] = int(time.time())
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"status": "updated", "run_id": run_id, **training_resources_payload()}


@app.get("/api/training/plan")
def training_plan() -> dict[str, Any]:
    config = load_config()
    training = filtered_training_state(config)
    return {
        "training": training,
        "accessories": [serialize_accessory(item) for item in config.get("accessories", [])],
        "background_sets": list_background_sets(),
        "default_background_set_id": selected_background_set_id(training.get("background_set_id")),
        "render_policy": {
            "sample_count_default": 4000,
            "background": "same-environment background library with per-sample crop/shift/photometric/noise/texture variation; glare ellipse disabled",
            "background_physical_size": BACKGROUND_SIZE_MM,
            "physical_size_rule": "object foreground uses clean alpha sprite physical_size; document/text uses saved rectified image directly at paper physical_size",
            "rotation": "text_full_random; object_upright_random_rotation; object_lying_random_rotation_with_inverse_source_position",
            "z_order": "randomized_per_sample",
            "label_shape": "visible_polygon_for_occluded_regions",
            "true_rule": "exact_count_match_required",
            "false_rule": "mostly missing_one; 10% of missing_one false bucket becomes extra_one_accessory",
        },
    }


@app.post("/api/training/preview")
def training_preview(request: TrainingPreviewRequest) -> dict[str, Any]:
    config = load_config()
    if ensure_object_clean_sprites_for_selection(config, request.selected_accessory_ids):
        save_config(config)
    selected = selected_accessories(config, request.selected_accessory_ids)
    pose_policy = normalize_preview_pose_family_policy(request.preview_pose_family_policy)
    background_set_id = selected_background_set_id(request.background_set_id)
    sprite_versions = {
        accessory_uid(item): {
            "clean_sprite_preprocessed_at": item.get("clean_sprite_preprocessed_at"),
            "clean_sprite_count": item.get("clean_sprite_count") or len(clean_sprite_assets(item)),
            "clean_sprite_version": accessory_sprite_version(item),
        }
        for item in selected
        if accessory_material_type(item) == "object"
    }
    cache_key = preview_cache_key(selected)
    preview_id = f"preview_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    job_dir = OUTPUT_DIR / "training_previews" / preview_id
    job_dir.mkdir(parents=True, exist_ok=True)
    previews = []
    count = max(1, min(12, int(request.preview_count)))
    pose_sequence = preview_pose_family_sequence(selected, count, pose_policy)
    pose_sequence_label = preview_pose_family_sequence_label(pose_sequence)
    seed_base = int(time.time() * 1000)
    for idx in range(count):
        output_path = job_dir / f"sample_{idx + 1:02d}.png"
        preview = draw_training_preview(
            selected,
            output_path,
            seed=seed_base + idx,
            pose_family_policy=pose_sequence[idx],
            background_set_id=background_set_id,
        )
        if any(label.get("material_type") == "object" and label.get("source_fallback_error") for label in preview.get("labels", [])):
            raise HTTPException(status_code=409, detail="Clean sprite is unavailable. Regenerate clean sprites before preview.")
        previews.append(preview)
    plan = {
        "id": preview_id,
        "status": "preview_ready",
        "sample_count": max(1, min(20000, int(request.sample_count))),
        "train_mode": request.train_mode,
        "background_set_id": background_set_id,
        "selected_accessories": selected,
        "previews": previews,
        "preview_cache_key": cache_key,
        "preview_sprite_versions": sprite_versions,
        "preview_pose_family_sequence": pose_sequence,
        "preview_pose_family_policy": pose_policy,
        "preview_pose_family_label": pose_sequence_label,
        "pipeline": [
            "normalize_accessory_assets",
            "reuse_preprocessed_clean_object_alpha_sprites",
            "remember_physical_size_metadata",
            "generate_synthetic_combinations",
            "crop_object_foreground_only",
            "paste_saved_rectified_document_directly",
            "scale_by_physical_size",
            "place_on_background_using_background_mm_per_px",
            "apply_pose_aware_rotation_policy",
            "compute_visible_polygon_labels",
            "user_preview_approval",
            "start_yolo_or_yolo_ocr_training",
        ],
    }
    (TRAINING_JOBS_DIR / f"{preview_id}.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    config["training"].update(
        {
            "status": "preview_ready",
            "last_preview_id": preview_id,
            "selected_accessory_ids": [item["id"] for item in selected],
            "sample_count": plan["sample_count"],
            "mode": request.train_mode,
            "background_set_id": background_set_id,
            "preview_urls": [item["url"] for item in previews],
            "previews": previews,
            "preview_cache_key": cache_key,
            "preview_sprite_versions": sprite_versions,
            "preview_pose_family_policy": pose_policy,
            "preview_pose_family_label": pose_sequence_label,
            "preview_generated_at": int(time.time()),
        }
    )
    save_config(config)
    return plan


@app.on_event("startup")
def resume_image_worker_queue() -> None:
    if os.environ.get("LOCAL_INSPECTION_AUTO_RESUME_WORKER") == "1":
        start_image_worker()


ensure_dirs()
