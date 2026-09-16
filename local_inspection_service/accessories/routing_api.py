"""The route-selection HTTP endpoint at its existing registration position."""
from collections.abc import Callable
from typing import Any
from fastapi import FastAPI
from ..schemas.accessories import AccessoryRouteRequest
from .routing import AccessoryRouting


def register_routing_api(app: FastAPI, service: AccessoryRouting) -> Callable[[str, AccessoryRouteRequest], dict[str, Any]]:
    @app.post("/api/accessories/{accessory_id}/route")
    def set_accessory_route(accessory_id: str, request: AccessoryRouteRequest) -> dict[str, Any]:
        return service.set_accessory_route(accessory_id, request)

    return set_accessory_route
