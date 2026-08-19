#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from local_inspection_service.storage.postgres_runtime_repository import (  # noqa: E402
    PostgresRuntimeRepository,
    PostgresRuntimeRepositoryError,
)


class Cursor:
    def __init__(self, connection: "Connection") -> None:
        self.connection = connection
        self.rowcount = 0
        self._one = None

    def execute(self, sql, params=()):
        self.connection.statements.append((" ".join(str(sql).split()), tuple(params)))
        if "SELECT raw_json FROM" in sql and "FOR UPDATE" in sql:
            self._one = {"raw_json": dict(self.connection.authority)}
            self.rowcount = 1
        elif "UPDATE" in sql and "final_decision" in sql:
            self.rowcount = 1
        elif "INSERT INTO" in sql and "audit_events" in sql:
            self.rowcount = 1
        elif "evidence_purged_at" in sql and "UPDATE" in sql:
            self.rowcount = 1
        else:
            self.rowcount = 0

    def fetchone(self):
        return self._one

    def fetchall(self):
        return []

    def close(self):
        return None


class Connection:
    def __init__(self, authority: dict) -> None:
        self.authority = authority
        self.statements: list[tuple[str, tuple]] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def main() -> None:
    authority = {
        "id": "itinsp_1",
        "task_id": "pipe_1",
        "auto_decision": "REVIEW_REQUIRED",
        "final_decision": "",
        "updated_at": 1,
    }
    connection = Connection(authority)
    repository = PostgresRuntimeRepository(connection, "postgres://redacted")
    result = repository.review_incoming_text_inspection(
        "itinsp_1",
        decision="RELEASED",
        reason="复核通过",
        actor_user_id="user_1",
        reviewed_at=100,
    )
    assert result["final_decision"] == "RELEASED"
    assert connection.commits == 1 and connection.rollbacks == 0
    sql_text = "\n".join(sql for sql, _ in connection.statements)
    assert "FOR UPDATE" in sql_text
    assert "UPDATE" in sql_text and "final_decision" in sql_text
    assert "audit_events" in sql_text and "ON CONFLICT (id) DO NOTHING" in sql_text

    same_connection = Connection({**authority, "final_decision": "RELEASED", "review_reason": "原原因"})
    same_repository = PostgresRuntimeRepository(same_connection, "postgres://redacted")
    same = same_repository.review_incoming_text_inspection(
        "itinsp_1",
        decision="RELEASED",
        reason="不得改写的新原因",
        actor_user_id="user_2",
        reviewed_at=200,
    )
    assert same["review_reason"] == "原原因"
    assert not any(sql.startswith("UPDATE ") for sql, _ in same_connection.statements)

    conflict_connection = Connection({**authority, "final_decision": "REJECTED"})
    conflict_repository = PostgresRuntimeRepository(conflict_connection, "postgres://redacted")
    try:
        conflict_repository.review_incoming_text_inspection(
            "itinsp_1",
            decision="RELEASED",
            reason="冲突",
            actor_user_id="user_1",
            reviewed_at=300,
        )
        raise AssertionError("opposite concurrent decision did not fail")
    except PostgresRuntimeRepositoryError:
        pass
    assert conflict_connection.rollbacks == 1

    retention_connection = Connection(authority)
    retention_repository = PostgresRuntimeRepository(retention_connection, "postgres://redacted")
    assert retention_repository.mark_incoming_text_evidence_purged("itinsp_1", purged_at=400, retention_days=90)
    retention_sql = retention_connection.statements[0][0]
    assert "jsonb_set" in retention_sql and "raw_json = %s" not in retention_sql

    migration = (ROOT / "local_inspection_service" / "storage" / "migrations" / "2026_08_06_incoming_text_v1.sql").read_text(encoding="utf-8")
    assert migration.startswith("BEGIN;") and migration.rstrip().endswith("COMMIT;")
    assert "UNIQUE (owner_user_id, task_id, capture_id)" in migration
    assert "WHERE status = 'active'" in migration
    assert "vantaline.feature_migrations" in migration
    assert "INSERT INTO vantaline.schema_migrations" not in migration
    assert "ON CONFLICT (version) DO NOTHING" in migration
    print("incoming text postgres contract smoke: PASS")


if __name__ == "__main__":
    main()
