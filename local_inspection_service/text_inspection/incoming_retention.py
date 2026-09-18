"""Legacy evidence retention and fail-closed disk capacity checks."""
import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from fastapi import HTTPException
from .incoming_ports import IncomingInspections, IncomingMedia, IncomingWrites, IncomingJSON, Record


class IncomingCapacity:
    def __init__(self, data_dir: Callable[[], Path], minimum_free: Callable[[], int]):
        self.data_dir, self.minimum_free = data_dir, minimum_free

    def require(self, upload_bytes: int) -> None:
        reserve = self.minimum_free() + max(0, int(upload_bytes)) * 3
        try:
            free_bytes = shutil.disk_usage(self.data_dir()).free
        except OSError as exc:
            raise HTTPException(status_code=507, detail="无法确认服务器存储空间，已停止本次检验") from exc
        if free_bytes < reserve:
            raise HTTPException(status_code=507, detail="服务器存储空间不足，已停止本次检验，请联系管理员清理空间")


class IncomingRetention:
    def __init__(self, inspections: IncomingInspections, media: IncomingMedia, writes: IncomingWrites,
                 json: IncomingJSON, audit: Callable[[], Callable[[Record], None]], system_owner: Callable[[], str]):
        self.inspections, self.media, self.writes = inspections, media, writes
        self.json, self.audit, self.system_owner = json, audit, system_owner

    def purge(self) -> dict[str, int]:
        """Delete only image evidence after the configured retention period."""
        retention_days = max(1, int(os.environ.get("VANTALINE_INCOMING_TEXT_IMAGE_RETENTION_DAYS", "90")))
        cutoff = int(time.time()) - retention_days * 86400
        repository = self.writes.repository()
        candidates = (
            repository.incoming_text_retention_candidates(before_created_at=cutoff)
            if repository is not None
            else [item for item in self.inspections.all() if int(item.get("created_at") or 0) < cutoff and not item.get("evidence_purged_at")]
        )
        deleted_files = 0
        updated_records = 0
        for inspection in candidates:
            all_removed = True
            for key in ("source_path", "corrected_path", "annotated_path"):
                path = Path(str(inspection.get(key) or ""))
                if path.exists() and self.media.under(path, self.media.root()):
                    try:
                        path.unlink()
                        deleted_files += 1
                    except OSError:
                        all_removed = False
            if not all_removed:
                continue
            purged_at = int(time.time())
            if repository is not None:
                changed = repository.mark_incoming_text_evidence_purged(
                    str(inspection.get("id") or ""), purged_at=purged_at, retention_days=retention_days
                )
            else:
                changed = False
                with self.writes.guard():
                    values = self.json.read(self.json.paths.inspections())
                    stored = next((item for item in values if str(item.get("id")) == str(inspection.get("id"))), None)
                    if stored and not stored.get("evidence_purged_at"):
                        stored["evidence_purged_at"] = purged_at
                        stored["evidence_retention_days"] = retention_days
                        self.json.write(self.json.paths.inspections(), values)
                        changed = True
            updated_records += int(changed)
        if updated_records:
            self.audit()(
                {
                    "id": f"incoming_retention_{cutoff // 86400}",
                    "event_type": "incoming_text.evidence_retention_purge",
                    "created_at": int(time.time()),
                    "actor_user_id": self.system_owner(),
                    "payload": {"records": updated_records, "files": deleted_files, "retention_days": retention_days},
                }
            )
        return {"records": updated_records, "files": deleted_files}
