"""Accessory cutout geometry without application imports."""
import cv2
import numpy as np
from typing import Any
from .cutout_geometry_ports import ChromaPolicyOperations, ChromaMatteOperations


class ChromaCutoutProcessor:
    def __init__(self, policy: ChromaPolicyOperations, matte: ChromaMatteOperations) -> None:
        self._policy = policy
        self._matte = matte


    def suppress_chroma_spill(self, image_bgr: np.ndarray, screen: dict[str, Any] | None = None) -> np.ndarray:
        if image_bgr is None or image_bgr.ndim != 3:
            return image_bgr
        name = str(self._policy.normalize()(screen).get("name") or "green")
        if name == "green":
            return self._policy.green_spill()(image_bgr)
        blue, green, red = cv2.split(image_bgr)
        if name == "blue":
            limit = np.maximum(red, green)
            spill = blue > limit
            blue = blue.copy()
            blue[spill] = limit[spill]
            return cv2.merge([blue, green, red])
        if name == "red":
            limit = np.maximum(blue, green)
            spill = red > limit
            red = red.copy()
            red[spill] = limit[spill]
            return cv2.merge([blue, green, red])
        return image_bgr

    def chroma_background_mask(self, image_bgr: np.ndarray, screen: dict[str, Any] | None = None) -> np.ndarray:
        screen = self._policy.normalize()(screen)
        name = str(screen.get("name") or "green")
        target_bgr = np.array([screen["rgb"][2], screen["rgb"][1], screen["rgb"][0]], dtype=np.int16)
        image_i16 = image_bgr.astype(np.int16)
        diff = np.abs(image_i16 - target_bgr.reshape(1, 1, 3))
        near_exact = (np.max(diff, axis=2) <= 42) | ((np.max(diff, axis=2) <= 70) & (np.sum(diff, axis=2) <= 120))
        blue, green, red = cv2.split(image_i16)
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        hue, sat, val = cv2.split(hsv)
        if name == "blue":
            chroma_shadow = (
                (hue >= 96)
                & (hue <= 135)
                & (sat >= 28)
                & (val >= 28)
                & (blue >= 90)
                & ((blue - np.maximum(red, green)) >= 28)
                & (red <= 150)
                & (green <= 150)
            )
        elif name == "red":
            chroma_shadow = (
                ((hue <= 12) | (hue >= 168))
                & (sat >= 28)
                & (val >= 28)
                & (red >= 90)
                & ((red - np.maximum(blue, green)) >= 28)
                & (blue <= 150)
                & (green <= 150)
            )
        else:
            chroma_shadow = (
                (hue >= 35)
                & (hue <= 95)
                & (sat >= 28)
                & (val >= 28)
                & (green >= 90)
                & ((green - np.maximum(red, blue)) >= 28)
                & (red <= 150)
                & (blue <= 150)
            )
        return near_exact | self._policy.saturated()(image_bgr, screen) | chroma_shadow

    def chroma_distance_alpha(self, image_bgr: np.ndarray, screen: dict[str, Any] | None = None) -> np.ndarray:
        screen = self._policy.normalize()(screen)
        target_bgr = np.array([screen["rgb"][2], screen["rgb"][1], screen["rgb"][0]], dtype=np.float32)
        diff = image_bgr.astype(np.float32) - target_bgr.reshape(1, 1, 3)
        distance = np.linalg.norm(diff, axis=2)
        alpha = np.clip((distance - 24.0) * (255.0 / 96.0), 0, 255)
        return alpha.astype(np.uint8)

    def chroma_screen_object_cutout(self,
        image_bgr: np.ndarray,
        screen: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
        """Remove a fixed solid chroma tabletop/background and keep the largest object."""
        if image_bgr is None or image_bgr.ndim != 3:
            return None
        height, width = image_bgr.shape[:2]
        background = self._matte.background()(image_bgr, screen)
        if float(background.mean()) < 0.20:
            return None
        foreground = (~background).astype(np.uint8) * 255
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8), iterations=2)
        num, labels, stats, _ = cv2.connectedComponentsWithStats(foreground, connectivity=8)
        if num <= 1:
            return None
        idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        if int(stats[idx, cv2.CC_STAT_AREA]) < max(400, int(height * width * 0.0015)):
            return None
        mask = (labels == idx).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        filled = np.zeros_like(mask)
        cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)
        inside_distance = cv2.distanceTransform((filled > 0).astype(np.uint8), cv2.DIST_L2, 3)
        core = inside_distance >= 3.0
        edge_band = (filled > 0) & ~core
        shape_alpha = np.clip(inside_distance * (255.0 / 3.0), 0, 255).astype(np.uint8)
        color_alpha = self._matte.distance()(image_bgr, screen)
        alpha = np.zeros_like(filled, dtype=np.uint8)
        alpha[core] = 255
        alpha[edge_band] = np.minimum(shape_alpha[edge_band], np.maximum(color_alpha[edge_band], 48))
        alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
        ys, xs = np.where(alpha > 8)
        if len(xs) < 240:
            return None
        x1, x2 = int(xs.min()), int(xs.max()) + 1
        y1, y2 = int(ys.min()), int(ys.max()) + 1
        crop_bgr = self._matte.spill()(image_bgr[y1:y2, x1:x2].copy(), screen)
        return crop_bgr, alpha[y1:y2, x1:x2].copy(), (x1, y1, x2, y2)

    def green_conveyor_object_cutout(self,
        image_bgr: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
        """Chroma-key a single object off an AI-generated green-conveyor plate.
    Removes green (and green-tinted cast-shadow) pixels, keeps the largest
    non-green blob, fills interior holes. Used as the fallback when the AI matte
    is unavailable; tuned to avoid biting into dark object edges or thin features
    (no aggressive open/erode that would shave a thin part's silhouette)."""
        if image_bgr is None or image_bgr.ndim != 3:
            return None
        height, width = image_bgr.shape[:2]
        blue, green, red = cv2.split(image_bgr.astype(np.int16))
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        hue, sat, val = cv2.split(hsv)
        # Only treat reasonably bright, saturated green as background so dark, low-value
        # object-edge pixels (which read slightly green from background bleed) survive.
        green_hue = (hue >= 35) & (hue <= 95) & (sat >= 45) & (val >= 60)
        green_dominant = ((green - np.maximum(red, blue)) > 22) & (sat >= 35) & (val >= 60)
        background = green_hue | green_dominant
        foreground = (~background).astype(np.uint8) * 255
        # Gentle cleanup only: a small open removes specks; close bridges the matte.
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, np.ones((13, 13), np.uint8), iterations=2)
        num, labels, stats, _ = cv2.connectedComponentsWithStats(foreground, connectivity=8)
        if num <= 1:
            return None
        idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        if int(stats[idx, cv2.CC_STAT_AREA]) < max(400, int(height * width * 0.0015)):
            return None
        mask = (labels == idx).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        filled = np.zeros_like(mask)
        cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)
        # No erosion (keep the full silhouette); a tiny blur anti-aliases the contour.
        filled = cv2.GaussianBlur(filled, (3, 3), 0)
        ys, xs = np.where(filled > 8)
        if len(xs) < 240:
            return None
        x1, x2 = int(xs.min()), int(xs.max()) + 1
        y1, y2 = int(ys.min()), int(ys.max()) + 1
        crop_bgr = self._policy.green_spill()(image_bgr[y1:y2, x1:x2].copy())
        return crop_bgr, filled[y1:y2, x1:x2].copy(), (x1, y1, x2, y2)
