"""Existing document crop, perspective and paper-size preparation algorithms."""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import cv2
import numpy as np
from fastapi import UploadFile
from .text_preparation_ports import TextGeometry, TextSources, TextMedia

@dataclass(frozen=True)
class AccessoryTextPreparation:
    geometry: TextGeometry
    sources: TextSources
    media: TextMedia

    def order_points(self, points: np.ndarray) -> np.ndarray:
        pts = points.reshape(4, 2).astype("float32")
        s = pts.sum(axis=1)
        diff = np.diff(pts, axis=1)
        ordered = np.zeros((4, 2), dtype="float32")
        ordered[0] = pts[np.argmin(s)]
        ordered[2] = pts[np.argmax(s)]
        ordered[1] = pts[np.argmin(diff)]
        ordered[3] = pts[np.argmax(diff)]
        return ordered


    def target_paper_pixel_size(self, physical_size: dict[str, Any] | None) -> tuple[int, int]:
        size = physical_size or {}
        width_mm = self.media.optional_float()(size.get("width_mm")) or self.media.STANDARD_PAPER_SIZES_MM()["A4"][0]
        height_mm = self.media.optional_float()(size.get("height_mm")) or self.media.STANDARD_PAPER_SIZES_MM()["A4"][1]
        if width_mm > height_mm:
            long_px = 1200
            return long_px, max(1, int(round(long_px * height_mm / width_mm)))
        long_px = 1200
        return max(1, int(round(long_px * width_mm / height_mm))), long_px


    def ratio_close(self, value: float, target: float, tolerance: float = 0.08) -> bool:
        if value <= 0 or target <= 0:
            return False
        return abs(value - target) / target <= tolerance


    def quad_is_axis_aligned(self, rect: np.ndarray, image_shape: tuple[int, ...]) -> bool:
        h, w = image_shape[:2]
        horizontal_tilt = max(abs(float(rect[0][1] - rect[1][1])), abs(float(rect[2][1] - rect[3][1]))) / max(1, h)
        vertical_tilt = max(abs(float(rect[1][0] - rect[2][0])), abs(float(rect[0][0] - rect[3][0]))) / max(1, w)
        return horizontal_tilt < 0.02 and vertical_tilt < 0.02


    def best_document_quad(self, image: np.ndarray, target_aspect: float | None = None) -> np.ndarray | None:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 160)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        image_area = image.shape[0] * image.shape[1]
        image_aspect = image.shape[1] / max(1, image.shape[0])
        image_already_paper_ratio = bool(target_aspect and self.geometry.ratio_close()(image_aspect, target_aspect))
        best: tuple[float, np.ndarray] | None = None
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:16]:
            area = float(cv2.contourArea(contour))
            if area < image_area * 0.05:
                continue
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
            used_rect_fallback = len(approx) != 4
            if used_rect_fallback:
                if area < image_area * 0.20:
                    continue
                rect = cv2.boxPoints(cv2.minAreaRect(contour)).reshape(4, 1, 2)
                approx = rect.astype(np.float32)
            rect = self.geometry.order_points()(approx)
            quad_area = float(cv2.contourArea(rect.astype(np.float32)))
            if quad_area <= 0:
                continue
            quad_area_ratio = quad_area / max(1, image_area)
            if image_already_paper_ratio and quad_area_ratio < 0.82 and self.geometry.quad_is_axis_aligned()(rect, image.shape):
                continue
            fill = area / quad_area
            min_fill = 0.82 if used_rect_fallback else 0.65
            if fill < min_fill:
                continue
            if used_rect_fallback:
                x, y, w, h = cv2.boundingRect(rect.astype(np.float32))
                touches_frame = x <= 2 or y <= 2 or x + w >= image.shape[1] - 2 or y + h >= image.shape[0] - 2
                if touches_frame:
                    continue
            score = quad_area * min(fill, 1.0)
            if best is None or score > best[0]:
                best = (score, rect)
        return best[1] if best else None


    def document_quad_mean_size(self, quad: np.ndarray) -> tuple[float, float]:
        "Mean width / height (px) of an ordered tl,tr,br,bl quad — used to recover\n    the document's true (deskewed) proportions."
        pts = quad.reshape(4, 2).astype("float32")
        tl, tr, br, bl = pts[0], pts[1], pts[2], pts[3]
        top = float(np.linalg.norm(tr - tl))
        bottom = float(np.linalg.norm(br - bl))
        left = float(np.linalg.norm(bl - tl))
        right = float(np.linalg.norm(br - tr))
        return (top + bottom) / 2.0, (left + right) / 2.0


    def detect_document_quad(self, image: np.ndarray, target_aspect: float | None = None) -> np.ndarray | None:
        'Robustly auto-crop the document/manual body. Tries edge contours first, then\n    bright-paper (Otsu) and low-saturation paper segmentation, so a manual shot on\n    a darker tabletop is still found even when its edges are weak. Returns an\n    ordered tl,tr,br,bl quad or None.'
        h, w = image.shape[:2]
        area = max(1, h * w)
        candidates: list[np.ndarray] = []
        edge_quad = self.geometry.best_document_quad()(image, target_aspect)
        if edge_quad is not None:
            candidates.append(edge_quad)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (7, 7), 0)
        _, otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if float((otsu > 0).mean()) < 0.5:
            otsu = cv2.bitwise_not(otsu)  # keep the bright paper as foreground
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        sat, val = hsv[:, :, 1], hsv[:, :, 2]
        paper = ((sat < 70) & (val > 110)).astype(np.uint8) * 255
        for mask in (otsu, paper):
            closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8), iterations=2)
            opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8), iterations=1)
            cnts, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not cnts:
                continue
            contour = max(cnts, key=cv2.contourArea)
            if float(cv2.contourArea(contour)) < area * 0.12:
                continue
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
            if len(approx) == 4:
                candidates.append(self.geometry.order_points()(approx.astype(np.float32)))
            else:
                box = cv2.boxPoints(cv2.minAreaRect(contour)).reshape(4, 1, 2).astype(np.float32)
                candidates.append(self.geometry.order_points()(box))
        best: tuple[float, np.ndarray] | None = None
        for quad in candidates:
            quad_area = float(cv2.contourArea(quad.astype(np.float32)))
            if quad_area < area * 0.10 or quad_area > area * 0.999:
                continue
            if best is None or quad_area > best[0]:
                best = (quad_area, quad)
        return best[1] if best else None


    def letterbox_document_onto_paper(self,
        image: np.ndarray,
        target_w: int,
        target_h: int,
        pad_value: tuple[int, int, int] = (255, 255, 255),
    ) -> np.ndarray:
        'Place a document image onto a clean paper-sized canvas preserving aspect\n    (white letterbox). Never stretches the content non-uniformly.'
        target_w = max(1, int(target_w))
        target_h = max(1, int(target_h))
        h, w = image.shape[:2]
        scale = min(target_w / max(1, w), target_h / max(1, h))
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        resized = cv2.resize(
            image,
            (new_w, new_h),
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
        )
        canvas = np.full((target_h, target_w, 3), pad_value, dtype=np.uint8)
        x0 = (target_w - new_w) // 2
        y0 = (target_h - new_h) // 2
        canvas[y0 : y0 + new_h, x0 : x0 + new_w] = resized
        return canvas


    def resize_document_to_paper(self, image: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
        'Resize a document image directly to the chosen paper pixel size.'
        target_w = max(1, int(target_w))
        target_h = max(1, int(target_h))
        h, w = image.shape[:2]
        scale = max(target_w / max(1, w), target_h / max(1, h))
        return cv2.resize(
            image,
            (target_w, target_h),
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
        )


    def is_text_rectified_path(self, path: Path | str) -> bool:
        stem = Path(str(path)).stem.lower()
        return stem.endswith("_rectified") or "_rectified_" in stem or "_manual_rectified" in stem


    def stable_text_crop_stem(self, path: Path | str) -> str:
        stem = Path(str(path)).stem.replace(" ", "_")[:80] or "document"
        stem = re.sub(r"[^a-zA-Z0-9_.-]+", "_", stem).strip("._-")
        return stem or "document"


    def text_raw_crop_prefix(self, path: Path | str) -> str:
        return f"{self.sources.stable_text_crop_stem()(path).lower()}_manual_rectified"


    def text_raw_has_rectified(self, raw_path: Path | str, rectified_sources: list[Path]) -> bool:
        raw_stem = self.sources.stable_text_crop_stem()(raw_path).lower()
        prefix = self.sources.text_raw_crop_prefix()(raw_path)
        for rectified in rectified_sources:
            stem = rectified.stem.lower()
            if stem == prefix or stem.startswith(f"{prefix}_"):
                return True
            if stem.endswith(f"_{raw_stem}.bin_manual_rectified") or stem.startswith(f"{raw_stem}.bin_manual_rectified_"):
                return True
        return False


    def text_image_paths_for_upload_limit(self, item: dict[str, Any]) -> list[Path]:
        original = item.get("original_source_files") if isinstance(item.get("original_source_files"), list) else []
        source = item.get("source_files") if isinstance(item.get("source_files"), list) else []
        paths = [Path(str(path)) for path in (original or source)]
        images = [path for path in paths if path.suffix.lower() in self.sources.IMAGE_REFERENCE_SUFFIXES()]
        if original:
            return images
        raw_images = [path for path in images if not self.sources.is_text_rectified_path()(path)]
        return raw_images or images


    def text_accessory_source_count(self, item: dict[str, Any]) -> int:
        return len(self.sources.text_image_paths_for_upload_limit()(item))


    def validate_text_accessory_uploads(self, files: list[UploadFile], *, existing_count: int = 0) -> None:
        image_count = 0
        for upload in files:
            suffix = Path(upload.filename or "").suffix.lower()
            if suffix not in self.sources.IMAGE_REFERENCE_SUFFIXES():
                raise self.sources.HTTPException()(status_code=400, detail="文字类配件只能上传图片，不能上传视频或其它文件")
            image_count += 1
        if existing_count + image_count > self.sources.MAX_TEXT_ACCESSORY_IMAGES():
            raise self.sources.HTTPException()(status_code=400, detail=f"文字类配件最多上传 {self.sources.MAX_TEXT_ACCESSORY_IMAGES()} 张图片")


    def normalize_text_image(self, src: Path, target_dir: Path, physical_size: dict[str, Any] | None = None) -> dict[str, Any] | None:
        'Lightweight document pipeline (no image generation): auto-crop the document\n    body, deskew/perspective-correct any tilt, then normalize onto the chosen paper\n    page (A4/A5/...). The output is always exactly the paper pixel size.'
        image = self.media._image_files().imread(str(src))
        if image is None:
            return None
        is_manual_rectified = self.sources.is_text_rectified_path()(src)
        target_w, target_h = self.geometry.target_paper_pixel_size()(physical_size)
        target_aspect = target_w / max(1, target_h)
        quad = None if is_manual_rectified else self.geometry.detect_document_quad()(image, target_aspect)
        if quad is not None:
            mean_w, mean_h = self.geometry.document_quad_mean_size()(quad)
            quad_aspect = mean_w / max(1.0, mean_h)
            if self.geometry.ratio_close()(quad_aspect, target_aspect, tolerance=0.18):
                # Cropped document already matches the chosen paper proportions: deskew
                # straight onto the page (fills the page, correct proportions).
                dst = np.array([[0, 0], [target_w - 1, 0], [target_w - 1, target_h - 1], [0, target_h - 1]], dtype="float32")
                warped = cv2.warpPerspective(image, cv2.getPerspectiveTransform(quad.astype("float32"), dst), (target_w, target_h))
                method = "paper_quad_perspective"
            else:
                # Deskew to the document's own true aspect, then resize to the page so
                # custom paper targets do not introduce white letterbox borders.
                rect_w = max(1, int(round(mean_w)))
                rect_h = max(1, int(round(mean_h)))
                dst = np.array([[0, 0], [rect_w - 1, 0], [rect_w - 1, rect_h - 1], [0, rect_h - 1]], dtype="float32")
                deskewed = cv2.warpPerspective(image, cv2.getPerspectiveTransform(quad.astype("float32"), dst), (rect_w, rect_h))
                warped = self.geometry.resize_document_to_paper()(deskewed, target_w, target_h)
                method = "paper_quad_deskew_resize"
        else:
            if not is_manual_rectified:
                return None
            # Already-rectified manual crop: stretch the whole crop to the requested
            # paper size instead of adding letterbox borders.
            warped = self.geometry.resize_document_to_paper()(image, target_w, target_h)
            method = "manual_rectified_resize"
        out = target_dir / f"{src.stem}_canonical.png"
        self.media._image_files().imwrite(str(out), warped)
        return {
            "kind": "canonical_text_image",
            "path": str(out),
            "method": method,
            "paper_size": physical_size or {},
            "width": int(warped.shape[1]),
            "height": int(warped.shape[0]),
            "workflow": ["auto_crop", "deskew_perspective_correction", "paper_size_normalize"],
        }
