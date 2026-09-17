"""Label comparison submission with unchanged provider and persistence ordering."""
import json
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from collections.abc import Callable
from typing import Any
from fastapi import HTTPException
from .comparison_ports import ComparisonMedia
from .inspection_ports import (
    Record, CaptureUpload, InspectionAccess, InspectionRecords, SubmissionPolicy,
    SubmissionImages, SubmissionModels, SubmissionDiagnostics, PreparedSubmit,
)


class ComparisonSubmission:
    def __init__(self, access: InspectionAccess, records: InspectionRecords,
                 load: Callable[[str], list[Record]], media: ComparisonMedia,
                 images: SubmissionImages, models: SubmissionModels, policy: SubmissionPolicy,
                 diagnostics: SubmissionDiagnostics, prepared_submit: PreparedSubmit,
                 resolve_extraction: Callable[[str, str, str, Record], tuple[bytes, Record]],
                 display_snapshot: Callable[[Record, Record], Record]):
        self.access, self.records, self.load, self.media = access, records, load, media
        self.images, self.models, self.policy = images, models, policy
        self.diagnostics, self.prepared_submit = diagnostics, prepared_submit
        self.resolve_extraction, self.display_snapshot = resolve_extraction, display_snapshot

    async def compare_text_inspection_label(self, captured_file: CaptureUpload | None,
                                           standard_asset_id: str, comparison_id: str, extraction_id: str) -> Record:
        request_received_at_ms = int(time.time() * 1000)
        self.access.require_permission("inspection", detail="没有文字检验权限")
        owner_user_id, owner_username = self.access.owner()
        if not re.fullmatch(r"[A-Za-z0-9_.-]{8,128}", comparison_id):
            raise HTTPException(status_code=400, detail="comparison_id 格式错误")
        asset = self.records.owned("assets", standard_asset_id, owner_user_id)
        standard = self.records.owned("standards", str(asset.get("standard_id") if asset else ""), owner_user_id)
        confirmed_snapshot = next((item for item in standard.get("confirmed_assets", []) if str(item.get("id")) == standard_asset_id), None) if standard else None
        if not asset or not standard or standard.get("status") != "confirmed" or not confirmed_snapshot:
            raise HTTPException(status_code=404, detail="已确认标准标签不存在")
        extraction = None
        if bool(captured_file) == bool(extraction_id):
            raise HTTPException(status_code=400, detail="请提供已确认提取或实物图片中的一种")
        if extraction_id:
            captured_upload, extraction = self.resolve_extraction(extraction_id, owner_user_id, standard_asset_id, standard)
        else:
            captured_upload = await captured_file.read(10 * 1024 * 1024 + 1)
        if confirmed_snapshot.get("preparation"):
            return self.prepared_submit(owner_user_id, owner_username, standard, asset, confirmed_snapshot, captured_upload, comparison_id, extraction)
        if self.policy.qwen_enabled(owner_user_id):
            raise HTTPException(status_code=409, detail="该标准尚未生成元素模板，请先在标准库启用并完成标准准备；无需提取实拍标签。")
        captured_upload_sha256 = self.media.digest(captured_upload)
        captured, captured_mime, source_suffix, captured_source_format = self.images.prepare(captured_upload, max_bytes=100 * 1024 * 1024 if extraction else 10 * 1024 * 1024)
        asset = {**asset, "sha256": str(confirmed_snapshot.get("sha256") or "")}
        reference_original = self.images.asset_bytes(asset, owner_user_id)
        reference, reference_mime, _, reference_source_format = self.images.prepare(reference_original)
        settings = self.models.settings("document")
        provider_settings = {
            **settings,
            "timeout_seconds": max(
                self.policy.timeout(),
                float(settings.get("timeout_seconds") or 0),
            ),
        }
        provider_reference, provider_reference_mime, provider_reference_format = self.images.provider_copy(reference, reference_mime)
        provider_captured, provider_captured_mime, provider_captured_format = self.images.provider_copy(captured, captured_mime)
        fingerprint_payload = {
            "reference_sha256": self.media.digest(reference_original), "reference_bytes": len(reference_original),
            "prepared_reference_sha256": self.media.digest(reference), "prepared_reference_bytes": len(reference),
            "captured_upload_sha256": captured_upload_sha256, "captured_upload_bytes": len(captured_upload),
            "captured_sha256": self.media.digest(captured), "captured_bytes": len(captured),
            "standard_asset_id": standard_asset_id, "provider": settings.get("provider"),
            "standard_revision_id": standard.get("current_revision_id", ""),
            "standard_revision_number": int(standard.get("revision_number") or 0),
            "model": settings.get("model"), "prompt_version": self.policy.prompt_version(),
            "schema_version": "text-compare-result-v1",
        }
        if extraction_id:
            fingerprint_payload["extraction_id"] = extraction_id
        fingerprint = self.media.digest(json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode())
        existing = next((item for item in self.load("records") if item.get("owner_user_id") == owner_user_id and item.get("comparison_id") == comparison_id), None)
        if existing:
            if existing.get("fingerprint") != fingerprint:
                raise HTTPException(status_code=409, detail="comparison_id 已用于其他图片")
            if existing.get("status") == "attempting":
                return {**self.records.public(existing), "decision": "REVIEW_REQUIRED", "message": "上次模型请求结果不确定，为避免重复计费未自动重试。"}
            return self.records.public(existing)
        now = int(time.time())
        diagnostics: dict[str, Any] = {
            "schema_version": "text-inspection-diagnostics-v1",
            "request_received_at_ms": request_received_at_ms,
            "request": {
                "comparison_id": comparison_id,
                "standard_id": standard["id"],
                "standard_asset_id": standard_asset_id,
                "standard_revision_id": standard.get("current_revision_id", ""),
                "standard_revision_number": int(standard.get("revision_number") or 0),
                "uploaded_actual": {
                    "bytes": len(captured_upload),
                    "sha256": captured_upload_sha256,
                    "filename_suffix": Path(str(captured_file.filename or "")).suffix.lower()[:20] if captured_file else ".png",
                    "declared_content_type": str(captured_file.content_type or "")[:120] if captured_file else "image/png",
                },
                "prepared_actual": self.diagnostics.image(
                    captured, source_format=captured_source_format, mime_type=captured_mime,
                ),
                "prepared_reference": self.diagnostics.image(
                    reference, source_format=reference_source_format, mime_type=reference_mime,
                ),
                "provider_actual": self.diagnostics.image(
                    provider_captured, source_format=provider_captured_format, mime_type=provider_captured_mime,
                ),
                "provider_reference": self.diagnostics.image(
                    provider_reference, source_format=provider_reference_format, mime_type=provider_reference_mime,
                ),
            },
            "provider_config": {
                "provider": settings.get("provider") or "",
                "model": settings.get("model") or "",
                "endpoint_host": urlsplit(str(settings.get("base_url") or "")).hostname or "",
                "timeout_seconds": provider_settings.get("timeout_seconds"),
                "configured": bool(settings.get("configured")),
                "api_key_present": bool(settings.get("api_key_present")),
                "key_source_name": settings.get("key_source_name") or "",
                "max_attempts": 1,
                "max_tokens": 1800,
                "external_vlm_enabled": self.policy.external_enabled(),
                "automatic_match_verified": self.policy.automatic_match_verified(),
            },
            "events": [],
        }
        self.diagnostics.event(diagnostics, "input_prepared", "ok")
        if extraction:
            diagnostics["extraction"] = extraction
        record = {"id": "ins_" + uuid.uuid4().hex, "owner_user_id": owner_user_id, "owner_username": owner_username, "standard_id": standard["id"], "standard_asset_id": standard_asset_id, "standard_revision_id": standard.get("current_revision_id", ""), "standard_revision_number": int(standard.get("revision_number") or 0), "reference_sha256": fingerprint_payload["reference_sha256"], "reference_source_format": reference_source_format, "comparison_id": comparison_id, "fingerprint": fingerprint, "fingerprint_components": fingerprint_payload, "status": "attempting", "attempt_id": "attempt_" + uuid.uuid4().hex, "attempt_started_at": now, "auto_decision": "REVIEW_REQUIRED", "final_decision": "", "source_upload_sha256": captured_upload_sha256, "source_sha256": self.media.digest(captured), "source_format": captured_source_format, "created_at": now, "updated_at": now, "prompt_version": self.policy.prompt_version(), "result_schema_version": "text-compare-result-v1", "planned_provider": settings.get("provider"), "planned_model": settings.get("model"), "differences": [], "diagnostics": diagnostics}
        record["history_display"] = self.display_snapshot(standard, asset)
        source_path = self.media.path(owner_user_id, standard["id"], f"{record['id']}-source{source_suffix}")
        self.media.write(source_path, captured)
        record["source_path"] = str(source_path)
        if not self.records.save("records", record, insert_only=True):
            winner = next((item for item in self.load("records") if item.get("owner_user_id") == owner_user_id and item.get("comparison_id") == comparison_id), None)
            if winner and winner.get("fingerprint") == fingerprint:
                return self.records.public(winner)
            raise HTTPException(status_code=409, detail="comparison_id 已用于其他输入")
        if not self.policy.external_enabled():
            self.diagnostics.event(diagnostics, "external_media_gate", "blocked")
            record.update({"status": "review_required", "decision": "REVIEW_REQUIRED", "message": "外部图片比对尚未完成客户授权和生产启用，请人工复核。", "attempt_finished_at": int(time.time()), "external_media_sent": False, "external_media_send_status": "not_sent"})
            self.records.save("records", record)
            self.diagnostics.write(record)
            return self.records.public(record)
        user_content = [
            {"type": "text", "text": "STANDARD_LABEL"},
            {"type": "image_url", "image_url": {"url": self.images.data_url(provider_reference, provider_reference_mime), "detail": "high"}},
            {"type": "text", "text": "CAPTURED_LABEL"},
            {"type": "image_url", "image_url": {"url": self.images.data_url(provider_captured, provider_captured_mime), "detail": "high"}},
        ]
        failure_stage = "provider_call"
        try:
            record["external_media_send_status"] = "attempting"
            record["external_media_sent"] = None
            self.diagnostics.event(diagnostics, "provider_call", "started")
            self.records.save("records", record)
            provider = self.models.call("provider.gemini.generate_json", {"provider_config": provider_settings, "system_prompt": self.models.prompt(), "user_content": user_content, "max_tokens": 1800, "max_attempts": 1})
            diagnostics["provider_result"] = self.diagnostics.provider(provider, provider_settings)
            self.diagnostics.event(
                diagnostics,
                "provider_call",
                "ok" if provider.get("ok") else "failed",
                details={
                    "latency_ms": provider.get("latency_ms"),
                    "timed_out": provider.get("timed_out"),
                    "http_status": provider.get("http_status"),
                    "error_type": provider.get("error_type"),
                },
            )
            record["external_media_sent"] = True
            record["external_media_send_status"] = "sent"
            if not provider.get("ok"):
                failure_stage = "provider_result"
                raise ValueError(str(provider.get("error") or "模型服务异常"))
            failure_stage = "response_validation"
            normalized_response = self.models.normalize(
                provider.get("parsed"),
                str(provider.get("provider") or provider_settings.get("provider") or ""),
            )
            diagnostics["normalized_response"] = self.diagnostics.value(normalized_response)
            checked = self.models.validate(normalized_response)
            self.diagnostics.event(diagnostics, "response_validation", "ok", details={"decision": checked.get("decision")})
            if checked["decision"] == "MATCH" and not self.policy.automatic_match_verified():
                checked = {"decision": "REVIEW_REQUIRED", "differences": [], "message": "模型未发现差异，但自动通过尚未完成现场验收，请人工确认。"}
                self.diagnostics.event(diagnostics, "automatic_match_gate", "blocked")
            record.update(checked)
            record["auto_decision"] = checked["decision"]
            record["status"] = "completed" if checked["decision"] != "REVIEW_REQUIRED" else "review_required"
            record["provider"] = provider.get("provider") or settings.get("provider")
            record["model"] = provider.get("model") or settings.get("model")
            record["latency_ms"] = provider.get("latency_ms")
            failure_stage = "annotation"
            annotated = self.images.annotate(captured, checked["differences"])
            annotated_path = self.media.path(owner_user_id, standard["id"], f"{record['id']}-annotated.jpg")
            self.media.write(annotated_path, annotated)
            record["annotated_path"] = str(annotated_path)
            record["annotated_sha256"] = self.media.digest(annotated)
            record["annotated_image_data_url"] = f"/api/text-inspection/inspections/{record['id']}/evidence/annotated"
            self.diagnostics.event(diagnostics, "annotation", "ok", details={"bytes": len(annotated), "sha256": record["annotated_sha256"]})
            self.diagnostics.event(diagnostics, "completed", "ok", details={"decision": record.get("decision")})
        except Exception as exc:
            provider_error_type = (
                str(provider.get("error_type") or "")
                if failure_stage == "provider_result" and isinstance(provider, dict)
                else ""
            )
            error_type = provider_error_type or type(exc).__name__
            diagnostics["failure"] = {
                "stage": failure_stage,
                "error_type": error_type,
                "message": str(exc)[:1000],
            }
            self.diagnostics.event(
                diagnostics,
                failure_stage,
                "failed",
                details={"error_type": error_type, "message": str(exc)},
            )
            record.update({"decision": "REVIEW_REQUIRED", "auto_decision": "REVIEW_REQUIRED", "status": "uncertain", "message": "模型请求结果不确定；为避免重复计费不会自动重试，请人工复核。", "error_code": error_type, "differences": [], "charge_status": "uncertain", "external_media_send_status": "uncertain", "external_media_sent": None})
        record["attempt_finished_at"] = int(time.time())
        record["updated_at"] = int(time.time())
        self.records.save("records", record)
        self.diagnostics.write(record)
        return self.records.public(record)
