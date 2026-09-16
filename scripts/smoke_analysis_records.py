"""Actual analysis repositories with synthetic records and optional isolated PostgreSQL."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from local_inspection_service.analytics.analysis_records import AnalysisNormalization, AnalysisNormalizer
from local_inspection_service.analytics.analysis_repository import AnalysisRepository, AnalysisStoreDependencies
from local_inspection_service.analytics.analysis_service import AnalysisAccess, AnalysisRecords
from local_inspection_service.runtime.connections import ThreadRepositoryFactory
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl


def normalizer():
    return AnalysisNormalizer(AnalysisNormalization(
        default_task_id="default-task", default_task_label="Default task",
        clean_task_name=lambda value, fallback: str(value or fallback).strip(),
        created_at=lambda record: int(record.get("created_at") or 0),
        updated_at=lambda record: int(record.get("updated_at") or 0),
        owner_id=lambda record: record.get("owner_user_id", "legacy"),
        owner_username=lambda record: record.get("owner_username", "legacy"),
    )).normalize_data_analysis_record


def seed(identity, *, timestamp=100, owner="alice"):
    return {"record_id": identity, "created_at": timestamp, "updated_at": timestamp,
            "owner_user_id": owner, "owner_username": owner, "task": {"id": "task-1", "name": "Task"},
            "source_image": {"filename": "synthetic.png"}, "ai_summary": {"passed": True},
            "image_processing_items": [{"id": str(i)} for i in range(205)]}


def access_contract(repository):
    checks = []
    def require(record, user, *, write=False):
        checks.append((record["record_id"], user["id"], write))
        if not user.get("admin") and record["owner_user_id"] != user["id"]:
            raise HTTPException(403, "denied")
    service = AnalysisRecords(repository, AnalysisAccess(
        is_admin=lambda user: bool(user.get("admin")),
        visible=lambda record, user, target: (not target or record["owner_user_id"] == target)
            if user.get("admin") else record["owner_user_id"] == user["id"],
        require_access=require,
    ))
    repository.save_data_analysis_records([seed("a"), seed("b", owner="bob")])
    assert [r["record_id"] for r in service.data_analysis_records_for_user({"id": "alice"})] == ["a"]
    assert [r["record_id"] for r in service.data_analysis_records_for_user({"id": "admin", "admin": True}, target_user_id="bob")] == ["b"]
    try: service.data_analysis_records_for_user({"id": "alice"}, target_user_id="bob")
    except HTTPException as exc: assert exc.status_code == 403
    else: raise AssertionError("cross-account filter accepted")
    try: service.delete_data_analysis_record("b", {"id": "alice"}, missing_ok=True)
    except HTTPException as exc: assert exc.status_code == 403
    else: raise AssertionError("unauthorized delete accepted")
    assert repository.load_data_analysis_record("b") is not None
    assert checks[-1] == ("b", "alice", True)
    assert service.delete_data_analysis_record("b", {"id": "bob"}) == "b"
    assert service.delete_data_analysis_record("b", {"id": "bob"}, missing_ok=True) is None
    try: service.find_data_analysis_record("missing", {"id": "alice"})
    except HTTPException as exc: assert exc.status_code == 404
    else: raise AssertionError("missing record accepted")


def json_contract():
    with tempfile.TemporaryDirectory(prefix="analysis-json-") as temporary:
        path = Path(temporary) / "data_analysis_records.json"
        lock = threading.RLock()
        repository = AnalysisRepository(AnalysisStoreDependencies(
            path=lambda: path, runtime_repository=lambda: None, lock=lambda: lock, ensure_dirs=lambda: None,
        ), normalizer())
        assert repository.load_data_analysis_records() == []
        for payload in ("invalid", "null", '{"records": {}}'):
            path.write_text(payload, encoding="utf-8")
            assert repository.load_data_analysis_records() == []
        path.write_text(json.dumps([seed("old"), None, {}]), encoding="utf-8")
        assert [r["record_id"] for r in repository.load_data_analysis_records()] == ["old"]
        repository.save_data_analysis_records([seed("a", timestamp=200), seed("b", timestamp=200), seed("c", timestamp=100)])
        assert [r["record_id"] for r in repository.load_data_analysis_records()] == ["b", "a", "c"]
        record = repository.save_data_analysis_record(seed("dirty/id", timestamp=300), prepend=True, max_records=3)
        assert record["record_id"] == "dirty_id" and len(record["image_processing_items"]) == 200
        assert [r["record_id"] for r in repository.load_data_analysis_records()] == ["dirty_id", "b", "a"]
        repository.save_data_analysis_record({**record, "ai_summary": {"passed": False}})
        assert repository.load_data_analysis_record("dirty/id")["ai_summary"] == {"passed": False}
        assert not path.with_name(path.name + ".tmp").exists()
        access_contract(repository)


def postgres_contract(dsn):
    import psycopg
    from psycopg import sql
    schema = "analysis_" + uuid.uuid4().hex
    connections = []
    def connect():
        connection = psycopg.connect(dsn)
        connections.append(connection)
        return SimpleNamespace(store="postgres", repository=PostgresRuntimeRepository(connection, "fixture", schema))
    factory = ThreadRepositoryFactory(connect, lambda: schema)
    with tempfile.TemporaryDirectory(prefix="analysis-pg-") as temporary, psycopg.connect(dsn, autocommit=True) as control:
        path = Path(temporary) / "must-not-exist.json"
        control.execute(postgres_ddl(schema))
        lock = threading.RLock()
        repository = AnalysisRepository(AnalysisStoreDependencies(
            path=lambda: path, runtime_repository=lambda: factory.selection().repository,
            lock=lambda: lock, ensure_dirs=lambda: None,
        ), normalizer())
        try:
            with factory.thread_scope():
                access_contract(repository)
                repository.save_data_analysis_records([])
            def write(index):
                with factory.thread_scope():
                    record = seed(f"record_{index:03d}", timestamp=index + 1, owner="alice" if index % 2 else "bob")
                    repository.save_data_analysis_record(record)
                    repository.save_data_analysis_record({**record, "ai_summary": {"passed": False}})
                    assert repository.load_data_analysis_record(record["record_id"])["ai_summary"] == {"passed": False}
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(write, range(40)))
            with factory.thread_scope():
                records = repository.load_data_analysis_records()
                assert len(records) == 40 and records[0]["record_id"] == "record_039"
                assert all(r["ai_summary"] == {"passed": False} for r in records)
                repository.delete_data_analysis_record("record_001")
                assert len(repository.load_data_analysis_records()) == 39
            assert not path.exists(), "PostgreSQL mode wrote a JSON fallback"
            assert all(connection.closed for connection in connections)
        finally:
            factory.clear()
            control.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--postgres", action="store_true")
    arguments = parser.parse_args()
    json_contract()
    if arguments.postgres:
        postgres_contract(os.environ["VANTALINE_POSTGRES_DSN"])
    print("PASS analysis JSON/optional PostgreSQL persistence, normalization, ownership and concurrent row upserts")
