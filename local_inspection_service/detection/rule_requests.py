"""Detection rule projection and configuration updates."""
from dataclasses import dataclass
from typing import Any
from fastapi import HTTPException
from ..schemas.detection import RuleConfig, TaskRuleConfig
from .rule_request_ports import RulePolicy, RuleStore, RuleAccess

@dataclass(frozen=True)
class DetectionRules:
    policy: RulePolicy
    store: RuleStore
    access: RuleAccess

    def task_rule_overrides(self, config: dict[str, Any], task_id: Any) -> dict[str, Any]:
        rules = config.get("task_rules") if isinstance(config.get("task_rules"), dict) else {}
        clean_id = self.policy.task_rule_id(task_id)
        raw = rules.get(clean_id) if clean_id else None
        return raw if isinstance(raw, dict) else {}


    def apply_task_rule_override_to_spec(self, spec: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        task_id = str(spec.get("task_id") or spec.get("run_id") or "").strip()
        override = self.task_rule_overrides(config, task_id)
        if not override:
            spec.setdefault("confidence_threshold", float(config.get("confidence_threshold", 0.25)))
            return spec
        next_spec = {**spec}
        try:
            next_spec["confidence_threshold"] = max(0.001, min(0.99, float(override.get("confidence_threshold", config.get("confidence_threshold", 0.25)))))
        except (TypeError, ValueError):
            next_spec["confidence_threshold"] = float(config.get("confidence_threshold", 0.25))
        selected_ids = {str(item_id) for item_id in next_spec.get("selected_accessory_ids") or []}
        counts: dict[str, int] = {}
        for item_id, value in (override.get("required_accessory_counts") or {}).items():
            clean_item_id = str(item_id)
            if selected_ids and clean_item_id not in selected_ids:
                continue
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
            if count > 0:
                counts[clean_item_id] = count
        if counts:
            next_spec["required_accessory_counts"] = counts
        return next_spec


    def update_rules(self, rule: RuleConfig) -> dict[str, Any]:
        if not 0.0 <= rule.confidence_threshold <= 1.0:
            raise HTTPException(status_code=400, detail="confidence_threshold must be between 0 and 1")
        unknown = [cls for cls in rule.required_classes if cls not in self.policy.CLASS_NAMES]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown class IDs: {unknown}")
        config = self.store.load_config()
        config["confidence_threshold"] = rule.confidence_threshold
        config["required_classes"] = rule.required_classes
        config["min_counts"] = {str(k): max(1, int(v)) for k, v in rule.min_counts.items()}
        self.store.save_config(config)
        return {"status": "saved", "rule": config}


    def update_task_rules(self, task_id: str, rule: TaskRuleConfig) -> dict[str, Any]:
        clean_task_id = self.policy.task_rule_id(task_id)
        if not clean_task_id:
            raise HTTPException(status_code=400, detail="task_id is required")
        if not 0.0 <= rule.confidence_threshold <= 1.0:
            raise HTTPException(status_code=400, detail="confidence_threshold must be between 0 and 1")
        user = self.access.current_auth_user()
        config = self.store.load_config()
        specs = [
            spec
            for spec in self.store.list_trained_model_specs(config)
            if self.policy.task_rule_id(spec.get("task_id") or spec.get("run_id") or "") == clean_task_id and self.access.record_visible_to_user(spec, user)
        ]
        if not specs:
            raise HTTPException(status_code=404, detail="Detection task not found")
        selected_ids = {str(item_id) for spec in specs for item_id in (spec.get("selected_accessory_ids") or [])}
        counts: dict[str, int] = {}
        for item_id, raw_count in (rule.required_accessory_counts or {}).items():
            clean_item_id = str(item_id or "").strip()
            if not clean_item_id or clean_item_id not in selected_ids:
                continue
            try:
                count = int(raw_count)
            except (TypeError, ValueError):
                continue
            if count > 0:
                counts[clean_item_id] = max(1, min(99, count))
        if not counts:
            raise HTTPException(status_code=400, detail="At least one required accessory is needed")
        config.setdefault("task_rules", {})[clean_task_id] = {
            "confidence_threshold": max(0.001, min(0.99, float(rule.confidence_threshold))),
            "required_accessory_counts": counts,
            "updated_at": self.store.time.time(),
        }
        self.store.save_config(config)
        return {"status": "saved", "task_id": clean_task_id, "rule": config["task_rules"][clean_task_id]}
