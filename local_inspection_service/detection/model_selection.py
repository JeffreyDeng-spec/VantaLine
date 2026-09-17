"""Select detection specifications without owning models or request identity."""
from collections.abc import Callable
from typing import Any
from fastapi import HTTPException
from .task_catalog import TrainedSpecs

Record = dict[str, Any]


class ModelSelection:
    def __init__(self, specialized: Callable[[Record | None], list[Record]], trained: TrainedSpecs,
                 registry: Callable[[], dict[str, Record]], default_id: Callable[[], str],
                 removed: Callable[[str], None]):
        self.specialized, self.trained, self.registry = specialized, trained, registry
        self.default_id, self.removed = default_id, removed

    def selected_model_spec(self, model_id: str | None, config: dict[str, Any] | None = None) -> dict[str, Any]:
        explicit_model = bool(model_id)
        requested = model_id or (config or {}).get("active_model_id") or self.default_id()
        if requested == "label_sheet_local_match":
            if explicit_model:
                self.removed("Label Sheet")
            requested = self.default_id()
        for spec in self.specialized(config):
            if spec["id"] == requested:
                return spec
        try:
            trained_specs = self.trained(config)
        except TypeError:
            trained_specs = self.trained()
        for spec in trained_specs:
            if spec["id"] == requested:
                return spec
        if requested not in self.registry():
            raise HTTPException(status_code=400, detail=f"Unknown model_id: {requested}")
        return self.registry()[requested]

