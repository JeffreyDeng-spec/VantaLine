"""Auto-optimization initialization use case with explicit model and state ports."""
from dataclasses import dataclass
import json
from typing import Any

from .auto_optimization_initialization_ports import AutoOptimizationAdvisorPorts, AutoOptimizationTaskInitializationPorts
from .auto_optimization_settings import normalize_expected_production_count


@dataclass(frozen=True)
class AutoOptimizationInitialization:
    negative_samples_default: int
    advisor: AutoOptimizationAdvisorPorts
    task: AutoOptimizationTaskInitializationPorts

    def agent_auto_optimize_initialization_recommendation(
        self,
        config: dict[str, Any],
        accessory_ids: list[str],
        expected_production_count: int,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        settings = self.advisor.ai_detection_settings()("training_vision")
        if not settings.get("configured"):
            return fallback
        accessories_by_id = self.advisor.accessory_lookup_by_id()(config)
        payload_accessories = []
        for item_id in accessory_ids:
            item = accessories_by_id.get(item_id) or {}
            profile = item.get("ai_profile") if isinstance(item.get("ai_profile"), dict) else {}
            payload_accessories.append(
                {
                    "id": item_id,
                    "name": item.get("name") or item_id,
                    "material_type": self.advisor.accessory_material_type()(item),
                    "source_image_count": len(item.get("source_files") or []),
                    "profile": {
                        "description": self.advisor.bounded_text()(profile.get("description") or "", 220),
                        "visual_signature": self.advisor.bounded_text()(profile.get("visual_signature") or "", 220),
                        "tags": profile.get("tags") if isinstance(profile.get("tags"), list) else [],
                        "dimensions_mm": profile.get("dimensions_mm") if isinstance(profile.get("dimensions_mm"), dict) else {},
                    },
                }
            )
        system = (
            "你是工业视觉质检平台的自动优化初始化 Agent。"
            "根据任务预计产量、配件数量、图片/画像复杂度，判断是否值得在当前生产任务内开启自动优化训练。"
            "只输出 JSON 对象，不要输出解释文本。字段："
            '{"enabled": bool, "complexity": string, "min_trainable_samples": int, '
            '"min_positive_samples": int, "min_negative_samples": int, "negative_samples_per_real_image": int, '
            '"samples_per_real_image": int, "training_epochs": int, "training_image_size": int, '
            '"max_label_jobs_per_cycle": int, "shadow_min_samples": int, "shadow_min_agreement": number, '
            '"auto_promote": bool, "reason": "中文一句话理由"}。'
            "samples_per_real_image 表示每张真实照片总共派生多少训练图；"
            "negative_samples_per_real_image 表示这些派生图里有多少张是负样本，不是额外追加的负样本。"
            "如果所需样本超过总产量，或超过前 30% 产量能采集到的样本量，enabled 必须为 false。"
        )
        prompt = {
            "expected_production_count": expected_production_count,
            "front_30_percent_quota": int(expected_production_count * 0.3) if expected_production_count else 0,
            "accessories": payload_accessories,
            "fallback": fallback,
            "policy": {
                "simple_min": 300,
                "medium_min": 800,
                "complex_min": 1500,
                "hard_min": 150,
                "max_threshold": 3000,
                "samples_per_real_image_default": 12,
                "samples_per_real_image_range": [8, 20],
                "negative_samples_per_real_image_default": self.negative_samples_default,
                "negative_samples_per_real_image_range": [0, 20],
                "negative_samples_are_part_of_samples_per_real_image": True,
                "training_epochs_range": [40, 120],
                "training_image_size_options": [640, 768, 960],
            },
        }
        try:
            parsed, latency_ms, meta = self.advisor.generate_provider_json_with_fallback()(
                settings,
                system,
                [{"type": "text", "text": json.dumps(prompt, ensure_ascii=False)}],
                max_tokens=800,
                max_attempts=1,
            )
            recommendation = self.advisor.clamp_auto_optimize_initialization_recommendation()(parsed, fallback, expected_production_count)
            recommendation["provider"] = settings.get("provider") or ""
            recommendation["model"] = settings.get("model") or ""
            recommendation["latency_ms"] = latency_ms
            if meta.get("usage_metadata"):
                recommendation["usage_metadata"] = meta.get("usage_metadata")
            return recommendation
        except Exception as exc:  # noqa: BLE001 - 初始化建议失败不能阻断任务创建
            return {**fallback, "agent_error": self.advisor.bounded_text()(str(exc), 180)}

    def initialize_auto_optimize_for_pipeline_task(self, task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        ai_task_id = self.task.sanitize_ai_detection_task_id()(task.get("ai_task_id"))
        if not ai_task_id:
            return {}
        expected_count = normalize_expected_production_count(
            task.get("expected_production_count") or (task.get("params") or {}).get("expected_production_count")
        )
        accessory_ids = self.task.canonical_pipeline_accessory_ids()(config, [str(item_id) for item_id in task.get("accessory_ids") or []])
        fallback = self.task.auto_optimize_complexity_rule_recommendation()(config, accessory_ids, expected_count)
        recommendation = self.task.agent_auto_optimize_initialization_recommendation()(config, accessory_ids, expected_count, fallback)
        with self.task._auto_optimize_lock():
            state = self.task.load_auto_optimize_state()(ai_task_id)
            settings = {**self.task.default_auto_optimize_settings(), **(state.get("settings") if isinstance(state.get("settings"), dict) else {})}
            settings.update(
                {
                    "enabled": bool(recommendation.get("enabled")),
                    "min_trainable_samples": int(recommendation.get("min_trainable_samples") or settings.get("min_trainable_samples") or 200),
                    "min_positive_samples": int(recommendation.get("min_positive_samples") or settings.get("min_positive_samples") or recommendation.get("min_trainable_samples") or 200),
                    "min_negative_samples": max(0, int(recommendation.get("min_negative_samples") or settings.get("min_negative_samples") or 0)),
                    "negative_samples_per_real_image": max(
                        0,
                        min(
                            20,
                            int(
                                recommendation.get("negative_samples_per_real_image")
                                if recommendation.get("negative_samples_per_real_image") is not None
                                else settings.get("negative_samples_per_real_image", self.negative_samples_default)
                            ),
                        ),
                    ),
                    "samples_per_real_image": max(1, min(50, int(recommendation.get("samples_per_real_image") or settings.get("samples_per_real_image") or 12))),
                    "training_epochs": max(1, min(500, int(recommendation.get("training_epochs") or settings.get("training_epochs") or 60))),
                    "training_image_size": max(320, min(2048, int(recommendation.get("training_image_size") or settings.get("training_image_size") or 640))),
                    "max_label_jobs_per_cycle": int(recommendation.get("max_label_jobs_per_cycle") or settings.get("max_label_jobs_per_cycle") or 3),
                    "shadow_min_samples": int(recommendation.get("shadow_min_samples") or settings.get("shadow_min_samples") or 80),
                    "shadow_min_agreement": float(recommendation.get("shadow_min_agreement") or settings.get("shadow_min_agreement") or 0.98),
                    "auto_promote": bool(recommendation.get("auto_promote")),
                    "serving_mode": "api_primary",
                }
            )
            state.update(
                {
                    "task_id": ai_task_id,
                    "task_name": task.get("name") or state.get("task_name") or "",
                    "owner_user_id": task.get("owner_user_id") or state.get("owner_user_id") or "",
                    "owner_username": task.get("owner_username") or state.get("owner_username") or "",
                    "selected_accessory_ids": accessory_ids,
                    "required_accessory_counts": task.get("accessory_counts") or state.get("required_accessory_counts") or {},
                    "expected_production_count": expected_count,
                    "auto_optimize_initialization": recommendation,
                    "settings": settings,
                }
            )
            self.task.save_auto_optimize_state()(state)
        task["auto_optimize_initialization"] = recommendation
        task["expected_production_count"] = expected_count
        if isinstance(task.get("params"), dict):
            task["params"]["expected_production_count"] = expected_count
        if recommendation.get("enabled"):
            self.task.start_auto_optimize_label_worker()(ai_task_id)
        return recommendation
