"""Explicit asset policies and configuration persistence for training preparation."""
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from fastapi import HTTPException
Record = dict[str, Any]

class AssetFiles(Protocol):
    def exists(self, path: Path) -> bool: ...

@dataclass(frozen=True)
class TrainingAssetPolicy:
    accessory_uid: Callable[[], Callable[[Record], str]]
    accessory_material_type: Callable[[], Callable[[Record], str]]
    clean_sprite_assets: Callable[[], Callable[[Record], list[Any]]]
    candidate_image_jobs: Callable[[], Callable[[Record], list[Record]]]
    _business_files: Callable[[], AssetFiles]
    POSE_COLLECTION_GRID_POSITIONS: Callable[[], Sequence[Any]]
    clean_sprites_policy_complete: Callable[[], Callable[[Record, list[Any]], bool]]
    preprocess_object_clean_sprites: Callable[[], Callable[..., bool]]
    canonical_text_assets: Callable[[], Callable[[Record], list[Any]]]
    canonical_text_assets_complete: Callable[[], Callable[..., bool]]
    normalize_accessory_assets: Callable[[], Callable[[Record], Record]]
    object_photo_highlight_source_paths: Callable[[], Callable[[Record], list[Path]]]
    photo_highlight_clean_sprites_ready: Callable[[], Callable[[Record, list[Path]], bool]]
    PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES: Callable[[], int]
    HTTPException: Callable[[], type[HTTPException]]

@dataclass(frozen=True)
class TrainingAssetPersistence:
    ensure_training_normalized_assets_for_selection: Callable[[], Callable[[Record, list[str]], bool]]
    merge_scoped_accessory_updates: Callable[[], Callable[[Record, Record, Record], Any]]
    save_config: Callable[[], Callable[[Record], None]]
