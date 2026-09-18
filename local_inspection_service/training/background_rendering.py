"""Training background image transforms and explicitly composed render orchestration."""
from collections.abc import Callable
import math
from typing import Any
import cv2
import numpy as np

Record = dict[str, Any]
RenderedBackground = tuple[np.ndarray, Record]


def background_candidates_for_split(library: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    if len(library) >= 3:
        if split == "val":
            return [library[-2]]
        if split == "test":
            return [library[-1]]
        return library[:-2]
    if len(library) == 2:
        return [library[1]] if split in {"val", "test"} else [library[0]]
    return library


def synthetic_training_background(rng: np.random.Generator) -> tuple[np.ndarray, dict[str, Any]]:
    canvas = np.full((900, 1280, 3), (232, 234, 235), dtype=np.uint8)
    base_color = np.array((87, 116, 98), dtype=np.float32)
    jitter = rng.normal(0, 6, size=3)
    color = tuple(int(np.clip(value, 0, 255)) for value in base_color + jitter)
    cv2.rectangle(canvas, (70, 100), (1210, 800), color, -1)
    for _ in range(18):
        x1 = int(rng.integers(70, 1210))
        y1 = int(rng.integers(100, 800))
        x2 = int(np.clip(x1 + rng.normal(0, 220), 70, 1210))
        y2 = int(np.clip(y1 + rng.normal(0, 36), 100, 800))
        shade = int(rng.integers(70, 135))
        cv2.line(canvas, (x1, y1), (x2, y2), (shade, shade, shade), 1, cv2.LINE_AA)
    return canvas, {
        "background_id": "synthetic_conveyor_fallback",
        "background_source": "generated_same_environment_fallback",
        "background_source_asset": None,
        "background_library_size": 0,
        "background_split_pool_size": 0,
        "background_split_pool_isolated": False,
    }


def fit_training_background_to_canvas(
    image: np.ndarray,
    rng: np.random.Generator,
    target_size: tuple[int, int] = (1280, 900),
) -> tuple[np.ndarray, dict[str, Any]]:
    target_w, target_h = target_size
    source_h, source_w = image.shape[:2]
    crop_scale = float(rng.uniform(1.0, 1.08))
    crop_w = int(round(target_w * crop_scale))
    crop_h = int(round(target_h * crop_scale))
    resize_ratio = max(crop_w / max(1, source_w), crop_h / max(1, source_h))
    resized_w = max(crop_w, int(math.ceil(source_w * resize_ratio)))
    resized_h = max(crop_h, int(math.ceil(source_h * resize_ratio)))
    resized = cv2.resize(image, (resized_w, resized_h), interpolation=cv2.INTER_AREA)
    max_x = max(0, resized_w - crop_w)
    max_y = max(0, resized_h - crop_h)
    crop_x = int(rng.integers(0, max_x + 1)) if max_x else 0
    crop_y = int(rng.integers(0, max_y + 1)) if max_y else 0
    crop = resized[crop_y : crop_y + crop_h, crop_x : crop_x + crop_w]
    canvas = cv2.resize(crop, (target_w, target_h), interpolation=cv2.INTER_AREA)
    return canvas, {
        "background_crop_scale": round(crop_scale, 4),
        "background_crop_xywh": [crop_x, crop_y, crop_w, crop_h],
        "background_resized_size_px": [resized_w, resized_h],
        "background_original_size_px": [source_w, source_h],
    }


def augment_training_background(canvas: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, dict[str, Any]]:
    image = canvas.astype(np.float32)
    contrast = float(rng.uniform(0.92, 1.1))
    brightness = float(rng.uniform(-14.0, 14.0))
    image = image * contrast + brightness
    noise_std = float(rng.uniform(1.0, 4.5))
    image += rng.normal(0.0, noise_std, size=image.shape).astype(np.float32)
    image = np.clip(image, 0, 255).astype(np.uint8)
    blur_kernel = 0
    if float(rng.random()) < 0.35:
        blur_kernel = int(rng.choice([3, 5]))
        image = cv2.GaussianBlur(image, (blur_kernel, blur_kernel), 0)
    glare_applied = False
    glare_alpha = 0.0
    texture_lines = int(rng.integers(6, 18))
    overlay = image.copy()
    for _ in range(texture_lines):
        x1 = int(rng.integers(70, 1210))
        y1 = int(rng.integers(100, 800))
        x2 = int(np.clip(x1 + rng.normal(0, 260), 70, 1210))
        y2 = int(np.clip(y1 + rng.normal(0, 28), 100, 800))
        shade = int(rng.integers(42, 210))
        cv2.line(overlay, (x1, y1), (x2, y2), (shade, shade, shade), 1, cv2.LINE_AA)
    alpha = max(glare_alpha, 0.03)
    image = cv2.addWeighted(overlay, alpha, image, 1.0 - alpha, 0)
    return image, {
        "background_augmentation": {
            "crop_shift": True,
            "brightness_delta": round(brightness, 3),
            "contrast": round(contrast, 4),
            "noise_std": round(noise_std, 3),
            "blur_kernel": blur_kernel,
            "glare_applied": glare_applied,
            "glare_alpha": round(glare_alpha, 4),
            "texture_lines": texture_lines,
        }
    }


class TrainingBackgroundRenderer:
    def __init__(self, library: Callable[[str | None], list[Record]],
                 candidates: Callable[[list[Record], str], list[Record]],
                 synthetic: Callable[[np.random.Generator], RenderedBackground],
                 fit: Callable[[np.ndarray, np.random.Generator], RenderedBackground],
                 augment: Callable[[np.ndarray, np.random.Generator], RenderedBackground]):
        self.library, self.candidates, self.synthetic = library, candidates, synthetic
        self.fit, self.augment = fit, augment

    def render_training_background(self,
        rng: np.random.Generator,
        split: str | None = None,
        background_set_id: str | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        split_name = split if split in {"train", "val", "test"} else "preview"
        library = self.library(background_set_id)
        candidates = self.candidates(library, split_name)
        if not candidates:
            canvas, meta = self.synthetic(rng)
        else:
            item = candidates[int(rng.integers(0, len(candidates)))]
            background = cv2.imread(str(item["path"]), cv2.IMREAD_COLOR)
            if background is None:
                canvas, meta = self.synthetic(rng)
                meta["background_source_error"] = f"unreadable_background:{item['path']}"
            else:
                canvas, crop_meta = self.fit(background, rng)
                meta = {
                    "background_id": item["id"],
                    "background_source": item["source"],
                    "background_source_asset": item["source_asset"],
                    "background_set_id": item.get("background_set_id"),
                    "background_library_size": item["library_size"],
                    "background_split_pool_size": len(candidates),
                    "background_split_pool_isolated": bool(len(library) > 1 and set(item["id"] for item in candidates) != set(item["id"] for item in library)),
                    **crop_meta,
                }
        canvas, augmentation_meta = self.augment(canvas, rng)
        meta.update(augmentation_meta)
        meta["background_split"] = split_name
        meta["background_policy"] = "same_environment_library_with_per_sample_crop_shift_photometric_noise_texture_no_glare"
        return canvas, meta
