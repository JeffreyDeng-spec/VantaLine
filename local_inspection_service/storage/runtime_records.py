"""Runtime row adapters shared by PostgreSQL endpoint integration.

The FastAPI runtime still owns business validation and file/blob writes. These
helpers only convert already-accepted in-memory records to the PostgreSQL
metadata rows defined in storage.schema.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


JSON_TEXT_SEPARATORS = (",", ":")


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=JSON_TEXT_SEPARATORS)


def stable_hash(value: Any, *, prefix: str = "") -> str:
    digest = hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}{digest}" if prefix else digest


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def session_key_hash(value: str) -> str:
    text = str(value or "")
    if re.fullmatch(r"[0-9a-f]{64}", text):
        return text
    return text_hash(text)


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def list_from_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def owner_fields(item: Mapping[str, Any]) -> tuple[str, str]:
    owner_user_id = clean_text(item.get("owner_user_id") or item.get("user_id") or item.get("created_by_user_id"))
    owner_username = clean_text(item.get("owner_username") or item.get("username") or item.get("created_by_username"))
    return owner_user_id, owner_username


def status_for(item: Mapping[str, Any], default: str = "legacy") -> str:
    status = clean_text(item.get("status") or item.get("stage") or default).lower()
    return status or default


def source_file_id(path: Path | str) -> str:
    return Path(path).stem


def decoded_json(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def raw_json(row: Mapping[str, Any]) -> dict[str, Any]:
    value = decoded_json(row.get("raw_json"), {})
    return value if isinstance(value, dict) else {}


def row_raw_json_list(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in (raw_json(row) for row in rows) if item]


def config_from_rows(app_config_rows: list[Mapping[str, Any]], accessory_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for row in app_config_rows:
        key = clean_text(row.get("config_key"))
        if key:
            raw_value = row.get("config_value_json")
            config[key] = None if raw_value is None else decoded_json(raw_value, None)
    config["accessories"] = row_raw_json_list(accessory_rows)
    return config


def auth_store_from_rows(user_rows: list[Mapping[str, Any]], session_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    users = row_raw_json_list(user_rows)
    sessions: dict[str, Any] = {}
    for row in session_rows:
        session = raw_json(row)
        session_id_hash = clean_text(session.get("id_hash") or row.get("id_hash"))
        if session_id_hash:
            session.pop("id_hash", None)
            sessions[session_id_hash] = session
    return {"users": users, "sessions": sessions}


def auth_user_rows(store: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for user in store.get("users") if isinstance(store.get("users"), list) else []:
        if not isinstance(user, dict):
            continue
        user_id = clean_text(user.get("id"))
        username = clean_text(user.get("username"))
        if not user_id or not username:
            continue
        rows.append(
            {
                "id": user_id,
                "username": username,
                "display_name": clean_text(user.get("display_name") or username),
                "role": clean_text(user.get("role") or "user"),
                "permissions_json": list_from_value(user.get("permissions")),
                "password_hash": clean_text(user.get("password_hash")),
                "active": bool(user.get("active", True)),
                "created_at": as_int(user.get("created_at")),
                "updated_at": as_int(user.get("updated_at") or user.get("created_at")),
                "raw_json": user,
            }
        )
    return rows


def auth_session_rows(store: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sessions = store.get("sessions") if isinstance(store.get("sessions"), dict) else {}
    for session_id, session in sorted(sessions.items()):
        if not isinstance(session, dict):
            continue
        id_hash = session_key_hash(str(session_id))
        session_copy = dict(session)
        session_copy["id_hash"] = id_hash
        rows.append(
            {
                "id_hash": id_hash,
                "user_id": clean_text(session.get("user_id")),
                "created_at": as_int(session.get("created_at")),
                "last_seen_at": as_int(session.get("last_seen_at") or session.get("created_at")),
                "expires_at": as_int(session.get("expires_at")),
                "raw_json": session_copy,
            }
        )
    return rows


def app_config_rows(config: Mapping[str, Any], *, updated_at: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, value in sorted(config.items()):
        if key == "accessories":
            continue
        rows.append(
            {
                "config_key": str(key),
                "config_value_json": value,
                "source_file": "config.json",
                "updated_at": updated_at,
            }
        )
    return rows


def accessory_row(item: Mapping[str, Any]) -> dict[str, Any] | None:
    row_id = clean_text(item.get("id") or item.get("accessory_id") or item.get("uid"))
    if not row_id:
        row_id = stable_hash(
            {"class_id": clean_text(item.get("class_id")), "name": clean_text(item.get("name") or item.get("english_name"))},
            prefix="acc_legacy_",
        )[:23]
    if not row_id:
        return None
    owner_user_id, owner_username = owner_fields(item)
    return {
        "id": row_id,
        "class_id": clean_text(item.get("class_id")),
        "name": clean_text(item.get("name") or item.get("english_name")),
        "status": status_for(item, default="active"),
        "material_type": clean_text(item.get("material_type")),
        "owner_user_id": owner_user_id,
        "owner_username": owner_username,
        "created_at": as_int(item.get("created_at")),
        "updated_at": as_int(item.get("updated_at") or item.get("created_at")),
        "raw_json": dict(item),
    }


def accessory_rows(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    accessories = config.get("accessories") if isinstance(config.get("accessories"), list) else []
    for item in accessories:
        if isinstance(item, dict):
            row = accessory_row(item)
            if row:
                rows.append(row)
    return rows


def accessory_candidate_row(candidate: Mapping[str, Any], *, fallback_id: str = "") -> dict[str, Any] | None:
    row_id = clean_text(candidate.get("id") or candidate.get("candidate_id") or fallback_id)
    if not row_id:
        return None
    owner_user_id, owner_username = owner_fields(candidate)
    return {
        "id": row_id,
        "name": clean_text(candidate.get("name")),
        "class_id": clean_text(candidate.get("class_id")),
        "status": status_for(candidate, default="legacy"),
        "owner_user_id": owner_user_id,
        "owner_username": owner_username,
        "created_at": as_int(candidate.get("created_at")),
        "updated_at": as_int(candidate.get("updated_at") or candidate.get("created_at")),
        "raw_json": dict(candidate),
    }


def ai_detection_task_row(task: Mapping[str, Any]) -> dict[str, Any] | None:
    row_id = clean_text(task.get("id") or task.get("task_id"))
    if not row_id:
        return None
    owner_user_id, owner_username = owner_fields(task)
    return {
        "id": row_id,
        "name": clean_text(task.get("name") or task.get("label")),
        "status": status_for(task, default="active"),
        "source": clean_text(task.get("source")),
        "owner_user_id": owner_user_id,
        "owner_username": owner_username,
        "created_at": as_int(task.get("created_at")),
        "updated_at": as_int(task.get("updated_at") or task.get("created_at")),
        "raw_json": dict(task),
    }


def data_analysis_record_row(record: Mapping[str, Any]) -> dict[str, Any] | None:
    row_id = clean_text(record.get("record_id") or record.get("id"))
    if not row_id:
        return None
    task = record.get("task") if isinstance(record.get("task"), dict) else {}
    source_image = record.get("source_image") if isinstance(record.get("source_image"), dict) else {}
    owner_user_id, owner_username = owner_fields(record)
    return {
        "record_id": row_id,
        "task_id": clean_text(task.get("id") or record.get("task_id")),
        "owner_user_id": owner_user_id,
        "owner_username": owner_username,
        "created_at": as_int(record.get("created_at")),
        "updated_at": as_int(record.get("updated_at") or record.get("created_at")),
        "image_path": clean_text(source_image.get("path") or source_image.get("url") or record.get("image_url")),
        "raw_json": dict(record),
    }


def training_task_row(task: Mapping[str, Any], *, fallback_id: str = "") -> dict[str, Any] | None:
    row_id = clean_text(task.get("task_id") or task.get("id") or task.get("job_id") or fallback_id)
    if not row_id:
        return None
    owner_user_id, owner_username = owner_fields(task)
    return {
        "id": row_id,
        "job_id": clean_text(task.get("job_id") or row_id),
        "action": clean_text(task.get("action")),
        "status": status_for(task, default="legacy"),
        "queue_kind": clean_text(task.get("queue_kind")),
        "owner_user_id": owner_user_id,
        "owner_username": owner_username,
        "created_at": as_int(task.get("created_at") or task.get("started_at")),
        "updated_at": as_int(task.get("updated_at") or task.get("completed_at") or task.get("started_at") or task.get("created_at")),
        "raw_json": dict(task),
    }


def pipeline_task_row(task: Mapping[str, Any]) -> dict[str, Any] | None:
    row_id = clean_text(task.get("id") or task.get("task_id"))
    if not row_id:
        return None
    owner_user_id, owner_username = owner_fields(task)
    return {
        "id": row_id,
        "name": clean_text(task.get("name")),
        "status": status_for(task, default="legacy"),
        "stage": clean_text(task.get("stage")),
        "owner_user_id": owner_user_id,
        "owner_username": owner_username,
        "created_at": as_int(task.get("created_at")),
        "updated_at": as_int(task.get("updated_at") or task.get("created_at")),
        "raw_json": dict(task),
    }


def incoming_text_reference_row(reference: Mapping[str, Any]) -> dict[str, Any] | None:
    row_id = clean_text(reference.get("id"))
    if not row_id:
        return None
    owner_user_id, owner_username = owner_fields(reference)
    return {
        "id": row_id,
        "task_id": clean_text(reference.get("task_id")),
        "version_label": clean_text(reference.get("version_label")),
        "material_code": clean_text(reference.get("material_code")),
        "status": status_for(reference, default="draft"),
        "owner_user_id": owner_user_id,
        "owner_username": owner_username,
        "source_path": clean_text(reference.get("source_path")),
        "source_sha256": clean_text(reference.get("source_sha256")),
        "created_at": as_int(reference.get("created_at")),
        "activated_at": as_int(reference.get("activated_at")),
        "raw_json": dict(reference),
    }


def incoming_text_inspection_row(inspection: Mapping[str, Any]) -> dict[str, Any] | None:
    row_id = clean_text(inspection.get("id"))
    if not row_id:
        return None
    owner_user_id, owner_username = owner_fields(inspection)
    return {
        "id": row_id,
        "capture_id": clean_text(inspection.get("capture_id")),
        "task_id": clean_text(inspection.get("task_id")),
        "reference_id": clean_text(inspection.get("reference_id")),
        "material_code": clean_text(inspection.get("material_code")),
        "status": status_for(inspection, default="processing"),
        "auto_decision": clean_text(inspection.get("auto_decision")),
        "final_decision": clean_text(inspection.get("final_decision")),
        "owner_user_id": owner_user_id,
        "owner_username": owner_username,
        "source_path": clean_text(inspection.get("source_path")),
        "source_sha256": clean_text(inspection.get("source_sha256")),
        "created_at": as_int(inspection.get("created_at")),
        "updated_at": as_int(inspection.get("updated_at") or inspection.get("created_at")),
        "raw_json": dict(inspection),
    }


def audit_event_row(event: Mapping[str, Any]) -> dict[str, Any] | None:
    row_id = clean_text(event.get("id"))
    if not row_id:
        return None
    return {
        "id": row_id,
        "event_type": clean_text(event.get("event_type")),
        "created_at": as_int(event.get("created_at")),
        "actor_user_id": clean_text(event.get("actor_user_id")),
        "payload_json": event.get("payload") if isinstance(event.get("payload"), dict) else {},
    }


def pipeline_state_rows(state: Mapping[str, Any], *, updated_at: int) -> list[dict[str, Any]]:
    return [
        {"state_key": str(key), "state_value_json": value, "updated_at": updated_at}
        for key, value in sorted(state.items())
    ]


def pipeline_state_from_rows(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for row in rows:
        key = clean_text(row.get("state_key"))
        if key:
            state[key] = decoded_json(row.get("state_value_json"), [])
    return state


def auto_optimize_state_row(state: Mapping[str, Any], *, fallback_id: str = "") -> dict[str, Any] | None:
    row_id = clean_text(state.get("task_id") or state.get("id") or fallback_id)
    if not row_id:
        return None
    owner_user_id, owner_username = owner_fields(state)
    return {
        "task_id": row_id,
        "status": status_for(state, default="legacy"),
        "owner_user_id": owner_user_id,
        "owner_username": owner_username,
        "created_at": as_int(state.get("created_at")),
        "updated_at": as_int(state.get("updated_at") or state.get("created_at")),
        "raw_json": dict(state),
    }


def file_stem_identifier(path: Path | str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.@-]+", "_", Path(path).stem).strip("_")
