"""Preview output directory and plan JSON persistence with existing partial-write semantics."""
from collections.abc import Callable
import json
from pathlib import Path
from typing import Any


class PreviewArtifactStore:
    def __init__(self, output: Callable[[str], Path], jobs: Callable[[], Path]):
        self.output, self.jobs = output, jobs

    def create_directory(self, preview_id: str) -> Path:
        job_dir = self.output("training_previews") / preview_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def write_plan(self, preview_id: str, plan: dict[str, Any]) -> None:
        (self.jobs() / f"{preview_id}.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
