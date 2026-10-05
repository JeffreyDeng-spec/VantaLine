"""Auto-optimization settings parsing with an explicit startup negative default."""
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AutoOptimizationSettings:
    negative_samples_default: int

    def default_auto_optimize_settings(self) -> dict[str, Any]:
        min_trainable_samples = max(20, int(os.environ.get("VANTALINE_AUTO_OPT_MIN_TRAINABLE_SAMPLES", "200")))
        return {
            "enabled": False,
            "serving_mode": "api_primary",
            "samples_per_real_image": max(1, min(50, int(os.environ.get("VANTALINE_AUTO_OPT_SAMPLES_PER_REAL_IMAGE", "12")))),
            "training_epochs": max(1, min(500, int(os.environ.get("VANTALINE_AUTO_OPT_EPOCHS", "60")))),
            "training_image_size": max(320, min(2048, int(os.environ.get("VANTALINE_AUTO_OPT_IMAGE_SIZE", "640")))),
            "min_trainable_samples": min_trainable_samples,
            "min_positive_samples": max(
                1,
                int(os.environ.get("VANTALINE_AUTO_OPT_MIN_POSITIVE_SAMPLES", str(min_trainable_samples))),
            ),
            "min_negative_samples": max(0, int(os.environ.get("VANTALINE_AUTO_OPT_MIN_NEGATIVE_SAMPLES", "0"))),
            "negative_samples_per_real_image": self.negative_samples_default,
            "max_label_jobs_per_cycle": max(1, int(os.environ.get("VANTALINE_AUTO_OPT_MAX_LABEL_JOBS_PER_CYCLE", "3"))),
            "mask_compare_min_score": max(0.0, min(1.0, float(os.environ.get("VANTALINE_AUTO_OPT_MASK_COMPARE_MIN_SCORE", "0.72")))),
            "shadow_min_samples": max(10, int(os.environ.get("VANTALINE_AUTO_OPT_SHADOW_MIN_SAMPLES", "80"))),
            "shadow_min_agreement": max(0.0, min(1.0, float(os.environ.get("VANTALINE_AUTO_OPT_SHADOW_MIN_AGREEMENT", "0.98")))),
            "auto_promote": True,
        }

    def auto_optimize_negative_samples_per_real_image(self, settings: dict[str, Any] | None) -> int:
        opts = {**self.default_auto_optimize_settings(), **(settings if isinstance(settings, dict) else {})}
        try:
            raw_value = (
                opts.get("negative_samples_per_real_image")
                if opts.get("negative_samples_per_real_image") is not None
                else self.negative_samples_default
            )
            return max(0, min(20, int(raw_value)))
        except (TypeError, ValueError):
            return self.negative_samples_default

    def auto_optimize_positive_derivatives_per_real_image(self, settings: dict[str, Any] | None) -> int:
        """Positive derivatives are the remainder after generated negatives."""
        samples_per_real = self.auto_optimize_samples_per_real_image(settings)
        negative_per_real = self.auto_optimize_negative_samples_per_real_image(settings)
        return max(0, samples_per_real - negative_per_real)

    def auto_optimize_training_requirements(self, settings: dict[str, Any] | None, *, real_positive_source_count: int = 0) -> dict[str, int]:
        opts = {**self.default_auto_optimize_settings(), **(settings if isinstance(settings, dict) else {})}
        try:
            min_trainable = max(1, int(opts.get("min_trainable_samples") or 200))
        except (TypeError, ValueError):
            min_trainable = 200
        try:
            min_positive = max(1, int(opts.get("min_positive_samples") or min_trainable))
        except (TypeError, ValueError):
            min_positive = min_trainable
        try:
            min_negative = max(0, int(opts.get("min_negative_samples") or 0))
        except (TypeError, ValueError):
            min_negative = 0
        negative_per_real = self.auto_optimize_negative_samples_per_real_image(opts)
        return {
            "min_trainable_samples": min_trainable,
            "min_positive_samples": min_positive,
            "min_negative_samples": min_negative,
            "negative_samples_per_real_image": negative_per_real,
            "positive_derivatives_per_real_image": self.auto_optimize_positive_derivatives_per_real_image(opts),
        }

    def auto_optimize_samples_per_real_image(self, settings: dict[str, Any] | None) -> int:
        opts = {**self.default_auto_optimize_settings(), **(settings if isinstance(settings, dict) else {})}
        try:
            return max(1, min(50, int(opts.get("samples_per_real_image") or 12)))
        except (TypeError, ValueError):
            return 12

    def auto_optimize_training_parameters(self, settings: dict[str, Any] | None) -> dict[str, int]:
        opts = {**self.default_auto_optimize_settings(), **(settings if isinstance(settings, dict) else {})}
        try:
            epochs = max(1, min(500, int(opts.get("training_epochs") or opts.get("epochs") or 60)))
        except (TypeError, ValueError):
            epochs = 60
        try:
            image_size = max(320, min(2048, int(opts.get("training_image_size") or opts.get("image_size") or 640)))
        except (TypeError, ValueError):
            image_size = 640
        return {"training_epochs": epochs, "training_image_size": image_size}


def normalize_expected_production_count(value: Any) -> int:
    try:
        return max(0, min(1_000_000, int(float(value or 0))))
    except (TypeError, ValueError):
        return 0
