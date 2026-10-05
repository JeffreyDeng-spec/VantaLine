"""Reference video frame selection and thumbnail rendering without Web dependencies."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import cv2
import numpy as np
from .reference_media_ports import ReferenceMediaDependencies

@dataclass(frozen=True)
class AccessoryReferenceMedia:
    dependencies: ReferenceMediaDependencies

    def frame_detail_score(self, frame: np.ndarray) -> float:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        hist = cv2.calcHist([gray], [0], None, [64], [0, 256]).reshape(-1)
        hist = hist / max(float(hist.sum()), 1.0)
        entropy = float(-(hist * np.log2(hist + 1e-9)).sum())
        mean = float(gray.mean())
        exposure_penalty = abs(mean - 135.0) * 2.0
        return blur_score + entropy * 80.0 - exposure_penalty


    def frame_histogram(self, frame: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256]).reshape(-1)
        hist = hist / max(float(hist.sum()), 1.0)
        return hist.astype(np.float32)


    def extract_video_reference_frames(self, video_path: Path, output_dir: Path, max_frames: int) -> list[dict[str, Any]]:
        output_dir.mkdir(parents=True, exist_ok=True)
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return []
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration = frame_count / fps if frame_count > 0 and fps > 0 else 0.0
            target_samples = 72
            stride = max(1, frame_count // target_samples) if frame_count > 0 else max(1, int(fps // 2) or 1)
            candidates: list[dict[str, Any]] = []
            idx = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if idx % stride == 0:
                    score = self.dependencies.frame_detail_score()(frame)
                    hist = self.dependencies.frame_histogram()(frame)
                    candidates.append(
                        {
                            "frame_index": idx,
                            "time_seconds": idx / fps if fps > 0 else 0.0,
                            "score": score,
                            "hist": hist,
                            "frame": frame.copy(),
                        }
                    )
                idx += 1
                if frame_count <= 0 and idx > 1800:
                    break
            if not candidates:
                return []

            candidates.sort(key=lambda item: item["score"], reverse=True)
            pool = candidates[: min(len(candidates), 36)]
            selected: list[dict[str, Any]] = []
            min_time_gap = max(duration / (max_frames * 2), 0.35) if duration else 0.35
            while pool and len(selected) < max_frames:
                best_item = None
                best_value = -1e18
                for item in pool:
                    if not selected:
                        value = float(item["score"])
                    else:
                        time_gap = min(abs(float(item["time_seconds"]) - float(other["time_seconds"])) for other in selected)
                        if time_gap < min_time_gap and len(pool) > max_frames:
                            continue
                        hist_gap = min(float(cv2.compareHist(item["hist"], other["hist"], cv2.HISTCMP_BHATTACHARYYA)) for other in selected)
                        value = float(item["score"]) + hist_gap * 550.0 + time_gap * 12.0
                    if value > best_value:
                        best_item = item
                        best_value = value
                if best_item is None:
                    best_item = pool[0]
                selected.append(best_item)
                pool = [item for item in pool if item is not best_item]

            selected.sort(key=lambda item: int(item["frame_index"]))
            extracted = []
            for out_idx, item in enumerate(selected, start=1):
                out_path = output_dir / f"{video_path.stem}_reference_frame_{out_idx:02d}.jpg"
                self.dependencies._image_files().imwrite(str(out_path), item["frame"], [int(cv2.IMWRITE_JPEG_QUALITY), 94])
                extracted.append(
                    {
                        "path": str(out_path),
                        "source_video": str(video_path),
                        "frame_index": int(item["frame_index"]),
                        "time_seconds": round(float(item["time_seconds"]), 3),
                        "detail_score": round(float(item["score"]), 3),
                    }
                )
            return extracted
        finally:
            cap.release()


    def write_thumbnail(self, image: np.ndarray, out_path: Path, angle: float = 0.0, size: int = 360) -> dict[str, Any]:
        h, w = image.shape[:2]
        scale = min(size / max(h, w), 1.0)
        resized = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
        rh, rw = resized.shape[:2]
        canvas = np.full((size, size, 3), (238, 240, 242), dtype=np.uint8)
        patch = np.full((size, size, 3), (238, 240, 242), dtype=np.uint8)
        x = (size - rw) // 2
        y = (size - rh) // 2
        patch[y : y + rh, x : x + rw] = resized
        matrix = cv2.getRotationMatrix2D((size / 2, size / 2), angle, 1.0)
        rotated = cv2.warpAffine(patch, matrix, (size, size), flags=cv2.INTER_LINEAR, borderValue=(238, 240, 242))
        canvas[:] = rotated
        self.dependencies._image_files().imwrite(str(out_path), canvas)
        return {"url": self.dependencies.public_output_url()(out_path), "angle": angle, "width": size, "height": size}
