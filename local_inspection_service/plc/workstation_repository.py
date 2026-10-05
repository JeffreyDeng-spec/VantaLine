"""Workstation row mapping and persistence; transaction ownership remains with adapters."""
from collections.abc import Callable
from dataclasses import dataclass
import copy
import json
import os
import time
from typing import Any
from .workstation_repository_ports import WorkstationRepositoryFiles, WorkstationRepositoryPolicy, WorkstationRepositoryStorage

@dataclass(frozen=True)
class PlcWorkstationRepository:
    files: WorkstationRepositoryFiles
    policy: WorkstationRepositoryPolicy
    storage: WorkstationRepositoryStorage

    def _plc_web_serial_empty_state(self) -> dict[str, dict[str, Any]]:
        return {"workstations": {}, "leases": {}, "dispatches": {}}


    def _plc_web_serial_load_local(self) -> dict[str, dict[str, Any]]:
        try:
            raw = json.loads(self.files._business_files().read_text(self.files.PLC_WEB_SERIAL_STATE_PATH(), encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return self.storage._plc_web_serial_empty_state()()
        state = self.storage._plc_web_serial_empty_state()()
        if isinstance(raw, dict):
            for key in state:
                value = raw.get(key)
                if isinstance(value, dict):
                    state[key] = {str(item_id): dict(item) for item_id, item in value.items() if isinstance(item, dict)}
        return state


    def _plc_web_serial_save_local(self, state: dict[str, dict[str, Any]]) -> None:
        self.files.DATA_DIR().mkdir(parents=True, exist_ok=True)
        temporary = self.files.PLC_WEB_SERIAL_STATE_PATH().with_suffix(".tmp")
        self.files._business_files().write_text(temporary, json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.files.PLC_WEB_SERIAL_STATE_PATH())


    def _plc_web_serial_record(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(row, dict):
            return None
        raw = row.get("raw_json")
        return dict(raw) if isinstance(raw, dict) else dict(row)


    def _plc_workstation_row(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": record["id"],
            "token_hash": record["token_hash"],
            "name": record["name"],
            "status": record.get("status") or "commissioning",
            "config_generation": int(record.get("config_generation") or 0),
            "profile_verified": bool(record.get("profile_verified")),
            "created_by_user_id": record.get("created_by_user_id") or self.policy.SYSTEM_OWNER_ID(),
            "created_at": int(record.get("created_at") or 0),
            "updated_at": int(record.get("updated_at") or 0),
            "raw_json": record,
        }


    def _plc_workstation_lease_row(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "station_id": record["station_id"],
            "session_id": record["session_id"],
            "state": record["state"],
            "lease_epoch": int(record["lease_epoch"]),
            "owner_user_id": record["owner_user_id"],
            "model_id": record.get("model_id") or "",
            "client_instance_id": record["client_instance_id"],
            "bundle_version": record["bundle_version"],
            "config_generation": int(record["config_generation"]),
            "heartbeat_at": int(record["heartbeat_at"]),
            "expires_at": int(record["expires_at"]),
            "raw_json": record,
        }


    def _plc_web_serial_dispatch_row(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": record["dispatch_id"],
            "station_id": record["station_id"],
            "detection_request_id": record["detection_request_id"],
            "session_id": record["session_id"],
            "lease_epoch": int(record["lease_epoch"]),
            "config_generation": int(record["config_generation"]),
            "status": record["status"],
            "passed": bool(record.get("passed")),
            "deadline_at": int(record.get("deadline_at") or 0),
            "created_at": int(record["created_at"]),
            "updated_at": int(record["updated_at"]),
            "raw_json": record,
        }


    def _plc_web_serial_upsert_row(self, table_name: str, row: dict[str, Any], local_key: str, row_id: str) -> None:
        repository = self.storage.runtime_postgres_repository_or_none()()
        if repository is not None:
            repository.upsert_row(table_name, row)
            return
        if str(os.environ.get(self.policy.PLC_WEB_SERIAL_JSON_TEST_ENV(), "")).strip().lower() not in {"1", "true", "yes"}:
            raise self.policy.PlcConfigError()("plc_web_serial_postgres_coordination_unavailable")
        with self.storage._config_io_lock():
            state = self.storage._plc_web_serial_load_local()()
            state[local_key][row_id] = row
            self.storage._plc_web_serial_save_local()(state)


    def _plc_web_serial_mutate(self,
        station_id: str,
        dispatch_id: str | None,
        mutator: Callable[[dict[str, dict[str, Any] | None]], None],
    ) -> dict[str, dict[str, Any] | None]:
        repository = self.storage.runtime_postgres_repository_or_none()()
        if repository is not None:
            return repository.mutate_plc_web_serial_rows(station_id, dispatch_id, mutator)
        if str(os.environ.get(self.policy.PLC_WEB_SERIAL_JSON_TEST_ENV(), "")).strip().lower() not in {"1", "true", "yes"}:
            raise self.policy.PlcConfigError()("plc_web_serial_postgres_coordination_unavailable")
        with self.storage._config_io_lock():
            local = self.storage._plc_web_serial_load_local()()
            state: dict[str, dict[str, Any] | None] = {
                "station": copy.deepcopy(local["workstations"].get(station_id)),
                "lease": copy.deepcopy(local["leases"].get(station_id)),
                "clock": {"now": int(time.time())},
            }
            if dispatch_id:
                state["dispatch"] = copy.deepcopy(local["dispatches"].get(dispatch_id))
            mutator(state)
            if state.get("station") is not None:
                local["workstations"][station_id] = dict(state["station"] or {})
            if state.get("lease") is not None:
                local["leases"][station_id] = dict(state["lease"] or {})
            if dispatch_id and state.get("dispatch") is not None:
                local["dispatches"][dispatch_id] = dict(state["dispatch"] or {})
            self.storage._plc_web_serial_save_local()(local)
            return state
