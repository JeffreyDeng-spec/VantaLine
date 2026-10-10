"""Register the current main's two operator routes before management routes."""
from dataclasses import dataclass
from typing import Any, Callable
from fastapi import Request, Response
from ..schemas.plc import PlcWebSerialConfigRequest, PlcWorkstationSelfPairRequest
from .workstation_self_service import WorkstationSelfService


@dataclass(frozen=True)
class SelfServiceRoutes:
    self_pair_plc_workstation: Callable[..., Any]
    self_config_plc_workstation: Callable[..., Any]


def register_workstation_self_service(app: Any, service: WorkstationSelfService) -> SelfServiceRoutes:
    @app.post("/api/plc/workstation/self-pair")
    def self_pair_plc_workstation(request: Request, response: Response, payload: PlcWorkstationSelfPairRequest) -> dict[str, Any]:
        return service.self_pair(request, response, payload)

    @app.post("/api/plc/workstation/self-config")
    def self_config_plc_workstation(request: Request, payload: PlcWebSerialConfigRequest) -> dict[str, Any]:
        return service.self_config(request, payload)

    return SelfServiceRoutes(self_pair_plc_workstation, self_config_plc_workstation)
