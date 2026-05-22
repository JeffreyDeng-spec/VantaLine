from __future__ import annotations

import json
import math
import random
import shutil
from pathlib import Path

import cv2
import numpy as np


ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
SOURCE_IMAGES = ROOT / "image2_optimized_1000_atom_proxy_combinations"
MANIFEST = ROOT / "synthetic_1000_atom_proxy_combinations" / "manifest.json"
OUT = ROOT / "yolo26_obb_2class_visible_trial" / "dataset"

CANVAS_W = 1448
CANVAS_H = 1086
MANUAL_SOURCE_W = 1240
MANUAL_SOURCE_H = 1754
MANUAL_LONG_SIDE = 560
BOTTLE_BAR_LENGTH = 315
BOTTLE_REAL_WIDTH = 79


def rotate_point(x: float, y: float, angle_degrees: float) -> tuple[float, float]:
    angle = math.radians(angle_degrees)
    c = math.cos(angle)
    s = math.sin(angle)
    return x * c + y * s, -x * s + y * c


def oriented_rect_corners_px(cx: float, cy: float, w: float, h: float, angle_degrees: float) -> np.ndarray:
    local = np.array(
        [
            [-w / 2, -h / 2],
            [w / 2, -h / 2],
            [w / 2, h / 2],
            [-w / 2, h / 2],
        ],
        dtype=np.float32,
    )
    pts = []
    for x, y in local:
        rx, ry = rotate_point(float(x), float(y), angle_degrees)
        pts.append([min(max(cx + rx, 0), CANVAS_W - 1), min(max(cy + ry, 0), CANVAS_H - 1)])
    return np.array(pts, dtype=np.float32)


def manual_size(scale: float) -> tuple[int, int]:
    long_side = round(MANUAL_LONG_SIDE * scale)
    resize_scale = long_side / max(MANUAL_SOURCE_W, MANUAL_SOURCE_H)
    return round(MANUAL_SOURCE_W * resize_scale), round(MANUAL_SOURCE_H * resize_scale)


def full_corners_for_annotation(ann: dict) -> np.ndarray:
    cx, cy = ann["center_xy"]
    if ann["item_id"] == "bottle_proxy":
        if ann["state"] == "upright_dot":
            width = height = BOTTLE_REAL_WIDTH
            angle = 0.0
        else:
            width = BOTTLE_REAL_WIDTH
            height = BOTTLE_BAR_LENGTH
            angle = float(ann["angle_degrees"])
    else:
        width, height = manual_size(float(ann["scale"]))
        angle = float(ann["angle_degrees"])
    return oriented_rect_corners_px(float(cx), float(cy), float(width), float(height), angle)


def mask_from_corners(corners: np.ndarray) -> np.ndarray:
    mask = np.zeros((CANVAS_H, CANVAS_W), dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.round(corners).astype(np.int32), 255)
    return mask


def visible_corners_from_mask(mask: np.ndarray) -> np.ndarray | None:
    points = cv2.findNonZero(mask)
    if points is None or len(points) < 12:
        return None
    rect = cv2.minAreaRect(points)
    box = cv2.boxPoints(rect)
    box[:, 0] = np.clip(box[:, 0], 0, CANVAS_W - 1)
    box[:, 1] = np.clip(box[:, 1], 0, CANVAS_H - 1)
    return box.astype(np.float32)


def yolo_obb_line(class_id: int, corners: np.ndarray) -> str:
    normalized = []
    for x, y in corners:
        normalized.extend([float(x) / CANVAS_W, float(y) / CANVAS_H])
    return " ".join([str(class_id), *(f"{v:.8f}" for v in normalized)])


def convert_record_annotations(record: dict) -> list[str]:
    annotations = sorted(record["annotations"], key=lambda ann: int(ann["z_index"]))
    full_masks = [mask_from_corners(full_corners_for_annotation(ann)) for ann in annotations]
    lines = []

    for idx, ann in enumerate(annotations):
        higher_mask = np.zeros((CANVAS_H, CANVAS_W), dtype=np.uint8)
        for mask in full_masks[idx + 1 :]:
            higher_mask = cv2.bitwise_or(higher_mask, mask)

        visible_mask = cv2.bitwise_and(full_masks[idx], cv2.bitwise_not(higher_mask))
        corners = visible_corners_from_mask(visible_mask)
        if corners is None:
            continue

        class_id = 0 if ann["item_id"] == "bottle_proxy" else 1
        lines.append(yolo_obb_line(class_id, corners))
    return lines


def build_splits(records: list[dict]) -> dict[str, list[dict]]:
    by_label = {"true": [], "false": []}
    for record in records:
        by_label[record["label"]].append(record)

    rng = random.Random(20260520)
    splits = {"train": [], "val": [], "test": []}
    for items in by_label.values():
        shuffled = items[:]
        rng.shuffle(shuffled)
        n = len(shuffled)
        splits["train"].extend(shuffled[: int(n * 0.70)])
        splits["val"].extend(shuffled[int(n * 0.70) : int(n * 0.85)])
        splits["test"].extend(shuffled[int(n * 0.85) :])
    for items in splits.values():
        rng.shuffle(items)
    return splits


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    records = manifest["records"]
    splits = build_splits(records)

    if OUT.exists():
        shutil.rmtree(OUT)
    for split in splits:
        (OUT / "images" / split).mkdir(parents=True, exist_ok=True)
        (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)

    stats = {}
    for split, items in splits.items():
        object_count = 0
        empty_objects = 0
        for record in items:
            src = SOURCE_IMAGES / record["file"]
            if not src.exists():
                raise FileNotFoundError(src)
            shutil.copy2(src, OUT / "images" / split / record["file"])

            lines = convert_record_annotations(record)
            object_count += len(lines)
            expected = len(record["annotations"])
            empty_objects += max(expected - len(lines), 0)
            (OUT / "labels" / split / f"{src.stem}.txt").write_text(
                "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
            )
        stats[split] = {
            "images": len(items),
            "objects": object_count,
            "fully_occluded_or_too_small_skipped": empty_objects,
        }

    (OUT / "data.yaml").write_text(
        f"""path: {OUT}
train: images/train
val: images/val
test: images/test
names:
  0: bottle
  1: manual
""",
        encoding="utf-8",
    )
    (OUT / "visible_label_metadata.json").write_text(
        json.dumps(
            {
                "source_manifest": str(MANIFEST),
                "source_images": str(SOURCE_IMAGES),
                "label_policy": "visible OBB: subtract higher z-index object masks, then use minAreaRect on visible pixels.",
                "stats": stats,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(OUT / "data.yaml")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
