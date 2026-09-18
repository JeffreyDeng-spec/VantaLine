"""Exact-count business rules with explicit, lazily read class/manual labels."""
from collections import Counter, defaultdict
from collections.abc import Callable
from typing import Any


class CountRules:
    def __init__(self, class_labels: Callable[[], dict[int, str]], manual_labels: Callable[[], dict[str, str]]):
        self.class_labels, self.manual_labels = class_labels, manual_labels

    def apply(self, detections: list[dict[str, Any]], config: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
        threshold = float(spec.get("confidence_threshold", config["confidence_threshold"]))
        if spec.get("is_specialized"):
            required_accessory_counts = {
                str(k): max(0, int(v))
                for k, v in (spec.get("required_accessory_counts") or {}).items()
            }
            if not required_accessory_counts:
                required_accessory_counts = {str(item_id): 1 for item_id in spec.get("selected_accessory_ids") or []}
            required_keys = list(required_accessory_counts.keys())
            class_labels = {str(k): str(v) for k, v in (spec.get("accessory_labels") or {}).items()}
            rule_source = "task"
            rule_task_id = spec.get("task_id")
            rule_label = " + ".join(str(x) for x in spec.get("accessory_names") or []) or str(spec.get("label") or "")
        else:
            required_keys = [int(x) for x in config["required_classes"]]
            required_accessory_counts = {}
            min_counts = {int(k): int(v) for k, v in config["min_counts"].items()}
            class_labels = {int(k): str(v) for k, v in self.class_labels().items()}
            rule_source = "global"
            rule_task_id = None
            rule_label = "通用规则"
        count_by_rule_key: Counter[Any] = Counter()
        max_conf_by_rule_key: defaultdict[Any, float] = defaultdict(float)
        for det in detections:
            conf = float(det["confidence"])
            if conf >= threshold:
                rule_key: Any = str(det.get("resolved_accessory_id") or det.get("accessory_id")) if spec.get("is_specialized") else int(det["class_id"])
                if spec.get("is_specialized") and (not rule_key or rule_key == "None"):
                    continue
                count_by_rule_key[rule_key] += 1
                max_conf_by_rule_key[rule_key] = max(max_conf_by_rule_key[rule_key], conf)

        missing = []
        present = []
        extra = []
        for rule_key in required_keys:
            need = required_accessory_counts.get(str(rule_key), min_counts.get(rule_key, 1) if not spec.get("is_specialized") else 1)
            found = count_by_rule_key.get(rule_key, 0)
            row = {
                "class_id": rule_key,
                "label": class_labels.get(rule_key, f"Class {rule_key}"),
                "required": need,
                "found": found,
                "max_confidence": round(max_conf_by_rule_key.get(rule_key, 0.0), 4),
            }
            if spec.get("is_specialized"):
                row["accessory_id"] = str(rule_key)
            if found == need:
                present.append(row)
            elif found > need:
                row["issue"] = "extra"
                extra.append(row)
                missing.append(row)
            else:
                row["issue"] = "missing"
                missing.append(row)

        manual_type_counts: Counter[str] = Counter()
        for det in detections:
            if int(det["class_id"]) == 1:
                manual_type = det.get("manual_type") or det.get("ocr", {}).get("manual_type")
                if manual_type and manual_type != "unknown":
                    manual_type_counts[str(manual_type)] += 1

        ocr_config = config.get("ocr", {})
        required_manual_types = [str(x) for x in ocr_config.get("manual_types", self.manual_labels().keys())]
        manual_type_missing = []
        manual_type_present = []
        if not spec.get("is_specialized") and ocr_config.get("enabled", True) and ocr_config.get("require_manual_types", True):
            for manual_type in required_manual_types:
                row = {
                    "manual_type": manual_type,
                    "label": self.manual_labels().get(manual_type, manual_type),
                    "required": 1,
                    "found": manual_type_counts.get(manual_type, 0),
                }
                if row["found"] == 1:
                    manual_type_present.append(row)
                else:
                    row["issue"] = "extra" if row["found"] > 1 else "missing"
                    manual_type_missing.append(row)

        passed = len(missing) == 0 and len(manual_type_missing) == 0
        return {
            "passed": passed,
            "threshold": threshold,
            "match_policy": "exact_count",
            "source": rule_source,
            "task_id": rule_task_id,
            "label": rule_label,
            "present": present,
            "missing": missing,
            "extra": extra,
            "counts": {class_labels.get(k, str(k)): v for k, v in sorted(count_by_rule_key.items(), key=lambda item: str(item[0]))},
            "ocr_enabled": bool(spec.get("uses_ocr", False) and ocr_config.get("enabled", True)),
            "manual_type_counts": {
                self.manual_labels().get(k, k): v for k, v in sorted(manual_type_counts.items())
            },
            "manual_type_present": manual_type_present,
            "manual_type_missing": manual_type_missing,
        }
