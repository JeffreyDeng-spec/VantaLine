"""Persist operational control under the same transaction fence as label submit/claim."""
from contextlib import contextmanager
import json
import time
import uuid

from ..runtime.label_identity import LabelRuntimeIdentity, RuntimeUnavailable

CONTROL_ID = "control"
KEYS = {"schema", "git_commit", "worker_mode", "config_revision", "maintenance", "paused", "revision"}


class LabelMaintenance(RuntimeUnavailable):
    pass


def decode_state(value):
    try:
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict) or value.keys() != KEYS or type(value["schema"]) is not int or value["schema"] != 1:
            raise ValueError()
        if type(value["maintenance"]) is not bool or type(value["paused"]) is not bool:
            raise ValueError()
        import re
        if not isinstance(value["revision"], str) or not re.fullmatch("[0-9a-f]{32}", value["revision"]):
            raise ValueError()
        if (not isinstance(value["git_commit"], str) or not re.fullmatch("[0-9a-f]{40}", value["git_commit"])
                or value["worker_mode"] not in ("embedded", "external")
                or (value["config_revision"] is not None and (not isinstance(value["config_revision"], str)
                    or not re.fullmatch("[0-9a-f]{64}", value["config_revision"])))
                or (value["worker_mode"] == "external" and value["config_revision"] is None)):
            raise ValueError()
        return value
    except (ValueError, TypeError, KeyError):
        raise RuntimeUnavailable("Label runtime state invalid") from None


class LabelRuntimeStore:
    def __init__(self, repository):
        self.repository = repository
        self.table = repository._qualified_table("label_runtime_state")
        self.jobs = repository._qualified_table("label_inspection_objects")

    @contextmanager
    def transaction(self, *, write=True):
        cursor = self.repository._cursor()
        try:
            if write:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended('label-inspection-v1',0))")
            yield cursor
            self.repository.connection.commit()
        except BaseException:
            self.repository.connection.rollback()
            raise
        finally:
            cursor.close()

    def read(self, cursor):
        cursor.execute(f"SELECT raw_json FROM {self.table} WHERE id=%s", (CONTROL_ID,))
        row = cursor.fetchone()
        return decode_state(self.repository._row_to_dict(cursor, row)["raw_json"]) if row is not None else None

    def require(self, cursor, identity: LabelRuntimeIdentity):
        state = self.read(cursor)
        if (state is None or state["git_commit"] != identity.commit or state["worker_mode"] != identity.mode
                or state["config_revision"] != identity.config_revision):
            raise RuntimeUnavailable("Label runtime generation mismatch")
        return state

    def write(self, cursor, state):
        decode_state(state)
        cursor.execute(f"INSERT INTO {self.table}(id,updated_at,raw_json) VALUES (%s,%s,%s::jsonb) "
                       "ON CONFLICT(id) DO UPDATE SET updated_at=EXCLUDED.updated_at,raw_json=EXCLUDED.raw_json",
                       (CONTROL_ID, int(time.time()), json.dumps(state, separators=(",", ":"))))

    def initialize(self, identity: LabelRuntimeIdentity):
        """Only the current Web generation initializes; new builds always start fenced."""
        with self.transaction() as cursor:
            state = self.read(cursor)
            if state and state["git_commit"] == identity.commit:
                return self.require(cursor, identity)
            state = {"schema": 1, "git_commit": identity.commit, "worker_mode": identity.mode,
                     "config_revision": identity.config_revision, "maintenance": True, "paused": True,
                     "revision": uuid.uuid4().hex}
            self.write(cursor, state)
            return state

    def change(self, identity: LabelRuntimeIdentity, revision: str, *, maintenance=None, paused=None):
        with self.transaction() as cursor:
            state = self.require(cursor, identity)
            if maintenance is not None:
                state["maintenance"] = maintenance
            if paused is not None:
                state["paused"] = paused
            state["revision"] = revision
            self.write(cursor, state)
            return state

    def snapshot(self, identity: LabelRuntimeIdentity):
        with self.transaction(write=False) as cursor:
            state = self.require(cursor, identity)
            cursor.execute(f"SELECT count(*) FILTER (WHERE status='queued'), "
                           "count(*) FILTER (WHERE status='running'), "
                           "min(created_at) FILTER (WHERE status='queued') "
                           f"FROM {self.jobs} WHERE kind='run' AND status IN ('queued','running')")
            queued, active, oldest = cursor.fetchone()
            return state, {"queued_runs": queued, "active_runs": active,
                           "oldest_queued_at": oldest}

    def require_admission(self, cursor, identity: LabelRuntimeIdentity):
        if self.require(cursor, identity)["maintenance"]:
            raise LabelMaintenance("标签检测维护中，请稍后重试；已提交任务继续处理")

    def may_claim(self, cursor, identity: LabelRuntimeIdentity):
        return not self.require(cursor, identity)["paused"]
