"""Materialized accessory assets, metadata normalization and readiness."""
from typing import Any
import cv2
from .materialized_asset_ports import MaterializedAssetPaths, SpriteCatalogPoseOperations, SpriteCatalogMaterialPolicy, SpriteCatalogReadiness, TextCatalogOperations

def clean_sprite_metadata_complete(asset: dict[str, Any]) -> bool:
    required_keys = [
        "task_id",
        "source_pose_collection_job_id",
        "pose_family",
        "source_pose_family",
        "pose_position",
        "source_position",
        "original_orientation_angle",
        "original_orientation_angle_degrees",
        "rotation_degrees_applied",
        "rotation_degrees_applied_to_upright",
        "source_restore_rotation_degrees",
        "normalized_axis_target_degrees",
        "source_region_bbox_xyxy",
        "source_object_bbox_xyxy",
        "source_object_center_xy",
        "source_object_size_px",
        "normalized_asset_size_px",
        "normalized_asset_dimensions_px",
        "normalized_bbox_xyxy",
        "pre_rotation_safety_margin_px",
        "post_rotation_safety_margin_px",
        "edge_alpha_max",
        "edge_alpha_pass",
        "mask_strategy",
        "foreground_component_bbox_xyxy",
        "removed_stray_component_count",
        "removed_stray_component_area_px",
        "alpha_edge_stats",
        "transparent_alpha_policy",
        "material_alpha_policy",
        "object_alpha_material_policy",
        "render_scale_basis",
        "render_footprint_mm",
        "render_footprint_px",
        "canonical_width_px",
        "canonical_height_px",
        "physical_footprint_basis",
        "source_long_side_px",
        "source_short_side_px",
        "source_long_edge_axis",
        "source_short_edge_axis",
        "source_long_short_ratio",
        "source_length_width_rule",
    ]
    return all(asset.get(key) is not None for key in required_keys)

def text_accessory_confirm_detail(
    item: dict[str, Any],
    text_assets: list[dict[str, Any]],
    text_assets_complete: bool,
    profile_ready: bool,
) -> dict[str, Any]:
    status = item.get("ai_profile_status") if isinstance(item.get("ai_profile_status"), dict) else {}
    return {
        "message": "文字/文档素材未完成",
        "canonical_text_asset_count": len(text_assets),
        "canonical_text_assets_complete": text_assets_complete,
        "ai_profile_ready": profile_ready,
        "ai_profile_status": status.get("status") or "",
        "ai_profile_source": status.get("source") or "",
        "ai_profile_message": status.get("message") or "",
    }

class SpriteAssetCatalog:
    def __init__(self, paths: MaterializedAssetPaths, pose: SpriteCatalogPoseOperations, policy: SpriteCatalogMaterialPolicy, readiness: SpriteCatalogReadiness) -> None:
        self._paths = paths
        self._pose = pose
        self._policy = policy
        self._readiness = readiness

    def clean_sprite_assets(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        assets = []
        for asset in item.get("normalized_assets", []):
            if asset.get("kind") != "clean_object_sprite":
                continue
            path = self._paths.resolve()(asset.get("path"))
            if not path.exists() or path.suffix.lower() != ".png":
                continue
            asset["path"] = str(path)
            if not asset.get("width") or not asset.get("height"):
                image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
                if image is not None:
                    asset.setdefault("width", int(image.shape[1]))
                    asset.setdefault("height", int(image.shape[0]))
            if not asset.get("source_object_size_px") and asset.get("width") and asset.get("height"):
                asset["source_object_size_px"] = [int(asset.get("width")), int(asset.get("height"))]
            if not asset.get("source_pose_family") and not asset.get("pose_family"):
                source_size = asset.get("source_object_size_px") or [int(asset.get("width") or 1), int(asset.get("height") or 1)]
                asset["pose_family"] = "upright" if self._pose.top_view()("", source_size) else "lying"
                asset["source_pose_family"] = asset["pose_family"]
            if asset.get("source_pose_family") and not asset.get("pose_family"):
                asset["pose_family"] = asset.get("source_pose_family")
            if asset.get("pose_position") and not asset.get("source_position"):
                asset["source_position"] = asset.get("pose_position")
            if not asset.get("pose_position"):
                asset["pose_position"] = "center"
            if not asset.get("source_position"):
                asset["source_position"] = asset.get("pose_position")
            if not asset.get("source_image_size_px") and asset.get("source_image_width") and asset.get("source_image_height"):
                asset["source_image_size_px"] = [int(asset.get("source_image_width")), int(asset.get("source_image_height"))]
            if not asset.get("source_image_size_px") and asset.get("source_object_size_px"):
                asset["source_image_size_px"] = list(asset.get("source_object_size_px"))
                asset["source_image_width"] = int(asset["source_image_size_px"][0])
                asset["source_image_height"] = int(asset["source_image_size_px"][1])
            if not asset.get("physical_size_mm") and isinstance(item.get("physical_size"), dict):
                asset["physical_size_mm"] = item.get("physical_size")
            if asset.get("source_object_size_px"):
                pose_family = str(asset.get("source_pose_family") or asset.get("pose_family") or "")
                physical_size = asset.get("physical_size_mm") if isinstance(asset.get("physical_size_mm"), dict) else item.get("physical_size")
                asset.update(self._pose.footprint()(pose_family, asset.get("source_object_size_px"), physical_size))
            if asset.get("render_footprint_px") and not asset.get("render_size_hint_px"):
                asset["render_size_hint_px"] = asset.get("render_footprint_px")
            asset.setdefault("task_id", "legacy_clean_sprite")
            asset.setdefault("source_pose_collection_job_id", "legacy_clean_sprite")
            assets.append(asset)
        self._pose.upright()(assets, item.get("physical_size"))
        self._pose.laying()(assets)
        return assets

    def clean_sprite_material_policy_matches(self, item: dict[str, Any], asset: dict[str, Any]) -> bool:
        expected = self._policy.expected()(item)
        asset_policy = self._policy.normalize()(asset.get("material_alpha_policy"))
        return bool(asset_policy and asset_policy == expected)

    def clean_sprites_policy_complete(self, item: dict[str, Any], assets: list[dict[str, Any]] | None = None) -> bool:
        sprites = assets if assets is not None else self._readiness.assets()(item)
        return bool(sprites) and all(self._readiness.metadata()(asset) and self._readiness.material()(item, asset) for asset in sprites)

class TextAssetCatalog:
    def __init__(self, paths: MaterializedAssetPaths, operations: TextCatalogOperations) -> None:
        self._paths = paths
        self._operations = operations

    def canonical_text_assets(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        assets = []
        for asset in item.get("normalized_assets", []):
            if asset.get("kind") != "canonical_text_image":
                continue
            path = self._paths.resolve()(asset.get("path"))
            if not path.exists() or path.suffix.lower() not in self._operations.suffixes():
                continue
            if not asset.get("width") or not asset.get("height"):
                image = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if image is not None:
                    asset.setdefault("width", int(image.shape[1]))
                    asset.setdefault("height", int(image.shape[0]))
            assets.append(asset)
        return assets

    def canonical_text_assets_complete(self, item: dict[str, Any], assets: list[dict[str, Any]] | None = None) -> bool:
        if item.get("manual_crop_required"):
            return False
        text_assets = assets if assets is not None else self._operations.assets()(item)
        return bool(text_assets) and all(asset.get("width") and asset.get("height") for asset in text_assets)
