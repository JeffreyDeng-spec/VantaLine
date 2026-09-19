"""Reference-image collection and tile rendering."""
from collections.abc import Callable
from pathlib import Path
from typing import Any
import numpy as np
from .media_ports import MediaImages, MediaArrays, ReferenceCollectionPolicy, BoundedText, EncodePath, Record

class ReferenceCollection:
    def __init__(self, text: Callable[[], BoundedText], uid: Callable[[Record], str],
                 paths: Callable[[Record], list[Path]], encode: EncodePath,
                 mime: Callable[[str], tuple[str, str]], policy: ReferenceCollectionPolicy):
        self.text, self.uid, self.paths, self.encode, self.mime, self.policy = text, uid, paths, encode, mime, policy

    def tool_accessory_reference_collect(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = payload.get("accessory") if isinstance(payload.get("accessory"), dict) else {}
        accessory_id = self.text()(payload.get("accessory_id") or self.uid(item), 120)
        try:
            max_images = max(0, min(16, int(payload.get("max_images", self.policy.limit()))))
        except (TypeError, ValueError):
            max_images = self.policy.limit()
        try:
            max_side = max(64, min(2048, int(payload.get("max_side", self.policy.max_side()))))
        except (TypeError, ValueError):
            max_side = self.policy.max_side()
        try:
            quality = max(40, min(95, int(payload.get("quality", self.policy.quality()))))
        except (TypeError, ValueError):
            quality = self.policy.quality()
        raw_paths = payload.get("reference_image_paths")
        paths = [Path(str(path)) for path in raw_paths] if isinstance(raw_paths, list) else self.paths(item)
        descriptors: list[dict[str, Any]] = []
        seen: set[str] = set()
        for path in paths:
            path_key = str(path)
            if path_key in seen:
                continue
            seen.add(path_key)
            data_url = self.encode(path, max_side=max_side, quality=quality)
            if not data_url:
                continue
            mime_type, _ = self.mime(data_url)
            descriptors.append(
                {
                    "accessory_id": accessory_id,
                    "source_path": path_key,
                    "mime_type": mime_type,
                    "data_url": data_url,
                    "detail": "low",
                    "ordinal": len(descriptors) + 1,
                }
            )
            if len(descriptors) >= max_images:
                break
        return {
            "tool": "accessory.reference.collect",
            "accessory_id": accessory_id,
            "references": descriptors,
            "reference_count": len(descriptors),
            "max_images": max_images,
        }


class ReferenceTileRenderer:
    def __init__(self, images: Callable[[], MediaImages], arrays: Callable[[], MediaArrays]):
        self.images, self.arrays = images, arrays

    def fit_image_into_cell(self, image: np.ndarray, width: int, height: int) -> np.ndarray:
        canvas = self.arrays().full((height, width, 3), 255, dtype=self.arrays().uint8)
        if image is None:
            return canvas
        if image.ndim == 2:
            image = self.images().cvtColor(image, self.images().COLOR_GRAY2BGR)
        if image.ndim == 3 and image.shape[2] >= 4:
            alpha = (image[:, :, 3].astype(self.arrays().float32) / 255.0)[..., None]
            bgr = image[:, :, :3].astype(self.arrays().float32)
            background = self.arrays().full_like(bgr, 255.0)
            image = (bgr * alpha + background * (1.0 - alpha)).astype(self.arrays().uint8)
        src_h, src_w = image.shape[:2]
        if src_h <= 0 or src_w <= 0:
            return canvas
        scale = min(width / src_w, height / src_h)
        resized_w = max(1, int(round(src_w * scale)))
        resized_h = max(1, int(round(src_h * scale)))
        resized = self.images().resize(image[:, :, :3], (resized_w, resized_h), interpolation=self.images().INTER_AREA)
        x = (width - resized_w) // 2
        y = (height - resized_h) // 2
        canvas[y : y + resized_h, x : x + resized_w] = resized
        return canvas
