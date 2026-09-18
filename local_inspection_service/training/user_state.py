"""Account-scoped training state and propagation of task changes to configuration."""
from collections.abc import Callable
from dataclasses import dataclass
import json
import time
from typing import Any, Protocol

Record = dict[str, Any]


def clear_training_private_state(training: dict[str, Any], reason: str) -> dict[str, Any]:
    training["preview_urls"] = []
    training["previews"] = []
    training["preview_cache_key"] = None
    training["preview_sprite_versions"] = {}
    training["last_preview_id"] = ""
    training["approved_preview_id"] = ""
    training["active_training_task_id"] = ""
    training["preview_stale_reason"] = reason
    return training


class TrainingStateVisibility(Protocol):
    def __call__(self, record: Record, user: Record, target_user_id: str | None = None) -> bool: ...


@dataclass(frozen=True)
class TrainingStateAccess:
    owner: Callable[[Record | None], str]
    visible: TrainingStateVisibility
    admin: Callable[[Record], bool]
    current_owner: Callable[[], Record]


@dataclass(frozen=True)
class TrainingStateStorage:
    find: Callable[[str], Record | None]
    load: Callable[[], Record]
    save: Callable[[Record], None]


class TrainingUserState:
    def __init__(self, defaults: Callable[[], Record], legacy_owner: Callable[[], str],
                 access: TrainingStateAccess, storage: TrainingStateStorage, sync_pipeline: Callable[[Record], None]):
        self.defaults, self.legacy_owner, self.access = defaults, legacy_owner, access
        self.storage, self.sync_pipeline = storage, sync_pipeline

    def default_training_state(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.defaults()))

    def normalize_training_owner_key(self, owner_user_id: Any) -> str:
        owner = str(owner_user_id or "").strip()
        return owner or self.legacy_owner()

    def training_state_store(self, config: dict[str, Any]) -> dict[str, dict[str, Any]]:
        raw_store = config.get("training_by_user_id") if isinstance(config.get("training_by_user_id"), dict) else {}
        store: dict[str, dict[str, Any]] = {
            self.normalize_training_owner_key(owner): state
            for owner, state in raw_store.items()
            if isinstance(state, dict)
        }
        legacy_training = config.get("training") if isinstance(config.get("training"), dict) else None
        if legacy_training:
            owner = self.normalize_training_owner_key(self.access.owner(legacy_training))
            store.setdefault(owner, legacy_training)
        config["training_by_user_id"] = store
        return store

    def sanitize_training_state_for_user(self,
        training: dict[str, Any] | None,
        user: dict[str, Any],
        selected_ids: set[str],
        target_user_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(training, dict):
            return self.default_training_state()
        if not self.access.visible(training, user, target_user_id):
            return self.default_training_state()
        scoped_training = training
        raw_selected = [str(item) for item in scoped_training.get("selected_accessory_ids", []) if str(item)]
        if raw_selected:
            visible_selected = [item_id for item_id in raw_selected if item_id in selected_ids]
            if len(visible_selected) != len(raw_selected):
                scoped_training["selected_accessory_ids"] = visible_selected
                clear_training_private_state(scoped_training, "training_selection_not_visible")
        return scoped_training

    def training_state_for_user(self,
        config: dict[str, Any],
        user: dict[str, Any],
        selected_ids: set[str],
        target_user_id: str | None = None,
    ) -> dict[str, Any]:
        store = self.training_state_store(config)
        if self.access.admin(user) and target_user_id:
            owner_key = self.normalize_training_owner_key(target_user_id)
        elif self.access.admin(user):
            states = [
                self.sanitize_training_state_for_user(dict(state), user, selected_ids, None)
                for state in store.values()
                if isinstance(state, dict) and self.access.visible(state, user)
            ]
            aggregate = self.default_training_state()
            aggregate["training_states"] = states
            return aggregate
        else:
            owner_key = self.normalize_training_owner_key(user["id"])
        state = store.get(owner_key)
        return self.sanitize_training_state_for_user(dict(state) if isinstance(state, dict) else None, user, selected_ids, target_user_id)

    def set_training_state_for_user(self, config: dict[str, Any], user: dict[str, Any], training_state: dict[str, Any]) -> None:
        state = {**self.default_training_state(), **training_state, **self.access.current_owner()}
        owner_key = self.normalize_training_owner_key(state.get("owner_user_id") or user["id"])
        store = self.training_state_store(config)
        store[owner_key] = state
        config["training_by_user_id"] = store
        if self.access.admin(user):
            config["training"] = state

    def sync_training_state_from_task(self, job_id: str) -> None:
        task = self.storage.find(job_id)
        if not task:
            return
        owner_user_id = str(task.get("owner_user_id") or task.get("user_id") or task.get("created_by_user_id") or self.legacy_owner())
        owner_username = str(task.get("owner_username") or task.get("username") or task.get("created_by_username") or "")
        full_config = self.storage.load()
        store = self.training_state_store(full_config)
        owner_key = self.normalize_training_owner_key(owner_user_id)
        existing = store.get(owner_key) if isinstance(store.get(owner_key), dict) else {}
        state = {**self.default_training_state(), **dict(existing)}
        for key in (
            "status",
            "progress",
            "note",
            "error",
            "current_epoch",
            "total_epochs",
            "completed_at",
            "stopped_at",
            "cancelled_at",
            "return_code",
            "training_executor",
            "remote_training_status",
            "remote_training_poll_error",
            "training_run_dir",
            "imported_model_path",
            "runpod_job_id",
            "runpod_best_pt_sha256",
        ):
            if key in task:
                state[key] = task.get(key)
        state.update(
            {
                "active_training_task_id": str(task.get("job_id") or task.get("task_id") or job_id),
                "active_training_action": task.get("action") or state.get("active_training_action") or "",
                "selected_accessory_ids": task.get("selected_accessory_ids") or state.get("selected_accessory_ids") or [],
                "sample_count": task.get("sample_count") or state.get("sample_count") or 0,
                "mode": task.get("train_mode") or task.get("mode") or task.get("model_variant") or state.get("mode") or "yolo",
                "epochs": task.get("epochs") or state.get("epochs") or 0,
                "image_size": task.get("image_size") or state.get("image_size") or 0,
                "dataset_id": task.get("dataset_id") or task.get("source_dataset_id") or state.get("dataset_id") or "",
                "owner_user_id": owner_user_id,
                "owner_username": owner_username,
                "updated_at": int(time.time()),
            }
        )
        store[owner_key] = state
        full_config["training_by_user_id"] = store
        current_training = full_config.get("training") if isinstance(full_config.get("training"), dict) else {}
        current_owner_key = self.normalize_training_owner_key(self.access.owner(current_training)) if current_training else ""
        if current_owner_key == owner_key or str(current_training.get("active_training_task_id") or "") == job_id:
            full_config["training"] = state
        self.storage.save(full_config)
        self.sync_pipeline(task)
