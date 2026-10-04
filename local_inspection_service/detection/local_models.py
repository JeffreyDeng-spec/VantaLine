"""Process-local model instances and path aliases, isolated from web application imports."""
from collections.abc import Callable
from pathlib import Path
from typing import Any, Generic, TypeVar
from .task_catalog import TrainedSpecs
from ..storage.artifacts.files import BusinessFiles

Record = dict[str, Any]
Model = TypeVar("Model")


class LocalModels(Generic[Model]):
    def __init__(self, select: Callable[[str | None, Record | None], Record],
                 factory: Callable[[], Callable[[str], Model]], legacy_specs: Callable[[], list[Record]],
                 trained_specs: TrainedSpecs, *, files=None):
        self.select, self.factory = select, factory
        self.legacy_specs, self.trained_specs = legacy_specs, trained_specs
        self.models: dict[str, Model] = {}
        self.paths: dict[str, Path] = {}
        self.files = files if files is not None else BusinessFiles()

    def model(self, model_id=None, config=None):
        if self.files.runtime_provider() is None:
            return self._local_model(model_id, config)
        return self._cos_model(model_id, config)

    def _local_model(self, model_id: str | None = None, config: dict[str, Any] | None = None) -> Model:
        spec = self.select(model_id, config)
        if spec.get("is_ai_detection"):
            raise RuntimeError("AI Detection does not use a local YOLO model")
        if spec.get("is_label_sheet_match"):
            raise RuntimeError("Label sheet matching does not use a local YOLO model")
        model_id = str(spec["id"])
        model_path = Path(spec["path"])
        if model_id not in self.models:
            if not model_path.exists():
                raise RuntimeError(f"Model file not found: {model_path}")
            resolved_model_path = model_path.resolve()
            for cached_id, cached_path in list(self.paths.items()):
                if cached_path == resolved_model_path and cached_id in self.models:
                    self.models[model_id] = self.models[cached_id]
                    self.paths[model_id] = resolved_model_path
                    return self.models[model_id]
            self.models[model_id] = self.factory()(str(model_path))
            self.paths[model_id] = resolved_model_path
        return self.models[model_id]

    def _cos_model(self, model_id: str | None = None, config: dict[str, Any] | None = None) -> Model:
        spec = self.select(model_id, config)
        if spec.get("is_ai_detection"):
            raise RuntimeError("AI Detection does not use a local YOLO model")
        if spec.get("is_label_sheet_match"):
            raise RuntimeError("Label sheet matching does not use a local YOLO model")
        model_id = str(spec["id"])
        model_path = Path(spec["path"])
        if model_id not in self.models:
            if not self.files.is_file(model_path):
                raise RuntimeError(f"Model file not found: {model_path}")
            resolved_model_path = model_path.resolve()
            for cached_id, cached_path in list(self.paths.items()):
                if cached_path == resolved_model_path and cached_id in self.models:
                    self.models[model_id] = self.models[cached_id]
                    self.paths[model_id] = resolved_model_path
                    return self.models[model_id]
            with self.files.local_file(model_path) as local_path:
                self.models[model_id] = self.factory()(str(local_path))
            self.paths[model_id] = resolved_model_path
        return self.models[model_id]

    def yolo_loaded_model_ids(self, config: dict[str, Any]) -> list[str]:
        loaded_paths = set(self.paths.values())
        ids = set(self.models.keys())
        if not loaded_paths:
            return sorted(ids)
        specs = [
            *self.legacy_specs(),
            *self.trained_specs(config),
        ]
        for spec in specs:
            if spec.get("is_ai_detection") or spec.get("is_label_sheet_match"):
                continue
            try:
                model_path = Path(spec.get("path") or "").resolve()
            except (TypeError, OSError):
                continue
            if model_path in loaded_paths:
                ids.add(str(spec.get("id") or ""))
        return sorted(item for item in ids if item)

    def yolo_model_ready(self, model_id: str, config: dict[str, Any]) -> bool:
        return str(model_id or "") in set(self.yolo_loaded_model_ids(config))
