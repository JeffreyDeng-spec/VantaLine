"""Preview and rectified-document asset loading."""
from typing import Any
from pathlib import Path
import cv2
import numpy as np
from .preview_asset_ports import PreviewAssetPolicy, PreviewAssetPaths, PreviewAssetOperations

def select_document_image_candidate(
    candidates: list[tuple[np.ndarray, dict[str, Any]]],
    rng: np.random.Generator | None,
    *,
    multi_policy: str,
    single_policy: str,
) -> tuple[np.ndarray, dict[str, Any]] | None:
    if not candidates:
        return None
    count = len(candidates)
    selected_index = int(rng.integers(0, count)) if rng is not None and count > 1 else 0
    image, metadata = candidates[selected_index]
    policy = multi_policy if count > 1 else single_policy
    return image, {
        **metadata,
        "document_asset_index": selected_index,
        "document_asset_count": count,
        "document_asset_selection_policy": policy,
    }

class PreviewAssetLoader:
    def __init__(self, policy: PreviewAssetPolicy, paths: PreviewAssetPaths, operations: PreviewAssetOperations) -> None:
        self._policy = policy
        self._paths = paths
        self._operations = operations

    def default_asset_for_accessory(self, item: dict[str, Any]) -> Path | None:
        name = str(item.get("name", "")).lower()
        if "warranty" in name:
            return self._policy.root() / "standardized_manuals" / "manual_from_2_warranty_service_precise_1240x1754.png"
        if "battery" in name:
            return self._policy.root() / "standardized_manuals" / "manual_from_3_battery_instruction_precise_1240x1754.png"
        if "download" in name:
            return self._policy.root() / "standardized_manuals" / "manual_from_4_download_service_precise_1240x1754.png"
        if "qr" in name or "service" in name:
            return self._policy.root() / "standardized_manuals" / "manual_from_6_service_qr_precise_1240x1754.png"
        if "bottle" in name:
            return self._policy.root() / "generated_bottle_pose_collection" / "overhead_bottle_pose_collection_image2.png"
        return None

    def load_preview_asset_with_metadata(self, item: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]] | None:
        for asset in item.get("normalized_assets", []):
            path = self._paths.resolve()(asset.get("path"))
            if path.exists() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                asset["path"] = str(path)
                image = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if image is not None:
                    return image, {
                        "asset_path": str(path),
                        "asset_kind": asset.get("kind"),
                        "asset_method": asset.get("method"),
                        "asset_source": "normalized_assets",
                        "source_image_size_px": [int(image.shape[1]), int(image.shape[0])],
                        "canonical_asset_dimensions_px": [int(asset.get("width") or image.shape[1]), int(asset.get("height") or image.shape[0])],
                    }
        for path_str in item.get("source_files", []):
            path = self._paths.resolve()(path_str)
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"} and path.exists():
                image = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if image is not None:
                    return image, {
                        "asset_path": str(path),
                        "asset_kind": "source_image",
                        "asset_method": "source_file_direct",
                        "asset_source": "source_files",
                        "source_image_size_px": [int(image.shape[1]), int(image.shape[0])],
                        "canonical_asset_dimensions_px": [int(image.shape[1]), int(image.shape[0])],
                    }
        default_path = self._operations.default()(item)
        if default_path and default_path.exists():
            image = cv2.imread(str(default_path), cv2.IMREAD_COLOR)
            if image is not None:
                return image, {
                    "asset_path": str(default_path),
                    "asset_kind": "default_image",
                    "asset_method": "default_asset_direct",
                    "asset_source": "default_asset",
                    "source_image_size_px": [int(image.shape[1]), int(image.shape[0])],
                    "canonical_asset_dimensions_px": [int(image.shape[1]), int(image.shape[0])],
                }
        return None

    def load_document_image_candidate(self, path_value: Any, metadata: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]] | None:
        path = self._paths.resolve()(path_value)
        if not path or not path.exists() or path.suffix.lower() not in self._policy.suffixes():
            return None
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            return None
        asset_width = int(metadata.get("width") or image.shape[1])
        asset_height = int(metadata.get("height") or image.shape[0])
        return image, {
            **metadata,
            "asset_path": str(path),
            "source_image_size_px": [int(image.shape[1]), int(image.shape[0])],
            "canonical_asset_dimensions_px": [asset_width, asset_height],
        }

    def load_rectified_document_asset_with_metadata(self,
        item: dict[str, Any],
        rng: np.random.Generator | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]] | None:
        normalized_candidates: list[tuple[np.ndarray, dict[str, Any]]] = []
        for normalized_index, asset in enumerate(item.get("normalized_assets", [])):
            if asset.get("kind") != "canonical_text_image":
                continue
            loaded = self._operations.candidate()(
                asset.get("path"),
                {
                    "asset_kind": asset.get("kind"),
                    "asset_method": asset.get("method"),
                    "asset_source": "normalized_assets",
                    "document_asset_source_index": normalized_index,
                    "width": asset.get("width"),
                    "height": asset.get("height"),
                },
            )
            if loaded is not None:
                normalized_candidates.append(loaded)
        selected = self._operations.select()(
            normalized_candidates,
            rng,
            multi_policy="seeded_uniform_canonical_text_image",
            single_policy="single_canonical_text_image",
        )
        if selected is not None:
            return selected

        normalized_fallback_candidates: list[tuple[np.ndarray, dict[str, Any]]] = []
        for normalized_index, asset in enumerate(item.get("normalized_assets", [])):
            loaded = self._operations.candidate()(
                asset.get("path"),
                {
                    "asset_kind": asset.get("kind"),
                    "asset_method": asset.get("method"),
                    "asset_source": "normalized_assets",
                    "document_asset_source_index": normalized_index,
                    "width": asset.get("width"),
                    "height": asset.get("height"),
                },
            )
            if loaded is not None:
                normalized_fallback_candidates.append(loaded)
        selected = self._operations.select()(
            normalized_fallback_candidates,
            rng,
            multi_policy="seeded_uniform_normalized_document_image_fallback",
            single_policy="single_normalized_document_image_fallback",
        )
        if selected is not None:
            return selected

        rectified_source_candidates: list[tuple[np.ndarray, dict[str, Any]]] = []
        for path_str in item.get("source_files", []):
            path = self._paths.resolve()(path_str)
            if not path.stem.endswith("_rectified"):
                continue
            loaded = self._operations.candidate()(
                path,
                {
                    "asset_kind": "rectified_source_image",
                    "asset_method": "manual_rectified_source_direct",
                    "asset_source": "source_files_rectified",
                },
            )
            if loaded is not None:
                rectified_source_candidates.append(loaded)
        selected = self._operations.select()(
            rectified_source_candidates,
            rng,
            multi_policy="seeded_uniform_rectified_source_image",
            single_policy="single_rectified_source_image",
        )
        if selected is not None:
            return selected

        default_path = self._operations.default()(item)
        if default_path and default_path.exists() and default_path.parent.name == "standardized_manuals":
            image = cv2.imread(str(default_path), cv2.IMREAD_COLOR)
            if image is not None:
                return image, {
                    "asset_path": str(default_path),
                    "asset_kind": "standardized_document_default",
                    "asset_method": "standardized_rectified_default_direct",
                    "asset_source": "standardized_default_asset",
                    "source_image_size_px": [int(image.shape[1]), int(image.shape[0])],
                    "canonical_asset_dimensions_px": [int(image.shape[1]), int(image.shape[0])],
                    "document_asset_index": 0,
                    "document_asset_count": 1,
                    "document_asset_selection_policy": "standardized_document_default",
                }
        return None

    def load_preview_asset(self, item: dict[str, Any]) -> np.ndarray | None:
        loaded = self._operations.preview()(item)
        return loaded[0] if loaded else None
