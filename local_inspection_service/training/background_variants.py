"""Local background pixel variants and minimum-image initialization with explicit dependencies."""
from collections.abc import Callable
from pathlib import Path
from typing import Protocol
import cv2
import numpy as np


class CreateBackgroundVariants(Protocol):
    def __call__(self, source_path: Path, set_dir: Path, count: int = 5) -> list[Path]: ...


class BackgroundVariants:
    def __init__(self, clock: Callable[[], float]):
        self.clock = clock

    def create_background_variants_from_source(self, source_path: Path, set_dir: Path, count: int = 5) -> list[Path]:
        image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
        if image is None:
            return []
        set_dir.mkdir(parents=True, exist_ok=True)
        created: list[Path] = []
        rng = np.random.default_rng(int(self.clock() * 1000) % (2**32 - 1))
        h, w = image.shape[:2]
        for idx in range(1, count + 1):
            variant = image.astype(np.float32)
            contrast = float(rng.uniform(0.94, 1.08))
            brightness = float(rng.uniform(-10, 10))
            variant = variant * contrast + brightness
            if float(rng.random()) < 0.8:
                variant += rng.normal(0, float(rng.uniform(1.0, 3.2)), size=variant.shape).astype(np.float32)
            variant = np.clip(variant, 0, 255).astype(np.uint8)
            scale = float(rng.uniform(1.0, 1.045))
            crop_w = max(1, int(w / scale))
            crop_h = max(1, int(h / scale))
            x = int(rng.integers(0, max(1, w - crop_w + 1)))
            y = int(rng.integers(0, max(1, h - crop_h + 1)))
            variant = cv2.resize(variant[y : y + crop_h, x : x + crop_w], (w, h), interpolation=cv2.INTER_AREA)
            overlay = variant.copy()
            for _ in range(int(rng.integers(5, 14))):
                x1 = int(rng.integers(0, w))
                y1 = int(rng.integers(0, h))
                x2 = int(np.clip(x1 + rng.normal(0, w * 0.2), 0, w - 1))
                y2 = int(np.clip(y1 + rng.normal(0, h * 0.025), 0, h - 1))
                shade = int(rng.integers(45, 210))
                cv2.line(overlay, (x1, y1), (x2, y2), (shade, shade, shade), 1, cv2.LINE_AA)
            alpha = float(rng.uniform(0.025, 0.06))
            variant = cv2.addWeighted(overlay, alpha, variant, 1.0 - alpha, 0)
            output = set_dir / f"{source_path.stem}_variant_{idx:02d}.png"
            cv2.imwrite(str(output), variant)
            created.append(output)
        return created



class BackgroundMinimumImages:
    def __init__(self, safe: Callable[[str], str], sets: Callable[[], Path],
                 images: Callable[[Path], list[Path]], create: Callable[[], CreateBackgroundVariants]):
        self.safe, self.sets, self.images, self.create = safe, sets, images, create

    def ensure_background_set_minimum_images(self, set_id: str, min_count: int = 6) -> None:
        clean_id = self.safe(set_id)
        set_dir = self.sets() / clean_id
        images = self.images(set_dir)
        if len(images) >= min_count or not images:
            return
        self.create()(images[0], set_dir, max(0, min_count - len(images)))
