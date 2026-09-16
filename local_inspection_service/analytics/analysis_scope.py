"""Required-accessory scope projection using explicit task/configuration sources."""
from collections.abc import Callable
from dataclasses import dataclass
import re
from typing import Any

Record = dict[str, Any]


@dataclass(frozen=True)
class ScopeDependencies:
    current_user: Callable[[], Record]
    load_config: Callable[[], Record]
    scope_config: Callable[[Record, Record], Record]
    accessory_lookup: Callable[[Record], dict[str, Record]]
    detection_tasks: Callable[[], list[Record]]
    serialize_task: Callable[[Record, Record], Record]
    normalize_counts: Callable[[Any], dict[str, int]]
    accessory_id: Callable[[Record], str]
    accessory_aliases: Callable[[Record], list[str]]
    english_name: Callable[[Any], str]
    bounded_text: Callable[[Any, int], str]


def data_analysis_scope_match_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def data_analysis_count_for_scope_item(record: dict[str, Any], scope_item: dict[str, Any]) -> int:
    ai_result = record.get("ai_detection_result") if isinstance(record.get("ai_detection_result"), dict) else {}
    rule_payload = ai_result.get("rule") if isinstance(ai_result.get("rule"), dict) else {}
    aliases = {str(item) for item in scope_item.get("aliases", []) if str(item).strip()}
    label_aliases = {str(item) for item in scope_item.get("label_aliases", []) if str(item).strip()}
    for raw_key, raw_count in (rule_payload.get("counts") or {}).items():
        key_text = str(raw_key or "").strip()
        if key_text not in aliases and data_analysis_scope_match_key(key_text) not in label_aliases:
            continue
        try:
            return max(0, int(raw_count))
        except (TypeError, ValueError):
            return 0
    for det in ai_result.get("detections", []):
        if not isinstance(det, dict):
            continue
        det_id = str(det.get("accessory_id") or "").strip()
        det_label_key = data_analysis_scope_match_key(det.get("label"))
        if det_id not in aliases and det_label_key not in label_aliases:
            continue
        if det.get("present") is not True:
            return 0
        try:
            return max(1, int(det.get("count") or 1))
        except (TypeError, ValueError):
            return 1
    return 0


class AnalysisScope:
    def __init__(self, dependencies: ScopeDependencies):
        self.dependencies = dependencies

    def data_analysis_record_required_scope(self, record: dict[str, Any]) -> dict[str, dict[str, Any]]:
        task_payload_for_type = record.get("task") if isinstance(record.get("task"), dict) else {}
        if str(task_payload_for_type.get("type") or "") == "image_processing":
            return {}
        ai_result = record.get("ai_detection_result") if isinstance(record.get("ai_detection_result"), dict) else {}
        model_payload = ai_result.get("model") if isinstance(ai_result.get("model"), dict) else {}
        user = self.dependencies.current_user()
        config = self.dependencies.scope_config(self.dependencies.load_config(), user)
        accessories_by_alias = self.dependencies.accessory_lookup(config)
        source_by_accessory: dict[str, dict[str, Any]] = {}

        task_payload: dict[str, Any] = {}
        task_id = str(model_payload.get("task_id") or (record.get("task") or {}).get("id") or "").strip()
        if task_id:
            for task in self.dependencies.detection_tasks():
                if str(task.get("id") or "") == task_id:
                    task_payload = self.dependencies.serialize_task(task, config)
                    break

        model_counts = self.dependencies.normalize_counts(model_payload.get("required_accessory_counts") or {})
        task_counts = self.dependencies.normalize_counts(task_payload.get("required_accessory_counts") or {})
        required_counts = model_counts or task_counts
        selected_ids = [str(item_id) for item_id in model_payload.get("selected_accessory_ids") or [] if str(item_id).strip()]
        if not selected_ids:
            selected_ids = [str(item_id) for item_id in task_payload.get("selected_accessory_ids") or [] if str(item_id).strip()]
        if not selected_ids:
            selected_ids = list(required_counts.keys())

        labels = {str(k): str(v) for k, v in (task_payload.get("accessory_labels") or {}).items() if str(v).strip()}
        labels.update({str(k): str(v) for k, v in (model_payload.get("accessory_labels") or {}).items() if str(v).strip()})
        accessory_names = [str(name) for name in model_payload.get("accessory_names") or [] if str(name).strip()]
        for index, item_id in enumerate(selected_ids):
            if item_id not in labels and index < len(accessory_names):
                labels[item_id] = accessory_names[index]

        scope: dict[str, dict[str, Any]] = {}

        def resolve_accessory(raw_id: Any) -> tuple[str, dict[str, Any]]:
            item_id = str(raw_id or "").strip()
            if not item_id:
                return "", {}
            accessory = accessories_by_alias.get(item_id)
            if accessory:
                canonical_id = self.dependencies.accessory_id(accessory)
                return canonical_id, accessory
            return item_id, {}

        def add_scope_item(raw_id: Any, expected_count: Any = 1, label: Any = "", source: str = "") -> None:
            canonical_id, accessory = resolve_accessory(raw_id)
            if not canonical_id:
                return
            try:
                count = max(1, min(99, int(expected_count or 1)))
            except (TypeError, ValueError):
                count = 1
            item = scope.setdefault(
                canonical_id,
                {
                    "accessory_id": canonical_id,
                    "required_count": count,
                    "label": "",
                    "aliases": set(),
                    "label_aliases": set(),
                    "source_item": source_by_accessory.get(canonical_id, {}),
                    "scope_source": source,
                },
            )
            item["required_count"] = count
            item["aliases"].add(canonical_id)
            raw_text = str(raw_id or "").strip()
            if raw_text:
                item["aliases"].add(raw_text)
            source_item = item.get("source_item") if isinstance(item.get("source_item"), dict) else {}
            if accessory:
                for alias in self.dependencies.accessory_aliases(accessory):
                    item["aliases"].add(alias)
                latest_source_item = source_by_accessory.get(canonical_id)
                if latest_source_item:
                    item["source_item"] = latest_source_item
                    source_item = latest_source_item
            native_label = str(
                label
                or labels.get(raw_text)
                or labels.get(canonical_id)
                or source_item.get("native_label")
                or (accessory or {}).get("name")
                or (accessory or {}).get("label")
                or canonical_id
            ).strip()
            display_label = (
                self.dependencies.english_name(source_item.get("display_label"))
                or self.dependencies.english_name(source_item.get("english_name"))
                or self.dependencies.english_name(label)
                or self.dependencies.english_name(labels.get(raw_text))
                or self.dependencies.english_name(labels.get(canonical_id))
                or self.dependencies.english_name((accessory or {}).get("english_name"))
                or self.dependencies.english_name((accessory or {}).get("name"))
                or native_label
            )
            item["label"] = self.dependencies.bounded_text(display_label, 160)
            item["native_label"] = self.dependencies.bounded_text(native_label, 160)
            for candidate in (display_label, native_label, labels.get(raw_text), labels.get(canonical_id), source_item.get("native_label"), (accessory or {}).get("name"), (accessory or {}).get("label")):
                key = data_analysis_scope_match_key(candidate)
                if key:
                    item["label_aliases"].add(key)

        for item_id in selected_ids:
            if not item_id:
                continue
            add_scope_item(item_id, required_counts.get(item_id, 1), labels.get(item_id), "model_required_accessories")
        for item_id, count in required_counts.items():
            if item_id not in scope:
                add_scope_item(item_id, count, labels.get(item_id), "model_required_counts")

        if scope:
            for item in scope.values():
                item["aliases"] = sorted(str(alias) for alias in item["aliases"] if str(alias).strip())
                item["label_aliases"] = sorted(str(alias) for alias in item["label_aliases"] if str(alias).strip())
            return scope

        rule_payload = ai_result.get("rule") if isinstance(ai_result.get("rule"), dict) else {}
        detections = [item for item in ai_result.get("detections", []) if isinstance(item, dict)]
        for det in detections:
            accessory_id = str(det.get("accessory_id") or "").strip()
            if not accessory_id:
                continue
            expected = det.get("required") or det.get("expected_count") or det.get("count") or 1
            add_scope_item(accessory_id, expected, det.get("label"), "legacy_detection_fallback")
        if not scope:
            for item_id, count in (rule_payload.get("counts") or {}).items():
                add_scope_item(item_id, count, "", "legacy_rule_count_fallback")
        for item in scope.values():
            item["aliases"] = sorted(str(alias) for alias in item["aliases"] if str(alias).strip())
            item["label_aliases"] = sorted(str(alias) for alias in item["label_aliases"] if str(alias).strip())
        return scope

    def data_analysis_scoped_ai_summary(self, record: dict[str, Any]) -> dict[str, Any]:
        scope = self.data_analysis_record_required_scope(record)
        if not scope:
            return record.get("ai_summary") if isinstance(record.get("ai_summary"), dict) else {}
        counts: dict[str, int] = {}
        missing: list[str] = []
        mismatches: dict[str, dict[str, Any]] = {}
        for accessory_id, scope_item in scope.items():
            expected = int(scope_item.get("required_count") or 1)
            found = data_analysis_count_for_scope_item(record, scope_item)
            counts[accessory_id] = found
            if found <= 0:
                missing.append(accessory_id)
            if found != expected:
                mismatches[accessory_id] = {
                    "expected": expected,
                    "found": found,
                    "issue": "over_count" if found > expected else "under_count",
                }
        result = record.get("ai_detection_result") if isinstance(record.get("ai_detection_result"), dict) else {}
        ai = result.get("ai") if isinstance(result.get("ai"), dict) else {}
        return {
            "passed": not mismatches,
            "detection_count": sum(1 for count in counts.values() if count > 0),
            "present_count": sum(1 for accessory_id, found in counts.items() if found == int(scope[accessory_id].get("required_count") or 1)),
            "missing_count": len(missing),
            "extra_count": 0,
            "count_mismatch_count": len(mismatches),
            "counts": counts,
            "missing": missing,
            "extra": [],
            "provider_status": str(ai.get("provider_status") or ""),
            "latency_ms": int(ai.get("latency_ms") or 0),
        }

    def public_data_analysis_scope_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": "ai_detection_task_required_accessories",
            "required_accessories": [
                {
                    "accessory_id": accessory_id,
                    "label": scope_item.get("label") or accessory_id,
                    "required_count": int(scope_item.get("required_count") or 1),
                    "ai_detection_count": data_analysis_count_for_scope_item(record, scope_item),
                }
                for accessory_id, scope_item in self.data_analysis_record_required_scope(record).items()
            ],
        }
