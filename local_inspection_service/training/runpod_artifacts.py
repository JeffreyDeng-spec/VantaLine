"""RunPod artifact verification and the existing ordered filesystem import."""
import base64
import binascii
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import time
from typing import Any
import zipfile
from contextlib import nullcontext
from ..storage.artifacts.runtime import get_runtime

Record = dict[str, Any]


@dataclass(frozen=True)
class RunPodArtifactPaths:
    resolve: Callable[[Any], Path]
    output_root: Callable[[], Path]
    output: Callable[[], Callable[[str, str], Path]]


class RunPodArtifacts:
    def __init__(self, paths: RunPodArtifactPaths, find: Callable[[str], Record | None],
                 summary: Callable[[Any], Any], *, runtime_provider=get_runtime):
        self.paths, self.find, self.summary = paths, find, summary
        self.runtime_provider = runtime_provider

    def import_runpod_yolo_artifacts(self, task, output):
        if self.runtime_provider() is None:
            return self._local_import_runpod_yolo_artifacts(task, output)
        return self._cos_import_runpod_yolo_artifacts(task, output)

    def _local_import_runpod_yolo_artifacts(self, task: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
        job_id = str(task.get("job_id") or task.get("task_id") or "").strip()
        artifacts = output.get("artifacts") if isinstance(output.get("artifacts"), dict) else {}
        best = artifacts.get("best_pt") if isinstance(artifacts.get("best_pt"), dict) else {}
        raw_b64 = str(best.get("artifact_b64") or "").strip()
        uploaded_archive_path: Path | None = None
        if raw_b64:
            try:
                payload = base64.b64decode(raw_b64, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise RuntimeError("RunPod best.pt artifact is not valid base64") from exc
        else:
            latest_task = self.find(job_id) or task
            archive_raw = str(latest_task.get("runpod_artifact_archive_path") or latest_task.get("runpod_artifact_upload_path") or "").strip()
            if not archive_raw:
                raise RuntimeError("RunPod worker completed but did not return or upload a best.pt artifact")
            uploaded_archive_path = Path(archive_raw).expanduser()
            if not uploaded_archive_path.is_absolute():
                uploaded_archive_path = self.paths.resolve(archive_raw)
            uploaded_archive_path = uploaded_archive_path.resolve()
            try:
                uploaded_archive_path.relative_to(self.paths.output_root().resolve())
            except ValueError as exc:
                raise RuntimeError("RunPod artifact archive path is outside the output directory") from exc
            if not uploaded_archive_path.exists() or not uploaded_archive_path.is_file():
                raise RuntimeError("RunPod uploaded artifact archive is missing")
            try:
                with zipfile.ZipFile(uploaded_archive_path) as archive:
                    best_members = [
                        name
                        for name in archive.namelist()
                        if name.replace("\\", "/").endswith("weights/best.pt") and not name.endswith("/")
                    ]
                    if not best_members:
                        raise RuntimeError("RunPod uploaded artifact archive does not contain weights/best.pt")
                    payload = archive.read(sorted(best_members)[0])
            except zipfile.BadZipFile as exc:
                raise RuntimeError("RunPod uploaded artifact archive is not a valid zip") from exc
        expected_sha = str(best.get("sha256") or "").strip().lower()
        actual_sha = hashlib.sha256(payload).hexdigest()
        if expected_sha and actual_sha != expected_sha:
            raise RuntimeError("RunPod best.pt checksum mismatch")
        run_dir = self.paths.output()("training_runs", str(task.get("owner_user_id") or "")) / job_id
        weights_dir = run_dir / "weights"
        weights_dir.mkdir(parents=True, exist_ok=True)
        best_path = weights_dir / "best.pt"
        best_path.write_bytes(payload)
        if uploaded_archive_path is not None:
            shutil.copy2(uploaded_archive_path, run_dir / "runpod_artifacts.zip")
        metadata = {
            "display_name": task.get("label") or job_id,
            "note": "Imported from RunPod YOLO training worker.",
            "pipeline_task_id": str(task.get("pipeline_task_id") or ""),
            "pipeline_task_name": str(task.get("pipeline_task_name") or ""),
            "runpod_job_id": task.get("runpod_job_id") or task.get("remote_training_job_id") or "",
            "runpod_worker": output.get("worker") or "",
            "runpod_contract_version": output.get("contract_version") or 0,
            "runpod_best_pt_sha256": actual_sha,
            "runpod_artifact_archive_path": str(uploaded_archive_path or ""),
            "updated_at": int(time.time()),
        }
        (run_dir / "library_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        (run_dir / "runpod_result.json").write_text(json.dumps(self.summary(output), indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "worker_artifacts_imported_at": int(time.time()),
            "worker_artifact_import_error": "",
            "training_run_dir": str(run_dir),
            "imported_model_path": str(best_path),
            "runpod_best_pt_sha256": actual_sha,
            "worker_artifact_sha256": actual_sha,
        }

    def _cos_import_runpod_yolo_artifacts(self, task: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
        job_id = str(task.get("job_id") or task.get("task_id") or "").strip()
        artifacts = output.get("artifacts") if isinstance(output.get("artifacts"), dict) else {}
        best = artifacts.get("best_pt") if isinstance(artifacts.get("best_pt"), dict) else {}
        raw_b64 = str(best.get("artifact_b64") or "").strip()
        uploaded_archive_path: Path | None = None
        runtime = self.runtime_provider()
        archive_row = None
        if raw_b64:
            try:
                payload = base64.b64decode(raw_b64, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise RuntimeError("RunPod best.pt artifact is not valid base64") from exc
        else:
            latest_task = self.find(job_id) or task
            archive_raw = str(latest_task.get("runpod_artifact_archive_path") or latest_task.get("runpod_artifact_upload_path") or "").strip()
            if not archive_raw:
                raise RuntimeError("RunPod worker completed but did not return or upload a best.pt artifact")
            uploaded_archive_path = Path(archive_raw).expanduser()
            if not uploaded_archive_path.is_absolute():
                uploaded_archive_path = self.paths.resolve(archive_raw)
            uploaded_archive_path = uploaded_archive_path.resolve()
            try:
                uploaded_archive_path.relative_to(self.paths.output_root().resolve())
            except ValueError as exc:
                raise RuntimeError("RunPod artifact archive path is outside the output directory") from exc
            if runtime is not None:
                archive_row = runtime.store.locations.get(runtime.key(uploaded_archive_path))
                if archive_row is None and runtime.mode == "cos" or archive_row is not None and archive_row.state != "ready":
                    raise RuntimeError("RunPod uploaded artifact archive is missing")
            if archive_row is None and (not uploaded_archive_path.exists() or not uploaded_archive_path.is_file()):
                raise RuntimeError("RunPod uploaded artifact archive is missing")
            if archive_row is not None and latest_task.get("runpod_artifact_archive_sha256") != archive_row.sha256:
                raise RuntimeError("RunPod uploaded artifact archive version changed")
            try:
                lease = runtime.store.cache.open(archive_row) if archive_row is not None else nullcontext(uploaded_archive_path)
                with lease as archive_file, zipfile.ZipFile(archive_file) as archive:
                    best_members = [
                        name
                        for name in archive.namelist()
                        if name.replace("\\", "/").endswith("weights/best.pt") and not name.endswith("/")
                    ]
                    if not best_members:
                        raise RuntimeError("RunPod uploaded artifact archive does not contain weights/best.pt")
                    if archive.getinfo(sorted(best_members)[0]).file_size > 512 * 1024 * 1024:
                        raise RuntimeError("RunPod best.pt exceeds the model import limit")
                    payload = archive.read(sorted(best_members)[0])
            except zipfile.BadZipFile as exc:
                raise RuntimeError("RunPod uploaded artifact archive is not a valid zip") from exc
        expected_sha = str(best.get("sha256") or "").strip().lower()
        actual_sha = hashlib.sha256(payload).hexdigest()
        if expected_sha and actual_sha != expected_sha:
            raise RuntimeError("RunPod best.pt checksum mismatch")
        run_dir = self.paths.output()("training_runs", str(task.get("owner_user_id") or "")) / job_id
        weights_dir = run_dir / "weights"
        best_path = weights_dir / "best.pt"
        def write(path, data):
            if runtime is None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            else:
                key = runtime.key(path)
                previous = runtime.store.locations.get(key)
                runtime.store.put_bytes(key, data, expected_generation=previous.generation if previous else 0)
        write(best_path, payload)
        if uploaded_archive_path is not None and runtime is None:
            shutil.copy2(uploaded_archive_path, run_dir / "runpod_artifacts.zip")
        elif archive_row is not None:
            from ..storage.artifacts.types import Artifact
            key = runtime.key(run_dir / "runpod_artifacts.zip")
            previous = runtime.store.locations.get(key)
            generation = previous.generation if previous else 0
            runtime.store.locations.publish(Artifact(key, generation + 1, archive_row.sha256, archive_row.size),
                                            expected_generation=generation)
        elif uploaded_archive_path is not None:
            key = runtime.key(run_dir / "runpod_artifacts.zip")
            previous = runtime.store.locations.get(key)
            runtime.store.put(key, uploaded_archive_path, expected_generation=previous.generation if previous else 0)
        metadata = {
            "display_name": task.get("label") or job_id,
            "note": "Imported from RunPod YOLO training worker.",
            "pipeline_task_id": str(task.get("pipeline_task_id") or ""),
            "pipeline_task_name": str(task.get("pipeline_task_name") or ""),
            "runpod_job_id": task.get("runpod_job_id") or task.get("remote_training_job_id") or "",
            "runpod_worker": output.get("worker") or "",
            "runpod_contract_version": output.get("contract_version") or 0,
            "runpod_best_pt_sha256": actual_sha,
            "runpod_artifact_archive_path": str(uploaded_archive_path or ""),
            "updated_at": int(time.time()),
        }
        write(run_dir / "library_metadata.json", json.dumps(metadata, indent=2).encode())
        write(run_dir / "runpod_result.json", json.dumps(self.summary(output), indent=2, ensure_ascii=False).encode())
        return {
            "worker_artifacts_imported_at": int(time.time()),
            "worker_artifact_import_error": "",
            "training_run_dir": str(run_dir),
            "imported_model_path": str(best_path),
            "runpod_best_pt_sha256": actual_sha,
            "worker_artifact_sha256": actual_sha,
        }
