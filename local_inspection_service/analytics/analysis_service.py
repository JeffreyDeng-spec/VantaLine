"""Owner-aware access to analysis records, separate from storage and HTTP."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from fastapi import HTTPException

from .analysis_records import sanitize_data_analysis_record_id
from .analysis_repository import AnalysisRepository

Record = dict[str, Any]


class RequireAnalysisAccess(Protocol):
    def __call__(self, record: Record, user: Record, *, write: bool = False) -> None: ...


@dataclass(frozen=True)
class AnalysisAccess:
    is_admin: Callable[[Record], bool]
    visible: Callable[[Record, Record, str | None], bool]
    require_access: RequireAnalysisAccess


class AnalysisRecords:
    def __init__(self, repository: AnalysisRepository, access: AnalysisAccess):
        self.repository = repository
        self.access = access

    def data_analysis_records_for_user(self,
        user: dict[str, Any],
        *,
        target_user_id: str | None = None,
        task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if target_user_id and not self.access.is_admin(user) and str(target_user_id) != str(user.get("id") or ""):
            raise HTTPException(status_code=403, detail="Admin role required for user filtering")
        clean_task_id = str(task_id or "").strip()
        records = [
            record
            for record in self.repository.load_data_analysis_records()
            if self.access.visible(record, user, target_user_id if self.access.is_admin(user) else None)
        ]
        if clean_task_id:
            records = [record for record in records if str((record.get("task") or {}).get("id") or "") == clean_task_id]
        return records

    def find_data_analysis_record(self, record_id: str, user: dict[str, Any], *, write: bool = False) -> dict[str, Any]:
        record = self.repository.load_data_analysis_record(record_id)
        if record is not None:
            self.access.require_access(record, user, write=write)
            return record
        raise HTTPException(status_code=404, detail="Analysis record not found")

    def delete_data_analysis_record(self, record_id: str, user: dict[str, Any], *, missing_ok: bool = False) -> str | None:
        clean_id = sanitize_data_analysis_record_id(record_id)
        if not clean_id:
            return None
        try:
            record = self.find_data_analysis_record(clean_id, user, write=True)
        except HTTPException as exc:
            if missing_ok and exc.status_code == 404:
                return None
            raise
        clean_id = str(record.get("record_id") or clean_id)
        return self.repository.delete_data_analysis_record(clean_id, missing_ok=missing_ok)
