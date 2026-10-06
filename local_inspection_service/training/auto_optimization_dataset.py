"""Automatic optimization dataset assembly and bounding-box source normalization."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import shutil
import time
import uuid
import cv2
import numpy as np
from .auto_optimization_dataset_ports import (
    DatasetConfiguration, DatasetSources, DatasetPublication, DatasetLayout,
)

@dataclass(frozen=True)
class AutoOptimizationDataset:
    configuration: DatasetConfiguration
    sources: DatasetSources
    publication: DatasetPublication
    layout: DatasetLayout

    def auto_optimize_bbox_training_entries(self, sample: dict[str, Any]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        manual_review = sample.get("manual_review") if isinstance(sample.get("manual_review"), dict) else {}
        sources = [
            *(sample.get("bbox_labels") if isinstance(sample.get("bbox_labels"), list) else []),
            *(sample.get("labels") if isinstance(sample.get("labels"), list) else []),
            *(sample.get("label_failures") if isinstance(sample.get("label_failures"), list) else []),
            *(manual_review.get("previous_label_failures") if isinstance(manual_review.get("previous_label_failures"), list) else []),
        ]
        seen: set[tuple[str, tuple[int, int, int, int]]] = set()
        for item in sources:
            if not isinstance(item, dict):
                continue
            accessory_id = str(item.get("accessory_id") or "").strip()
            bbox = item.get("bbox_xyxy")
            if not accessory_id or not isinstance(bbox, list) or len(bbox) < 4:
                continue
            try:
                clean_bbox = tuple(int(round(float(value))) for value in bbox[:4])
            except (TypeError, ValueError):
                continue
            key = (accessory_id, clean_bbox)
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {
                    "accessory_id": accessory_id,
                    "label": item.get("label") or accessory_id,
                    "bbox_xyxy": list(clean_bbox),
                    "color": item.get("color") or item.get("color_hex") or "",
                    "source_status": item.get("status") or sample.get("label_status") or "",
                    "source_reason": item.get("reason") or "",
                }
            )
        return entries


    def build_auto_optimize_dataset(self, task_id: str, state: dict[str, Any], samples: list[dict[str, Any]]) -> dict[str, Any] | None:
        selected_ids = [str(item) for item in state.get("selected_accessory_ids") or [] if str(item)]
        if not selected_ids:
            selected_ids = sorted({str(label.get("accessory_id") or "") for sample in samples for label in sample.get("labels") or [] if label.get("accessory_id")})
        if not selected_ids:
            return None
        request_user = self.configuration._request_user().get()
        config = self.configuration.scope_config_for_user()(self.configuration.load_config()(), request_user) if request_user else self.configuration.load_config()()
        accessories_by_id = self.configuration.accessory_lookup_by_id()(config)
        class_index = {item_id: idx for idx, item_id in enumerate(selected_ids)}
        class_names = [str((accessories_by_id.get(item_id) or {}).get("name") or (accessories_by_id.get(item_id) or {}).get("label") or item_id) for item_id in selected_ids]
        dataset_id = f"autoopt_{self.publication.safe_record_id()(task_id)}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        owner_id = str(state.get("owner_user_id") or (self.configuration._request_user().get() or {}).get("id") or "")
        dataset_dir = self.publication.output_write_dir_for_owner()("training_datasets", owner_id) / dataset_id
        for split in ("train", "val", "test"):
            (dataset_dir / "images" / split).mkdir(parents=True, exist_ok=True)
            (dataset_dir / "labels" / split).mkdir(parents=True, exist_ok=True)
        settings = state.get("settings") if isinstance(state.get("settings"), dict) else self.configuration.default_auto_optimize_settings()
        samples_per_real_image = self.configuration.auto_optimize_samples_per_real_image(settings)
        positive_derivatives_per_real_image = self.configuration.auto_optimize_positive_derivatives_per_real_image(settings)
        negative_samples_per_real_image = self.configuration.auto_optimize_negative_samples_per_real_image(settings)
        dataset_background_set_id = self.layout.safe_background_set_id()(str(state.get("background_set_id") or "green_conveyor"))
        positive_samples = [sample for sample in samples if isinstance(sample, dict) and sample.get("label_status") == "trainable"]
        bbox_only_samples = [sample for sample in samples if isinstance(sample, dict) and sample.get("label_status") == "trainable_bbox_only"]
        negative_samples = [sample for sample in samples if isinstance(sample, dict) and sample.get("label_status") == "negative"]
        synthetic_jobs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for sample in positive_samples:
            generated = self.sources.auto_optimize_generate_synthetic_batch_for_sample()(task_id, state, sample)
            for rendered in generated:
                if isinstance(rendered, dict) and rendered.get("image") and rendered.get("labels"):
                    synthetic_jobs.append((sample, rendered))
        real_bbox_source_samples = positive_samples + bbox_only_samples
        real_bbox_jobs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for sample in real_bbox_source_samples:
            if not self.sources.auto_optimize_bbox_training_entries()(sample):
                continue
            for copy_index in range(self.sources.AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT()):
                real_bbox_jobs.append(
                    (
                        sample,
                        {
                            "job_type": "real_bbox_original",
                            "copy_index": copy_index + 1,
                            "sample_weight": self.sources.AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT(),
                        },
                    )
                )
        negative_jobs = [(sample, -1) for sample in negative_samples]
        generated_negative_jobs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for source_sample in real_bbox_source_samples:
            for variant_index in range(negative_samples_per_real_image):
                generated_negative_jobs.append(
                    (
                        source_sample,
                        {
                            "job_type": "synthetic_negative_background",
                            "variant_index": variant_index + 1,
                            "source_policy": "per_real_positive_source_empty_background",
                        },
                    )
                )
        render_jobs = synthetic_jobs + real_bbox_jobs + negative_jobs + generated_negative_jobs
        if not synthetic_jobs and not real_bbox_jobs:
            state["last_dataset_error"] = "no_trainable_ai_mask_sprites_or_bbox_labels"
            return None
        counts = self.layout.split_counts()(len(render_jobs))
        split_sequence: list[str] = []
        for split in ("train", "val", "test"):
            split_sequence.extend([split] * int(counts.get(split, 0)))
        if len(split_sequence) < len(render_jobs):
            split_sequence.extend(["train"] * (len(render_jobs) - len(split_sequence)))
        rng = np.random.default_rng(int(time.time()))
        order = list(range(len(render_jobs)))
        rng.shuffle(order)
        sample_records: list[dict[str, Any]] = []
        preview_dir = dataset_dir / "previews"
        for out_idx, sample_idx in enumerate(order):
            sample, rendered_or_marker = render_jobs[sample_idx]
            split = split_sequence[out_idx] if out_idx < len(split_sequence) else "train"
            image_name = f"sample_{out_idx + 1:06d}.png"
            image_out = dataset_dir / "images" / split / image_name
            label_out = dataset_dir / "labels" / split / f"{Path(image_name).stem}.txt"
            if isinstance(rendered_or_marker, dict) and rendered_or_marker.get("job_type") == "real_bbox_original":
                split = "train"
                image_out = dataset_dir / "images" / split / image_name
                label_out = dataset_dir / "labels" / split / f"{Path(image_name).stem}.txt"
                source_path = self.publication.resolve_service_path()((sample.get("source_image") or {}).get("path"))
                image = self.publication._image_files().imread(str(source_path), cv2.IMREAD_COLOR)
                if image is None:
                    continue
                height, width = image.shape[:2]
                bbox_entries = [
                    entry
                    for entry in self.sources.auto_optimize_bbox_training_entries()(sample)
                    if str(entry.get("accessory_id") or "") in class_index
                ]
                if not bbox_entries:
                    continue
                weak_labels = [
                    {
                        "id": str(entry.get("accessory_id") or ""),
                        "name": str((accessories_by_id.get(str(entry.get("accessory_id") or "")) or {}).get("name") or entry.get("label") or entry.get("accessory_id") or ""),
                        "amodal_bbox_xyxy": entry.get("bbox_xyxy"),
                        "bbox_xyxy": entry.get("bbox_xyxy"),
                        "real_bbox_original": True,
                        "source_sample_id": sample.get("sample_id"),
                        "source_record_id": sample.get("record_id"),
                        "source_reason": entry.get("source_reason") or "",
                    }
                    for entry in bbox_entries
                ]
                lines = [
                    line
                    for line in (
                        self.layout.yolo_detection_label_line()(class_index[str(entry["id"])], entry.get("amodal_bbox_xyxy"), width=width, height=height)
                        for entry in weak_labels
                        if str(entry.get("id") or "") in class_index
                    )
                    if line
                ]
                if not lines:
                    continue
                self.publication._business_files().copy2(source_path, image_out, local_copy=shutil.copy2)
                self.publication._business_files().write_text(label_out, "\n".join(lines) + "\n", encoding="utf-8")
                annotated_url = self.layout.write_training_annotation_preview()(image_out, weak_labels, preview_dir / split / f"{Path(image_name).stem}_boxed.jpg")
                is_bbox_only = sample.get("label_status") == "trainable_bbox_only"
                sample_records.append(
                    {
                        "image": str(image_out),
                        "labels": str(label_out),
                        "url": self.layout.public_training_output_url()(image_out),
                        "annotated_url": annotated_url,
                        "source_sample_id": sample.get("sample_id"),
                        "source_record_id": sample.get("record_id"),
                        "split": split,
                        "sample_type": "real_positive_bbox_only" if is_bbox_only else "real_positive_original_bbox",
                        "label_status": sample.get("label_status") or "",
                        "label_count": len(lines),
                        "weak_labels": weak_labels,
                        "sample_weight": int(rendered_or_marker.get("sample_weight") or self.sources.AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT()),
                        "weight_index": int(rendered_or_marker.get("copy_index") or 1),
                    }
                )
                continue
            if isinstance(rendered_or_marker, dict) and rendered_or_marker.get("job_type") == "synthetic_negative_background":
                canvas, background_meta = self.layout.render_training_background()(rng, split, dataset_background_set_id)
                image_out.parent.mkdir(parents=True, exist_ok=True)
                label_out.parent.mkdir(parents=True, exist_ok=True)
                self.publication._image_files().imwrite(str(image_out), canvas)
                self.publication._business_files().write_text(label_out, "", encoding="utf-8")
                annotated_path = preview_dir / split / f"{Path(image_name).stem}_negative.jpg"
                annotated_path.parent.mkdir(parents=True, exist_ok=True)
                self.publication._image_files().imwrite(str(annotated_path), canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                sample_records.append(
                    {
                        "image": str(image_out),
                        "labels": str(label_out),
                        "url": self.layout.public_training_output_url()(image_out),
                        "annotated_url": self.layout.public_training_output_url()(annotated_path),
                        "source_sample_id": sample.get("sample_id"),
                        "source_record_id": sample.get("record_id"),
                        "split": split,
                        "sample_type": "synthetic_negative_empty_background",
                        "label_status": "synthetic_negative",
                        "label_count": 0,
                        "weak_labels": [],
                        "background": background_meta,
                        "negative_policy": rendered_or_marker.get("source_policy") or "",
                        "negative_variant_index": int(rendered_or_marker.get("variant_index") or 1),
                    }
                )
                continue
            if isinstance(rendered_or_marker, dict):
                synthetic = dict(rendered_or_marker)
                source_image = self.publication.resolve_service_path()(synthetic.get("image") or "")
                source_label = self.publication.resolve_service_path()(synthetic.get("labels") or "")
                if not self.publication._business_files().exists(source_image) or not self.publication._business_files().exists(source_label):
                    continue
                self.publication._business_files().copy2(source_image, image_out, local_copy=shutil.copy2)
                self.publication._business_files().copy2(source_label, label_out, local_copy=shutil.copy2)
                annotated_source = self.publication.resolve_service_path()(synthetic.get("annotated_path") or "")
                annotated_url = ""
                if self.publication._business_files().exists(annotated_source):
                    annotated_out = preview_dir / split / f"{Path(image_name).stem}_boxed.jpg"
                    annotated_out.parent.mkdir(parents=True, exist_ok=True)
                    self.publication._business_files().copy2(annotated_source, annotated_out, local_copy=shutil.copy2)
                    annotated_url = self.layout.public_training_output_url()(annotated_out)
                else:
                    annotated_url = self.layout.write_training_annotation_preview()(image_out, synthetic.get("weak_labels") or [], preview_dir / split / f"{Path(image_name).stem}_boxed.jpg")
                synthetic.update(
                    {
                        "image": str(image_out),
                        "labels": str(label_out),
                        "url": self.layout.public_training_output_url()(image_out),
                        "annotated_url": annotated_url,
                        "source_sample_id": sample.get("sample_id"),
                        "source_record_id": sample.get("record_id"),
                        "label_status": sample.get("label_status") or "",
                        "split": split,
                    }
                )
                sample_records.append(synthetic)
                continue
            source_path = self.publication.resolve_service_path()((sample.get("source_image") or {}).get("path"))
            image = self.publication._image_files().imread(str(source_path), cv2.IMREAD_COLOR)
            if image is None:
                continue
            self.publication._business_files().copy2(source_path, image_out, local_copy=shutil.copy2)
            self.publication._business_files().write_text(label_out, "", encoding="utf-8")
            annotated_path = preview_dir / split / f"{Path(image_name).stem}_negative.jpg"
            annotated_path.parent.mkdir(parents=True, exist_ok=True)
            self.publication._image_files().imwrite(str(annotated_path), image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            sample_records.append(
                {
                    "image": str(image_out),
                    "labels": str(label_out),
                    "url": self.layout.public_training_output_url()(image_out),
                    "annotated_url": self.layout.public_training_output_url()(annotated_path),
                    "source_sample_id": sample.get("sample_id"),
                    "source_record_id": sample.get("record_id"),
                    "split": split,
                    "sample_type": "real_negative_empty_label",
                    "label_status": sample.get("label_status") or "",
                    "label_count": 0,
                    "weak_labels": [],
                }
            )
        if not sample_records:
            return None
        yaml_path = dataset_dir / "dataset.yaml"
        self.layout.write_dataset_yaml()(yaml_path, dataset_dir, class_names)
        manifest = {
            "id": dataset_id,
            "task_id": task_id,
            "created_at": int(time.time()),
            "display_name": f"自动优化弱标注数据集 · {state.get('task_name') or task_id}",
            "mode": "yolo",
            "model_variant": "yolo",
            "sample_count": len(sample_records),
            "selected_accessory_ids": selected_ids,
            "required_accessory_counts": {item_id: 1 for item_id in selected_ids},
            "accessory_class_map": {str(idx): item_id for item_id, idx in class_index.items()},
            "class_accessory_map": {item_id: idx for item_id, idx in class_index.items()},
            "ocr_accessory_ids": [],
            "class_names": class_names,
            "dataset_yaml": str(yaml_path),
            "positive_sample_count": len([item for item in sample_records if int(item.get("label_count") or 0) > 0]),
            "negative_sample_count": len([item for item in sample_records if int(item.get("label_count") or 0) == 0]),
            "real_positive_source_count": len(positive_samples) + len(bbox_only_samples),
            "real_bbox_source_count": len([sample for sample in real_bbox_source_samples if self.sources.auto_optimize_bbox_training_entries()(sample)]),
            "real_bbox_sample_weight": self.sources.AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT(),
            "real_bbox_only_source_count": len(bbox_only_samples),
            "real_negative_source_count": len(negative_samples),
            "negative_samples_per_real_image": negative_samples_per_real_image,
            "positive_derivatives_per_real_image": positive_derivatives_per_real_image,
            "generated_negative_sample_count": len([item for item in sample_records if item.get("sample_type") == "synthetic_negative_empty_background"]),
            "samples_per_real_image": samples_per_real_image,
            "synthetic_sample_count": len([item for item in sample_records if item.get("sample_type") == "synthetic_positive_from_ai_mask_sprite"]),
            "real_bbox_sample_count": len([item for item in sample_records if item.get("sample_type") in {"real_positive_original_bbox", "real_positive_bbox_only"}]),
            "real_original_bbox_sample_count": len([item for item in sample_records if item.get("sample_type") == "real_positive_original_bbox"]),
            "real_bbox_only_sample_count": len([item for item in sample_records if item.get("sample_type") == "real_positive_bbox_only"]),
            "training_requirements": self.configuration.auto_optimize_training_requirements(
                state.get("settings") if isinstance(state.get("settings"), dict) else {},
                real_positive_source_count=len(positive_samples) + len(bbox_only_samples),
            ),
            "pass_fail_rule": "synthetic_from_ai_detection_ai_mask_sprite",
            "sample_generation_policy": {
                "source": "real_detection_photo_ai_mask_sprite_augmentation",
                "primary_detector": "ai_api",
                "label_shape": "object_bounding_box",
                "mask_quality_gate": "ai_detection_class_set_matches_ai_mask_color_set",
                "positive_samples": "ai_mask_sprites_are_pasted_on_green_conveyor_background_with_controlled_rotation",
                "samples_per_real_image": samples_per_real_image,
                "positive_derivatives_per_real_image": positive_derivatives_per_real_image,
                "real_detection_bbox_original_weight": self.sources.AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT(),
                "real_detection_bbox_originals": "verifier_or_manual_approved_original_detection_images_are_oversampled_in_train_split_as_trusted_bbox_labels",
                "background_set_id": dataset_background_set_id,
                "negative_samples": "ai_detection_absent_images_are_kept_as_real_empty_yolo_labels; generated_empty_background_negatives_are_part_of_the_per_real_image_derivative_budget",
                "negative_samples_per_real_image": negative_samples_per_real_image,
                "existing_training_pipeline_modified": False,
            },
            "samples": sample_records,
            "owner_user_id": str(state.get("owner_user_id") or ""),
            "owner_username": str(state.get("owner_username") or ""),
        }
        manifest_path = dataset_dir / "manifest.json"
        self.publication._business_files().write_text(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "id": dataset_id,
            "dataset_dir": str(dataset_dir),
            "dataset_yaml": str(yaml_path),
            "manifest_path": str(manifest_path),
            "sample_count": len(sample_records),
            "synthetic_sample_count": manifest["synthetic_sample_count"],
            "real_positive_source_count": len(positive_samples) + len(bbox_only_samples),
            "real_bbox_sample_count": manifest["real_bbox_sample_count"],
            "real_bbox_sample_weight": self.sources.AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT(),
            "real_negative_source_count": len(negative_samples),
            "generated_negative_sample_count": manifest["generated_negative_sample_count"],
            "negative_samples_per_real_image": negative_samples_per_real_image,
            "samples_per_real_image": samples_per_real_image,
            "selected_accessory_ids": selected_ids,
            "display_name": manifest["display_name"],
            "background_set_id": dataset_background_set_id,
            "created_at": manifest["created_at"],
        }
