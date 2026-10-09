"""Training task persistence and account configuration around the same owner."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from ..runtime.training_tasks import TrainingTaskRuntime
from .state_composition import TrainingStateWorkflows, TrainingRecordAccess
from .record_store import TrainingRows
from .task_lifecycle import TrainingTaskWrites, RequireTrainingAccess
from .task_views import TrainingViewAccess
from .user_state import TrainingUserState, TrainingStateAccess, TrainingStateStorage

Record = dict[str, Any]


@dataclass(frozen=True)
class TrainingConfiguration:
    load: Callable[[], Record]
    save: Callable[[Record], None]


class TrainingAccountState:
    def __init__(self, *, runtime: TrainingTaskRuntime, storage: TrainingRecordAccess,
                 rows: TrainingRows, writes: TrainingTaskWrites,
                 require_access: RequireTrainingAccess, view_access: TrainingViewAccess,
                 defaults: Callable[[], Record], legacy_owner: Callable[[], str],
                 access: TrainingStateAccess, configuration: TrainingConfiguration,
                 sync_pipeline: Callable[[Record], None]):
        self.records = TrainingStateWorkflows(
            runtime=runtime, storage=storage, rows=rows, writes=writes,
            require_access=require_access, view_access=view_access,
        )
        self.users = TrainingUserState(
            defaults=defaults, legacy_owner=legacy_owner, access=access,
            storage=TrainingStateStorage(
                find=lambda job_id: self.records.find_training_task(job_id),
                load=configuration.load, save=configuration.save,
            ),
            sync_pipeline=sync_pipeline,
        )

    def default_training_state(self) -> Record:
        return self.users.default_training_state()

    def normalize_training_owner_key(self, owner_user_id: Any) -> str:
        return self.users.normalize_training_owner_key(owner_user_id)

    def training_state_store(self, config: Record) -> dict[str, Record]:
        return self.users.training_state_store(config)

    def sanitize_training_state_for_user(self, training: Record | None, user: Record,
                                         selected_ids: set[str], target_user_id: str | None = None) -> Record:
        return self.users.sanitize_training_state_for_user(training, user, selected_ids, target_user_id)

    def training_state_for_user(self, config: Record, user: Record, selected_ids: set[str],
                                target_user_id: str | None = None) -> Record:
        return self.users.training_state_for_user(config, user, selected_ids, target_user_id)

    def set_training_state_for_user(self, config: Record, user: Record, training_state: Record) -> None:
        return self.users.set_training_state_for_user(config, user, training_state)

    def sync_training_state_from_task(self, job_id: str) -> None:
        return self.users.sync_training_state_from_task(job_id)
