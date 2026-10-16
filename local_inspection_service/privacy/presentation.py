"""Closed public JSON vocabulary and neutral wire values.

Customer text and business evidence are preserved. Provider/debug envelopes never
cross the member boundary, including when nested inside a historical record.
"""
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit
from .references import References
from .identities import PRIVATE_IDENTITIES, neutralize_identities

PUBLIC_FIELDS = frozenset(json.loads(Path(__file__).with_name("public_fields.json").read_text()))
SENSITIVE = re.compile(r"yolo|ultralytics|gemini|doubao|豆包|qwen|千问|通义|codex|agnes|cursor(?:[-_]|\b)|sam[-_ ]?\d|paddleocr|paddlepaddle|dashscope|volcengine|openai|anthropic|claude|gpt[-_ ]?(?:\d|image)|runpod|generativelanguage|seedream|seededit|seedance|dall[-_ ]?e|imagen(?:[-_ ]?\d|\b)", re.I)
WORDS = re.compile(r"[a-z0-9_.+-]*(?:yolo|ultralytics|gemini|doubao|qwen|codex|agnes|cursor(?:[-_]|\b)|sam[-_ ]?\d|paddleocr|paddlepaddle|dashscope|volcengine|openai|anthropic|claude|gpt[-_ ]?(?:\d|image)|runpod|generativelanguage|seedream|seededit|seedance|dall[-_ ]?e|imagen(?:[-_ ]?\d|\b))[a-z0-9_.+-]*|豆包|千问|通义", re.I)
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
    PRIVATE_IDENTITIES,
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
TEXT = frozenset({"reference_text", "actual_text", "expected", "observed", "note", "username", "display_name", "standard_name", "material_code", "version_label", "business_label", "original_filename", "filename", "file_name", "name", "label", "description", "task_label", "accessory_names", "accessory_labels", "text", "extracted_text", "ocr_text"})
MAPS = frozenset({"features", "min_counts", "required_accessory_counts", "accessory_counts", "required_counts", "ai_counts", "count_mismatches", "accessory_labels", "accessory_class_map", "class_accessory_map", "accessory_names_by_id", "class_counts", "expected_counts", "actual_counts", "counts", "classes_by_id", "class_map", "task_rules", "by_status", "metrics", "doc_filter_stats", "summary", "bindings", "params", "parameters", "stages", "stage_states", "rule_overrides"})
MODES = frozenset({"variant", "variants", "model_variant", "method", "train_mode", "train_modes", "recommended_train_mode", "optimization_route", "route", "detection_method", "pipeline_method", "mode"})
WIRE_VALUES = MODES | {"type", "kind", "source", "source_type", "status", "stage", "job_type", "task_type", "job_kind", "phase"}
IDENTIFIERS = frozenset({"id", "task", "before", "after"})
WIRE_KEYS = frozenset({"yolo_warmup", "cursor_image2", "codex_image_job", "codex_image_jobs", "codex_comparison_tasks"})
CUSTOMER_MAPS = MAPS - {"params", "parameters", "stages", "stage_states", "rule_overrides", "bindings", "metrics", "doc_filter_stats", "summary"}
LABEL_MAPS = frozenset({"accessory_labels", "accessory_names_by_id"})
FILE_REFERENCES = frozenset({"source_path"})


def gallery_stem(value):
    name = re.split(r"[\\/]", re.split(r"[?#]", str(value or ""), maxsplit=1)[0])[-1]
    return re.sub(r"\.[^.]+$", "", name).lower()


def rectified_stem(stem):
    return stem.endswith("_rectified") or "_rectified_" in stem or "_manual_rectified" in stem


def internal_route(path: str) -> str:
    if path == PUBLIC_ROUTE or path.startswith(PUBLIC_ROUTE + "/"):
        return INTERNAL_ROUTE + path[len(PUBLIC_ROUTE):]
    return path


def neutral_text(value: str) -> str:
    return WORDS.sub("AI 检测", value).replace("YOLO + OCR", "视觉模型＋文字识别")


class Presentation:
    def __init__(self, references: References):
        self.references = references

    def decode_path(self, path: str, *, strict=False) -> str:
        # ASGI path is already URL-decoded. Do not parse literal ?/# in a
        # customer filename as query/fragment, or quote spaces a second time.
        segments = []
        for segment in path.split("/"):
            if strict and not segment.startswith(References.PREFIX) and SENSITIVE.search(segment):
                raise ValueError("Public reference required")
            segments.append(self.references.decode(segment))
        return internal_route("/".join(segments))

    def path(self, value: str, *, incoming=False, strict=False) -> str:
        parsed = urlsplit(value)
        path = parsed.path if incoming else parsed.path.replace(INTERNAL_ROUTE, PUBLIC_ROUTE)
        segments = []
        for segment in path.split("/"):
            text = unquote(segment)
            if incoming:
                if strict and not text.startswith(References.PREFIX) and SENSITIVE.search(text):
                    raise ValueError("Public reference required")
                text = self.references.decode(text)
            elif SENSITIVE.search(text) or text.startswith(References.PREFIX):
                text = self.references.encode(text)
            segments.append(quote(text, safe="-_.~:@"))
        query = urlencode([(key, self.incoming(item, key, strict=strict) if incoming else self.outgoing(item, field=key))
                           for key, item in parse_qsl(parsed.query, keep_blank_values=True)]) if parsed.query else ""
        resolved = internal_route("/".join(segments)) if incoming else "/".join(segments)
        return urlunsplit((parsed.scheme, parsed.netloc, resolved, query, parsed.fragment))

    def incoming(self, value, field="", *, strict=False):
        if isinstance(value, dict):
            return {(REVERSE.get(key, key) if REVERSE.get(key) in WIRE_KEYS and field not in CUSTOMER_MAPS else key):
                    self.incoming(item, "accessory_labels" if field in CUSTOMER_MAPS else key, strict=strict) for key, item in value.items()}
        if isinstance(value, list):
            return [self.incoming(item, field, strict=strict) for item in value]
        if isinstance(value, str) and field not in TEXT:
            model_reference = field == "model_id" or field.endswith(("_model_id", "model_ids"))
            if strict and value.strip() and (model_reference or field in FILE_REFERENCES) and not value.startswith(References.PREFIX):
                raise ValueError("Public reference required")
            if strict and field in MODES and (value.strip().lower() in WIRE or SENSITIVE.search(value)):
                raise ValueError("Public mode required")
            if value.startswith(References.PREFIX) and (field in IDENTIFIERS or field in FILE_REFERENCES or field.endswith(("_id", "_ids"))):
                return self.references.decode(value)
            if field in WIRE_VALUES and not (field in IDENTIFIERS or field.endswith(("_id", "_ids"))):
                return REVERSE.get(value, value)
        return value

    def outgoing(self, value, *, admin=False, plc=False, field="", mapping=False):
        if admin and field in {"diagnostics", "debug", "raw", "raw_json", "raw_response", "parsed_response", "normalized_response", "profile_snapshot", "model_audits", "provider_response", "provider_result", "provider_status"}:
            return value
        if isinstance(value, list):
            if not admin and field == "gallery":
                stems = [gallery_stem(item.get("source_path")) for item in value if isinstance(item, dict)]
                rectified = [stem for stem in stems if rectified_stem(stem)]
                value = [dict(item, crop_source_eligible=bool(item.get("source_path")) and
                    not rectified_stem(gallery_stem(item.get("source_path"))) and not any(
                        stem == gallery_stem(item.get("source_path")) + "_manual_rectified" or
                        stem.startswith(gallery_stem(item.get("source_path")) + "_manual_rectified_")
                        for stem in rectified)) if isinstance(item, dict) else item for item in value]
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
                    if key == "business_label" and not isinstance(item, str):
                        continue
                    if not (mapping and field in CUSTOMER_MAPS) and key not in FILE_REFERENCES and key.endswith(("_path", "_dir", "_directory")):
                        continue
                    if not (mapping and field in CUSTOMER_MAPS) and key in HIDDEN and not (plc and key in PLC_FIELDS) and not (key == "model" and isinstance(item, dict)):
                        continue
                    if not mapping and key not in PUBLIC_FIELDS and key not in WIRE and not (plc and key in PLC_FIELDS):
                        continue
                    if not (mapping and field in CUSTOMER_MAPS) and SENSITIVE.search(key) and key not in WIRE and key not in OPAQUE:
                        continue
                public_key = key if mapping else WIRE.get(key, key)
                item_field = "accessory_labels" if field in LABEL_MAPS else key
                if not admin and value.get("role") in {"agent", "assistant"} and key in {"message", "reason", "source"}:
                    item = neutralize_identities(item, value.get(PRIVATE_IDENTITIES))
                if key == "message" and value.get("role") in {"user", "agent", "assistant"}:
                    item_field = "text" if value["role"] == "user" else "message_to_user"
                result[public_key] = self.outgoing(item, admin=admin, plc=plc or key == "plc_sync", field=item_field, mapping=key in MAPS)
                if not admin and model_record and key == "id" and isinstance(item, str) and item:
                    result[public_key] = self.references.encode(item)
                if not admin and model_record and key in {"label", "description", "name", "display_name"}:
                    suffix = self.references.encode(str(value["id"]))[5:13] if value.get("id") else ""
                    business = value.get("business_label")
                    result[public_key] = business if key != "description" and isinstance(business, str) and business.strip() else capability + (" · " + suffix if suffix and key != "description" else "")
            if model_record and "id" in value:
                result["is_real_photo"] = str(value["id"]).startswith("trained_train_real_")
            return result
        if not isinstance(value, str):
            return value
        if admin and field in HIDDEN:
            return value
        if field in OPAQUE or value.startswith(("data:image/", "data:video/")):
            return value
        if plc and field in PLC_FIELDS:
            return value
        if not admin and field in FILE_REFERENCES and value:
            return self.references.encode(value)
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
