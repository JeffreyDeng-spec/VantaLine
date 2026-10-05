"""Training mask sprite crop, normalization and public metadata publication."""
from dataclasses import dataclass
from typing import Any
from pathlib import Path
import cv2
import numpy as np
from .auto_optimization_sprite_publication_ports import SpritePublication

@dataclass(frozen=True)
class AutoOptimizationSpritePublication:
    publication: SpritePublication

    def auto_optimize_write_sprite_artifact(self,
        *,
        image_bgr: np.ndarray,
        full_mask: np.ndarray,
        bbox: list[int],
        sample_id: str,
        accessory_id: str,
        label_name: str,
        artifact_dir: Path,
        source_image_path: Path,
    ) -> dict[str, Any]:
        x1, y1, x2, y2 = [int(value) for value in bbox[:4]]
        height, width = image_bgr.shape[:2]
        x1 = max(0, min(x1, width - 1))
        y1 = max(0, min(y1, height - 1))
        x2 = max(x1 + 1, min(x2, width))
        y2 = max(y1 + 1, min(y2, height))
        roi_bgr = image_bgr[y1:y2, x1:x2].copy()
        roi_mask = full_mask[y1:y2, x1:x2].copy()
        safe_accessory_id = self.publication.safe_record_id()(accessory_id or label_name or "target")
        sprite_dir = artifact_dir / "sprites"
        sprite_dir.mkdir(parents=True, exist_ok=True)
        raw_path = sprite_dir / f"{sample_id}_{safe_accessory_id}_sprite_raw.png"
        normalized_path = sprite_dir / f"{sample_id}_{safe_accessory_id}_sprite.png"
        bgra = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2BGRA)
        bgra[:, :, 3] = roi_mask
        self.publication._image_files().imwrite(str(raw_path), bgra)
        metadata = {
            "task_id": "auto_optimize",
            "source_sample_id": sample_id,
            "accessory_id": accessory_id,
            "label": label_name,
            "source_image_path": str(source_image_path),
            "source_object_bbox_xyxy": [x1, y1, x2, y2],
            "source_object_size_px": [int(x2 - x1), int(y2 - y1)],
            "source_pose_family": "real_photo_ai_mask",
            "pose_family": "real_photo_ai_mask",
            "source_pose_collection_job_id": "auto_optimize_ai_mask",
            "object_alpha_material_policy": "ai_mask_visible_object",
            "transparent_alpha_policy": "ai_mask_alpha",
        }
        normalized = self.publication.write_clean_sprite()(normalized_path, roi_bgr, roi_mask, metadata) or {}
        chosen_path = self.publication.resolve_service_path()(normalized.get("path") or normalized_path)
        if not self.publication._business_files().exists(chosen_path):
            chosen_path = raw_path
        return {
            "accessory_id": accessory_id,
            "label": label_name,
            "status": "available" if self.publication._business_files().exists(chosen_path) else "failed",
            "path": str(chosen_path),
            "url": self.publication.public_output_url_for_existing()(chosen_path),
            "raw_path": str(raw_path),
            "raw_url": self.publication.public_output_url_for_existing()(raw_path),
            "bbox_xyxy": [x1, y1, x2, y2],
            "width": int(roi_bgr.shape[1]),
            "height": int(roi_bgr.shape[0]),
            "source_sample_id": sample_id,
            "source_image_path": str(source_image_path),
            "normalized": self.publication.public_path_sanitized()(normalized),
        }
