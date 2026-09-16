"""Analysis HTTP routes mounted in original order by the composition root."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from fastapi import FastAPI
from .analysis_queries import AnalysisQueries


@dataclass(frozen=True)
class AnalysisRoutes:
    list_records: Callable[..., dict[str, Any]]
    get_record: Callable[[str], dict[str, Any]]
    delete_record: Callable[[str], dict[str, Any]]
    locate_record: Callable[[str], dict[str, Any]]
    locate_batch: Callable[[], dict[str, Any]]


def register_analysis_api(app: FastAPI, current_user: Callable[[], dict[str, Any]],
                          removed_feature: Callable[[str], Any], queries: AnalysisQueries) -> AnalysisRoutes:
    @app.get("/api/data-analysis/records")
    def list_data_analysis_records_api(task_id: str | None = None, user_id: str | None = None,
                                       limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return queries.list_records(current_user(), task_id=task_id, user_id=user_id, limit=limit, offset=offset)

    @app.get("/api/data-analysis/records/{record_id}")
    def get_data_analysis_record_api(record_id: str) -> dict[str, Any]:
        return queries.get_record(current_user(), record_id)

    @app.delete("/api/data-analysis/records/{record_id}")
    def delete_data_analysis_record_api(record_id: str) -> dict[str, Any]:
        deleted_record_id = queries.records.delete_data_analysis_record(record_id, current_user())
        return {"status": "deleted", "record_id": deleted_record_id}

    @app.post("/api/data-analysis/records/{record_id}/locate")
    def run_data_analysis_record_locate_api(record_id: str) -> dict[str, Any]:
        removed_feature("LocateAnything data-analysis comparison")

    @app.post("/api/data-analysis/locate")
    def run_data_analysis_batch_locate_api() -> dict[str, Any]:
        removed_feature("LocateAnything data-analysis comparison")

    return AnalysisRoutes(list_data_analysis_records_api, get_data_analysis_record_api,
                          delete_data_analysis_record_api, run_data_analysis_record_locate_api,
                          run_data_analysis_batch_locate_api)
