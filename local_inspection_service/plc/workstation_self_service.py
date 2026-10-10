"""Operator-owned workstation setup with explicit request-time capabilities."""
from dataclasses import dataclass
from typing import Any, Callable
from .workstation_management_ports import WorkstationErrors, Getter


@dataclass(frozen=True)
class OperatorIdentity:
    current_user: Getter
    has_permission: Getter


@dataclass(frozen=True)
class SelfServiceStation:
    station_from_request: Getter
    require_station: Getter
    station_payload: Getter
    pair: Getter
    update_config: Getter


@dataclass(frozen=True)
class SelfPairRecords:
    record: Getter
    row: Getter
    mutate: Getter
    clock: Callable[[], float]


class WorkstationSelfService:
    def __init__(self, identity: OperatorIdentity, station: SelfServiceStation,
                 records: SelfPairRecords, errors: WorkstationErrors) -> None:
        self.identity = identity
        self.station = station
        self.records = records
        self.errors = errors

    def require_operator(self) -> None:
        user = self.identity.current_user()()
        if not user:
            raise self.errors.http_error()(status_code=401, detail="Authentication required")
        if not any(self.identity.has_permission()(user, permission) for permission in ("inspection", "ai_detection")):
            raise self.errors.http_error()(status_code=403, detail="Inspection permission required")

    def self_pair(self, request: Any, response: Any, payload: Any) -> dict[str, Any]:
        self.require_operator()
        station = self.station.station_from_request()(request)
        if station:
            if payload.name is not None:
                name = " ".join(payload.name.split())
                if not name:
                    raise self.errors.http_error()(status_code=400, detail="工作站名称不能为空")
                def rename(state):
                    record = self.records.record()(state.get("station"))
                    if not record:
                        raise self.errors.config_error()("plc_workstation_not_found")
                    record.update(name=name, updated_at=int(self.records.clock()))
                    state["station"] = self.records.row()(record)
                state = self.records.mutate()(str(station["id"]), None, rename)
                station = self.records.record()(state.get("station"))
            return self.station.station_payload()(station)
        try:
            return self.station.pair()(request, response, payload.name or "产线电脑")
        except self.errors.config_error() as exc:
            raise self.errors.http_error()(status_code=400, detail=str(exc)) from exc

    def self_config(self, request: Any, payload: Any) -> dict[str, Any]:
        self.require_operator()
        station = self.station.require_station()(request)
        try:
            return self.station.update_config()(str(station["id"]), payload.model_dump(), require_disconnected=True)
        except self.errors.config_error() as exc:
            if str(exc) == "plc_workstation_in_use_disconnect_before_config":
                raise self.errors.http_error()(status_code=409, detail="请先断开本机 PLC 连接，再修改配置。") from exc
            raise self.errors.http_error()(status_code=400, detail=str(exc)) from exc
