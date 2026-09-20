"""Asset canvas composition and physical render metadata."""
from typing import Any
import cv2
import numpy as np
from .compositing_ports import CompositionGeometry, CompositionOperations

def physical_mask_for_rect_asset(asset: np.ndarray) -> np.ndarray:
    return np.full(asset.shape[:2], 255, dtype=np.uint8)

def trim_rect_asset(asset: np.ndarray, pad: int = 0) -> np.ndarray:
    gray = cv2.cvtColor(asset, cv2.COLOR_BGR2GRAY)
    border = np.concatenate([gray[:5, :].reshape(-1), gray[-5:, :].reshape(-1), gray[:, :5].reshape(-1), gray[:, -5:].reshape(-1)])
    bg = float(np.median(border))
    diff = np.abs(gray.astype(np.float32) - bg)
    mask = (diff > 8).astype(np.uint8) * 255
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if num <= 1:
        return asset
    areas = stats[1:, cv2.CC_STAT_AREA]
    idx = int(np.argmax(areas)) + 1
    x, y, w, h, _ = stats[idx]
    if w * h < asset.shape[0] * asset.shape[1] * 0.2:
        return asset
    x1, y1 = max(0, x - pad), max(0, y - pad)
    x2, y2 = min(asset.shape[1], x + w + pad), min(asset.shape[0], y + h + pad)
    return asset[y1:y2, x1:x2].copy()

def long_axis_unified_render_box(
    visible_w: int,
    visible_h: int,
    target_long_px: int,
    target_short_px: int,
) -> tuple[int, int]:
    """Return a render box whose aspect equals the sprite's own visible aspect and
    whose LONG side equals the physical-footprint long side.

    The compositor pastes with preserve_aspect_ratio=min(w/vw, h/vh). When the
    footprint aspect (from physical dims) does not match a particular AI pose
    image's visible aspect, that min() clamps to the short side and the object
    shrinks to a fraction of its true size (the source of the 10x size spread).
    By matching the box aspect to the sprite, min() resolves to the long-axis
    scale, so every view of the same accessory renders at the same long-axis
    length and stays size-consistent without distortion."""
    vw = max(1, int(visible_w))
    vh = max(1, int(visible_h))
    target_long = max(16, int(round(max(target_long_px, target_short_px))))
    scale = target_long / max(1, max(vw, vh))
    return max(16, int(round(vw * scale))), max(16, int(round(vh * scale)))

def paste_rectified_document_asset(
    canvas: np.ndarray,
    asset: np.ndarray,
    center: tuple[int, int],
    target_size: tuple[int, int],
    angle: float,
) -> dict[str, Any]:
    target_w, target_h = max(1, int(target_size[0])), max(1, int(target_size[1]))
    source_h, source_w = asset.shape[:2]
    # Fit the document into the paper box preserving aspect (never stretch). The
    # canonical asset already matches the paper aspect, so this is normally a clean
    # uniform scale; the min() guard protects any legacy/odd-aspect canonical.
    fit_scale = min(target_w / max(1, source_w), target_h / max(1, source_h))
    fit_w = max(1, int(round(source_w * fit_scale)))
    fit_h = max(1, int(round(source_h * fit_scale)))
    resized = cv2.resize(
        asset,
        (fit_w, fit_h),
        interpolation=cv2.INTER_AREA if fit_scale < 1 else cv2.INTER_CUBIC,
    )
    diagonal = int(np.ceil(np.sqrt(target_w * target_w + target_h * target_h))) + 8
    patch = np.zeros((diagonal, diagonal, 3), dtype=np.uint8)
    patch_mask = np.zeros((diagonal, diagonal), dtype=np.uint8)
    x0 = (diagonal - fit_w) // 2
    y0 = (diagonal - fit_h) // 2
    patch[y0 : y0 + fit_h, x0 : x0 + fit_w] = resized
    patch_mask[y0 : y0 + fit_h, x0 : x0 + fit_w] = 255
    matrix = cv2.getRotationMatrix2D((diagonal / 2, diagonal / 2), angle, 1.0)
    rotated = cv2.warpAffine(patch, matrix, (diagonal, diagonal), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))
    rotated_mask = cv2.warpAffine(patch_mask, matrix, (diagonal, diagonal), flags=cv2.INTER_LINEAR, borderValue=0)
    cx, cy = center
    dest_x = cx - diagonal // 2
    dest_y = cy - diagonal // 2
    x1, y1 = max(0, dest_x), max(0, dest_y)
    x2, y2 = min(canvas.shape[1], dest_x + diagonal), min(canvas.shape[0], dest_y + diagonal)
    sx1, sy1 = x1 - dest_x, y1 - dest_y
    sx2, sy2 = sx1 + (x2 - x1), sy1 + (y2 - y1)
    if x2 > x1 and y2 > y1:
        roi = canvas[y1:y2, x1:x2]
        pasted_mask = rotated_mask[sy1:sy2, sx1:sx2]
        alpha = (pasted_mask.astype(float) / 255.0)[..., None]
        roi[:] = (rotated[sy1:sy2, sx1:sx2] * alpha + roi * (1 - alpha)).astype(np.uint8)
        visible_mask = np.zeros(canvas.shape[:2], dtype=np.uint8)
        visible_mask[y1:y2, x1:x2] = pasted_mask
    else:
        visible_mask = np.zeros(canvas.shape[:2], dtype=np.uint8)
    return {
        "document_mask_crop_bypassed": True,
        "object_alpha_pipeline_bypassed": True,
        "document_full_asset_pasted": True,
        "document_asset_policy": "full_rectified_asset_direct_physical_size",
        "document_physical_scale_basis": "paper_width_height_mm_to_background_px",
        "render_box_px": [target_w, target_h],
        "render_visible_footprint_px": [fit_w, fit_h],
        "render_resize_policy": "document_rectified_fit_preserve_aspect_paper_box",
        "source_visible_footprint_px": [int(source_w), int(source_h)],
        "non_uniform_scaling_applied": False,
        "render_scale_x": round(float(fit_scale), 6),
        "render_scale_y": round(float(fit_scale), 6),
        "_visible_mask_canvas": visible_mask,
    }

class AssetCompositor:
    def __init__(self, geometry: CompositionGeometry, operations: CompositionOperations) -> None:
        self._geometry = geometry
        self._operations = operations

    def paste_masked_asset(self,
        canvas: np.ndarray,
        asset: np.ndarray,
        mask: np.ndarray,
        center: tuple[int, int],
        target_size: tuple[int, int],
        angle: float,
        trim_before_paste: bool = True,
        return_visible_mask: bool = False,
        resize_to_target: bool = True,
    ) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
        if trim_before_paste:
            asset, mask = self._geometry.trim()(asset, mask)
        visible_mask = np.zeros(canvas.shape[:2], dtype=np.uint8) if return_visible_mask else None
        target_w, target_h = target_size
        h, w = asset.shape[:2]
        if resize_to_target:
            scale = min(target_w / max(w, 1), target_h / max(h, 1))
            resized = cv2.resize(asset, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
            resized_mask = cv2.resize(mask, (resized.shape[1], resized.shape[0]), interpolation=cv2.INTER_LINEAR)
        else:
            resized = asset
            resized_mask = mask
        rh, rw = resized.shape[:2]
        diagonal = int(np.ceil(np.sqrt(rw * rw + rh * rh))) + 8
        patch = np.zeros((diagonal, diagonal, 3), dtype=np.uint8)
        patch_mask = np.zeros((diagonal, diagonal), dtype=np.uint8)
        x0 = (diagonal - rw) // 2
        y0 = (diagonal - rh) // 2
        patch[y0 : y0 + rh, x0 : x0 + rw] = resized
        patch_mask[y0 : y0 + rh, x0 : x0 + rw] = resized_mask
        matrix = cv2.getRotationMatrix2D((diagonal / 2, diagonal / 2), angle, 1.0)
        rotated = cv2.warpAffine(patch, matrix, (diagonal, diagonal), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))
        rotated_mask = cv2.warpAffine(patch_mask, matrix, (diagonal, diagonal), flags=cv2.INTER_LINEAR, borderValue=0)
        cx, cy = center
        dest_x = cx - diagonal // 2
        dest_y = cy - diagonal // 2
        x1, y1 = max(0, dest_x), max(0, dest_y)
        x2, y2 = min(canvas.shape[1], dest_x + diagonal), min(canvas.shape[0], dest_y + diagonal)
        sx1, sy1 = x1 - dest_x, y1 - dest_y
        sx2, sy2 = sx1 + (x2 - x1), sy1 + (y2 - y1)
        if x2 <= x1 or y2 <= y1:
            return (canvas, visible_mask) if return_visible_mask else canvas
        roi = canvas[y1:y2, x1:x2]
        pasted_mask = rotated_mask[sy1:sy2, sx1:sx2]
        alpha = (pasted_mask.astype(float) / 255.0)[..., None]
        roi[:] = (rotated[sy1:sy2, sx1:sx2] * alpha + roi * (1 - alpha)).astype(np.uint8)
        if visible_mask is not None:
            visible_mask[y1:y2, x1:x2] = pasted_mask
            return canvas, visible_mask
        return canvas

    def paste_physical_object_asset(self,
        canvas: np.ndarray,
        asset: np.ndarray,
        mask: np.ndarray,
        center: tuple[int, int],
        target_long_side_px: int,
        target_short_side_px: int,
        angle: float,
        preserve_aspect_ratio: bool = False,
    ) -> dict[str, Any]:
        target_size = (max(1, int(target_long_side_px)), max(1, int(target_short_side_px)))
        resized, resized_mask, render_meta = self._geometry.resize_footprint()(asset, mask, target_size, preserve_aspect_ratio)
        pre_paste_visible_footprint = render_meta.get("render_visible_footprint_px")
        _, visible_mask = self._operations.paste_masked()(
            canvas,
            resized,
            resized_mask,
            center,
            target_size,
            angle,
            trim_before_paste=True,
            return_visible_mask=True,
            resize_to_target=False,
        )
        final_visible_footprint = self._geometry.visible_size()(visible_mask)
        render_meta["pre_paste_visible_footprint_px"] = pre_paste_visible_footprint
        render_meta["final_pasted_visible_footprint_px"] = final_visible_footprint
        render_meta["render_visible_footprint_px"] = final_visible_footprint
        render_meta["render_paste_rescaled"] = False
        render_meta["render_paste_resize_policy"] = "trim_already_sized_physical_object_no_second_resize"
        render_meta["_visible_mask_canvas"] = visible_mask
        return render_meta

    def paste_rotated_asset(self, canvas: np.ndarray, asset: np.ndarray, center: tuple[int, int], target_size: tuple[int, int], angle: float) -> np.ndarray:
        asset = self._operations.trim_rect()(asset)
        return self._operations.paste_masked()(canvas, asset, self._operations.physical_mask()(asset), center, target_size, angle)
