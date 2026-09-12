"""Real PostgreSQL in an explicitly supplied test database and disposable schema."""
import copy
import os
import threading
import uuid

import psycopg
from psycopg import sql
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository


def main():
    dsn = os.environ["PREPARATION_TEST_DATABASE_URL"]
    schema = "preparation_test_"+uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as control:
        control.execute(postgres_ddl(schema))
        try:
            with psycopg.connect(dsn) as connection:
                repo = PostgresRuntimeRepository(connection, "test", schema)
                claim = dict(id="ocr-test",owner_user_id="owner",status="attempting",created_at=1,raw_json={"state":"attempting"})
                assert repo.insert_row_once("text_ocr_evidence",claim)
                assert not repo.insert_row_once("text_ocr_evidence",claim)
                assert not repo.update_text_attempt("text_ocr_evidence",{**claim,"owner_user_id":"other","status":"completed"},"attempting")
                assert repo.update_text_attempt("text_ocr_evidence",{**claim,"status":"unknown"},"attempting")
                assert not repo.update_text_attempt("text_ocr_evidence",{**claim,"status":"completed"},"attempting")
                assert repo.fetch_one_by_columns("text_ocr_evidence",{"id":"ocr-test","owner_user_id":"other"}) is None
                standard = dict(id="std", owner_user_id="owner", standard_type="label", status="draft", revision_number=0)
                asset = dict(id="asset", standard_id="std", owner_user_id="owner", status="candidate", ordinal=1, sha256="a"*64, preparation_required=True)
                repo.upsert_row("text_inspection_standards", dict(**standard, name="test", material_code="test", version_label="1", source_sha256="b"*64, created_at=1, updated_at=1, raw_json=standard))
                repo.upsert_row("text_inspection_assets", dict(**{k:v for k,v in asset.items() if k != "preparation_required"}, asset_kind="label_candidate", created_at=1, updated_at=1, raw_json=asset))
                winners = []
                def worker():
                    with psycopg.connect(dsn) as conn:
                        worker_repo = PostgresRuntimeRepository(conn, "test", schema)
                        def claim(std, assets):
                            if assets[0].get("attempt"): return False
                            assets[0]["attempt"] = "claimed-before-provider"
                            return True
                        winners.append(worker_repo.mutate_text_document("std", "owner", claim))
                threads = [threading.Thread(target=worker) for _ in range(2)]
                for thread in threads: thread.start()
                for thread in threads: thread.join()
                assert sorted(winners) == [False, True]
                def publish(std, assets):
                    std["status"] = "confirmed"
                    assets[0]["active_preparation"] = dict(id="prep1", sha256="c"*64, elements=[{"id":"e1", "text":"MODEL X"}])
                    return {"published": True}
                repo.mutate_text_document("std", "owner", publish, revision_action="prepare")
                first = repo.fetch_by_primary_key("text_inspection_standards", {"id":"std"})["raw_json"]
                assert first["revision_number"] == 1
                assert first["confirmed_assets"][0]["sha256"] == "a"*64
                assert first["confirmed_assets"][0]["reference_sha256"] == "c"*64
                historical = copy.deepcopy(repo.fetch_by_primary_key("text_inspection_standard_revisions", {"id":first["current_revision_id"]}))
                def edit(std, assets):
                    assets[0]["active_preparation"] = dict(id="prep2", sha256="d"*64, elements=[{"id":"e1", "text":"MODEL Y"}])
                    return {"published": True}
                repo.mutate_text_document("std", "owner", edit, revision_action="prepare")
                assert repo.fetch_by_primary_key("text_inspection_standard_revisions", {"id":first["current_revision_id"]}) == historical
                try:
                    repo.mutate_text_document("std", "other", edit, revision_action="prepare")
                    raise AssertionError("cross owner accepted")
                except Exception as exc:
                    assert not isinstance(exc, AssertionError)
                def fail(std, assets):
                    assets[0]["active_preparation"]["id"] = "must-not-commit"
                    raise ValueError("fixture failure")
                try: repo.mutate_text_document("std", "owner", fail, revision_action="prepare")
                except ValueError: pass
                assert repo.fetch_by_primary_key("text_inspection_assets", {"id":"asset"})["raw_json"]["active_preparation"]["id"] == "prep2"
        finally:
            control.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
    print("preparation real PostgreSQL concurrent claim/atomic publish/history/rollback/owner: PASS")


if __name__ == "__main__": main()
