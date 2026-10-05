"""Camera dispatch planning, declaration and browser receipts; no physical I/O."""
from dataclasses import dataclass
import copy
import json
import math
import re
import hashlib
import hmac
import secrets
import time
from typing import Any
from .browser_dispatch_ports import BrowserDispatchStorage, BrowserDispatchIdentity, BrowserDispatchPolicy, BrowserDispatchProjection, PlcWebSerialAttemptRequest, PlcWebSerialReceiptRequest

@dataclass(frozen=True)
class PlcBrowserDispatchService:
    storage: BrowserDispatchStorage
    identity: BrowserDispatchIdentity
    policy: BrowserDispatchPolicy
    projection: BrowserDispatchProjection

    def plc_web_serial_begin_camera_detection(self,
        station_id: str,
        session_id: str,
        camera_request_id: str,
        model_id: str,
        fingerprint: str,
    ) -> tuple[dict[str, Any], bool]:
        clean_request_id = str(camera_request_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._:-]{8,160}", clean_request_id):
            raise self.policy.PlcConfigError()("invalid_camera_request_id")
        dispatch_id = "plcweb_" + hashlib.sha256(f"{station_id}:{clean_request_id}".encode("utf-8")).hexdigest()[:32]
        created = False

        def mutate(state: dict[str, dict[str, Any] | None]) -> None:
            nonlocal created
            station, lease, now = self.identity._plc_web_serial_require_active_lease()(state, session_id)
            in_flight_id = str(lease.get("in_flight_dispatch_id") or "")
            in_flight_deadline = int(lease.get("in_flight_deadline_at") or 0)
            if in_flight_id and in_flight_id != dispatch_id and in_flight_deadline > now:
                raise self.policy.PlcConfigError()("plc_workstation_attempt_in_flight")
            if str(lease.get("model_id") or "") != str(model_id or ""):
                raise self.policy.PlcConfigError()("plc_workstation_model_changed")
            existing = self.storage._plc_web_serial_record()(state.get("dispatch"))
            if existing:
                self.projection.verify_plc_web_serial_dispatch()(
                    existing,
                    station,
                    require_frames=existing.get("status") != "detecting",
                    require_current_config=False,
                )
                if existing.get("fingerprint") != fingerprint or existing.get("model_id") != model_id:
                    raise self.policy.PlcConfigError()("plc_camera_request_payload_conflict")
                return
            config_snapshot = self.policy.migrate_web_serial_config()(station.get("config") or {})
            record = {
                "dispatch_id": dispatch_id,
                "protocol_version": self.policy.WEB_SERIAL_PROTOCOL_VERSION(),
                "station_id": station_id,
                "detection_request_id": clean_request_id,
                "session_id": session_id,
                "lease_epoch": int(lease["lease_epoch"]),
                "config_generation": int(station.get("config_generation") or 0),
                "config_snapshot": config_snapshot,
                "config_fingerprint": self.policy.web_serial_config_fingerprint()(config_snapshot),
                "model_id": model_id,
                "fingerprint": fingerprint,
                "source": "camera",
                "status": "detecting",
                "passed": False,
                "frames": [],
                "deadline_at": 0,
                "created_at": now,
                "updated_at": now,
                "result": None,
                "evidence_source": "browser_workstation",
            }
            state["dispatch"] = self.storage._plc_web_serial_dispatch_row()(record)
            lease["in_flight_dispatch_id"] = dispatch_id
            lease["in_flight_deadline_at"] = int(lease.get("expires_at") or now)
            state["lease"] = self.storage._plc_workstation_lease_row()(lease)
            created = True

        state = self.storage._plc_web_serial_mutate()(station_id, dispatch_id, mutate)
        record = self.storage._plc_web_serial_record()(state.get("dispatch"))
        if not record:
            raise self.policy.PlcConfigError()("plc_dispatch_persist_failed")
        return record, created


    def plc_web_serial_finish_camera_detection(self,
        station_id: str,
        dispatch_id: str,
        session_id: str,
        result: dict[str, Any] | None,
        error: str = "",
    ) -> dict[str, Any]:
        def mutate(state: dict[str, dict[str, Any] | None]) -> None:
            station, _, now = self.identity._plc_web_serial_require_active_lease()(state, session_id)
            record = self.storage._plc_web_serial_record()(state.get("dispatch"))
            if not record or record.get("session_id") != session_id:
                raise self.policy.PlcConfigError()("plc_dispatch_not_owned")
            self.projection.verify_plc_web_serial_dispatch()(record, station, require_frames=False)
            if record.get("status") != "detecting":
                return
            if error or not isinstance(result, dict):
                record["status"] = "detection_failed"
                record["error_code"] = str(error or "detection_failed")[:120]
                if lease := self.storage._plc_web_serial_record()(state.get("lease")):
                    if lease.get("in_flight_dispatch_id") == dispatch_id:
                        lease.pop("in_flight_dispatch_id", None)
                        lease.pop("in_flight_deadline_at", None)
                        state["lease"] = self.storage._plc_workstation_lease_row()(lease)
            else:
                passed = bool(result.get("passed"))
                frames = self.policy.build_web_serial_plan()(record.get("config_snapshot") or {}, passed)
                record.update(
                    {
                        "status": "planned",
                        "passed": passed,
                        "frames": frames,
                        "targets": [item["target"] for item in frames],
                        "result": copy.deepcopy(result),
                    }
                )
            record["updated_at"] = now
            state["dispatch"] = self.storage._plc_web_serial_dispatch_row()(record)

        state = self.storage._plc_web_serial_mutate()(station_id, dispatch_id, mutate)
        record = self.storage._plc_web_serial_record()(state.get("dispatch"))
        if not record:
            raise self.policy.PlcConfigError()("plc_dispatch_not_found")
        return record


    def plc_web_serial_dispatch_public(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "dispatch_id": record["dispatch_id"],
            "source": "camera",
            "passed": bool(record.get("passed")),
            "enabled": True,
            "attempted": record.get("status") not in {"detecting", "planned"},
            "protocol": self.policy.PLC_PROTOCOL_ID(),
            "transport_mode": "web_serial",
            "protocol_version": str(record.get("protocol_version") or self.policy.LEGACY_WEB_SERIAL_PROTOCOL_VERSION()),
            "status": record.get("status") or "planned",
            "outcome": record.get("outcome") or "",
            "targets": list(record.get("targets") or []),
            "operations": copy.deepcopy(record.get("operations") or []),
            "evidence_source": "browser_workstation",
            "config_generation": int(record.get("config_generation") or 0),
            "lease_epoch": int(record.get("lease_epoch") or 0),
            "updated_at": int(record.get("updated_at") or 0),
        }


    def verify_plc_web_serial_dispatch(self,
        record: dict[str, Any],
        station: dict[str, Any],
        *,
        require_frames: bool = True,
        require_current_config: bool = True,
    ) -> None:
        station_id = str(station.get("id") or "")
        request_id = str(record.get("detection_request_id") or "")
        expected_id = "plcweb_" + hashlib.sha256(f"{station_id}:{request_id}".encode("utf-8")).hexdigest()[:32]
        if record.get("dispatch_id") != expected_id or record.get("station_id") != station_id:
            raise self.policy.PlcConfigError()("plc_dispatch_identity_invalid")
        if record.get("source") != "camera" or record.get("evidence_source") != "browser_workstation":
            raise self.policy.PlcConfigError()("plc_dispatch_source_invalid")
        if not re.fullmatch(r"[A-Za-z0-9._:-]{8,160}", request_id):
            raise self.policy.PlcConfigError()("plc_dispatch_request_id_invalid")
        if require_current_config and int(record.get("config_generation") or -1) != int(station.get("config_generation") or 0):
            raise self.policy.PlcConfigError()("plc_dispatch_generation_invalid")
        snapshot = record.get("config_snapshot")
        if not isinstance(snapshot, dict):
            raise self.policy.PlcConfigError()("plc_dispatch_config_snapshot_missing")
        protocol_version = str(record.get("protocol_version") or self.policy.LEGACY_WEB_SERIAL_PROTOCOL_VERSION())
        if protocol_version == self.policy.WEB_SERIAL_PROTOCOL_VERSION():
            config = self.policy.normalize_web_serial_config()(snapshot)
            config_fingerprint = self.policy.web_serial_config_fingerprint()(config)
            expected_frames_builder = self.policy.build_web_serial_plan()
        elif protocol_version == self.policy.LEGACY_WEB_SERIAL_PROTOCOL_VERSION():
            config = self.policy.normalize_legacy_web_serial_config()(snapshot)
            config_fingerprint = self.policy.legacy_web_serial_config_fingerprint()(config)
            expected_frames_builder = self.policy.build_legacy_web_serial_plan()
        else:
            raise self.policy.PlcConfigError()("plc_dispatch_protocol_version_invalid")
        if not hmac.compare_digest(str(record.get("config_fingerprint") or ""), config_fingerprint):
            raise self.policy.PlcConfigError()("plc_dispatch_config_fingerprint_invalid")
        if require_current_config:
            if protocol_version != self.policy.WEB_SERIAL_PROTOCOL_VERSION():
                raise self.policy.PlcConfigError()("plc_dispatch_protocol_obsolete")
            current = self.policy.migrate_web_serial_config()(station.get("config") if isinstance(station.get("config"), dict) else {})
            if not hmac.compare_digest(self.policy.web_serial_config_fingerprint()(current), self.policy.web_serial_config_fingerprint()(config)):
                raise self.policy.PlcConfigError()("plc_dispatch_config_changed")
        if require_frames:
            if type(record.get("passed")) is not bool:
                raise self.policy.PlcConfigError()("plc_dispatch_passed_invalid")
            result = record.get("result")
            if not isinstance(result, dict) or type(result.get("passed")) is not bool or result.get("passed") is not record.get("passed"):
                raise self.policy.PlcConfigError()("plc_dispatch_result_mismatch")
            expected_frames = expected_frames_builder(config, bool(record.get("passed")))
            actual_frames = record.get("frames")
            if not isinstance(actual_frames, list) or json.dumps(actual_frames, sort_keys=True, separators=(",", ":")) != json.dumps(expected_frames, sort_keys=True, separators=(",", ":")):
                raise self.policy.PlcConfigError()("plc_dispatch_frames_invalid")
            if record.get("targets") != [item["target"] for item in expected_frames]:
                raise self.policy.PlcConfigError()("plc_dispatch_targets_invalid")


    def plc_web_serial_declare_attempt(self,
        station_id: str,
        dispatch_id: str,
        request: PlcWebSerialAttemptRequest,
    ) -> dict[str, Any]:
        attempt_token = secrets.token_urlsafe(32)

        def mutate(state: dict[str, dict[str, Any] | None]) -> None:
            station, lease, now = self.identity._plc_web_serial_require_active_lease()(state, request.session_id, request.lease_epoch)
            record = self.storage._plc_web_serial_record()(state.get("dispatch"))
            if not record or record.get("station_id") != station_id:
                raise self.policy.PlcConfigError()("plc_dispatch_not_found")
            self.projection.verify_plc_web_serial_dispatch()(record, station)
            if record.get("status") != "planned":
                raise self.policy.PlcConfigError()("plc_dispatch_already_declared")
            in_flight_id = str(lease.get("in_flight_dispatch_id") or "")
            in_flight_deadline = int(lease.get("in_flight_deadline_at") or 0)
            if in_flight_id and in_flight_id != dispatch_id and in_flight_deadline > now:
                raise self.policy.PlcConfigError()("plc_workstation_attempt_in_flight")
            if int(request.config_generation) != int(station.get("config_generation") or 0) or int(record.get("config_generation") or -1) != int(request.config_generation):
                raise self.policy.PlcConfigError()("plc_workstation_generation_changed")
            if record.get("session_id") != request.session_id or int(record.get("lease_epoch") or -1) != int(lease.get("lease_epoch") or -2):
                raise self.policy.PlcConfigError()("plc_dispatch_not_owned")
            record["status"] = "browser_attempt_declared"
            record["attempt_token_hash"] = self.identity._plc_web_serial_token_hash()(attempt_token)
            record["deadline_at"] = now + max(1, int(math.ceil(self.policy.WEB_SERIAL_PLAN_DEADLINE_SECONDS())))
            record["updated_at"] = now
            state["dispatch"] = self.storage._plc_web_serial_dispatch_row()(record)
            lease["in_flight_dispatch_id"] = dispatch_id
            lease["in_flight_deadline_at"] = record["deadline_at"]
            state["lease"] = self.storage._plc_workstation_lease_row()(lease)

        state = self.storage._plc_web_serial_mutate()(station_id, dispatch_id, mutate)
        record = self.storage._plc_web_serial_record()(state.get("dispatch"))
        if not record:
            raise self.policy.PlcConfigError()("plc_dispatch_not_found")
        return {
            **self.projection.plc_web_serial_dispatch_public()(record),
            "attempt_token": attempt_token,
            "deadline_at": int(record["deadline_at"]),
            "execution_window_ms": int(self.policy.WEB_SERIAL_PLAN_DEADLINE_SECONDS() * 1000),
            "ack_timeout_ms": int((station_config := self.policy.migrate_web_serial_config()((self.storage._plc_web_serial_record()(state.get("station")) or {}).get("config") or {}))["ack_timeout_ms"]),
            "frames": copy.deepcopy(record.get("frames") or []),
            "serial_options": {
                "baudRate": station_config["baudrate"],
                "dataBits": station_config["data_bits"],
                "stopBits": station_config["stop_bits"],
                "parity": "even",
                "flowControl": "none",
            },
        }


    def _plc_web_serial_receipt_outcome(self, frames: list[dict[str, Any]], operations: list[dict[str, Any]]) -> str:
        allowed_statuses = {"acknowledged", "nak", "timeout", "serial_error", "unexpected_response"}
        if not operations:
            return "uncertain"
        if len(operations) > len(frames):
            raise self.policy.PlcConfigError()("plc_receipt_has_extra_operations")
        normalized: list[dict[str, Any]] = []
        for index, operation in enumerate(operations):
            if not isinstance(operation, dict):
                raise self.policy.PlcConfigError()("plc_receipt_operation_invalid")
            expected = frames[index]
            status = str(operation.get("status") or "")
            response_hex = str(operation.get("response_hex") or "").upper()
            if status not in allowed_statuses:
                raise self.policy.PlcConfigError()("plc_receipt_status_invalid")
            if operation.get("target") != expected.get("target") or operation.get("frame_sha256") != expected.get("frame_sha256"):
                raise self.policy.PlcConfigError()("plc_receipt_frame_mismatch")
            if status == "acknowledged" and response_hex != "06":
                raise self.policy.PlcConfigError()("plc_receipt_ack_evidence_invalid")
            if status == "nak" and response_hex != "15":
                raise self.policy.PlcConfigError()("plc_receipt_nak_evidence_invalid")
            if status in {"timeout", "serial_error"} and response_hex:
                raise self.policy.PlcConfigError()("plc_receipt_empty_response_required")
            normalized.append({**operation, "response_hex": response_hex})
        operations[:] = normalized
        first = operations[0]["status"]
        if len(operations) > 1 and first != "acknowledged":
            raise self.policy.PlcConfigError()("plc_receipt_y_without_d_ack")
        if first == "nak":
            return "rejected"
        if first != "acknowledged":
            return "uncertain"
        if len(frames) == 1:
            return "acknowledged"
        if len(operations) < len(frames):
            return "uncertain"
        second = operations[1]["status"]
        if second == "acknowledged":
            return "acknowledged"
        if second == "nak":
            return "partial_success"
        return "uncertain"


    def plc_web_serial_record_receipt(self,
        station_id: str,
        dispatch_id: str,
        request: PlcWebSerialReceiptRequest,
    ) -> dict[str, Any]:
        def mutate(state: dict[str, dict[str, Any] | None]) -> None:
            record = self.storage._plc_web_serial_record()(state.get("dispatch"))
            if not record:
                raise self.policy.PlcConfigError()("plc_dispatch_not_receivable")
            station = self.storage._plc_web_serial_record()(state.get("station"))
            if not station:
                raise self.policy.PlcConfigError()("plc_workstation_not_found")
            self.projection.verify_plc_web_serial_dispatch()(record, station, require_current_config=False)
            if not hmac.compare_digest(str(record.get("attempt_token_hash") or ""), self.identity._plc_web_serial_token_hash()(request.attempt_token)):
                raise self.policy.PlcConfigError()("plc_attempt_token_invalid")
            if record.get("session_id") != request.session_id or int(record.get("lease_epoch") or -1) != int(request.lease_epoch):
                raise self.policy.PlcConfigError()("plc_dispatch_not_owned")
            operations = [item.model_dump() for item in request.operations]
            outcome = self.projection._plc_web_serial_receipt_outcome()(list(record.get("frames") or []), operations)
            declared_outcome = str(request.outcome or "")
            if declared_outcome and declared_outcome != outcome:
                raise self.policy.PlcConfigError()("plc_receipt_outcome_mismatch")
            receipt_fingerprint = hashlib.sha256(
                json.dumps(
                    {"outcome": outcome, "operations": operations},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            if record.get("status") in {"acknowledged", "rejected", "partial_success", "uncertain"}:
                if hmac.compare_digest(str(record.get("receipt_fingerprint") or ""), receipt_fingerprint):
                    return
                raise self.policy.PlcConfigError()("plc_receipt_conflict")
            if record.get("status") != "browser_attempt_declared":
                raise self.policy.PlcConfigError()("plc_dispatch_not_receivable")
            now = int((state.get("clock") or {}).get("now") or time.time())
            record["operations"] = operations
            record["outcome"] = outcome
            record["status"] = outcome
            record["receipt_fingerprint"] = receipt_fingerprint
            record["evidence_source"] = "browser_workstation"
            record["updated_at"] = now
            state["dispatch"] = self.storage._plc_web_serial_dispatch_row()(record)
            lease = self.storage._plc_web_serial_record()(state.get("lease"))
            if lease and lease.get("in_flight_dispatch_id") == dispatch_id:
                lease.pop("in_flight_dispatch_id", None)
                lease.pop("in_flight_deadline_at", None)
                if lease.get("state") == "draining":
                    lease["state"] = "released"
                    lease["expires_at"] = now
                state["lease"] = self.storage._plc_workstation_lease_row()(lease)

        state = self.storage._plc_web_serial_mutate()(station_id, dispatch_id, mutate)
        record = self.storage._plc_web_serial_record()(state.get("dispatch"))
        if not record:
            raise self.policy.PlcConfigError()("plc_dispatch_not_found")
        return self.projection.plc_web_serial_dispatch_public()(record)
