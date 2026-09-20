"""Masked sprite geometry without application imports."""
from typing import Any
import math
import cv2
import numpy as np
from .sprite_geometry_ports import SpriteTransformOperations, SpriteFootprintOperations


class SpriteGeometry:
    def __init__(self, transform: SpriteTransformOperations, footprint: SpriteFootprintOperations) -> None:
        self._transform = transform
        self._footprint = footprint


    def masked_major_axis_angle(self, mask: np.ndarray) -> tuple[float, float]:
        ys, xs = np.where(mask > 8)
        if len(xs) < 24:
            return 0.0, 1.0
        points = np.column_stack([xs.astype(np.float32), ys.astype(np.float32)])
        centered = points - points.mean(axis=0)
        cov = np.cov(centered, rowvar=False)
        values, vectors = np.linalg.eigh(cov)
        order = np.argsort(values)[::-1]
        major = vectors[:, order[0]]
        angle = self._transform.normalize()(math.degrees(math.atan2(float(major[1]), float(major[0]))))
        ratio = float(values[order[0]] / max(values[order[1]], 1e-6)) if len(values) >= 2 else 1.0
        return angle, ratio

    def rotate_masked_asset(self,
        asset: np.ndarray,
        mask: np.ndarray,
        angle: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        h, w = asset.shape[:2]
        safety_pad = max(10, int(round(max(w, h) * 0.08)))
        asset, mask = self._transform.margin()(asset, mask, safety_pad)
        h, w = asset.shape[:2]
        if abs(angle) < 0.05:
            return self._transform.trim()(asset, mask, pad=safety_pad)
        radians = math.radians(abs(angle))
        new_w = max(1, int(math.ceil(w * math.cos(radians) + h * math.sin(radians)))) + safety_pad * 2
        new_h = max(1, int(math.ceil(w * math.sin(radians) + h * math.cos(radians)))) + safety_pad * 2
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        matrix[0, 2] += (new_w - w) / 2
        matrix[1, 2] += (new_h - h) / 2
        rotated_asset = cv2.warpAffine(
            asset,
            matrix,
            (new_w, new_h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        )
        rotated_mask = cv2.warpAffine(
            mask,
            matrix,
            (new_w, new_h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        return self._transform.trim()(rotated_asset, rotated_mask, pad=safety_pad)

    def normalize_sprite_upright(self, asset: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
        trimmed_asset, trimmed_mask = self._transform.trim()(asset, mask, pad=8)
        original_h, original_w = trimmed_asset.shape[:2]
        orientation_angle, axis_ratio = self._transform.axis()(trimmed_mask)
        target_axis = 90.0
        correction = self._transform.normalize()(orientation_angle - target_axis)
        if axis_ratio < 1.18:
            correction = 0.0
        pre_rotation_margin = max(18, int(round(max(original_w, original_h) * 0.14)))
        padded_asset, padded_mask = self._transform.margin()(trimmed_asset, trimmed_mask, pre_rotation_margin)
        upright_asset, upright_mask = self._transform.rotate()(padded_asset, padded_mask, correction)
        return upright_asset, upright_mask, {
            "original_angle_degrees": round(float(orientation_angle), 3),
            "rotation_degrees": round(float(correction), 3),
            "original_orientation_angle": round(float(orientation_angle), 3),
            "original_orientation_angle_degrees": round(float(orientation_angle), 3),
            "rotation_degrees_applied": round(float(correction), 3),
            "rotation_degrees_applied_to_upright": round(float(correction), 3),
            "source_restore_rotation_degrees": round(float(-correction), 3),
            "normalized_axis_target_degrees": round(float(target_axis), 3),
            "orientation_axis_ratio": round(float(axis_ratio), 4),
            "pre_normalized_asset_size_px": [int(original_w), int(original_h)],
            "pre_rotation_safety_margin_px": int(pre_rotation_margin),
            "upright_normalized": True,
        }

    def visible_mask_size_px(self, mask: np.ndarray) -> list[int]:
        bbox = self._footprint.bounds()(mask)
        return [max(0, int(bbox[2] - bbox[0])), max(0, int(bbox[3] - bbox[1]))]

    def resize_masked_asset_to_visible_footprint(self,
        asset: np.ndarray,
        mask: np.ndarray,
        target_size: tuple[int, int],
        preserve_aspect_ratio: bool = False,
    ) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
        target_w, target_h = max(1, int(target_size[0])), max(1, int(target_size[1]))
        source_visible = self._footprint.visible()(mask)
        if asset.size == 0 or mask.size == 0:
            return asset, mask, {
                "render_box_px": [target_w, target_h],
                "render_visible_footprint_px": [0, 0],
                "render_resize_policy": (
                    "alpha_visible_bbox_fit_physical_footprint_preserve_aspect"
                    if preserve_aspect_ratio
                    else "alpha_visible_bbox_exact_physical_footprint"
                ),
                "source_visible_footprint_px": source_visible,
                "non_uniform_scaling_applied": False,
                "render_scale_x": None,
                "render_scale_y": None,
            }
        source_w = max(1, int(asset.shape[1]))
        source_h = max(1, int(asset.shape[0]))
        visible_w, visible_h = max(1, int(source_visible[0])), max(1, int(source_visible[1]))
        if preserve_aspect_ratio:
            scale = min(target_w / visible_w, target_h / visible_h)
            resized_w = max(1, int(round(source_w * scale)))
            resized_h = max(1, int(round(source_h * scale)))
            render_policy = "alpha_visible_bbox_fit_physical_footprint_preserve_aspect"
            scale_x = scale
            scale_y = scale
        else:
            scale_x = target_w / visible_w
            scale_y = target_h / visible_h
            resized_w = max(1, int(round(source_w * scale_x)))
            resized_h = max(1, int(round(source_h * scale_y)))
            render_policy = "alpha_visible_bbox_exact_physical_footprint"
        resized = cv2.resize(asset, (resized_w, resized_h), interpolation=cv2.INTER_AREA if max(asset.shape[:2]) > max(resized_h, resized_w) else cv2.INTER_CUBIC)
        resized_mask = cv2.resize(mask, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)
        return resized, resized_mask, {
            "render_box_px": [target_w, target_h],
            "render_visible_footprint_px": self._footprint.visible()(resized_mask),
            "render_resize_policy": render_policy,
            "source_visible_footprint_px": source_visible,
            "non_uniform_scaling_applied": bool(abs(scale_x - scale_y) > 0.0005),
            "render_scale_x": round(float(scale_x), 6),
            "render_scale_y": round(float(scale_y), 6),
        }
