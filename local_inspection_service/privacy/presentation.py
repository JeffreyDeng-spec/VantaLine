"""Closed public JSON vocabulary and neutral wire values.

Customer text and business evidence are preserved. Provider/debug envelopes never
cross the member boundary, including when nested inside a historical record.
"""
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit
from .references import References

PUBLIC_FIELDS = frozenset(json.loads(Path(__file__).with_name("public_fields.json").read_text()))
SENSITIVE = re.compile(r"yolo|ultralytics|gemini|doubao|豆包|qwen|千问|通义|codex|agnes|cursor(?:[-_]|\b)|sam[-_ ]?\d|paddleocr|paddlepaddle|dashscope|volcengine|openai|anthropic|claude|gpt[-_ ]?\d|runpod|generativelanguage", re.I)
WORDS = re.compile(r"[a-z0-9_.+-]*(?:yolo|ultralytics|gemini|doubao|qwen|codex|agnes|cursor(?:[-_]|\b)|sam[-_ ]?\d|paddleocr|paddlepaddle|dashscope|volcengine|openai|anthropic|claude|gpt[-_ ]?\d|runpod|generativelanguage)[a-z0-9_.+-]*|豆包|千问|通义", re.I)
WIRE = {
    "yolo_ocr": "vision_text", "yolo": "vision", "qwen_ocr": "text_evidence",
    "yolo_warmup": "vision_warmup", "cursor_image2": "image_service",
    "codex_image_job": "image_job", "codex_image_jobs": "image_jobs",
    "queued_for_codex_image_worker": "queued_for_image_worker",
    "promoted_yolo": "promoted_vision", "codex_comparison_tasks": "smart_comparison_tasks",
}
REVERSE = {value: key for key, value in WIRE.items()}
PUBLIC_ROUTE = "/api/label-check"
INTERNAL_ROUTE = "/api/text-compare-codex"
HIDDEN = frozenset({
    "provider", "provider_label", "provider_status", "provider_result", "provider_response",
    "model", "model_name", "base_model", "model_path", "weights", "weight_path",
    "architecture", "backbone", "model_family", "model_type", "model_size", "model_version", "engine",
    "path", "artifact_path", "metadata_path", "training_log_path", "log_path", "log_tail",
    "diagnostics", "diagnostics_url", "debug", "raw", "raw_json", "raw_response",
    "parsed_response", "response_preview", "normalized_response", "model_audits",
    "model_profiles", "profile_snapshot", "profile_id", "model_profile", "secret_ref",
    "api_key", "masked_key", "api_keys", "active_key_id", "api_key_env", "key_source",
    "password", "password_hash", "api_key_candidates", "image_api_key", "access_token", "refresh_token", "authorization", "credentials", "secrets",
    "base_url", "proxy_url", "proxy_url_raw", "endpoint", "endpoint_url",
    "prompt", "prompt_hash", "prompt_version", "prompt_source", "system_prompt", "raw_model_response", "operational",
    "skill_sha256", "skill_version", "session_id", "executor", "execution_backend",
    "stdout", "stderr", "traceback", "stack", "agent_error", "raw_error",
})
# PLC session identity is a protocol capability, not a provider diagnostic.
# It must remain byte-for-byte intact at the existing station/dispatch endpoints.
PLC_FIELDS = frozenset({"profile_id", "session_id", "station_id", "workstation_id", "client_instance_id", "lease_id", "dispatch_id", "request_id", "operation_id", "binding_token", "nonce", "signature", "fingerprint", "camera_request_id"})
OPAQUE = frozenset({"cursor", "next_cursor", "refresh_cursor", "snapshot_cursor", "before", "after"})
TEXT = frozenset({"reference_text", "actual_text", "expected", "observed", "note", "username", "display_name", "standard_name", "material_code", "original_filename", "filename", "file_name", "name", "label", "description", "task_label", "accessory_names", "accessory_labels", "text", "extracted_text", "ocr_text"})
MAPS = frozenset({"features", "min_counts", "required_accessory_counts", "accessory_counts", "required_counts", "ai_counts", "count_mismatches", "accessory_labels", "accessory_class_map", "class_accessory_map", "accessory_names_by_id", "class_counts", "expected_counts", "actual_counts", "counts", "classes_by_id", "class_map", "task_rules", "by_status", "metrics", "doc_filter_stats", "summary", "bindings", "params", "parameters", "stages", "stage_states", "rule_overrides"})
MODES = frozenset({"variant", "variants", "model_variant", "method", "train_mode", "train_modes", "recommended_train_mode", "optimization_route", "route", "detection_method", "pipeline_method", "mode"})
IDENTIFIERS = frozenset({"id", "task", "before", "after"})
WIRE_KEYS = frozenset({"yolo_warmup", "cursor_image2", "codex_image_job", "codex_image_jobs", "codex_comparison_tasks"})
CUSTOMER_MAPS = MAPS - {"params", "parameters", "stages", "stage_states", "rule_overrides", "bindings", "metrics", "doc_filter_stats", "summary"}
LABEL_MAPS = frozenset({"accessory_labels", "accessory_names_by_id"})


def internal_route(path: str) -> str:
    if path == PUBLIC_ROUTE or path.startswith(PUBLIC_ROUTE + "/"):
        return INTERNAL_ROUTE + path[len(PUBLIC_ROUTE):]
    return path


def neutral_text(value: str) -> str:
    return WORDS.sub("AI 检测", value).replace("YOLO + OCR", "视觉模型＋文字识别")


class Presentation:
    def __init__(self, references: References):
        self.references = references

    def path(self, value: str, *, incoming=False) -> str:
        parsed = urlsplit(value)
        path = internal_route(parsed.path) if incoming else parsed.path.replace(INTERNAL_ROUTE, PUBLIC_ROUTE)
        segments = []
        for segment in path.split("/"):
            text = unquote(segment)
            if incoming:
                text = self.references.decode(text)
            elif SENSITIVE.search(text):
                text = self.references.encode(text)
            segments.append(quote(text, safe="-_.~:@"))
        query = urlencode([(key, self.incoming(item, key) if incoming else self.outgoing(item, field=key))
                           for key, item in parse_qsl(parsed.query, keep_blank_values=True)]) if parsed.query else ""
        return urlunsplit((parsed.scheme, parsed.netloc, "/".join(segments), query, parsed.fragment))

    def incoming(self, value, field=""):
        if isinstance(value, dict):
            return {(REVERSE.get(key, key) if REVERSE.get(key) in WIRE_KEYS and field not in CUSTOMER_MAPS else key):
                    self.incoming(item, "accessory_labels" if field in LABEL_MAPS else key) for key, item in value.items()}
        if isinstance(value, list):
            return [self.incoming(item, field) for item in value]
        if isinstance(value, str) and field not in TEXT:
            if value.startswith(References.PREFIX) and (field in IDENTIFIERS or field.endswith(("_id", "_ids"))):
                return self.references.decode(value)
            if not (field in IDENTIFIERS or field.endswith(("_id", "_ids"))):
                return REVERSE.get(value, value)
        return value

    def outgoing(self, value, *, admin=False, plc=False, field="", mapping=False):
        if isinstance(value, list):
            return [self.outgoing(item, admin=admin, plc=plc, field=field) for item in value]
        if isinstance(value, dict):
            result = {}
            diagnostic = value.get("diagnostics")
            if not admin and isinstance(diagnostic, dict):
                phase = diagnostic.get("phase")
                if phase:
                    result["progress_phase"] = phase if phase in {"queued", "extracting_text", "direct_matching", "mapping_unmatched", "rereading_regions", "transcribing_regions", "verifying_saving", "recognizing", "completed"} else "processing"
                normalized = diagnostic.get("normalized_response")
                if isinstance(normalized, dict) and isinstance(normalized.get("elements"), list) and isinstance(normalized.get("observations"), list):
                    # These are the existing business overlay/evidence links, not
                    # an alternate route to the raw model response envelope.
                    result["match_evidence"] = self.outgoing(
                        {"elements": normalized["elements"], "observations": normalized["observations"]},
                        admin=False, plc=plc, field="match_evidence",
                    )
            model_record = field in {"model", "models", "available_models", "specialized_models", "candidate_models"} or any(key in value for key in ("variant", "is_ai_detection", "uses_ocr"))
            capability = "AI 检测" if value.get("is_ai_detection") else "视觉模型＋文字识别" if value.get("uses_ocr") or value.get("variant") == "yolo_ocr" else "视觉模型"
            for key, item in value.items():
                if not admin:
                    if not (mapping and field in CUSTOMER_MAPS) and key.endswith(("_path", "_dir", "_directory")):
                        continue
                    if not (mapping and field in CUSTOMER_MAPS) and key in HIDDEN and not (plc and key in PLC_FIELDS) and not (key == "model" and isinstance(item, dict)):
                        continue
                    if not mapping and key not in PUBLIC_FIELDS and key not in WIRE and not (plc and key in PLC_FIELDS):
                        continue
                    if not (mapping and field in CUSTOMER_MAPS) and SENSITIVE.search(key) and key not in WIRE and key not in OPAQUE:
                        continue
                public_key = key if mapping else WIRE.get(key, key)
                item_field = "accessory_labels" if field in LABEL_MAPS else key
                if key == "message" and value.get("role") in {"user", "agent", "assistant"}:
                    item_field = "text" if value["role"] == "user" else "message_to_user"
                result[public_key] = self.outgoing(item, admin=admin, plc=plc or key == "plc_sync", field=item_field, mapping=key in MAPS)
                if not admin and model_record and key == "id" and isinstance(item, str) and item:
                    result[public_key] = self.references.encode(item)
                if not admin and model_record and key in {"label", "description", "name", "display_name"} and isinstance(item, str):
                    suffix = self.references.encode(str(value["id"]))[5:13] if value.get("id") else ""
                    result[public_key] = capability + (" · " + suffix if suffix and key != "description" else "")
            if model_record and "id" in value:
                result["is_real_photo"] = str(value["id"]).startswith("trained_train_real_")
            return result
        if not isinstance(value, str):
            return value
        if field in OPAQUE or value.startswith(("data:image/", "data:video/")):
            return value
        if plc and field in PLC_FIELDS:
            return value
        if not admin and value and (field == "model_id" or field.endswith(("_model_id", "model_ids"))):
            return self.references.encode(value)
        if not admin and field in {"model_label", "active_model_label", "candidate_model_label"}:
            return "视觉模型"
        if not admin and field in {"variant", "variants", "model_variant"} and value not in {"ai", "ai_detection", "vision", "vision_text", "yolo", "yolo_ocr"}:
            return "vision"
        if field not in TEXT and not (field in IDENTIFIERS or field.endswith(("_id", "_ids"))) and value in WIRE:
            return WIRE[value]
        if admin or field in TEXT:
            return WIRE.get(value, value) if field in MODES else value
        if field in {"error", "last_error"} and value:
            return "服务暂时不可用，请稍后检查或联系管理员。"
        if value.startswith(("/api/", "/outputs/", "/workspace/")):
            value = value.replace("/workspace/text-compare-codex", "/workspace/label-check")
            return self.path(value)
        if field in MODES:
            return WIRE.get(value, neutral_text(value) if SENSITIVE.search(value) else value)
        if SENSITIVE.search(value):
            if field in IDENTIFIERS or field.endswith(("_id", "_ids")):
                return self.references.encode(value)
            if field in {"error", "detail", "message"}:
                return "服务暂时不可用，请稍后检查或联系管理员。"
            return neutral_text(value)
        return value
