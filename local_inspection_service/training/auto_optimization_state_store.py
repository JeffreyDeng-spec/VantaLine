"""Auto-optimization state persistence with operation-local repositories and explicit caches."""
from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any

from ..model_profiles.snapshots import freeze_record as freeze_model_record
from .auto_optimization_state_ports import AutoOptimizationStateStorage, AutoOptimizationStatePolicy, AutoOptimizationStateCache


@dataclass(frozen=True)
class AutoOptimizationStateStore:
    storage: AutoOptimizationStateStorage
    policy: AutoOptimizationStatePolicy
    cache: AutoOptimizationStateCache

    def auto_optimize_task_path(self, task_id: str) -> Path:
        safe_task_id = self.policy.safe_record_id()(self.policy.sanitize_ai_detection_task_id()(task_id) or self.storage.AI_DETECTION_MODEL_ID())
        return self.storage.AUTO_OPTIMIZE_DIR() / f"{safe_task_id}.json"

    def load_auto_optimize_state(self, task_id: str) -> dict[str, Any]:
        clean_task_id = self.policy.sanitize_ai_detection_task_id()(task_id) or self.storage.AI_DETECTION_MODEL_ID()
        read_cache = self.cache._read_path_cache().get()
        cache_key = f"auto_optimize_state:{clean_task_id}"
        if read_cache is not None and cache_key in read_cache:
            return read_cache[cache_key]
        repository = self.storage.runtime_postgres_repository_or_none()()
        if repository is not None:
            row = repository.fetch_by_primary_key("auto_optimize_states", {"task_id": clean_task_id})
            state = self.policy.row_raw_json_list()([row])[0] if row else {}
        else:
            path = self.storage.auto_optimize_task_path()(clean_task_id)
            try:
                state = json.loads(self.storage._business_files().read_text(path, encoding="utf-8")) if self.storage._business_files().exists(path) else {}
            except (OSError, json.JSONDecodeError):
                state = {}
        if not isinstance(state, dict):
            state = {}
        settings = {**self.policy.default_auto_optimize_settings()(), **(state.get("settings") if isinstance(state.get("settings"), dict) else {})}
        state.setdefault("task_id", clean_task_id)
        state.setdefault("created_at", int(time.time()))
        state.setdefault("updated_at", int(time.time()))
        state.setdefault("samples", [])
        state.setdefault("datasets", [])
        state.setdefault("candidate_models", [])
        state.setdefault("shadow_runs", [])
        state.setdefault("active_model_id", "")
        state.setdefault("retired_model_ids", [])
        state["settings"] = settings
        if read_cache is not None:
            read_cache[cache_key] = state
        return state

    def save_auto_optimize_state(self, state: dict[str, Any]) -> dict[str, Any]:
        freeze_model_record(self.policy.resolve_model_profiles(), state)
        self.storage.AUTO_OPTIMIZE_DIR().mkdir(parents=True, exist_ok=True)
        state["updated_at"] = int(time.time())
        clean_task_id = self.policy.sanitize_ai_detection_task_id()(state.get("task_id")) or self.storage.AI_DETECTION_MODEL_ID()
        state["task_id"] = clean_task_id
        self.cache.store_read_cache_invalidate()("auto_optimize_states")
        repository = self.storage.runtime_postgres_repository_or_none()()
        if repository is not None:
            row = self.policy.auto_optimize_state_row()(state, fallback_id=clean_task_id)
            if row:
                repository.upsert_row("auto_optimize_states", row)
            return state
        path = self.storage.auto_optimize_task_path()(clean_task_id)
        tmp_path = path.with_suffix(".json.tmp")
        self.storage._business_files().write_text(tmp_path, json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(path)
        return state

    def list_auto_optimize_states(self) -> list[dict[str, Any]]:
        cached, cached_states = self.cache.store_read_cache_get()("auto_optimize_states")
        if cached:
            return list(cached_states)
        repository = self.storage.runtime_postgres_repository_or_none()()
        if repository is not None:
            states: list[dict[str, Any]] = []
            for row in repository.fetch_all("auto_optimize_states"):
                raw_states = self.policy.row_raw_json_list()([row])
                state = raw_states[0] if raw_states else {}
                if not isinstance(state, dict):
                    continue
                task_id = str(row.get("task_id") or "").strip()
                if task_id and not state.get("task_id"):
                    state["task_id"] = task_id
                states.append(state)
            self.cache.store_read_cache_put()("auto_optimize_states", states)
            return list(states)
        states = []
        for path in self.storage._business_files().glob(self.storage.AUTO_OPTIMIZE_DIR(), "*.json"):
            try:
                state = json.loads(self.storage._business_files().read_text(path, encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(state, dict):
                if not state.get("task_id"):
                    state["task_id"] = path.stem
                states.append(state)
        self.cache.store_read_cache_put()("auto_optimize_states", states)
        return list(states)
