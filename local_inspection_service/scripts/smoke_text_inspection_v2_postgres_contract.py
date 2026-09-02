#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp(prefix="vantaline_text_v2_pg_contract_"))
(TMP / "local_inspection_service" / "static").mkdir(parents=True)
os.environ["LOCAL_INSPECTION_ROOT"] = str(TMP)
os.environ["VANTALINE_DATA_STORE"] = "json"
sys.path.insert(0, str(ROOT))

from local_inspection_service import server  # noqa: E402
from local_inspection_service.scripts.smoke_postgres_runtime_repository import FakeConnection  # noqa: E402
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository, _legacy_text_standard_baseline_revision  # noqa: E402
from local_inspection_service.storage.schema import TEXT_INSPECTION_STANDARD_REVISIONS_SCHEMA_VERSION  # noqa: E402


def main() -> None:
    now = 1_800_000_000
    samples = {
        "standards": {"id": "std_1", "owner_user_id": "user_1", "name": "label", "material_code": "PKG", "version_label": "V1", "standard_type": "label", "status": "draft", "source_sha256": "a" * 64, "created_at": now, "updated_at": now},
        "assets": {"id": "ast_1", "standard_id": "std_1", "owner_user_id": "user_1", "asset_kind": "label_candidate", "ordinal": 1, "status": "candidate", "sha256": "b" * 64, "created_at": now, "updated_at": now},
        "revisions": {"id": "rev_1", "standard_id": "std_1", "owner_user_id": "user_1", "revision_number": 1, "action": "confirm", "asset_id": "", "created_at": now},
        "records": {"id": "ins_1", "owner_user_id": "user_1", "standard_id": "std_1", "comparison_id": "cmp_12345678", "status": "review_required", "auto_decision": "REVIEW_REQUIRED", "final_decision": "", "source_sha256": "c" * 64, "created_at": now, "updated_at": now},
        "sessions": {"id": "man_1", "owner_user_id": "user_1", "standard_id": "std_1", "status": "active", "created_at": now, "updated_at": now},
        "pages": {"id": "pg_1", "session_id": "man_1", "owner_user_id": "user_1", "capture_id": "capture_12345678", "standard_asset_id": "ast_1", "status": "review_required", "created_at": now, "updated_at": now},
        "feedback": {"id": "fb_1", "owner_user_id": "user_1", "standard_id": "std_1", "asset_id": "ast_1", "action": "restore", "created_at": now},
    }
    connection = FakeConnection()
    repository = PostgresRuntimeRepository(connection=connection, database_url_redacted="postgresql:///vantaline")
    for kind, value in samples.items():
        row = server._text_v2_row(kind, value)
        repository.upsert_row(server.TEXT_INSPECTION_TABLES[kind], row)
    sql = "\n".join(statement for statement, _ in connection.statements)
    for table in server.TEXT_INSPECTION_TABLES.values():
        assert f'INSERT INTO "vantaline"."{table}"' in sql, table

    migration = (ROOT / "local_inspection_service" / "storage" / "migrations" / f"{TEXT_INSPECTION_STANDARD_REVISIONS_SCHEMA_VERSION}.sql").read_text(encoding="utf-8")
    assert "text_inspection_standard_revisions" in migration
    assert "UNIQUE (standard_id, revision_number)" in migration
    assert "DROP TABLE" not in migration.upper() and "ALTER TABLE" not in migration.upper()
    repository_source = Path(server.__file__).with_name("storage").joinpath("postgres_runtime_repository.py").read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock" in repository_source
    assert "add_text_inspection_standard_asset" in repository_source
    assert "expected_revision" in repository_source
    baseline = _legacy_text_standard_baseline_revision({
        **samples["standards"], "status": "confirmed",
        "confirmed_assets": [{"id": "ast_old", "sha256": "d" * 64, "ordinal": 1, "mime_type": "image/png"}],
    }, now)
    assert baseline["revision_number"] == 1 and baseline["action"] == "baseline"
    assert baseline["confirmed_asset_ids"] == ["ast_old"]
    print("text inspection v2 PostgreSQL contract smoke passed")


if __name__ == "__main__":
    main()
