"""Browser diagnostic reservation state transition; serial I/O stays in the browser."""
from typing import Any

from .diagnostic_state_ports import DiagnosticStatePorts


class DiagnosticState:
    def __init__(self, ports: DiagnosticStatePorts) -> None:
        self.ports = ports

    def plan(self, station_id: str, request: Any) -> dict[str, Any]:
        plan: dict[str, Any] = {}
        diagnostic_id = "plcdiag_" + self.ports.token_hex()(16)
        attempt_token = self.ports.token_urlsafe()(32)

        def validate(state: dict[str, dict[str, Any] | None]) -> None:
            nonlocal plan
            station, lease, now = self.ports.active_lease()(
                state, request.session_id, request.lease_epoch
            )
            if int(station.get("config_generation") or 0) != int(request.config_generation):
                raise self.ports.config_error()("plc_workstation_generation_changed")
            in_flight_id = str(lease.get("in_flight_dispatch_id") or "")
            in_flight_deadline = int(lease.get("in_flight_deadline_at") or 0)
            if in_flight_id and in_flight_deadline > now:
                raise self.ports.config_error()("plc_workstation_dispatch_in_flight")
            issued_at_ms = int(self.ports.clock()() * 1000)
            deadline_at_ms = issued_at_ms + 2000
            deadline_at = int(self.ports.ceil()(deadline_at_ms / 1000))
            lease["in_flight_dispatch_id"] = diagnostic_id
            lease["in_flight_deadline_at"] = deadline_at
            lease["diagnostic_token_hash"] = self.ports.token_hash()(attempt_token)
            state["lease"] = self.ports.lease_row()(lease)
            plan = {
                "diagnostic_id": diagnostic_id,
                "attempt_token": attempt_token,
                "protocol_version": self.ports.protocol_version(),
                "register": "D206",
                "write_value": 6,
                "issued_at": now,
                "deadline_at_ms": deadline_at_ms,
                "execution_window_ms": 2000,
                "ack_timeout_ms": 500,
                "read_timeout_ms": 500,
                "frames": self.ports.frames()(),
            }

        self.ports.mutate()(station_id, None, validate)
        return plan
