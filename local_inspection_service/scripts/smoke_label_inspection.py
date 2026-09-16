"""Isolated PostgreSQL + real routes + deterministic provider contract regressions."""

import io
import json
import os
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import psycopg
from psycopg import sql
from PIL import Image
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from local_inspection_service.label_inspection import model
from local_inspection_service.label_inspection.api import register, PREFIX
from local_inspection_service.label_inspection.worker import process
from local_inspection_service.storage.label_inspection import LabelRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.postgres_runtime_repository import (
    PostgresRuntimeRepository,
)
from local_inspection_service.codex_compare.media import MediaStore
from local_inspection_service.text_inspection_v2 import extract_docx_candidates


from smoke_label_quality import picture


def docx(broken=False, count=2):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr(
            "word/_rels/document.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="media/test.png"/></Relationships>',
        )
        z.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>'
            + ('<w:p><w:r><a:blip r:embed="r1"/></w:r></w:p>' * count)
            + "</w:body></w:document>",
        )
        z.writestr("word/media/test.png", b"broken" if broken else picture())
    return b.getvalue()


def main():
    from smoke_label_coordinates import main as coordinate_checks

    coordinate_checks()
    from smoke_label_quality import main as quality_checks

    quality_checks()
    dsn = os.environ["VANTALINE_POSTGRES_DSN"]
    schema = "label_evolving_" + uuid.uuid4().hex
    root = Path(tempfile.mkdtemp(prefix="label-evolving-test-"))
    owner = ContextVar("owner", default="alice")
    connections = []
    admin = ContextVar("admin", default=False)

    def raw():
        conn = psycopg.connect(dsn)
        connections.append(conn)
        return PostgresRuntimeRepository(conn, "test", schema)

    def permission(_):
        if owner.get() == "anonymous":
            raise HTTPException(401, "请登录")
        if owner.get() == "denied":
            raise HTTPException(403, "没有权限")

    def require_admin():
        permission("inspection")
        if not admin.get():
            raise HTTPException(403, "Admin role required")

    app = FastAPI()

    @app.middleware("http")
    async def identity(request, call_next):
        admin_token = admin.set(request.headers.get("x-test-admin") == "true")
        token = owner.set(request.headers.get("x-test-owner", "alice"))
        try:
            return await call_next(request)
        finally:
            owner.reset(token)
            admin.reset(admin_token)

    ns = {
        "app": app,
        "DATA_DIR": root,
        "require_permission": permission,
        "require_admin_role": require_admin,
        "_text_v2_owner": lambda: (owner.get(), "test"),
        "runtime_postgres_repository_or_none": raw,
        "clear_thread_runtime_repository_selection": lambda: None,
        "extract_docx_candidates": extract_docx_candidates,
    }
    register(ns)
    # TestClient without lifespan: tests invoke worker explicitly; never call a live provider.
    client = TestClient(app)
    config = root / "key"
    config.write_text("test-only-placeholder")
    os.environ["VANTALINE_LABEL_INSPECTION_ENABLED"] = "true"
    os.environ["VANTALINE_LABEL_INSPECTION_KEY_FILE"] = str(config)

    def check(response, status=200):
        assert response.status_code == status, (
            response.status_code,
            response.text[:400],
        )
        return response.json()

    document = docx()

    def create(request="document-0001"):
        return check(
            client.post(
                PREFIX + "/tasks",
                data={"request_id": request},
                files={"file": ("test.docx", document)},
            )
        )

    with psycopg.connect(dsn, autocommit=True) as control:
        control.execute(postgres_ddl(schema))
        try:
            task = create()
            sid = task["id"]
            aid = task["assets"][0]["id"]
            assert len(task["assets"]) == 2 and task["assets"][1]["duplicate_of"]
            assert create()["id"] == sid
            assert create("document-0002")["id"] != sid
            base = PREFIX + "/tasks/" + sid
            for suffix in ("", "/media/" + task["assets"][0]["media"]["image"]):
                check(client.get(base + suffix, headers={"x-test-owner": "bob"}), 404)
                check(
                    client.get(base + suffix, headers={"x-test-owner": "anonymous"}),
                    401,
                )
                check(
                    client.get(base + suffix, headers={"x-test-owner": "denied"}), 403
                )
            for name, data in [
                ("bad.docx", b"bad"),
                ("empty.docx", docx(count=0)),
                ("large.docx", docx(count=501)),
            ]:
                check(
                    client.post(
                        PREFIX + "/tasks",
                        data={"request_id": key()},
                        files={"file": (name, data)},
                    ),
                    422,
                )
            broken = check(
                client.post(
                    PREFIX + "/tasks",
                    data={"request_id": key()},
                    files={"file": ("bad-image.docx", docx(True))},
                )
            )
            assert broken["assets"][0]["error"] and not broken["assets"][0]["enabled"]

            def submit(req="detection-0001", revision=1, actual=None):
                return client.post(
                    base + "/runs",
                    data={"request_id": req, "revision": revision, "asset_id": aid},
                    files={"file": ("actual.png", actual or picture())},
                )

            run = check(submit())
            assert check(submit())["id"] == run["id"]
            check(submit("detection-0002"), 409)
            changed = check(
                client.patch(
                    base,
                    json={
                        "request_id": "edit-000001",
                        "revision": 1,
                        "operation": "hide",
                        "value": aid,
                    },
                )
            )
            assert changed["revision"] == 2
            assert check(client.get(PREFIX + "/runs/" + run["id"]))["reference"][
                "enabled"
            ]
            repo = LabelRepository(raw())
            media = MediaStore(root / "label_inspection" / "media")
            claimed = repo.claim()
            calls = []

            def provider(body, key_value):
                assert key_value == "test-only-placeholder"
                calls.append(body)
                assert (
                    body["model"] == model.MODEL
                    and body["thinking"] == {"type": "disabled"}
                    and body["temperature"] == 0.1
                )
                answer = (
                    {"isMultiLabel": False, "labelCount": 1, "cropRect": None}
                    if len(calls) == 1
                    else {"hasDiff": False, "similarity": 100, "issues": []}
                )
                assert body["max_tokens"] == (512 if len(calls) == 1 else 8192)
                return 200, json.dumps(
                    {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {"content": json.dumps(answer)},
                            }
                        ],
                        "usage": {"total_tokens": 123},
                    }
                )

            process(repo, media, claimed, "test-only-placeholder", provider)
            final = check(client.get(PREFIX + "/runs/" + run["id"]))
            assert final["decision"] == "MATCH" and len(calls) == 2
            assert final["quality"] == {"checked": True}
            assert (
                not {"model", "prompt_hash", "layout", "transformations"} & final.keys()
            )
            check(client.get(PREFIX + "/runs/" + run["id"] + "/diagnostics"), 403)
            check(
                client.get(
                    PREFIX + "/runs/" + run["id"] + "/diagnostics",
                    headers={"x-test-owner": "anonymous"},
                ),
                401,
            )
            diagnostics = check(
                client.get(
                    PREFIX + "/runs/" + run["id"] + "/diagnostics",
                    headers={"x-test-admin": "true"},
                )
            )
            assert (
                len(diagnostics["calls"]) == 2
                and "base64" not in json.dumps(diagnostics)
                and "test-only-placeholder" not in json.dumps(diagnostics)
            )
            assert diagnostics["quality"]["preflight"]["passed"]
            assert diagnostics["quality"]["selected"]["passed"]
            assert diagnostics["run"]["model"] == model.MODEL
            for suffix in ("", "/diagnostics"):
                check(
                    client.get(
                        PREFIX + "/runs/" + run["id"] + suffix,
                        headers={"x-test-owner": "bob", "x-test-admin": "true"},
                    ),
                    404,
                )
            check(
                client.patch(
                    base,
                    json={
                        "request_id": "edit-restore",
                        "revision": 2,
                        "operation": "restore",
                        "value": aid,
                    },
                )
            )
            # Quality rejection persists without paid calls; retry is a new linked attempt.
            blocked = check(submit("quality-rejected", 3, picture(7)))
            assert blocked["quality"] == {"checked": True}
            claim = repo.claim()
            seen = []
            process(
                repo, media, claim, "test-only-placeholder", lambda *a: seen.append(1)
            )
            rejected = check(client.get(PREFIX + "/runs/" + blocked["id"]))
            assert not seen and rejected["error_code"] == "QUALITY_BLURRED"
            assert (
                rejected["status"] == "failed"
                and rejected["decision"] == "REVIEW_REQUIRED"
            )
            assert not rejected.get("result")
            assert (
                check(submit("quality-rejected", 3, picture(7)))["id"] == blocked["id"]
            )
            diagnostic = check(
                client.get(
                    PREFIX + "/runs/" + blocked["id"] + "/diagnostics",
                    headers={"x-test-admin": "true"},
                )
            )
            assert (
                diagnostic["calls"] == []
                and not diagnostic["quality"]["preflight"]["passed"]
            )
            check(
                client.get(
                    PREFIX + "/runs/" + blocked["id"], headers={"x-test-owner": "bob"}
                ),
                404,
            )
            retry = check(
                client.post(
                    base + "/runs",
                    data={
                        "request_id": "quality-retry",
                        "revision": 3,
                        "asset_id": aid,
                        "parent_id": blocked["id"],
                    },
                    files={"file": ("actual.png", picture())},
                )
            )
            assert retry["parent_id"] == blocked["id"] and retry["id"] != blocked["id"]
            claim = repo.claim()
            calls.clear()
            process(repo, media, claim, "test-only-placeholder", provider)
            assert (
                repo.get("alice", retry["id"])["status"] == "completed"
                and len(calls) == 2
            )
            # Paid stage errors never pass or auto retry. Missing target boxes stay missing.
            for index, response in enumerate(
                [
                    (429, "{}"),
                    (200, "bad"),
                    (200, json.dumps({"choices": [{"finish_reason": "length"}]})),
                    (
                        200,
                        json.dumps(
                            {
                                "choices": [
                                    {
                                        "finish_reason": "stop",
                                        "message": {
                                            "content": '{"isMultiLabel":false,"labelCount":0}'
                                        },
                                    }
                                ]
                            }
                        ),
                    ),
                ]
            ):
                check(submit("failure-" + str(index), 3))
                claim = repo.claim()
                seen = []
                process(
                    repo,
                    media,
                    claim,
                    "test-only-placeholder",
                    lambda *a: (seen.append(1) or response),
                )
                assert (
                    repo.get("alice", claim["id"])["decision"] == "REVIEW_REQUIRED"
                    and len(seen) == 1
                )
            valid = {
                "hasDiff": True,
                "similarity": 80,
                "issues": [
                    {
                        "description": "missing",
                        "onCamera": False,
                        "bboxCamera": {"x": 0, "y": 0, "w": 1, "h": 1},
                    }
                ],
            }
            assert (
                model.result(valid, [30, 20, 150, 100], (300, 200))["issues"][0][
                    "actual_box"
                ]
                is None
            )
            for bad in (
                {"hasDiff": False, "similarity": 90, "issues": [{}]},
                {"hasDiff": True, "similarity": 100, "issues": []},
            ):
                try:
                    model.result(bad, None, (300, 200))
                    raise AssertionError("contradiction accepted")
                except ValueError:
                    pass
            assert model.crop_rect(
                {
                    "isMultiLabel": True,
                    "labelCount": 2,
                    "cropRect": {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5},
                },
                (300, 200),
            ) == [30, 20, 150, 100]
            original = Image.new("RGB", (120, 80))
            exif = original.getexif()
            exif[274] = 6
            b = io.BytesIO()
            original.save(b, "JPEG", exif=exif)
            normalized, transform = model.decode(b.getvalue())
            assert normalized.size == (80, 120) and transform["orientation"] == 6
            # Atomic global concurrency across independent DB connections.
            for i in range(3):
                t = create("parallel-" + str(i))
                check(
                    client.post(
                        PREFIX + "/tasks/" + t["id"] + "/runs",
                        data={
                            "request_id": "parallel-run-" + str(i),
                            "revision": 1,
                            "asset_id": t["assets"][0]["id"],
                        },
                        files={"file": ("a.png", picture())},
                    )
                )
            barrier = threading.Barrier(3)

            def claim(_):
                r = LabelRepository(raw())
                barrier.wait()
                return r.claim()

            with ThreadPoolExecutor(3) as pool:
                claimed = list(pool.map(claim, range(3)))
            assert sum(x is not None for x in claimed) == 2
            # Simulated restart / deadline: no stage is replayed; next queued run may start.
            for r in filter(None, claimed):
                with repo.tx() as c:
                    r["deadline"] = time.time() - 1
                    repo.put(c, r)
            next_run = repo.claim()
            assert next_run
            assert all(
                repo.get("alice", r["id"])["status"] == "interrupted"
                for r in filter(None, claimed)
            )
            rows = []
            cursor = ""
            while True:
                page = check(
                    client.get(PREFIX + "/tasks", params={"limit": 2, "cursor": cursor})
                )
                rows += page["items"]
                cursor = page["next_cursor"]
                if not cursor:
                    break
            assert len(rows) == len({r["id"] for r in rows}) == 6
            assert (
                check(client.get(PREFIX + "/tasks", headers={"x-test-owner": "bob"}))[
                    "items"
                ]
                == []
            )
            first = check(client.get(PREFIX + "/tasks", params={"limit": 2}))
            target = next(
                r for r in rows if r["id"] not in {x["id"] for x in first["items"]}
            )
            old_task = check(client.get(PREFIX + "/tasks/" + target["id"]))
            check(
                client.patch(
                    PREFIX + "/tasks/" + target["id"],
                    json={
                        "request_id": key(),
                        "revision": old_task["revision"],
                        "operation": "name",
                        "value": "moved during pagination",
                    },
                )
            )
            stable = first["items"]
            token = first["next_cursor"]
            while token:
                page = check(
                    client.get(PREFIX + "/tasks", params={"limit": 2, "cursor": token})
                )
                stable += page["items"]
                token = page["next_cursor"]
            assert len(stable) == len({x["id"] for x in stable}) == 6
            check(
                client.get(
                    PREFIX + "/tasks",
                    params={"cursor": first["next_cursor"]},
                    headers={"x-test-owner": "bob"},
                ),
                404,
            )
            from local_inspection_service.storage.schema import TABLE_BY_NAME

            def seed(table, value):
                columns = TABLE_BY_NAME[table].columns
                values = []
                for col in columns:
                    values.append(
                        json.dumps(value)
                        if col == "raw_json"
                        else value.get(
                            col,
                            (
                                0
                                if col in {"created_at", "updated_at", "ordinal"}
                                else (
                                    value["id"]
                                    if col
                                    in {
                                        "comparison_id",
                                        "idempotency_key",
                                        "material_code",
                                    }
                                    else ""
                                )
                            ),
                        )
                    )
                with repo.tx() as c:
                    c.execute(
                        f"INSERT INTO {repo.repository._qualified_table(table)} ({','.join(columns)}) VALUES ({','.join(['%s']*len(columns))})",
                        tuple(values),
                    )

            for sid_old in ("old-one", "old-two"):
                seed(
                    "text_inspection_standards",
                    {
                        "id": sid_old,
                        "owner_user_id": "alice",
                        "standard_type": "label",
                        "name": "same name",
                        "created_at": 5,
                    },
                )
                seed(
                    "text_inspection_assets",
                    {
                        "id": "asset-" + sid_old,
                        "owner_user_id": "alice",
                        "standard_id": sid_old,
                        "ordinal": 1,
                    },
                )
            for index, sid_old in enumerate(("old-one", "old-one", "missing-order")):
                seed(
                    "text_inspection_records",
                    {
                        "id": "record-" + str(index),
                        "owner_user_id": "alice",
                        "standard_id": sid_old,
                        "status": "completed",
                        "decision": "MATCH",
                        "created_at": 6 + index,
                    },
                )
            seed(
                "codex_comparison_tasks",
                {
                    "id": "beta-batch",
                    "owner_user_id": "alice",
                    "report_version": "label-batch-v3",
                    "inputs": {"standard_name": "Beta batch"},
                    "labels": {"one": {}, "two": {}},
                    "status": "completed",
                    "created_at": 10,
                },
            )
            ns["_text_v2_asset_bytes"] = lambda old, uid: (
                picture() if uid == "alice" else (_ for _ in ()).throw(KeyError())
            )
            listing = check(client.get(PREFIX + "/tasks", params={"limit": 100}))[
                "items"
            ]
            assert len([x for x in listing if x["name"] == "same name"]) == 2
            assert (
                next(x for x in listing if x["id"] == "legacy:old-one")["run_count"]
                == 2
            )
            assert next(x for x in listing if x["id"] == "beta:beta-batch")[
                "url"
            ].endswith("?batch=beta-batch")
            check(client.post(PREFIX + "/tasks/legacy:missing-order/continue"), 422)
            check(
                client.get(
                    PREFIX + "/tasks/legacy:old-one", headers={"x-test-owner": "bob"}
                ),
                404,
            )
            continued = check(client.post(PREFIX + "/tasks/legacy:old-one/continue"))
            assert continued["revision"] == 1 and len(continued["runs"]) == 2
            assert (
                check(client.post(PREFIX + "/tasks/legacy:old-one/continue"))["id"]
                == continued["id"]
            )
            listing = check(client.get(PREFIX + "/tasks", params={"source": "legacy"}))[
                "items"
            ]
            assert (
                len(listing) == 3
                and len([x for x in listing if x["name"] == "same name"]) == 2
            )
            assert all(
                r["decision"] == "MATCH"
                for r in LabelRepository(raw()).legacy("alice", "records")
            )
            assert (
                check(client.get(PREFIX + "/requests/detection-0001"))["run"]["id"]
                == run["id"]
            )
            assert (
                check(
                    client.get(
                        PREFIX + "/requests/detection-0001",
                        headers={"x-test-owner": "bob"},
                    )
                )["run"]
                is None
            )
            print(
                "PASS: PostgreSQL/routes/import/duplicates/versioning/idempotency/owner isolation/two calls/failures/restart/global concurrency/pagination"
            )
        finally:
            for conn in connections:
                conn.close()
            control.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


def key():
    return uuid.uuid4().hex


if __name__ == "__main__":
    main()
