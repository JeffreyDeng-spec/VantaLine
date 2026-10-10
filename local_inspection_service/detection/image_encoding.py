"""JPEG data URLs from arrays and local images."""
from ..storage.artifacts.images import image_backend
from ..storage.artifacts.runtime import ArtifactRuntime
from collections.abc import Callable
from pathlib import Path
import base64
import numpy as np
from .media_ports import MediaImages, EncodeArray

class ImageEncoding:
    def __init__(self, images: Callable[[], MediaImages], error: Callable[[str], Exception], encode: EncodeArray,
                 *, runtime_provider: Callable[[], ArtifactRuntime | None]):
        if not callable(runtime_provider):
            raise TypeError("runtime_provider must be callable")
        self.runtime_provider = runtime_provider
        self.images, self.error, self.encode = images, error, encode

    def image_bgr_data_url(self, image_bgr: np.ndarray, max_side: int = 1280, quality: int = 82) -> str:
        image = image_bgr
        h, w = image.shape[:2]
        scale = min(float(max_side) / max(h, w), 1.0)
        if scale < 1.0:
            image = self.images().resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=self.images().INTER_AREA)
        ok, encoded = self.images().imencode(".jpg", image, [int(self.images().IMWRITE_JPEG_QUALITY), int(quality)])
        if not ok:
            raise self.error("Failed to encode image for AI provider")
        return f"data:image/jpeg;base64,{base64.b64encode(encoded.tobytes()).decode('ascii')}"

    def image_path_data_url(self, path: Path, max_side: int = 1024, quality: int = 78) -> str | None:
        image = image_backend(self.images(), runtime_provider=self.runtime_provider).imread(str(path), self.images().IMREAD_COLOR)
        if image is None:
            return None
        return self.encode(image, max_side=max_side, quality=quality)
