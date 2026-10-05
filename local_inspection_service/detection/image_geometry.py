"""Image scaling policy with the existing rounding and size bounds."""
import cv2
import numpy as np


def resize_bgr_max_side(image_bgr: np.ndarray, max_side: int) -> np.ndarray:
    height, width = image_bgr.shape[:2]
    longest = max(width, height)
    if longest <= max_side:
        return image_bgr
    scale = max_side / float(longest)
    next_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return cv2.resize(image_bgr, next_size, interpolation=cv2.INTER_AREA)
