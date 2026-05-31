#!/usr/bin/env python3
"""Generate synthetic accessory training samples with the server render rules."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def load_selected_accessories(approved_preview: str | None, selected_ids: list[str]) -> list[dict]:
    config = server.load_config()
    if approved_preview and approved_preview != "none":
        preview_path = server.TRAINING_JOBS_DIR / f"{approved_preview}.json"
        if not preview_path.exists():
            raise SystemExit(f"Approved preview not found: {approved_preview}")
        preview = json.loads(preview_path.read_text(encoding="utf-8"))
        preview_items = preview.get("selected_accessories")
        if isinstance(preview_items, list) and preview_items:
            return preview_items
    ids = selected_ids or config.get("training", {}).get("selected_accessory_ids", [])
    selected = server.selected_accessories(config, ids)
    if not selected:
        raise SystemExit("No selected accessories. Pass --selected-id or generate/approve a preview first.")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate local synthetic accessory dataset samples.")
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--mode", default="yolo_ocr", choices=["yolo", "yolo_ocr"])
    parser.add_argument("--approved-preview", default=None)
    parser.add_argument("--selected-id", action="append", default=[])
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--preview-pose-family-policy", default="auto")
    args = parser.parse_args()

    sample_count = max(1, min(20000, int(args.samples)))
    selected = load_selected_accessories(args.approved_preview, args.selected_id)
    pose_policy = server.normalize_preview_pose_family_policy(args.preview_pose_family_policy)
    sequence = server.preview_pose_family_sequence(selected, sample_count, pose_policy)
    seed_base = int(args.seed if args.seed is not None else time.time() * 1000)

    dataset_id = f"dataset_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    output_dir = Path(args.output_dir) if args.output_dir else server.OUTPUT_DIR / "training_datasets" / dataset_id
    try:
        output_dir.resolve().relative_to(server.OUTPUT_DIR.resolve())
    except ValueError as exc:
        raise SystemExit(f"--output-dir must be under {server.OUTPUT_DIR}") from exc
    images_dir = output_dir / "images"
    labels_dir = output_dir / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    samples = []
    for idx in range(sample_count):
        image_path = images_dir / f"sample_{idx + 1:06d}.png"
        rendered = server.draw_training_preview(
            selected,
            image_path,
            seed=seed_base + idx,
            pose_family_policy=sequence[idx],
        )
        label_path = labels_dir / f"sample_{idx + 1:06d}.json"
        label_payload = {
            "image": str(image_path),
            "mode": args.mode,
            "seed": seed_base + idx,
            "pose_family_policy": sequence[idx],
            "labels": rendered.get("labels", []),
        }
        label_path.write_text(json.dumps(label_payload, indent=2), encoding="utf-8")
        samples.append({"image": str(image_path), "labels": str(label_path), "url": rendered.get("url")})

    manifest = {
        "id": dataset_id,
        "created_at": int(time.time()),
        "mode": args.mode,
        "approved_preview": args.approved_preview,
        "sample_count": sample_count,
        "selected_accessory_ids": [item.get("id") for item in selected],
        "render_engine": "server.draw_training_preview",
        "render_policy": {
            "object_object_overlap": "forbidden_by_choose_object_center_inside_background",
            "object_document_overlap": "allowed_documents_not_in_placed_objects",
            "document_document_overlap": "allowed_documents_not_in_placed_objects",
        },
        "samples": samples,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"status": "generated", "manifest": str(output_dir / "manifest.json"), "samples": sample_count}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
