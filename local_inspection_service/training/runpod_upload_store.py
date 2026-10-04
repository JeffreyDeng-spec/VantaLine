"""Streaming artifact persistence retaining the existing cleanup and replacement boundaries."""
from collections.abc import AsyncIterator, Callable
import hashlib
from pathlib import Path
from typing import Protocol
from fastapi import HTTPException
from ..storage.artifacts.runtime import get_runtime


class UploadStream(Protocol):
    def stream(self) -> AsyncIterator[bytes]: ...


class ArtifactReceiver(Protocol):
    async def receive(self, target_path: Path, request: UploadStream) -> tuple[str, int]: ...


class RunPodUploadStore:
    def __init__(self, limit: Callable[[], int], *, runtime_provider=get_runtime):
        self.limit = limit
        self.runtime_provider = runtime_provider

    async def receive(self, target_path: Path, request: UploadStream) -> tuple[str, int]:
        runtime = self.runtime_provider()
        if runtime is not None:
            return await self._receive_cos(runtime, target_path, request)
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

    async def _receive_cos(self, runtime, target_path, request):
        from anyio import to_thread
        from ..storage.artifacts.archives import BoundedOutput
        from ..storage.artifacts.types import Artifact
        key = runtime.key(target_path)
        previous = runtime.store.locations.get(key)
        generation = previous.generation if previous else 0
        maximum = min(self.limit(), runtime.store.budget.limits["upload"])
        with runtime.store.budget.workspace("upload", maximum) as workspace:
            temporary = workspace / "run.zip"
            digest, total = hashlib.sha256(), 0
            with temporary.open("xb") as raw:
                bounded = BoundedOutput(raw, runtime.store.budget, maximum)
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > maximum:
                        raise HTTPException(413, "Training artifact upload is too large")
                    bounded.write(chunk)
                    digest.update(chunk)
                bounded.flush()
            if not total:
                raise HTTPException(400, "Training artifact upload is empty")
            row = Artifact(key, generation + 1, digest.hexdigest(), total)
            # The lease owns the only staging copy through full COS verification
            # and CAS. Disconnect/failure removes scratch, never the old object.
            def publish():
                runtime.store.objects.put(row, temporary)
                runtime.store.locations.publish(row, expected_generation=generation)
            await to_thread.run_sync(publish)
            return row.sha256, row.size
