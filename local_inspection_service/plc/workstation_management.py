"""Five workstation-management flows; state and protocol remain caller-owned."""
from typing import Any

from .workstation_management_ports import (
    WorkstationAccess, WorkstationErrors, WorkstationMutation, WorkstationProjection,
)


class WorkstationManagement:
    def __init__(self, access: WorkstationAccess, projection: WorkstationProjection,
                 mutation: WorkstationMutation, errors: WorkstationErrors) -> None:
        self.access = access
        self.projection = projection
        self.mutation = mutation
        self.errors = errors

    def get(self, request: Any) -> dict[str, Any]:
        station = self.access.station_from_request()(request)
        return self.projection.station_payload()(station) if station else self.projection.unpaired_payload()()

    def list(self) -> dict[str, Any]:
        self.access.require_permission()("system_settings")
        return {"items": self.projection.list_workstations()()}

    def pair(self, request: Any, response: Any, payload: Any) -> dict[str, Any]:
        self.access.require_permission()("system_settings")
        try:
            return self.mutation.pair()(request, response, payload.name, payload.station_id)
        except self.errors.config_error() as exc:
            raise self.errors.http_error()(status_code=400, detail=str(exc)) from exc

    def update_config(self, request: Any, payload: Any) -> dict[str, Any]:
        self.access.require_permission()("system_settings")
        station = self.access.require_station()(request)
        try:
            return self.mutation.update_config()(str(station["id"]), payload.model_dump())
        except self.errors.config_error() as exc:
            raise self.errors.http_error()(status_code=400, detail=str(exc)) from exc

    def verify_profile(self, request: Any, payload: Any) -> dict[str, Any]:
        self.access.require_permission()("system_settings")
        station = self.access.require_station()(request)
        try:
            return self.mutation.set_verified()(str(station["id"]), payload.verified)
        except self.errors.config_error() as exc:
            raise self.errors.http_error()(status_code=400, detail=str(exc)) from exc
