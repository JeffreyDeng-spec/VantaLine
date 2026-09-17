"""Dataset file orchestration; rendering and configuration remain explicit dependencies."""
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any, Protocol
from fastapi import HTTPException

Record = dict[str, Any]


class DrawTrainingSample(Protocol):
    def __call__(self, selected: list[Record], image_path: Path, *, seed: int,
                 pose_family_policy: str | None, split: str, background_set_id: str) -> Record: ...


class DatasetProgress(Protocol):
    def __call__(self, job_id: str, **updates: Any) -> Record: ...


@dataclass(frozen=True)
class DatasetRecords:
    load: Callable[[], Record]
    save: Callable[[Record], None]
    normalize_assets: Callable[[Record, list[str]], bool]
    select: Callable[[Record, list[str]], list[Record]]
    uses_ocr: Callable[[Record], bool]


@dataclass(frozen=True)
class DatasetPlanning:
    normalize_pose: Callable[[], Callable[[str | None], str]]
    background: Callable[[], Callable[[str | None], str]]
    build: Callable[[list[Record], int, int, str], list[Record]]


@dataclass(frozen=True)
class DatasetRendering:
    draw: Callable[[], DrawTrainingSample]
    label: Callable[[], Callable[[int, list[float] | None], str | None]]
    annotation: Callable[[], Callable[[Path, list[Record], Path], str]]
    yaml: Callable[[Path, Path, list[str]], None]
    max_occlusion: Callable[[], float]
    min_visible_area: Callable[[], int]


class DatasetGenerator:
    def __init__(self, records: DatasetRecords, plan: DatasetPlanning, render: DatasetRendering,
                 output: Callable[[], Callable[[str, str], Path]], update_provider: Callable[[], DatasetProgress]):
        self.records, self.plan, self.render = records, plan, render
        self.output, self.update_provider = output, update_provider

    def generate_training_dataset(self, task: dict[str, Any]) -> dict[str, Any]:
        config = self.records.load()
        selected_ids = list(task.get("selected_accessory_ids") or [])
        try:
            assets_changed = self.records.normalize_assets(config, selected_ids)
        except HTTPException:
            self.records.save(config)
            raise
        if assets_changed:
            self.records.save(config)
        selected = self.records.select(config, selected_ids)
        sample_count = max(1, min(20000, int(task.get("sample_count") or 100)))
        pose_policy = self.plan.normalize_pose()(task.get("preview_pose_family_policy") or "auto")
        background_set_id = self.plan.background()(task.get("background_set_id"))
        seed_base = int(task.get("seed") or time.time() * 1000)
        sample_plan = self.plan.build(selected, sample_count, seed_base, pose_policy)
        dataset_dir = self.output()("training_datasets", str(task.get("owner_user_id") or "")) / str(task["job_id"])
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
            rendered = self.render.draw()(
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
                # Detection dataset: one amodal (full, occlusion-complete) bbox per
                # part. Parts that are essentially fully hidden are skipped.
                if label.get("detection_dropped"):
                    continue
                line = self.render.label()(
                    class_index.get(str(label.get("id") or ""), 0),
                    label.get("amodal_bbox_xyxy"),
                )
                if line:
                    lines.append(line)
            label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            annotated_path = preview_dir / split / f"sample_{idx + 1:06d}_boxed.jpg"
            annotated_url = self.render.annotation()(image_path, rendered.get("labels", []), annotated_path)
            rendered_labels = rendered.get("labels", [])
            document_assets = [
                {
                    "id": label.get("id"),
                    "name": label.get("name"),
                    "document_asset_path": label.get("document_asset_path"),
                    "document_asset_index": label.get("document_asset_index"),
                    "document_asset_count": label.get("document_asset_count"),
                    "document_asset_selection_policy": label.get("document_asset_selection_policy"),
                    "document_asset_source": label.get("document_asset_source"),
                    "document_asset_method": label.get("document_asset_method"),
                }
                for label in rendered_labels
                if label.get("material_type") == "text"
            ]
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
                    "document_assets": document_assets,
                }
            )
            if idx == 0 or (idx + 1) % max(1, sample_count // 40) == 0 or idx + 1 == sample_count:
                self.update_provider()(
                    str(task["job_id"]),
                    status="running",
                    progress=min(72, 8 + int(((idx + 1) / sample_count) * 64)),
                    completed_samples=idx + 1,
                    note=f"正在生成训练样本：{idx + 1}/{sample_count}",
                )
        yaml_path = dataset_dir / "dataset.yaml"
        self.render.yaml(yaml_path, dataset_dir, class_names)
        manifest = {
            "id": task["job_id"],
            "task_id": task["job_id"],
            "pipeline_task_id": str(task.get("pipeline_task_id") or ""),
            "pipeline_task_name": str(task.get("pipeline_task_name") or ""),
            "created_at": int(time.time()),
            "mode": task.get("mode"),
            "model_variant": task.get("mode") or "yolo",
            "background_set_id": background_set_id,
            "sample_count": sample_count,
            "selected_accessory_ids": [item.get("id") for item in selected],
            "required_accessory_counts": {str(item.get("id")): 1 for item in selected},
            "accessory_class_map": {str(idx): str(item.get("id")) for idx, item in enumerate(selected)},
            "class_accessory_map": {str(item.get("id")): idx for idx, item in enumerate(selected)},
            "ocr_accessory_ids": [str(item.get("id")) for item in selected if self.records.uses_ocr(item)],
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
            "document_asset_path_distribution": Counter(
                str(asset.get("document_asset_path") or "none")
                for sample in samples
                for asset in sample.get("document_assets", [])
            ),
            "document_asset_index_distribution": Counter(
                str(asset.get("document_asset_index"))
                for sample in samples
                for asset in sample.get("document_assets", [])
                if asset.get("document_asset_index") is not None
            ),
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
                "model_task": "detection",
                "label_shape": "object_bounding_box",
                "occlusion_policy": f"detection bbox is amodal: each part keeps its full bounding box even when another part is pasted on top; a part is dropped only when >{int(self.render.max_occlusion() * 100)}% hidden or its visible area < {self.render.min_visible_area()}px",
                "rotation_policy": "objects use continuous random planar rotation sampled uniformly from -180 to 180 degrees; not limited to cardinal angles",
                "format_reference": "Ultralytics YOLO detection dataset.yaml with train/val/test and per-image `class cx cy w h` txt labels",
            },
            "samples": samples,
            "owner_user_id": str(task.get("owner_user_id") or ""),
            "owner_username": str(task.get("owner_username") or ""),
        }
        manifest_path = dataset_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return {"dataset_dir": str(dataset_dir), "dataset_yaml": str(yaml_path), "manifest_path": str(manifest_path)}
