"""HTTP maintenance behavior with the real label registrar and isolated PostgreSQL."""
from contextvars import ContextVar
import io
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from local_inspection_service.runtime.connections import ThreadRepositoryFactory
from local_inspection_service.runtime.label_identity import LabelRuntimeIdentity
from local_inspection_service.label_inspection import api, worker_api, pdf_import
from local_inspection_service.label_inspection.runtime_control import LabelRuntimeControl
from local_inspection_service.label_inspection.dependencies import LabelAccess, LabelImports, RepositoryLifecycle
from local_inspection_service.storage.label_inspection import LabelRepository
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.runtime_selector import default_postgres_connector


def main():
    schema = "label_http_" + uuid.uuid4().hex[:12]
    dsn = os.environ["VANTALINE_POSTGRES_DSN"]
    connections = []
    def create():
        connection = default_postgres_connector(dsn)
        connections.append(connection)
        return SimpleNamespace(repository=PostgresRuntimeRepository(connection, "<synthetic>", schema_name=schema))
    factory = ThreadRepositoryFactory(create, lambda: schema)
    repositories = RepositoryLifecycle(lambda: factory.selection().repository, factory.clear)
    setup = default_postgres_connector(dsn)
    try:
        with setup.cursor() as cursor:
            cursor.execute(postgres_ddl(schema))
        setup.commit()
        identity = LabelRuntimeIdentity("a"*40, "v2026.10.1", "embedded")
        repo = LabelRepository(PostgresRuntimeRepository(setup, "<synthetic>", schema_name=schema))
        task = repo.create("alice", "synthetic-task", "synthetic", [{"id": "asset", "enabled": True,
                                                                   "media": {"original": "0"*64}}])
        account = ContextVar("test_account", default="")
        def require(_):
            if not account.get():
                raise HTTPException(401, "login required")
        models = SimpleNamespace(snapshot=lambda: {"label": {"id": "pinned", "version": 1}},
            resolve=lambda *args: {"provider": "doubao", "model": "synthetic", "api_key": "synthetic"})
        with tempfile.TemporaryDirectory(prefix="label-http-") as temporary:
            root = Path(temporary)
            app = FastAPI()
            @app.middleware("http")
            async def context(request, call_next):
                token = account.set(request.headers.get("x-fixture-account", ""))
                try:
                    return await call_next(request)
                finally:
                    account.reset(token)
            def build_control(build, lifecycle, worker, **options):
                return LabelRuntimeControl(build, lifecycle, worker, directory=root/"control", allowed_uid=os.getuid(), **options)
            configuration = worker_api.ConfigurationSnapshot.capture({"VANTALINE_DATA_STORE": "postgres", "DATABASE_URL": "fixture"}, root)
            with patch.object(worker_api.ConfigurationSnapshot, "capture", return_value=configuration), \
                    patch.object(worker_api, "create_control_factory", return_value=factory), \
                    patch.object(worker_api, "read_identity", return_value=identity), \
                    patch.object(worker_api, "LabelRuntimeControl", side_effect=build_control), \
                    patch.object(pdf_import, "register", return_value=None):
                api.register(app, LabelAccess(require, lambda: require("admin"), lambda: (account.get(), account.get())),
                             repositories, LabelImports(lambda: root, lambda *_: ([], []), lambda *_: ([], []),
                                                       lambda *_: b"", lambda *_: b""),
                             lambda: models, lambda: {"enabled": True})
            output = io.BytesIO()
            Image.new("RGB", (20, 20), "white").save(output, format="PNG")
            with TestClient(app) as client:
                def submit(key="synthetic-run", owner="alice"):
                    return client.post(api.PREFIX+"/tasks/"+task["id"]+"/runs",
                        headers={"x-fixture-account": owner},
                        data={"request_id": key, "revision": "1", "asset_id": "asset"},
                        files={"file": ("synthetic.png", output.getvalue(), "image/png")})
                response = submit()
                assert response.status_code == 503 and response.json() == {"detail": "标签检测维护中，请稍后重试；已提交任务继续处理"}
                assert submit(owner="").status_code == 401
                assert submit(owner="bob").status_code == 404
                assert repo.list("alice", "run", task["id"]) == []
                control = app.state.label_worker.runtime_control
                control.command({"schema": 1, "command": "open_admission", "revision": "b"*32})
                response = submit()
                assert response.status_code == 200, response.status_code
                assert response.json()["status"] == "queued"
                run = response.json()
                control.command({"schema": 1, "command": "close_admission", "revision": "c"*32})
                assert submit().json() == run  # Acknowledged request is not duplicated.
                assert submit(key="synthetic-new").status_code == 503
                stored = repo.list("alice", "run", task["id"])
                assert len(stored) == 1 and stored[0]["profile_snapshot"] == {"id": "pinned", "version": 1}
                assert client.get(api.PREFIX+"/runs/"+run["id"], headers={"x-fixture-account": "alice"}).status_code == 200
                assert app.state.label_worker.runtime_status()["state"] == "drained"
            assert not (root/"control/web-control.sock").exists()
        print("label runtime HTTP: 503 maintenance, idempotent replay, 401/404 ownership, pinned snapshot and history passed")
    finally:
        # Direct registrar fixtures have no host middleware; explicitly close their test connections.
        factory.clear()
        for connection in connections:
            connection.close()
        setup.rollback()
        with setup.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        setup.commit()
        setup.close()


if __name__ == "__main__":
    main()
