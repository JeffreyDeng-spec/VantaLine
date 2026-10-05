"""Status projection and settings workflow with explicit state and policy boundaries."""
from collections import Counter
from dataclasses import dataclass
from typing import Any

from .auto_optimization_status_ports import AutoOptimizationStatusState, AutoOptimizationStatusPolicy


@dataclass(frozen=True)
class AutoOptimizationStatus:
    state: AutoOptimizationStatusState
    policy: AutoOptimizationStatusPolicy

    def public_auto_optimize_state(self, task_id: str, *, user: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.state._auto_optimize_lock():
            state = self.state.load_auto_optimize_state()(task_id)
            state_changed = self.state.hydrate_auto_optimize_background_from_ai_task()(state)
            completed_model_id = self.state.auto_optimize_completed_model_id()(state)
            if completed_model_id and self.state.auto_optimize_stop_capture_for_model_locked()(
                state,
                completed_model_id,
                reason="completed_model_ready",
            ):
                state_changed = True
            if state_changed:
                self.state.save_auto_optimize_state()(state)
        samples = [sample for sample in state.get("samples") or [] if isinstance(sample, dict)]
        if user:
            samples = [sample for sample in samples if self.state.record_visible_to_user()(sample, user)]
        label_counts = Counter(str(sample.get("label_status") or "captured") for sample in samples)
        shadow_runs = [run for run in state.get("shadow_runs") or [] if isinstance(run, dict)]
        agreements = [float(run.get("agreement") or 0.0) for run in shadow_runs if run.get("status") == "completed"]
        latest_dataset = next((item for item in state.get("datasets") or [] if isinstance(item, dict)), None)
        settings = state.get("settings") if isinstance(state.get("settings"), dict) else self.policy.default_auto_optimize_settings()()
        sprite_pool = self.policy.auto_optimize_public_sprite_pool()(state)
        background_set_id = str(state.get("background_set_id") or "")
        environment_background = state.get("environment_background") if isinstance(state.get("environment_background"), dict) else {}
        background_set = self.policy.background_set_payload()(background_set_id) if background_set_id else {}
        dataset_synthetic_samples = sum(int((dataset or {}).get("synthetic_sample_count") or 0) for dataset in state.get("datasets") or [] if isinstance(dataset, dict))
        generated_synthetic_samples = sum(int((sample or {}).get("synthetic_count") or 0) for sample in samples if isinstance(sample, dict))
        synthetic_samples = max(dataset_synthetic_samples, generated_synthetic_samples)
        samples_per_real_image = self.policy.auto_optimize_samples_per_real_image()(settings)
        for candidate in state.get("candidate_models") or []:
            if not isinstance(candidate, dict):
                continue
            task = self.state.find_training_task()(str(candidate.get("job_id") or ""))
            if task:
                candidate["status"] = task.get("status") or candidate.get("status") or ""
                candidate["progress"] = task.get("progress") or candidate.get("progress") or 0
                candidate["note"] = task.get("note") or candidate.get("note") or ""
        latest_candidate = next((item for item in state.get("candidate_models") or [] if isinstance(item, dict)), None)
        training_parameters = self.policy.auto_optimize_training_parameters()(settings)
        positive_samples = label_counts.get("trainable", 0)
        bbox_only_samples = label_counts.get("trainable_bbox_only", 0)
        negative_samples = label_counts.get("negative", 0)
        real_positive_source_count = positive_samples + bbox_only_samples
        training_requirements = self.policy.auto_optimize_training_requirements()(settings, real_positive_source_count=real_positive_source_count)
        negative_samples_per_real_image = self.policy.auto_optimize_negative_samples_per_real_image()(settings)
        positive_derivatives_per_real_image = self.policy.auto_optimize_positive_derivatives_per_real_image()(settings)
        generated_negative_samples = real_positive_source_count * negative_samples_per_real_image
        projected_negative_training_samples = negative_samples + generated_negative_samples
        projected_real_bbox_training_samples = (positive_samples + bbox_only_samples) * self.policy.AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT()
        projected_positive_training_samples = positive_samples * positive_derivatives_per_real_image + projected_real_bbox_training_samples
        return {
            "task_id": state.get("task_id") or task_id,
            "enabled": bool(settings.get("enabled")),
            "serving_mode": settings.get("serving_mode") or "api_primary",
            "active_model_id": state.get("active_model_id") or "",
            "samples_total": len(samples),
            "captured_samples": len(samples),
            "pending_labels": label_counts.get("pending", 0),
            "trainable_samples": positive_samples,
            "bbox_only_samples": bbox_only_samples,
            "review_required_samples": label_counts.get("review_required", 0),
            "negative_samples": negative_samples,
            "generated_negative_sample_count": generated_negative_samples,
            "projected_negative_training_samples": projected_negative_training_samples,
            "negative_samples_per_real_image": negative_samples_per_real_image,
            "positive_derivatives_per_real_image": positive_derivatives_per_real_image,
            "usable_training_samples": positive_samples + bbox_only_samples + negative_samples,
            "projected_positive_training_samples": projected_positive_training_samples,
            "projected_training_samples": projected_positive_training_samples + projected_negative_training_samples,
            "projected_real_bbox_training_samples": projected_real_bbox_training_samples,
            "real_bbox_sample_weight": self.policy.AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT(),
            "samples_per_real_image": samples_per_real_image,
            "sprite_pool_count": len(sprite_pool),
            "sprite_pool": sprite_pool,
            "synthetic_sample_count": synthetic_samples,
            "generated_synthetic_sample_count": generated_synthetic_samples,
            "dataset_synthetic_sample_count": dataset_synthetic_samples,
            "rejected_samples": label_counts.get("rejected", 0) + label_counts.get("failed", 0),
            "latest_sample_at": max([int(sample.get("created_at") or 0) for sample in samples] or [0]),
            "latest_dataset": self.policy.public_path_sanitized()(latest_dataset or {}),
            "latest_candidate_model": self.policy.public_path_sanitized()(latest_candidate or {}),
            "candidate_model_count": len(state.get("candidate_models") or []),
            "shadow_runs": len(shadow_runs),
            "shadow_agreement": round(sum(agreements) / len(agreements), 6) if agreements else 0.0,
            "settings": settings,
            "training_requirements": training_requirements,
            "training_parameters": training_parameters,
            "background_set_id": background_set_id,
            "environment_background": self.policy.public_path_sanitized()(environment_background),
            "background_set": self.policy.public_path_sanitized()(background_set) if background_set else {},
            "phase": self.policy.auto_optimize_phase_name()(state),
            "expected_production_count": self.policy.normalize_expected_production_count()(state.get("expected_production_count")),
            "initialization": self.policy.public_auto_optimize_initialization_payload()(state, settings),
            "samples": [self.policy.public_path_sanitized()(sample) for sample in samples[:80]],
        }

    def auto_optimize_update_settings(self, task_id: str, request: Any) -> dict[str, Any]:
        with self.state._auto_optimize_lock():
            state = self.state.load_auto_optimize_state()(task_id)
            settings = {**self.policy.default_auto_optimize_settings()(), **(state.get("settings") or {})}
            payload = request.dict(exclude_unset=True) if hasattr(request, "dict") else dict(request or {})
            for key in ("enabled", "auto_promote"):
                if key in payload and payload[key] is not None:
                    settings[key] = bool(payload[key])
            for key in ("min_trainable_samples", "min_positive_samples", "samples_per_real_image", "max_label_jobs_per_cycle", "shadow_min_samples"):
                if key in payload and payload[key] is not None:
                    settings[key] = max(1, int(payload[key]))
            if "training_epochs" in payload and payload["training_epochs"] is not None:
                settings["training_epochs"] = max(1, min(500, int(payload["training_epochs"])))
            if "training_image_size" in payload and payload["training_image_size"] is not None:
                settings["training_image_size"] = max(320, min(2048, int(payload["training_image_size"])))
            if "min_negative_samples" in payload and payload["min_negative_samples"] is not None:
                settings["min_negative_samples"] = max(0, int(payload["min_negative_samples"]))
            if "negative_samples_per_real_image" in payload and payload["negative_samples_per_real_image"] is not None:
                settings["negative_samples_per_real_image"] = max(0, min(20, int(payload["negative_samples_per_real_image"])))
            for key in ("mask_compare_min_score", "shadow_min_agreement"):
                if key in payload and payload[key] is not None:
                    settings[key] = max(0.0, min(1.0, float(payload[key])))
            if settings.get("enabled") and settings.get("serving_mode") == "disabled":
                settings["serving_mode"] = "api_primary"
            state["settings"] = settings
            completed_model_id = self.state.auto_optimize_completed_model_id()(state)
            if completed_model_id:
                self.state.auto_optimize_stop_capture_for_model_locked()(state, completed_model_id, reason="completed_model_ready")
            self.state.save_auto_optimize_state()(state)
        if state.get("settings", {}).get("enabled"):
            self.state.start_auto_optimize_label_worker()(str(state.get("task_id") or task_id))
        return self.state.public_auto_optimize_state()(str(state.get("task_id") or task_id), user=self.state.current_auth_user()())
