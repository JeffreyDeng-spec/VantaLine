"""Training preview orchestration with explicit assets, geometry and rendering capabilities."""
from collections.abc import Callable
from pathlib import Path
from typing import Any
import cv2
import numpy as np
from .preview_ports import (PreviewAssets, PreviewLayout, PreviewPoses, PreviewSizes,
                            PreviewSurface, PreviewThresholds, Record)


class PreviewRenderer:
    def __init__(self, material: Callable[[Record], str], surface: PreviewSurface,
                 assets: PreviewAssets, sizes: PreviewSizes, poses: PreviewPoses,
                 layout: PreviewLayout, thresholds: PreviewThresholds):
        self.material, self.surface, self.assets = material, surface, assets
        self.sizes, self.poses, self.layout, self.thresholds = sizes, poses, layout, thresholds

    def draw_training_preview(self,
        accessories: list[dict[str, Any]],
        output_path: Path,
        seed: int,
        pose_family_policy: str | None = None,
        split: str | None = None,
        background_set_id: str | None = None,
    ) -> dict[str, Any]:
        rng = np.random.default_rng(seed)
        canvas, background_meta = self.surface.background(rng, split, background_set_id)
        cv2.rectangle(canvas, (70, 100), (1210, 800), (49, 72, 60), 2)
        labels = []
        placed_objects: list[dict[str, Any]] = []
        visible_label_records: list[dict[str, Any]] = []
        render_accessories = sorted(accessories, key=lambda entry: 0 if self.material(entry) == "text" else 1)
        for idx, item in enumerate(render_accessories):
            material_type = self.material(item)
            angle = float(rng.uniform(-175, 175)) if material_type == "text" else 0.0
            final_render_angle = angle
            perspective_rotation = 0.0
            source_restore_rotation = 0.0
            size = self.sizes.physical(item, material_type)
            center = self.layout.random_center(rng, size, angle)
            loaded_asset = (
                self.assets.document(item, rng)
                if material_type == "text"
                else self.assets.generic(item)
            )
            asset = loaded_asset[0] if loaded_asset else None
            sprite_meta: dict[str, Any] = {}
            if material_type == "text":
                if asset is not None:
                    sprite_meta.update(loaded_asset[1] if loaded_asset else {})
                    sprite_meta.update(self.assets.paste_document(canvas, asset, center, size, angle))
                else:
                    rect = (center, size, angle)
                    box = cv2.boxPoints(rect).astype(np.int32)
                    cv2.fillConvexPoly(canvas, box, (245, 246, 246))
                    cv2.polylines(canvas, [box], True, (25, 27, 29), 2)
                    fallback_visible_mask = self.layout.mask()(canvas.shape[:2], box.tolist())
                    sprite_meta = {
                        "source_fallback_error": "document_rectified_asset_not_available",
                        "document_mask_crop_bypassed": True,
                        "object_alpha_pipeline_bypassed": True,
                        "render_resize_policy": "document_placeholder_physical_size",
                        "render_box_px": [int(size[0]), int(size[1])],
                        "render_visible_footprint_px": [int(size[0]), int(size[1])],
                        "_visible_mask_canvas": fallback_visible_mask,
                    }
            else:
                sprites = self.assets.sprites(item)
                pose_family = pose_family_policy if pose_family_policy in self.poses.available(item) else self.poses.choose(sprites, rng)
                render_policy = self.poses.policy(pose_family, rng)
                perspective_rotation = float(render_policy["perspective_rotation_degrees"])
                angle = float(render_policy["placement_angle_degrees"])
                top_view_pose = self.poses.top_view()(pose_family or "")
                size = self.sizes.pose()(item, pose_family)
                center, placement_meta = self.layout.choose_center(rng, size, angle, placed_objects)
                target_position = self.poses.position(center)
                selected_source_position = self.poses.source(target_position, perspective_rotation, pose_family, rng)
                sprite = self.assets.object_sprite()(
                    item,
                    rng,
                    target_position,
                    pose_family=pose_family,
                    source_position=selected_source_position,
                )
                if sprite is not None:
                    sprite_image, sprite_mask, sprite_meta = sprite
                    sprite_meta = dict(sprite_meta)
                    top_view_pose = self.poses.top_view()(
                        str(sprite_meta.get("source_pose_family") or sprite_meta.get("pose_family") or ""),
                        sprite_meta.get("source_object_size_px"),
                    )
                    sprite_size = self.sizes.pose()(
                        item,
                        str(sprite_meta.get("source_pose_family") or sprite_meta.get("pose_family") or pose_family or ""),
                    )
                    sprite_size = self.sizes.sprite(item, material_type, sprite_meta)
                    size = sprite_size
                    ignored_source_restore_rotation = 0.0
                    source_restore_rotation = 0.0
                    final_render_angle = perspective_rotation
                    current_source_position = sprite_meta.get("source_position") or sprite_meta.get("pose_position")
                    if selected_source_position and current_source_position != selected_source_position:
                        rematched = self.assets.object_sprite()(
                            item,
                            rng,
                            target_position,
                            pose_family=str(sprite_meta.get("source_pose_family") or sprite_meta.get("pose_family") or pose_family or ""),
                            source_position=selected_source_position,
                        )
                        if rematched is not None:
                            sprite_image, sprite_mask, sprite_meta = rematched
                            sprite_meta = dict(sprite_meta)
                            top_view_pose = self.poses.top_view()(
                                str(sprite_meta.get("source_pose_family") or sprite_meta.get("pose_family") or ""),
                                sprite_meta.get("source_object_size_px"),
                            )
                            ignored_source_restore_rotation = 0.0
                            source_restore_rotation = 0.0
                            final_render_angle = perspective_rotation
                            sprite_size = self.sizes.pose()(
                                item,
                                str(sprite_meta.get("source_pose_family") or sprite_meta.get("pose_family") or pose_family or ""),
                            )
                            sprite_size = self.sizes.sprite(item, material_type, sprite_meta)
                            size = sprite_size
                    sprite_image, sprite_mask, source_restore_rotation, ignored_source_restore_rotation = (
                        self.assets.restore()(
                            sprite_image,
                            sprite_mask,
                            sprite_meta,
                            top_view_pose=bool(top_view_pose),
                        )
                    )
                    actual_source_position = sprite_meta.get("source_position") or sprite_meta.get("pose_position")
                    sprite_meta["target_position"] = target_position
                    sprite_meta["selected_source_position"] = selected_source_position
                    sprite_meta["actual_source_position"] = actual_source_position
                    sprite_meta["source_selection_rule"] = render_policy["source_selection_rule"]
                    sprite_meta["source_selection_reason"] = self.poses.reason(
                        target_position,
                        selected_source_position,
                        perspective_rotation,
                    )
                    sprite_meta["desired_lie_direction"] = render_policy.get("desired_lie_direction")
                    sprite_meta["desired_facing_direction"] = render_policy["desired_facing_direction"]
                    sprite_meta["perspective_rotation_degrees"] = round(float(perspective_rotation), 2)
                    sprite_meta["placement_angle_degrees"] = round(float(angle), 2)
                    sprite_meta["final_render_angle_degrees"] = round(float(final_render_angle), 2)
                    sprite_meta["source_rotation_correction_degrees"] = round(float(source_restore_rotation), 2)
                    sprite_meta["ignored_source_restore_rotation_degrees"] = round(float(ignored_source_restore_rotation), 2)
                    sprite_meta["render_pose_policy"] = render_policy["render_pose_policy"]
                    sprite_meta["upright_pose_no_rotation"] = False
                    sprite_meta["upright_pose_random_rotation"] = bool(top_view_pose)
                    sprite_meta.update(placement_meta)
                    # Size every view of an accessory to the same long-axis pixel length
                    # (physical longest dimension * scale) so the cut-outs stay
                    # size-consistent and never collapse to a tiny clamp.
                    visible_now = self.sizes.visible(sprite_mask)
                    unified_long_px, unified_short_px = self.sizes.unified()(
                        visible_now[0],
                        visible_now[1],
                        int(sprite_size[0]),
                        int(sprite_size[1]),
                    )
                    sprite_meta["unified_render_box_px"] = [unified_long_px, unified_short_px]
                    sprite_meta["unified_render_long_axis_px"] = max(unified_long_px, unified_short_px)
                    sprite_meta.update(
                        self.assets.paste_object(
                            canvas,
                            sprite_image,
                            sprite_mask,
                            center,
                            unified_long_px,
                            unified_short_px,
                            final_render_angle,
                            preserve_aspect_ratio=True,
                        )
                    )
                else:
                    sprite_meta = {
                        "method": "missing_clean_object_sprite",
                        "source_fallback_error": "clean_object_sprite_not_available",
                        "render_pose_policy": render_policy["render_pose_policy"],
                        "target_position": target_position,
                        "selected_source_position": selected_source_position,
                        "actual_source_position": None,
                        "source_selection_rule": render_policy["source_selection_rule"],
                        "source_selection_reason": self.poses.reason(
                            target_position,
                            selected_source_position,
                            perspective_rotation,
                        ),
                        "desired_lie_direction": render_policy.get("desired_lie_direction"),
                        "desired_facing_direction": render_policy["desired_facing_direction"],
                        "perspective_rotation_degrees": round(float(perspective_rotation), 2),
                        "placement_angle_degrees": round(float(angle), 2),
                        "final_render_angle_degrees": round(float(angle), 2),
                    }
                    sprite_meta.update(placement_meta)
                    final_render_angle = angle
                    rect = (center, size, angle)
                    box = cv2.boxPoints(rect).astype(np.int32)
                    cv2.fillConvexPoly(canvas, box, (34, 36, 38))
                    cv2.polylines(canvas, [box], True, (7, 8, 9), 2)
                    cv2.circle(canvas, tuple(box[0]), 18, (128, 37, 31), -1)
                    sprite_meta["_visible_mask_canvas"] = self.layout.mask()(canvas.shape[:2], box.tolist())
            current_visible_mask = sprite_meta.pop("_visible_mask_canvas", None)
            placement_polygon = self.layout.box(center, size, final_render_angle)
            if material_type == "object":
                placed_objects.append(
                    {
                        "id": item["id"],
                        "rect": self.layout.rectangle(center, size, final_render_angle),
                        "polygon": placement_polygon,
                    }
                )
            label_entry = {
                    "id": item["id"],
                    "name": item["name"],
                    "angle": round(final_render_angle, 2),
                    "placement_angle_degrees": round(angle, 2),
                    "final_render_angle_degrees": round(final_render_angle, 2),
                    "z_index": idx + 1,
                    "material_type": material_type,
                    "physical_size": item.get("physical_size"),
                    "center_xy": [int(center[0]), int(center[1])],
                    "render_size_px": self.sizes.sprite(item, material_type, sprite_meta),
                    "render_policy": (
                        str(sprite_meta.get("render_scale_basis") or "object_side_major_axis_equals_physical_length")
                        if material_type == "object"
                        else "paper_width_height_equals_physical_size"
                    ),
                    "pose_position": self.poses.position(center) if material_type == "object" else None,
                    "target_position": sprite_meta.get("target_position") if material_type == "object" else None,
                    "selected_source_position": sprite_meta.get("selected_source_position") if material_type == "object" else None,
                    "actual_source_position": sprite_meta.get("actual_source_position") if material_type == "object" else None,
                    "source_selection_rule": sprite_meta.get("source_selection_rule") if material_type == "object" else None,
                    "source_selection_reason": sprite_meta.get("source_selection_reason") if material_type == "object" else None,
                    "desired_lie_direction": sprite_meta.get("desired_lie_direction") if material_type == "object" else None,
                    "desired_facing_direction": sprite_meta.get("desired_facing_direction") if material_type == "object" else None,
                    "perspective_rotation_degrees": sprite_meta.get("perspective_rotation_degrees") if material_type == "object" else None,
                    "render_pose_policy": sprite_meta.get("render_pose_policy") if material_type == "object" else None,
                    "preview_pose_family_policy": pose_family_policy if material_type == "object" else None,
                    "sprite_index": sprite_meta.get("sprite_index") if material_type == "object" else None,
                    "sprite_path": sprite_meta.get("sprite_path") if material_type == "object" else None,
                    "clean_sprite_preprocessed_at": sprite_meta.get("clean_sprite_preprocessed_at") if material_type == "object" else None,
                    "clean_sprite_version": sprite_meta.get("clean_sprite_version") if material_type == "object" else None,
                    "sprite_source_method": sprite_meta.get("method") if material_type == "object" else None,
                    "source_fallback_error": sprite_meta.get("source_fallback_error") if material_type == "object" else None,
                    "task_id": sprite_meta.get("task_id") if material_type == "object" else None,
                    "source_pose_collection_job_id": sprite_meta.get("source_pose_collection_job_id") if material_type == "object" else None,
                    "pose_source_position": sprite_meta.get("pose_position") if material_type == "object" else None,
                    "source_position": sprite_meta.get("source_position") if material_type == "object" else None,
                    "source_image_size_px": sprite_meta.get("source_image_size_px"),
                    "source_image_width": sprite_meta.get("source_image_width") if material_type == "object" else (sprite_meta.get("source_image_size_px") or [None, None])[0],
                    "source_image_height": sprite_meta.get("source_image_height") if material_type == "object" else (sprite_meta.get("source_image_size_px") or [None, None])[1],
                    "target_source_position_match": (
                        sprite_meta.get("actual_source_position") == sprite_meta.get("selected_source_position")
                        if material_type == "object" and sprite_meta.get("selected_source_position")
                        else None
                    ),
                    "pose_source_family": (sprite_meta.get("pose_family") or sprite_meta.get("source_pose_family")) if material_type == "object" else None,
                    "pose_source_bbox_xyxy": sprite_meta.get("source_object_bbox_xyxy") if material_type == "object" else None,
                    "pose_source_footprint_px": sprite_meta.get("source_object_size_px") if material_type == "object" else None,
                    "source_long_side_px": sprite_meta.get("source_long_side_px") if material_type == "object" else None,
                    "source_short_side_px": sprite_meta.get("source_short_side_px") if material_type == "object" else None,
                    "source_long_edge_axis": sprite_meta.get("source_long_edge_axis") if material_type == "object" else None,
                    "source_short_edge_axis": sprite_meta.get("source_short_edge_axis") if material_type == "object" else None,
                    "source_long_short_ratio": sprite_meta.get("source_long_short_ratio") if material_type == "object" else None,
                    "source_length_width_rule": sprite_meta.get("source_length_width_rule") if material_type == "object" else None,
                    "render_footprint_mm": sprite_meta.get("render_footprint_mm") if material_type == "object" else None,
                    "render_footprint_px": sprite_meta.get("render_footprint_px") if material_type == "object" else sprite_meta.get("render_visible_footprint_px"),
                    "render_footprint_mm_unoriented_long_short": sprite_meta.get("render_footprint_mm_unoriented_long_short") if material_type == "object" else None,
                    "render_footprint_px_unoriented_long_short": sprite_meta.get("render_footprint_px_unoriented_long_short") if material_type == "object" else None,
                    "render_source_aspect_preserved": sprite_meta.get("render_source_aspect_preserved") if material_type == "object" else None,
                    "render_box_px": sprite_meta.get("render_box_px"),
                    "render_visible_footprint_px": sprite_meta.get("render_visible_footprint_px"),
                    "pre_paste_visible_footprint_px": sprite_meta.get("pre_paste_visible_footprint_px") if material_type == "object" else None,
                    "final_pasted_visible_footprint_px": sprite_meta.get("final_pasted_visible_footprint_px") if material_type == "object" else None,
                    "source_visible_footprint_px": sprite_meta.get("source_visible_footprint_px"),
                    "render_resize_policy": sprite_meta.get("render_resize_policy"),
                    "render_paste_resize_policy": sprite_meta.get("render_paste_resize_policy") if material_type == "object" else None,
                    "render_paste_rescaled": sprite_meta.get("render_paste_rescaled") if material_type == "object" else None,
                    "non_uniform_scaling_applied": sprite_meta.get("non_uniform_scaling_applied"),
                    "render_scale_x": sprite_meta.get("render_scale_x"),
                    "render_scale_y": sprite_meta.get("render_scale_y"),
                    "render_scale_basis": sprite_meta.get("render_scale_basis") if material_type == "object" else None,
                    "material_alpha_policy": item.get("material_alpha_policy") if material_type == "object" else None,
                    "object_alpha_material_policy": sprite_meta.get("object_alpha_material_policy") if material_type == "object" else None,
                    "transparent_alpha_policy": sprite_meta.get("transparent_alpha_policy") if material_type == "object" else None,
                    "placement_polygon_xy": placement_polygon,
                    "object_non_overlap_attempts": sprite_meta.get("object_non_overlap_attempts") if material_type == "object" else None,
                    "object_overlap_area_px": sprite_meta.get("object_overlap_area_px") if material_type == "object" else None,
                    "object_non_overlap_pass": sprite_meta.get("object_non_overlap_pass") if material_type == "object" else None,
                    "render_scale_basis_before_correction": sprite_meta.get("render_scale_basis_before_correction") if material_type == "object" else None,
                    "render_footprint_px_before_correction": sprite_meta.get("render_footprint_px_before_correction") if material_type == "object" else None,
                    "render_footprint_px_after_correction": sprite_meta.get("render_footprint_px_after_correction") if material_type == "object" else None,
                    "upright_scale_correction": sprite_meta.get("upright_scale_correction") if material_type == "object" else None,
                    "upright_scale_correction_raw": sprite_meta.get("upright_scale_correction_raw") if material_type == "object" else None,
                    "upright_scale_correction_before_visual_adjustment": sprite_meta.get("upright_scale_correction_before_visual_adjustment") if material_type == "object" else None,
                    "upright_scale_visual_adjustment": sprite_meta.get("upright_scale_visual_adjustment") if material_type == "object" else None,
                    "upright_scale_adjustment_percent": sprite_meta.get("upright_scale_adjustment_percent") if material_type == "object" else None,
                    "upright_scale_adjustment_reason": sprite_meta.get("upright_scale_adjustment_reason") if material_type == "object" else None,
                    "upright_scale_visually_adjusted": sprite_meta.get("upright_scale_visually_adjusted") if material_type == "object" else None,
                    "upright_scale_correction_basis": sprite_meta.get("upright_scale_correction_basis") if material_type == "object" else None,
                    "upright_scale_correction_source_dimensions": sprite_meta.get("upright_scale_correction_source_dimensions") if material_type == "object" else None,
                    "upright_scale_correction_physical_ratio": sprite_meta.get("upright_scale_correction_physical_ratio") if material_type == "object" else None,
                    "upright_scale_correction_clamped": sprite_meta.get("upright_scale_correction_clamped") if material_type == "object" else None,
                    "original_orientation_angle": sprite_meta.get("original_orientation_angle") if material_type == "object" else None,
                    "rotation_degrees_applied": sprite_meta.get("rotation_degrees_applied") if material_type == "object" else None,
                    "source_restore_rotation_degrees": round(source_restore_rotation, 2) if material_type == "object" else None,
                    "source_rotation_correction_degrees": sprite_meta.get("source_rotation_correction_degrees") if material_type == "object" else None,
                    "source_restore_rotation_degrees_requested": sprite_meta.get("source_restore_rotation_degrees_requested") if material_type == "object" else None,
                    "ignored_source_restore_rotation_degrees": sprite_meta.get("ignored_source_restore_rotation_degrees") if material_type == "object" else None,
                    "source_orientation_restored_for_render": sprite_meta.get("source_orientation_restored_for_render") if material_type == "object" else None,
                    "upright_pose_no_rotation": sprite_meta.get("upright_pose_no_rotation") if material_type == "object" else None,
                    "upright_pose_random_rotation": sprite_meta.get("upright_pose_random_rotation") if material_type == "object" else None,
                    "canonical_asset_dimensions_px": sprite_meta.get("canonical_asset_dimensions_px"),
                    "canonical_width_px": sprite_meta.get("canonical_width_px") if material_type == "object" else (sprite_meta.get("canonical_asset_dimensions_px") or [None, None])[0],
                    "canonical_height_px": sprite_meta.get("canonical_height_px") if material_type == "object" else (sprite_meta.get("canonical_asset_dimensions_px") or [None, None])[1],
                    "normalized_asset_dimensions_px": sprite_meta.get("normalized_asset_dimensions_px") if material_type == "object" else sprite_meta.get("canonical_asset_dimensions_px"),
                    "document_asset_path": sprite_meta.get("asset_path") if material_type == "text" else None,
                    "document_asset_index": sprite_meta.get("document_asset_index") if material_type == "text" else None,
                    "document_asset_count": sprite_meta.get("document_asset_count") if material_type == "text" else None,
                    "document_asset_selection_policy": sprite_meta.get("document_asset_selection_policy") if material_type == "text" else None,
                    "document_asset_source_index": sprite_meta.get("document_asset_source_index") if material_type == "text" else None,
                    "document_asset_source": sprite_meta.get("asset_source") if material_type == "text" else None,
                    "document_asset_method": sprite_meta.get("asset_method") if material_type == "text" else None,
                    "document_mask_crop_bypassed": sprite_meta.get("document_mask_crop_bypassed") if material_type == "text" else None,
                    "object_alpha_pipeline_bypassed": sprite_meta.get("object_alpha_pipeline_bypassed") if material_type == "text" else None,
                    "document_full_asset_pasted": sprite_meta.get("document_full_asset_pasted") if material_type == "text" else None,
                    "document_asset_policy": sprite_meta.get("document_asset_policy") if material_type == "text" else None,
                    "document_physical_scale_basis": sprite_meta.get("document_physical_scale_basis") if material_type == "text" else None,
                }
            labels.append(label_entry)
            if isinstance(current_visible_mask, np.ndarray):
                current_visible_mask = current_visible_mask.copy()
                for record in visible_label_records:
                    record["mask"][current_visible_mask > 24] = 0
                # Keep the part's full footprint (before later parts are pasted over it)
                # so its detection box stays amodal/complete under occlusion.
                visible_label_records.append(
                    {"label": label_entry, "mask": current_visible_mask, "full_mask": current_visible_mask.copy()}
                )
        canvas_h, canvas_w = canvas.shape[:2]
        for record in visible_label_records:
            final_visible_footprint = self.sizes.visible(record["mask"])
            record["label"]["final_visible_footprint_px"] = final_visible_footprint
            if record["label"].get("material_type") == "object":
                record["label"]["render_visible_footprint_px"] = final_visible_footprint
            visible_polygon = self.layout.polygon(record["mask"])
            if visible_polygon:
                record["label"]["visible_polygon_xy"] = visible_polygon
                record["label"]["visible_polygons_xy"] = [visible_polygon]
                record["label"]["placement_polygon_xy"] = visible_polygon
                record["label"]["final_visible_polygon_max_pair_px"] = round(self.layout.max_distance(visible_polygon), 2)
            # Amodal detection box from the full footprint, clipped to the frame. This
            # is the box written to the YOLO detection label (a part on top no longer
            # cuts the part below in half).
            full_mask = record.get("full_mask")
            full_area = int(np.count_nonzero(full_mask > 24)) if isinstance(full_mask, np.ndarray) else 0
            visible_area = int(np.count_nonzero(record["mask"] > 24))
            occlusion_fraction = round(1.0 - (visible_area / full_area), 4) if full_area > 0 else 1.0
            record["label"]["occlusion_fraction"] = occlusion_fraction
            amodal_bbox = None
            if isinstance(full_mask, np.ndarray) and full_area > 0:
                ys, xs = np.where(full_mask > 24)
                x1 = max(0, int(xs.min()))
                y1 = max(0, int(ys.min()))
                x2 = min(canvas_w, int(xs.max()) + 1)
                y2 = min(canvas_h, int(ys.max()) + 1)
                if x2 > x1 and y2 > y1:
                    amodal_bbox = [x1, y1, x2, y2]
            record["label"]["amodal_bbox_xyxy"] = amodal_bbox
            # Drop a part from the labels only when it is essentially fully hidden.
            record["label"]["detection_dropped"] = bool(
                amodal_bbox is None
                or visible_area < self.thresholds.min_visible_area()
                or occlusion_fraction > self.thresholds.max_occlusion()
            )
        cv2.imwrite(str(output_path), canvas)
        return {
            "url": self.surface.public_url(output_path),
            "pose_family_policy": pose_family_policy,
            "render_policy_note": (
                "controlled_pose_family_per_preview_card; upright uses no rotation; lying uses cardinal rotation with inverse source-position mapping"
            ),
            "background": background_meta,
            "labels": labels,
        }
