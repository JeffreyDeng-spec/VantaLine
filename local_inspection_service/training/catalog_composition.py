"""Compose model queries and pipeline linkage without application-entry imports."""
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..detection.local_models import LocalModels, ModelFiles
from ..detection.model_selection import ModelSelection
from ..pipeline.training_links import PipelineTrainedModelLink, TrainingLinks
from .file_ports import ModelCatalogFiles
from .model_catalog import (
    TrainedModelCatalog, TrainingAccess, TrainingAccessories, TrainingFiles, TrainingPipeline,
)
from .task_lookup import (
    LookupCache, LookupRows, TaskFinder, TrainingRepository, TrainingTaskLookup,
)

Record = dict[str, Any]


class CatalogFiles(ModelFiles, ModelCatalogFiles, Protocol):
    """Shared model artifact capabilities for this owner's query graph."""


@dataclass(frozen=True)
class ModelRunFiles:
    roots: Callable[[], Sequence[Path]]
    task_path: Callable[[], Callable[[str], Path]]
    read: Callable[[Path], Any]
    output: Callable[[], Path]
    resolve: Callable[[], Callable[[str], Path]]


@dataclass(frozen=True)
class ModelPipeline:
    tasks: Callable[[], list[Record]]
    name: Callable[[Record], str]
    method: Callable[[], Callable[[str], str]]


@dataclass(frozen=True)
class ModelRegistry:
    specialized: Callable[[Record | None], list[Record]]
    registry: Callable[[], dict[str, Record]]
    default_id: Callable[[], str]
    removed: Callable[[str], None]
    factory: Callable[[], Callable[[str], Any]]


class ModelCatalog:
    """One inert graph with operation-time identity and database selection.

    Queries stay separate from the existing task mutation/storage services.
    Lookup snapshots are created per operation, never during construction.
    No query resolves back through an application-entry compatibility function.
    """
    def __init__(self, *, repository: Callable[[], TrainingRepository | None],
                 file_loader: Callable[[], TaskFinder], cache: LookupCache, rows: LookupRows,
                 config: Callable[[], Record], runs: ModelRunFiles,
                 accessories: TrainingAccessories, pipeline: ModelPipeline,
                 access: TrainingAccess, rules: Callable[[Record, Record], Record],
                 registry: ModelRegistry, files: CatalogFiles):
        self.registry = registry
        self.files = files
        self.lookup = TrainingTaskLookup(repository, file_loader, cache, rows)
        self.links = TrainingLinks(pipeline.tasks, pipeline.name)
        self.catalog = TrainedModelCatalog(
            config,
            TrainingFiles(
                roots=runs.roots, finder=lambda: self.lookup.training_task_finder(),
                task_path=runs.task_path, read=runs.read, output=runs.output, resolve=runs.resolve,
            ),
            accessories,
            TrainingPipeline(tasks=pipeline.tasks,
                link=lambda: self.links.pipeline_task_link_for_training_run,
                method=pipeline.method),
            access, rules, business_files=files,
        )
        self.selection = ModelSelection(
            registry.specialized, lambda *args: self.catalog.list_trained_model_specs(*args),
            registry.registry, registry.default_id, registry.removed,
        )
        self.local = LocalModels(
            select=lambda model_id, config: self.selection.selected_model_spec(model_id, config),
            factory=registry.factory, legacy_specs=lambda: self.legacy_model_specs(),
            trained_specs=lambda *args: self.catalog.list_trained_model_specs(*args), files=files,
        )
        self.pipeline_link = PipelineTrainedModelLink(
            catalog=lambda: self.catalog.list_trained_model_specs,
        )

    def legacy_model_specs(self) -> list[Record]:
        specs = []
        for spec in self.registry.registry().values():
            variant = spec.get("variant") or ("yolo_ocr" if spec.get("uses_ocr") else "yolo")
            specs.append({**spec, "is_legacy": not bool(spec.get("is_ai_detection") or spec.get("is_label_sheet_match")), "variant": variant})
        return specs
