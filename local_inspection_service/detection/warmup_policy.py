"""Warmup admission settings and ordered pipeline/trained model candidates."""
from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any
from .task_catalog import TrainedSpecs

Record = dict[str, Any]


def yolo_warmup_enabled() -> bool:
    return os.environ.get("VANTALINE_YOLO_PREWARM", "1").strip().lower() not in {"0", "false", "no", "off"}


def yolo_warmup_limit() -> int:
    try:
        return max(1, min(12, int(os.environ.get("VANTALINE_YOLO_PREWARM_LIMIT", "6"))))
    except (TypeError, ValueError):
        return 6


@dataclass(frozen=True)
class WarmupPipeline:
    tasks: Callable[[], list[Record]]
    method: Callable[[], Callable[[str], str]]
    status: Callable[[Record], str]
    model_id: Callable[[Record], str]


@dataclass(frozen=True)
class WarmupModels:
    default_id: Callable[[], str]
    trained: TrainedSpecs
    resolve: Callable[[], Callable[[str], Path]]


class WarmupCandidates:
    def __init__(self, pipeline: WarmupPipeline, models: WarmupModels, limit: Callable[[], int]):
        self.pipeline, self.models, self.limit = pipeline, models, limit

    def yolo_warmup_configured_model_ids(self, config: dict[str, Any]) -> list[str]:
        explicit = [
            item.strip()
            for item in os.environ.get("VANTALINE_YOLO_PREWARM_MODELS", "").split(",")
            if item.strip()
        ]
        if explicit:
            return explicit[: self.limit()]
        ids: list[str] = []
        active_model_id = str(config.get("active_model_id") or self.models.default_id()).strip()
        if active_model_id:
            ids.append(active_model_id)
        pipeline_tasks = sorted(
            [
                task for task in self.pipeline.tasks()
                if isinstance(task, dict)
                and str(task.get("stage") or "") == "library"
                and self.pipeline.method()(str(task.get("detection_method") or "")) in {"yolo", "yolo_ocr"}
                and self.pipeline.status(task) == "available"
            ],
            key=lambda task: int(task.get("updated_at") or task.get("created_at") or 0),
            reverse=True,
        )
        for task in pipeline_tasks:
            model_id = self.pipeline.model_id(task)
            if model_id:
                ids.append(model_id)
            if len(ids) >= self.limit():
                break
        trained_specs = sorted(
            [spec for spec in self.models.trained(config) if not spec.get("is_ai_detection") and not spec.get("is_label_sheet_match")],
            key=lambda spec: int(spec.get("updated_at") or spec.get("created_at") or 0),
            reverse=True,
        )
        seen_paths: set[str] = set()
        for spec in trained_specs:
            path = str(self.models.resolve()(spec.get("path") or spec.get("artifact_path") or ""))
            if path in seen_paths:
                continue
            seen_paths.add(path)
            model_id = str(spec.get("id") or "").strip()
            if model_id:
                ids.append(model_id)
            if len(ids) >= self.limit():
                break
        result: list[str] = []
        seen_ids: set[str] = set()
        for model_id in ids:
            if model_id and model_id not in seen_ids:
                seen_ids.add(model_id)
                result.append(model_id)
        return result[: self.limit()]

