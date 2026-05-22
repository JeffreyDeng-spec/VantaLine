import json
import math
import os
import random
import shutil
from pathlib import Path


ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
SOURCE_IMAGES = ROOT / "image2_optimized_1000_atom_proxy_combinations"
MANIFEST = ROOT / "synthetic_1000_atom_proxy_combinations" / "manifest.json"
OUT = ROOT / "yolo26_obb_trial" / "dataset"

CLASSES = [
    "bottle_proxy",
    "manual_warranty_service",
    "manual_battery_instruction",
    "manual_download_service",
    "manual_service_qr",
]

CANVAS_W = 1448
CANVAS_H = 1086
MANUAL_SOURCE_W = 1240
MANUAL_SOURCE_H = 1754
MANUAL_LONG_SIDE = 560
BOTTLE_BAR_LENGTH = 315
BOTTLE_DOT_DIAMETER = 38
# The proxy stick is only a direction marker.  The actual Image2 bottle asset
# is about 25% as wide as it is long in the fifth/reference photo set.
BOTTLE_REAL_WIDTH = 79


def rotate_point(x, y, angle_degrees):
    """Rotate around origin in image coordinates, matching PIL's positive CCW angle."""
    a = math.radians(angle_degrees)
    c = math.cos(a)
    s = math.sin(a)
    return x * c + y * s, -x * s + y * c


def oriented_rect_corners(cx, cy, w, h, angle_degrees):
    local = [
        (-w / 2, -h / 2),
        (w / 2, -h / 2),
        (w / 2, h / 2),
        (-w / 2, h / 2),
    ]
    pts = []
    for x, y in local:
        rx, ry = rotate_point(x, y, angle_degrees)
        px = min(max(cx + rx, 0), CANVAS_W)
        py = min(max(cy + ry, 0), CANVAS_H)
        pts.append((px / CANVAS_W, py / CANVAS_H))
    return pts


def manual_size(scale):
    long_side = round(MANUAL_LONG_SIDE * scale)
    resize_scale = long_side / max(MANUAL_SOURCE_W, MANUAL_SOURCE_H)
    return round(MANUAL_SOURCE_W * resize_scale), round(MANUAL_SOURCE_H * resize_scale)


def annotation_corners(ann):
    cx, cy = ann["center_xy"]
    if ann["item_id"] == "bottle_proxy":
        if ann["state"] == "upright_dot":
            w = h = BOTTLE_REAL_WIDTH
            angle = 0.0
        else:
            w = BOTTLE_REAL_WIDTH
            h = BOTTLE_BAR_LENGTH
            angle = float(ann["angle_degrees"])
    else:
        w, h = manual_size(float(ann["scale"]))
        angle = float(ann["angle_degrees"])
    return oriented_rect_corners(float(cx), float(cy), w, h, angle)


def write_preview_metadata(records):
    metadata = {
        "format": "YOLO OBB polygon labels: class_id x1 y1 x2 y2 x3 y3 x4 y4, normalized to 0-1.",
        "classes": CLASSES,
        "source_manifest": str(MANIFEST),
        "source_images": str(SOURCE_IMAGES),
        "note": (
            "Rotated boxes are reconstructed from the original synthetic generation metadata: "
            "center_xy, angle_degrees, scale, and bottle state. Bottle labels use the proxy "
            "stick length for long-side direction, but real bottle width from the reference "
            "bottle asset instead of the thin black proxy width."
        ),
        "bottle_label_model": {
            "lying_length_px": BOTTLE_BAR_LENGTH,
            "lying_width_px": BOTTLE_REAL_WIDTH,
            "upright_body_diameter_px": BOTTLE_REAL_WIDTH,
            "proxy_dot_diameter_px": BOTTLE_DOT_DIAMETER,
            "width_source": "Generated Bottle Pose Collection side-bottle crop ratio: 524/2099 * 315 ≈ 79px",
        },
        "record_count": len(records),
    }
    (OUT / "obb_label_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    records = manifest["records"]
    class_to_id = {name: idx for idx, name in enumerate(CLASSES)}

    by_label = {"true": [], "false": []}
    for record in records:
        by_label[record["label"]].append(record)

    rng = random.Random(20260520)
    splits = {"train": [], "val": [], "test": []}
    for label, items in by_label.items():
        items = items[:]
        rng.shuffle(items)
        n = len(items)
        splits["train"].extend(items[: int(n * 0.70)])
        splits["val"].extend(items[int(n * 0.70) : int(n * 0.85)])
        splits["test"].extend(items[int(n * 0.85) :])

    if OUT.exists():
        shutil.rmtree(OUT)
    for split in splits:
        (OUT / "images" / split).mkdir(parents=True, exist_ok=True)
        (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)

    stats = {}
    for split, items in splits.items():
        rng.shuffle(items)
        object_count = 0
        for record in items:
            src = SOURCE_IMAGES / record["file"]
            if not src.exists():
                raise FileNotFoundError(src)
            dst = OUT / "images" / split / record["file"]
            shutil.copy2(src, dst)

            lines = []
            for ann in record["annotations"]:
                cls_id = class_to_id[ann["item_id"]]
                pts = annotation_corners(ann)
                coords = " ".join(f"{v:.8f}" for pt in pts for v in pt)
                lines.append(f"{cls_id} {coords}")
            object_count += len(lines)
            (OUT / "labels" / split / f"{src.stem}.txt").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )

        stats[split] = {
            "images": len(items),
            "objects": object_count,
            "true": sum(1 for r in items if r["label"] == "true"),
            "false": sum(1 for r in items if r["label"] == "false"),
        }

    names_text = "\n".join(f"  {idx}: {name}" for idx, name in enumerate(CLASSES))
    (OUT / "data.yaml").write_text(
        f"""path: {OUT}
train: images/train
val: images/val
test: images/test
names:
{names_text}
""",
        encoding="utf-8",
    )
    write_preview_metadata(records)
    (OUT / "dataset_build_summary.json").write_text(
        json.dumps({"splits": stats, "classes": CLASSES}, indent=2), encoding="utf-8"
    )
    print(OUT / "data.yaml")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
