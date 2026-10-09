"""Retained PLC coordination state; does not enable server-side serial I/O."""
from collections.abc import Callable
import copy
from dataclasses import dataclass
from typing import Any, Protocol

Record = dict[str, Any]
Mutation = Callable[[Record], None]


class NamespaceRepository(Protocol):
    def mutate_app_config_namespace(self, protected_keys: tuple[str, ...], mutator: Mutation, *, updated_at: int) -> Record: ...


@dataclass(frozen=True)
class LegacyCoordinationStorage:
    repository: Callable[[], Callable[[], NamespaceRepository | None]]
    mutate_config: Callable[[], Callable[[Mutation], Record]]
    load_config: Callable[[], Callable[[], Record]]
    mutate_rows: Callable[[], Callable[[Record, Mutation], None]]
    mutate_runtime: Callable[[], Callable[[Mutation], Record]]
    start_heartbeat: Callable[[], Callable[[int], None]]


@dataclass(frozen=True)
class LegacyCoordinationPolicy:
    runtime_key: Callable[[], str]
    receipts_key: Callable[[], str]
    process_id: Callable[[], str]
    lease_seconds: Callable[[], float]
    quarantine_seconds: Callable[[], float]
    clock: Callable[[], Callable[[], float]]


@dataclass(frozen=True)
class LegacyRuntimeCoordination:
    storage: LegacyCoordinationStorage
    policy: LegacyCoordinationPolicy

    def mutate_plc_runtime_coordination(self, mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        """Mutate only the small PLC runtime row; never rewrite the dispatch audit list on heartbeats."""
        repository = self.storage.repository()()
        if repository is not None:
            values = repository.mutate_app_config_namespace(
                (self.policy.runtime_key(),),
                lambda rows: self.storage.mutate_rows()(rows, mutator),
                updated_at=int(self.policy.clock()()),
            )
            value = values.get(self.policy.runtime_key())
            return copy.deepcopy(value) if isinstance(value, dict) else {}

        result: dict[str, Any] = {}
        def mutate(config: dict[str, Any]) -> None:
            nonlocal result
            current = config.get(self.policy.runtime_key())
            state = copy.deepcopy(current) if isinstance(current, dict) else {}
            mutator(state)
            config[self.policy.runtime_key()] = state
            result = copy.deepcopy(state)
        self.storage.mutate_config()(mutate)
        return result


    def plc_completed_capture_receipt(self, trigger_id: str) -> dict[str, Any] | None:
        receipts = self.storage.load_config()().get(self.policy.receipts_key())
        receipt = receipts.get(trigger_id) if isinstance(receipts, dict) else None
        return copy.deepcopy(receipt) if isinstance(receipt, dict) else None


    def _mutate_plc_runtime_rows(self, rows: dict[str, Any], mutator: Callable[[dict[str, Any]], None]) -> None:
        current = rows.get(self.policy.runtime_key())
        state = copy.deepcopy(current) if isinstance(current, dict) else {}
        mutator(state)
        rows[self.policy.runtime_key()] = state


    def plc_claim_or_renew_io_owner(self) -> dict[str, Any] | None:
        now = self.policy.clock()()
        claimed: dict[str, Any] | None = None
        def mutate(state: dict[str, Any]) -> None:
            nonlocal claimed
            owner = state.get("io_owner") if isinstance(state.get("io_owner"), dict) else {}
            owner_id = str(owner.get("owner_id") or "")
            expires_at = float(owner.get("expires_at") or 0.0)
            quarantine_until = float(owner.get("quarantine_until") or 0.0)
            if owner_id == self.policy.process_id():
                epoch = int(owner.get("epoch") or 1)
            elif expires_at <= now and quarantine_until <= now:
                epoch = int(owner.get("epoch") or 0) + 1
            else:
                return
            claimed = {
                "owner_id": self.policy.process_id(),
                "epoch": epoch,
                "heartbeat_at": now,
                "expires_at": now + self.policy.lease_seconds(),
                "quarantine_until": now + self.policy.lease_seconds() + self.policy.quarantine_seconds(),
            }
            state["io_owner"] = copy.deepcopy(claimed)
        self.storage.mutate_runtime()(mutate)
        if claimed is not None and self.storage.repository()() is not None:
            self.storage.start_heartbeat()(int(claimed["epoch"]))
        return claimed


    def plc_current_process_owns_io(self, epoch: int | None = None) -> bool:
        current = self.storage.load_config()().get(self.policy.runtime_key())
        owner = current.get("io_owner") if isinstance(current, dict) and isinstance(current.get("io_owner"), dict) else {}
        return bool(
            owner.get("owner_id") == self.policy.process_id()
            and float(owner.get("expires_at") or 0.0) > self.policy.clock()()
            and (epoch is None or int(owner.get("epoch") or 0) == epoch)
        )
