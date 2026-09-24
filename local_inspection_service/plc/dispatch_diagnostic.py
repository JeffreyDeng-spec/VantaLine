"""Five PLC dispatch/diagnostic HTTP flows; state and evidence stay caller-owned."""
from typing import Any

from .dispatch_diagnostic_ports import DispatchAccess, DispatchErrors, DispatchMutation


class DispatchDiagnostic:
    def __init__(self, access: DispatchAccess, mutation: DispatchMutation, errors: DispatchErrors) -> None:
        self.access = access
        self.mutation = mutation
        self.errors = errors

    def _run(self, request: Any, payload: Any, callee: Any, *,
             dispatch_id: Any = None, has_dispatch: bool = False, admin: bool = False) -> dict[str, Any]:
        if admin:
            self.access.require_permission()("system_settings")
        station = self.access.require_station()(request)
        try:
            if has_dispatch:
                return callee()(str(station["id"]), dispatch_id, payload)
            return callee()(str(station["id"]), payload)
        except self.errors.config_error() as exc:
            raise self.errors.http_error()(status_code=409, detail=str(exc)) from exc

    def declare_attempt(self, dispatch_id: str, request: Any, payload: Any) -> dict[str, Any]:
        return self._run(request, payload, self.mutation.declare_attempt, dispatch_id=dispatch_id, has_dispatch=True)

    def diagnostic_plan(self, request: Any, payload: Any) -> dict[str, Any]:
        return self._run(request, payload, self.mutation.diagnostic_plan, admin=True)

    def diagnostic_receipt(self, request: Any, payload: Any) -> dict[str, Any]:
        return self._run(request, payload, self.mutation.diagnostic_receipt, admin=True)

    def diagnostic_confirm(self, request: Any, payload: Any) -> dict[str, Any]:
        return self._run(request, payload, self.mutation.diagnostic_confirm, admin=True)

    def record_receipt(self, dispatch_id: str, request: Any, payload: Any) -> dict[str, Any]:
        return self._run(request, payload, self.mutation.record_receipt, dispatch_id=dispatch_id, has_dispatch=True)
