"""Auto-optimization recommendation rules and public projection, without model calls."""
from dataclasses import dataclass
from typing import Any, Callable
from .auto_optimization_settings import AutoOptimizationSettings, normalize_expected_production_count


@dataclass(frozen=True)
class AutoOptimizationRecommendations:
    settings: AutoOptimizationSettings
    accessory_lookup_by_id: Callable[[dict[str, Any]], dict[str, dict[str, Any]]]
    accessory_material_type: Callable[[dict[str, Any]], str]
    bounded_text: Callable[[], Callable[[Any, int], str]]

    def auto_optimize_complexity_rule_recommendation(
        self,
        config: dict[str, Any],
        accessory_ids: list[str],
        expected_production_count: int,
    ) -> dict[str, Any]:
        accessories_by_id = self.accessory_lookup_by_id(config)
        selected = [accessories_by_id.get(item_id, {}) for item_id in accessory_ids]
        class_count = max(1, len(selected))
        material_types = {self.accessory_material_type(item) for item in selected if item}
        has_text = "text" in material_types
        low_reference_count = any(len(item.get("source_files") or []) < 3 for item in selected if item)
        if has_text:
            min_samples = 400 if class_count <= 3 else 700
            complexity = "text_yolo_ocr"
        elif class_count <= 2:
            min_samples = 300
            complexity = "simple"
        elif class_count <= 6:
            min_samples = 800
            complexity = "medium"
        else:
            min_samples = 1500
            complexity = "complex"
        if low_reference_count:
            min_samples += 150
        min_samples = max(150, min(3000, min_samples))
        early_quota = int(expected_production_count * 0.3) if expected_production_count else 0
        feasible = bool(expected_production_count and min_samples <= expected_production_count and min_samples <= early_quota)
        if not expected_production_count:
            reason = "未填写预计产量，无法判断当前生产流程能否覆盖训练样本，默认关闭自动优化。"
        elif min_samples > expected_production_count:
            reason = f"预计至少需要 {min_samples} 张可训练样本，已超过预计产量 {expected_production_count}，不适合开启自动优化。"
        elif min_samples > early_quota:
            reason = f"预计至少需要 {min_samples} 张可训练样本，但前 30% 产量约 {early_quota} 张，训练上线可能赶不上当前产线。"
        else:
            reason = f"任务复杂度 {complexity}，预计产量 {expected_production_count}，建议以 {min_samples} 张可训练样本作为训练阈值。"
        return {
            "enabled": feasible,
            "complexity": complexity,
            "samples_per_real_image": 12 if class_count <= 6 else 16,
            "training_epochs": 80 if has_text or class_count > 2 else 60,
            "training_image_size": 768 if has_text else 640,
            "min_trainable_samples": min_samples,
            "min_positive_samples": min_samples,
            "min_negative_samples": 0,
            "negative_samples_per_real_image": self.settings.negative_samples_default,
            "max_label_jobs_per_cycle": 5 if feasible and expected_production_count >= 3000 else 3,
            "shadow_min_samples": max(20, min(120, int(min_samples * 0.25))),
            "shadow_min_agreement": 0.98,
            "auto_promote": bool(feasible and expected_production_count >= min_samples * 3),
            "expected_production_count": expected_production_count,
            "early_training_quota": early_quota,
            "reason": reason,
            "source": "rules",
        }

    def clamp_auto_optimize_initialization_recommendation(
        self,
        raw: dict[str, Any],
        fallback: dict[str, Any],
        expected_production_count: int,
    ) -> dict[str, Any]:
        result = dict(fallback)
        try:
            min_samples = max(150, min(3000, int(raw.get("min_trainable_samples") or fallback["min_trainable_samples"])))
        except (TypeError, ValueError):
            min_samples = int(fallback["min_trainable_samples"])
        raw_min_positive = raw.get("min_positive_samples") if "min_positive_samples" in raw else fallback.get("min_positive_samples")
        try:
            min_positive = max(1, min(3000, int(raw_min_positive or min_samples)))
        except (TypeError, ValueError):
            min_positive = int(fallback.get("min_positive_samples") or min_samples)
        raw_min_negative = raw.get("min_negative_samples") if "min_negative_samples" in raw else fallback.get("min_negative_samples")
        try:
            min_negative = max(0, min(3000, int(0 if raw_min_negative is None else raw_min_negative)))
        except (TypeError, ValueError):
            min_negative = int(fallback.get("min_negative_samples") or 0)
        raw_negative_per_real = (
            raw.get("negative_samples_per_real_image")
            if "negative_samples_per_real_image" in raw
            else fallback.get("negative_samples_per_real_image")
        )
        try:
            raw_negative_ratio = raw_negative_per_real if raw_negative_per_real is not None else self.settings.negative_samples_default
            negative_per_real = max(0, min(20, int(raw_negative_ratio)))
        except (TypeError, ValueError):
            negative_per_real = int(fallback.get("negative_samples_per_real_image") or self.settings.negative_samples_default)
        early_quota = int(expected_production_count * 0.3) if expected_production_count else 0
        required_samples = max(min_samples, min_positive + min_negative)
        feasible = bool(expected_production_count and required_samples <= expected_production_count and required_samples <= early_quota)
        result.update(
            {
                "enabled": feasible and bool(raw.get("enabled", fallback.get("enabled"))),
                "complexity": self.bounded_text()(raw.get("complexity") or fallback.get("complexity") or "unknown", 80),
                "min_trainable_samples": min_samples,
                "min_positive_samples": min_positive,
                "min_negative_samples": min_negative,
                "negative_samples_per_real_image": negative_per_real,
                "samples_per_real_image": max(1, min(50, int(raw.get("samples_per_real_image") or fallback.get("samples_per_real_image") or 12))),
                "training_epochs": max(1, min(500, int(raw.get("training_epochs") or fallback.get("training_epochs") or 60))),
                "training_image_size": max(320, min(2048, int(raw.get("training_image_size") or fallback.get("training_image_size") or 640))),
                "max_label_jobs_per_cycle": max(1, min(20, int(raw.get("max_label_jobs_per_cycle") or fallback.get("max_label_jobs_per_cycle") or 3))),
                "shadow_min_samples": max(10, min(500, int(raw.get("shadow_min_samples") or fallback.get("shadow_min_samples") or 80))),
                "shadow_min_agreement": max(0.8, min(1.0, float(raw.get("shadow_min_agreement") or fallback.get("shadow_min_agreement") or 0.98))),
                "auto_promote": bool(raw.get("auto_promote", fallback.get("auto_promote", True))) and feasible,
                "expected_production_count": expected_production_count,
                "early_training_quota": early_quota,
                "source": "gemini",
                "reason": self.bounded_text()(raw.get("reason") or fallback.get("reason") or "", 240),
            }
        )
        if expected_production_count and not feasible:
            result["enabled"] = False
            if required_samples > expected_production_count:
                result["reason"] = f"Agent 估算需要 {required_samples} 张可用训练样本，超过预计产量 {expected_production_count}，自动优化关闭。"
            elif required_samples > early_quota:
                result["reason"] = f"Agent 估算需要 {required_samples} 张可用训练样本，超过前 30% 产量 {early_quota}，当前产线不适合自动训练切换。"
        return result

    def public_auto_optimize_initialization_payload(self, state: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("auto_optimize_initialization")
        payload = dict(raw) if isinstance(raw, dict) else {}
        expected_production_count = normalize_expected_production_count(
            state.get("expected_production_count") or payload.get("expected_production_count")
        )
        requirements = self.settings.auto_optimize_training_requirements(settings)
        min_trainable = int(requirements.get("min_trainable_samples") or 0)
        min_positive = int(requirements.get("min_positive_samples") or min_trainable)
        min_negative = int(requirements.get("min_negative_samples") or 0)
        required_samples = max(min_trainable, min_positive + min_negative)
        early_quota = int(expected_production_count * 0.3) if expected_production_count else 0
        payload.update(
            {
                "expected_production_count": expected_production_count,
                "early_training_quota": early_quota,
                "min_trainable_samples": min_trainable,
                "min_positive_samples": min_positive,
                "min_negative_samples": min_negative,
                "samples_per_real_image": self.settings.auto_optimize_samples_per_real_image(settings),
                "negative_samples_per_real_image": self.settings.auto_optimize_negative_samples_per_real_image(settings),
                "positive_derivatives_per_real_image": self.settings.auto_optimize_positive_derivatives_per_real_image(settings),
            }
        )
        if not expected_production_count:
            payload["reason"] = "未填写预计产量，无法判断当前生产流程能否覆盖训练样本，默认关闭自动优化。"
        elif required_samples > expected_production_count:
            payload["reason"] = (
                f"Agent 估算需要 {required_samples} 张可用训练样本"
                f"（正样本 {min_positive}、额外必需负样本 {min_negative}；派生负样本计入单图派生预算），"
                f"超过预计产量 {expected_production_count}，自动优化关闭。"
            )
        elif required_samples > early_quota:
            payload["reason"] = (
                f"Agent 估算需要 {required_samples} 张可用训练样本"
                f"（正样本 {min_positive}、额外必需负样本 {min_negative}；派生负样本计入单图派生预算），"
                f"超过前 30% 产量 {early_quota}，当前产线不适合自动训练切换。"
            )
        elif payload.get("enabled"):
            payload["reason"] = (
                f"预计产量 {expected_production_count}，训练阈值 {required_samples}，"
                f"派生负样本计入单图派生预算，可开启自动优化。"
            )
        else:
            payload["reason"] = (
                f"按当前配置需要 {required_samples} 张可用训练样本"
                f"（正样本 {min_positive}、额外必需负样本 {min_negative}；派生负样本计入单图派生预算），"
                f"未超过前 30% 产量 {early_quota}；自动优化当前未由初始化建议开启。"
            )
        return payload
