"""Ordered sprite fingerprints and preview metadata completeness checks."""
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

Record = dict[str, Any]


@dataclass(frozen=True)
class SpriteVersionInputs:
    sprites: Callable[[Record], list[Record]]
    uid: Callable[[Record], str]
    material: Callable[[Record], str]
    alpha_policy: Callable[[Record], str]


class TrainingPreviewCache:
    def __init__(self, inputs: SpriteVersionInputs, schema: Callable[[], str],
                 resolve: Callable[[], Callable[[Any], Path]], version: Callable[[Record], str]):
        self.inputs, self.schema, self.resolve, self.version = inputs, schema, resolve, version

    def accessory_sprite_version(self, item: dict[str, Any]) -> str:
        sprites = self.inputs.sprites(item)
        parts = [
            self.schema(),
            str(self.inputs.uid(item)),
            str(self.inputs.material(item)),
            str(self.inputs.alpha_policy(item)) if self.inputs.material(item) == "object" else "",
            json.dumps(item.get("physical_size") or {}, sort_keys=True, separators=(",", ":")),
            str(item.get("clean_sprite_status") or ""),
            str(item.get("clean_sprite_preprocessed_at") or 0),
            str(item.get("clean_sprite_count") or len(sprites)),
            str(item.get("clean_sprite_expected_count") or ""),
        ]
        for idx, asset in enumerate(sprites):
            path = self.resolve()(asset.get("path"))
            try:
                stat = path.stat()
                mtime_ns = stat.st_mtime_ns
                size = stat.st_size
            except OSError:
                mtime_ns = 0
                size = 0
            parts.extend(
                [
                    str(idx + 1),
                    str(path),
                    str(mtime_ns),
                    str(size),
                    str(asset.get("task_id") or ""),
                    str(asset.get("source_position") or asset.get("pose_position") or ""),
                    str(asset.get("source_pose_family") or asset.get("pose_family") or ""),
                    str(asset.get("material_alpha_policy") or ""),
                    str(asset.get("object_alpha_material_policy") or ""),
                    json.dumps(asset.get("physical_size_mm") or {}, sort_keys=True, separators=(",", ":")),
                    json.dumps(asset.get("source_object_bbox_xyxy") or [], separators=(",", ":")),
                    json.dumps(asset.get("source_object_size_px") or [], separators=(",", ":")),
                    str(asset.get("source_long_side_px") or ""),
                    str(asset.get("source_short_side_px") or ""),
                    str(asset.get("source_long_edge_axis") or ""),
                    str(asset.get("source_short_edge_axis") or ""),
                    str(asset.get("source_long_short_ratio") or ""),
                    json.dumps(asset.get("normalized_bbox_xyxy") or [], separators=(",", ":")),
                    json.dumps(asset.get("render_footprint_px") or [], separators=(",", ":")),
                    json.dumps(asset.get("render_footprint_mm") or [], separators=(",", ":")),
                    json.dumps(asset.get("render_size_hint_px") or [], separators=(",", ":")),
                ]
            )
        return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]

    def preview_cache_key(self, selected: list[dict[str, Any]]) -> str:
        raw = "|".join(f"{self.inputs.uid(item)}:{self.version(item)}" for item in selected)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def training_preview_metadata_missing(self, training: dict[str, Any], selected: list[dict[str, Any]]) -> bool:
        has_object = any(self.inputs.material(item) == "object" for item in selected)
        has_preview_state = bool(training.get("preview_urls") or training.get("previews") or training.get("last_preview_id"))
        if not has_object or not has_preview_state:
            return False
        if not training.get("preview_cache_key"):
            return True
        sprite_versions = training.get("preview_sprite_versions")
        return not isinstance(sprite_versions, dict) or not sprite_versions
