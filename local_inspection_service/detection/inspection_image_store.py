"""Inspection image persistence with existing failure boundaries."""
from collections.abc import Callable
from pathlib import Path
import hashlib
import numpy as np
from .media_ports import MediaImages, InspectionImagePolicy

class InspectionImageStore:
    def __init__(self, images: Callable[[], MediaImages], policy: InspectionImagePolicy,
                 now_ns: Callable[[], int], name: Callable[[str], str]):
        self.images, self.policy, self.now_ns, self.name = images, policy, now_ns, name

    def write_mcp_inspection_image(self, image_bgr: np.ndarray, request_id: str) -> Path | None:
        try:
            self.policy.directory().mkdir(parents=True, exist_ok=True)
            image = image_bgr
            h, w = image.shape[:2]
            scale = min(float(self.policy.max_side()) / max(h, w), 1.0)
            if scale < 1.0:
                image = self.images().resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=self.images().INTER_AREA)
            digest = hashlib.sha1(f"{request_id}:{self.now_ns()}".encode("utf-8")).hexdigest()[:12]
            path = self.policy.directory() / f"{self.name(request_id)[:80]}_{digest}.jpg"
            ok = self.images().imwrite(str(path), image, [int(self.images().IMWRITE_JPEG_QUALITY), self.policy.quality()])
            return path if ok else None
        except Exception:
            return None
