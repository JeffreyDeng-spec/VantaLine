from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

from build_yolo26_seg_2class_visible_polygon_dataset import (
    contours_from_visible_mask,
    full_corners_for_annotation,
    mask_from_corners,
    yolo_seg_line,
)


ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
OLD_SOURCE_IMAGES = ROOT / "image2_optimized_1000_atom_proxy_combinations"
OLD_MANIFEST = ROOT / "synthetic_1000_atom_proxy_combinations" / "manifest.json"
NEW_PROXY_IMAGES = ROOT / "synthetic_3000_atom_proxy_full_rotation_combinations"
NEW_SOURCE_IMAGES = ROOT / "image2_optimized_3000_atom_proxy_full_rotation_combinations"
NEW_MANIFEST = NEW_PROXY_IMAGES / "manifest.json"
OUT_ROOT = ROOT / "yolo26_seg_5class_visible_polygon_4000_full_rotation_trial"
OUT = OUT_ROOT / "dataset"

CLASS_BY_ITEM_ID = {
    "bottle_proxy": 0,
    "manual_warranty_service": 1,
    "manual_battery_instruction": 2,
    "manual_download_service": 3,
    "manual_service_qr": 4,
}

CLASS_NAMES = {
    0: "Bottle",
    1: "Warranty Service Manual",
    2: "Battery Instruction Manual",
    3: "Download Service Manual",
    4: "Service QR Manual",
}


def load_records(manifest_path: Path, source_images: Path, source_name: str) -> list[dict]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = []
    for record in payload["records"]:
        records.append({**record, "_source_images": str(source_images), "_source_name": source_name})
    return records


def build_splits(records: list[dict]) -> dict[str, list[dict]]:
    by_source_label = {}
    for record in records:
        key = (record["_source_name"], record["label"])
        by_source_label.setdefault(key, []).append(record)

    rng = random.Random(20260522)
    splits = {"train": [], "val": [], "test": []}
    for items in by_source_label.values():
        shuffled = items[:]
        rng.shuffle(shuffled)
        n = len(shuffled)
        train_end = int(n * 0.70)
        val_end = int(n * 0.85)
        splits["train"].extend(shuffled[:train_end])
        splits["val"].extend(shuffled[train_end:val_end])
        splits["test"].extend(shuffled[val_end:])
    for items in splits.values():
        rng.shuffle(items)
    return splits


def image_readable(path: Path) -> bool:
    im = cv2.imread(str(path))
    return im is not None and im.size > 0


def convert_record_annotations_5class(record: dict) -> tuple[list[str], list[dict], dict[str, int]]:
    annotations = sorted(record["annotations"], key=lambda ann: int(ann["z_index"]))
    full_masks = [mask_from_corners(full_corners_for_annotation(ann)) for ann in annotations]
    lines = []
    audit_rows = []
    segment_counts = {str(class_id): 0 for class_id in CLASS_NAMES}

    for idx, ann in enumerate(annotations):
        item_id = ann["item_id"]
        if item_id not in CLASS_BY_ITEM_ID:
            audit_rows.append(
                {
                    "file": record["file"],
                    "sample_index": record.get("sample_index"),
                    "item_id": item_id,
                    "reason": "unmapped annotation item_id",
                }
            )
            continue

        higher_mask = np.zeros_like(full_masks[idx])
        for mask in full_masks[idx + 1 :]:
            higher_mask = cv2.bitwise_or(higher_mask, mask)

        visible_mask = cv2.bitwise_and(full_masks[idx], cv2.bitwise_not(higher_mask))
        class_id = CLASS_BY_ITEM_ID[item_id]
        for polygon in contours_from_visible_mask(visible_mask):
            lines.append(yolo_seg_line(class_id, polygon))
            segment_counts[str(class_id)] += 1
    return lines, audit_rows, segment_counts


def main() -> None:
    old_records = load_records(OLD_MANIFEST, OLD_SOURCE_IMAGES, "old_image2_optimized_1000")
    new_records = load_records(NEW_MANIFEST, NEW_SOURCE_IMAGES, "new_full_rotation_3000")
    records = old_records + new_records
    splits = build_splits(records)

    if OUT.exists():
        shutil.rmtree(OUT)
    for split in splits:
        (OUT / "images" / split).mkdir(parents=True, exist_ok=True)
        (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)

    stats = {}
    audit_rows = []
    seen_output_names = set()
    for split, items in splits.items():
        segment_count = 0
        source_counts = {}
        class_segment_counts = {str(class_id): 0 for class_id in CLASS_NAMES}
        for record in items:
            src = Path(record["_source_images"]) / record["file"]
            if not src.exists():
                raise FileNotFoundError(src)
            if not image_readable(src):
                raise RuntimeError(f"Unreadable image: {src}")
            if record["file"] in seen_output_names:
                raise RuntimeError(f"Duplicate output filename across datasets: {record['file']}")
            seen_output_names.add(record["file"])

            lines, record_audit_rows, record_class_counts = convert_record_annotations_5class(record)
            audit_rows.extend(record_audit_rows)
            if record_audit_rows:
                continue

            shutil.copy2(src, OUT / "images" / split / record["file"])
            segment_count += len(lines)
            for class_id, count in record_class_counts.items():
                class_segment_counts[class_id] += count
            (OUT / "labels" / split / f"{src.stem}.txt").write_text(
                "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
            )
            source_counts[record["_source_name"]] = source_counts.get(record["_source_name"], 0) + 1
        stats[split] = {
            "images": len(items),
            "written_images": sum(source_counts.values()),
            "visible_polygon_segments": segment_count,
            "class_segment_counts": class_segment_counts,
            "source_counts": source_counts,
        }

    (OUT / "data.yaml").write_text(
        f"""path: {OUT}
train: images/train
val: images/val
test: images/test
names:
  0: Bottle
  1: Warranty Service Manual
  2: Battery Instruction Manual
  3: Download Service Manual
  4: Service QR Manual
""",
        encoding="utf-8",
    )
    (OUT / "visible_polygon_metadata.json").write_text(
        json.dumps(
            {
                "old_manifest": str(OLD_MANIFEST),
                "old_source_images": str(OLD_SOURCE_IMAGES),
                "new_manifest": str(NEW_MANIFEST),
                "new_source_images": str(NEW_SOURCE_IMAGES),
                "new_proxy_images": str(NEW_PROXY_IMAGES),
                "label_policy": "visible polygon segmentation: full object rectangle mask minus all higher z-index object masks; RETR_EXTERNAL contours.",
                "class_policy": {str(k): v for k, v in CLASS_NAMES.items()},
                "item_id_class_mapping": CLASS_BY_ITEM_ID,
                "note": (
                    "Five-class segmentation labels are derived from manifest annotation item_id values. "
                    "Geometry is generated with the same visible polygon code used by the two-class dataset."
                ),
                "stats": stats,
                "audit_file": str(OUT / "audit_unmapped_annotations.json"),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (OUT / "audit_unmapped_annotations.json").write_text(
        json.dumps(audit_rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if audit_rows:
        raise RuntimeError(f"Unmapped annotations found: {len(audit_rows)}. See {OUT / 'audit_unmapped_annotations.json'}")

    print(OUT / "data.yaml")
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    print(f"audit_unmapped_annotations: {len(audit_rows)}")


if __name__ == "__main__":
    main()
