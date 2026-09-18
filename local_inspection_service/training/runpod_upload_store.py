"""Streaming artifact persistence retaining the existing cleanup and replacement boundaries."""
from collections.abc import AsyncIterator, Callable
import hashlib
from pathlib import Path
from typing import Protocol
from fastapi import HTTPException


class UploadStream(Protocol):
    def stream(self) -> AsyncIterator[bytes]: ...


class ArtifactReceiver(Protocol):
    async def receive(self, target_path: Path, request: UploadStream) -> tuple[str, int]: ...


class RunPodUploadStore:
    def __init__(self, limit: Callable[[], int]):
        self.limit = limit

    async def receive(self, target_path: Path, request: UploadStream) -> tuple[str, int]:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(target_path.suffix + ".uploading")
        max_bytes = self.limit()
        digest = hashlib.sha256()
        total = 0
        try:
            with tmp_path.open("wb") as handle:
                async for chunk in request.stream():
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise HTTPException(status_code=413, detail="Training artifact upload is too large")
                    digest.update(chunk)
                    handle.write(chunk)
            if total <= 0:
                raise HTTPException(status_code=400, detail="Training artifact upload is empty")
            tmp_path.replace(target_path)
        except Exception:
            try:
                tmp_path.unlink()
            except OSError:
                pass
            raise
        sha = digest.hexdigest()
        return sha, total
