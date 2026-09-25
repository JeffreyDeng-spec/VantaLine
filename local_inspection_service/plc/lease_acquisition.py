"""Browser workstation lease claim and activation transitions."""
from typing import Any

from .lease_acquisition_ports import LeaseAcquisitionPorts


class LeaseAcquisition:
    def __init__(self, ports: LeaseAcquisitionPorts) -> None:
        self.ports = ports

    def claim(self, station_id: str, request: Any) -> dict[str, Any]:
        user = self.ports.current_user()()
        client_instance_id = str(request.client_instance_id or "").strip()
        model_id = str(request.model_id or "").strip()
        bundle_version = str(request.bundle_version or "").strip()
        if not self.ports.release_version()()["consistent"]:
            raise self.ports.config_error()("plc_release_version_mismatch")
        if not self.ports.fullmatch()(r"[A-Za-z0-9._:-]{8,160}", client_instance_id):
            raise self.ports.config_error()("invalid_client_instance_id")
        if bundle_version != self.ports.protocol_version():
            raise self.ports.config_error()("plc_browser_protocol_version_mismatch")
        self.ports.require_model_permission()(model_id or None)

        def mutate(state: dict[str, dict[str, Any] | None]) -> None:
            station = self.ports.record()(state.get("station"))
            if not station:
                raise self.ports.config_error()("plc_workstation_not_found")
            config = self.ports.migrate_config()(
                station.get("config") if isinstance(station.get("config"), dict) else {}
            )
            if not config["enabled"]:
                raise self.ports.config_error()("plc_workstation_disabled")
            now = int((state.get("clock") or {}).get("now") or self.ports.clock()())
            current = self.ports.record()(state.get("lease"))
            if current and current.get("state") in {"connecting", "active", "draining"} and int(current.get("expires_at") or 0) > now:
                raise self.ports.config_error()("plc_workstation_in_use")
            epoch = int((current or {}).get("lease_epoch") or 0) + 1
            lease = {
                "station_id": station_id,
                "session_id": f"plcwsess_{self.ports.uuid4()().hex}",
                "state": "connecting",
                "lease_epoch": epoch,
                "owner_user_id": str(user.get("id") or ""),
                "model_id": model_id,
                "client_instance_id": client_instance_id,
                "bundle_version": bundle_version,
                "config_generation": int(station.get("config_generation") or 0),
                "heartbeat_at": now,
                "expires_at": now + self.ports.connecting_ttl(),
                "serial_info": {},
            }
            state["lease"] = self.ports.lease_row()(lease)

        state = self.ports.mutate()(station_id, None, mutate)
        lease = self.ports.record()(state.get("lease"))
        if not lease:
            raise self.ports.config_error()("plc_lease_persist_failed")
        return lease

    def activate(self, station_id: str, request: Any) -> dict[str, Any]:
        user_id = str((self.ports.current_user()() or {}).get("id") or "")

        def mutate(state: dict[str, dict[str, Any] | None]) -> None:
            lease = self.ports.record()(state.get("lease"))
            station = self.ports.record()(state.get("station"))
            now = int((state.get("clock") or {}).get("now") or self.ports.clock()())
            if not lease or not station:
                raise self.ports.config_error()("plc_workstation_lease_missing")
            if lease.get("session_id") != request.session_id or int(lease.get("lease_epoch") or -1) != int(request.lease_epoch):
                raise self.ports.config_error()("plc_workstation_lease_fenced")
            if lease.get("owner_user_id") != user_id or lease.get("state") != "connecting" or int(lease.get("expires_at") or 0) <= now:
                raise self.ports.config_error()("plc_workstation_lease_expired")
            if int(lease.get("config_generation") or -1) != int(station.get("config_generation") or 0):
                raise self.ports.config_error()("plc_workstation_generation_changed")
            lease["state"] = "active"
            lease["heartbeat_at"] = now
            lease["expires_at"] = now + self.ports.active_ttl()
            lease["serial_info"] = {
                "usb_vendor_id": request.usb_vendor_id,
                "usb_product_id": request.usb_product_id,
            }
            state["lease"] = self.ports.lease_row()(lease)

        state = self.ports.mutate()(station_id, None, mutate)
        return self.ports.record()(state.get("lease")) or {}
