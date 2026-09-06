#!/usr/bin/env python3
"""Real PostgreSQL insert-once races in an isolated, disposable schema."""
import json
import os
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import psycopg
from psycopg import sql
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository


def main():
    dsn=os.environ["VANTALINE_POSTGRES_DSN"]
    schema="label_test_"+uuid.uuid4().hex
    with psycopg.connect(dsn,autocommit=True) as control:
        control.execute(postgres_ddl(schema))
        try:
            barrier=threading.Barrier(2)
            def writer(index):
                with psycopg.connect(dsn) as conn:
                    repo=PostgresRuntimeRepository(conn,"test",schema)
                    row={"id":"root_v1","owner_user_id":"owner","created_at":1,"raw_json":{"id":"root_v1","root_id":"root","version":1,"winner":index}}
                    barrier.wait()
                    return repo.insert_row_once("text_label_extractions",row)
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes=list(pool.map(writer,[1,2]))
            assert sum(outcomes)==1,"concurrent revisions must have one winner"
            with psycopg.connect(dsn) as conn:
                repo=PostgresRuntimeRepository(conn,"test",schema)
                winner=repo.fetch_by_primary_key("text_label_extractions",{"id":"root_v1"})
                assert winner["raw_json"]["winner"] in {1,2}
                assert repo.fetch_label_extraction_rows("owner","root")==[winner["raw_json"]]
                assert repo.fetch_label_extraction_rows("other","root")==[]
                assert repo.fetch_label_extraction_rows("owner","wrong")==[]
        finally:
            control.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
    print("single label PostgreSQL concurrency smoke: PASS")


if __name__=="__main__":main()
