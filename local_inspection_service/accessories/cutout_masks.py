"""Accessory cutout geometry without application imports."""
import cv2
import numpy as np


def foreground_mask(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    border = np.concatenate(
        [
            image[: max(3, h // 20), :, :].reshape(-1, 3),
            image[-max(3, h // 20) :, :, :].reshape(-1, 3),
            image[:, : max(3, w // 20), :].reshape(-1, 3),
            image[:, -max(3, w // 20) :, :].reshape(-1, 3),
        ],
        axis=0,
    )
    bg = np.median(border, axis=0).astype(np.float32)
    diff = np.linalg.norm(image.astype(np.float32) - bg, axis=2)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    green_bg = (hue > 30) & (hue < 100) & (sat > 24) & (val > 35)
    red = ((hue < 14) | (hue > 165)) & (sat > 70)
    dark = val < 78
    bright_glass = (sat < 62) & (val > 128) & (diff > 10)
    mask = ((~green_bg & (diff > 18)) | red | dark | bright_glass).astype(np.uint8) * 255
    edges = cv2.Canny(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 45, 140)
    mask = cv2.bitwise_or(mask, cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((17, 17), np.uint8), iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    return mask

def suppress_green_spill(image_bgr: np.ndarray) -> np.ndarray:
    """Green-spill decontamination: where the green channel exceeds both red and
    blue (a green-tinted boundary/halo pixel), pull green down to max(red,blue).
    This neutralises the green fringe around a dark object cut from a green plate
    without removing or shrinking the silhouette. Neutral/grey/silver/black object
    pixels (green ~= red ~= blue) are untouched."""
    if image_bgr is None or image_bgr.ndim != 3:
        return image_bgr
    blue, green, red = cv2.split(image_bgr)
    limit = np.maximum(red, blue)
    spill = green > limit
    green = green.copy()
    green[spill] = limit[spill]
    return cv2.merge([blue, green, red])

def bright_green_conveyor_mask(image_bgr: np.ndarray) -> np.ndarray:
    """Boolean mask of UNAMBIGUOUS bright conveyor-green pixels. Tuned to catch the
    saturated, well-lit green plate while sparing dark/olive object pixels (e.g.
    carbon-fibre) and dark anti-aliased object edges, so it can trim a green halo
    without biting into the object."""
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    hue, sat, val = cv2.split(hsv)
    blue, green, red = cv2.split(image_bgr.astype(np.int16))
    return (
        (hue >= 35)
        & (hue <= 95)
        & (sat >= 70)
        & (val >= 80)
        & ((green - np.maximum(red, blue)) > 25)
    )
