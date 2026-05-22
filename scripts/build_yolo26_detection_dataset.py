import json
import os
import random
import shutil
from pathlib import Path


ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
SOURCE_IMAGES = ROOT / "image2_optimized_1000_atom_proxy_combinations"
MANIFEST = ROOT / "synthetic_1000_atom_proxy_combinations" / "manifest.json"
OUT = ROOT / "yolo26_detection_trial" / "dataset"

CLASSES = [
    "bottle_proxy",
    "manual_warranty_service",
    "manual_battery_instruction",
    "manual_download_service",
    "manual_service_qr",
]


def yolo_box(xyxy, width, height):
    x1, y1, x2, y2 = xyxy
    x1 = max(0, min(width, x1))
    x2 = max(0, min(width, x2))
    y1 = max(0, min(height, y1))
    y2 = max(0, min(height, y2))
    cx = ((x1 + x2) / 2) / width
    cy = ((y1 + y2) / 2) / height
    bw = (x2 - x1) / width
    bh = (y2 - y1) / height
    return cx, cy, bw, bh


def main():
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))["records"]
    class_to_id = {name: idx for idx, name in enumerate(CLASSES)}

    by_label = {"true": [], "false": []}
    for record in records:
        label = record["label"]
        by_label[label].append(record)

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
        obj_count = 0
        for record in items:
            src = SOURCE_IMAGES / record["file"]
            if not src.exists():
                raise FileNotFoundError(src)

            image_dst = OUT / "images" / split / record["file"]
            os.symlink(src, image_dst)

            width = int(record["width"])
            height = int(record["height"])
            label_lines = []
            for ann in record["annotations"]:
                item_id = ann["item_id"]
                cls_id = class_to_id[item_id]
                cx, cy, bw, bh = yolo_box(ann["bbox_xyxy"], width, height)
                if bw <= 0 or bh <= 0:
                    continue
                label_lines.append(f"{cls_id} {cx:.8f} {cy:.8f} {bw:.8f} {bh:.8f}")
            obj_count += len(label_lines)

            label_dst = OUT / "labels" / split / f"{src.stem}.txt"
            label_dst.write_text("\n".join(label_lines) + "\n", encoding="utf-8")

        stats[split] = {
            "images": len(items),
            "objects": obj_count,
            "true": sum(1 for r in items if r["label"] == "true"),
            "false": sum(1 for r in items if r["label"] == "false"),
        }

    data_yaml = OUT / "data.yaml"
    names_text = "\n".join(f"  {idx}: {name}" for idx, name in enumerate(CLASSES))
    data_yaml.write_text(
        f"""path: {OUT}
train: images/train
val: images/val
test: images/test
names:
{names_text}
""",
        encoding="utf-8",
    )

    (OUT / "dataset_build_summary.json").write_text(
        json.dumps(
            {
                "source_images": str(SOURCE_IMAGES),
                "manifest": str(MANIFEST),
                "classes": CLASSES,
                "splits": stats,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(data_yaml)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
