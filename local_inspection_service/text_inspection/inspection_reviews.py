"""Account-scoped inspection evidence and persisted human review."""
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from fastapi import HTTPException
from .inspection_ports import Record, InspectionAccess, InspectionRecords, ReadVerified


class InspectionReviews:
    def __init__(self, access: InspectionAccess, records: InspectionRecords,
                 read_verified: ReadVerified, audit: Callable[[Record], None],
                 bounded_text: Callable[[Any, int], str]):
        self.access, self.records, self.read_verified = access, records, read_verified
        self.audit, self.bounded_text = audit, bounded_text

    def get_text_inspection_v2_evidence(self, inspection_id: str, kind: str) -> tuple[bytes, str]:
        self.access.require_permission("inspection", detail="没有文字检验权限")
        owner_user_id, _ = self.access.owner()
        record = self.records.owned("records", inspection_id, owner_user_id)
        if not record or kind not in {"source", "annotated"}:
            raise HTTPException(status_code=404, detail="检验证据不存在")
        expected = str(record.get("source_sha256") or "") if kind == "source" else str(record.get("annotated_sha256") or "")
        contents = self.read_verified(str(record.get(f"{kind}_path") or ""), owner_user_id, str(record.get("standard_id") or ""), expected_sha256=expected, max_bytes=20 * 1024 * 1024)
        mime = "image/png" if contents.startswith(b"\x89PNG") else "image/jpeg"
        return contents, mime

    async def review_text_inspection_v2(self, inspection_id: str, read_body: Callable[[], Awaitable[Any]]) -> Record:
        self.access.require_permission("inspection", detail="没有文字检验权限")
        owner_user_id, owner_username = self.access.owner()
        record = self.records.owned("records", inspection_id, owner_user_id)
        if not record:
            raise HTTPException(status_code=404, detail="检验记录不存在")
        standard = self.records.owned("standards", record.get("standard_id", ""), owner_user_id)
        if record.get("standard_type") == "manual" or (standard and standard.get("standard_type") == "manual"):
            raise HTTPException(status_code=410, detail="旧说明书历史仅供查阅，请在文字检验重新导入 PDF")
        body = await read_body()
        decision = str(body.get("decision") or "") if isinstance(body, dict) else ""
        reason = self.bounded_text(body.get("reason") if isinstance(body, dict) else "", 500).strip()
        if decision not in {"PASS", "FAIL"} or not reason:
            raise HTTPException(status_code=400, detail="强制放行或判退必须填写原因")
        record.update({"final_decision": decision, "review_reason": reason, "reviewed_by_user_id": owner_user_id, "reviewed_by_username": owner_username, "reviewed_at": int(time.time()), "updated_at": int(time.time())})
        self.records.save("records", record)
        self.audit({"id": "audit_" + uuid.uuid4().hex, "event_type": "text_inspection_v2_review", "entity_type": "text_inspection_record", "entity_id": inspection_id, "created_at": int(time.time()), "actor_user_id": owner_user_id, "payload": {"decision": decision, "reason": reason, "training_pool": "pending_review" if decision == "PASS" else ""}})
        return self.records.public(record)
