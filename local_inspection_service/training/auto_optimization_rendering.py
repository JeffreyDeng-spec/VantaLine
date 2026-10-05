"""Synthetic positive image rendering and ordered artifact publication."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import numpy as np
from .auto_optimization_rendering_ports import SyntheticGeometry, SyntheticPublication

@dataclass(frozen=True)
class AutoOptimizationRendering:
    geometry: SyntheticGeometry
    publication: SyntheticPublication

    def auto_optimize_render_synthetic_sample(
        self,
        *,
        sprites: list[dict[str, Any]],
        class_index: dict[str, int],
        accessories_by_id: dict[str, dict[str, Any]],
        output_path: Path,
        label_path: Path,
        annotated_path: Path,
        split: str,
        rng: np.random.Generator,
        canonical_sizes: dict[str, dict[str, int]] | None = None,
        background_set_id: str | None = None,
    ) -> dict[str, Any] | None:
        requested_background_set_id = self.publication.safe_background_set_id()(background_set_id or "green_conveyor")
        canvas, background_meta = self.publication.render_training_background()(rng, split, requested_background_set_id)
        effective_background_set_id = str(background_meta.get("background_set_id") or requested_background_set_id or "green_conveyor")
        placed_objects: list[dict[str, Any]] = []
        labels: list[dict[str, Any]] = []
        for sprite in sprites:
            accessory_id = str(sprite.get("accessory_id") or "")
            if accessory_id not in class_index:
                continue
            loaded = self.geometry.auto_optimize_load_sprite()(sprite)
            if loaded is None:
                continue
            sprite_image, sprite_mask = loaded
            accessory = accessories_by_id.get(accessory_id) or {"id": accessory_id, "name": sprite.get("label") or accessory_id}
            target_size = self.geometry.auto_optimize_sprite_target_size()(sprite_mask, (canonical_sizes or {}).get(accessory_id))
            angle = float(rng.uniform(-180.0, 180.0))
            center, placement_meta = self.geometry.choose_object_center_inside_background()(rng, target_size, angle, placed_objects)
            pasted = self.geometry.paste_masked_asset()(
                canvas,
                sprite_image,
                sprite_mask,
                center,
                target_size,
                angle,
                return_visible_mask=True,
            )
            if not isinstance(pasted, tuple):
                continue
            canvas, visible_mask = pasted
            bbox = self.geometry.alpha_bbox()(visible_mask, threshold=8)
            if bbox == [0, 0, 0, 0]:
                continue
            placed_objects.append({"id": accessory_id, "rect": self.geometry.rotated_rect_tuple()(center, target_size, angle)})
            labels.append(
                {
                    "id": accessory_id,
                    "name": str(accessory.get("name") or sprite.get("label") or accessory_id),
                    "amodal_bbox_xyxy": bbox,
                    "bbox_xyxy": bbox,
                    "angle": round(angle, 2),
                    "center_xy": [int(center[0]), int(center[1])],
                    "render_size_px": [int(target_size[0]), int(target_size[1])],
                    "render_size_policy": self.geometry.AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY(),
                    "canonical_render_size": (canonical_sizes or {}).get(accessory_id) or {},
                    "source_sample_id": sprite.get("source_sample_id"),
                    "source_record_id": sprite.get("source_record_id"),
                    "sprite_path": sprite.get("path") or sprite.get("raw_path"),
                    "synthetic_from_real_sprite": True,
                    **placement_meta,
                }
            )
        if not labels:
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        label_path.parent.mkdir(parents=True, exist_ok=True)
        self.publication._image_files().imwrite(str(output_path), canvas)
        height, width = canvas.shape[:2]
        lines = [
            line
            for line in (
                self.publication.yolo_detection_label_line()(class_index[str(label["id"])], label.get("amodal_bbox_xyxy"), width=width, height=height)
                for label in labels
            )
            if line
        ]
        self.publication._business_files().write_text(label_path, "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        annotated_url = self.publication.write_training_annotation_preview()(output_path, labels, annotated_path)
        return {
            "image": str(output_path),
            "labels": str(label_path),
            "annotated_path": str(annotated_path),
            "url": self.publication.public_training_output_url()(output_path),
            "annotated_url": annotated_url,
            "split": split,
            "is_true": True,
            "sample_type": "synthetic_positive_from_ai_mask_sprite",
            "label_count": len(lines),
            "weak_labels": labels,
            "background": background_meta,
            "source_sample_ids": sorted({str(label.get("source_sample_id") or "") for label in labels if label.get("source_sample_id")}),
            "source_record_ids": sorted({str(label.get("source_record_id") or "") for label in labels if label.get("source_record_id")}),
            "augmentation": {
                "source": "real_photo_ai_mask_sprite",
                "rotation_policy": "uniform_-180_180",
                "background_set_id": effective_background_set_id,
                "requested_background_set_id": requested_background_set_id,
            },
        }
