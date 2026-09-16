"""Source preparation with unchanged crop ordering and partial-file behavior."""
from pathlib import Path
from typing import Any
from .policy import accessory_uid, accessory_material_type
from .preparation_ports import PreparationPaths, TextPreparation, ReferenceMedia, RefreshPreparation, RefreshProfiles


def build_object_view_plan(name: str) -> list[dict[str, Any]]:
    return [
        {"view": "front", "angle": 0, "scale": "1.00x"},
        {"view": "left_oblique", "angle": -45, "scale": "0.90x"},
        {"view": "right_oblique", "angle": 45, "scale": "1.10x"},
        {"view": "top", "angle": 90, "scale": "0.85x"},
        {"view": "lying_horizontal", "angle": 180, "scale": "1.00x"},
        {"view": "standing", "angle": "cap diameter calibrated", "scale": "matched_to_proxy_length"},
    ]


def defer_accessory_normalization(item: dict[str, Any]) -> None:
    item["normalized_assets"] = []
    for key in (
        "clean_sprite_status",
        "clean_sprite_count",
        "clean_sprite_expected_count",
        "clean_sprite_failed_cells",
        "clean_sprite_preprocessed_at",
    ):
        item.pop(key, None)
    item["normalization_deferred"] = True
    item["preprocess"] = "已保存用户上传素材；任务进入生成样本阶段后再生成规范化文件。"


class AccessoryPreparation:
    def __init__(self, paths: PreparationPaths, text: TextPreparation, media: ReferenceMedia):
        self.paths, self.text, self.media = paths, text, media

    def normalize_accessory_assets(self, item: dict[str, Any]) -> dict[str, Any]:
        normalized_dir = self.paths.normalized() / accessory_uid(item)
        normalized_dir.mkdir(parents=True, exist_ok=True)
        source_files = [Path(path) for path in item.get("source_files", [])]
        image_sources = [path for path in source_files if path.suffix.lower() in self.paths.image_suffixes()]
        material_type = accessory_material_type(item)
        if material_type == "text":
            assets = []
            physical_size = item.get("physical_size") if isinstance(item.get("physical_size"), dict) else {}
            skipped_for_manual_crop = False
            rectified_sources = [path for path in image_sources if self.text.is_rectified(path)]
            raw_sources = [path for path in image_sources if not self.text.is_rectified(path)]
            text_sources = rectified_sources + raw_sources
            original_sources = [
                Path(str(path))
                for path in (item.get("original_source_files") or [])
                if Path(str(path)).suffix.lower() in self.paths.image_suffixes() and not self.text.is_rectified(path)
            ]
            crop_required_sources = original_sources or raw_sources
            all_required_sources_cropped = all(self.text.has_rectified(path, rectified_sources) for path in crop_required_sources)
            for src in text_sources[:self.text.max_images()]:
                if not self.text.is_rectified(src):
                    skipped_for_manual_crop = True
                    continue
                normalized = self.text.normalize(src, normalized_dir, physical_size)
                if normalized:
                    assets.append(normalized)
                else:
                    skipped_for_manual_crop = True
            manual_crop_required = bool(crop_required_sources) and not all_required_sources_cropped
            manual_crop_reason = ""
            if manual_crop_required:
                manual_crop_reason = "manual_crop_required"
            elif not assets and skipped_for_manual_crop:
                manual_crop_reason = "manual_crop_required"
            return {
                "status": "normalized_text_ready" if assets and not manual_crop_required else "needs_crop",
                "normalized_assets": assets,
                "manual_crop_required": manual_crop_required or (not assets and skipped_for_manual_crop),
                "manual_crop_reason": manual_crop_reason,
                "preprocess": "用户裁剪包含完整文字的文档图像，系统进行透视校正并生成规整说明书图。",
            }
        prompt = (
            f"Image-to-image asset expansion for '{item.get('name', 'accessory')}'. "
            "Generate clean isolated product views with consistent material, multiple angles, "
            "standing/lying poses when applicable, calibrated size variants, object-only framing, "
            "no background/backing/surface/shadows, and transparent PNG alpha when supported."
        )
        return {
            "status": "image_tool_plan_ready",
            "normalized_assets": [
                {
                    "kind": "object_view_plan",
                    "source_files": [str(path) for path in image_sources],
                    "image_tool_prompt": prompt,
                    "view_plan": build_object_view_plan(str(item.get("name", "accessory"))),
                }
            ],
            "preprocess": "系统记录 Image tool 扩展计划，用于生成多视角、多尺寸辅助素材。",
        }

    def expand_accessory_reference_sources(self, candidate_id: str, source_files: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
        expanded = list(source_files)
        extracted_frames: list[dict[str, Any]] = []
        frame_dir = self.paths.uploads() / "accessory_candidates" / candidate_id / "video_reference_frames"
        for path_str in source_files:
            path = Path(path_str)
            if path.suffix.lower() not in self.paths.video_suffixes():
                continue
            frames = self.media.extract_frames(path, frame_dir)
            extracted_frames.extend(frames)
            expanded.extend(frame["path"] for frame in frames)
        return expanded, extracted_frames

    def ensure_default_ai_profile_reference(self, item: dict[str, Any]) -> bool:
        current_refs = [str(path) for path in self.media.profile_paths(item)]
        if current_refs:
            if item.get("ai_profile_reference_files") != current_refs:
                item["ai_profile_reference_files"] = current_refs
                return True
            return False
        first_source = self.media.first_source(item)
        if not first_source:
            return False
        item["ai_profile_reference_files"] = [str(first_source)]
        return True


class AccessoryRefresh:
    def __init__(self, preparation: RefreshPreparation, profiles: RefreshProfiles):
        self.preparation, self.profiles = preparation, profiles

    def refresh_accessory_assets_after_source_change(self, item: dict[str, Any], *, force_profile: bool = True) -> None:
        if accessory_material_type(item) == "text":
            item.update(self.preparation.normalize(item))
            item["normalization_deferred"] = False
        else:
            self.preparation.defer(item)
        self.preparation.ensure_reference(item)
        if force_profile:
            item["ai_profile"] = self.profiles.fallback(item)
            item["ai_profile_status"] = "ready"
            self.profiles.generate(item, allow_provider=True)
