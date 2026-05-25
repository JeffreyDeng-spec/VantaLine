import json
import os
import re
import signal
import shutil
import subprocess
import threading
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
NORMALIZED_DIR = DATA_DIR / "normalized_assets"
TRAINING_JOBS_DIR = DATA_DIR / "training_jobs"
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


for path in (UPLOAD_DIR, OUTPUT_DIR, DATA_DIR, NORMALIZED_DIR, TRAINING_JOBS_DIR, ACCESSORY_CANDIDATES_DIR, IMAGE_WORKER_LOG_DIR):
    path.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Assembly Line Local Inspection Service")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

_models: dict[str, YOLO] = {}
_ocr: Any | None = None
_rembg_session: Any | None = None
_image_worker_lock = threading.Lock()
_image_worker_thread: threading.Thread | None = None
_image_worker_processes: dict[str, subprocess.Popen] = {}

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


class TrainingStartRequest(BaseModel):
    selected_accessory_ids: list[str]
    sample_count: int = 4000
    train_mode: str = "yolo_ocr"
    approved_preview_id: str | None = None


STANDARD_PAPER_SIZES_MM = {
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "A6": (105.0, 148.0),
}

MM_TO_PREVIEW_PX = 1.43
# Default object size is calibrated to the real reference photo ratio:
# bottle long side ~= 0.55-0.60 of an A4 manual long side in the 1280x900 preview.
DEFAULT_OBJECT_SIZE_MM = {"length_mm": 170.0, "width_mm": 38.0, "height_mm": 38.0}
BACKGROUND_ROI_PX = (70, 100, 1210, 800)
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
        return {
            "kind": "paper",
            "preset": preset,
            "width_mm": optional_float(paper_width_mm) or default_w,
            "height_mm": optional_float(paper_height_mm) or default_h,
        }
    return {
        "kind": "object",
        "length_mm": optional_float(object_length_mm) or DEFAULT_OBJECT_SIZE_MM["length_mm"],
        "width_mm": optional_float(object_width_mm) or DEFAULT_OBJECT_SIZE_MM["width_mm"],
        "height_mm": optional_float(object_height_mm) or DEFAULT_OBJECT_SIZE_MM["height_mm"],
    }


def ensure_dirs() -> None:
    for path in (UPLOAD_DIR, OUTPUT_DIR, DATA_DIR, NORMALIZED_DIR, TRAINING_JOBS_DIR, ACCESSORY_CANDIDATES_DIR, IMAGE_WORKER_LOG_DIR):
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
    copy.setdefault("source_files", [])
    copy.setdefault("normalized_assets", [])
    copy.setdefault("training_role", "detect_and_classify")
    return copy


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


def normalize_text_image(src: Path, target_dir: Path) -> dict[str, Any] | None:
    image = cv2.imread(str(src))
    if image is None:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 160)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    warped = None
    method = "resize_fallback"
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(approx) == 4 and cv2.contourArea(approx) > image.shape[0] * image.shape[1] * 0.08:
            rect = order_points(approx)
            width_a = np.linalg.norm(rect[2] - rect[3])
            width_b = np.linalg.norm(rect[1] - rect[0])
            height_a = np.linalg.norm(rect[1] - rect[2])
            height_b = np.linalg.norm(rect[0] - rect[3])
            max_w = max(480, int(max(width_a, width_b)))
            max_h = max(640, int(max(height_a, height_b)))
            dst = np.array([[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]], dtype="float32")
            matrix = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(image, matrix, (max_w, max_h))
            method = "largest_quad_perspective"
            break
    if warped is None:
        h, w = image.shape[:2]
        scale = min(1200 / max(h, w), 1.0)
        warped = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    out = target_dir / f"{src.stem}_canonical.png"
    cv2.imwrite(str(out), warped)
    return {
        "kind": "canonical_text_image",
        "path": str(out),
        "method": method,
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


def load_preview_asset(item: dict[str, Any]) -> np.ndarray | None:
    for asset in item.get("normalized_assets", []):
        path = Path(str(asset.get("path", "")))
        if path.exists() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is not None:
                return image
    for path_str in item.get("source_files", []):
        path = Path(path_str)
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"} and path.exists():
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is not None:
                return image
    default_path = default_asset_for_accessory(item)
    if default_path and default_path.exists():
        return cv2.imread(str(default_path), cv2.IMREAD_COLOR)
    return None


def accessory_image_paths(item: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    job = item.get("codex_image_job") or {}
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
    if _rembg_session is not None:
        return _rembg_session
    try:
        from rembg import new_session

        _rembg_session = new_session("u2net")
        return _rembg_session
    except Exception:
        _rembg_session = None
        return None


def ai_background_cutout(image: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    session = rembg_session()
    if session is None:
        return None
    try:
        from PIL import Image
        from rembg import remove

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
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
        return crop_bgr, crop_alpha
    except Exception:
        return None


def green_screen_object_cutout(image: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray] | None:
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
        return object_cutout_from_image(image, rng)
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
    # Neutralize green-screen color inside transparent glass so the belt underneath shows through naturally.
    green_tint = (ch > 30) & (ch < 100) & (cs > 22)
    crop[green_tint & (alpha > 0)] = (
        crop[green_tint & (alpha > 0)].astype(np.float32) * 0.45
        + np.array([225, 232, 226], dtype=np.float32) * 0.55
    ).astype(np.uint8)
    return crop, alpha


def pose_collection_regions(image: np.ndarray) -> list[tuple[int, int, int, int]]:
    h, w = image.shape[:2]
    rel_regions = [
        (0.05, 0.03, 0.36, 0.23),
        (0.43, 0.02, 0.58, 0.35),
        (0.62, 0.06, 0.96, 0.25),
        (0.08, 0.30, 0.33, 0.62),
        (0.36, 0.32, 0.61, 0.68),
        (0.68, 0.32, 0.94, 0.66),
        (0.08, 0.58, 0.30, 0.96),
        (0.34, 0.72, 0.66, 0.94),
        (0.74, 0.58, 0.96, 0.96),
    ]
    regions = []
    for x1, y1, x2, y2 in rel_regions:
        regions.append((int(w * x1), int(h * y1), int(w * x2), int(h * y2)))
    return regions


def load_object_preview_sprite(item: dict[str, Any], rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray] | None:
    def usable_cutout(cutout: tuple[np.ndarray, np.ndarray] | None, source_shape: tuple[int, int, int]) -> tuple[np.ndarray, np.ndarray] | None:
        if not cutout:
            return None
        cut_asset, cut_mask = trim_masked_asset(cutout[0], cutout[1], pad=2)
        source_h, source_w = source_shape[:2]
        cut_h, cut_w = cut_asset.shape[:2]
        mask_fill = float((cut_mask > 8).sum()) / max(1, cut_mask.shape[0] * cut_mask.shape[1])
        # Reject loose matting that treats an entire pose-cell as foreground;
        # otherwise the bottle inside that cell remains visually tiny after scaling.
        if cut_w > source_w * 0.82 and cut_h > source_h * 0.82 and mask_fill > 0.72:
            return None
        return cut_asset, cut_mask

    job = item.get("codex_image_job") or {}
    pose_path = Path(str(job.get("output_path", "")))
    if pose_path.exists():
        pose = cv2.imread(str(pose_path), cv2.IMREAD_COLOR)
        if pose is not None:
            regions = pose_collection_regions(pose)
            pose_sprites: list[tuple[np.ndarray, np.ndarray]] = []
            for x1, y1, x2, y2 in regions:
                tile = pose[y1:y2, x1:x2].copy()
                ai_cutout = usable_cutout(ai_background_cutout(tile), tile.shape)
                if ai_cutout:
                    pose_sprites.append(ai_cutout)
            if pose_sprites:
                return pose_sprites[int(rng.integers(0, len(pose_sprites)))]
            for x1, y1, x2, y2 in regions:
                tile = pose[y1:y2, x1:x2].copy()
                cutout = usable_cutout(green_screen_object_cutout(tile, rng), tile.shape)
                if cutout:
                    pose_sprites.append(cutout)
            if pose_sprites:
                return pose_sprites[int(rng.integers(0, len(pose_sprites)))]
    for path in accessory_image_paths(item):
        if path == pose_path:
            continue
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            continue
        ai_cutout = ai_background_cutout(image)
        if ai_cutout:
            return ai_cutout
        cutout = object_cutout_from_image(image, rng)
        if cutout:
            return cutout
    image = load_preview_asset(item)
    if image is None:
        return None
    mask = np.full(image.shape[:2], 255, dtype=np.uint8)
    return image, mask


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
) -> np.ndarray:
    asset, mask = trim_masked_asset(asset, mask)
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
        return canvas
    roi = canvas[y1:y2, x1:x2]
    alpha = (rotated_mask[sy1:sy2, sx1:sx2].astype(float) / 255.0)[..., None]
    roi[:] = (rotated[sy1:sy2, sx1:sx2] * alpha + roi * (1 - alpha)).astype(np.uint8)
    return canvas


def paste_physical_object_asset(
    canvas: np.ndarray,
    asset: np.ndarray,
    mask: np.ndarray,
    center: tuple[int, int],
    target_long_side_px: int,
    target_short_side_px: int,
    angle: float,
) -> np.ndarray:
    asset, mask = trim_masked_asset(asset, mask)
    h, w = asset.shape[:2]
    long_side = max(w, h, 1)
    scale = target_long_side_px / long_side
    resized_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
    resized = cv2.resize(asset, resized_size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    resized_mask = cv2.resize(mask, resized_size, interpolation=cv2.INTER_LINEAR)
    return paste_masked_asset(canvas, resized, resized_mask, center, resized_size, angle)


def paste_rotated_asset(canvas: np.ndarray, asset: np.ndarray, center: tuple[int, int], target_size: tuple[int, int], angle: float) -> np.ndarray:
    asset = trim_rect_asset(asset)
    return paste_masked_asset(canvas, asset, physical_mask_for_rect_asset(asset), center, target_size, angle)


def normalize_accessory_assets(item: dict[str, Any]) -> dict[str, Any]:
    normalized_dir = NORMALIZED_DIR / accessory_uid(item)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    source_files = [Path(path) for path in item.get("source_files", [])]
    image_sources = [path for path in source_files if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}]
    material_type = item.get("material_type", "object")
    if material_type == "text":
        assets = []
        for src in image_sources[:4]:
            normalized = normalize_text_image(src, normalized_dir)
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
        "standing/lying poses when applicable, calibrated size variants, and transparent or neutral background."
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


def build_pose_collection_prompt(item: dict[str, Any]) -> str:
    return (
        f"Create one production-environment Pose Collection image for the accessory '{item.get('name', 'accessory')}' "
        "using the uploaded reference photo as the source of truth. Before generating, internally infer the object's "
        "3D spatial structure, stable support surfaces, center of mass, likely contact points, and how it can physically "
        "stand, lie down, lean, rotate, or rest on a production table. Show the same physical item from multiple natural "
        "top-down and slightly oblique overhead angles, including horizontal, diagonal, rotated, laid-down, upright, "
        "standing, and leaning poses when those states are physically plausible. If the reference photo only shows one "
        "state, still include other realistic physical states that the real object could take. Do not show impossible "
        "floating, unsupported, intersecting, or gravity-defying poses. Keep the item in a realistic assembly-line "
        "production context: neutral green conveyor or industrial work-surface lighting, natural contact shadows, "
        "subtle reflections, and believable scale. "
        "Preserve the material properties exactly, including transparency, gloss, metal, plastic, rubber, glass, labels, "
        "caps, seams, and surface texture. Do not redesign the object. Do not invent extra accessories. Do not add text "
        "labels, captions, arrows, measurement marks, borders, or decorative graphics. Arrange the poses as a clean "
        "collection sheet with enough separation between each pose for later automatic cropping and segmentation. "
        "Make every pose fully visible, sharply bounded, and not overlapping. Avoid messy background fragments around "
        "the object; edges must be clean enough for downstream cutout extraction."
    )


def create_accessory_candidate(
    name: str,
    material_type: str,
    training_role: str,
    source_files: list[str],
    physical_size: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_id = f"cand_{uuid.uuid4().hex[:10]}"
    thumb_dir = OUTPUT_DIR / "accessory_candidates" / candidate_id
    thumb_dir.mkdir(parents=True, exist_ok=True)
    item = {
        "id": candidate_id,
        "class_id": -1,
        "name": name,
        "material_type": material_type,
        "training_role": training_role,
        "physical_size": physical_size or physical_size_payload(material_type),
        "status": "candidate_review",
        "source_files": source_files,
        "created_at": int(time.time()),
    }
    normalized = normalize_accessory_assets(item)
    item.update(normalized)
    thumbnails = []
    image_sources = [Path(path) for path in source_files if Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}]
    for idx, src in enumerate(image_sources[:6]):
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
    item["ai_generation_required"] = material_type == "object" and len(image_sources) <= 1
    item["pose_collection_prompt"] = build_pose_collection_prompt(item) if item["ai_generation_required"] else ""
    if item["ai_generation_required"]:
        output_path = OUTPUT_DIR / "accessory_pose_collections" / candidate_id / "pose_collection.png"
        item["codex_image_job"] = {
            "job_id": f"imgjob_{candidate_id}",
            "candidate_id": candidate_id,
            "status": "queued_for_codex_image_worker",
            "mode": "image_to_image",
            "input_files": [str(path) for path in image_sources],
            "prompt": item["pose_collection_prompt"],
            "output_path": str(output_path),
            "output_url": public_output_url(output_path),
            "progress": 0,
            "created_at": int(time.time()),
            "note": "Queued for local Codex CLI ImageWorker. The backend will pass the reference image and prompt to Codex CLI and write output_path.",
        }
    (ACCESSORY_CANDIDATES_DIR / f"{candidate_id}.json").write_text(json.dumps(item, indent=2), encoding="utf-8")
    return item


def load_accessory_candidate(candidate_id: str) -> dict[str, Any]:
    path = ACCESSORY_CANDIDATES_DIR / f"{candidate_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Accessory candidate not found")
    return json.loads(path.read_text(encoding="utf-8"))


def save_accessory_candidate(path: Path, candidate: dict[str, Any]) -> None:
    path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")


def image_job_prompt(job: dict[str, Any]) -> str:
    output_path = str(job.get("output_path", ""))
    return f"""
You are the ImageWorker for the local assembly-line inspection service.

Use the attached input image as the visual source of truth.
Generate a single realistic bitmap PNG Pose Collection image.

Core prompt:
{job.get("prompt", "")}

Hard requirements:
- Save the final generated bitmap exactly to this path:
  {output_path}
- The output must be a valid PNG file.
- Do not return only text. Do not create a script-only placeholder.
- If you need to create intermediate files, keep them temporary, but the final output must be the exact path above.
- After generation, verify that the PNG exists at the exact output path.
""".strip()


def image_job_is_active(status: str) -> bool:
    return status in {"queued_for_codex_image_worker", "queued", "running"}


def next_queued_image_job() -> tuple[Path, dict[str, Any], dict[str, Any]] | None:
    for path in sorted(ACCESSORY_CANDIDATES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime):
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        job = candidate.get("codex_image_job")
        if not job:
            continue
        status = str(job.get("status", ""))
        if status not in {"queued_for_codex_image_worker", "queued"}:
            continue
        output_path = Path(str(job.get("output_path", "")))
        if output_path.exists():
            job["status"] = "completed"
            job["progress"] = 100
            job["output_url"] = public_output_url(output_path)
            job["completed_at"] = int(output_path.stat().st_mtime)
            candidate["codex_image_job"] = job
            save_accessory_candidate(path, candidate)
            continue
        return path, candidate, job
    return None


def update_image_worker_status(path: Path, candidate: dict[str, Any], job: dict[str, Any], **fields: Any) -> None:
    job.update(fields)
    candidate["codex_image_job"] = job
    save_accessory_candidate(path, candidate)


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
            error="No valid input image was found for this ImageWorker job.",
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
    for input_file in input_files[:4]:
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
        note="Codex CLI ImageWorker is processing this image-to-image task.",
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
            error="Codex CLI image generation timed out after 900 seconds.",
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

    try:
        latest = json.loads(path.read_text(encoding="utf-8"))
        latest_job = latest.get("codex_image_job", job)
    except json.JSONDecodeError:
        latest = candidate
        latest_job = job
    if latest_job.get("status") == "stopped":
        return

    if return_code == 0 and output_path.exists():
        latest_job.update(
            {
                "status": "completed",
                "progress": 100,
                "output_url": public_output_url(output_path),
                "completed_at": int(time.time()),
                "log_path": str(log_path),
                "note": "Generated by local Codex CLI ImageWorker.",
            }
        )
    else:
        latest_job.update(
            {
                "status": "failed",
                "progress": 100,
                "failed_at": int(time.time()),
                "error": f"Codex CLI exited with {return_code}, and output file was not found at {output_path}.",
                "log_path": str(log_path),
            }
        )
    latest["codex_image_job"] = latest_job
    save_accessory_candidate(path, latest)


def image_worker_loop() -> None:
    while True:
        queued = next_queued_image_job()
        if not queued:
            return
        run_codex_image_job(*queued)


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
    if output_path.exists():
        copy["status"] = "completed"
        copy["progress"] = 100
        copy["output_url"] = public_output_url(output_path)
        copy["completed_at"] = int(output_path.stat().st_mtime)
    elif str(copy.get("status")) == "running":
        started_at = int(copy.get("started_at") or copy.get("created_at") or time.time())
        elapsed = max(0, int(time.time()) - started_at)
        copy["progress"] = min(95, max(int(copy.get("progress", 0)), 18 + elapsed // 8))
        copy.setdefault("output_url", public_output_url(output_path) if str(output_path).startswith(str(OUTPUT_DIR)) else "")
    elif str(copy.get("status")) in {"failed", "stopped"}:
        copy["progress"] = int(copy.get("progress", 100))
    else:
        copy["progress"] = int(copy.get("progress", 0))
        copy.setdefault("output_url", public_output_url(output_path) if str(output_path).startswith(str(OUTPUT_DIR)) else "")
    return copy


def list_codex_image_jobs() -> list[dict[str, Any]]:
    jobs = []
    for path in sorted(ACCESSORY_CANDIDATES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        job = candidate.get("codex_image_job")
        if job:
            refreshed = refresh_codex_image_job(job)
            refreshed["candidate_name"] = candidate.get("name", "Accessory")
            refreshed["candidate_id"] = candidate.get("id", refreshed.get("candidate_id"))
            refreshed["job_id"] = refreshed.get("job_id") or f"imgjob_{refreshed['candidate_id']}"
            jobs.append(refreshed)
    return jobs


def update_codex_image_job(job_id: str, action: str) -> dict[str, Any]:
    for path in ACCESSORY_CANDIDATES_DIR.glob("*.json"):
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        job = candidate.get("codex_image_job")
        if not job:
            continue
        candidate_job_id = job.get("job_id") or f"imgjob_{candidate.get('id')}"
        if candidate_job_id != job_id:
            continue
        if action == "stop":
            process = _image_worker_processes.get(job_id)
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
            candidate["codex_image_job"] = job
        elif action == "delete":
            candidate.pop("codex_image_job", None)
        else:
            raise HTTPException(status_code=400, detail="Unknown job action")
        path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
        return {"status": action, "job_id": job_id}
    raise HTTPException(status_code=404, detail="Image job not found")


def write_gallery_preview(src: Path, out_path: Path, max_side: int = 1200) -> dict[str, Any] | None:
    image = cv2.imread(str(src), cv2.IMREAD_COLOR)
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
    material_type = item.get("material_type", "object")
    job = item.get("codex_image_job") or {}
    output_path = Path(str(job.get("output_path", "")))
    if material_type == "object" and output_path.exists() and str(output_path).startswith(str(OUTPUT_DIR)):
        gallery.append(
            {
                "label": "Pose Collection",
                "kind": "pose_collection",
                "url": public_output_url(output_path),
                "source_path": str(output_path),
            }
        )
        return {"item": serialize_accessory(item), "gallery": gallery}
    source_index = 1
    for path in accessory_image_paths(item):
        if path == output_path:
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
    return {"item": serialize_accessory(item), "gallery": gallery}


def selected_accessories(config: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
    indexed = {accessory_uid(item): serialize_accessory(item) for item in config.get("accessories", [])}
    selected = [indexed[item_id] for item_id in ids if item_id in indexed]
    if not selected:
        selected = [serialize_accessory(item) for item in config.get("accessories", [])]
    return selected


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


def draw_training_preview(accessories: list[dict[str, Any]], output_path: Path, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    bg_path = ROOT / "backgrounds" / "conveyor_surface_topdown_ai_reference5.png"
    background = cv2.imread(str(bg_path), cv2.IMREAD_COLOR) if bg_path.exists() else None
    if background is None:
        canvas = np.full((900, 1280, 3), (232, 234, 235), dtype=np.uint8)
        cv2.rectangle(canvas, (70, 100), (1210, 800), (87, 116, 98), -1)
    else:
        canvas = cv2.resize(background, (1280, 900), interpolation=cv2.INTER_AREA)
    cv2.rectangle(canvas, (70, 100), (1210, 800), (49, 72, 60), 2)
    labels = []
    render_accessories = sorted(accessories, key=lambda entry: 0 if entry.get("material_type", "object") == "text" else 1)
    for idx, item in enumerate(render_accessories):
        material_type = item.get("material_type", "object")
        angle = float(rng.uniform(-175, 175))
        size = physical_render_size_px(item, material_type)
        center = random_center_inside_background(rng, size, angle)
        asset = load_preview_asset(item)
        if material_type == "text":
            if asset is not None:
                paste_rotated_asset(canvas, asset, center, size, angle)
            else:
                rect = (center, size, angle)
                box = cv2.boxPoints(rect).astype(np.int32)
                cv2.fillConvexPoly(canvas, box, (245, 246, 246))
                cv2.polylines(canvas, [box], True, (25, 27, 29), 2)
        else:
            sprite = load_object_preview_sprite(item, rng)
            if sprite is not None:
                sprite_image, sprite_mask = sprite
                paste_physical_object_asset(canvas, sprite_image, sprite_mask, center, size[0], size[1], angle)
            else:
                rect = (center, size, angle)
                box = cv2.boxPoints(rect).astype(np.int32)
                cv2.fillConvexPoly(canvas, box, (34, 36, 38))
                cv2.polylines(canvas, [box], True, (7, 8, 9), 2)
                cv2.circle(tuple(box[0]), 18, (128, 37, 31), -1)
        labels.append(
            {
                "id": item["id"],
                "name": item["name"],
                "angle": round(angle, 2),
                "z_index": idx + 1,
                "physical_size": item.get("physical_size"),
                "render_size_px": physical_render_size_px(item, material_type),
                "render_policy": "object_alpha_long_side_equals_physical_length" if material_type == "object" else "paper_width_height_equals_physical_size",
            }
        )
    cv2.imwrite(str(output_path), canvas)
    return {"url": public_output_url(output_path), "labels": labels}


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
    return {"items": [serialize_accessory(item) for item in load_config()["accessories"]]}


@app.get("/api/accessories/{accessory_id}/detail")
def get_accessory_detail(accessory_id: str) -> dict[str, Any]:
    for item in load_config().get("accessories", []):
        if accessory_uid(item) == accessory_id:
            return accessory_detail_payload(item)
    raise HTTPException(status_code=404, detail="Accessory not found")


@app.get("/api/accessories/candidates/{candidate_id}")
def get_accessory_candidate(candidate_id: str) -> dict[str, Any]:
    candidate = load_accessory_candidate(candidate_id)
    job = candidate.get("codex_image_job")
    if job:
        refreshed = refresh_codex_image_job(job)
        candidate["codex_image_job"] = refreshed
        save_accessory_candidate(ACCESSORY_CANDIDATES_DIR / f"{candidate_id}.json", candidate)
    return {"status": "candidate_ready", "candidate": candidate}


@app.get("/api/image-jobs")
def image_jobs() -> dict[str, Any]:
    start_image_worker()
    jobs = list_codex_image_jobs()
    active_statuses = {"queued_for_codex_image_worker", "queued", "running"}
    return {
        "items": jobs,
        "active": [job for job in jobs if job.get("status") in active_statuses],
        "completed": [job for job in jobs if job.get("status") == "completed"],
    }


@app.get("/api/image-jobs/{job_id}")
def image_job(job_id: str) -> dict[str, Any]:
    for job in list_codex_image_jobs():
        if job.get("job_id") == job_id:
            return job
    raise HTTPException(status_code=404, detail="Image job not found")


@app.post("/api/image-jobs/{job_id}/stop")
def stop_image_job(job_id: str) -> dict[str, Any]:
    return update_codex_image_job(job_id, "stop")


@app.delete("/api/image-jobs/{job_id}")
def delete_image_job(job_id: str) -> dict[str, Any]:
    return update_codex_image_job(job_id, "delete")


@app.post("/api/accessories")
async def add_accessory(
    name: str = Form(...),
    class_id: int = Form(-1),
    material_type: str = Form("object"),
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
    normalized = normalize_accessory_assets(item)
    item.update(normalized)
    config["accessories"].append(item)
    save_config(config)
    return {"status": "saved", "item": serialize_accessory(config["accessories"][-1])}


@app.post("/api/accessories/preview")
async def preview_accessory(
    name: str = Form(...),
    material_type: str = Form("object"),
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
    candidate = create_accessory_candidate(name, material_type, training_role, saved_files, physical_size)
    if candidate.get("codex_image_job"):
        start_image_worker()
    return {"status": "candidate_ready", "candidate": candidate}


@app.post("/api/accessories/confirm/{candidate_id}")
def confirm_accessory(candidate_id: str) -> dict[str, Any]:
    candidate = load_accessory_candidate(candidate_id)
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


@app.post("/api/training/start")
def request_training(request: TrainingStartRequest) -> dict[str, Any]:
    config = load_config()
    selected = selected_accessories(config, request.selected_accessory_ids)
    mode_label = "YOLO + OCR" if request.train_mode == "yolo_ocr" else "YOLO"
    config["training"] = {
        "status": "requested",
        "last_requested_at": int(time.time()),
        "selected_accessory_ids": [item["id"] for item in selected],
        "sample_count": max(100, min(20000, int(request.sample_count))),
        "mode": request.train_mode,
        "approved_preview_id": request.approved_preview_id,
        "note": f"{mode_label} 训练请求已记录。下一步将按已确认样本生成训练集并启动训练。",
        "command_preview": (
            "python scripts/generate_accessory_dataset.py "
            f"--samples {max(100, min(20000, int(request.sample_count)))} "
            f"--mode {request.train_mode} && yolo segment train imgsz=640 ..."
        ),
    }
    save_config(config)
    return config["training"]


@app.post("/api/training/generate")
def request_sample_generation(request: TrainingStartRequest) -> dict[str, Any]:
    config = load_config()
    selected = selected_accessories(config, request.selected_accessory_ids)
    sample_count = max(100, min(20000, int(request.sample_count)))
    estimated_minutes = max(4, int(round(sample_count * 0.08)))
    estimated_gb = round(sample_count * 1.8 / 1024, 2)
    config["training"] = {
        "status": "sample_generation_requested",
        "last_requested_at": int(time.time()),
        "selected_accessory_ids": [item["id"] for item in selected],
        "sample_count": sample_count,
        "mode": request.train_mode,
        "approved_preview_id": request.approved_preview_id,
        "preview_urls": config.get("training", {}).get("preview_urls", []),
        "render_policy": {
            "background_physical_size": BACKGROUND_SIZE_MM,
            "physical_size_rule": "All samples must crop each accessory/document body first, then scale the cropped body by physical_size before placement.",
            "pose_collection_rule": "Pose Collection provides pose only; physical_size is applied only during preview and dataset rendering.",
        },
        "note": f"样本生成请求已记录：{sample_count} 张，预计 {estimated_minutes} 分钟，约 {estimated_gb} GB。",
        "command_preview": (
            "python scripts/generate_accessory_dataset.py "
            f"--samples {sample_count} --mode {request.train_mode} --approved-preview {request.approved_preview_id or 'none'}"
        ),
    }
    save_config(config)
    return config["training"]


@app.get("/api/training/status")
def training_status() -> dict[str, Any]:
    return load_config()["training"]


@app.get("/api/training/plan")
def training_plan() -> dict[str, Any]:
    config = load_config()
    return {
        "training": config["training"],
        "accessories": [serialize_accessory(item) for item in config.get("accessories", [])],
        "render_policy": {
            "sample_count_default": 4000,
            "background": "fixed conveyor background",
            "background_physical_size": BACKGROUND_SIZE_MM,
            "physical_size_rule": "crop foreground first, then scale foreground body by physical_size, never by original input canvas",
            "rotation": "full_random_0_to_360_with_random_state",
            "z_order": "randomized_per_sample",
            "label_shape": "visible_polygon_for_occluded_regions",
            "true_rule": "all selected required accessories present",
        },
    }


@app.post("/api/training/preview")
def training_preview(request: TrainingPreviewRequest) -> dict[str, Any]:
    config = load_config()
    selected = selected_accessories(config, request.selected_accessory_ids)
    preview_id = f"preview_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    job_dir = OUTPUT_DIR / "training_previews" / preview_id
    job_dir.mkdir(parents=True, exist_ok=True)
    previews = []
    count = max(1, min(12, int(request.preview_count)))
    for idx in range(count):
        output_path = job_dir / f"sample_{idx + 1:02d}.png"
        previews.append(draw_training_preview(selected, output_path, seed=idx + int(time.time())))
    plan = {
        "id": preview_id,
        "status": "preview_ready",
        "sample_count": max(100, min(20000, int(request.sample_count))),
        "train_mode": request.train_mode,
        "selected_accessories": selected,
        "previews": previews,
        "pipeline": [
            "normalize_accessory_assets",
            "remember_physical_size_metadata",
            "generate_synthetic_combinations",
            "crop_foreground_or_document_body",
            "scale_cropped_body_by_physical_size",
            "place_on_background_using_background_mm_per_px",
            "apply_full_rotation_randomization",
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
            "preview_urls": [item["url"] for item in previews],
        }
    )
    save_config(config)
    return plan


@app.on_event("startup")
def resume_image_worker_queue() -> None:
    start_image_worker()


ensure_dirs()
