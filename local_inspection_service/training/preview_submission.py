"""Preview submission business flow; identity, configuration and file persistence are explicit."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID
from fastapi import HTTPException
from ..schemas.training import TrainingPreviewRequest

Record = dict[str, Any]


class PreviewArtifacts(Protocol):
    def create_directory(self, preview_id: str) -> Path: ...
    def write_plan(self, preview_id: str, plan: Record) -> None: ...


class DrawPreview(Protocol):
    def __call__(self, selected: list[Record], output_path: Path, *, seed: int,
                 pose_family_policy: str | None, background_set_id: str | None) -> Record: ...


@dataclass(frozen=True)
class PreviewConfiguration:
    load: Callable[[], Record]
    scope: Callable[[Record, Record], Record]
    ensure: Callable[[], Callable[[Record, Record, Record, list[str]], bool]]
    set_state: Callable[[Record, Record, Record], None]
    merge: Callable[[Record, Record, Record], None]
    save: Callable[[Record], Any]


@dataclass(frozen=True)
class PreviewSelection:
    selected: Callable[[], Callable[[Record, list[str]], list[Record]]]
    uid: Callable[[Record], str]
    material: Callable[[Record], str]
    sprites: Callable[[Record], list[Record]]
    version: Callable[[Record], str]
    cache: Callable[[list[Record]], str]


@dataclass(frozen=True)
class PreviewPolicy:
    normalize: Callable[[], Callable[[str | None], str]]
    background: Callable[[], Callable[[str | None, Record], str | None]]
    sequence: Callable[[list[Record], int, str], list[str | None]]
    label: Callable[[list[str | None]], str | None]


class TrainingPreviewSubmission:
    def __init__(self, current: Callable[[], Record], config: PreviewConfiguration,
                 selection: PreviewSelection, policy: PreviewPolicy, artifacts: PreviewArtifacts,
                 draw: Callable[[], DrawPreview], clock: Callable[[], float], uuid: Callable[[], UUID]):
        self.current, self.config, self.selection, self.policy = current, config, selection, policy
        self.artifacts, self.draw, self.clock, self.uuid = artifacts, draw, clock, uuid

    def training_preview(self, request: TrainingPreviewRequest) -> dict[str, Any]:
        user = self.current()
        full_config = self.config.load()
        config = self.config.scope(full_config, user)
        if self.config.ensure()(full_config, config, user, request.selected_accessory_ids):
            config = self.config.scope(full_config, user)
        selected = self.selection.selected()(config, request.selected_accessory_ids)
        pose_policy = self.policy.normalize()(request.preview_pose_family_policy)
        background_set_id = self.policy.background()(request.background_set_id, user)
        sprite_versions = {
            self.selection.uid(item): {
                "clean_sprite_preprocessed_at": item.get("clean_sprite_preprocessed_at"),
                "clean_sprite_count": item.get("clean_sprite_count") or len(self.selection.sprites(item)),
                "clean_sprite_version": self.selection.version(item),
            }
            for item in selected
            if self.selection.material(item) == "object"
        }
        cache_key = self.selection.cache(selected)
        preview_id = f"preview_{int(self.clock())}_{self.uuid().hex[:6]}"
        job_dir = self.artifacts.create_directory(preview_id)
        previews = []
        count = max(1, min(12, int(request.preview_count)))
        pose_sequence = self.policy.sequence(selected, count, pose_policy)
        pose_sequence_label = self.policy.label(pose_sequence)
        seed_base = int(self.clock() * 1000)
        for idx in range(count):
            output_path = job_dir / f"sample_{idx + 1:02d}.png"
            preview = self.draw()(
                selected,
                output_path,
                seed=seed_base + idx,
                pose_family_policy=pose_sequence[idx],
                background_set_id=background_set_id,
            )
            if any(label.get("material_type") == "object" and label.get("source_fallback_error") for label in preview.get("labels", [])):
                raise HTTPException(status_code=409, detail="Clean sprite is unavailable. Regenerate clean sprites before preview.")
            previews.append(preview)
        plan = {
            "id": preview_id,
            "status": "preview_ready",
            "sample_count": max(1, min(20000, int(request.sample_count))),
            "train_mode": request.train_mode,
            "background_set_id": background_set_id,
            "selected_accessories": selected,
            "previews": previews,
            "preview_cache_key": cache_key,
            "preview_sprite_versions": sprite_versions,
            "preview_pose_family_sequence": pose_sequence,
            "preview_pose_family_policy": pose_policy,
            "preview_pose_family_label": pose_sequence_label,
            "pipeline": [
                "normalize_accessory_assets",
                "reuse_preprocessed_clean_object_alpha_sprites",
                "remember_physical_size_metadata",
                "generate_synthetic_combinations",
                "crop_object_foreground_only",
                "paste_saved_rectified_document_directly",
                "scale_by_physical_size",
                "place_on_background_using_background_mm_per_px",
                "apply_pose_aware_rotation_policy",
                "compute_visible_polygon_labels",
                "user_preview_approval",
                "start_yolo_or_yolo_ocr_training",
            ],
        }
        self.artifacts.write_plan(preview_id, plan)
        preview_training_state = {
            "status": "preview_ready",
            "last_preview_id": preview_id,
            "selected_accessory_ids": [item["id"] for item in selected],
            "sample_count": plan["sample_count"],
            "mode": request.train_mode,
            "background_set_id": background_set_id,
            "preview_urls": [item["url"] for item in previews],
            "previews": previews,
            "preview_cache_key": cache_key,
            "preview_sprite_versions": sprite_versions,
            "preview_pose_family_policy": pose_policy,
            "preview_pose_family_label": pose_sequence_label,
            "preview_generated_at": int(self.clock()),
        }
        self.config.set_state(full_config, user, preview_training_state)
        self.config.merge(full_config, config, user)
        self.config.save(full_config)
        return plan
