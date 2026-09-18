"""Legacy inspection visibility, duplicate lookup and human disposition."""
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any
from fastapi import HTTPException
from ..schemas.text_inspection import IncomingTextReviewRequest
from ..incoming_text_inspection import REVIEW_REQUIRED as INCOMING_TEXT_REVIEW_REQUIRED
from .incoming_ports import IncomingAccess, IncomingInspections, IncomingTasks, IncomingMedia, IncomingWrites, IncomingJSON


class IncomingReviews:
    def __init__(self, access: IncomingAccess, inspections: IncomingInspections, tasks: IncomingTasks,
                 media: IncomingMedia, writes: IncomingWrites, json: IncomingJSON,
                 decode_rows: Callable[[], Callable[[list[dict[str, Any]]], list[dict[str, Any]]]],
                 public: Callable[[dict[str, Any]], dict[str, Any]]):
        self.access, self.inspections, self.tasks = access, inspections, tasks
        self.media, self.writes, self.json = media, writes, json
        self.decode_rows, self.public = decode_rows, public

    def duplicate(self, owner_user_id: str, task_id: str, capture_id: str) -> dict[str, Any] | None:
        repository = self.writes.repository()
        if repository is not None:
            row = repository.fetch_one_by_columns(
                "incoming_text_inspections",
                {"owner_user_id": owner_user_id, "task_id": task_id, "capture_id": capture_id},
            )
            values = self.decode_rows()([row]) if row else []
            return values[0] if values else None
        return next(
            (
                item
                for item in self.inspections.all()
                if str(item.get("owner_user_id")) == owner_user_id
                and str(item.get("task_id")) == task_id
                and str(item.get("capture_id")) == capture_id
            ),
            None,
        )

    def get_incoming_text_inspection_evidence(self, inspection_id: str, asset_kind: str) -> Path:
        inspection = self.inspections.load(inspection_id)
        if not inspection:
            raise HTTPException(status_code=404, detail="检验记录不存在")
        # The task owner is authoritative. Legacy shared assignments do not grant
        # access after the self-owned task model was introduced.
        self.access.task()(str(inspection.get("task_id")))
        key = {"source": "source_path", "corrected": "corrected_path", "annotated": "annotated_path"}.get(asset_kind)
        path = Path(str(inspection.get(key or "") or ""))
        if not key or not path.exists() or not self.media.under(path, self.media.root()):
            raise HTTPException(status_code=404, detail="检验证据文件不存在")
        return path

    def review_incoming_text_inspection(self, inspection_id: str, request: IncomingTextReviewRequest) -> dict[str, Any]:
        self.access.permission("inspection", detail="没有来料检验权限")
        inspection = self.inspections.load(inspection_id)
        if not inspection:
            raise HTTPException(status_code=404, detail="检验记录不存在")
        # Only the task owner (or a platform administrator) may disposition records.
        self.access.task()(str(inspection.get("task_id") or ""))
        if inspection.get("auto_decision") != INCOMING_TEXT_REVIEW_REQUIRED:
            raise HTTPException(status_code=409, detail="只有需复核记录可以人工处理")
        decision = request.decision.strip().upper()
        if decision not in {"RELEASED", "REJECTED"}:
            raise HTTPException(status_code=400, detail="人工结论只能是 RELEASED 或 REJECTED")
        reason = request.reason.strip()
        if not reason or len(reason) > 500:
            raise HTTPException(status_code=400, detail="请填写 1–500 字复核原因")
        existing = str(inspection.get("final_decision") or "")
        if existing:
            if existing == decision:
                return self.public(inspection)
            raise HTTPException(status_code=409, detail="该记录已经作出不同的人工结论")
        reviewed_at = int(time.time())
        actor_user_id = str(self.access.user().get("id") or "")
        repository = self.writes.repository()
        if repository is not None:
            try:
                inspection = repository.review_incoming_text_inspection(
                    inspection_id,
                    decision=decision,
                    reason=reason,
                    actor_user_id=actor_user_id,
                    reviewed_at=reviewed_at,
                )
            except Exception as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from None
        else:
            with self.writes.guard():
                inspections = self.json.read(self.json.paths.inspections())
                stored = next((item for item in inspections if str(item.get("id")) == inspection_id), None)
                if not stored:
                    raise HTTPException(status_code=404, detail="检验记录不存在")
                stored_decision = str(stored.get("final_decision") or "")
                if stored_decision and stored_decision != decision:
                    raise HTTPException(status_code=409, detail="该记录已经作出不同的人工结论")
                stored.update(
                    {
                        "final_decision": decision,
                        "review_reason": reason,
                        "reviewed_at": reviewed_at,
                        "reviewed_by_user_id": actor_user_id,
                        "updated_at": reviewed_at,
                    }
                )
                audit_event = {
                    "id": f"incoming_review_{inspection_id}",
                    "event_type": "incoming_text.reviewed",
                    "created_at": reviewed_at,
                    "actor_user_id": actor_user_id,
                    "payload": {"inspection_id": inspection_id, "task_id": stored.get("task_id"), "decision": decision, "reason": reason},
                }
                audits = self.json.read(self.json.paths.audit())
                if not any(str(item.get("id")) == audit_event["id"] for item in audits):
                    audits.insert(0, audit_event)
                self.json.write(self.json.paths.inspections(), inspections)
                self.json.write(self.json.paths.audit(), audits)
                inspection = stored
        return self.public(inspection)

    def list_incoming_text_inspections(self, task_id: str | None = None, material_code: str | None = None, decision: str | None = None, limit: int = 100) -> dict[str, Any]:
        self.access.permission("inspection", detail="没有来料检验权限")
        user = self.access.user()
        normalized_decision = str(decision or "").strip().upper()
        visible_task_ids = {
            str(task.get("id"))
            for task in self.tasks.all()
            if str(task.get("task_kind") or "") == "incoming_material_text" and self.access.task_allowed(task, user)
        }
        repository = self.writes.repository()
        bounded = max(1, min(500, limit))
        if repository is not None:
            result = repository.list_incoming_text_inspections(
                task_ids=sorted(visible_task_ids),
                task_id=str(task_id or ""),
                material_code=str(material_code or ""),
                decision=normalized_decision,
                limit=bounded,
            )
            return {
                "items": [self.public(item) for item in self.decode_rows()(result.get("items") or [])],
                "total": int(result.get("total") or 0),
                "summary": result.get("summary") or {},
            }
        items = [item for item in self.inspections.all() if str(item.get("task_id")) in visible_task_ids]
        if task_id:
            items = [item for item in items if str(item.get("task_id")) == task_id]
        if material_code:
            items = [item for item in items if str(item.get("material_code")) == material_code]
        if normalized_decision:
            items = [item for item in items if normalized_decision in {str(item.get("auto_decision")), str(item.get("final_decision"))}]
        items.sort(key=lambda item: int(item.get("created_at") or 0), reverse=True)
        counts = Counter(str(item.get("final_decision") or item.get("auto_decision") or "UNKNOWN") for item in items)
        return {"items": [self.public(item) for item in items[:bounded]], "total": len(items), "summary": dict(counts)}
