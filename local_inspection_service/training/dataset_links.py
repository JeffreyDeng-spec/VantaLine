"""Mark training dataset links under the existing process-owned training guard."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
import time
from typing import Any

Record = dict[str, Any]


@dataclass(frozen=True)
class DatasetLinkRecords:
    load: Callable[[], list[Record]]
    save: Callable[[Record], None]
    dataset_id: Callable[[Record], str]


class TrainingDatasetLinks:
    def __init__(self, guard: Callable[[], AbstractContextManager], records: DatasetLinkRecords,
                 mutable: Callable[[Record, Record], bool], clean: Callable[[str], str]):
        self.guard, self.records, self.mutable, self.clean = guard, records, mutable, clean

    def mark_training_task_dataset_deleted(self, dataset_id: str, user: dict[str, Any]) -> int:
        clean_id = self.clean(dataset_id)
        if not clean_id:
            return 0
        now = int(time.time())
        changed = 0
        with self.guard():
            for task in self.records.load():
                if task.get("action") not in {"generate_samples", "train_model"}:
                    continue
                if self.records.dataset_id(task) != clean_id:
                    continue
                if not self.mutable(task, user):
                    continue
                task.update({"dataset_status": "deleted", "dataset_deleted_at": now, "updated_at": now})
                self.records.save(task)
                changed += 1
        return changed
