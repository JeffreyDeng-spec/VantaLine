"""Pipeline accessory HTTP routes mounted in their original order."""
from typing import Any
from fastapi import FastAPI
from .accessory_routes import PipelineAccessoryRoutes


def register_pipeline_accessory_routes_api(app: FastAPI, controller: PipelineAccessoryRoutes):
    @app.post("/api/pipeline/accessories/{accessory_id}")
    def add_pipeline_accessory(accessory_id: str) -> dict[str, Any]:
        return controller.add(accessory_id)

    @app.delete("/api/pipeline/accessories/{accessory_id}")
    def remove_pipeline_accessory(accessory_id: str) -> dict[str, Any]:
        return controller.remove(accessory_id)

    return add_pipeline_accessory, remove_pipeline_accessory