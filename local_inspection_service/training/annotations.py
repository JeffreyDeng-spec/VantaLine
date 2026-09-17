"""YOLO annotation formats, dataset YAML and visual annotation previews."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any
import cv2


def yolo_label_line(class_index: int, polygon: list[list[int]], width: int = 1280, height: int = 900) -> str | None:
    if not polygon or len(polygon) < 3:
        return None
    values = [str(class_index)]
    for x, y in polygon:
        nx = min(1.0, max(0.0, float(x) / float(width)))
        ny = min(1.0, max(0.0, float(y) / float(height)))
        values.extend([f"{nx:.6f}", f"{ny:.6f}"])
    return " ".join(values)


def yolo_detection_label_line(
    class_index: int,
    bbox_xyxy: list[float] | None,
    width: int = 1280,
    height: int = 900,
) -> str | None:
    """YOLO detection label line: `class cx cy w h` (all normalized 0-1)."""
    if not bbox_xyxy or len(bbox_xyxy) < 4:
        return None
    x1, y1, x2, y2 = (float(v) for v in bbox_xyxy[:4])
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    bw = (x2 - x1) / float(width)
    bh = (y2 - y1) / float(height)
    if bw <= 0 or bh <= 0:
        return None
    cx = ((x1 + x2) / 2.0) / float(width)
    cy = ((y1 + y2) / 2.0) / float(height)
    cx = min(1.0, max(0.0, cx))
    cy = min(1.0, max(0.0, cy))
    bw = min(1.0, max(0.0, bw))
    bh = min(1.0, max(0.0, bh))
    return f"{class_index} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"


def write_dataset_yaml(path: Path, dataset_dir: Path, names: list[str]) -> None:
    safe_names = [
        re.sub(r"[^a-zA-Z0-9_]+", "_", str(name or f"class_{idx}")).strip("_") or f"class_{idx}"
        for idx, name in enumerate(names)
    ]
    body = [
        f"path: {dataset_dir.as_posix()}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "names:",
    ]
    body.extend([f"  {idx}: {name}" for idx, name in enumerate(safe_names)])
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class AnnotationMedia:
    output_root: Callable[[], Path]
    public_url: Callable[[Path], str]


class TrainingOutputLinks:
    def __init__(self, media: AnnotationMedia):
        self.media = media

    def public_training_output_url(self, path: Path) -> str:
        if str(path).startswith(str(self.media.output_root())):
            return self.media.public_url(path)
        return ""

class AnnotationPreview:
    def __init__(self, public_url: Callable[[Path], str]):
        self.public_url = public_url

    def write_training_annotation_preview(self, image_path: Path, labels: list[dict[str, Any]], out_path: Path) -> str:
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            return ""
        palette = [(0, 210, 60), (45, 125, 255), (250, 170, 35), (210, 65, 210), (60, 220, 220)]
        for idx, label in enumerate(labels):
            if label.get("detection_dropped"):
                continue
            bbox = label.get("amodal_bbox_xyxy")
            if not bbox or len(bbox) < 4:
                continue
            x1, y1, x2, y2 = (int(round(float(v))) for v in bbox[:4])
            color = palette[idx % len(palette)]
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 3)
            x = x1
            y = max(24, y1 - 8)
            cv2.putText(image, str(label.get("name") or label.get("id") or "part"), (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_path), image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        return self.public_url(out_path)
