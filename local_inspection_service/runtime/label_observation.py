"""Read-only database evidence of periodic progress; never start an application."""
from dataclasses import dataclass
import json
import math
import time

from .label_identity import RuntimeUnavailable
from ..storage.label_runtime import LabelRuntimeStore, valid_heartbeat


@dataclass(frozen=True)
class RuntimeObservation:
    revision: str
    maintenance: bool
    paused: bool
    queued: int
    active: int
    # role, instance, pid, actual persisted sampled_at
    roles: tuple[tuple[str, str, int, float], ...]


@dataclass(frozen=True)
class RuntimeProgress:
    before: RuntimeObservation
    after: RuntimeObservation


def read_observation(repository, identity, *, now=time.time):
    """The connection must use repeatable-read, read-only transactions."""
    store = LabelRuntimeStore(repository)
    with store.transaction(write=False) as cursor:
        # Verify the session contract before reading any runtime records.
        cursor.execute("SHOW transaction_read_only")
        if cursor.fetchone()[0] != "on":
            raise RuntimeUnavailable("Runtime observation requires a read-only transaction")
        cursor.execute("SHOW transaction_isolation")
        if cursor.fetchone()[0] != "repeatable read":
            raise RuntimeUnavailable("Runtime observation requires a stable snapshot")
        state = store.require(cursor, identity)
        cursor.execute(f"SELECT count(*) FILTER (WHERE status='queued'), "
                       "count(*) FILTER (WHERE status='running') "
                       f"FROM {store.jobs} WHERE kind='run' AND status IN ('queued','running')")
        queued, active = cursor.fetchone()
        cursor.execute(f"SELECT id,raw_json FROM {store.table} WHERE id IN (%s,%s)",
                       ("heartbeat:web", "heartbeat:label"))
        samples = {row["id"]: row["raw_json"] for row in
                   (repository._row_to_dict(cursor, raw) for raw in cursor.fetchall())}
        sampled_now = now()
        roles = []
        for role in (("web", "label") if identity.mode == "external" else ("web",)):
            sample = samples.get("heartbeat:" + role)
            if isinstance(sample, str):
                try:
                    sample = json.loads(sample)
                except ValueError:
                    sample = None
            if (not valid_heartbeat(sample) or sample["role"] != role
                    or sample["git_commit"] != identity.commit or sample["release"] != identity.release
                    or sample["worker_mode"] != identity.mode or sample["config_revision"] != identity.config_revision
                    or not 0 <= sampled_now - sample["sampled_at"] <= 15
                    or sample["state"] not in ("ready", "drained")):
                raise RuntimeUnavailable("Runtime heartbeat observation unavailable")
            roles.append((role, sample["instance"], sample["pid"], sample["sampled_at"]))
        if not 0 <= active <= 2:
            raise RuntimeUnavailable("Runtime concurrency observation invalid")
        return RuntimeObservation(state["revision"], state["maintenance"], state["paused"],
                                  queued, active, tuple(roles))


def observe_progress(read, *, timeout=30, clock=time.monotonic, sleep=time.sleep):
    """Require both roles to advance within one stable generation and process set."""
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise RuntimeUnavailable("Runtime observation deadline invalid")
    deadline = clock() + timeout
    first = read()
    while clock() < deadline:
        sleep(min(1, max(0, deadline - clock())))
        if clock() >= deadline:
            break
        second = read()
        if clock() >= deadline:
            break
        if (first.revision, first.maintenance, first.paused) != (
                second.revision, second.maintenance, second.paused):
            raise RuntimeUnavailable("Runtime admission changed during observation")
        if tuple(row[:3] for row in first.roles) != tuple(row[:3] for row in second.roles):
            raise RuntimeUnavailable("Runtime process changed during observation")
        if any(after[3] < before[3] for before, after in zip(first.roles, second.roles)):
            raise RuntimeUnavailable("Runtime heartbeat regressed during observation")
        if all(after[3] > before[3] for before, after in zip(first.roles, second.roles)):
            return RuntimeProgress(first, second)
    raise RuntimeUnavailable("Runtime heartbeat did not progress")
