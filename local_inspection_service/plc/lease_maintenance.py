"""Browser lease heartbeat and release state transitions."""
from typing import Any

from .lease_maintenance_ports import LeaseMaintenancePorts


class LeaseMaintenance:
    def __init__(self, ports: LeaseMaintenancePorts) -> None:
        self.ports = ports

    def heartbeat(self, station_id: str, request: Any) -> dict[str, Any]:
        user_id = str((self.ports.current_user()() or {}).get("id") or "")

        def mutate(state: dict[str, dict[str, Any] | None]) -> None:
            lease = self.ports.record()(state.get("lease"))
            station = self.ports.record()(state.get("station"))
            now = int((state.get("clock") or {}).get("now") or self.ports.clock()())
            if not lease or not station:
                raise self.ports.config_error()("plc_workstation_lease_missing")
            valid = (
                lease.get("session_id") == request.session_id
                and int(lease.get("lease_epoch") or -1) == int(request.lease_epoch)
                and lease.get("owner_user_id") == user_id
                and lease.get("state") == "active"
                and int(lease.get("expires_at") or 0) > now
                and int(lease.get("config_generation") or -1) == int(station.get("config_generation") or 0)
            )
            if not valid:
                raise self.ports.config_error()("plc_workstation_lease_fenced")
            lease["heartbeat_at"] = now
            lease["expires_at"] = now + self.ports.active_ttl()
            if str(lease.get("in_flight_dispatch_id") or "").startswith("plcweb_"):
                lease["in_flight_deadline_at"] = lease["expires_at"]
            state["lease"] = self.ports.lease_row()(lease)

        state = self.ports.mutate()(station_id, None, mutate)
        return self.ports.record()(state.get("lease")) or {}

    def release(self, station_id: str, request: Any) -> dict[str, Any]:
        user_id = str((self.ports.current_user()() or {}).get("id") or "")

        def mutate(state: dict[str, dict[str, Any] | None]) -> None:
            lease = self.ports.record()(state.get("lease"))
            now = int((state.get("clock") or {}).get("now") or self.ports.clock()())
            if not lease:
                return
            if lease.get("session_id") == request.session_id and int(lease.get("lease_epoch") or -1) == int(request.lease_epoch) and lease.get("owner_user_id") == user_id:
                in_flight_deadline = int(lease.get("in_flight_deadline_at") or 0)
                lease["state"] = "draining" if in_flight_deadline > now else "released"
                lease["heartbeat_at"] = now
                lease["expires_at"] = max(now, in_flight_deadline)
                state["lease"] = self.ports.lease_row()(lease)

        state = self.ports.mutate()(station_id, None, mutate)
        return self.ports.record()(state.get("lease")) or {"state": "released"}
