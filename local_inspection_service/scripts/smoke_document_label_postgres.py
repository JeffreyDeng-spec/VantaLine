"""Real PostgreSQL document-claim races and immutable crop replacement."""
import os
from pathlib import Path
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import psycopg
from psycopg import sql
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository


def main():
    dsn = os.environ["VANTALINE_POSTGRES_DSN"]
    schema = "document_test_" + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as control:
        control.execute(postgres_ddl(schema))
        try:
            barrier = threading.Barrier(2)
            def writer(index):
                with psycopg.connect(dsn) as conn:
                    repo = PostgresRuntimeRepository(conn, "test", schema)
                    value = {"id": "one_claim", "owner_user_id": "owner", "root_id": "root", "created_at": 1}
                    row = {**value, "raw_json": {**value, "winner": index}}
                    barrier.wait()
                    return repo.insert_row_once("text_document_imports", row)
            with ThreadPoolExecutor(max_workers=2) as pool:
                assert sum(pool.map(writer, [1, 2])) == 1
            with psycopg.connect(dsn) as conn:
                repo = PostgresRuntimeRepository(conn, "test", schema)
                assert len(repo.fetch_document_import_rows("owner", "root")) == 1
                assert repo.fetch_document_import_rows("other", "root") == []
                standard = {"id": "standard", "owner_user_id": "owner", "name": "test", "material_code": "M", "version_label": "V1",
                    "standard_type": "label", "status": "draft", "source_sha256": "source", "created_at": 1, "updated_at": 1}
                repo.insert_row_once("text_inspection_standards", {**standard, "raw_json": standard})
                def asset(version):
                    return {"id": f"asset_{version}", "standard_id": "standard", "owner_user_id": "owner", "asset_kind": "label_candidate",
                        "ordinal": 0, "status": "candidate", "sha256": f"hash_{version}", "created_at": 1, "updated_at": 1,
                        "document_item_id": "item", "document_crop_version": version}
                def publish(version):
                    return repo.add_text_inspection_standard_asset("standard", "owner", asset(version),
                        revision_id="rev_" + uuid.uuid4().hex, updated_at=2, replace_document_item="item")
                publish(0)
                repo.confirm_text_inspection_standard("standard", "owner", 2, revision_id="initial")
                _, changed = publish(1)
                assert changed["revision_number"] == 2
                assert changed["confirmed_asset_ids"] == ["asset_1"]
                publish(1)
                publish(0)
                assert repo.fetch_by_primary_key("text_inspection_assets", {"id": "asset_0"})["raw_json"]["status"] == "excluded"
                assert repo.fetch_by_primary_key("text_inspection_standard_revisions", {"id": "initial"})["raw_json"]["confirmed_asset_ids"] == ["asset_0"]
                # A late older publisher cannot supersede a newer crop.
                publish(3)
                chosen, unchanged = publish(2)
                assert chosen["id"] == "asset_3" and unchanged["revision_number"] == 3
        finally:
            control.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
    print("document PostgreSQL claims/revisions: PASS")


if __name__ == "__main__":
    main()
