"""Five connection-lease HTTP flows; the lease state machine stays caller-owned."""
from typing import Any

from .connection_lease_ports import LeaseAccess, LeaseErrors, LeaseMutation


class ConnectionLease:
    def __init__(self, access: LeaseAccess, mutation: LeaseMutation, errors: LeaseErrors) -> None:
        self.access = access
        self.mutation = mutation
        self.errors = errors

    def _run(self, request: Any, payload: Any, callee: Any, *, model_permission: bool = False) -> dict[str, Any]:
        station = self.access.require_station()(request)
        if model_permission:
            self.access.require_model_permission()(payload.model_id)
        try:
            return callee()(str(station["id"]), payload)
        except self.errors.config_error() as exc:
            raise self.errors.http_error()(status_code=409, detail=str(exc)) from exc

    def claim(self, request: Any, payload: Any) -> dict[str, Any]:
        return self._run(request, payload, self.mutation.claim)

    def activate(self, request: Any, payload: Any) -> dict[str, Any]:
        return self._run(request, payload, self.mutation.activate)

    def heartbeat(self, request: Any, payload: Any) -> dict[str, Any]:
        return self._run(request, payload, self.mutation.heartbeat)

    def rebind_model(self, request: Any, payload: Any) -> dict[str, Any]:
        return self._run(request, payload, self.mutation.rebind_model, model_permission=True)

    def disconnect(self, request: Any, payload: Any) -> dict[str, Any]:
        return self._run(request, payload, self.mutation.disconnect)
