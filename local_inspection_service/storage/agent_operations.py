"""Durable operation primitives. No network, model or physical I/O occurs here.

All transitions lock the account first, so reservations, policy revocation and
worker claims serialize across API processes. Uncertain attempts are never
re-queued. Domain services must validate ownership and supply a fixed operation
kind and bounded validated payload; this is not a generic HTTP executor.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from contextlib import contextmanager


class OperationConflict(ValueError):
    pass


class OperationDenied(ValueError):
    pass


def canonical_payload(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode()) > 65536:
        raise ValueError("operation payload exceeds 64KiB; use asset IDs")
    return encoded


class AgentOperationsRepository:
    """Composes the existing runtime repository; never creates connections."""

    def __init__(self, repository):
        self.repository = repository

    @contextmanager
    def transaction(self, owner):
        if not owner:
            raise OperationDenied("account required")
        cursor = self.repository._cursor()
        try:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("agent:" + owner,))
            yield cursor
            self.repository.connection.commit()
        except Exception:
            self.repository.connection.rollback()
            raise
        finally:
            cursor.close()

    def table(self, name):
        return self.repository._qualified_table(name)

    def read(self, cursor, table, owner, identifier):
        cursor.execute(f"SELECT raw_json FROM {self.table(table)} WHERE owner_user_id=%s AND id=%s", (owner, identifier))
        row = cursor.fetchone()
        if row is None:
            return None
        raw = self.repository._row_to_dict(cursor, row)["raw_json"]
        return json.loads(raw) if isinstance(raw, str) else raw

    def write(self, cursor, table, value, *, insert=False):
        # Audit rows are append-only through this interface.
        if table == "agent_operation_audit" and not insert:
            raise ValueError("audit is append-only")
        columns = ["id", "owner_user_id", "created_at", "raw_json"]
        values = [value["id"], value["owner_user_id"], value["created_at"], canonical_payload(value)]
        if table == "agent_operations":
            columns += ["idempotency_key", "status", "updated_at"]
            values += [value["idempotency_key"], value["status"], value["updated_at"]]
        placeholders = ["%s::jsonb" if column == "raw_json" else "%s" for column in columns]
        sql = f"INSERT INTO {self.table(table)} ({','.join(columns)}) VALUES ({','.join(placeholders)})"
        if not insert:
            sql += " ON CONFLICT (id) DO UPDATE SET " + ",".join(f"{column}=EXCLUDED.{column}" for column in columns if column not in {"id", "owner_user_id", "created_at"})
        cursor.execute(sql, tuple(values))

    def audit(self, cursor, owner, operation_id, event):
        self.write(cursor, "agent_operation_audit", {"id":uuid.uuid4().hex, "owner_user_id":owner, "created_at":int(time.time()), "operation_id":operation_id, "event":event}, insert=True)

    def policy(self, owner):
        with self.transaction(owner) as cursor:
            return self.read(cursor, "agent_policies", owner, owner)

    def set_policy(self, owner, *, expected_version, enabled, budget, cloud_targets):
        if not isinstance(enabled, bool) or type(budget) is not int or not 0 <= budget <= 10**12:
            raise ValueError("invalid policy")
        if not isinstance(cloud_targets, list) or len(cloud_targets) > 50 or any(not isinstance(v,str) or not v or len(v)>80 or ":" in v or "/" in v for v in cloud_targets):
            raise ValueError("cloud targets must be configured provider IDs, not URLs")
        with self.transaction(owner) as cursor:
            previous = self.read(cursor, "agent_policies", owner, owner)
            if (previous or {}).get("version", 0) != expected_version:
                raise OperationConflict("policy version changed")
            now = int(time.time())
            policy = {"id":owner, "owner_user_id":owner, "created_at":(previous or {}).get("created_at",now), "version":expected_version+1, "enabled":enabled, "budget":budget, "reserved":(previous or {}).get("reserved",0), "spent":(previous or {}).get("spent",0), "cloud_targets":sorted(set(cloud_targets))}
            self.write(cursor,"agent_policies",policy)
            self.audit(cursor,owner,"","policy_updated")
            return policy

    def accept(self, owner, *, kind, payload, idempotency_key, reserve, queue_limit=20):
        if not isinstance(kind,str) or not kind or len(kind)>80 or not isinstance(idempotency_key,str) or not 8<=len(idempotency_key)<=128:
            raise ValueError("invalid operation identity")
        if type(reserve) is not int or reserve<0 or type(queue_limit) is not int or not 1<=queue_limit<=20:
            raise ValueError("invalid reservation or queue limit")
        identity = hashlib.sha256(canonical_payload({"kind":kind,"payload":payload,"reserve":reserve}).encode()).hexdigest()
        identifier = hashlib.sha256((owner+"\0"+idempotency_key).encode()).hexdigest()
        with self.transaction(owner) as cursor:
            previous = self.read(cursor,"agent_operations",owner,identifier)
            if previous:
                if previous["parameter_hash"] != identity:
                    raise OperationConflict("idempotency key reused with different parameters")
                return previous
            policy = self.read(cursor,"agent_policies",owner,owner)
            if not policy or not policy["enabled"]:
                raise OperationDenied("operation admission disabled")
            if policy["budget"] - policy["reserved"] - policy["spent"] < reserve:
                raise OperationDenied("budget exhausted")
            cursor.execute(f"SELECT count(*) AS total FROM {self.table('agent_operations')} WHERE owner_user_id=%s AND status IN ('accepted','running','cancel_requested','outcome_unknown')",(owner,))
            if self.repository._row_to_dict(cursor,cursor.fetchone())["total"] >= queue_limit:
                raise OperationDenied("operation queue full")
            now = int(time.time())
            operation = {"id":identifier,"owner_user_id":owner,"kind":kind,"payload":payload,"parameter_hash":identity,"idempotency_key":idempotency_key,"reserved":reserve,"status":"accepted","version":1,"created_at":now,"updated_at":now}
            policy["reserved"] += reserve
            self.write(cursor,"agent_policies",policy)
            self.write(cursor,"agent_operations",operation,insert=True)
            self.audit(cursor,owner,identifier,"accepted")
            return operation

    def get(self, owner, identifier):
        with self.transaction(owner) as cursor:
            return self.read(cursor,"agent_operations",owner,identifier)

    def transition(self, owner, identifier, *, expected_version, event, actual_cost=0, provider_id="", external_job_id="", now=None):
        if type(actual_cost) is not int or actual_cost < 0:
            raise ValueError("invalid actual cost")
        if not isinstance(external_job_id,str) or len(external_job_id)>200:
            raise ValueError("invalid provider job identity")
        now = int(time.time()) if now is None else now
        with self.transaction(owner) as cursor:
            operation = self.read(cursor,"agent_operations",owner,identifier)
            if not operation:
                raise OperationDenied("operation not found")
            if operation["version"] != expected_version:
                raise OperationConflict("operation version changed")
            policy = self.read(cursor,"agent_policies",owner,owner)
            status = operation["status"]
            release = False
            if event == "claim" and status == "accepted":
                if not policy["enabled"]:
                    raise OperationDenied("operation admission disabled")
                operation.update(status="running", attempt_id=uuid.uuid4().hex, claimed_at=now)
                self.write(cursor,"agent_operation_attempts",{"id":operation["attempt_id"],"owner_user_id":owner,"operation_id":identifier,"created_at":now,"status":"prepared"},insert=True)
            elif event == "egress" and status == "running":
                if not policy["enabled"] or provider_id not in policy["cloud_targets"]:
                    raise OperationDenied("external provider disabled")
                attempt = self.read(cursor,"agent_operation_attempts",owner,operation["attempt_id"])
                if attempt["status"] != "prepared":
                    raise OperationConflict("external call has already been attempted; never replay")
                attempt.update(status="attempting",provider_id=provider_id)
                self.write(cursor,"agent_operation_attempts",attempt)
            elif event == "external_job" and status in {"running","cancel_requested","outcome_unknown"}:
                attempt = self.read(cursor,"agent_operation_attempts",owner,operation["attempt_id"])
                if not external_job_id or (attempt.get("external_job_id") and attempt["external_job_id"] != external_job_id):
                    raise OperationConflict("provider identity missing or changed")
                attempt["external_job_id"] = external_job_id
                self.write(cursor,"agent_operation_attempts",attempt)
                operation["external_job_id"] = external_job_id
            elif event == "cancel" and status == "accepted":
                operation["status"], release = "cancelled", True
            elif event == "cancel" and status in {"running","cancel_requested"}:
                operation["status"] = "cancel_requested"
            elif event == "unknown" and status in {"running","cancel_requested"}:
                operation["status"] = "outcome_unknown"
            elif event in {"complete","fail_verified","cancel_verified"} and status in {"running","cancel_requested","outcome_unknown"}:
                if actual_cost > operation["reserved"]:
                    raise OperationConflict("actual cost exceeds reservation; retain unknown outcome for reconciliation")
                operation["status"] = {"complete":"completed","fail_verified":"failed","cancel_verified":"cancelled"}[event]
                operation["actual_cost"], release = actual_cost, True
                policy["spent"] += actual_cost
            else:
                raise OperationConflict("invalid state transition")
            if release:
                policy["reserved"] -= operation["reserved"]
                self.write(cursor,"agent_policies",policy)
            operation.update(version=operation["version"]+1,updated_at=now)
            self.write(cursor,"agent_operations",operation)
            self.audit(cursor,owner,identifier,event)
            return operation
