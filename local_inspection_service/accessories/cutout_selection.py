"""Accessory cutout geometry without application imports."""
import cv2
import numpy as np
from .cutout_geometry_ports import SelectionOperations


class ObjectCutoutSelection:
    def __init__(self, selection: SelectionOperations) -> None:
        self._selection = selection


    def object_cutout_from_image(self, image: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray] | None:
        mask = self._selection.foreground()(image)
        num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        components = []
        image_area = image.shape[0] * image.shape[1]
        for idx in range(1, num):
            x, y, w, h, area = stats[idx]
            if area < max(500, image_area * 0.001) or area > image_area * 0.55:
                continue
            if w < 8 or h < 8:
                continue
            components.append((x, y, w, h, area))
        if not components:
            return None
        components = sorted(components, key=lambda item: item[4], reverse=True)[:8]
        weights = np.array([item[4] for item in components], dtype=float)
        weights = weights / weights.sum()
        x, y, w, h, _ = components[int(rng.choice(len(components), p=weights))]
        pad = max(8, int(max(w, h) * 0.18))
        x1, y1 = max(0, x - pad), max(0, y - pad)
        x2, y2 = min(image.shape[1], x + w + pad), min(image.shape[0], y + h + pad)
        crop = image[y1:y2, x1:x2].copy()
        crop_mask = mask[y1:y2, x1:x2].copy()
        crop_mask = cv2.GaussianBlur(crop_mask, (5, 5), 0)
        return crop, crop_mask

    def green_screen_object_cutout_with_bbox(self, image: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hue = hsv[:, :, 0]
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        red = (((hue < 14) | (hue > 165)) & (sat > 70)).astype(np.uint8) * 255
        dark = ((val < 92) & (sat > 25)).astype(np.uint8) * 255
        glass_highlight = ((sat < 80) & (val > 125)).astype(np.uint8) * 255
        edges = cv2.Canny(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 45, 135)
        seed = cv2.bitwise_or(cv2.bitwise_or(red, dark), cv2.bitwise_or(glass_highlight, edges))
        seed = cv2.morphologyEx(seed, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
        joined = cv2.dilate(seed, np.ones((29, 29), np.uint8), iterations=1)
        joined = cv2.morphologyEx(joined, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8), iterations=1)
        num, labels, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
        components = []
        image_area = image.shape[0] * image.shape[1]
        for idx in range(1, num):
            x, y, w, h, area = stats[idx]
            if area < max(650, image_area * 0.002) or area > image_area * 0.45:
                continue
            if w < 18 or h < 18:
                continue
            anchor = int(red[y : y + h, x : x + w].sum() // 255) + int(dark[y : y + h, x : x + w].sum() // 255)
            highlight = int(glass_highlight[y : y + h, x : x + w].sum() // 255)
            components.append((x, y, w, h, area, anchor, highlight))
        if not components:
            fallback = self._selection.object_fallback()(image, rng)
            if not fallback:
                return None
            return fallback[0], fallback[1], (0, 0, fallback[0].shape[1], fallback[0].shape[0])
        anchored = [item for item in components if item[5] > 25]
        components = sorted(anchored or components, key=lambda item: item[5] * 12 + item[6] * 0.2 + item[4] * 0.02, reverse=True)[:5]
        x, y, w, h, *_ = components[0]
        pad = max(10, int(max(w, h) * 0.08))
        x1, y1 = max(0, x - pad), max(0, y - pad)
        x2, y2 = min(image.shape[1], x + w + pad), min(image.shape[0], y + h + pad)
        crop = image[y1:y2, x1:x2].copy()
        crop_hsv = hsv[y1:y2, x1:x2]
        crop_seed = seed[y1:y2, x1:x2]
        crop_joined = joined[y1:y2, x1:x2]
        ch, cs, cv = crop_hsv[:, :, 0], crop_hsv[:, :, 1], crop_hsv[:, :, 2]
        crop_red = (((ch < 14) | (ch > 165)) & (cs > 70))
        crop_dark = (cv < 92) & (cs > 25)
        crop_highlight = (cs < 80) & (cv > 125)
        alpha = np.zeros(crop.shape[:2], dtype=np.uint8)
        alpha[crop_highlight | (crop_seed > 0)] = 178
        alpha[crop_red | crop_dark] = 255
        alpha = cv2.dilate(alpha, np.ones((3, 3), np.uint8), iterations=1)
        alpha = cv2.GaussianBlur(alpha, (5, 5), 0)
        keep = np.zeros_like(alpha)
        num, labels, stats, _ = cv2.connectedComponentsWithStats((alpha > 28).astype(np.uint8), connectivity=8)
        alpha_area = alpha.shape[0] * alpha.shape[1]
        components = []
        for idx in range(1, num):
            x, y, w, h, area = stats[idx]
            if area < max(35, alpha_area * 0.002):
                continue
            components.append((idx, area))
        for idx, _ in sorted(components, key=lambda item: item[1], reverse=True)[:2]:
            keep[labels == idx] = 255
        if components:
            alpha = cv2.bitwise_and(alpha, keep)
        # Treat green spill in glass as transparency, not white material.
        green_tint = (ch > 30) & (ch < 100) & (cs > 22)
        alpha[green_tint & (alpha > 0) & ~(crop_red | crop_dark)] = np.minimum(alpha[green_tint & (alpha > 0) & ~(crop_red | crop_dark)], 82)
        return crop, alpha, (int(x1), int(y1), int(x2), int(y2))

    def ai_background_cutout(self, image: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
        result = self._selection.bounded_ai()(image)
        if not result:
            return None
        return result[0], result[1]

    def green_screen_object_cutout(self, image: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray] | None:
        result = self._selection.bounded_green()(image, rng)
        if not result:
            return None
        return result[0], result[1]
