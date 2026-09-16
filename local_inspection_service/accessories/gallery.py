"""Gallery projection and preview writes retain existing read-time side effects."""
from pathlib import Path
from typing import Any
import cv2
import numpy as np
from .gallery_ports import GalleryAssets, GalleryStorage, GalleryDisplay
from .policy import accessory_uid, accessory_material_type
from .projection import AccessoryProjection


class AccessoryGallery:
    def __init__(self, assets: GalleryAssets, storage: GalleryStorage,
                 display: GalleryDisplay, projection: AccessoryProjection):
        self.assets, self.storage = assets, storage
        self.display, self.projection = display, projection

    def public_accessory_detail_item(self, item: dict[str, Any]) -> dict[str, Any]:
        copy = self.projection.serialize_accessory(item)
        for key in list(copy):
            if key.startswith("codex_image") or key.startswith("pose_collection_prompt"):
                copy.pop(key, None)
        if copy.get("preprocess"):
            copy["preprocess"] = self.display.public_text(copy["preprocess"])
        return self.display.redact(copy, self.display.current_user())

    def write_gallery_preview(self, src: Path, out_path: Path, max_side: int = 1200) -> dict[str, Any] | None:
        raw = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
        if raw is None:
            return None
        if raw.ndim == 3 and raw.shape[2] >= 4:
            alpha = (raw[:, :, 3].astype(np.float32) / 255.0)[..., None]
            bgr = raw[:, :, :3].astype(np.float32)
            background = np.full_like(bgr, 245.0)
            image = (bgr * alpha + background * (1.0 - alpha)).astype(np.uint8)
        else:
            image = raw if raw.ndim == 3 else cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
        if image is None:
            return None
        h, w = image.shape[:2]
        scale = min(max_side / max(h, w), 1.0)
        preview = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_path), preview)
        return {"url": self.storage.public_url(out_path), "width": int(preview.shape[1]), "height": int(preview.shape[0])}

    def accessory_detail_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        uid = accessory_uid(item)
        gallery_dir = self.storage.write_directory("accessory_gallery") / uid
        gallery: list[dict[str, Any]] = []
        material_type = accessory_material_type(item)
        ai_reference_paths = {
            str(path)
            for path in item.get("ai_profile_reference_files", []) or []
            if str(path).strip()
        }
        if not ai_reference_paths:
            default_ref = self.assets.default_reference(item)
            if default_ref:
                ai_reference_paths.add(str(default_ref))
        shown_paths: set[str] = set()
        for source_index, path in enumerate(self.assets.sources(item), start=1):
            preview = self.write_gallery_preview(path, gallery_dir / f"source_{source_index:02d}.png")
            if preview:
                shown_paths.add(str(path))
                gallery.append(
                    {
                        "label": "实拍照片" if material_type == "object" else "文档照片",
                        "kind": "source",
                        "source_path": str(path),
                        "deletable": True,
                        "ai_reference": str(path) in ai_reference_paths,
                        **self.display.audit(item, path),
                        **preview,
                    }
                )
        pose_output_paths = []
        clean_sprites = self.assets.clean_sprites(item)[:18]
        for job in self.assets.image_jobs(item):
            output_path = Path(str(job.get("output_path", "")))
            if material_type == "object" and output_path.exists() and str(output_path).startswith(str(self.storage.output_directory())):
                if str(output_path) in shown_paths:
                    continue
                pose_output_paths.append(output_path)
                shown_paths.add(str(output_path))
                gallery.append(
                    {
                        "label": self.display.public_text(job.get("label") or "多角度视图"),
                        "kind": "pose_collection",
                        "url": self.storage.public_url(output_path),
                        "source_path": str(output_path),
                        "deletable": True,
                        "ai_reference": str(output_path) in ai_reference_paths,
                        **self.display.audit(item, output_path),
                    }
                )
        for idx, asset in enumerate(clean_sprites):
            path = self.assets.resolve_path(asset.get("path"))
            if str(path) in shown_paths:
                continue
            preview = self.write_gallery_preview(path, gallery_dir / f"clean_sprite_{idx + 1:02d}.png")
            if preview:
                shown_paths.add(str(path))
                gallery.append(
                    {
                        "label": f"无背景 sprite {idx + 1}",
                        "kind": "clean_object_sprite",
                        "source_path": str(path),
                        "pose_family": asset.get("pose_family") or asset.get("source_pose_family"),
                        "pose_position": asset.get("pose_position"),
                        "source_position": asset.get("source_position") or asset.get("pose_position"),
                        "source_object_bbox_xyxy": asset.get("source_object_bbox_xyxy"),
                        "source_object_center_xy": asset.get("source_object_center_xy"),
                        "source_object_size_px": asset.get("source_object_size_px"),
                        "source_long_side_px": asset.get("source_long_side_px"),
                        "source_short_side_px": asset.get("source_short_side_px"),
                        "source_long_edge_axis": asset.get("source_long_edge_axis"),
                        "source_short_edge_axis": asset.get("source_short_edge_axis"),
                        "source_long_short_ratio": asset.get("source_long_short_ratio"),
                        "source_length_width_rule": asset.get("source_length_width_rule"),
                        "task_id": asset.get("task_id"),
                        "source_pose_collection_job_id": asset.get("source_pose_collection_job_id"),
                        "rotation_degrees_applied": asset.get("rotation_degrees_applied"),
                        "rotation_degrees_applied_to_upright": asset.get("rotation_degrees_applied_to_upright"),
                        "original_orientation_angle": asset.get("original_orientation_angle"),
                        "original_orientation_angle_degrees": asset.get("original_orientation_angle_degrees"),
                        "source_restore_rotation_degrees": asset.get("source_restore_rotation_degrees"),
                        "normalized_asset_size_px": asset.get("normalized_asset_size_px"),
                        "normalized_asset_dimensions_px": asset.get("normalized_asset_dimensions_px"),
                        "normalized_bbox_xyxy": asset.get("normalized_bbox_xyxy"),
                        "edge_alpha_max": asset.get("edge_alpha_max"),
                        "edge_alpha_pass": asset.get("edge_alpha_pass"),
                        "pre_rotation_safety_margin_px": asset.get("pre_rotation_safety_margin_px"),
                        "post_rotation_safety_margin_px": asset.get("post_rotation_safety_margin_px"),
                        "physical_size_mm": asset.get("physical_size_mm"),
                        "material_alpha_policy": asset.get("material_alpha_policy"),
                        "object_alpha_material_policy": asset.get("object_alpha_material_policy"),
                        "transparent_alpha_policy": asset.get("transparent_alpha_policy"),
                        "render_scale_basis": asset.get("render_scale_basis"),
                        "render_footprint_mm": asset.get("render_footprint_mm"),
                        "render_footprint_px": asset.get("render_footprint_px"),
                        "render_footprint_mm_unoriented_long_short": asset.get("render_footprint_mm_unoriented_long_short"),
                        "render_footprint_px_unoriented_long_short": asset.get("render_footprint_px_unoriented_long_short"),
                        "render_source_aspect_preserved": asset.get("render_source_aspect_preserved"),
                        "deletable": True,
                        "ai_reference": str(path) in ai_reference_paths,
                        **self.display.audit(item, path),
                        **preview,
                    }
                )
        source_paths = {str(path) for path in self.assets.sources(item)}
        normalized_index = 1
        for path in self.assets.derived_paths(item):
            if path in pose_output_paths:
                continue
            if str(path) in source_paths or str(path) in shown_paths:
                continue
            preview = self.write_gallery_preview(path, gallery_dir / f"asset_{normalized_index:02d}.png")
            if preview:
                shown_paths.add(str(path))
                gallery.append(
                    {
                        "label": "规范化文档" if material_type == "text" else "派生素材",
                        "kind": "normalized" if material_type == "text" else "derived",
                        "source_path": str(path),
                        "deletable": True,
                        "ai_reference": str(path) in ai_reference_paths,
                        **self.display.audit(item, path),
                        **preview,
                    }
                )
                normalized_index += 1
        return {"item": self.public_accessory_detail_item(item), "gallery": gallery}
