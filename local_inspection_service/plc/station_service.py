"""Workstation pairing, configuration and projections; browser retains physical I/O."""
from dataclasses import dataclass
import hashlib
import hmac
import secrets
import time
import uuid
from typing import Any
from fastapi import Request, Response
from .station_ports import StationStorage, StationIdentity, StationPolicy, StationProjection

@dataclass(frozen=True)
class PlcStationService:
    storage: StationStorage
    identity: StationIdentity
    policy: StationPolicy
    projection: StationProjection

    def _plc_web_serial_token_hash(self, token: str) -> str:
        return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


    def plc_web_serial_station_from_request(self, request: Request) -> dict[str, Any] | None:
        token = str(request.cookies.get(self.identity.PLC_WORKSTATION_COOKIE()) or "").strip()
        if not token:
            return None
        token_hash = self.identity._plc_web_serial_token_hash()(token)
        repository = self.storage.runtime_postgres_repository_or_none()()
        if repository is not None:
            return self.storage._plc_web_serial_record()(
                repository.fetch_one_by_columns("plc_workstations", {"token_hash": token_hash})
            )
        with self.storage._config_io_lock():
            for row in self.storage._plc_web_serial_load_local()()["workstations"].values():
                record = self.storage._plc_web_serial_record()(row)
                if record and hmac.compare_digest(str(record.get("token_hash") or ""), token_hash):
                    return record
        return None


    def require_plc_web_serial_station(self, request: Request) -> dict[str, Any]:
        station = self.identity.plc_web_serial_station_from_request()(request)
        if not station:
            raise self.policy.HTTPException()(status_code=409, detail="plc_workstation_not_paired")
        return station


    def plc_web_serial_current_lease(self, station_id: str) -> dict[str, Any] | None:
        repository = self.storage.runtime_postgres_repository_or_none()()
        if repository is not None:
            return self.storage._plc_web_serial_record()(
                repository.fetch_by_primary_key("plc_workstation_leases", {"station_id": station_id})
            )
        with self.storage._config_io_lock():
            return self.storage._plc_web_serial_record()(self.storage._plc_web_serial_load_local()()["leases"].get(station_id))


    def plc_web_serial_recent_dispatches(self, station_id: str, limit: int = 20) -> list[dict[str, Any]]:
        repository = self.storage.runtime_postgres_repository_or_none()()
        if repository is not None:
            rows = repository.fetch_all("plc_web_serial_dispatches")
        else:
            with self.storage._config_io_lock():
                rows = list(self.storage._plc_web_serial_load_local()()["dispatches"].values())
        records = [record for record in (self.storage._plc_web_serial_record()(row) for row in rows) if record and record.get("station_id") == station_id]
        now = int(time.time())
        for record in records:
            if record.get("status") != "browser_attempt_declared" or int(record.get("deadline_at") or 0) > now:
                continue

            def expire_attempt(state: dict[str, dict[str, Any] | None]) -> None:
                current = self.storage._plc_web_serial_record()(state.get("dispatch"))
                database_now = int((state.get("clock") or {}).get("now") or time.time())
                if current and current.get("status") == "browser_attempt_declared" and int(current.get("deadline_at") or 0) <= database_now:
                    current["status"] = "uncertain"
                    current["outcome"] = "uncertain"
                    current["error_code"] = "browser_receipt_missing_after_deadline"
                    current["updated_at"] = database_now
                    state["dispatch"] = self.storage._plc_web_serial_dispatch_row()(current)
                    lease = self.storage._plc_web_serial_record()(state.get("lease"))
                    if lease and lease.get("in_flight_dispatch_id") == current.get("dispatch_id"):
                        lease.pop("in_flight_dispatch_id", None)
                        lease.pop("in_flight_deadline_at", None)
                        if lease.get("state") == "draining":
                            lease["state"] = "released"
                            lease["expires_at"] = database_now
                        state["lease"] = self.storage._plc_workstation_lease_row()(lease)

            reconciled = self.storage._plc_web_serial_mutate()(station_id, str(record["dispatch_id"]), expire_attempt)
            updated = self.storage._plc_web_serial_record()(reconciled.get("dispatch"))
            if updated:
                record.clear()
                record.update(updated)
        return sorted(records, key=lambda item: int(item.get("updated_at") or 0), reverse=True)[:limit]


    def plc_web_serial_ensure_current_station_contract(self, station: dict[str, Any]) -> dict[str, Any]:
        raw_config = station.get("config") if isinstance(station.get("config"), dict) else {}
        try:
            self.policy.normalize_web_serial_config()(raw_config)
            return station
        except self.policy.PlcConfigError():
            migrated = self.policy.migrate_web_serial_config()(raw_config)

        station_id = str(station.get("id") or "")
        if not station_id:
            raise self.policy.PlcConfigError()("plc_workstation_not_found")

        def upgrade(state: dict[str, dict[str, Any] | None]) -> None:
            current = self.storage._plc_web_serial_record()(state.get("station"))
            if not current:
                raise self.policy.PlcConfigError()("plc_workstation_not_found")
            current_raw = current.get("config") if isinstance(current.get("config"), dict) else {}
            try:
                self.policy.normalize_web_serial_config()(current_raw)
                return
            except self.policy.PlcConfigError():
                current_migrated = self.policy.migrate_web_serial_config()(current_raw)
            now = int((state.get("clock") or {}).get("now") or time.time())
            current["config"] = current_migrated
            current["config_generation"] = int(current.get("config_generation") or 0) + 1
            current["profile_verified"] = False
            current["profile_verified_fingerprint"] = ""
            current["status"] = "commissioning"
            current["updated_at"] = now
            state["station"] = self.storage._plc_workstation_row()(current)
            lease = self.storage._plc_web_serial_record()(state.get("lease"))
            if lease and lease.get("state") in {"connecting", "active", "draining"}:
                in_flight_deadline = int(lease.get("in_flight_deadline_at") or 0)
                lease["state"] = "draining" if in_flight_deadline > now else "revoked_protocol_upgraded"
                lease["expires_at"] = max(now, in_flight_deadline)
                lease["heartbeat_at"] = now
                state["lease"] = self.storage._plc_workstation_lease_row()(lease)

        upgraded = self.storage._plc_web_serial_mutate()(station_id, None, upgrade)
        return self.storage._plc_web_serial_record()(upgraded.get("station")) or {**station, "config": migrated}


    def plc_web_serial_station_payload(self, station: dict[str, Any]) -> dict[str, Any]:
        station = self.projection.plc_web_serial_ensure_current_station_contract()(station)
        config = self.policy.normalize_web_serial_config()(station.get("config") if isinstance(station.get("config"), dict) else {})
        profile_verified = bool(
            station.get("profile_verified")
            and hmac.compare_digest(
                str(station.get("profile_verified_fingerprint") or ""),
                self.policy.web_serial_profile_fingerprint()(config),
            )
        )
        lease = self.projection.plc_web_serial_current_lease()(str(station["id"]))
        now = int(time.time())
        lease_active = bool(
            lease
            and lease.get("state") == "active"
            and int(lease.get("expires_at") or 0) > now
            and int(lease.get("config_generation") or -1) == int(station.get("config_generation") or 0)
            and lease.get("bundle_version") == self.policy.WEB_SERIAL_PROTOCOL_VERSION()
        )
        release_consistent = bool(self.projection.current_release_version()()["consistent"])
        config_generation = int(station.get("config_generation") or 0)
        return {
            "paired": True,
            "protocol_version": self.policy.WEB_SERIAL_PROTOCOL_VERSION(),
            "station": {
                "id": station["id"],
                "name": station["name"],
                "status": station.get("status") or "commissioning",
                "profile_verified": profile_verified,
            },
            "config": config,
            "config_generation": config_generation,
            "resolved_addresses": self.projection.web_serial_resolved_addresses()(config),
            "capture_read_plan": self.projection.build_web_serial_capture_read_plan()(config, config_generation),
            "lease": lease if lease_active else None,
            "effective_enabled": bool(config["enabled"] and lease_active and release_consistent),
            "production_ready": bool(config["enabled"] and lease_active and profile_verified and release_consistent),
            "release_consistent": release_consistent,
            "heartbeat_seconds": self.policy.WEB_SERIAL_HEARTBEAT_SECONDS(),
            "lease_ttl_seconds": self.policy.WEB_SERIAL_ACTIVE_LEASE_SECONDS(),
            "recent_dispatches": self.projection.plc_web_serial_recent_dispatches()(str(station["id"])),
        }


    def plc_web_serial_unpaired_payload(self) -> dict[str, Any]:
        return {
            "paired": False,
            "protocol_version": self.policy.WEB_SERIAL_PROTOCOL_VERSION(),
            "station": None,
            "config": None,
            "config_generation": 0,
            "resolved_addresses": {"result_register": "", "output_control_point": "", "capture_input_register": ""},
            "capture_read_plan": None,
            "lease": None,
            "effective_enabled": False,
            "production_ready": False,
            "release_consistent": bool(self.projection.current_release_version()()["consistent"]),
            "heartbeat_seconds": self.policy.WEB_SERIAL_HEARTBEAT_SECONDS(),
            "lease_ttl_seconds": self.policy.WEB_SERIAL_ACTIVE_LEASE_SECONDS(),
            "recent_dispatches": [],
        }


    def plc_web_serial_list_workstations(self) -> list[dict[str, Any]]:
        repository = self.storage.runtime_postgres_repository_or_none()()
        if repository is not None:
            rows = repository.fetch_all("plc_workstations")
        else:
            with self.storage._config_io_lock():
                rows = list(self.storage._plc_web_serial_load_local()()["workstations"].values())
        records = [
            self.projection.plc_web_serial_ensure_current_station_contract()(record)
            for record in (self.storage._plc_web_serial_record()(row) for row in rows)
            if record
        ]
        return [
            {
                "id": record["id"],
                "name": record["name"],
                "status": record.get("status") or "commissioning",
                "profile_verified": bool(record.get("profile_verified")),
                "updated_at": int(record.get("updated_at") or 0),
            }
            for record in sorted(records, key=lambda item: str(item.get("name") or "").casefold())
        ]


    def plc_web_serial_pair(self, request: Request, response: Response, name: str, station_id: str | None = None) -> dict[str, Any]:
        clean_name = " ".join(str(name or "").split())
        if not 1 <= len(clean_name) <= 80:
            raise self.policy.PlcConfigError()("workstation name must contain 1 through 80 characters")
        user = self.identity.current_auth_user()()
        now = int(time.time())
        current = self.identity.plc_web_serial_station_from_request()(request)
        requested_station_id = str(station_id or "").strip()
        if requested_station_id and (not current or current.get("id") != requested_station_id):
            repository = self.storage.runtime_postgres_repository_or_none()()
            if repository is not None:
                current = self.storage._plc_web_serial_record()(
                    repository.fetch_by_primary_key("plc_workstations", {"id": requested_station_id})
                )
            else:
                with self.storage._config_io_lock():
                    current = self.storage._plc_web_serial_record()(
                        self.storage._plc_web_serial_load_local()()["workstations"].get(requested_station_id)
                    )
            if not current:
                raise self.policy.PlcConfigError()("plc_workstation_not_found")
        token = secrets.token_urlsafe(32)
        if current:
            record = {**current, "token_hash": self.identity._plc_web_serial_token_hash()(token), "name": clean_name, "updated_at": now}
        else:
            station_id = f"plcws_{uuid.uuid4().hex}"
            record = {
                "id": station_id,
                "token_hash": self.identity._plc_web_serial_token_hash()(token),
                "name": clean_name,
                "status": "commissioning",
                "config_generation": 0,
                "profile_verified": False,
                "config": dict(self.policy.DEFAULT_WEB_SERIAL_CONFIG()),
                "created_by_user_id": str(user.get("id") or self.identity.SYSTEM_OWNER_ID()),
                "created_at": now,
                "updated_at": now,
            }
        if current:
            def rebind(state: dict[str, dict[str, Any] | None]) -> None:
                existing = self.storage._plc_web_serial_record()(state.get("station"))
                if not existing:
                    raise self.policy.PlcConfigError()("plc_workstation_not_found")
                existing.update({"token_hash": record["token_hash"], "name": clean_name, "updated_at": now})
                state["station"] = self.storage._plc_workstation_row()(existing)
                lease = self.storage._plc_web_serial_record()(state.get("lease"))
                if lease and lease.get("state") in {"connecting", "active", "draining"}:
                    in_flight_deadline = int(lease.get("in_flight_deadline_at") or 0)
                    lease.update({
                        "state": "draining" if in_flight_deadline > now else "revoked_browser_rebound",
                        "expires_at": max(now, in_flight_deadline),
                        "heartbeat_at": now,
                    })
                    state["lease"] = self.storage._plc_workstation_lease_row()(lease)

            rebound = self.storage._plc_web_serial_mutate()(str(record["id"]), None, rebind)
            record = self.storage._plc_web_serial_record()(rebound.get("station")) or record
        else:
            self.storage._plc_web_serial_upsert_row()("plc_workstations", self.storage._plc_workstation_row()(record), "workstations", record["id"])
        response.set_cookie(
            self.identity.PLC_WORKSTATION_COOKIE(),
            token,
            max_age=self.identity.PLC_WORKSTATION_COOKIE_TTL_SECONDS(),
            httponly=True,
            secure=self.identity.request_is_https()(request),
            samesite="lax",
            path="/",
        )
        return self.projection.plc_web_serial_station_payload()(record)


    def plc_web_serial_update_config(self, station_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
        normalized = self.policy.normalize_web_serial_config()(candidate)

        def mutate(state: dict[str, dict[str, Any] | None]) -> None:
            station = self.storage._plc_web_serial_record()(state.get("station"))
            if not station:
                raise self.policy.PlcConfigError()("plc_workstation_not_found")
            current_raw = station.get("config") if isinstance(station.get("config"), dict) else {}
            try:
                current = self.policy.normalize_web_serial_config()(current_raw)
                protocol_upgraded = False
            except self.policy.PlcConfigError():
                current = self.policy.migrate_web_serial_config()(current_raw)
                protocol_upgraded = True
            now = int((state.get("clock") or {}).get("now") or time.time())
            if protocol_upgraded or current != normalized:
                station["config_generation"] = int(station.get("config_generation") or 0) + 1
                if protocol_upgraded or self.policy.web_serial_profile_fingerprint()(current) != self.policy.web_serial_profile_fingerprint()(normalized):
                    station["profile_verified"] = False
                    station["profile_verified_fingerprint"] = ""
                    station["status"] = "commissioning"
            station["config"] = normalized
            station["updated_at"] = now
            state["station"] = self.storage._plc_workstation_row()(station)
            lease = self.storage._plc_web_serial_record()(state.get("lease"))
            if lease and lease.get("state") in {"connecting", "active", "draining"}:
                in_flight_deadline = int(lease.get("in_flight_deadline_at") or 0)
                lease["state"] = "draining" if in_flight_deadline > now else "revoked_config_changed"
                lease["expires_at"] = max(now, in_flight_deadline)
                lease["heartbeat_at"] = now
                state["lease"] = self.storage._plc_workstation_lease_row()(lease)

        state = self.storage._plc_web_serial_mutate()(station_id, None, mutate)
        record = self.storage._plc_web_serial_record()(state.get("station"))
        if not record:
            raise self.policy.PlcConfigError()("plc_workstation_not_found")
        return self.projection.plc_web_serial_station_payload()(record)


    def plc_web_serial_set_verified(self, station_id: str, verified: bool) -> dict[str, Any]:
        def mutate(state: dict[str, dict[str, Any] | None]) -> None:
            station = self.storage._plc_web_serial_record()(state.get("station"))
            if not station:
                raise self.policy.PlcConfigError()("plc_workstation_not_found")
            now = int((state.get("clock") or {}).get("now") or time.time())
            station["profile_verified"] = bool(verified)
            station["profile_verified_fingerprint"] = self.policy.web_serial_profile_fingerprint()(
                self.policy.migrate_web_serial_config()(station.get("config") or {})
            ) if verified else ""
            station["status"] = "production" if verified else "commissioning"
            station["verified_at"] = now if verified else 0
            station["verified_by_user_id"] = str((self.identity.current_auth_user()() or {}).get("id") or "") if verified else ""
            station["updated_at"] = now
            state["station"] = self.storage._plc_workstation_row()(station)

        state = self.storage._plc_web_serial_mutate()(station_id, None, mutate)
        record = self.storage._plc_web_serial_record()(state.get("station"))
        if not record:
            raise self.policy.PlcConfigError()("plc_workstation_not_found")
        return self.projection.plc_web_serial_station_payload()(record)
