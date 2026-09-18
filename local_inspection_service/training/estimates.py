"""Existing training resource estimates; no runtime dependencies."""
import math
from typing import Any


def training_estimate(
    sample_count: int,
    include_training: bool = False,
    include_generation: bool = True,
    epochs: int = 80,
    image_size: int = 640,
    selected_count: int = 1,
    train_mode: str = "yolo",
) -> dict[str, Any]:
    sample_count = max(1, min(20000, int(sample_count)))
    selected_count = max(1, min(100, int(selected_count or 1)))
    epochs = max(1, min(500, int(epochs or 1)))
    image_size = max(320, min(1280, int(image_size or 640)))
    generate_seconds = 8 + sample_count * (0.12 + selected_count * 0.025 + 0.018) if include_generation else 0
    train_seconds = 0.0
    if include_training:
        size_factor = (image_size / 640.0) ** 2
        mode_factor = 1.03 if train_mode == "yolo_ocr" else 1.0
        train_seconds = 75 + epochs * 7 + sample_count * epochs * 0.085 * size_factor * mode_factor
    generate_minutes = max(0, int(math.ceil(generate_seconds / 60.0)))
    train_minutes = max(0, int(math.ceil(train_seconds / 60.0)))
    return {
        "sample_count": sample_count,
        "estimated_minutes": max(1, generate_minutes + train_minutes),
        "estimated_generate_minutes": generate_minutes,
        "estimated_train_minutes": train_minutes,
        "estimated_gb": round(sample_count * 1.8 / 1024, 2),
        "estimate_formula_version": "gpu-cache-autobatch-v3",
    }
