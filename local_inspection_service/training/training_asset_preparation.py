"""Training asset validation, preparation and partial-progress persistence."""
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any
from .training_asset_preparation_ports import TrainingAssetPolicy, TrainingAssetPersistence

@dataclass(frozen=True)
class TrainingAssetPreparation:
    policy: TrainingAssetPolicy
    persistence: TrainingAssetPersistence

    def ensure_object_clean_sprites_for_selection(self, config: dict[str, Any], ids: list[str]) -> bool:
        wanted = set(ids)
        changed = False
        for item in config.get("accessories", []):
            uid = self.policy.accessory_uid()(item)
            if wanted and uid not in wanted:
                continue
            if self.policy.accessory_material_type()(item) == "text":
                continue
            sprites = self.policy.clean_sprite_assets()(item)
            pose_jobs = [
                job
                for job in self.policy.candidate_image_jobs()(item)
                if self.policy._business_files().exists(Path(str(job.get("output_path", "")))) and not job.get("intermediate")
            ]
            expected_count = min(18, len(pose_jobs) * len(self.policy.POSE_COLLECTION_GRID_POSITIONS())) if pose_jobs else len(sprites)
            if sprites and len(sprites) >= expected_count and self.policy.clean_sprites_policy_complete()(item, sprites):
                continue
            changed = self.policy.preprocess_object_clean_sprites()(item, allow_ai_cutout=True, force=bool(sprites and pose_jobs)) or changed
        return changed


    def ensure_training_normalized_assets_for_selection(self, config: dict[str, Any], ids: list[str]) -> bool:
        wanted = set(ids)
        if not wanted:
            raise self.policy.HTTPException()(status_code=400, detail="流水线任务还没有选择配件")
        changed = False
        found: set[str] = set()
        for item in config.get("accessories", []):
            uid = self.policy.accessory_uid()(item)
            if uid not in wanted:
                continue
            found.add(uid)
            if self.policy.accessory_material_type()(item) == "text":
                text_assets = self.policy.canonical_text_assets()(item)
                if item.get("normalization_deferred") or not self.policy.canonical_text_assets_complete()(item, text_assets):
                    item.update(self.policy.normalize_accessory_assets()(item))
                    changed = True
                if not self.policy.canonical_text_assets_complete()(item):
                    raise self.policy.HTTPException()(status_code=409, detail=f"配件 {item.get('name') or uid} 的文字规范化文件生成失败")
            else:
                photo_sources = self.policy.object_photo_highlight_source_paths()(item)
                photo_sprites_ready = self.policy.photo_highlight_clean_sprites_ready()(item, photo_sources)
                if not photo_sprites_ready:
                    if len(photo_sources) < self.policy.PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES():
                        raise self.policy.HTTPException()(
                            status_code=409,
                            detail=(
                                f"配件 {item.get('name') or uid} 至少需要 "
                                f"{self.policy.PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES()} 张不同角度实拍图"
                            ),
                        )
                    raise self.policy.HTTPException()(status_code=409, detail=f"配件 {item.get('name') or uid} 的实拍高亮抠图素材尚未生成")
                sprites = self.policy.clean_sprite_assets()(item)
                if not sprites:
                    raise self.policy.HTTPException()(status_code=409, detail=f"配件 {item.get('name') or uid} 的物品规范化文件生成失败")
            if item.get("normalization_deferred"):
                item["normalization_deferred"] = False
                changed = True
            item["normalized_for_training_at"] = int(time.time())
        missing = wanted - found
        if missing:
            raise self.policy.HTTPException()(status_code=404, detail=f"配件不存在: {', '.join(sorted(missing))}")
        return changed


    def ensure_training_assets_for_request(self,
        full_config: dict[str, Any],
        scoped_config: dict[str, Any],
        user: dict[str, Any],
        ids: list[str],
    ) -> bool:
        try:
            changed = self.persistence.ensure_training_normalized_assets_for_selection()(scoped_config, ids)
        except self.policy.HTTPException():
            self.persistence.merge_scoped_accessory_updates()(full_config, scoped_config, user)
            self.persistence.save_config()(full_config)
            raise
        if changed:
            self.persistence.merge_scoped_accessory_updates()(full_config, scoped_config, user)
            self.persistence.save_config()(full_config)
        return changed
