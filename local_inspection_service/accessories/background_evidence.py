"""Background plate derivation and reference signatures."""
from typing import Any
from pathlib import Path
import time
import cv2
import numpy as np
from .background_evidence_ports import PlateSources, PlatePolicy, BackgroundMasks, SignatureSources, SignaturePolicy, SignatureProjections

def background_patch_boxes(width: int, height: int) -> list[tuple[int, int, int, int]]:
    patch = max(48, min(256, int(round(min(width, height) * 0.18))))
    patch = min(patch, width, height)
    if patch <= 0:
        return []
    centers = [
        (patch // 2, patch // 2),
        (width - patch // 2, patch // 2),
        (patch // 2, height - patch // 2),
        (width - patch // 2, height - patch // 2),
        (width // 2, patch // 2),
        (width // 2, height - patch // 2),
        (patch // 2, height // 2),
        (width - patch // 2, height // 2),
    ]
    boxes: list[tuple[int, int, int, int]] = []
    seen: set[tuple[int, int, int, int]] = set()
    for cx, cy in centers:
        x1 = max(0, min(width - patch, int(cx - patch // 2)))
        y1 = max(0, min(height - patch, int(cy - patch // 2)))
        box = (x1, y1, x1 + patch, y1 + patch)
        if box not in seen:
            boxes.append(box)
            seen.add(box)
    return boxes

def background_patch_signature(patch_bgr: np.ndarray) -> dict[str, Any] | None:
    if patch_bgr is None or patch_bgr.ndim != 3 or patch_bgr.shape[0] < 16 or patch_bgr.shape[1] < 16:
        return None
    sample = cv2.resize(patch_bgr, (64, 64), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(sample, cv2.COLOR_BGR2LAB).astype(np.float32) / 255.0
    hsv = cv2.cvtColor(sample, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([hsv], [0, 1], None, [8, 4], [0, 180, 0, 256]).astype(np.float32).flatten()
    hist_sum = float(hist.sum())
    if hist_sum > 0:
        hist /= hist_sum
    return {
        "lab_mean": lab.reshape(-1, 3).mean(axis=0).tolist(),
        "lab_std": lab.reshape(-1, 3).std(axis=0).tolist(),
        "texture": min(1.0, float(cv2.Laplacian(gray, cv2.CV_32F).std()) / 128.0),
        "hist": hist.tolist(),
    }

def background_signature_distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_mean = np.array(left.get("lab_mean") or [0, 0, 0], dtype=np.float32)
    right_mean = np.array(right.get("lab_mean") or [0, 0, 0], dtype=np.float32)
    left_std = np.array(left.get("lab_std") or [0, 0, 0], dtype=np.float32)
    right_std = np.array(right.get("lab_std") or [0, 0, 0], dtype=np.float32)
    left_hist = np.array(left.get("hist") or [], dtype=np.float32)
    right_hist = np.array(right.get("hist") or [], dtype=np.float32)
    mean_dist = float(np.linalg.norm(left_mean - right_mean) / max(np.sqrt(3.0), 1e-6))
    std_dist = float(np.linalg.norm(left_std - right_std) / max(np.sqrt(3.0), 1e-6))
    texture_dist = abs(float(left.get("texture") or 0.0) - float(right.get("texture") or 0.0))
    hist_dist = 1.0
    if left_hist.size and right_hist.size and left_hist.size == right_hist.size:
        hist_dist = float(0.5 * np.abs(left_hist - right_hist).sum())
    return float(0.55 * mean_dist + 0.15 * std_dist + 0.10 * texture_dist + 0.20 * hist_dist)

class BackgroundPlateDerivation:
    def __init__(self, sources: PlateSources, policy: PlatePolicy, masks: BackgroundMasks) -> None:
        self._sources = sources
        self._policy = policy
        self._masks = masks

    def derive_background_plate_from_accessory(self, item: dict[str, Any], out_path: Path) -> Path | None:
        "Build an empty background plate from the first accessory's own capture\n    environment by segmenting out every foreground object and inpainting the\n    holes, leaving only the bare work surface. This guarantees a\n    first-accessory-derived task background even when the image model declines to\n    synthesize an empty surface. Returns the written plate path or None."
        candidates: list[Path] = []
        for asset in self._sources.pose_assets()(item):
            path = self._sources.resolve()(asset.get("path"))
            if path.exists() and path.suffix.lower() in self._sources.suffixes():
                candidates.append(path)
        for ref in self._sources.contexts()(item, max_images=4):
            path = self._sources.resolve()(ref.get("source_path"))
            if path.exists() and path.suffix.lower() in self._sources.suffixes():
                candidates.append(path)
        def longest_clean_run(occupied: np.ndarray) -> tuple[int, int]:
            best_start = best_len = run_start = run_len = 0
            for i, taken in enumerate(occupied):
                if taken:
                    run_len = 0
                    run_start = i + 1
                else:
                    run_len += 1
                    if run_len > best_len:
                        best_len, best_start = run_len, run_start
            return best_start, best_len

        deadline = time.monotonic() + self._policy.time_budget()
        for path in candidates:
            if time.monotonic() > deadline:
                print("[pipeline.bg_plate] time budget exceeded; aborting plate derivation", flush=True)
                break
            full = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if full is None:
                continue
            orig_h, orig_w = full.shape[:2]
            # Downscale large captures to a bounded working resolution BEFORE any mask
            # or inpaint work so cost is bounded regardless of the source megapixels.
            long_side = max(orig_h, orig_w)
            if long_side > self._policy.max_side():
                scale = self._policy.max_side() / float(long_side)
                image = cv2.resize(
                    full,
                    (max(1, int(round(orig_w * scale))), max(1, int(round(orig_h * scale)))),
                    interpolation=cv2.INTER_AREA,
                )
            else:
                image = full
            height, width = image.shape[:2]
            image_area = height * width
            t0 = time.monotonic()
            mask = self._masks.foreground()(image)
            num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
            object_mask = np.zeros((height, width), dtype=np.uint8)
            covered = 0
            for idx in range(1, num):
                area = int(stats[idx, cv2.CC_STAT_AREA])
                if area < max(500, int(image_area * 0.001)) or area > int(image_area * 0.75):
                    continue
                object_mask[labels == idx] = 255
                covered += area
            # Need some bare surface left, and an actual object to remove.
            if covered <= 0 or covered > int(image_area * 0.8):
                continue
            margin = cv2.dilate(object_mask, np.ones((11, 11), np.uint8), iterations=1)
            col_taken = margin.max(axis=0) > 0
            row_taken = margin.max(axis=1) > 0
            # Preferred: crop the largest fully object-free strip of the SAME belt and
            # scale it to the full frame. This keeps the first accessory's real
            # surface/lighting with no inpaint artifacts.
            plate: np.ndarray | None = None
            plate_method = ""
            col_start, col_len = longest_clean_run(col_taken)
            row_start, row_len = longest_clean_run(row_taken)
            if col_len >= int(width * 0.18) and col_len * height >= row_len * width:
                strip = image[:, col_start : col_start + col_len]
                plate = cv2.resize(strip, (width, height), interpolation=cv2.INTER_LINEAR)
                plate_method = "strip_col"
            elif row_len >= int(height * 0.18):
                strip = image[row_start : row_start + row_len, :]
                plate = cv2.resize(strip, (width, height), interpolation=cv2.INTER_LINEAR)
                plate_method = "strip_row"
            # Fallback: remove the object and blend the hole toward the belt's own
            # median colour + matched noise. Inpaint only when the hole is small enough
            # and we are within budget; otherwise skip the costly TELEA call and rely
            # on the cheap median+noise fill below.
            if plate is None:
                inpaint_mask = cv2.dilate(object_mask, np.ones((17, 17), np.uint8), iterations=1)
                mask_frac = float(int((inpaint_mask > 0).sum())) / float(max(1, image_area))
                radius = min(self._policy.max_radius(), max(6, int(0.02 * max(height, width))))
                background_pixels = image[inpaint_mask == 0].reshape(-1, 3)
                if mask_frac <= self._policy.mask_fraction() and time.monotonic() <= deadline:
                    plate = cv2.inpaint(image, inpaint_mask, radius, cv2.INPAINT_TELEA)
                    plate_method = f"inpaint_r{radius}"
                else:
                    plate = image.copy()
                    plate_method = "median_fill"
                if background_pixels.size:
                    median = np.median(background_pixels, axis=0)
                    spread = np.maximum(background_pixels.std(axis=0) * 0.5, 3.0)
                    noise = np.random.default_rng(7).normal(0.0, spread, plate.shape)
                    fill = np.clip(median + noise, 0, 255).astype(np.uint8)
                    weight = cv2.GaussianBlur((inpaint_mask > 0).astype(np.float32), (0, 0), max(1, radius))[..., None] * 0.9
                    plate = (plate.astype(np.float32) * (1.0 - weight) + fill.astype(np.float32) * weight).astype(np.uint8)
            # Upscale the bounded plate back to the source resolution so downstream
            # consumers still receive a full-size background.
            if plate is not None and (plate.shape[0] != orig_h or plate.shape[1] != orig_w):
                plate = cv2.resize(plate, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if plate is not None and cv2.imwrite(str(out_path), plate):
                print(
                    f"[pipeline.bg_plate] plate ok src={orig_w}x{orig_h} work={width}x{height} "
                    f"method={plate_method} covered_px={covered} elapsed_ms={int((time.monotonic() - t0) * 1000)}",
                    flush=True,
                )
                return out_path
        return None

class BackgroundReferenceSignatures:
    def __init__(self, sources: SignatureSources, policy: SignaturePolicy, masks: BackgroundMasks, projections: SignatureProjections) -> None:
        self._sources = sources
        self._policy = policy
        self._masks = masks
        self._projections = projections

    def background_reference_signatures_from_accessory(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        signatures: list[dict[str, Any]] = []
        for source_path in self._sources.paths()(item, limit=self._sources.limit()):
            image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
            if image is None:
                continue
            height, width = image.shape[:2]
            mask = self._masks.foreground()(image)
            occupied = np.zeros((height, width), dtype=np.uint8)
            if mask.size:
                num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
                image_area = height * width
                for idx in range(1, num):
                    area = int(stats[idx, cv2.CC_STAT_AREA])
                    if area < max(500, int(image_area * 0.001)) or area > int(image_area * 0.75):
                        continue
                    occupied[labels == idx] = 255
                if occupied.any():
                    occupied = cv2.dilate(occupied, np.ones((19, 19), np.uint8), iterations=1)
            fallback_allowed = bool(occupied.mean() > 230 or occupied.mean() < 1)
            for box in self._projections.boxes()(width, height):
                if len(signatures) >= self._policy.max_patches():
                    break
                x1, y1, x2, y2 = box
                patch = image[y1:y2, x1:x2]
                if patch.size == 0:
                    continue
                if not fallback_allowed:
                    free_fraction = float((occupied[y1:y2, x1:x2] == 0).mean())
                    if free_fraction < 0.72:
                        continue
                signature = self._projections.signature()(patch)
                if not signature:
                    continue
                signature.update({"source_path": str(source_path), "box_xyxy": [int(x1), int(y1), int(x2), int(y2)]})
                signatures.append(signature)
        return signatures
