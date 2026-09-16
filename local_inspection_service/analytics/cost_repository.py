"""Read-only ledger sources; connection and path ownership stays with the caller."""
from collections.abc import Callable, Iterator
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from ..storage.postgres_runtime_repository import PostgresRuntimeRepository
from ..storage.runtime_records import row_raw_json_list


@dataclass(frozen=True)
class CostPaths:
    data: Path
    analysis: Path
    detection: Path
    pipeline: Path
    auto_optimize: Path
    profile_cache: Path


@dataclass(frozen=True)
class CostStoreDependencies:
    paths: Callable[[], CostPaths]
    runtime_repository: Callable[[], PostgresRuntimeRepository | None]
    detection_tasks: Callable[[], list[dict[str, Any]]]
    pipeline_tasks: Callable[[], Any]
    auto_states: Callable[[], list[dict[str, Any]]]
    training_tasks: Callable[[], list[dict[str, Any]]]
    sanitize_task_id: Callable[[str], str]


class CostRepository:
    def __init__(self, dependencies: CostStoreDependencies):
        self.dependencies = dependencies

    def store_payloads(self) -> list[tuple[Path, Any]]:
        """Usage-bearing payloads read through the runtime store loaders (Postgres
        when active, legacy JSON otherwise). The paired paths are the legacy JSON
        locations so category classification and record ids stay stable across the
        Postgres cutover."""
        paths = self.dependencies.paths()
        pipeline_path = paths.pipeline
        repository = self.dependencies.runtime_repository()
        if repository is not None:
            # Raw rows, not the normalized loader output: normalization whitelists
            # fields and could drop usage metadata recorded outside the known spots.
            analysis_records: Any = row_raw_json_list(repository.fetch_all("data_analysis_records"))
        else:
            try:
                raw = json.loads(paths.analysis.read_text(encoding="utf-8")) if paths.analysis.exists() else {}
            except (OSError, json.JSONDecodeError):
                raw = {}
            analysis_records = raw.get("records") if isinstance(raw, dict) else raw
            if not isinstance(analysis_records, list):
                analysis_records = []
        payloads: list[tuple[Path, Any]] = [
            (paths.analysis, {"records": analysis_records}),
            (paths.detection, {"tasks": self.dependencies.detection_tasks()}),
            (pipeline_path, self.dependencies.pipeline_tasks()),
        ]
        for state in self.dependencies.auto_states():
            task_id = self.dependencies.sanitize_task_id(state.get("task_id") or "") or "state"
            payloads.append((paths.auto_optimize / f"{task_id}.json", state))
        return payloads


    def metadata_payloads(self) -> Iterator[tuple[Path, Any]]:
        paths = self.dependencies.paths()
        json_paths: list[Path] = []
        if paths.profile_cache.exists():
            json_paths.append(paths.profile_cache)
        for pattern in (
            "outputs/users/*/agent_mcp_pose_images/**/*.metadata.json",
            "outputs/users/*/auto_optimize_masks/**/*.metadata.json",
            "outputs/agent_mcp_pose_images/**/*.metadata.json",
            "outputs/auto_optimize_masks/**/*.metadata.json",
            "image_worker_logs/**/*.json",
        ):
            json_paths.extend(paths.data.glob(pattern))
        seen_paths: set[Path] = set()
        for path in json_paths:
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved in seen_paths or not path.exists() or not path.is_file():
                continue
            seen_paths.add(resolved)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            yield path, payload

    def training_tasks(self) -> list[dict[str, Any]]:
        return self.dependencies.training_tasks()

    def auto_states(self) -> list[dict[str, Any]]:
        return self.dependencies.auto_states()
