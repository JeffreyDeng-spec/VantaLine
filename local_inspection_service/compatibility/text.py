"""Historical default-only forwarders. Production business ports use owned graphs."""
from __future__ import annotations
from ..runtime.default_application import default_application as _application
import os
from typing import Any
from pathlib import Path
_beta_comparison = _application.text._beta_comparison
_incoming_capacity = _application.text._incoming_capacity
_incoming_ocr_engine = _application.text._incoming_ocr_engine
_incoming_retention = _application.text._incoming_retention
_incoming_reviews = _application.text._incoming_reviews
_incoming_task_access = _application.text._incoming_task_access
_incoming_text_store = _application.text._incoming_text_store
_text_comparisons = _application.text._text_comparisons
_text_diagnostics = _application.text._text_diagnostics
_text_media = _application.text._text_media
_text_records = _application.text._text_records
_text_revisions = _application.text._text_revisions

def _text_v2_json_path(kind: str) -> Path:
    return _text_records.json_path(kind)

def _text_v2_load(kind: str) -> list[dict[str, Any]]:
    return _text_records.load(kind)

def _text_v2_save(kind: str, value: dict[str, Any], *, insert_only: bool=False) -> bool:
    return _text_records.save(kind, value, insert_only=insert_only)

def _text_v2_update_attempt(kind: str, value: dict[str, Any], expected_status: str='attempting') -> bool:
    return _text_records.update_attempt(kind, value, expected_status)

def _text_v2_owned(kind: str, record_id: str, owner_user_id: str) -> dict[str, Any] | None:
    return _text_records.owned(kind, record_id, owner_user_id)

def _text_v2_media_path(owner_user_id: str, standard_id: str, filename: str) -> Path:
    return _text_media.media_path(owner_user_id, standard_id, filename)

def _text_v2_write(path: Path, contents: bytes) -> None:
    return _text_media.write(path, contents)

def _text_v2_read_verified(path_value: str, owner_user_id: str, standard_id: str, *, expected_sha256: str='', max_bytes: int=120 * 1024 * 1024) -> bytes:
    return _text_media.read_verified(path_value, owner_user_id, standard_id, expected_sha256=expected_sha256, max_bytes=max_bytes)

def _text_v2_asset_bytes(asset: dict[str, Any], owner_user_id: str) -> bytes:
    return _text_media.asset_bytes(asset, owner_user_id)

def _text_v2_apply_revision(standard: dict[str, Any], assets: list[dict[str, Any]], *, action: str, asset_id: str, now: int) -> dict[str, Any]:
    return _text_revisions.apply(standard, assets, action=action, asset_id=asset_id, now=now)

def _text_v2_image_diagnostics(contents: bytes, *, source_format: str, mime_type: str) -> dict[str, Any]:
    return _text_diagnostics.image_diagnostics(contents, source_format=source_format, mime_type=mime_type)

def _text_v2_write_server_diagnostic(record: dict[str, Any]) -> None:
    return _text_diagnostics.write_server_diagnostic(record)

def _submit_prepared_text_comparison(owner_user_id, owner_username, standard, asset, confirmed_snapshot, captured_upload, comparison_id, extraction):
    return _text_comparisons.submit_prepared(owner_user_id, owner_username, standard, asset, confirmed_snapshot, captured_upload, comparison_id, extraction)

def load_incoming_text_references() -> list[dict[str, Any]]:
    return _incoming_text_store.load_incoming_text_references()

def load_incoming_text_inspections() -> list[dict[str, Any]]:
    return _incoming_text_store.load_incoming_text_inspections()

def load_incoming_text_reference(reference_id: str) -> dict[str, Any] | None:
    return _incoming_text_store.load_incoming_text_reference(reference_id)

def load_incoming_text_inspection(inspection_id: str) -> dict[str, Any] | None:
    return _incoming_text_store.load_incoming_text_inspection(inspection_id)

def save_incoming_text_reference(reference: dict[str, Any], *, insert_only: bool=False) -> bool:
    return _incoming_text_store.save_incoming_text_reference(reference, insert_only=insert_only)

def save_incoming_text_inspection(inspection: dict[str, Any], *, insert_only: bool=False) -> bool:
    return _incoming_text_store.save_incoming_text_inspection(inspection, insert_only=insert_only)

def append_incoming_text_audit(event: dict[str, Any]) -> None:
    return _incoming_text_store.append_incoming_text_audit(event)

def require_incoming_text_task(task_id: str, *, write: bool=False) -> dict[str, Any]:
    return _incoming_task_access.require(task_id, write=write)

def incoming_text_ocr_engine() -> Any:
    return _incoming_ocr_engine.get()

def _duplicate_incoming_capture(owner_user_id: str, task_id: str, capture_id: str) -> dict[str, Any] | None:
    return _incoming_reviews.duplicate(owner_user_id, task_id, capture_id)

def require_incoming_text_storage_capacity(upload_bytes: int) -> None:
    return _incoming_capacity.require(upload_bytes)

def _run_text_compare_beta(user_id: str, clean_id: str, reference_bytes: bytes, captured_bytes: bytes) -> dict[str, Any]:
    return _beta_comparison.run(user_id, clean_id, reference_bytes, captured_bytes)

def purge_expired_incoming_text_evidence() -> dict[str, int]:
    return _incoming_retention.purge()
