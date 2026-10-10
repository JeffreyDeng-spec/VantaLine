"""Single-iteration policy for retained, disabled legacy PLC worker entry points."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

Record = dict[str, Any]


class PendingFlag(Protocol):
    def is_set(self) -> bool: ...


class DispatchSlots(Protocol):
    def acquire(self, blocking: bool = True) -> bool: ...
    def release(self) -> None: ...


@dataclass(frozen=True)
class LegacyOperationConfiguration:
    load: Callable[[], Callable[[], Record]]
    normalize: Callable[[], Callable[[Any], Record]]
    namespace: Callable[[], Callable[[Record], Any]]
    error: Callable[[], type[Exception]]
    activation: Callable[[], Callable[[Record], list[Record]]]
    generation_key: Callable[[], str]


@dataclass(frozen=True)
class LegacyOperationOwnership:
    claim: Callable[[], Callable[[], Record | None]]
    owns: Callable[[], Callable[[int], bool]]


@dataclass(frozen=True)
class LegacyDispatchIteration:
    records: Callable[[], Callable[[Record], list[Record]]]
    verify: Callable[[], Callable[[Record], Record]]
    conflict: Callable[[], type[Exception]]
    pristine: Callable[[], Callable[[Record], bool]]
    blocker: Callable[[], Callable[..., str | None]]
    finalize: Callable[[], Callable[..., Record]]
    run: Callable[[], Callable[..., Record]]


@dataclass(frozen=True)
class LegacyCaptureIteration:
    pending: Callable[[], PendingFlag]
    slots: Callable[[], DispatchSlots]
    read: Callable[[], Callable[..., int]]
    transport: Callable[[], Callable[..., Any] | None]
    disarm: Callable[[], Callable[[str], None]]
    observe: Callable[[], Callable[..., Record | None]]


@dataclass(frozen=True)
class LegacyPlcOperations:
    configuration: LegacyOperationConfiguration
    ownership: LegacyOperationOwnership
    dispatch: LegacyDispatchIteration
    capture: LegacyCaptureIteration

    def plc_reconcile_pending_dispatches_once(self) -> dict[str, Any] | None:
        """Let the fenced I/O owner adopt one durable dispatch that provably never wrote."""
        config = self.configuration.load()()
        try:
            settings = self.configuration.normalize()(self.configuration.namespace()(config))
        except self.configuration.error():
            return None
        if not settings["enabled"] or self.configuration.activation()(settings):
            return None
        owner = self.ownership.claim()()
        if owner is None:
            return None
        for raw_record in self.dispatch.records()(config):
            try:
                record = self.dispatch.verify()(raw_record)
            except self.dispatch.conflict():
                continue
            if not self.dispatch.pristine()(record):
                continue
            blocker = self.dispatch.blocker()(
                record,
                settings=settings,
                generation=int(config.get(self.configuration.generation_key()) or 0),
            )
            if blocker:
                if blocker == "version_not_adoptable":
                    continue
                reason = (
                    "plc_dispatch_queue_timeout"
                    if blocker in {"deadline_missing", "deadline_expired"}
                    else "cancelled_after_config_change"
                )
                return self.dispatch.finalize()(
                    str(record.get("dispatch_id") or ""),
                    expected_version=int(record.get("state_version") or 0),
                    reason=reason,
                )
            result = {
                "request_id": str(record.get("request_id") or ""),
                "passed": bool(record.get("passed")),
            }
            return self.dispatch.run()(
                result,
                source=str(record.get("source") or ""),
                fingerprint=str(record.get("detection_identity") or ""),
            ).get("plc_sync")
        return None


    def plc_capture_poll_once(self) -> dict[str, Any] | None:
        config = self.configuration.load()()
        generation = int(config.get(self.configuration.generation_key()) or 0)
        try:
            settings = self.configuration.normalize()(self.configuration.namespace()(config))
        except self.configuration.error():
            return None
        if not settings["enabled"] or not settings["capture_trigger_enabled"] or self.configuration.activation()(settings):
            return None
        owner = self.ownership.claim()()
        if owner is None:
            return None
        owner_epoch = int(owner["epoch"])
        if self.capture.pending().is_set() or not self.capture.slots().acquire(blocking=False):
            return None
        try:
            if self.capture.pending().is_set() or not self.ownership.owns()(owner_epoch):
                return None
            read_settings = {**settings, "timeout": min(float(settings["timeout"]), 0.15)}
            value = self.capture.read()(
                read_settings,
                settings["capture_input_register"],
                transport_factory=self.capture.transport(),
            )
        except Exception as exc:
            self.capture.disarm()(f"read_failed:{type(exc).__name__}")
            return None
        finally:
            self.capture.slots().release()
        current = self.configuration.load()()
        if (
            int(current.get(self.configuration.generation_key()) or 0) != generation
            or not self.ownership.owns()(owner_epoch)
        ):
            self.capture.disarm()("stale_read_discarded")
            return None
        return self.capture.observe()(
            value,
            generation=generation,
            owner_epoch=owner_epoch,
            trigger_value=int(settings["capture_trigger_value"]),
        )
