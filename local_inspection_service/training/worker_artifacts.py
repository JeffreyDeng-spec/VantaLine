"""Legacy artifact import preserving validation, file writes and partial-failure semantics."""
from collections.abc import Callable
import base64
import binascii
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any


class WorkerArtifactImport:
    def __init__(self, owner_output: Callable[[], Callable[[str, str], Path]], safe_name: Callable[[], Callable[[str], str]],
                 clock: Callable[[], float]):
        self.owner_output, self.safe_name, self.clock = owner_output, safe_name, clock

    def import_worker_training_artifacts(self, task: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
        if task.get("worker_artifacts_imported_at"):
            return {}
        job_id = str(task.get("job_id") or task.get("task_id") or "").strip()
        if not job_id:
            return {}
        model_artifact = next(
            (
                item
                for item in artifacts.get("models", [])
                if isinstance(item, dict) and str(item.get("artifact_b64") or "").strip()
            ),
            None,
        )
        if not model_artifact:
            return {}
        try:
            payload = base64.b64decode(str(model_artifact["artifact_b64"]), validate=True)
        except (ValueError, binascii.Error):
            return {"worker_artifact_import_error": "Worker model artifact payload is not valid base64"}
        expected_sha = str(model_artifact.get("artifact_sha256") or "").strip().lower()
        actual_sha = hashlib.sha256(payload).hexdigest()
        if expected_sha and actual_sha != expected_sha:
            return {"worker_artifact_import_error": "Worker model artifact checksum mismatch"}
        run_dir = self.owner_output()("training_runs", str(task.get("owner_user_id") or "")) / job_id
        weights_dir = run_dir / "weights"
        weights_dir.mkdir(parents=True, exist_ok=True)
        filename = self.safe_name()(str(model_artifact.get("artifact_filename") or "best.pt"))
        if not filename.endswith(".pt"):
            filename = "best.pt"
        model_path = weights_dir / filename
        model_path.write_bytes(payload)
        best_path = weights_dir / "best.pt"
        if model_path.name != "best.pt":
            shutil.copyfile(model_path, best_path)
        metadata = {
            "display_name": task.get("label") or model_artifact.get("label") or job_id,
            "note": "Imported from Windows Worker transfer result.",
            "pipeline_task_id": str(task.get("pipeline_task_id") or ""),
            "pipeline_task_name": str(task.get("pipeline_task_name") or ""),
            "worker_job_id": task.get("remote_training_job_id"),
            "worker_artifact_sha256": actual_sha,
            "updated_at": int(self.clock()),
        }
        (run_dir / "library_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return {
            "worker_artifacts_imported_at": int(self.clock()),
            "worker_artifact_import_error": "",
            "training_run_dir": str(run_dir),
            "imported_model_path": str(best_path),
            "worker_artifact_sha256": actual_sha,
        }
