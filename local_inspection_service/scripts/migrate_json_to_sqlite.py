#!/usr/bin/env python3
"""Dry-run VantaLine JSON metadata into a local SQLite shadow database.

This script is PR1-only migration tooling. It does not switch the runtime data
store and does not import local_inspection_service.server.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from local_inspection_service.storage.db import apply_schema, connect_sqlite, table_counts
from local_inspection_service.storage.json_loader import JsonSource, SourceInventory, load_inventory
from local_inspection_service.storage.repositories import insert_row, insert_rows
from local_inspection_service.storage.schema import (
    ACTIVE_RUNTIME_STATUSES,
    HISTORICAL_RUNTIME_STATUSES,
    OWNER_REQUIRED_TABLES,
    SCHEMA_VERSION,
    SOURCE_TO_TABLE_MAPPING,
    TABLES,
    is_active_status,
)

JSON_TEXT_SEPARATORS = (",", ":")
PATH_FIELDS = (
    "source_files",
    "original_source_files",
    "normalized_assets",
    "ai_profile_reference_files",
    "thumbnails",
    "video_reference_frames",
    "image_url",
    "source_image",
    "source_path",
    "dataset_dir",
    "dataset_yaml",
    "manifest_path",
    "training_log_path",
    "training_run_dir",
)

RUNTIME_DEPENDENT_PATH_FIELDS = frozenset(
    {
        "source_files",
        "original_source_files",
        "normalized_assets",
        "image_url",
        "source_image",
        "source_path",
        "dataset_dir",
        "dataset_yaml",
        "manifest_path",
        "training_log_path",
        "training_run_dir",
    }
)


class MigrationState:
    def __init__(self, *, inventory: SourceInventory, allow_legacy_id_repair: bool) -> None:
        self.inventory = inventory
        self.allow_legacy_id_repair = allow_legacy_id_repair
        self.rows: dict[str, list[dict[str, Any]]] = {table.name: [] for table in TABLES}
        self.source_errors: list[dict[str, Any]] = []
        self.source_warnings: list[dict[str, Any]] = []
        self.blocking_errors: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.legacy_repairs: list[dict[str, Any]] = []
        self.duplicate_counts: dict[str, int] = {}
        self.missing_owner_counts: dict[str, int] = {}
        self.orphan_counts: dict[str, int] = {}
        self.missing_path_counts: dict[str, int] = {}
        self.missing_path_samples: list[dict[str, str]] = []
        self.pending_links: list[dict[str, str]] = []

    def add_blocker(self, code: str, *, table: str, source: str, detail: str) -> None:
        self.blocking_errors.append({"code": code, "table": table, "source": source, "detail": detail})

    def add_warning(self, code: str, *, table: str, source: str, detail: str) -> None:
        self.warnings.append({"code": code, "table": table, "source": source, "detail": detail})

    def count_missing_owner(self, table: str, source: str, row_id: str, status: str) -> None:
        self.missing_owner_counts[table] = self.missing_owner_counts.get(table, 0) + 1
        policy = "active_missing_owner" if is_active_status(status) else "legacy_missing_owner"
        self.add_warning(policy, table=table, source=source, detail=row_id)

    def add_link(
        self,
        *,
        from_table: str,
        source: str,
        row_id: str,
        status: str,
        field: str,
        target_table: str,
        target_id: str,
    ) -> None:
        clean_target = clean_text(target_id)
        if not clean_target:
            return
        self.pending_links.append(
            {
                "from_table": from_table,
                "source": source,
                "row_id": row_id,
                "status": status,
                "field": field,
                "target_table": target_table,
                "target_id": clean_target,
            }
        )

    def count_orphan(self, table: str, source: str, detail: str, *, status: str) -> None:
        self.orphan_counts[table] = self.orphan_counts.get(table, 0) + 1
        if is_active_status(status):
            self.add_blocker("active_orphan_reference", table=table, source=source, detail=detail)
        else:
            self.add_warning("historical_orphan_reference", table=table, source=source, detail=detail)

    def count_missing_path(
        self,
        table: str,
        source: str,
        path: str,
        *,
        parent_table: str,
        parent_id: str,
        field: str,
        status: str,
    ) -> None:
        self.missing_path_counts[table] = self.missing_path_counts.get(table, 0) + 1
        if len(self.missing_path_samples) < 20:
            self.missing_path_samples.append({"table": table, "source": source, "path": path, "status": status})
        detail = f"{parent_table}:{parent_id}.{field} -> {path}"
        if is_active_status(status) and field in RUNTIME_DEPENDENT_PATH_FIELDS:
            self.add_blocker("active_missing_path", table=table, source=source, detail=detail)
        else:
            self.add_warning("historical_missing_path", table=table, source=source, detail=detail)


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=JSON_TEXT_SEPARATORS)


def stable_hash(value: Any, *, prefix: str = "") -> str:
    digest = hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}{digest}" if prefix else digest


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def slug_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", clean_text(value).lower()).strip("_")


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


def find_source(inventory: SourceInventory, rel_path: str) -> JsonSource | None:
    for source in inventory.json_sources:
        if source.rel_path == rel_path:
            return source
    return None


def legacy_accessory_id(item: dict[str, Any]) -> str:
    basis = {
        "class_id": clean_text(item.get("class_id")),
        "name": clean_text(item.get("name") or item.get("english_name")),
    }
    return stable_hash(basis, prefix="acc_legacy_")[:23]


def source_file_id(rel_path: str) -> str:
    return Path(rel_path).stem


def resolve_record_id(
    state: MigrationState,
    *,
    table: str,
    source: str,
    item: dict[str, Any],
    keys: tuple[str, ...],
    fallback_id: str = "",
    repair_kind: str = "",
) -> str:
    for key in keys:
        value = clean_text(item.get(key))
        if value:
            return value
    if fallback_id:
        return fallback_id
    if repair_kind == "accessory":
        repaired = legacy_accessory_id(item)
        detail = {
            "table": table,
            "source": source,
            "repaired_id": repaired,
            "source_fields": {
                "class_id": clean_text(item.get("class_id")),
                "name": clean_text(item.get("name") or item.get("english_name")),
            },
        }
        if state.allow_legacy_id_repair:
            state.legacy_repairs.append(detail)
            return repaired
        state.add_blocker("legacy_id_repair_required", table=table, source=source, detail=stable_json(detail["source_fields"]))
        return ""
    state.add_blocker("missing_primary_key", table=table, source=source, detail=stable_json({"keys": keys}))
    return ""


def owner_fields(item: dict[str, Any]) -> tuple[str, str]:
    owner_user_id = clean_text(item.get("owner_user_id") or item.get("user_id") or item.get("created_by_user_id"))
    owner_username = clean_text(item.get("owner_username") or item.get("username") or item.get("created_by_username"))
    return owner_user_id, owner_username


def status_for(item: dict[str, Any], default: str = "legacy") -> str:
    status = clean_text(item.get("status") or item.get("stage") or default).lower()
    return status or default


def record_owner_policy(state: MigrationState, *, table: str, source: str, row_id: str, item: dict[str, Any], status: str) -> tuple[str, str]:
    owner_user_id, owner_username = owner_fields(item)
    if table in OWNER_REQUIRED_TABLES and not owner_user_id and not owner_username:
        state.count_missing_owner(table, source, row_id, status)
    return owner_user_id, owner_username


def normalized_path_values(value: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for nested_key in ("path", "url", "filename", "source_path", "canonical", "thumbnail", "preview_url"):
            nested = value.get(nested_key)
            if isinstance(nested, str) and nested.strip():
                paths.append(nested.strip())
        for nested in value.values():
            if isinstance(nested, (list, tuple)):
                paths.extend(normalized_path_values(list(nested)))
    elif isinstance(value, list):
        for item in value:
            paths.extend(normalized_path_values(item))
    elif isinstance(value, str) and value.strip():
        paths.append(value.strip())
    return paths


def looks_like_local_file(path_text: str) -> bool:
    if not path_text:
        return False
    lowered = path_text.lower()
    if lowered.startswith(("http://", "https://", "data:")):
        return False
    if path_text.startswith("/api/"):
        return False
    return any(token in path_text for token in ("/", "\\", ".")) or lowered.startswith(("uploads", "outputs", "normalized_assets", "data/"))


def resolve_local_path(inventory: SourceInventory, path_text: str) -> Path | None:
    if not looks_like_local_file(path_text):
        return None
    path_text = path_text.replace("\\", "/")
    if path_text.startswith("/outputs/"):
        return inventory.data_dir / path_text.lstrip("/")
    if path_text.startswith("/data/"):
        return inventory.service_root / path_text.lstrip("/")
    path = Path(path_text)
    if path.is_absolute():
        return path
    if path_text.startswith("data/"):
        return inventory.service_root / path_text
    return inventory.data_dir / path_text


def add_asset_rows(
    state: MigrationState,
    *,
    parent_table: str,
    parent_id: str,
    source: str,
    status: str,
    item: dict[str, Any],
) -> None:
    for field in PATH_FIELDS:
        if field not in item:
            continue
        for index, path_text in enumerate(normalized_path_values(item.get(field))):
            if not looks_like_local_file(path_text):
                continue
            path = resolve_local_path(state.inventory, path_text)
            exists = bool(path and path.exists())
            if not exists:
                state.count_missing_path(
                    "accessory_assets",
                    source,
                    path_text,
                    parent_table=parent_table,
                    parent_id=parent_id,
                    field=field,
                    status=status,
                )
            state.rows["accessory_assets"].append(
                {
                    "id": stable_hash(
                        {"parent_table": parent_table, "parent_id": parent_id, "field": field, "index": index, "path": path_text},
                        prefix="asset_",
                    )[:24],
                    "parent_table": parent_table,
                    "parent_id": parent_id,
                    "asset_kind": field,
                    "source_field": field,
                    "path": path_text,
                    "path_exists": 1 if exists else 0,
                    "raw_json": stable_json({"path": path_text}),
                }
            )


def add_auth_rows(state: MigrationState, source: JsonSource) -> None:
    if not isinstance(source.data, dict):
        state.add_blocker("invalid_shape", table="users", source=source.rel_path, detail="auth root must be object")
        return
    users = source.data.get("users") if isinstance(source.data.get("users"), list) else []
    sessions = source.data.get("sessions") if isinstance(source.data.get("sessions"), dict) else {}
    for user in users:
        if not isinstance(user, dict):
            continue
        user_id = resolve_record_id(state, table="users", source=source.rel_path, item=user, keys=("id",))
        username = clean_text(user.get("username"))
        if not user_id or not username:
            state.add_blocker("missing_user_identity", table="users", source=source.rel_path, detail=stable_json({"id": user_id, "username": username}))
            continue
        state.rows["users"].append(
            {
                "id": user_id,
                "username": username,
                "display_name": clean_text(user.get("display_name") or username),
                "role": clean_text(user.get("role") or "user"),
                "permissions_json": stable_json(list_from_value(user.get("permissions"))),
                "password_hash": clean_text(user.get("password_hash")),
                "active": 1 if bool(user.get("active", True)) else 0,
                "created_at": as_int(user.get("created_at")),
                "updated_at": as_int(user.get("updated_at") or user.get("created_at")),
                "raw_json": stable_json(user),
            }
        )
    user_ids = {row["id"] for row in state.rows["users"]}
    for session_id, session in sorted(sessions.items()):
        if not isinstance(session, dict):
            continue
        user_id = clean_text(session.get("user_id"))
        if user_id and user_id not in user_ids:
            session_status = "active" if as_int(session.get("expires_at")) > int(time.time()) else "completed"
            state.count_orphan("auth_sessions", source.rel_path, f"user_id={user_id}", status=session_status)
        redacted_session = dict(session)
        redacted_session["id_hash"] = text_hash(str(session_id))
        state.rows["auth_sessions"].append(
            {
                "id_hash": text_hash(str(session_id)),
                "user_id": user_id,
                "created_at": as_int(session.get("created_at")),
                "last_seen_at": as_int(session.get("last_seen_at") or session.get("created_at")),
                "expires_at": as_int(session.get("expires_at")),
                "raw_json": stable_json(redacted_session),
            }
        )


def add_config_rows(state: MigrationState, source: JsonSource) -> None:
    if not isinstance(source.data, dict):
        state.add_blocker("invalid_shape", table="app_config", source=source.rel_path, detail="config root must be object")
        return
    now = as_int(source.path.stat().st_mtime)
    for key, value in sorted(source.data.items()):
        if key == "accessories":
            continue
        state.rows["app_config"].append(
            {
                "config_key": key,
                "config_value_json": stable_json(value),
                "source_file": source.rel_path,
                "updated_at": now,
            }
        )
    accessories = source.data.get("accessories") if isinstance(source.data.get("accessories"), list) else []
    for item in accessories:
        if not isinstance(item, dict):
            continue
        row_id = resolve_record_id(
            state,
            table="accessories",
            source=source.rel_path,
            item=item,
            keys=("id", "accessory_id", "uid"),
            repair_kind="accessory",
        )
        if not row_id:
            continue
        status = status_for(item, default="active")
        owner_user_id, owner_username = record_owner_policy(
            state, table="accessories", source=source.rel_path, row_id=row_id, item=item, status=status
        )
        state.rows["accessories"].append(
            {
                "id": row_id,
                "class_id": clean_text(item.get("class_id")),
                "name": clean_text(item.get("name") or item.get("english_name")),
                "status": status,
                "material_type": clean_text(item.get("material_type")),
                "owner_user_id": owner_user_id,
                "owner_username": owner_username,
                "created_at": as_int(item.get("created_at")),
                "updated_at": as_int(item.get("updated_at") or item.get("created_at")),
                "raw_json": stable_json(item),
            }
        )
        add_asset_rows(state, parent_table="accessories", parent_id=row_id, source=source.rel_path, status=status, item=item)


def add_candidate_row(state: MigrationState, source: JsonSource) -> None:
    if source.error:
        state.source_errors.append({"source": source.rel_path, "error": source.error})
        return
    if not isinstance(source.data, dict):
        state.add_blocker("invalid_shape", table="accessory_candidates", source=source.rel_path, detail="candidate must be object")
        return
    item = source.data
    row_id = resolve_record_id(
        state,
        table="accessory_candidates",
        source=source.rel_path,
        item=item,
        keys=("id", "candidate_id"),
        fallback_id=source_file_id(source.rel_path),
    )
    status = status_for(item, default="legacy")
    owner_user_id, owner_username = record_owner_policy(
        state, table="accessory_candidates", source=source.rel_path, row_id=row_id, item=item, status=status
    )
    state.rows["accessory_candidates"].append(
        {
            "id": row_id,
            "name": clean_text(item.get("name")),
            "class_id": clean_text(item.get("class_id")),
            "status": status,
            "owner_user_id": owner_user_id,
            "owner_username": owner_username,
            "created_at": as_int(item.get("created_at")),
            "updated_at": as_int(item.get("updated_at") or item.get("created_at")),
            "raw_json": stable_json(item),
        }
    )
    add_asset_rows(state, parent_table="accessory_candidates", parent_id=row_id, source=source.rel_path, status=status, item=item)


def add_ai_detection_rows(state: MigrationState, source: JsonSource) -> None:
    if not isinstance(source.data, dict):
        state.add_blocker("invalid_shape", table="ai_detection_tasks", source=source.rel_path, detail="AI tasks root must be object")
        return
    tasks = source.data.get("tasks") if isinstance(source.data.get("tasks"), list) else []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        row_id = resolve_record_id(state, table="ai_detection_tasks", source=source.rel_path, item=task, keys=("id", "task_id"))
        if not row_id:
            continue
        status = status_for(task, default="active")
        owner_user_id, owner_username = record_owner_policy(
            state, table="ai_detection_tasks", source=source.rel_path, row_id=row_id, item=task, status=status
        )
        state.rows["ai_detection_tasks"].append(
            {
                "id": row_id,
                "name": clean_text(task.get("name") or task.get("label")),
                "status": status,
                "source": clean_text(task.get("source")),
                "owner_user_id": owner_user_id,
                "owner_username": owner_username,
                "created_at": as_int(task.get("created_at")),
                "updated_at": as_int(task.get("updated_at") or task.get("created_at")),
                "raw_json": stable_json(task),
            }
        )
        for accessory_id in list_from_value(task.get("selected_accessory_ids")):
            state.add_link(
                from_table="ai_detection_tasks",
                source=source.rel_path,
                row_id=row_id,
                status=status,
                field="selected_accessory_ids",
                target_table="accessories",
                target_id=clean_text(accessory_id),
            )


def add_data_analysis_rows(state: MigrationState, source: JsonSource) -> None:
    records: list[Any]
    if isinstance(source.data, dict):
        records = source.data.get("records") if isinstance(source.data.get("records"), list) else []
    elif isinstance(source.data, list):
        records = source.data
    else:
        state.add_blocker("invalid_shape", table="data_analysis_records", source=source.rel_path, detail="records must be list/object")
        return
    for record in records:
        if not isinstance(record, dict):
            continue
        row_id = resolve_record_id(state, table="data_analysis_records", source=source.rel_path, item=record, keys=("record_id", "id"))
        if not row_id:
            continue
        task = record.get("task") if isinstance(record.get("task"), dict) else {}
        source_image = record.get("source_image") if isinstance(record.get("source_image"), dict) else {}
        status = status_for(record, default="completed")
        owner_user_id, owner_username = record_owner_policy(
            state, table="data_analysis_records", source=source.rel_path, row_id=row_id, item=record, status=status
        )
        image_path = clean_text(source_image.get("path") or source_image.get("url") or record.get("image_url"))
        task_id = clean_text(task.get("id") or record.get("task_id"))
        state.rows["data_analysis_records"].append(
            {
                "record_id": row_id,
                "task_id": task_id,
                "owner_user_id": owner_user_id,
                "owner_username": owner_username,
                "created_at": as_int(record.get("created_at")),
                "updated_at": as_int(record.get("updated_at") or record.get("created_at")),
                "image_path": image_path,
                "raw_json": stable_json(record),
            }
        )
        state.add_link(
            from_table="data_analysis_records",
            source=source.rel_path,
            row_id=row_id,
            status=status,
            field="task.id",
            target_table="ai_detection_tasks",
            target_id=task_id,
        )
        if image_path:
            add_asset_rows(
                state,
                parent_table="data_analysis_records",
                parent_id=row_id,
                source=source.rel_path,
                status=status,
                item={"image_url": image_path},
            )


def add_training_task_row(state: MigrationState, source: JsonSource) -> None:
    if source.error:
        state.source_errors.append({"source": source.rel_path, "error": source.error})
        return
    if not isinstance(source.data, dict):
        state.add_blocker("invalid_shape", table="training_tasks", source=source.rel_path, detail="training task must be object")
        return
    item = source.data
    row_id = resolve_record_id(
        state,
        table="training_tasks",
        source=source.rel_path,
        item=item,
        keys=("task_id", "id", "job_id"),
        fallback_id=source_file_id(source.rel_path),
    )
    status = status_for(item, default="legacy")
    owner_user_id, owner_username = record_owner_policy(
        state, table="training_tasks", source=source.rel_path, row_id=row_id, item=item, status=status
    )
    state.rows["training_tasks"].append(
        {
            "id": row_id,
            "job_id": clean_text(item.get("job_id") or row_id),
            "action": clean_text(item.get("action")),
            "status": status,
            "queue_kind": clean_text(item.get("queue_kind")),
            "owner_user_id": owner_user_id,
            "owner_username": owner_username,
            "created_at": as_int(item.get("created_at") or item.get("started_at")),
            "updated_at": as_int(item.get("updated_at") or item.get("completed_at") or item.get("started_at") or item.get("created_at")),
            "raw_json": stable_json(item),
        }
    )
    add_asset_rows(state, parent_table="training_tasks", parent_id=row_id, source=source.rel_path, status=status, item=item)


def add_pipeline_rows(state: MigrationState, source: JsonSource) -> None:
    if source.rel_path == "pipeline_state.json":
        if not isinstance(source.data, dict):
            state.add_blocker("invalid_shape", table="pipeline_state", source=source.rel_path, detail="pipeline state must be object")
            return
        now = as_int(source.path.stat().st_mtime)
        for key, value in sorted(source.data.items()):
            state.rows["pipeline_state"].append({"state_key": key, "state_value_json": stable_json(value), "updated_at": now})
        for accessory_id in list_from_value(source.data.get("accessory_ids")):
            state.add_link(
                from_table="pipeline_state",
                source=source.rel_path,
                row_id="pipeline_state",
                status="active",
                field="accessory_ids",
                target_table="accessories",
                target_id=clean_text(accessory_id),
            )
        for candidate_id in list_from_value(source.data.get("pending_candidate_ids")):
            state.add_link(
                from_table="pipeline_state",
                source=source.rel_path,
                row_id="pipeline_state",
                status="active",
                field="pending_candidate_ids",
                target_table="accessory_candidates",
                target_id=clean_text(candidate_id),
            )
        return
    tasks: list[Any]
    if isinstance(source.data, list):
        tasks = source.data
    elif isinstance(source.data, dict):
        tasks = source.data.get("tasks") if isinstance(source.data.get("tasks"), list) else []
    else:
        state.add_blocker("invalid_shape", table="pipeline_tasks", source=source.rel_path, detail="pipeline tasks must be list/object")
        return
    for task in tasks:
        if not isinstance(task, dict):
            continue
        row_id = resolve_record_id(state, table="pipeline_tasks", source=source.rel_path, item=task, keys=("id", "task_id"))
        if not row_id:
            continue
        status = status_for(task, default="legacy")
        owner_user_id, owner_username = record_owner_policy(
            state, table="pipeline_tasks", source=source.rel_path, row_id=row_id, item=task, status=status
        )
        state.rows["pipeline_tasks"].append(
            {
                "id": row_id,
                "name": clean_text(task.get("name")),
                "status": status,
                "stage": clean_text(task.get("stage")),
                "owner_user_id": owner_user_id,
                "owner_username": owner_username,
                "created_at": as_int(task.get("created_at")),
                "updated_at": as_int(task.get("updated_at") or task.get("created_at")),
                "raw_json": stable_json(task),
            }
        )
        for field in ("training_task_id", "samples_task_id", "dataset_id"):
            state.add_link(
                from_table="pipeline_tasks",
                source=source.rel_path,
                row_id=row_id,
                status=status,
                field=field,
                target_table="training_tasks",
                target_id=clean_text(task.get(field)),
            )
        for accessory_id in list_from_value(task.get("accessory_ids")):
            state.add_link(
                from_table="pipeline_tasks",
                source=source.rel_path,
                row_id=row_id,
                status=status,
                field="accessory_ids",
                target_table="accessories",
                target_id=clean_text(accessory_id),
            )


def add_auto_optimize_row(state: MigrationState, source: JsonSource) -> None:
    if source.error:
        state.source_errors.append({"source": source.rel_path, "error": source.error})
        return
    if not isinstance(source.data, dict):
        state.add_blocker("invalid_shape", table="auto_optimize_states", source=source.rel_path, detail="auto optimize state must be object")
        return
    item = source.data
    row_id = resolve_record_id(
        state,
        table="auto_optimize_states",
        source=source.rel_path,
        item=item,
        keys=("task_id", "id"),
        fallback_id=source_file_id(source.rel_path),
    )
    status = status_for(item, default="legacy")
    owner_user_id, owner_username = record_owner_policy(
        state, table="auto_optimize_states", source=source.rel_path, row_id=row_id, item=item, status=status
    )
    state.rows["auto_optimize_states"].append(
        {
            "task_id": row_id,
            "status": status,
            "owner_user_id": owner_user_id,
            "owner_username": owner_username,
            "created_at": as_int(item.get("created_at")),
            "updated_at": as_int(item.get("updated_at") or item.get("created_at")),
            "raw_json": stable_json(item),
        }
    )


def collect_rows(inventory: SourceInventory, *, allow_legacy_id_repair: bool) -> MigrationState:
    state = MigrationState(inventory=inventory, allow_legacy_id_repair=allow_legacy_id_repair)
    for source in inventory.json_sources:
        if source.parse_warning:
            state.source_warnings.append({"source": source.rel_path, "warning": source.parse_warning})
        if source.error:
            state.source_errors.append({"source": source.rel_path, "error": source.error})
            continue
        if source.rel_path == "auth.json":
            add_auth_rows(state, source)
        elif source.rel_path == "config.json":
            add_config_rows(state, source)
        elif source.rel_path == "ai_detection_tasks.json":
            add_ai_detection_rows(state, source)
        elif source.rel_path == "data_analysis_records.json":
            add_data_analysis_rows(state, source)
        elif source.rel_path in {"pipeline_state.json", "pipeline_tasks.json"}:
            add_pipeline_rows(state, source)
        elif source.rel_path.startswith("accessory_candidates/"):
            add_candidate_row(state, source)
        elif source.rel_path.startswith("training_tasks/"):
            add_training_task_row(state, source)
        elif source.rel_path.startswith("auto_optimize/"):
            add_auto_optimize_row(state, source)
    evaluate_links(state)
    detect_duplicates(state)
    return state


def table_identifiers(state: MigrationState, table_name: str) -> set[str]:
    identifiers: set[str] = set()
    for row in state.rows.get(table_name, []):
        if table_name == "accessories":
            row_id = clean_text(row.get("id"))
            class_id = clean_text(row.get("class_id"))
            name = clean_text(row.get("name"))
            identifiers.update(value for value in (row_id, class_id, f"{class_id}_{slug_text(name)}" if class_id and name else "") if value)
        elif table_name == "training_tasks":
            identifiers.update(value for value in (clean_text(row.get("id")), clean_text(row.get("job_id"))) if value)
        elif table_name == "accessory_candidates":
            identifiers.add(clean_text(row.get("id")))
        elif table_name == "ai_detection_tasks":
            identifiers.add(clean_text(row.get("id")))
        else:
            identifiers.update(clean_text(value) for value in row.values() if isinstance(value, str))
    return {value for value in identifiers if value}


def evaluate_links(state: MigrationState) -> None:
    target_sets: dict[str, set[str]] = {}
    for link in state.pending_links:
        target_table = link["target_table"]
        if target_table not in target_sets:
            target_sets[target_table] = table_identifiers(state, target_table)
        if link["target_id"] not in target_sets[target_table]:
            detail = (
                f"{link['from_table']}:{link['row_id']}.{link['field']} -> "
                f"{target_table}:{link['target_id']}"
            )
            state.count_orphan(link["from_table"], link["source"], detail, status=link["status"])


def detect_duplicates(state: MigrationState) -> None:
    primary_key = {
        "schema_migrations": "version",
        "users": "id",
        "auth_sessions": "id_hash",
        "app_config": "config_key",
        "accessories": "id",
        "accessory_assets": "id",
        "accessory_candidates": "id",
        "ai_detection_tasks": "id",
        "data_analysis_records": "record_id",
        "training_tasks": "id",
        "pipeline_tasks": "id",
        "pipeline_state": "state_key",
        "auto_optimize_states": "task_id",
        "audit_events": "id",
    }
    for table, rows in state.rows.items():
        key = primary_key.get(table)
        if not key:
            continue
        seen: set[str] = set()
        duplicate_count = 0
        for row in rows:
            value = clean_text(row.get(key))
            if not value:
                continue
            if value in seen:
                duplicate_count += 1
            seen.add(value)
        if duplicate_count:
            state.duplicate_counts[table] = duplicate_count
            state.add_blocker("duplicate_primary_key", table=table, source="collected_rows", detail=f"{key}: {duplicate_count}")


def write_rows(conn: sqlite3.Connection, state: MigrationState) -> None:
    for table in TABLES:
        if table.name == "schema_migrations":
            continue
        insert_rows(conn, table.name, state.rows.get(table.name, []))
    insert_row(
        conn,
        "audit_events",
        {
            "id": stable_hash({"schema_version": SCHEMA_VERSION, "event": "migration_dry_run"}, prefix="audit_")[:24],
            "event_type": "migration_dry_run",
            "created_at": 0,
            "actor_user_id": "",
            "payload_json": stable_json({"schema_version": SCHEMA_VERSION}),
        },
    )
    conn.commit()


def default_dry_run_path(name: str) -> Path:
    timestamp = int(time.time() * 1000)
    return Path(tempfile.gettempdir()) / f"vantaline_{name}_{timestamp}"


def validate_output_path(path: Path, *, dry_run: bool, source_data_dir: Path) -> None:
    resolved = path.resolve()
    source_root = source_data_dir.resolve()
    if not dry_run or not (resolved == source_root or source_root in resolved.parents):
        return
    rel = resolved.relative_to(source_root).as_posix()
    allowed = (
        rel.startswith("db_migration_reports/")
        or rel.startswith("db_migration_backups/")
        or rel.startswith("vantaline.sqlite3")
        or "migration_report" in Path(rel).name
    )
    if not allowed:
        raise ValueError(f"dry-run output must be /tmp or an explicit ignored migration artifact path: {path}")


def create_apply_backup(inventory: SourceInventory) -> Path:
    backup_dir = inventory.data_dir / "db_migration_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"json_metadata_backup_{int(time.time())}.tar.gz"
    with tarfile.open(backup_path, "w:gz") as archive:
        for source in inventory.json_sources:
            if source.path.exists():
                archive.add(source.path, arcname=source.rel_path)
    return backup_path


def build_report(
    *,
    state: MigrationState,
    conn: sqlite3.Connection,
    dry_run: bool,
    db_path: Path,
    backup_path: Path | None,
) -> dict[str, Any]:
    inventory = state.inventory
    sensitive_sources = [
        {
            "source": source.rel_path,
            "exists": source.exists,
            "size_bytes": source.size_bytes,
            "policy": "excluded_redacted_no_checksum",
        }
        for source in inventory.sensitive_sources
    ]
    source_checksums = [
        {
            "source": source.rel_path,
            "size_bytes": source.size_bytes,
            "sha256": source.sha256,
            "parse_error": bool(source.error),
            "parse_warning": source.parse_warning,
        }
        for source in inventory.json_sources
    ]
    warning_counts: dict[str, int] = {}
    for warning in state.warnings:
        code = warning["code"]
        warning_counts[code] = warning_counts.get(code, 0) + 1
    blocking_error_counts: dict[str, int] = {}
    for error in state.blocking_errors:
        code = error["code"]
        blocking_error_counts[code] = blocking_error_counts.get(code, 0) + 1
    report = {
        "report_version": 1,
        "schema_version": SCHEMA_VERSION,
        "dry_run": dry_run,
        "source_root": str(inventory.source_root),
        "data_dir": str(inventory.data_dir),
        "db_artifact": {
            "path_policy": "/tmp" if str(db_path).startswith(tempfile.gettempdir()) else "explicit_local_path",
            "backup_created": bool(backup_path),
        },
        "source_to_table_mapping": SOURCE_TO_TABLE_MAPPING,
        "code_defined_status_sets": {
            "active_runtime_statuses": sorted(ACTIVE_RUNTIME_STATUSES),
            "historical_runtime_statuses": sorted(HISTORICAL_RUNTIME_STATUSES),
        },
        "row_counts": table_counts(conn),
        "source_checksums": source_checksums,
        "sensitive_sources": sensitive_sources,
        "source_errors": sorted(state.source_errors, key=lambda item: item["source"]),
        "source_warnings": sorted(state.source_warnings, key=lambda item: item["source"]),
        "blocking_errors": sorted(state.blocking_errors, key=lambda item: (item["table"], item["code"], item["detail"])),
        "blocking_error_counts": dict(sorted(blocking_error_counts.items())),
        "warnings": sorted(state.warnings, key=lambda item: (item["table"], item["code"], item["detail"]))[:200],
        "warning_counts": dict(sorted(warning_counts.items())),
        "duplicate_counts": dict(sorted(state.duplicate_counts.items())),
        "missing_owner_counts": dict(sorted(state.missing_owner_counts.items())),
        "orphan_counts": dict(sorted(state.orphan_counts.items())),
        "missing_path_counts": dict(sorted(state.missing_path_counts.items())),
        "missing_path_samples": state.missing_path_samples,
        "legacy_repairs": sorted(state.legacy_repairs, key=lambda item: (item["table"], item["source"], item["repaired_id"])),
        "security_policy": {
            "auth_sessions": "raw session tokens are stored only as sha256(token)",
            "reports": "raw session tokens, user password verifier values, provider keys, and local env contents are omitted",
            "secrets": "local secret/config files are presence-counted only",
        },
    }
    return report


def run_migration(args: argparse.Namespace) -> dict[str, Any]:
    inventory = load_inventory(Path(args.source))
    dry_run = not args.apply_local
    if args.db:
        db_path = Path(args.db)
    elif dry_run:
        db_path = default_dry_run_path("migration.sqlite3")
    else:
        db_path = inventory.data_dir / "vantaline.sqlite3"
    if args.report:
        report_path = Path(args.report)
    elif dry_run:
        report_path = default_dry_run_path("migration_report.json")
    else:
        report_path = inventory.data_dir / "db_migration_reports" / f"migration_report_{int(time.time())}.json"

    validate_output_path(db_path, dry_run=dry_run, source_data_dir=inventory.data_dir)
    validate_output_path(report_path, dry_run=dry_run, source_data_dir=inventory.data_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{db_path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()

    state = collect_rows(inventory, allow_legacy_id_repair=bool(args.allow_legacy_id_repair))
    backup_path = None
    if args.apply_local:
        if state.blocking_errors or state.source_errors:
            raise RuntimeError("apply-local refused because dry-run has source or blocking errors")
        backup_path = create_apply_backup(inventory)

    conn = connect_sqlite(db_path)
    try:
        apply_schema(conn)
        write_rows(conn, state)
        report = build_report(state=state, conn=conn, dry_run=dry_run, db_path=db_path, backup_path=backup_path)
    finally:
        conn.close()
    report_path.write_text(stable_json(report) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    report["db_path"] = str(db_path)
    if backup_path:
        report["backup_path"] = str(backup_path)
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(REPO_ROOT / "local_inspection_service"), help="Repo, service, or data directory to inventory")
    parser.add_argument("--db", default="", help="SQLite output path. Dry-run defaults to /tmp.")
    parser.add_argument("--report", default="", help="Redacted JSON report path. Dry-run defaults to /tmp.")
    parser.add_argument("--dry-run", action="store_true", help="Explicit dry-run mode. This is the default.")
    parser.add_argument("--apply-local", action="store_true", help="Create local ignored DB under data/ after backup and zero blockers.")
    parser.add_argument("--allow-legacy-id-repair", action="store_true", help="Deterministically repair legacy accessory IDs missing in config.json.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.dry_run and args.apply_local:
        print("--dry-run and --apply-local are mutually exclusive", file=sys.stderr)
        return 2
    try:
        report = run_migration(args)
    except Exception as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        return 2
    summary = {
        "report_path": report["report_path"],
        "db_path": report["db_path"],
        "row_counts": report["row_counts"],
        "source_error_count": len(report["source_errors"]),
        "blocking_error_count": len(report["blocking_errors"]),
        "legacy_repair_count": len(report["legacy_repairs"]),
        "missing_owner_counts": report["missing_owner_counts"],
        "missing_path_counts": report["missing_path_counts"],
    }
    print(stable_json(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
