"""Retained capture sessions, edge events and durable analysis receipts."""
from dataclasses import dataclass
import copy
import hashlib
import time
import uuid
from typing import Any
from .plc_capture_state_ports import CaptureStateTransactions, CaptureStatePolicy

@dataclass(frozen=True)
class PlcCaptureState:
    transactions: CaptureStateTransactions
    policy: CaptureStatePolicy

    def _plc_capture_runtime(self, state: dict[str, Any]) -> dict[str, Any]:
        capture = state.get("capture")
        if not isinstance(capture, dict):
            capture = {"sequence": 0, "armed": False, "events": []}
            state["capture"] = capture
        if not isinstance(capture.get("events"), list):
            capture["events"] = []
        return capture


    def _plc_expire_capture_state(self, capture: dict[str, Any], now: float) -> None:
        session = capture.get("session") if isinstance(capture.get("session"), dict) else None
        if session is not None and float(session.get("expires_at") or 0.0) <= now:
            capture.pop("session", None)
        events = [dict(item) for item in capture.get("events", []) if isinstance(item, dict)]
        for event in events:
            status = str(event.get("status") or "")
            if status == "claimed":
                deadline = float(event.get("submission_expires_at") or 0.0)
            elif status == "processing":
                deadline = float(event.get("processing_expires_at") or 0.0)
            elif status == "dispatching":
                deadline = float(event.get("dispatch_expires_at") or 0.0)
            else:
                deadline = float(event.get("expires_at") or 0.0)
            if status in {"pending", "claimed", "processing", "dispatching"} and deadline <= now:
                event["status"] = "expired"
                event["finished_at"] = now
                active_session = capture.get("session") if isinstance(capture.get("session"), dict) else None
                if active_session is not None and active_session.get("session_id") == event.get("session_id"):
                    active_session["busy"] = False
        capture["events"] = events[-100:]


    def plc_claim_capture_session(self, user_id: str, model_id: str) -> dict[str, Any]:
        now = time.time()
        claimed: dict[str, Any] = {}
        generation = int(self.transactions.load_config()().get(self.policy.PLC_CONTROL_GENERATION_KEY()) or 0)
        def mutate(state: dict[str, Any]) -> None:
            nonlocal claimed
            capture = self.policy._plc_capture_runtime()(state)
            self.policy._plc_expire_capture_state()(capture, now)
            current = capture.get("session") if isinstance(capture.get("session"), dict) else None
            if current is not None:
                raise self.policy.PlcConfigError()("plc_capture_session_in_use")
            session_id = uuid.uuid4().hex
            claimed = {
                "session_id": session_id,
                "user_id": user_id,
                "model_id": model_id,
                "generation": generation,
                "busy": False,
                "heartbeat_at": now,
                "expires_at": now + 6.0,
            }
            capture["session"] = copy.deepcopy(claimed)
        self.transactions.mutate_plc_runtime_coordination()(mutate)
        return claimed


    def plc_heartbeat_capture_session(self, session_id: str, user_id: str) -> dict[str, Any]:
        now = time.time()
        generation = int(self.transactions.load_config()().get(self.policy.PLC_CONTROL_GENERATION_KEY()) or 0)
        renewed: dict[str, Any] = {}
        def mutate(state: dict[str, Any]) -> None:
            nonlocal renewed
            capture = self.policy._plc_capture_runtime()(state)
            self.policy._plc_expire_capture_state()(capture, now)
            session = capture.get("session") if isinstance(capture.get("session"), dict) else None
            if session is None or session.get("session_id") != session_id or session.get("user_id") != user_id:
                raise self.policy.PlcConfigError()("plc_capture_session_not_owned")
            if int(session.get("generation") or -1) != generation:
                raise self.policy.PlcConfigError()("plc_capture_session_generation_changed")
            session["heartbeat_at"] = now
            session["expires_at"] = now + 6.0
            renewed = copy.deepcopy(session)
        self.transactions.mutate_plc_runtime_coordination()(mutate)
        return renewed


    def plc_release_capture_session(self, session_id: str, user_id: str) -> None:
        def mutate(state: dict[str, Any]) -> None:
            capture = self.policy._plc_capture_runtime()(state)
            session = capture.get("session") if isinstance(capture.get("session"), dict) else None
            if session is not None and session.get("session_id") == session_id and session.get("user_id") == user_id:
                capture.pop("session", None)
        self.transactions.mutate_plc_runtime_coordination()(mutate)


    def plc_capture_disarm(self, reason: str) -> None:
        def mutate(state: dict[str, Any]) -> None:
            capture = self.policy._plc_capture_runtime()(state)
            capture["armed"] = False
            capture["last_value"] = None
            capture["disarmed_reason"] = reason
            capture["updated_at"] = time.time()
        self.transactions.mutate_plc_runtime_coordination()(mutate)


    def plc_apply_capture_observation(self, value: int, *, generation: int, owner_epoch: int, trigger_value: int) -> dict[str, Any] | None:
        """Persist one read observation and atomically create at most one edge event."""
        now = time.time()
        created: dict[str, Any] | None = None
        def mutate(state: dict[str, Any]) -> None:
            nonlocal created
            capture = self.policy._plc_capture_runtime()(state)
            self.policy._plc_expire_capture_state()(capture, now)
            binding_changed = (
                int(capture.get("generation") or -1) != generation
                or int(capture.get("owner_epoch") or -1) != owner_epoch
            )
            if binding_changed:
                capture["generation"] = generation
                capture["owner_epoch"] = owner_epoch
                capture["armed"] = False
                capture["last_value"] = None
            armed = bool(capture.get("armed"))
            if value != trigger_value:
                capture["armed"] = True
            elif armed:
                sequence = int(capture.get("sequence") or 0) + 1
                capture["sequence"] = sequence
                trigger_id = hashlib.sha256(f"{generation}:{owner_epoch}:{sequence}".encode("ascii")).hexdigest()[:24]
                session = capture.get("session") if isinstance(capture.get("session"), dict) else None
                session_valid = bool(
                    session
                    and float(session.get("expires_at") or 0.0) > now
                    and int(session.get("generation") or -1) == generation
                    and not bool(session.get("busy"))
                )
                created = {
                    "trigger_id": trigger_id,
                    "generation": generation,
                    "owner_epoch": owner_epoch,
                    "sequence": sequence,
                    "value": value,
                    "created_at": now,
                    "expires_at": now + self.policy.PLC_CAPTURE_EVENT_TTL_SECONDS(),
                    "status": "pending" if session_valid else "missed",
                    "reason": "" if session_valid else "no_ready_capture_session",
                    "session_id": str(session.get("session_id") or "") if session_valid else "",
                    "user_id": str(session.get("user_id") or "") if session_valid else "",
                    "model_id": str(session.get("model_id") or "") if session_valid else "",
                }
                capture["events"].append(copy.deepcopy(created))
                capture["armed"] = False
            capture["last_value"] = value
            capture["last_read_at"] = now
            capture["disarmed_reason"] = ""
        self.transactions.mutate_plc_runtime_coordination()(mutate)
        return created


    def plc_claim_next_capture_event(self, session_id: str, user_id: str) -> dict[str, Any] | None:
        now = time.time()
        claimed: dict[str, Any] | None = None
        def mutate(state: dict[str, Any]) -> None:
            nonlocal claimed
            capture = self.policy._plc_capture_runtime()(state)
            self.policy._plc_expire_capture_state()(capture, now)
            session = capture.get("session") if isinstance(capture.get("session"), dict) else None
            if session is None or session.get("session_id") != session_id or session.get("user_id") != user_id:
                raise self.policy.PlcConfigError()("plc_capture_session_not_owned")
            if bool(session.get("busy")):
                return
            for event in capture.get("events", []):
                if not isinstance(event, dict) or event.get("status") != "pending":
                    continue
                if event.get("session_id") != session_id or event.get("user_id") != user_id:
                    continue
                event["status"] = "claimed"
                event["claimed_at"] = now
                event["submission_expires_at"] = now + 10.0
                session["busy"] = True
                claimed = copy.deepcopy(event)
                return
        self.transactions.mutate_plc_runtime_coordination()(mutate)
        return claimed


    def plc_begin_triggered_analysis(self, trigger_id: str, session_id: str, user_id: str, model_id: str, fingerprint: str) -> dict[str, Any] | None:
        now = time.time()
        durable_receipt = self.transactions.plc_completed_capture_receipt()(trigger_id)
        if durable_receipt is not None:
            if (
                durable_receipt.get("session_id") != session_id
                or durable_receipt.get("user_id") != user_id
                or durable_receipt.get("model_id") != model_id
            ):
                raise self.policy.PlcConfigError()("plc_capture_event_not_owned")
            if durable_receipt.get("fingerprint") != fingerprint:
                raise self.policy.PlcConfigError()("plc_capture_event_payload_conflict")
            stored_result = durable_receipt.get("result")
            return copy.deepcopy(stored_result) if isinstance(stored_result, dict) else {}
        duplicate_result: dict[str, Any] | None = None
        def mutate(state: dict[str, Any]) -> None:
            nonlocal duplicate_result
            capture = self.policy._plc_capture_runtime()(state)
            self.policy._plc_expire_capture_state()(capture, now)
            session = capture.get("session") if isinstance(capture.get("session"), dict) else None
            if session is None or session.get("session_id") != session_id or session.get("user_id") != user_id:
                raise self.policy.PlcConfigError()("plc_capture_session_not_owned")
            event = next((item for item in capture.get("events", []) if isinstance(item, dict) and item.get("trigger_id") == trigger_id), None)
            if event is None or event.get("session_id") != session_id or event.get("user_id") != user_id:
                raise self.policy.PlcConfigError()("plc_capture_event_not_owned")
            if str(event.get("model_id") or "") != model_id:
                raise self.policy.PlcConfigError()("plc_capture_event_model_mismatch")
            if event.get("status") == "completed":
                if event.get("fingerprint") != fingerprint:
                    raise self.policy.PlcConfigError()("plc_capture_event_payload_conflict")
                duplicate_result = copy.deepcopy(event.get("result")) if isinstance(event.get("result"), dict) else {}
                return
            if event.get("status") != "claimed" or float(event.get("submission_expires_at") or 0.0) <= now:
                raise self.policy.PlcConfigError()("plc_capture_event_not_claimable")
            event["status"] = "processing"
            event["fingerprint"] = fingerprint
            event["processing_at"] = now
            event["processing_expires_at"] = now + self.policy.PLC_CAPTURE_PROCESSING_TTL_SECONDS()
        self.transactions.mutate_plc_runtime_coordination()(mutate)
        return duplicate_result


    def plc_prepare_triggered_dispatch(self, trigger_id: str, session_id: str, user_id: str) -> None:
        """Atomically prove a fresh session/event immediately before any PLC dispatch."""
        now = time.time()
        generation = int(self.transactions.load_config()().get(self.policy.PLC_CONTROL_GENERATION_KEY()) or 0)
        def mutate(state: dict[str, Any]) -> None:
            capture = self.policy._plc_capture_runtime()(state)
            self.policy._plc_expire_capture_state()(capture, now)
            session = capture.get("session") if isinstance(capture.get("session"), dict) else None
            event = next(
                (item for item in capture.get("events", []) if isinstance(item, dict) and item.get("trigger_id") == trigger_id),
                None,
            )
            if (
                session is None
                or session.get("session_id") != session_id
                or session.get("user_id") != user_id
                or float(session.get("expires_at") or 0.0) <= now
            ):
                raise self.policy.PlcConfigError()("plc_capture_session_not_owned")
            if (
                event is None
                or event.get("status") != "processing"
                or event.get("session_id") != session_id
                or event.get("user_id") != user_id
                or int(event.get("generation") or -1) != generation
            ):
                raise self.policy.PlcConfigError()("plc_capture_event_not_dispatchable")
            event["status"] = "dispatching"
            event["dispatching_at"] = now
            event["dispatch_expires_at"] = now + self.policy.PLC_WORKER_TOTAL_TIMEOUT_SECONDS() + 5.0
        self.transactions.mutate_plc_runtime_coordination()(mutate)


    def plc_finish_triggered_analysis(self, trigger_id: str, session_id: str, user_id: str, result: dict[str, Any] | None, error: str = "") -> None:
        now = time.time()
        def mutate(config: dict[str, Any]) -> None:
            current_state = config.get(self.policy.PLC_RUNTIME_COORDINATION_KEY())
            state = copy.deepcopy(current_state) if isinstance(current_state, dict) else {}
            capture = self.policy._plc_capture_runtime()(state)
            self.policy._plc_expire_capture_state()(capture, now)
            config[self.policy.PLC_RUNTIME_COORDINATION_KEY()] = state
            session = capture.get("session") if isinstance(capture.get("session"), dict) else None
            event = next((item for item in capture.get("events", []) if isinstance(item, dict) and item.get("trigger_id") == trigger_id), None)
            if event is None or event.get("session_id") != session_id or event.get("user_id") != user_id:
                return
            allowed_statuses = {"processing", "dispatching"} if result is not None else {"claimed", "processing", "dispatching"}
            if event.get("status") not in allowed_statuses:
                return
            event["status"] = "completed" if result is not None else "failed"
            event["finished_at"] = now
            if result is not None:
                event["result"] = copy.deepcopy(result)
                receipt = {
                    "trigger_id": trigger_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "model_id": str(event.get("model_id") or ""),
                    "fingerprint": str(event.get("fingerprint") or ""),
                    "result": copy.deepcopy(result),
                    "completed_at": now,
                }
                current_receipts = config.get(self.policy.PLC_CAPTURE_RESULTS_KEY())
                receipts = copy.deepcopy(current_receipts) if isinstance(current_receipts, dict) else {}
                existing_receipt = receipts.get(trigger_id)
                if isinstance(existing_receipt, dict) and self.policy._plc_canonical()(existing_receipt) != self.policy._plc_canonical()(receipt):
                    raise self.policy.PlcConfigError()("plc_capture_result_receipt_conflict")
                receipts[trigger_id] = receipt
                config[self.policy.PLC_CAPTURE_RESULTS_KEY()] = receipts
            else:
                event["error"] = str(error or "analysis_failed")[:240]
            if session is not None and session.get("session_id") == session_id:
                session["busy"] = False
        self.transactions.mutate_app_config_atomically()(mutate)
