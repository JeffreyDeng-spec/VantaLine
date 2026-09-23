"""Ordered background candidate reads and image-signature matching."""
from typing import Any, Callable
from pathlib import Path
import cv2
from .background_library_selection_ports import BackgroundOwnership, BackgroundCatalogSources, BackgroundCatalogPolicy, BackgroundMatchSources, BackgroundMatchFeatures

class BackgroundCandidateCatalog:
    def __init__(self, ownership: BackgroundOwnership, sources: BackgroundCatalogSources, policy: BackgroundCatalogPolicy) -> None:
        self._ownership = ownership
        self._sources = sources
        self._policy = policy

    def background_set_visible_for_owner(self, meta: dict[str, Any], owner_id: str) -> bool:
        meta_owner = str(meta.get("owner_user_id") or "")
        shared = meta.get("shared_with_user_ids") if isinstance(meta.get("shared_with_user_ids"), list) else []
        return not meta_owner or meta_owner in {owner_id, self._ownership.system(), self._ownership.legacy()} or "*" in shared or owner_id in shared

    def background_library_image_candidates(self, owner_id: str) -> list[tuple[str, Path, dict[str, Any]]]:
        manifest = self._sources.manifest()()
        meta_sets = manifest.get("sets") if isinstance(manifest.get("sets"), dict) else {}
        candidates: list[tuple[str, Path, dict[str, Any]]] = []
        ids = {path.name for path in self._sources.directories()()} | {self._sources.sanitize()(item) for item in meta_sets.keys()}
        for set_id in sorted(ids):
            clean_id = self._sources.sanitize()(set_id)
            if clean_id.startswith("task_plate_"):
                continue
            meta = meta_sets.get(clean_id) or meta_sets.get(set_id) or {}
            if not self._sources.visible()(meta, owner_id):
                continue
            images = self._sources.images()(self._policy.directory() / clean_id)
            source = self._sources.resolve()(meta.get("source"))
            if source.exists() and source.suffix.lower() in self._policy.suffixes():
                images = [source] + [path for path in images if path.resolve() != source.resolve()]
            for image_path in images[:8]:
                candidates.append((clean_id, image_path, meta))
                if len(candidates) >= self._policy.limit():
                    return candidates
        return candidates

class BackgroundLibraryMatcher:
    def __init__(self, sources: BackgroundMatchSources, features: BackgroundMatchFeatures, threshold: Callable[[], float]) -> None:
        self._sources = sources
        self._features = features
        self._threshold = threshold

    def match_background_library_plate(self, item: dict[str, Any], owner_id: str) -> dict[str, Any] | None:
        source_signatures = self._sources.references()(item)
        if not source_signatures:
            return None
        best: dict[str, Any] | None = None
        for set_id, image_path, meta in self._sources.candidates()(owner_id):
            image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if image is None:
                continue
            height, width = image.shape[:2]
            library_signatures: list[dict[str, Any]] = []
            for box in self._features.boxes()(width, height):
                x1, y1, x2, y2 = box
                signature = self._features.signature()(image[y1:y2, x1:x2])
                if signature:
                    library_signatures.append(signature)
            whole = self._features.signature()(image)
            if whole:
                library_signatures.append(whole)
            for source_sig in source_signatures:
                for lib_sig in library_signatures:
                    distance = self._features.distance()(source_sig, lib_sig)
                    if best is None or distance < float(best.get("distance") or 999.0):
                        best = {
                            "background_set_id": set_id,
                            "image_path": str(image_path),
                            "distance": round(float(distance), 6),
                            "threshold": self._threshold(),
                            "source_path": source_sig.get("source_path"),
                            "source_box_xyxy": source_sig.get("box_xyxy"),
                            "generation_method": meta.get("generation_method") or "",
                        }
        if best and float(best.get("distance") or 999.0) <= self._threshold():
            return best
        return None
