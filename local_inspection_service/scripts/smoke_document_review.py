#!/usr/bin/env python3
"""Exercise production review handlers with isolated stores / a DB-API double.

No server boot, model calls, customer files, or live PostgreSQL are involved.
This is not a live database or authentication middleware integration test.
"""
from __future__ import annotations

import ast
import asyncio
import copy
import json
import sys
import threading
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository, PostgresRuntimeRepositoryError


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        super().__init__(detail)


def fixtures():
    return ({"id": "std", "owner_user_id": "owner", "standard_type": "label", "status": "draft", "revision_number": 0},
            {"id": "asset", "standard_id": "std", "owner_user_id": "owner", "ordinal": 1, "status": "candidate", "classification_source": "vlm", "category": "label_design"})


def handlers():
    standard, asset = fixtures()
    store = {"standards": [standard], "assets": [asset], "feedback": []}
    def owned(kind, identity, owner):
        return next((copy.deepcopy(x) for x in store[kind] if x["id"] == identity and x["owner_user_id"] == owner), None)
    def save(kind, value, **kwargs):
        store[kind] = [x for x in store[kind] if x["id"] != value["id"]] + [copy.deepcopy(value)]
        return True
    ns = {"__builtins__": __builtins__, "HTTPException": HTTPException, "uuid": uuid, "time": time,
          "require_permission": lambda *a, **kw: None, "_text_v2_owner": lambda: ("owner", "tester"),
          "_text_v2_owned": owned, "_text_v2_load": lambda k: copy.deepcopy(store[k]), "_text_v2_save": save,
          "_text_v2_public": copy.deepcopy, "runtime_postgres_repository_or_none": lambda: None,
          "_incoming_text_store_lock": threading.RLock(), "_text_v2_expected_revision": lambda v: v,
          "_text_v2_confirmed_snapshot": lambda assets: [x for x in assets if x["status"] in {"candidate", "page"}],
          "_text_v2_apply_revision": lambda *a, **kw: None}
    tree = ast.parse((ROOT / "local_inspection_service/server.py").read_text())
    names = {"patch_text_inspection_asset", "confirm_text_inspection_standard"}
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    for n in nodes:
        n.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "review-handlers", "exec"), ns)
    return store, ns


class Request:
    def __init__(self, action, revision=0): self.action, self.revision = action, revision
    async def json(self): return {"action": self.action, "expected_revision": self.revision}


class Connection:
    def __init__(self, standard, asset):
        self.standard, self.asset = copy.deepcopy(standard), copy.deepcopy(asset)
        self.statements, self.revisions, self.rows = [], [], []
        self.commits = self.rollbacks = 0
    def cursor(self): return self
    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        if sql.startswith("SELECT raw_json"):
            if '"text_inspection_standards"' in sql:
                self.rows = [{"raw_json": copy.deepcopy(self.standard)}] if params == (self.standard["id"], self.standard["owner_user_id"]) else []
            else:
                self.rows = [{"raw_json": copy.deepcopy(self.asset)}]
        elif sql.startswith("UPDATE") and '"text_inspection_assets"' in sql:
            self.asset = json.loads(params[2])
        elif sql.startswith("UPDATE") and '"text_inspection_standards"' in sql:
            self.standard = json.loads(params[1])
    def fetchone(self): return self.rows.pop(0) if self.rows else None
    def fetchall(self): return self.rows
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1
    def close(self): pass


class Repository(PostgresRuntimeRepository):
    def _insert_text_standard_revision(self, cursor, value):
        self.connection.revisions.append(copy.deepcopy(value))


class ReviewTests(unittest.TestCase):
    def test_json_all_transitions_and_original_evidence(self):
        store, ns = handlers()
        for action, status in [("review", "needs_confirmation"), ("remove", "excluded"), ("confirm", "candidate")]:
            result = asyncio.run(ns["patch_text_inspection_asset"]("std", "asset", Request(action)))
            self.assertEqual(result["status"], status)
            self.assertEqual(result["classification_source"], "human")
            self.assertEqual(result["original_classification"]["status"], "candidate")
        self.assertEqual([x["action"] for x in store["feedback"]], ["review", "remove", "confirm"])

    def test_json_pending_blocks_confirmation_and_cross_owner_rejected(self):
        store, ns = handlers()
        asyncio.run(ns["patch_text_inspection_asset"]("std", "asset", Request("review")))
        with self.assertRaises(HTTPException) as error: ns["confirm_text_inspection_standard"]("std")
        self.assertEqual(error.exception.status_code, 409)
        ns["_text_v2_owner"] = lambda: ("other", "other")
        with self.assertRaises(HTTPException) as error:
            asyncio.run(ns["patch_text_inspection_asset"]("std", "asset", Request("confirm")))
        self.assertEqual(error.exception.status_code, 404)

    def test_json_stale_and_unknown_action_rejected(self):
        _, ns = handlers()
        for request, status in [(Request("review", 99), 409), (Request("invented"), 400)]:
            with self.assertRaises(HTTPException) as error:
                asyncio.run(ns["patch_text_inspection_asset"]("std", "asset", request))
            self.assertEqual(error.exception.status_code, status)

    def test_postgres_review_removes_current_membership_not_history(self):
        standard, asset = fixtures()
        standard.update(status="confirmed", revision_number=1, confirmed_asset_ids=["asset"])
        connection = Connection(standard, asset)
        repo = Repository(connection=connection, database_url_redacted="test-only")
        result, current = repo.patch_text_inspection_asset("std", "asset", "owner", "review", 1, revision_id="rev2", expected_revision=1)
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertEqual(current["confirmed_asset_ids"], [])
        self.assertEqual(standard["confirmed_asset_ids"], ["asset"])
        self.assertEqual(connection.revisions[0]["action"], "review")
        result, current = repo.patch_text_inspection_asset("std", "asset", "owner", "confirm", 2, revision_id="rev3", expected_revision=2)
        self.assertEqual(current["confirmed_asset_ids"], ["asset"])
        self.assertEqual(result["original_classification"]["classification_source"], "vlm")
        with self.assertRaises(PostgresRuntimeRepositoryError):
            repo.patch_text_inspection_asset("std", "asset", "owner", "remove", 3, revision_id="bad", expected_revision=1)

    def test_postgres_pending_blocks_and_cross_owner_rejected(self):
        standard, asset = fixtures()
        asset["status"] = "needs_confirmation"
        connection = Connection(standard, asset)
        repo = Repository(connection=connection, database_url_redacted="test-only")
        with self.assertRaises(PostgresRuntimeRepositoryError):
            repo.confirm_text_inspection_standard("std", "owner", 1, revision_id="rev1")
        with self.assertRaises(PostgresRuntimeRepositoryError):
            repo.patch_text_inspection_asset("std", "asset", "other", "confirm", 1, revision_id="bad")
        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 2)


if __name__ == "__main__": unittest.main()
