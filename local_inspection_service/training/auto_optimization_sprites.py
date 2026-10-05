"""Automatic training sprite records, backfill and canonical size policy."""
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
import time
import cv2
import numpy as np

from .auto_optimization_sprites_ports import SpriteFiles, SpriteGeometry


@dataclass(frozen=True)
class AutoOptimizationSprites:
    files: SpriteFiles
    geometry: SpriteGeometry

    def auto_optimize_load_sprite(self, sprite: dict[str, Any]) -> tuple[np.ndarray, np.ndarray] | None:
        path = self.files.resolve_service_path()(sprite.get("path") or sprite.get("raw_path") or "")
        image = self.files._image_files().imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is None or image.size == 0:
            return None
        if image.ndim == 3 and image.shape[2] == 4:
            return image[:, :, :3].copy(), image[:, :, 3].copy()
        if image.ndim == 3:
            return image.copy(), np.full(image.shape[:2], 255, dtype=np.uint8)
        return None

    def auto_optimize_sprite_records_for_sample(self, sample: dict[str, Any]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for label in sample.get("labels") or []:
            if not isinstance(label, dict):
                continue
            sprite = label.get("sprite") if isinstance(label.get("sprite"), dict) else {}
            if not sprite.get("path") and not sprite.get("raw_path"):
                continue
            accessory_id = str(label.get("accessory_id") or sprite.get("accessory_id") or "")
            if not accessory_id:
                continue
            records.append(
                {
                    **sprite,
                    "accessory_id": accessory_id,
                    "label": label.get("label") or sprite.get("label") or accessory_id,
                    "source_sample_id": sample.get("sample_id"),
                    "source_record_id": sample.get("record_id"),
                    "source_image_path": (sample.get("source_image") or {}).get("path") if isinstance(sample.get("source_image"), dict) else "",
                }
            )
        return records

    def auto_optimize_resolve_artifact_path(self, value: Any) -> Path:
        raw = str(value or "").strip()
        if not raw:
            return Path("")
        raw = raw.split("?", 1)[0]
        if raw.startswith("/outputs/"):
            return (self.files.OUTPUT_DIR() / PurePosixPath(raw.removeprefix("/outputs/").lstrip("/"))).resolve()
        if raw.startswith("/static/"):
            return (self.files.STATIC_DIR() / PurePosixPath(raw.removeprefix("/static/").lstrip("/"))).resolve()
        return self.files.resolve_service_path()(raw)

    def auto_optimize_backfill_missing_sprites_for_sample(self, task_id: str, state: dict[str, Any], sample: dict[str, Any]) -> int:
        labels = [label for label in sample.get("labels") or [] if isinstance(label, dict)]
        missing = [
            label
            for label in labels
            if not ((label.get("sprite") if isinstance(label.get("sprite"), dict) else {}).get("path") or (label.get("sprite") if isinstance(label.get("sprite"), dict) else {}).get("raw_path"))
        ]
        if not missing:
            return 0
        artifacts = sample.get("label_artifacts") if isinstance(sample.get("label_artifacts"), dict) else {}
        color_mask_url = artifacts.get("color_mask_url") or artifacts.get("mask_url")
        source_image = sample.get("source_image") if isinstance(sample.get("source_image"), dict) else {}
        image_path = self.files.auto_optimize_resolve_artifact_path()(source_image.get("path") or source_image.get("url") or "")
        color_mask_path = self.files.auto_optimize_resolve_artifact_path()(color_mask_url or "")
        image_bgr = self.files._image_files().imread(str(image_path), cv2.IMREAD_COLOR)
        mask_bgr = self.files._image_files().imread(str(color_mask_path), cv2.IMREAD_COLOR)
        if image_bgr is None or mask_bgr is None:
            return 0
        height, width = image_bgr.shape[:2]
        if mask_bgr.shape[:2] != (height, width):
            mask_bgr = cv2.resize(mask_bgr, (width, height), interpolation=cv2.INTER_NEAREST)
        owner_id = str(state.get("owner_user_id") or sample.get("owner_user_id") or "")
        artifact_dir = self.files.output_write_dir_for_owner()("auto_optimize_masks", owner_id) / self.files.safe_record_id()(task_id)
        sample_id = self.files.safe_record_id()(str(sample.get("sample_id") or "sample"))
        rebuilt = 0
        non_black = (np.max(mask_bgr, axis=2) > 8).astype(np.uint8) * 255
        for label in missing:
            bbox = label.get("bbox_xyxy")
            if not isinstance(bbox, list) or len(bbox) < 4:
                continue
            x1, y1, x2, y2 = [int(value) for value in bbox[:4]]
            x1 = max(0, min(x1, width - 1))
            y1 = max(0, min(y1, height - 1))
            x2 = max(x1 + 1, min(x2, width))
            y2 = max(y1 + 1, min(y2, height))
            full_mask = np.zeros((height, width), dtype=np.uint8)
            full_mask[y1:y2, x1:x2] = non_black[y1:y2, x1:x2]
            if int(np.count_nonzero(full_mask)) <= 0:
                continue
            accessory_id = str(label.get("accessory_id") or "")
            label_name = str(label.get("label") or accessory_id or "target")
            sprite_artifact = self.files.auto_optimize_write_sprite_artifact()(
                image_bgr=image_bgr,
                full_mask=full_mask,
                bbox=[x1, y1, x2, y2],
                sample_id=sample_id,
                accessory_id=accessory_id,
                label_name=label_name,
                artifact_dir=artifact_dir,
                source_image_path=image_path,
            )
            label["sprite"] = sprite_artifact
            label.setdefault("mask_meta", {})
            if isinstance(label["mask_meta"], dict):
                label["mask_meta"].setdefault("processing_artifacts", {})
                if isinstance(label["mask_meta"]["processing_artifacts"], dict):
                    label["mask_meta"]["processing_artifacts"]["transparent_sprite_url"] = sprite_artifact.get("url") or ""
                    label["mask_meta"]["processing_artifacts"]["raw_transparent_sprite_url"] = sprite_artifact.get("raw_url") or ""
            rebuilt += 1
        if rebuilt:
            sample["sprite_backfilled_at"] = int(time.time())
            sample["sprite_backfill_count"] = int(sample.get("sprite_backfill_count") or 0) + rebuilt
        return rebuilt

    def auto_optimize_public_sprite_pool(self, state: dict[str, Any], limit: int = 80) -> list[dict[str, Any]]:
        sprites: list[dict[str, Any]] = []
        for sample in state.get("samples") or []:
            if not isinstance(sample, dict) or sample.get("label_status") != "trainable":
                continue
            sprites.extend(self.geometry.auto_optimize_sprite_records_for_sample()(sample))
        return [self.files.public_path_sanitized()(sprite) for sprite in sprites[:limit]]

    def auto_optimize_sprite_visible_size(self, sprite_mask: np.ndarray) -> tuple[int, int] | None:
        bbox = self.geometry.alpha_bbox()(sprite_mask, threshold=8)
        width = int(bbox[2] - bbox[0])
        height = int(bbox[3] - bbox[1])
        if width <= 0 or height <= 0:
            return None
        return max(1, width), max(1, height)

    def auto_optimize_source_to_canvas_scale(self, source_path_value: Any, cache: dict[str, float]) -> float:
        source_path = str(source_path_value or "").strip()
        if not source_path:
            return 1.0
        if source_path in cache:
            return cache[source_path]
        path = self.files.resolve_service_path()(source_path)
        image = self.files._image_files().imread(str(path), cv2.IMREAD_COLOR)
        if image is None or image.size == 0:
            cache[source_path] = 1.0
            return 1.0
        source_h, source_w = image.shape[:2]
        canvas_w, canvas_h = self.geometry.AUTO_OPTIMIZE_SYNTHETIC_CANVAS_SIZE()
        scale = min(float(canvas_w) / max(1, source_w), float(canvas_h) / max(1, source_h))
        cache[source_path] = max(0.01, min(self.geometry.AUTO_OPTIMIZE_SYNTHETIC_MAX_UPSCALE(), scale))
        return cache[source_path]

    def auto_optimize_canonical_sprite_sizes(self, state: dict[str, Any], extra_sprites: list[dict[str, Any]] | None = None) -> dict[str, dict[str, int]]:
        grouped: dict[str, list[tuple[int, int]]] = defaultdict(list)
        source_scale_cache: dict[str, float] = {}
        records: list[dict[str, Any]] = []
        for sample in state.get("samples") or []:
            if not isinstance(sample, dict) or sample.get("label_status") != "trainable":
                continue
            records.extend(self.geometry.auto_optimize_sprite_records_for_sample()(sample))
        records.extend(extra_sprites or [])
        seen: set[tuple[str, str]] = set()
        for sprite in records:
            if not isinstance(sprite, dict):
                continue
            accessory_id = str(sprite.get("accessory_id") or "")
            if not accessory_id:
                continue
            sprite_key = str(sprite.get("path") or sprite.get("raw_path") or "")
            seen_key = (accessory_id, sprite_key)
            if sprite_key and seen_key in seen:
                continue
            if sprite_key:
                seen.add(seen_key)
            loaded = self.geometry.auto_optimize_load_sprite()(sprite)
            if loaded is None:
                continue
            _, sprite_mask = loaded
            visible_size = self.geometry.auto_optimize_sprite_visible_size()(sprite_mask)
            if not visible_size:
                continue
            width, height = visible_size
            scale = self.geometry.auto_optimize_source_to_canvas_scale()(sprite.get("source_image_path"), source_scale_cache)
            width = max(1, int(round(width * scale)))
            height = max(1, int(round(height * scale)))
            grouped[accessory_id].append((max(width, height), min(width, height)))
        canonical: dict[str, dict[str, int]] = {}
        for accessory_id, sizes in grouped.items():
            if not sizes:
                continue
            canonical[accessory_id] = {
                "long": max(18, int(round(float(np.median([item[0] for item in sizes]))))),
                "short": max(18, int(round(float(np.median([item[1] for item in sizes]))))),
                "source_count": len(sizes),
            }
        return canonical

    def auto_optimize_sprite_target_size(self,
        sprite_mask: np.ndarray,
        canonical_size: dict[str, int] | None = None,
    ) -> tuple[int, int]:
        visible_size = self.geometry.auto_optimize_sprite_visible_size()(sprite_mask)
        if not visible_size:
            return 18, 18
        source_w, source_h = visible_size
        if canonical_size:
            long_side = max(18, int(canonical_size.get("long") or max(source_w, source_h)))
            short_side = max(18, int(canonical_size.get("short") or min(source_w, source_h)))
            if source_w >= source_h:
                return long_side, short_side
            return short_side, long_side
        return max(18, source_w), max(18, source_h)
