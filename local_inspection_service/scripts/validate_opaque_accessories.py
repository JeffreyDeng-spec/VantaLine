#!/usr/bin/env python3
"""Validate opaque accessory handling through VantaLine task workflows.

The harness intentionally keeps downloaded public images and generated reports
under data/outputs so the repo stays clean. It exercises the same server
rendering, YOLO parsing/rule logic, and AI Detection presence flow used by the
FastAPI image endpoint.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402


COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_USER_AGENT = "AlookTonyVantaLineOpaqueAccessoryValidation/1.0 (tony@alook.ai)"
PRICING_SOURCE_URL = "https://ai.google.dev/gemini-api/docs/pricing"
GEMINI_FLASH_LITE_PRICING = {
    "model_prefixes": ["gemini-2.5-flash-lite"],
    "source_url": PRICING_SOURCE_URL,
    "checked_at": "2026-06-06",
    "input_usd_per_1m_tokens": 0.10,
    "output_usd_per_1m_tokens": 0.40,
    "cache_input_usd_per_1m_tokens": 0.01,
}


ACCESSORY_CLASSES: list[dict[str, Any]] = [
    {"id": "key", "name": "key", "physical_size": {"kind": "object", "length_mm": 58.0, "width_mm": 22.0, "height_mm": 3.0}},
    {"id": "padlock", "name": "padlock", "physical_size": {"kind": "object", "length_mm": 45.0, "width_mm": 32.0, "height_mm": 16.0}},
    {"id": "screwdriver", "name": "screwdriver", "physical_size": {"kind": "object", "length_mm": 155.0, "width_mm": 24.0, "height_mm": 24.0}},
    {"id": "scissors", "name": "scissors", "physical_size": {"kind": "object", "length_mm": 170.0, "width_mm": 65.0, "height_mm": 8.0}},
    {"id": "headphones", "name": "headphones", "physical_size": {"kind": "object", "length_mm": 80.0, "width_mm": 50.0, "height_mm": 30.0}},
    {"id": "wristwatch", "name": "wristwatch", "physical_size": {"kind": "object", "length_mm": 100.0, "width_mm": 42.0, "height_mm": 32.0}},
    {"id": "battery", "name": "AA battery", "physical_size": {"kind": "object", "length_mm": 50.5, "width_mm": 14.5, "height_mm": 14.5}},
    {"id": "usb_flash_drive", "name": "USB flash drive", "physical_size": {"kind": "object", "length_mm": 60.0, "width_mm": 20.0, "height_mm": 9.0}},
]


CURATED_COMMONS_TITLES: dict[str, list[str]] = {
    "key": [
        "File:4-way utility key.JPG",
        "File:A key of vintage wooden wall clock of Smiths (from circa 1930s).jpg",
        "File:Ancient rusty key.jpg",
        "File:Bit Key by Russell & Erwin Mfg.jpg",
        "File:Bumpkey2.jpg",
        "File:Key picture.jpg",
        "File:Bossnøkkel.jpg",
        "File:CARI-36558 Magnolia Blacksmith Shop Key (147864e4-1dd8-b71c-0720-bf53df5805ee).jpg",
        "File:A Medieval Key (Locking) (FindID 1001698).jpg",
        "File:Broken key IMG 7123.JPG",
    ],
    "padlock": [
        "File:- Padlock -.jpg",
        "File:15mm Boss Padlocks Vorhangschloss.JPG",
        "File:A Padlock.jpg",
        "File:A padlock.jpg",
        "File:Alarm Padlock.jpg",
        "File:Altes Schloss von Burg-Wächter.jpg",
        "File:Bamberger Railroad lock (42077028800).jpg",
        "File:Best 4B72 Roanoke Logo Padlock.jpg",
        "File:Rusty Padlock Close Up.jpg",
        "File:Bilock.JPG",
    ],
    "screwdriver": [
        "File:09 CacciaviteTaglionero.JPG",
        "File:1970s chrome vanadium steel flathead screwdriver by Geilo Verktoy Norway.jpg",
        "File:1980s Phillips screwdriver SMS 2561 by German company Wittekind.jpg",
        "File:1999 Weralit 450 PR Gr 4 screwdriver by Germany company Wera Werkzeuge GmbH.jpg",
        "File:Big flat screwdriver.jpg",
        "File:Bit screwdriver.jpg",
        "File:Bithalter-wiha.jpg",
        "File:Black screwdriver.png",
        "File:CacciavitePanciaStella.JPG",
        "File:CacciaviteStellaArancio.JPG",
    ],
    "scissors": [
        "File:ChriSchere GebogeneBranchen.jpg",
        "File:.Schere.jpg",
        "File:13-01-02-inventur-wmde-blitz-42.jpg",
        "File:1914 or earlier iron scissors by Carl Wilfrid Dahlgren Eskilstuna Sweden.jpg",
        "File:2020 pair of Westcott scissors stainless steel.jpg",
        "File:Marttelius Scissors for trimming candle wicks.jpg",
        "File:54408 Dahle Scissors.jpg",
        "File:A Scissor.jpg",
        "File:A aesthetic scissors.JPG",
        "File:A pair of red scissors.png",
    ],
    "headphones": [
        "File:1970s or earlier Queen 505 8 Ohm headphones made in Japan.jpg",
        "File:1970s or earlier Elega DR 243C stereo headphones made in Japan.jpg",
        "File:500px photo (37986468).jpeg",
        "File:=Headphone.JPG",
        "File:A Headphone.jpg",
        "File:Anker Soundcore Space One.jpg",
        "File:AudioQuest NightHawk Carbon headphones (33582571334).jpg",
        "File:AudioQuest Nighthawk Carbon headphones (34382953586).jpg",
        "File:Audifonos E-350.jpg",
        "File:Bakelite products of Germany Kopfhörer 01.JPG",
    ],
    "wristwatch": [
        "File:\"WIN\" wristwatch.JPG",
        "File:01 Frontal braun.tif",
        "File:1970s Texas Instruments (TI) Red LED Display Men's Wrist Watch, Great Space Age Look (8492641399).jpg",
        "File:1970s Watch Ancre Antishoc stainless steel back antmagnetic (51878890718).jpg",
        "File:1972 Aquadive Time-Depth wrist watch.jpg",
        "File:1976 campaign wristwatch.JPG",
        "File:1 Front - slow Jo 17 - Swiss Made, 24 hour one hand wrist watch, GMT movement, dark brown vintage leather band, silver case, creme dial.jpg",
        "File:201210303 Glashuette Spezichron-11-27 diagonale Frontansicht 2012.jpg",
        "File:265-yema-spationaute-2-circa-1985-mostra-store-aix-space-astronaut-15-dial-cadran.jpg",
        "File:A Nordgreen watch.jpg",
    ],
    "battery": [
        "File:2500 mAh NiMH Battery - AA (11469147674).jpg",
        "File:A23 battery.jpg",
        "File:AA VARTA battery-side PNr°0782.jpg",
        "File:Battery AA horizontal.jpg",
        "File:DSCF0876 (31066076458).jpg",
        "File:Duracell quantum.jpg",
        "File:Duracell quantum powercheck.jpg",
        "File:E-Circuit AA Alkaline Battery.jpg",
        "File:Varta AA battery.jpg",
        "File:AA Battery (2176210906).jpg",
    ],
    "usb_flash_drive": [
        "File:16Mb Disgo flash drive.jpg",
        "File:8gb hp pendrive.jpg",
        "File:A USB stick with a Micro USB plug.png",
        "File:Beeman's USB Flash Drive.jpg",
        "File:BellaUSB.jpg",
        "File:CD-R King USB Flash Disk AX Series 16GB.jpg",
        "File:China Construction Bank First Generation USB Key 1.jpg",
        "File:Clé USB 1.jpg",
        "File:USB flash drive, 1TB.jpg",
        "File:Lexar USB flash drive.jpg",
    ],
}

CURATED_EXPECTED_COUNTS: dict[str, int] = {}


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("._")
    return slug[:120] or "item"


def output_root() -> Path:
    root = server.OUTPUT_DIR / "opaque_accessory_validation"
    root.mkdir(parents=True, exist_ok=True)
    return root


def commons_request(params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode({**params, "format": "json", "origin": "*"})
    request = urllib.request.Request(
        f"{COMMONS_API}?{query}",
        headers={"User-Agent": COMMONS_USER_AGENT},
    )
    last_error: BaseException | None = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(1.5 * attempt)
    raise RuntimeError(f"Commons API request failed after retries: {last_error}") from last_error


def imageinfo_for_titles(titles: list[str], width: int) -> dict[str, dict[str, Any]]:
    resolved: dict[str, dict[str, Any]] = {}
    for start in range(0, len(titles), 20):
        batch = titles[start : start + 20]
        data = commons_request(
            {
                "action": "query",
                "titles": "|".join(batch),
                "prop": "imageinfo",
                "iiprop": "url|mime|size|extmetadata",
                "iiurlwidth": str(width),
            }
        )
        for page in (data.get("query") or {}).get("pages", {}).values():
            if not isinstance(page, dict) or "missing" in page:
                continue
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") if isinstance(info.get("extmetadata"), dict) else {}
            resolved[str(page.get("title") or "")] = {
                "title": str(page.get("title") or ""),
                "page_url": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(str(page.get("title") or "").replace(" ", "_"), safe="/:_()'\","),
                "source_url": str(info.get("url") or ""),
                "download_url": str(info.get("thumburl") or info.get("url") or ""),
                "mime": str(info.get("mime") or ""),
                "width": int(info.get("width") or 0),
                "height": int(info.get("height") or 0),
                "license": str((meta.get("LicenseShortName") or {}).get("value") or ""),
                "license_url": str((meta.get("LicenseUrl") or {}).get("value") or ""),
                "artist": re.sub(r"<[^>]+>", "", str((meta.get("Artist") or {}).get("value") or ""))[:240],
                "credit": re.sub(r"<[^>]+>", "", str((meta.get("Credit") or {}).get("value") or ""))[:240],
            }
    return resolved


def download_url(url: str, path: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": COMMONS_USER_AGENT})
    last_error: BaseException | None = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = response.read()
            break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(1.5 * attempt)
    else:
        raise RuntimeError(f"Image download failed after retries: {url}: {last_error}") from last_error
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def write_contact_sheet(records: list[dict[str, Any]], split: str, path: Path) -> None:
    selected = [record for record in records if record.get("split") == split]
    if not selected:
        return
    cell_w, cell_h = 240, 190
    image_h = 145
    cols = 5
    rows = math.ceil(len(selected) / cols)
    sheet = np.full((rows * cell_h, cols * cell_w, 3), 245, dtype=np.uint8)
    for idx, record in enumerate(selected, start=1):
        image = cv2.imread(str(record.get("image_path") or ""), cv2.IMREAD_COLOR)
        if image is None:
            continue
        h, w = image.shape[:2]
        scale = min((cell_w - 16) / max(1, w), (image_h - 10) / max(1, h), 1.0)
        if scale < 1.0:
            image = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
        row = (idx - 1) // cols
        col = (idx - 1) % cols
        x0 = col * cell_w
        y0 = row * cell_h
        x = x0 + (cell_w - image.shape[1]) // 2
        y = y0 + 4 + (image_h - image.shape[0]) // 2
        sheet[y : y + image.shape[0], x : x + image.shape[1]] = image
        caption = f"{idx}:{record.get('label')} {int(record.get('expected_count') or 1)}"
        title = safe_slug(str(record.get("title") or "").removeprefix("File:"))[:28]
        cv2.putText(sheet, caption, (x0 + 6, y0 + image_h + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 1, cv2.LINE_AA)
        cv2.putText(sheet, title, (x0 + 6, y0 + image_h + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (45, 45, 45), 1, cv2.LINE_AA)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), sheet, [int(cv2.IMWRITE_JPEG_QUALITY), 92])


def extension_for_mime(title: str, mime: str) -> str:
    suffix = Path(title).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
        return ".jpg" if suffix in {".tif", ".tiff"} else suffix
    if mime == "image/png":
        return ".png"
    if mime == "image/webp":
        return ".webp"
    return ".jpg"


def decode_downloaded_image(path: Path) -> np.ndarray | None:
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        return None
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGRA)
    if image.ndim == 3 and image.shape[2] == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    if image.ndim == 3 and image.shape[2] == 4:
        return image
    return None


def write_jpeg_if_needed(path: Path) -> Path:
    if path.suffix.lower() not in {".tif", ".tiff"}:
        return path
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return path
    out = path.with_suffix(".jpg")
    cv2.imwrite(str(out), image, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    return out


def download_public_set(reference_per_class: int, max_side: int, force: bool = False) -> Path:
    labels = [item["id"] for item in ACCESSORY_CLASSES]
    all_titles = [title for label in labels for title in CURATED_COMMONS_TITLES[label]]
    info_by_title = imageinfo_for_titles(all_titles, max_side)
    records: list[dict[str, Any]] = []
    root = output_root()
    images_dir = root / "public_images"
    for label in labels:
        titles = CURATED_COMMONS_TITLES[label]
        if len(titles) < reference_per_class + 5:
            raise RuntimeError(f"{label} needs at least {reference_per_class + 5} curated titles")
        for idx, title in enumerate(titles):
            info = info_by_title.get(title)
            if not info:
                raise RuntimeError(f"Commons title could not be resolved: {title}")
            split = "reference" if idx < reference_per_class else "holdout"
            ext = extension_for_mime(title, info.get("mime", ""))
            image_path = images_dir / label / f"{split}_{idx + 1:02d}_{safe_slug(title.removeprefix('File:'))}{ext}"
            if force or not image_path.exists():
                download_url(info["download_url"], image_path)
            image_path = write_jpeg_if_needed(image_path)
            image = decode_downloaded_image(image_path)
            if image is None:
                raise RuntimeError(f"Downloaded image could not be decoded: {image_path}")
            sha = hashlib.sha256(image_path.read_bytes()).hexdigest()
            records.append(
                {
                    "label": label,
                    "expected_count": int(CURATED_EXPECTED_COUNTS.get(title, 1)),
                    "split": split,
                    "curation_status": "curated_public_clean_opaque_accessory",
                    "title": title,
                    "image_path": str(image_path),
                    "sha256": sha,
                    "width": int(image.shape[1]),
                    "height": int(image.shape[0]),
                    **info,
                }
            )
    records = normalize_holdout_records(records)
    manifest = {
        "created_at": int(time.time()),
        "source": "Wikimedia Commons MediaWiki API",
        "source_api": COMMONS_API,
        "curation_note": "Explicit file-title manifest; final holdout excludes reference images used for sprite/training generation.",
        "reference_per_class": reference_per_class,
        "holdout_per_class": 5,
        "classes": ACCESSORY_CLASSES,
        "records": records,
    }
    manifest_path = root / "public_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_contact_sheet(records, "reference", root / "reference_contact_sheet.jpg")
    write_contact_sheet(records, "holdout", root / "holdout_crops_contact_sheet.jpg")
    return manifest_path


def load_public_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or output_root() / "public_manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Public manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest.get("records") if isinstance(manifest.get("records"), list) else []
    needs_refresh = any(
        (item.get("split") == "holdout" and not item.get("validation_transform"))
        or int(item.get("expected_count") or 1)
        != int(CURATED_EXPECTED_COUNTS.get(str(item.get("title") or ""), int(item.get("expected_count") or 1)))
        for item in records
        if isinstance(item, dict)
    )
    if needs_refresh:
        manifest["records"] = normalize_holdout_records(records)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_contact_sheet(manifest["records"], "reference", output_root() / "reference_contact_sheet.jpg")
    write_contact_sheet(manifest["records"], "holdout", output_root() / "holdout_crops_contact_sheet.jpg")
    return manifest


def foreground_mask_from_clean_photo(image_bgra: np.ndarray) -> np.ndarray:
    alpha = image_bgra[:, :, 3]
    if int(cv2.countNonZero(alpha)) < alpha.size:
        return alpha
    bgr = image_bgra[:, :, :3]
    border = np.concatenate(
        [
            bgr[:8, :, :].reshape(-1, 3),
            bgr[-8:, :, :].reshape(-1, 3),
            bgr[:, :8, :].reshape(-1, 3),
            bgr[:, -8:, :].reshape(-1, 3),
        ],
        axis=0,
    )
    bg = np.median(border.astype(np.float32), axis=0)
    diff = np.linalg.norm(bgr.astype(np.float32) - bg, axis=2)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edge = cv2.Canny(gray, 40, 120)
    mask = ((diff > 24) | (edge > 0)).astype(np.uint8) * 255
    kernel = np.ones((5, 5), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if num <= 1:
        return np.full(mask.shape, 255, dtype=np.uint8)
    areas = stats[1:, cv2.CC_STAT_AREA]
    largest = int(np.argmax(areas)) + 1
    component = (labels == largest).astype(np.uint8) * 255
    area_ratio = float(stats[largest, cv2.CC_STAT_AREA]) / float(mask.size)
    if area_ratio < 0.01 or area_ratio > 0.92:
        return np.full(mask.shape, 255, dtype=np.uint8)
    component = cv2.dilate(component, np.ones((3, 3), dtype=np.uint8), iterations=1)
    return component


def trim_bgra_to_mask(image_bgra: np.ndarray, mask: np.ndarray, pad: int = 8) -> tuple[np.ndarray, np.ndarray, list[int]]:
    ys, xs = np.where(mask > 8)
    if len(xs) == 0 or len(ys) == 0:
        h, w = mask.shape[:2]
        return image_bgra, np.full((h, w), 255, dtype=np.uint8), [0, 0, w, h]
    x1 = max(0, int(xs.min()) - pad)
    y1 = max(0, int(ys.min()) - pad)
    x2 = min(mask.shape[1], int(xs.max()) + pad + 1)
    y2 = min(mask.shape[0], int(ys.max()) + pad + 1)
    return image_bgra[y1:y2, x1:x2].copy(), mask[y1:y2, x1:x2].copy(), [x1, y1, x2, y2]


def create_sprite(record: dict[str, Any], class_info: dict[str, Any], sprite_dir: Path) -> dict[str, Any]:
    source = Path(record["image_path"])
    image = decode_downloaded_image(source)
    if image is None:
        raise RuntimeError(f"Could not decode reference image: {source}")
    max_side = 420
    h, w = image.shape[:2]
    scale = min(float(max_side) / float(max(h, w)), 1.0)
    if scale < 1.0:
        image = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    mask = foreground_mask_from_clean_photo(image)
    trimmed, trimmed_mask, bbox = trim_bgra_to_mask(image, mask)
    trimmed[:, :, 3] = trimmed_mask
    sprite_dir.mkdir(parents=True, exist_ok=True)
    sprite_path = sprite_dir / f"{safe_slug(record['label'])}_{safe_slug(record['title'].removeprefix('File:'))}.png"
    cv2.imwrite(str(sprite_path), trimmed)
    source_size = [int(max(1, bbox[2] - bbox[0])), int(max(1, bbox[3] - bbox[1]))]
    metadata = server.pose_render_footprint_metadata("", source_size, class_info["physical_size"])
    return {
        "kind": "clean_object_sprite",
        "path": str(sprite_path),
        "method": "public_commons_clean_photo_foreground_mask",
        "width": int(trimmed.shape[1]),
        "height": int(trimmed.shape[0]),
        "normalized_asset_size_px": [int(trimmed.shape[1]), int(trimmed.shape[0])],
        "normalized_asset_dimensions_px": [int(trimmed.shape[1]), int(trimmed.shape[0])],
        "normalized_bbox_xyxy": [0, 0, int(trimmed.shape[1]), int(trimmed.shape[0])],
        "source_object_bbox_xyxy": bbox,
        "source_object_center_xy": [int((bbox[0] + bbox[2]) / 2), int((bbox[1] + bbox[3]) / 2)],
        "source_object_size_px": source_size,
        "source_image_size_px": [int(w), int(h)],
        "source_image_width": int(w),
        "source_image_height": int(h),
        "source_pose_family": "lying" if metadata.get("source_long_short_ratio", 1.0) >= 1.35 else "upright",
        "pose_family": "lying" if metadata.get("source_long_short_ratio", 1.0) >= 1.35 else "upright",
        "pose_position": "center",
        "source_position": "center",
        "task_id": "opaque_accessory_public_reference",
        "source_pose_collection_job_id": "opaque_accessory_public_reference",
        "physical_size_mm": class_info["physical_size"],
        "material_alpha_policy": "opaque",
        "object_alpha_material_policy": "opaque",
        "transparent_alpha_policy": "solid_foreground_opaque_mask",
        "edge_alpha_max": 0,
        "edge_alpha_pass": True,
        "alpha_edge_stats": {"max": 0, "nonzero_px": 0, "mean": 0.0},
        "mask_strategy": "public_clean_photo_border_background_component",
        "foreground_component_bbox_xyxy": [0, 0, int(trimmed.shape[1]), int(trimmed.shape[0])],
        "removed_stray_component_count": 0,
        "removed_stray_component_area_px": 0,
        "pre_rotation_safety_margin_px": 0,
        "post_rotation_safety_margin_px": 0,
        "original_orientation_angle": 0.0,
        "original_orientation_angle_degrees": 0.0,
        "rotation_degrees_applied": 0.0,
        "rotation_degrees_applied_to_upright": 0.0,
        "source_restore_rotation_degrees": 0.0,
        "normalized_axis_target_degrees": 0.0,
        **metadata,
    }


def create_holdout_crop(record: dict[str, Any], crop_dir: Path) -> dict[str, Any]:
    source = Path(record["image_path"])
    image = decode_downloaded_image(source)
    if image is None:
        raise RuntimeError(f"Could not decode holdout image: {source}")
    original_h, original_w = image.shape[:2]
    mask = foreground_mask_from_clean_photo(image)
    trimmed, trimmed_mask, bbox = trim_bgra_to_mask(image, mask, pad=14)
    alpha = (trimmed_mask.astype(np.float32) / 255.0)[..., None]
    bgr = trimmed[:, :, :3].astype(np.float32)
    white = np.full_like(bgr, 255.0)
    composite = np.clip(bgr * alpha + white * (1.0 - alpha), 0, 255).astype(np.uint8)
    max_side = 900
    h, w = composite.shape[:2]
    scale = min(float(max_side) / float(max(h, w)), 1.0)
    if scale < 1.0:
        composite = cv2.resize(composite, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    crop_dir.mkdir(parents=True, exist_ok=True)
    crop_path = crop_dir / f"{safe_slug(record['label'])}_{safe_slug(record['title'].removeprefix('File:'))}_crop.jpg"
    cv2.imwrite(str(crop_path), composite, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    updated = dict(record)
    updated.update(
        {
            "original_image_path": str(source),
            "original_width": int(original_w),
            "original_height": int(original_h),
            "image_path": str(crop_path),
            "validation_transform": "foreground_crop_from_public_source_on_white_background",
            "crop_bbox_xyxy": bbox,
            "crop_width": int(composite.shape[1]),
            "crop_height": int(composite.shape[0]),
            "curation_status": "curated_public_opaque_accessory_foreground_crop",
            "sha256": hashlib.sha256(crop_path.read_bytes()).hexdigest(),
        }
    )
    return updated


def normalize_holdout_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    crop_root = output_root() / "public_holdout_crops"
    normalized: list[dict[str, Any]] = []
    for record in records:
        record = {
            **record,
            "expected_count": int(CURATED_EXPECTED_COUNTS.get(str(record.get("title") or ""), int(record.get("expected_count") or 1))),
        }
        if record.get("split") == "holdout":
            normalized.append(create_holdout_crop(record, crop_root / str(record["label"])))
        else:
            normalized.append(record)
    return normalized


def validation_accessories(public_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    by_class = {item["id"]: item for item in ACCESSORY_CLASSES}
    sprite_root = output_root() / "reference_sprites"
    items: list[dict[str, Any]] = []
    for class_info in ACCESSORY_CLASSES:
        label = class_info["id"]
        references = [item for item in public_manifest["records"] if item["label"] == label and item["split"] == "reference"]
        source_files = [record["image_path"] for record in references]
        item = {
            "id": label,
            "class_id": len(items),
            "name": class_info["name"],
            "material_type": "object",
            "material_alpha_policy": "opaque",
            "training_role": "object",
            "status": "active",
            "source_files": source_files,
            "ai_profile_reference_files": source_files[:2],
            "physical_size": class_info["physical_size"],
            "normalized_assets": [],
            "clean_sprite_status": "ready",
            "clean_sprite_preprocessed_at": int(time.time()),
        }
        for record in references:
            item["normalized_assets"].append(create_sprite(record, by_class[label], sprite_root / label))
        item["clean_sprite_count"] = len(item["normalized_assets"])
        item["clean_sprite_expected_count"] = len(item["normalized_assets"])
        item["ai_profile"] = server.fallback_accessory_ai_profile(item)
        item["ai_profile"]["reference_images"] = server.accessory_reference_image_contexts(item)
        item["ai_profile_status"] = server.profile_generation_status(server.ai_detection_settings(), source="fallback")
        items.append(item)
    return items


def patch_server_config(config: dict[str, Any]):
    class Patch:
        def __init__(self) -> None:
            self.original_load = server.load_config
            self.original_save = server.save_config

        def __enter__(self):
            server.load_config = lambda: config
            server.save_config = lambda _config: None
            return self

        def __exit__(self, exc_type, exc, tb):
            server.load_config = self.original_load
            server.save_config = self.original_save

    return Patch()


def validation_config(accessories: list[dict[str, Any]]) -> dict[str, Any]:
    config = server.load_config()
    return {
        **config,
        "active_model_id": server.DEFAULT_MODEL_ID,
        "image_size": int(config.get("image_size") or 640),
        "confidence_threshold": 0.05,
        "required_classes": [],
        "min_counts": {},
        "ocr": {"enabled": False, "require_manual_types": False},
        "accessories": accessories,
        "training": {
            "selected_accessory_ids": [item["id"] for item in accessories],
            "sample_count": 640,
            "mode": "yolo",
            "background_set_id": "green_conveyor",
        },
    }


def save_validation_config_snapshot(config: dict[str, Any]) -> Path:
    path = output_root() / "validation_config_snapshot.json"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def rotate_bgra(image_bgra: np.ndarray, angle_degrees: float) -> np.ndarray:
    h, w = image_bgra.shape[:2]
    center = (w / 2.0, h / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle_degrees, 1.0)
    cos_v = abs(matrix[0, 0])
    sin_v = abs(matrix[0, 1])
    new_w = max(1, int((h * sin_v) + (w * cos_v)))
    new_h = max(1, int((h * cos_v) + (w * sin_v)))
    matrix[0, 2] += (new_w / 2.0) - center[0]
    matrix[1, 2] += (new_h / 2.0) - center[1]
    return cv2.warpAffine(
        image_bgra,
        matrix,
        (new_w, new_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255, 0),
    )


def light_photo_background(size: int, rng: np.random.Generator) -> np.ndarray:
    base = int(rng.integers(232, 256))
    background = np.full((size, size, 3), base, dtype=np.uint8)
    gradient_axis = np.linspace(-1.0, 1.0, size, dtype=np.float32)
    gradient = gradient_axis[None, :] if rng.random() < 0.5 else gradient_axis[:, None]
    background = np.clip(background.astype(np.float32) + gradient[..., None] * float(rng.uniform(4.0, 18.0)), 0, 255)
    noise = rng.normal(0.0, float(rng.uniform(1.0, 4.5)), background.shape)
    return np.clip(background + noise, 0, 255).astype(np.uint8)


def polygon_from_mask(mask: np.ndarray) -> list[list[int]]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) <= 4:
        return []
    epsilon = max(1.0, 0.004 * cv2.arcLength(contour, True))
    approx = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
    if len(approx) < 3:
        x, y, w, h = cv2.boundingRect(contour)
        approx = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype=np.int32)
    if len(approx) > 96:
        step = int(math.ceil(len(approx) / 96.0))
        approx = approx[::step]
    return [[int(x), int(y)] for x, y in approx]


def render_real_reference_training_example(
    record: dict[str, Any],
    class_index: int | None,
    split: str,
    image_path: Path,
    label_path: Path,
    rng: np.random.Generator,
    image_size: int,
) -> dict[str, Any]:
    source = Path(record["image_path"])
    image = decode_downloaded_image(source)
    if image is None:
        raise RuntimeError(f"Could not decode reference image: {source}")
    mask = foreground_mask_from_clean_photo(image)
    trimmed, trimmed_mask, bbox = trim_bgra_to_mask(image, mask, pad=18)
    trimmed[:, :, 3] = trimmed_mask
    h, w = trimmed.shape[:2]
    target_long_side = int(rng.uniform(0.42, 0.82) * image_size)
    scale = max(0.08, target_long_side / float(max(h, w, 1)))
    resized = cv2.resize(trimmed, (max(3, int(w * scale)), max(3, int(h * scale))), interpolation=cv2.INTER_AREA)
    bgr = resized[:, :, :3].astype(np.float32)
    bgr = np.clip(bgr * float(rng.uniform(0.86, 1.14)) + float(rng.uniform(-10.0, 10.0)), 0, 255)
    resized[:, :, :3] = bgr.astype(np.uint8)
    rotated = rotate_bgra(resized, float(rng.uniform(-28.0, 28.0)))
    alpha = rotated[:, :, 3]
    if int(cv2.countNonZero(alpha)) == 0:
        raise RuntimeError(f"Reference augmentation produced empty alpha: {source}")
    oh, ow = rotated.shape[:2]
    margin = 8
    max_object_side = max(8, image_size - (2 * margin))
    if oh > max_object_side or ow > max_object_side:
        shrink = min(max_object_side / max(oh, 1), max_object_side / max(ow, 1))
        rotated = cv2.resize(rotated, (max(3, int(ow * shrink)), max(3, int(oh * shrink))), interpolation=cv2.INTER_AREA)
        alpha = rotated[:, :, 3]
        oh, ow = rotated.shape[:2]
    canvas = light_photo_background(image_size, rng)
    x_min = margin if ow <= image_size - (2 * margin) else 0
    y_min = margin if oh <= image_size - (2 * margin) else 0
    x_max = max(x_min, image_size - ow - x_min)
    y_max = max(y_min, image_size - oh - y_min)
    x = int(rng.integers(x_min, x_max + 1))
    y = int(rng.integers(y_min, y_max + 1))
    object_alpha = (alpha.astype(np.float32) / 255.0)[..., None]
    roi = canvas[y : y + oh, x : x + ow].astype(np.float32)
    canvas[y : y + oh, x : x + ow] = np.clip(
        rotated[:, :, :3].astype(np.float32) * object_alpha + roi * (1.0 - object_alpha),
        0,
        255,
    ).astype(np.uint8)
    full_mask = np.zeros((image_size, image_size), dtype=np.uint8)
    full_mask[y : y + oh, x : x + ow] = np.maximum(full_mask[y : y + oh, x : x + ow], alpha)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(image_path), canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if class_index is None:
        label_path.write_text("", encoding="utf-8")
        label_kind = "negative_empty_label"
    else:
        polygon = polygon_from_mask(full_mask)
        line = server.yolo_label_line(class_index, polygon, width=image_size, height=image_size)
        if not line:
            raise RuntimeError(f"Could not create YOLO polygon for reference image: {source}")
        label_path.write_text(line + "\n", encoding="utf-8")
        label_kind = "positive_segmentation_label"
    return {
        "image": str(image_path),
        "labels": str(label_path),
        "split": split,
        "is_true": True,
        "source": "public_reference_real_photo_domain_adaptation",
        "source_image": str(source),
        "source_title": record.get("title") or "",
        "source_url": record.get("source_url") or "",
        "page_url": record.get("page_url") or "",
        "license": record.get("license") or "",
        "label": record.get("label") or "",
        "class_index": class_index,
        "label_kind": label_kind,
        "source_object_bbox_xyxy": bbox,
        "pass_fail_rule": "exact_count_match_required",
    }


def append_real_reference_training_examples(
    dataset: dict[str, Any],
    config: dict[str, Any],
    public_manifest: dict[str, Any],
    augmentations_per_reference: int,
    image_size: int,
    seed: int,
) -> dict[str, Any]:
    augmentations_per_reference = max(0, int(augmentations_per_reference))
    if augmentations_per_reference <= 0:
        return {"added": 0, "split_counts": {}, "records": []}
    dataset_dir = Path(dataset["dataset_dir"])
    manifest_path = Path(dataset["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    class_index = {str(item.get("id")): idx for idx, item in enumerate(config["accessories"])}
    references_by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in public_manifest.get("records") or []:
        if isinstance(record, dict) and record.get("split") == "reference":
            references_by_label[str(record.get("label") or "")].append(record)
    added_records: list[dict[str, Any]] = []
    rng = np.random.default_rng(seed)
    image_size = max(320, int(image_size))
    for label in labels():
        references = references_by_label.get(label) or []
        if len(references) < 5:
            raise RuntimeError(f"{label} needs at least 5 reference images for real-photo YOLO adaptation")
        for ref_index, record in enumerate(references):
            split = "train" if ref_index < 3 else "val" if ref_index == 3 else "test"
            for aug_index in range(augmentations_per_reference):
                stem = f"realref_{label}_{ref_index + 1:02d}_{aug_index + 1:03d}"
                image_path = dataset_dir / "images" / split / f"{stem}.jpg"
                label_path = dataset_dir / "labels" / split / f"{stem}.txt"
                added_records.append(
                    render_real_reference_training_example(
                        record,
                        class_index[label],
                        split,
                        image_path,
                        label_path,
                        rng,
                        image_size,
                    )
                )
    samples = manifest.get("samples") if isinstance(manifest.get("samples"), list) else []
    samples.extend(added_records)
    manifest.update(
        {
            "samples": samples,
            "sample_count": len(samples),
            "synthetic_sample_count": int(dataset.get("synthetic_sample_count") or dataset.get("sample_count") or 0),
            "real_reference_training_examples": len(added_records),
            "real_reference_augmentations_per_reference": augmentations_per_reference,
            "real_reference_source_split": "public manifest reference split only; final holdout records are excluded",
            "split_counts": dict(Counter(str(sample.get("split") or "unknown") for sample in samples)),
            "real_reference_split_counts": dict(Counter(str(sample.get("split") or "unknown") for sample in added_records)),
            "sample_generation_policy": {
                **(manifest.get("sample_generation_policy") if isinstance(manifest.get("sample_generation_policy"), dict) else {}),
                "real_photo_domain_adaptation": "reference-split public photos are foreground-cropped, augmented, and appended as YOLO segmentation examples; holdout split is never used for training",
            },
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "added": len(added_records),
        "split_counts": dict(Counter(str(sample.get("split") or "unknown") for sample in added_records)),
        "records": added_records,
    }


def reference_split_for_index(index: int) -> str:
    return "train" if index < 3 else "val" if index == 3 else "test"


def reference_records_by_label(public_manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in public_manifest.get("records") or []:
        if isinstance(record, dict) and record.get("split") == "reference":
            grouped[str(record.get("label") or "")].append(record)
    return grouped


def generate_per_class_yolo_dataset(
    public_manifest: dict[str, Any],
    target_label: str,
    job_id: str,
    positive_augmentations: int,
    negative_augmentations: int,
    image_size: int,
    seed: int,
) -> dict[str, Any]:
    references_by_label = reference_records_by_label(public_manifest)
    target_references = references_by_label.get(target_label) or []
    if len(target_references) < 5:
        raise RuntimeError(f"{target_label} needs at least 5 reference images for one-vs-rest YOLO training")
    dataset_dir = server.OUTPUT_DIR / "training_datasets" / job_id
    for split in ("train", "val", "test"):
        (dataset_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (dataset_dir / "labels" / split).mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    samples: list[dict[str, Any]] = []
    image_size = max(320, int(image_size))
    positive_augmentations = max(1, int(positive_augmentations))
    negative_augmentations = max(0, int(negative_augmentations))
    for ref_index, record in enumerate(target_references):
        split = reference_split_for_index(ref_index)
        for aug_index in range(positive_augmentations):
            stem = f"positive_{target_label}_{ref_index + 1:02d}_{aug_index + 1:03d}"
            samples.append(
                render_real_reference_training_example(
                    record,
                    0,
                    split,
                    dataset_dir / "images" / split / f"{stem}.jpg",
                    dataset_dir / "labels" / split / f"{stem}.txt",
                    rng,
                    image_size,
                )
            )
    for other_label, records in references_by_label.items():
        if other_label == target_label:
            continue
        for ref_index, record in enumerate(records):
            split = reference_split_for_index(ref_index)
            for aug_index in range(negative_augmentations):
                stem = f"negative_{other_label}_{ref_index + 1:02d}_{aug_index + 1:03d}"
                sample = render_real_reference_training_example(
                    record,
                    None,
                    split,
                    dataset_dir / "images" / split / f"{stem}.jpg",
                    dataset_dir / "labels" / split / f"{stem}.txt",
                    rng,
                    image_size,
                )
                sample["negative_for_label"] = target_label
                samples.append(sample)
    yaml_path = dataset_dir / "dataset.yaml"
    server.write_dataset_yaml(yaml_path, dataset_dir, [target_label])
    manifest = {
        "id": job_id,
        "task_id": job_id,
        "created_at": int(time.time()),
        "mode": "yolo",
        "model_variant": "yolo_one_vs_rest",
        "selected_accessory_ids": [target_label],
        "required_accessory_counts": {target_label: 1},
        "accessory_class_map": {"0": target_label},
        "class_accessory_map": {target_label: 0},
        "ocr_accessory_ids": [],
        "class_names": [target_label],
        "dataset_yaml": str(yaml_path),
        "pass_fail_rule": "exact_count_match_required",
        "split_counts": dict(Counter(str(sample.get("split") or "unknown") for sample in samples)),
        "positive_count": sum(1 for sample in samples if sample.get("label_kind") == "positive_segmentation_label"),
        "negative_count": sum(1 for sample in samples if sample.get("label_kind") == "negative_empty_label"),
        "positive_augmentations_per_reference": positive_augmentations,
        "negative_augmentations_per_non_target_reference": negative_augmentations,
        "holdout_policy": "final public holdout split is excluded; only public reference split is used for positive and negative training examples",
        "sample_generation_policy": {
            "strategy": "one-vs-rest public-reference YOLO segmentation",
            "positive_examples": "target class reference photos, foreground-cropped and augmented",
            "negative_examples": "other accessory reference photos with empty labels",
            "validation_target": "per-class persisted model selected by server.analyze_bgr",
        },
        "samples": samples,
    }
    manifest_path = dataset_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    task = {
        "job_id": job_id,
        "task_id": job_id,
        "candidate_id": job_id,
        "candidate_name": f"opaque accessory one-vs-rest: {target_label}",
        "label": f"opaque accessory one-vs-rest: {target_label}",
        "queue_kind": "training",
        "action": "train_model",
        "status": "prepared",
        "created_at": int(time.time()),
        "selected_accessory_ids": [target_label],
        "required_accessory_counts": {target_label: 1},
        "accessory_class_map": {"0": target_label},
        "class_accessory_map": {target_label: 0},
        "ocr_accessory_ids": [],
        "model_variant": "yolo_one_vs_rest",
        "sample_count": len(samples),
        "mode": "yolo",
        "epochs": 0,
        "image_size": image_size,
        "dataset_dir": str(dataset_dir),
        "dataset_yaml": str(yaml_path),
        "manifest_path": str(manifest_path),
        "note": "Prepared one-vs-rest public-reference YOLO dataset.",
    }
    server.save_training_task(task)
    return {"task": task, "dataset_dir": str(dataset_dir), "dataset_yaml": str(yaml_path), "manifest_path": str(manifest_path), "manifest": manifest}


def train_yolo_per_class_models(
    public_manifest: dict[str, Any],
    epochs: int,
    image_size: int,
    device: str,
    base_weights: Path | None,
    positive_augmentations: int,
    negative_augmentations: int,
) -> dict[str, Any]:
    started = int(time.time())
    results: dict[str, Any] = {}
    for label in labels():
        job_id = f"opaque_accessory_ovr_{label}_{started}_{hashlib.sha1(f'{label}-{os.urandom(8)!r}'.encode()).hexdigest()[:6]}"
        dataset = generate_per_class_yolo_dataset(
            public_manifest,
            label,
            job_id,
            positive_augmentations,
            negative_augmentations,
            image_size,
            seed=20260606 + len(results) * 1009,
        )
        train = train_yolo_model(dataset["task"], epochs, image_size, device, base_weights=base_weights)
        weights = Path(train["weights"])
        results[label] = {**dataset, **train, "job_id": job_id, "weights": str(weights)}
        if train.get("return_code") != 0 or not weights.exists():
            raise RuntimeError(f"One-vs-rest YOLO training failed for {label}; log: {train.get('log_path')}")
    return {
        "mode": "one_vs_rest",
        "labels": labels(),
        "epochs": epochs,
        "image_size": image_size,
        "base_weights": str(base_weights or ""),
        "positive_augmentations_per_reference": positive_augmentations,
        "negative_augmentations_per_non_target_reference": negative_augmentations,
        "per_class": results,
        "weights_by_label": {label: str(item["weights"]) for label, item in results.items()},
    }


def generate_training_artifacts(
    config: dict[str, Any],
    public_manifest: dict[str, Any],
    sample_count: int,
    seed: int,
    job_id: str,
    real_reference_augmentations: int,
    image_size: int,
) -> dict[str, Any]:
    task = {
        "job_id": job_id,
        "task_id": job_id,
        "candidate_id": job_id,
        "candidate_name": "opaque accessory public validation",
        "label": "opaque accessory public validation",
        "queue_kind": "training",
        "action": "train_model",
        "status": "running",
        "created_at": int(time.time()),
        "started_at": int(time.time()),
        "selected_accessory_ids": [item["id"] for item in config["accessories"]],
        "required_accessory_counts": {str(item["id"]): 1 for item in config["accessories"]},
        "accessory_class_map": {str(idx): str(item["id"]) for idx, item in enumerate(config["accessories"])},
        "class_accessory_map": {str(item["id"]): idx for idx, item in enumerate(config["accessories"])},
        "ocr_accessory_ids": [],
        "model_variant": "yolo",
        "sample_count": sample_count,
        "mode": "yolo",
        "epochs": 1,
        "image_size": int(config.get("image_size") or 640),
        "background_set_id": server.selected_background_set_id("green_conveyor"),
        "preview_pose_family_policy": "auto",
        "seed": seed,
        "note": "Generated by validate_opaque_accessories.py",
    }
    server.save_training_task(task)
    with patch_server_config(config):
        dataset = server.generate_training_dataset(task)
    dataset["synthetic_sample_count"] = sample_count
    real_reference_dataset = append_real_reference_training_examples(
        dataset,
        config,
        public_manifest,
        real_reference_augmentations,
        image_size,
        seed + 99173,
    )
    task.update(dataset)
    task["real_reference_training_examples"] = real_reference_dataset["added"]
    task["real_reference_augmentations_per_reference"] = real_reference_augmentations
    task["real_reference_split_counts"] = real_reference_dataset["split_counts"]
    server.save_training_task(task)
    return {"task": task, **dataset, "real_reference_dataset": real_reference_dataset}


def train_yolo_model(task: dict[str, Any], epochs: int, image_size: int, device: str, base_weights: Path | None = None) -> dict[str, Any]:
    job_id = str(task["job_id"])
    run_dir = server.OUTPUT_DIR / "training_runs"
    log_path = server.TRAINING_TASKS_DIR / f"{job_id}_opaque_validation.log"
    model_path = str(base_weights if base_weights and base_weights.exists() else server.MODEL_PATH if server.MODEL_PATH.exists() else server.REPO_MODEL_PATH)
    command = [
        "yolo",
        "segment",
        "train",
        f"model={model_path}",
        f"data={task['dataset_yaml']}",
        f"imgsz={image_size}",
        f"epochs={epochs}",
        "batch=0.72",
        f"device={device}",
        "cache=ram",
        "workers=0",
        "amp=True",
        "patience=10",
        "optimizer=auto",
        "mosaic=0.0",
        "mixup=0.0",
        "copy_paste=0.0",
        f"project={run_dir}",
        f"name={job_id}",
        "exist_ok=True",
    ]
    task.update(
        {
            "epochs": epochs,
            "image_size": image_size,
            "training_command": command,
            "training_log_path": str(log_path),
            "base_weights": model_path,
            "status": "running",
        }
    )
    server.save_training_task(task)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.run(command, cwd=str(server.APP_DIR), stdout=log, stderr=subprocess.STDOUT, text=True, check=False)
    weights = run_dir / job_id / "weights" / "best.pt"
    task.update(
        {
            "status": "completed" if process.returncode == 0 and weights.exists() else "failed",
            "completed_at": int(time.time()),
            "return_code": process.returncode,
            "training_run_dir": str(run_dir / job_id),
            "note": "YOLO training completed." if process.returncode == 0 and weights.exists() else "YOLO training failed.",
        }
    )
    server.save_training_task(task)
    return {"return_code": process.returncode, "weights": str(weights), "log_path": str(log_path), "command": command}


def labels() -> list[str]:
    return [item["id"] for item in ACCESSORY_CLASSES]


def register_workflow_task_specs(
    config: dict[str, Any],
    weights_path: Path | None = None,
    weights_by_label: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Create persisted per-class task/model aliases for selected workflow validation."""
    label_list = labels()
    registered: dict[str, dict[str, Any]] = {}
    for label in label_list:
        per_class_weights = Path(weights_by_label[label]) if weights_by_label and label in weights_by_label else None
        alias_source_weights = per_class_weights if per_class_weights and per_class_weights.exists() else weights_path
        model_labels = [label] if per_class_weights and per_class_weights.exists() else label_list
        accessory_class_map = {str(idx): class_label for idx, class_label in enumerate(model_labels)}
        class_accessory_map = {class_label: idx for idx, class_label in enumerate(model_labels)}
        run_id = f"opaque_accessory_workflow_{label}"
        dataset_dir = server.OUTPUT_DIR / "training_datasets" / run_id
        run_dir = server.OUTPUT_DIR / "training_runs" / run_id
        weights_dir = run_dir / "weights"
        dataset_dir.mkdir(parents=True, exist_ok=True)
        weights_dir.mkdir(parents=True, exist_ok=True)
        alias_weights = weights_dir / "best.pt"
        if alias_source_weights and alias_source_weights.exists():
            if alias_weights.exists() or alias_weights.is_symlink():
                alias_weights.unlink()
            try:
                alias_weights.symlink_to(alias_source_weights.resolve())
            except OSError:
                shutil.copy2(alias_source_weights, alias_weights)
        manifest_path = dataset_dir / "manifest.json"
        dataset_yaml = dataset_dir / "dataset.yaml"
        dataset_yaml.write_text(
            "\n".join(
                [
                    f"path: {dataset_dir}",
                    "train: images/train",
                    "val: images/val",
                    "test: images/test",
                    "names:",
                    *[f"  {idx}: {class_label}" for idx, class_label in enumerate(model_labels)],
                    "",
                ]
            ),
            encoding="utf-8",
        )
        manifest = {
            "id": run_id,
            "task_id": run_id,
            "mode": "yolo",
            "model_variant": "yolo",
            "selected_accessory_ids": [label],
            "required_accessory_counts": {label: 1},
            "accessory_class_map": accessory_class_map,
            "class_accessory_map": class_accessory_map,
            "ocr_accessory_ids": [],
            "class_names": model_labels,
            "dataset_yaml": str(dataset_yaml),
            "pass_fail_rule": "exact_count_match_required",
            "validation_alias": True,
            "validation_alias_mode": "one_vs_rest" if len(model_labels) == 1 else "shared_multiclass",
            "source": "validate_opaque_accessories.py",
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        task = {
            "job_id": run_id,
            "task_id": run_id,
            "candidate_id": run_id,
            "candidate_name": f"opaque accessory workflow validation: {label}",
            "label": f"opaque accessory workflow validation: {label}",
            "queue_kind": "training",
            "action": "train_model",
            "status": "completed",
            "created_at": int(time.time()),
            "completed_at": int(time.time()),
            "selected_accessory_ids": [label],
            "required_accessory_counts": {label: 1},
            "accessory_class_map": accessory_class_map,
            "class_accessory_map": class_accessory_map,
            "ocr_accessory_ids": [],
            "model_variant": "yolo",
            "sample_count": 0,
            "mode": "yolo",
            "epochs": 0,
            "image_size": int(config.get("image_size") or 640),
            "dataset_dir": str(dataset_dir),
            "dataset_yaml": str(dataset_yaml),
            "manifest_path": str(manifest_path),
            "training_run_dir": str(run_dir),
            "note": "Persisted one-vs-rest validation task alias generated by validate_opaque_accessories.py." if len(model_labels) == 1 else "Persisted validation task alias generated by validate_opaque_accessories.py.",
        }
        server.save_training_task(task)
        (run_dir / "library_metadata.json").write_text(
            json.dumps(
                {
                    "display_name": f"Opaque accessory validation - {label}",
                    "note": "Per-class validation task alias for selected model workflow checks.",
                    "created_by": "validate_opaque_accessories.py",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        registered[label] = {
            "run_id": run_id,
            "manifest_path": str(manifest_path),
            "dataset_yaml": str(dataset_yaml),
            "weights_path": str(alias_weights),
            "yolo_model_id": f"trained_{run_id}__yolo",
            "ai_model_id": server.ai_detection_task_model_id(run_id),
        }
    return registered


def holdout_records(public_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    records = [item for item in public_manifest["records"] if item["split"] == "holdout"]
    by_label = Counter(item["label"] for item in records)
    missing = {label: count for label, count in by_label.items() if count < 5}
    if missing:
        raise RuntimeError(f"Holdout has fewer than 5 images per class: {missing}")
    return records


def result_label_counts(detections: list[dict[str, Any]], threshold: float) -> Counter[str]:
    counts: Counter[str] = Counter()
    for det in detections:
        try:
            conf = float(det.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf < threshold:
            continue
        accessory_id = str(det.get("accessory_id") or det.get("class_name") or "")
        if accessory_id:
            counts[accessory_id] += int(det.get("count") or 1)
    return counts


def yolo_correct(result: dict[str, Any], expected_label: str, expected_count: int, threshold: float) -> tuple[bool, str, dict[str, int]]:
    detections = result.get("detections") if isinstance(result.get("detections"), list) else []
    counts = result_label_counts(detections, threshold)
    predicted = dict(counts)
    expected_only = counts.get(expected_label, 0) == max(1, int(expected_count)) and sum(counts.values()) == max(1, int(expected_count))
    rule = result.get("rule") if isinstance(result.get("rule"), dict) else {}
    correct = bool(result.get("passed")) and expected_only and not rule.get("missing") and not rule.get("extra")
    predicted_label = expected_label if counts.get(expected_label, 0) else (counts.most_common(1)[0][0] if counts else "")
    return correct, predicted_label, predicted


def gemini_correct(result: dict[str, Any], expected_label: str, expected_count: int) -> tuple[bool, str, dict[str, int]]:
    rule = result.get("rule") if isinstance(result.get("rule"), dict) else {}
    ai = result.get("ai") if isinstance(result.get("ai"), dict) else {}
    detections = result.get("detections") if isinstance(result.get("detections"), list) else []
    counts = {str(k): int(v) for k, v in (rule.get("counts") or {}).items() if str(k)}
    predicted_count = counts.get(expected_label, 0)
    matching = [
        det for det in detections
        if isinstance(det, dict) and str(det.get("accessory_id") or "") == expected_label and det.get("present") is True
    ]
    has_evidence = any(str(det.get("evidence") or "").strip() or float(det.get("confidence") or 0.0) > 0 for det in matching)
    provider_ok = not ai.get("provider_failure") and not ai.get("timed_out") and not ai.get("error")
    required_count = max(1, int(expected_count))
    correct = bool(result.get("passed")) and provider_ok and predicted_count == required_count and has_evidence and not rule.get("missing") and not rule.get("extra")
    predicted_label = expected_label if predicted_count else ""
    return correct, predicted_label, counts


def usage_value(metadata: dict[str, Any], *names: str) -> int:
    for name in names:
        value = metadata.get(name)
        if isinstance(value, int):
            return max(0, value)
    return 0


def estimate_gemini_cost(usage_metadata: dict[str, Any], model: str) -> dict[str, Any]:
    input_tokens = usage_value(usage_metadata, "promptTokenCount", "prompt_token_count", "input_tokens")
    cached_tokens = usage_value(usage_metadata, "cachedContentTokenCount", "cached_content_token_count", "cached_tokens")
    output_tokens = usage_value(
        usage_metadata,
        "candidatesTokenCount",
        "candidates_token_count",
        "output_tokens",
    )
    thoughts_tokens = usage_value(usage_metadata, "thoughtsTokenCount", "thoughts_token_count")
    billable_output = output_tokens + thoughts_tokens
    if model.startswith("gemini-2.5-flash-lite"):
        input_cost = max(0, input_tokens - cached_tokens) / 1_000_000.0 * GEMINI_FLASH_LITE_PRICING["input_usd_per_1m_tokens"]
        cache_cost = cached_tokens / 1_000_000.0 * GEMINI_FLASH_LITE_PRICING["cache_input_usd_per_1m_tokens"]
        output_cost = billable_output / 1_000_000.0 * GEMINI_FLASH_LITE_PRICING["output_usd_per_1m_tokens"]
    else:
        input_cost = max(0, input_tokens - cached_tokens) / 1_000_000.0 * 0.30
        cache_cost = cached_tokens / 1_000_000.0 * 0.03
        output_cost = billable_output / 1_000_000.0 * 2.50
    return {
        "model": model,
        "pricing_source_url": PRICING_SOURCE_URL,
        "usage_metadata": usage_metadata,
        "input_tokens": input_tokens,
        "cached_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "thoughts_tokens": thoughts_tokens,
        "estimated_cost_usd": round(input_cost + cache_cost + output_cost, 8),
    }


def run_yolo_validation(
    public_manifest: dict[str, Any],
    weights_path: Path | None,
    config: dict[str, Any],
    workflow_specs: dict[str, dict[str, Any]],
    out_dir: Path,
) -> dict[str, Any]:
    if weights_path is not None and not weights_path.exists():
        raise RuntimeError(f"YOLO weights not found: {weights_path}")
    if weights_path is None:
        missing_aliases = [
            label for label, workflow in workflow_specs.items()
            if not Path(str(workflow.get("weights_path") or "")).exists()
        ]
        if missing_aliases:
            raise RuntimeError(f"YOLO alias weights missing for labels: {missing_aliases}")
    rows: list[dict[str, Any]] = []
    threshold = float(config.get("confidence_threshold") or 0.25)
    out_dir.mkdir(parents=True, exist_ok=True)
    for index, record in enumerate(holdout_records(public_manifest), start=1):
        image_path = Path(record["image_path"])
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"Could not decode holdout image: {image_path}")
        request_id = f"opaque_yolo_{index:03d}_{record['label']}"
        expected_count = max(1, int(record.get("expected_count") or 1))
        workflow = workflow_specs[str(record["label"])]
        model_id = workflow["yolo_model_id"]
        start = time.monotonic()
        with patch_server_config(config):
            server._models.pop(model_id, None)
            result = server.analyze_bgr(image, request_id, model_id, image_path=image_path)
        latency_ms = int((time.monotonic() - start) * 1000)
        annotated_path = server.OUTPUT_DIR / str(result.get("annotated_url") or "").removeprefix("/outputs/")
        correct, predicted_label, predicted_counts = yolo_correct(result, str(record["label"]), expected_count, threshold)
        rows.append(
            {
                "method": "yolo",
                "workflow_path": "server.analyze_bgr selected_model_spec (same core path as /api/analyze/image after upload decode)",
                "workflow_model_id": model_id,
                "image_path": str(image_path),
                "source_url": record.get("source_url") or "",
                "page_url": record.get("page_url") or "",
                "license": record.get("license") or "",
                "expected_label": record["label"],
                "expected_count": expected_count,
                "predicted_label": predicted_label,
                "predicted_counts": predicted_counts,
                "passed": bool(result["passed"]),
                "correct": correct,
                "latency_ms": latency_ms,
                "error": "",
                "annotated_path": str(annotated_path),
                "raw": result,
            }
        )
    return summarize_rows("yolo", rows, out_dir)


def gemini_cost_entries(ai: dict[str, Any], model: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    failed_usage = ai.get("failed_usage_metadata") if isinstance(ai.get("failed_usage_metadata"), list) else []
    for idx, usage in enumerate(failed_usage, start=1):
        if not isinstance(usage, dict) or not usage:
            continue
        failed_cost = estimate_gemini_cost(usage, model)
        failed_cost["kind"] = f"failed_generate_content_attempt_{idx}"
        entries.append(failed_cost)
    usage_metadata = ai.get("usage_metadata") if isinstance(ai.get("usage_metadata"), dict) else {}
    provider_failed = bool(ai.get("provider_failure"))
    should_count_top_level = bool(usage_metadata) and (not provider_failed or not failed_usage or usage_metadata != failed_usage[-1])
    if should_count_top_level:
        cost = estimate_gemini_cost(usage_metadata, model)
        cost["kind"] = "generate_content"
        entries.append(cost)
    return entries, usage_metadata


def run_gemini_validation(
    public_manifest: dict[str, Any],
    config: dict[str, Any],
    workflow_specs: dict[str, dict[str, Any]],
    out_dir: Path,
    budget_stop_usd: float,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    cumulative_cost = 0.0
    settings = server.ai_detection_settings()
    if settings.get("provider") == "gemini" and settings.get("model") != "gemini-2.5-flash-lite":
        settings = {**settings, "model": "gemini-2.5-flash-lite"}
    for index, record in enumerate(holdout_records(public_manifest), start=1):
        if cumulative_cost + 0.02 >= budget_stop_usd:
            raise RuntimeError(f"Gemini budget stop reached before image {index}: ${cumulative_cost:.6f}")
        image_path = Path(record["image_path"])
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"Could not decode holdout image: {image_path}")
        request_id = f"opaque_gemini_{index:03d}_{record['label']}"
        expected_count = max(1, int(record.get("expected_count") or 1))
        workflow = workflow_specs[str(record["label"])]
        model_id = workflow["ai_model_id"]
        start = time.monotonic()
        original_settings = server.ai_detection_settings
        try:
            server.ai_detection_settings = lambda: settings
            with patch_server_config(config):
                result = server.analyze_bgr(image, request_id, model_id, image_path=image_path)
        finally:
            server.ai_detection_settings = original_settings
        latency_ms = int((time.monotonic() - start) * 1000)
        ai = result.get("ai") if isinstance(result.get("ai"), dict) else {}
        cost_entries, usage_metadata = gemini_cost_entries(ai, str(settings.get("model") or ""))
        profile_cache = ai.get("profile_cache") if isinstance(ai.get("profile_cache"), dict) else {}
        cache_usage = profile_cache.get("usage_metadata") if isinstance(profile_cache.get("usage_metadata"), dict) else {}
        if cache_usage:
            cache_cost = estimate_gemini_cost(cache_usage, str(settings.get("model") or ""))
            cache_cost["kind"] = "cached_content_create"
            cost_entries.append(cache_cost)
        image_cost = round(sum(float(entry["estimated_cost_usd"]) for entry in cost_entries), 8)
        cumulative_cost += image_cost
        if cumulative_cost > budget_stop_usd:
            raise RuntimeError(f"Gemini budget stop exceeded after image {index}: ${cumulative_cost:.6f}")
        correct, predicted_label, predicted_counts = gemini_correct(result, str(record["label"]), expected_count)
        rows.append(
            {
                "method": "gemini",
                "workflow_path": "server.analyze_bgr selected_model_spec (same core path as /api/analyze/image after upload decode)",
                "workflow_model_id": model_id,
                "image_path": str(image_path),
                "source_url": record.get("source_url") or "",
                "page_url": record.get("page_url") or "",
                "license": record.get("license") or "",
                "expected_label": record["label"],
                "expected_count": expected_count,
                "predicted_label": predicted_label,
                "predicted_counts": predicted_counts,
                "passed": bool(result.get("passed")),
                "correct": correct,
                "latency_ms": latency_ms,
                "error": str(ai.get("error") or ai.get("failure_reason") or ""),
                "annotated_path": str(server.OUTPUT_DIR / str(result.get("annotated_url") or "").removeprefix("/outputs/")),
                "estimated_cost_usd": image_cost,
                "cumulative_estimated_cost_usd": round(cumulative_cost, 8),
                "usage_metadata": usage_metadata,
                "cost_estimates": cost_entries,
                "raw": result,
            }
        )
    summary = summarize_rows("gemini", rows, out_dir)
    summary["cumulative_estimated_cost_usd"] = round(cumulative_cost, 8)
    summary["budget_stop_usd"] = budget_stop_usd
    summary["pricing"] = GEMINI_FLASH_LITE_PRICING
    return summary


def summarize_rows(method: str, rows: list[dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    total = len(rows)
    correct = sum(1 for row in rows if row["correct"])
    per_class: dict[str, dict[str, Any]] = {}
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        expected = str(row["expected_label"])
        predicted = str(row["predicted_label"] or "__none__")
        confusion[expected][predicted] += 1
        bucket = per_class.setdefault(expected, {"total": 0, "correct": 0})
        bucket["total"] += 1
        bucket["correct"] += int(bool(row["correct"]))
    for bucket in per_class.values():
        bucket["accuracy"] = round(bucket["correct"] / max(1, bucket["total"]), 6)
    summary = {
        "method": method,
        "total_images": total,
        "correct_images": correct,
        "image_level_accuracy": round(correct / max(1, total), 6),
        "per_class": per_class,
        "confusion": {label: dict(counter) for label, counter in confusion.items()},
        "rows_path": str(out_dir / f"{method}_rows.json"),
        "csv_path": str(out_dir / f"{method}_rows.csv"),
    }
    (out_dir / f"{method}_rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_fields = [
        "method",
        "image_path",
        "source_url",
        "page_url",
        "license",
        "workflow_model_id",
        "workflow_path",
        "expected_label",
        "expected_count",
        "predicted_label",
        "predicted_counts",
        "passed",
        "correct",
        "latency_ms",
        "estimated_cost_usd",
        "cumulative_estimated_cost_usd",
        "error",
        "annotated_path",
    ]
    with (out_dir / f"{method}_rows.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=csv_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: json.dumps(row.get(field), ensure_ascii=False) if isinstance(row.get(field), (dict, list)) else row.get(field, "") for field in csv_fields})
    return summary


def write_report(out_dir: Path, public_manifest_path: Path, config_path: Path, summaries: list[dict[str, Any]], training: dict[str, Any] | None) -> Path:
    lines = [
        "# Opaque Accessory Validation Report",
        "",
        f"- public manifest: `{public_manifest_path}`",
        f"- validation config snapshot: `{config_path}`",
        f"- pricing reference: {PRICING_SOURCE_URL}",
    ]
    if training:
        if training.get("mode") == "one_vs_rest":
            lines.extend(
                [
                    "- YOLO training mode: `one_vs_rest`",
                    f"- base weights: `{training.get('base_weights') or ''}`",
                    f"- positive augmentations/reference: {training.get('positive_augmentations_per_reference')}",
                    f"- negative augmentations/non-target reference: {training.get('negative_augmentations_per_non_target_reference')}",
                    "",
                    "Per-class YOLO models:",
                ]
            )
            for label, item in sorted((training.get("per_class") or {}).items()):
                lines.append(
                    f"- {label}: job `{item.get('job_id')}`, manifest `{item.get('manifest_path')}`, "
                    f"weights `{item.get('weights')}`, log `{item.get('log_path')}`"
                )
        else:
            real_reference = training.get("real_reference_dataset") if isinstance(training.get("real_reference_dataset"), dict) else {}
            lines.extend(
                [
                    f"- training dataset manifest: `{training.get('manifest_path')}`",
                    f"- training dataset yaml: `{training.get('dataset_yaml')}`",
                    f"- training weights: `{training.get('weights')}`",
                    f"- training log: `{training.get('log_path')}`",
                    f"- base weights: `{training.get('base_weights') or ''}`",
                    f"- real public reference YOLO examples added: {int(real_reference.get('added') or 0)}",
                    f"- real public reference split counts: {real_reference.get('split_counts') or {}}",
                ]
            )
    lines.append("")
    for summary in summaries:
        lines.extend(
            [
                f"## {summary['method'].upper()}",
                "",
                f"- image-level exact accuracy: {summary['correct_images']}/{summary['total_images']} = {summary['image_level_accuracy']:.6f}",
                f"- rows json: `{summary['rows_path']}`",
                f"- rows csv: `{summary['csv_path']}`",
            ]
        )
        if "cumulative_estimated_cost_usd" in summary:
            lines.append(f"- cumulative estimated Gemini spend: ${summary['cumulative_estimated_cost_usd']:.8f} (stop ${summary['budget_stop_usd']:.2f})")
        lines.extend(["", "Per class:", ""])
        for label, bucket in sorted(summary["per_class"].items()):
            lines.append(f"- {label}: {bucket['correct']}/{bucket['total']} = {bucket['accuracy']:.6f}")
        lines.extend(["", "Confusion:", ""])
        for label, counts in sorted(summary["confusion"].items()):
            lines.append(f"- {label}: {counts}")
        lines.append("")
    path = out_dir / "opaque_accessory_validation_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def self_test() -> int:
    lite = estimate_gemini_cost({"promptTokenCount": 1000, "candidatesTokenCount": 100}, "gemini-2.5-flash-lite")
    assert lite["estimated_cost_usd"] == round((1000 / 1_000_000 * 0.10) + (100 / 1_000_000 * 0.40), 8)
    assert len(ACCESSORY_CLASSES) >= 8
    for item in ACCESSORY_CLASSES:
        assert len(CURATED_COMMONS_TITLES[item["id"]]) >= 10
    print(json.dumps({"status": "ok", "classes": len(ACCESSORY_CLASSES)}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download or refresh the curated public Commons set.")
    parser.add_argument("--force-download", action="store_true", help="Re-download public images.")
    parser.add_argument("--reference-per-class", type=int, default=5)
    parser.add_argument("--max-download-side", type=int, default=1280)
    parser.add_argument("--sample-count", type=int, default=640)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--device", default="0")
    parser.add_argument("--job-id", default="")
    parser.add_argument("--base-weights", default="", help="Optional YOLO weights to fine-tune from.")
    parser.add_argument("--real-reference-augmentations", type=int, default=24, help="Augmented real public reference examples per reference image for YOLO domain adaptation.")
    parser.add_argument("--train-yolo", action="store_true")
    parser.add_argument("--train-yolo-per-class", action="store_true", help="Train one-vs-rest YOLO models for each accessory class from public reference photos.")
    parser.add_argument("--per-class-positive-augmentations", type=int, default=48)
    parser.add_argument("--per-class-negative-augmentations", type=int, default=10)
    parser.add_argument("--yolo-weights", default="")
    parser.add_argument("--run-yolo", action="store_true")
    parser.add_argument("--run-gemini", action="store_true")
    parser.add_argument("--budget-stop-usd", type=float, default=4.50)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if args.download:
        manifest_path = download_public_set(args.reference_per_class, args.max_download_side, force=args.force_download)
    else:
        manifest_path = output_root() / "public_manifest.json"
        if not manifest_path.exists():
            manifest_path = download_public_set(args.reference_per_class, args.max_download_side, force=False)

    public_manifest = load_public_manifest(manifest_path)
    accessories = validation_accessories(public_manifest)
    config = validation_config(accessories)
    config_path = save_validation_config_snapshot(config)
    out_dir = output_root() / f"reports_{int(time.time())}"
    out_dir.mkdir(parents=True, exist_ok=True)
    training_result: dict[str, Any] | None = None
    weights_path = Path(args.yolo_weights) if args.yolo_weights else None
    weights_by_label: dict[str, str] = {}
    base_weights = Path(args.base_weights) if args.base_weights else None
    if base_weights and not base_weights.is_absolute():
        base_weights = (Path.cwd() / base_weights).resolve()

    if args.train_yolo_per_class:
        training_result = train_yolo_per_class_models(
            public_manifest,
            epochs=args.epochs,
            image_size=args.image_size,
            device=args.device,
            base_weights=base_weights,
            positive_augmentations=args.per_class_positive_augmentations,
            negative_augmentations=args.per_class_negative_augmentations,
        )
        weights_by_label = dict(training_result["weights_by_label"])

    if args.train_yolo:
        job_id = args.job_id or f"opaque_accessory_{int(time.time())}_{hashlib.sha1(os.urandom(8)).hexdigest()[:6]}"
        generated = generate_training_artifacts(
            config,
            public_manifest,
            args.sample_count,
            seed=20260606,
            job_id=job_id,
            real_reference_augmentations=args.real_reference_augmentations,
            image_size=args.image_size,
        )
        train = train_yolo_model(generated["task"], args.epochs, args.image_size, args.device, base_weights=base_weights)
        training_result = {**generated, **train}
        weights_path = Path(train["weights"])

    workflow_specs = register_workflow_task_specs(
        config,
        weights_path if weights_path and weights_path.exists() else None,
        weights_by_label=weights_by_label or None,
    )
    summaries: list[dict[str, Any]] = []
    if args.run_yolo:
        if weights_path is None and not weights_by_label:
            raise RuntimeError("--run-yolo requires --yolo-weights, --train-yolo, or --train-yolo-per-class")
        summaries.append(run_yolo_validation(public_manifest, weights_path, config, workflow_specs, out_dir / "yolo"))
    if args.run_gemini:
        summaries.append(run_gemini_validation(public_manifest, config, workflow_specs, out_dir / "gemini", args.budget_stop_usd))
    if summaries:
        report = write_report(out_dir, manifest_path, config_path, summaries, training_result)
        print(json.dumps({"status": "completed", "report": str(report), "summaries": summaries}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"status": "prepared", "public_manifest": str(manifest_path), "validation_config": str(config_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
