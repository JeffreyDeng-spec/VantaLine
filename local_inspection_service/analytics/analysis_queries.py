"""Analysis list/detail use cases with a narrow presentation boundary."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol

from .analysis_service import AnalysisRecords

Record = dict[str, Any]


class ProcessingItems(Protocol):
    def __call__(self, record: Record, *, include_auto_optimize: bool = True) -> list[Record]: ...


class PresentRecord(Protocol):
    def __call__(self, record: Record, *, detail: bool = False, include_debug: bool = False,
                 include_auto_optimize: bool = True, include_scope: bool = True,
                 processing_items: list[Record] | None = None) -> Record: ...


class TaskGroups(Protocol):
    def __call__(self, records: list[Record], *, include_auto_optimize: bool = True) -> list[Record]: ...


@dataclass(frozen=True)
class AnalysisPresentation:
    cache_scope: Callable[[], AbstractContextManager]
    processing_items: ProcessingItems
    record: PresentRecord
    task_groups: TaskGroups
    processing_summary: Callable[[list[Record]], Record]


class AnalysisQueries:
    def __init__(self, records: AnalysisRecords, presentation: AnalysisPresentation, batch_limit: int):
        self.records = records
        self.presentation = presentation
        self.batch_limit = batch_limit

    def list_records(self, user: Record,
        task_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        bounded_limit = max(1, min(int(limit or 100), 200))
        bounded_offset = max(0, int(offset or 0))
        task_records = self.records.data_analysis_records_for_user(user, target_user_id=user_id)
        records = [
            record
            for record in task_records
            if not str(task_id or "").strip() or str((record.get("task") or {}).get("id") or "") == str(task_id or "").strip()
        ]
        page = records[bounded_offset : bounded_offset + bounded_limit]
        # The list view must stay fast by skipping expensive required-scope rebuilds,
        # but it still includes task-execution image processing items for manual review.
        # The cache scope memoizes auto-optimize states and dataset manifests so each
        # is loaded once per request instead of once per record/sample, and the items
        # expansion below is computed once per record and shared with the page payload.
        with self.presentation.cache_scope():
            expanded = [
                (record, self.presentation.processing_items(record, include_auto_optimize=True))
                for record in records
            ]
            processing_items = [item for _, items in expanded for item in items]
            items_by_identity = {id(record): items for record, items in expanded}
            record_payloads = [
                self.presentation.record(
                    record,
                    include_auto_optimize=True,
                    include_scope=False,
                    processing_items=items_by_identity.get(id(record)),
                )
                for record in page
            ]
            task_groups = self.presentation.task_groups(task_records, include_auto_optimize=False)
        return {
            "records": record_payloads,
            "tasks": task_groups,
            "total": len(records),
            "limit": bounded_limit,
            "offset": bounded_offset,
            "batch_limit": self.batch_limit,
            "image_processing_summary": self.presentation.processing_summary(processing_items),
        }

    def get_record(self, user: Record, record_id: str) -> dict[str, Any]:
        record = self.records.find_data_analysis_record(record_id, user)
        with self.presentation.cache_scope():
            return {"record": self.presentation.record(record, detail=True, include_debug=self.records.access.is_admin(user))}
