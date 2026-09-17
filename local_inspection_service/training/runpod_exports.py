"""RunPod download/upload export metadata with explicit storage and task ports."""
from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import re
import secrets
import shutil
import time
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

Record = dict[str, Any]


class TemporaryBundle(Protocol):
    def cleanup(self) -> None: ...


class ExportTaskUpdate(Protocol):
    def __call__(self, job_id: str, **values: Any) -> Record: ...


@dataclass(frozen=True)
class RunPodExportPaths:
    resolve: Callable[[], Callable[[Any], Path]]
    output: Callable[[str, str], Path]
    safe_name: Callable[[str], str]


@dataclass(frozen=True)
class RunPodExportPolicy:
    token_hash: Callable[[str], str]
    ttl: Callable[[], int]
    public_base: Callable[[], str]


class RunPodExports:
    def __init__(self, paths: RunPodExportPaths, policy: RunPodExportPolicy,
                 bundle: Callable[[Path, str], tuple[TemporaryBundle, Path]],
                 digest: Callable[[Path], str], update_provider: Callable[[], ExportTaskUpdate]):
        self.paths, self.policy = paths, policy
        self.bundle, self.digest, self.update_provider = bundle, digest, update_provider

    def create_runpod_training_dataset_archive(self, job_id: str, task: dict[str, Any], dataset: dict[str, Any]) -> dict[str, Any]:
        dataset_dir = self.paths.resolve()(dataset.get("dataset_dir", ""))
        temp_dir, archive_path = self.bundle(dataset_dir, job_id)
        try:
            owner_id = str(task.get("owner_user_id") or "")
            export_dir = self.paths.output("runpod_training_datasets", owner_id) / self.paths.safe_name(job_id)
            if export_dir.exists():
                shutil.rmtree(export_dir)
            export_dir.mkdir(parents=True, exist_ok=True)
            target_path = export_dir / "dataset.zip"
            shutil.copy2(archive_path, target_path)
            token = secrets.token_urlsafe(32)
            token_hash = self.policy.token_hash(token)
            expires_at = int(time.time()) + self.policy.ttl()
            public_base = self.policy.public_base()
            url = f"{public_base}/api/training/runpod/datasets/{quote(job_id, safe='')}/{quote(token, safe='')}/dataset.zip"
            sha = self.digest(target_path)
            metadata = {
                "job_id": job_id,
                "path": str(target_path),
                "sha256": sha,
                "size": target_path.stat().st_size,
                "token_sha256": token_hash,
                "expires_at": expires_at,
                "created_at": int(time.time()),
            }
            (export_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            self.update_provider()(
                job_id,
                runpod_dataset_archive_path=str(target_path),
                runpod_dataset_archive_sha256=sha,
                runpod_dataset_archive_size=target_path.stat().st_size,
                runpod_dataset_token_sha256=token_hash,
                runpod_dataset_token_expires_at=expires_at,
                runpod_dataset_public_host=urlsplit(public_base).netloc,
                worker_bundle_size_mb=round(target_path.stat().st_size / (1024 * 1024), 1),
                note="已生成 RunPod 训练数据包，等待远端 worker 拉取。",
            )
            return {"url": url, "sha256": sha, "size": target_path.stat().st_size, "path": str(target_path)}
        finally:
            temp_dir.cleanup()

    def create_runpod_training_artifact_upload(self, job_id: str, task: dict[str, Any]) -> dict[str, Any]:
        owner_id = str(task.get("owner_user_id") or "")
        clean_job_id = str(job_id or "").strip()
        artifact_dir_name = re.sub(r"[^A-Za-z0-9_.@-]+", "_", clean_job_id).strip("._") or "runpod_training"
        export_dir = self.paths.output("runpod_training_artifacts", owner_id) / artifact_dir_name
        if export_dir.exists():
            shutil.rmtree(export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)
        target_path = export_dir / "run.zip"
        token = secrets.token_urlsafe(32)
        token_hash = self.policy.token_hash(token)
        expires_at = int(time.time()) + self.policy.ttl()
        public_base = self.policy.public_base()
        url = f"{public_base}/api/training/runpod/artifacts/{quote(clean_job_id, safe='')}/{quote(token, safe='')}/run.zip"
        self.update_provider()(
            job_id,
            runpod_artifact_upload_path=str(target_path),
            runpod_artifact_token_sha256=token_hash,
            runpod_artifact_token_expires_at=expires_at,
            runpod_artifact_public_host=urlsplit(public_base).netloc,
            note="已生成 RunPod 训练产物上传地址，等待远端 worker 上传。",
        )
        return {"url": url, "path": str(target_path)}
