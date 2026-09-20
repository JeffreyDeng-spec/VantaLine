"""Accessory cutout behavior without application imports."""
from typing import Any
import cv2
import numpy as np
from .cutout_ports import CutoutRuntimeOperations, CutoutGreenOperations


class BackgroundCutoutProcessor:
    def __init__(self, runtime: CutoutRuntimeOperations, green: CutoutGreenOperations) -> None:
        self._runtime = runtime
        self._green = green


    def ai_background_cutout_with_bbox(self, image: np.ndarray) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
        session = self._runtime.session()()
        if session is None:
            return None
        try:
            from PIL import Image
            from rembg import remove

            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            with self._runtime.lock():
                result = remove(
                    Image.fromarray(rgb),
                    session=session,
                    alpha_matting=True,
                    alpha_matting_foreground_threshold=240,
                    alpha_matting_background_threshold=12,
                    alpha_matting_erode_size=8,
                )
            rgba = np.array(result.convert("RGBA"))
            alpha = rgba[:, :, 3]
            ys, xs = np.where(alpha > 12)
            if len(xs) == 0 or len(ys) == 0:
                return None
            x1, x2 = max(0, xs.min() - 4), min(alpha.shape[1], xs.max() + 5)
            y1, y2 = max(0, ys.min() - 4), min(alpha.shape[0], ys.max() + 5)
            if (x2 - x1) * (y2 - y1) < 240:
                return None
            crop_rgb = rgba[y1:y2, x1:x2, :3]
            crop_alpha = alpha[y1:y2, x1:x2]
            crop_bgr = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2BGR)
            return crop_bgr, crop_alpha, (int(x1), int(y1), int(x2), int(y2))
        except Exception:
            return None

    def precise_green_plate_cutout(self,
        image_bgr: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
        """High-precision cut-out of the single object on an AI green-conveyor plate
    using the local AI matte (rembg/u2net). Keeps the FULL silhouette (thin ends,
    corrugations, caps — no erosion) and only trims unambiguous bright-green halo
    pixels. Falls back to None when rembg is unavailable so callers can use the
    chroma-key path."""
        if image_bgr is None or image_bgr.ndim != 3:
            return None
        session = self._runtime.session()()
        if session is None:
            return None
        try:
            from PIL import Image
            from rembg import remove

            rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            with self._runtime.lock():
                result = remove(
                    Image.fromarray(rgb),
                    session=session,
                    alpha_matting=True,
                    alpha_matting_foreground_threshold=240,
                    alpha_matting_background_threshold=10,
                    alpha_matting_erode_size=0,
                )
            alpha = np.array(result.convert("RGBA"))[:, :, 3]
        except Exception:
            return None
        if alpha is None or alpha.ndim != 2:
            return None
        # Drop only unambiguous bright conveyor-green pixels (halo), never the object.
        alpha = alpha.copy()
        alpha[self._green.mask()(image_bgr)] = 0
        binary = (alpha > 16).astype(np.uint8)
        if int(binary.sum()) < 240:
            return None
        # Keep the largest connected component, then fill interior holes so surface
        # texture/holes inside the object don't punch through the matte.
        num, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        if num <= 1:
            return None
        idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        height, width = image_bgr.shape[:2]
        if int(stats[idx, cv2.CC_STAT_AREA]) < max(400, int(height * width * 0.0015)):
            return None
        component = (labels == idx).astype(np.uint8)
        contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        solid = np.zeros((height, width), dtype=np.uint8)
        cv2.drawContours(solid, contours, -1, 255, thickness=cv2.FILLED)
        # Combine the soft matte alpha (precise edges) with the solid silhouette so we
        # keep crisp anti-aliased boundaries without any erosion of the object.
        refined = np.where(solid > 0, alpha, 0).astype(np.uint8)
        ys, xs = np.where(refined > 8)
        if len(xs) < 240:
            return None
        x1, x2 = int(xs.min()), int(xs.max()) + 1
        y1, y2 = int(ys.min()), int(ys.max()) + 1
        # Neutralise any residual green fringe on the kept boundary pixels.
        crop_bgr = self._green.spill()(image_bgr[y1:y2, x1:x2].copy())
        return crop_bgr, refined[y1:y2, x1:x2].copy(), (x1, y1, x2, y2)
