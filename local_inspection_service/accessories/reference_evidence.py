"""Accessory reference paths, metadata and chroma evidence."""
from typing import Any
from pathlib import Path
import hashlib
import cv2
import numpy as np
from .reference_evidence_ports import ReferencePolicy, ReferencePaths, ReferenceContexts, ReferenceChroma

def saturated_chroma_mask(image_bgr: np.ndarray, screen: dict[str, Any]) -> np.ndarray:
    if image_bgr is None or image_bgr.ndim != 3:
        return np.zeros((0, 0), dtype=bool)
    name = str(screen.get("name") or "green")
    blue, green, red = cv2.split(image_bgr.astype(np.int16))
    if name == "blue":
        return (blue >= 160) & (red <= 110) & (green <= 140) & ((blue - np.maximum(red, green)) >= 50)
    if name == "red":
        return (red >= 160) & (blue <= 120) & (green <= 120) & ((red - np.maximum(blue, green)) >= 50)
    return (green >= 160) & (red <= 110) & (blue <= 110) & ((green - np.maximum(red, blue)) >= 50)

class ReferenceEvidence:
    def __init__(self, policy: ReferencePolicy, paths: ReferencePaths, contexts: ReferenceContexts, chroma: ReferenceChroma) -> None:
        self._policy = policy
        self._paths = paths
        self._contexts = contexts
        self._chroma = chroma

    def accessory_image_paths(self, item: dict[str, Any]) -> list[Path]:
        paths: list[Path] = []
        for job in self._paths.jobs()(item):
            if job.get("intermediate"):
                continue
            output_path = self._paths.resolve()(job.get("output_path"))
            if output_path.exists():
                job["output_path"] = str(output_path)
                paths.append(output_path)
        for asset in item.get("normalized_assets", []):
            path = self._paths.resolve()(asset.get("path"))
            if path.exists():
                asset["path"] = str(path)
                paths.append(path)
        for path_str in item.get("source_files", []):
            path = self._paths.resolve()(path_str)
            if path.exists() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                paths.append(path)
        default_path = self._paths.default()(item)
        if default_path and default_path.exists():
            paths.append(default_path)
        unique = []
        seen = set()
        for path in paths:
            key = str(path)
            if key not in seen:
                unique.append(path)
                seen.add(key)
        return unique

    def ai_profile_reference_paths(self, item: dict[str, Any]) -> list[Path]:
        paths: list[Path] = []
        for path_str in item.get("ai_profile_reference_files", []) or []:
            path = self._paths.resolve()(path_str)
            if path.exists() and path.suffix.lower() in self._policy.suffixes():
                paths.append(path)
        unique = []
        seen = set()
        for path in paths:
            key = str(path)
            if key not in seen:
                unique.append(path)
                seen.add(key)
        return unique

    def image_reference_context(self, path: Path, accessory_id: str, ordinal: int) -> dict[str, Any] | None:
        try:
            if not path.exists() or path.suffix.lower() not in self._policy.suffixes():
                return None
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            height = int(image.shape[0]) if image is not None else 0
            width = int(image.shape[1]) if image is not None else 0
        except OSError:
            return None
        mime_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return {
            "accessory_id": self._contexts.bounded()(accessory_id, 120),
            "source_path": str(path),
            "sha256": digest,
            "mime_type": mime_type,
            "width": width,
            "height": height,
            "ordinal": ordinal,
        }

    def accessory_reference_image_contexts(self, item: dict[str, Any], *, max_images: int) -> list[dict[str, Any]]:
        contexts: list[dict[str, Any]] = []
        seen: set[str] = set()
        accessory_id = self._contexts.uid()(item)
        preferred_paths = self._paths.preferred()(item)
        default_source_path = self._paths.first_source()(item) if not preferred_paths else None
        source_paths = preferred_paths if preferred_paths else ([default_source_path] if default_source_path else self._paths.inventory()(item))
        for path in source_paths:
            path_key = str(path)
            if path_key in seen:
                continue
            seen.add(path_key)
            context = self._contexts.context()(path, accessory_id, len(contexts) + 1)
            if context:
                contexts.append(context)
            if len(contexts) >= max_images:
                break
        return contexts

    def normalize_chroma_screen(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            name = str(value.get("name") or "").strip().lower()
        else:
            name = str(value or "").strip().lower()
        return dict(self._policy.screens().get(name) or self._policy.screens()["green"])

    def accessory_reference_chroma_fraction(self, item: dict[str, Any], screen_name: str, *, max_images: int = 3) -> float:
        screen = self._chroma.normalize()(screen_name)
        best = 0.0
        for ref in self._contexts.references()(item, max_images=max_images):
            path = self._paths.resolve()(ref.get("source_path"))
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None or image.size == 0:
                continue
            mask = self._chroma.mask()(image, screen)
            if mask.size:
                best = max(best, float(mask.mean()))
        return best
