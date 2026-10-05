"""Owner-scoped synthetic batch preparation, reuse and result state transitions."""
from dataclasses import dataclass
from typing import Any
import time
import numpy as np
from .auto_optimization_synthetic_batch_ports import (
    SyntheticBatchConfiguration, SyntheticBatchSprites, SyntheticBatchPublication,
)

@dataclass(frozen=True)
class AutoOptimizationSyntheticBatch:
    configuration: SyntheticBatchConfiguration
    sprites: SyntheticBatchSprites
    publication: SyntheticBatchPublication

    def auto_optimize_generate_synthetic_batch_for_sample(
        self,
        task_id: str,
        state: dict[str, Any],
        sample: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not isinstance(sample, dict) or sample.get("label_status") != "trainable":
            return []
        requested_background_set_id = self.configuration.safe_background_set_id()(str(state.get("background_set_id") or "green_conveyor"))
        settings = state.get("settings") if isinstance(state.get("settings"), dict) else self.configuration.default_auto_optimize_settings()()
        sample_count = self.configuration.auto_optimize_positive_derivatives_per_real_image()(settings)
        if sample_count <= 0:
            sample["synthetic_samples"] = []
            sample["synthetic_count"] = 0
            sample["synthetic_status"] = "completed"
            sample["synthetic_completed_at"] = int(time.time())
            sample.pop("synthetic_error", None)
            return []
        existing = [item for item in sample.get("synthetic_samples") or [] if isinstance(item, dict) and item.get("image") and item.get("labels")]
        if len(existing) == sample_count and sample.get("synthetic_status") == "completed" and all(
            item.get("target_size_policy") == self.configuration.AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY()
            and ((item.get("augmentation") if isinstance(item.get("augmentation"), dict) else {}).get("requested_background_set_id") or (item.get("augmentation") if isinstance(item.get("augmentation"), dict) else {}).get("background_set_id") or "green_conveyor") == requested_background_set_id
            for item in existing
        ):
            return existing
        selected_ids = [str(item) for item in state.get("selected_accessory_ids") or [] if str(item)]
        if not selected_ids:
            selected_ids = sorted({str(label.get("accessory_id") or "") for label in sample.get("labels") or [] if isinstance(label, dict) and label.get("accessory_id")})
        if not selected_ids:
            sample["synthetic_status"] = "failed"
            sample["synthetic_error"] = "missing_selected_accessory_ids"
            return []
        request_user = self.configuration._request_user().get() or {
            "id": str(state.get("owner_user_id") or self.configuration.LEGACY_OWNER_ID()),
            "username": str(state.get("owner_username") or state.get("owner_user_id") or self.configuration.LEGACY_OWNER_ID()),
            "role": "admin",
        }
        config = self.configuration.scope_config_for_user()(self.configuration.load_config()(), request_user)
        accessories_by_id = self.configuration.accessory_lookup_by_id()(config)
        class_index = {item_id: idx for idx, item_id in enumerate(selected_ids)}
        self.sprites.auto_optimize_backfill_missing_sprites_for_sample()(task_id, state, sample)
        sprites = self.sprites.auto_optimize_sprite_records_for_sample()(sample)
        if not sprites:
            sample["synthetic_status"] = "failed"
            sample["synthetic_error"] = "no_trainable_ai_mask_sprites"
            return []
        canonical_sizes = self.sprites.auto_optimize_canonical_sprite_sizes()(state, extra_sprites=sprites)
        owner_id = str(state.get("owner_user_id") or sample.get("owner_user_id") or "")
        sample_id = self.publication.safe_record_id()(str(sample.get("sample_id") or "sample"))
        output_dir = self.publication.output_write_dir_for_owner()("auto_optimize_synthetic", owner_id) / self.publication.safe_record_id()(task_id) / sample_id
        generated: list[dict[str, Any]] = []
        sample["synthetic_status"] = "running"
        sample["synthetic_started_at"] = int(time.time())
        rng = np.random.default_rng(int(time.time() * 1000) ^ abs(hash(sample_id)) % (2**31))
        for idx in range(sample_count):
            image_path = output_dir / "images" / f"synthetic_{idx + 1:04d}.png"
            label_path = output_dir / "labels" / f"synthetic_{idx + 1:04d}.txt"
            annotated_path = output_dir / "previews" / f"synthetic_{idx + 1:04d}_boxed.jpg"
            rendered = self.publication.auto_optimize_render_synthetic_sample()(
                sprites=sprites,
                class_index=class_index,
                accessories_by_id=accessories_by_id,
                output_path=image_path,
                label_path=label_path,
                annotated_path=annotated_path,
                split="train",
                rng=rng,
                canonical_sizes=canonical_sizes,
                background_set_id=requested_background_set_id,
            )
            if not rendered:
                continue
            rendered.update(
                {
                    "source_sample_id": sample.get("sample_id"),
                    "source_record_id": sample.get("record_id"),
                    "variant_index": idx,
                    "created_at": int(time.time()),
                    "target_size_policy": self.configuration.AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY(),
                }
            )
            generated.append(rendered)
            sample["synthetic_count"] = len(generated)
        sample["synthetic_samples"] = generated
        sample["synthetic_count"] = len(generated)
        sample["synthetic_completed_at"] = int(time.time())
        sample["synthetic_status"] = "completed" if generated else "failed"
        if not generated:
            sample["synthetic_error"] = "synthetic_render_failed"
        else:
            sample.pop("synthetic_error", None)
        return generated
