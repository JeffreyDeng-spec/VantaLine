"""Pipeline state snapshots and partial transactions under the existing update guard."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Any, Protocol
from .state_policy import normalize_pipeline_state

Record = dict[str, Any]
State = dict[str, list[str]]


class StateConnection(Protocol):
    def commit(self) -> None: ...


class PipelineStateRepository(Protocol):
    connection: StateConnection
    def fetch_all(self, table: str) -> list[Record]: ...
    def replace_all(self, table: str, rows: list[Record]) -> None: ...
    def upsert_row(self, table: str, row: Record, *, commit: bool = True) -> None: ...


class EncodePipelineState(Protocol):
    def __call__(self, state: State, *, updated_at: int) -> list[Record]: ...


@dataclass(frozen=True)
class PipelineStatePaths:
    data: Callable[[], Path]
    state: Callable[[], Path]


@dataclass(frozen=True)
class PipelineStateRows:
    encode: Callable[[], EncodePipelineState]
    decode: Callable[[], Callable[[list[Record]], Record]]


class PipelineStateStore:
    def __init__(self, repository: Callable[[], PipelineStateRepository | None], paths: PipelineStatePaths,
                 rows: PipelineStateRows, guard: Callable[[], AbstractContextManager]):
        self.repository, self.paths, self.rows, self.guard = repository, paths, rows, guard

    def load_pipeline_state(self) -> dict[str, list[str]]:
        repository = self.repository()
        if repository is not None:
            return normalize_pipeline_state(self.rows.decode()(repository.fetch_all("pipeline_state")))
        if not self.paths.state().exists():
            return {"accessory_ids": [], "pending_candidate_ids": []}
        try:
            raw = json.loads(self.paths.state().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        return normalize_pipeline_state(raw)

    def save_pipeline_state(self, state: dict[str, list[str]]) -> None:
        self.paths.data().mkdir(parents=True, exist_ok=True)
        payload = normalize_pipeline_state(state)
        repository = self.repository()
        if repository is not None:
            repository.replace_all("pipeline_state", self.rows.encode()(payload, updated_at=int(time.time())))
            return
        tmp_path = self.paths.state().with_name(f"{self.paths.state().name}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_path, self.paths.state())

    def save_pipeline_state_keys(self, state: dict[str, list[str]], changed_keys: set[str]) -> None:
        payload = normalize_pipeline_state(state)
        key_set = {key for key in changed_keys if key in payload}
        if not key_set:
            return
        repository = self.repository()
        if repository is not None:
            rows = [row for row in self.rows.encode()(payload, updated_at=int(time.time())) if row.get("state_key") in key_set]
            try:
                for row in rows:
                    repository.upsert_row("pipeline_state", row, commit=False)
                repository.connection.commit()
            except Exception:
                rollback = getattr(repository.connection, "rollback", None)
                if callable(rollback):
                    rollback()
                raise
            return
        self.save_pipeline_state(payload)

    def update_pipeline_state(self, mutator: Callable[[dict[str, list[str]]], None]) -> dict[str, list[str]]:
        with self.guard():
            before = self.load_pipeline_state()
            state = json.loads(json.dumps(before))
            mutator(state)
            state = normalize_pipeline_state(state)
            changed_keys = {key for key, value in state.items() if before.get(key) != value}
            self.save_pipeline_state_keys(state, changed_keys)
            return state

    def add_pipeline_accessory_id(self, accessory_id: str) -> dict[str, list[str]]:
        clean_id = str(accessory_id or "").strip()

        def mutate(state: dict[str, list[str]]) -> None:
            if clean_id and clean_id not in state["accessory_ids"]:
                state["accessory_ids"].insert(0, clean_id)

        return self.update_pipeline_state(mutate)

    def remove_pipeline_accessory_id(self, accessory_id: str) -> dict[str, list[str]]:
        clean_id = str(accessory_id or "").strip()

        def mutate(state: dict[str, list[str]]) -> None:
            state["accessory_ids"] = [item_id for item_id in state["accessory_ids"] if item_id != clean_id]

        return self.update_pipeline_state(mutate)

    def add_pipeline_pending_candidate_id(self, candidate_id: str) -> dict[str, list[str]]:
        clean_id = str(candidate_id or "").strip()

        def mutate(state: dict[str, list[str]]) -> None:
            if clean_id and clean_id not in state["pending_candidate_ids"]:
                state["pending_candidate_ids"].insert(0, clean_id)

        return self.update_pipeline_state(mutate)

    def remove_pipeline_pending_candidate_id(self, candidate_id: str) -> dict[str, list[str]]:
        clean_id = str(candidate_id or "").strip()

        def mutate(state: dict[str, list[str]]) -> None:
            state["pending_candidate_ids"] = [item_id for item_id in state["pending_candidate_ids"] if item_id != clean_id]

        return self.update_pipeline_state(mutate)
