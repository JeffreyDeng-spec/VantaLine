"""Isolated real-PostgreSQL races for append-only revisions and terminal outcomes."""
import os
import sys
import uuid
import threading
import tempfile
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import psycopg
from psycopg import sql
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository


def main():
    schema="sheet_test_"+uuid.uuid4().hex
    dsn=os.environ["VANTALINE_POSTGRES_DSN"]
    with psycopg.connect(dsn,autocommit=True) as control:
        control.execute(postgres_ddl(schema))
        try:
            for identifier in ("root_v1","root_terminal","root_vlm_claim"):
                barrier=threading.Barrier(2)
                def writer(index):
                    with psycopg.connect(dsn) as conn:
                        repo=PostgresRuntimeRepository(conn,"test",schema)
                        row={"id":identifier,"owner_user_id":"owner","root_id":"root","created_at":1.5,
                             "raw_json":{"id":identifier,"root_id":"root","owner_user_id":"owner","winner":index}}
                        barrier.wait()
                        return repo.insert_row_once("text_sheet_elements",row)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    assert sum(pool.map(writer,[1,2]))==1
            with psycopg.connect(dsn) as conn:
                repo=PostgresRuntimeRepository(conn,"test",schema)
                values=repo.fetch_sheet_element_rows("owner","root")
                assert len(values)==3 and all(isinstance(v,dict) for v in values)
                assert repo.fetch_sheet_element_rows("other","root")==[]
                assert repo.fetch_sheet_element_rows("owner","different")==[]
        finally:
            control.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
    print("sheet PostgreSQL ownership and immutable races: PASS")


if __name__=="__main__":
    if os.environ.get("VANTALINE_POSTGRES_DSN"):
        main()
    else:
        binary=Path(os.environ["VANTALINE_POSTGRES_BIN_DIR"])
        with tempfile.TemporaryDirectory(prefix="sheet-pg-",dir="/tmp") as directory:
            cluster=str(Path(directory)/"data")
            subprocess.run([str(binary/"initdb"),"-D",cluster,"-A","trust","-U","postgres"],check=True,stdout=subprocess.DEVNULL)
            subprocess.run([str(binary/"pg_ctl"),"-D",cluster,"-l",str(Path(directory)/"postgres.log"),"-o",f"-h '' -k {directory} -p 55439","-w","start"],check=True,stdout=subprocess.DEVNULL)
            try:
                os.environ["VANTALINE_POSTGRES_DSN"]=f"host={directory} port=55439 user=postgres dbname=postgres"
                main()
            finally:
                subprocess.run([str(binary/"pg_ctl"),"-D",cluster,"-m","fast","-w","stop"],check=True,stdout=subprocess.DEVNULL)
