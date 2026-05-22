from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

from build_yolo26_seg_2class_visible_polygon_dataset import convert_record_annotations


ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
OLD_SOURCE_IMAGES = ROOT / "image2_optimized_1000_atom_proxy_combinations"
OLD_MANIFEST = ROOT / "synthetic_1000_atom_proxy_combinations" / "manifest.json"
NEW_PROXY_IMAGES = ROOT / "synthetic_3000_atom_proxy_full_rotation_combinations"
NEW_SOURCE_IMAGES = ROOT / "image2_optimized_3000_atom_proxy_full_rotation_combinations"
NEW_MANIFEST = NEW_PROXY_IMAGES / "manifest.json"
OUT = ROOT / "yolo26_seg_2class_visible_polygon_4000_full_rotation_trial" / "dataset"


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
    seen_output_names = set()
    for split, items in splits.items():
        segment_count = 0
        source_counts = {}
        for record in items:
            src = Path(record["_source_images"]) / record["file"]
            if not src.exists():
                raise FileNotFoundError(src)
            if not image_readable(src):
                raise RuntimeError(f"Unreadable image: {src}")
            if record["file"] in seen_output_names:
                raise RuntimeError(f"Duplicate output filename across datasets: {record['file']}")
            seen_output_names.add(record["file"])

            shutil.copy2(src, OUT / "images" / split / record["file"])
            lines = convert_record_annotations(record)
            segment_count += len(lines)
            (OUT / "labels" / split / f"{src.stem}.txt").write_text(
                "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
            )
            source_counts[record["_source_name"]] = source_counts.get(record["_source_name"], 0) + 1
        stats[split] = {
            "images": len(items),
            "visible_polygon_segments": segment_count,
            "source_counts": source_counts,
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
    (OUT / "visible_polygon_metadata.json").write_text(
        json.dumps(
            {
                "old_manifest": str(OLD_MANIFEST),
                "old_source_images": str(OLD_SOURCE_IMAGES),
                "new_manifest": str(NEW_MANIFEST),
                "new_source_images": str(NEW_SOURCE_IMAGES),
                "new_proxy_images": str(NEW_PROXY_IMAGES),
                "label_policy": "visible polygon segmentation: full object rectangle mask minus all higher z-index object masks; RETR_EXTERNAL contours.",
                "class_policy": {"0": "bottle", "1": "manual"},
                "note": (
                    "First 1000 images are copied from the previous image2-optimized set. "
                    "Additional 3000 images use continuous non-upright manual rotations, "
                    "with proxy bottle marks replaced by bottle sprites extracted from the generated bottle pose collection."
                ),
                "stats": stats,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(OUT / "data.yaml")
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
