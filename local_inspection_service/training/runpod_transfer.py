"""Token-protected RunPod transfer validation and task metadata updates."""
from collections.abc import Callable
from dataclasses import dataclass
import hmac
from pathlib import Path
import re
from typing import Any, Protocol
from fastapi import HTTPException
from fastapi.responses import FileResponse
from .runpod_exports import ExportTaskUpdate
from .runpod_upload_store import ArtifactReceiver, UploadStream

Record = dict[str, Any]


class TransferPathResolver(Protocol):
    def __call__(self, value: Any, *, for_write: bool = False) -> Path: ...


@dataclass(frozen=True)
class TransferPaths:
    resolve: Callable[[], TransferPathResolver]
    output: Callable[[], Path]


class RunPodTrainingTransfer:
    def __init__(self, find: Callable[[str], Record | None], token_hash: Callable[[str], str],
                 clock: Callable[[], float], paths: TransferPaths, uploads: ArtifactReceiver, update_provider: Callable[[], ExportTaskUpdate]):
        self.find, self.token_hash, self.clock = find, token_hash, clock
        self.paths, self.uploads, self.update_provider = paths, uploads, update_provider

    def download_runpod_training_dataset(self, job_id: str, token: str) -> FileResponse:
        clean_job_id = str(job_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,160}", clean_job_id):
            raise HTTPException(status_code=404, detail="Training dataset not found")
        task = self.find(clean_job_id)
        if not task:
            raise HTTPException(status_code=404, detail="Training dataset not found")
        expected_hash = str(task.get("runpod_dataset_token_sha256") or "").strip()
        if not expected_hash or not hmac.compare_digest(expected_hash, self.token_hash(token)):
            raise HTTPException(status_code=404, detail="Training dataset not found")
        expires_at = int(task.get("runpod_dataset_token_expires_at") or 0)
        if expires_at and expires_at < int(self.clock()):
            raise HTTPException(status_code=410, detail="Training dataset URL expired")
        archive_path = self.paths.resolve()(task.get("runpod_dataset_archive_path") or "")
        try:
            archive_path.relative_to(self.paths.output().resolve())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Training dataset not found") from exc
        if not archive_path.exists() or not archive_path.is_file():
            raise HTTPException(status_code=404, detail="Training dataset not found")
        download_name = re.sub(r"[^A-Za-z0-9_.@-]+", "_", clean_job_id).strip("._") or "training"
        return FileResponse(
            archive_path,
            media_type="application/zip",
            filename=f"{download_name}_dataset.zip",
            headers={"Cache-Control": "no-store"},
        )

    async def upload_runpod_training_artifact(self, job_id: str, token: str, request: UploadStream) -> dict[str, Any]:
        clean_job_id = str(job_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,160}", clean_job_id):
            raise HTTPException(status_code=404, detail="Training artifact upload not found")
        task = self.find(clean_job_id)
        if not task:
            raise HTTPException(status_code=404, detail="Training artifact upload not found")
        expected_hash = str(task.get("runpod_artifact_token_sha256") or "").strip()
        if not expected_hash or not hmac.compare_digest(expected_hash, self.token_hash(token)):
            raise HTTPException(status_code=404, detail="Training artifact upload not found")
        expires_at = int(task.get("runpod_artifact_token_expires_at") or 0)
        if expires_at and expires_at < int(self.clock()):
            raise HTTPException(status_code=410, detail="Training artifact upload URL expired")
        target_raw = str(task.get("runpod_artifact_upload_path") or "").strip()
        if not target_raw:
            raise HTTPException(status_code=404, detail="Training artifact upload not found")
        target_path = Path(target_raw).expanduser()
        if not target_path.is_absolute():
            target_path = self.paths.resolve()(target_raw, for_write=True)
        target_path = target_path.resolve()
        try:
            target_path.relative_to(self.paths.output().resolve())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Training artifact upload not found") from exc
        sha, total = await self.uploads.receive(target_path, request)
        self.update_provider()(
            clean_job_id,
            runpod_artifact_archive_path=str(target_path),
            runpod_artifact_archive_sha256=sha,
            runpod_artifact_archive_size=total,
            runpod_artifact_uploaded_at=int(self.clock()),
            note="RunPod 训练产物已上传，等待平台导入模型。",
        )
        return {"ok": True, "sha256": sha, "size": total}
