"""Accepted-main/candidate label-list projection and bounded query-count contract."""
import ast
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from local_inspection_service.label_inspection import api


class FakeRepository:
    def __init__(self, count):
        self.owner = "alice"
        self.tasks = [
            {
                "id": f"li_task_{i:05}", "kind": "task", "revision": 1,
                "name": f"订单 {i:05}", "source": {"type": "word"},
                "assets": [], "created_at": i, "updated_at": i, "status": "ready",
            }
            for i in range(count)
        ]
        self.runs = {
            task["id"]: [
                {"id": f"li_run_{i:05}", "kind": "run", "task_id": task["id"],
                 "created_at": i + 0.5, "status": "succeeded",
                 "decision": "MATCH" if i % 2 else "DIFFERENCES"},
            ]
            for i, task in enumerate(self.tasks)
        }
        self.legacy_rows = {
            "standards": [{"id": "old", "standard_type": "label", "name": "旧订单",
                           "created_at": -10, "updated_at": -9},
                          {"id": "manual", "standard_type": "manual", "name": "旧说明书",
                           "created_at": -10, "updated_at": -8}],
            "records": [], "assets": [], "sessions": [], "pages": [],
            "beta": [{"id": "beta", "inputs": {"standard_name": "Beta"},
                      "created_at": -7, "status": "succeeded",
                      "summary": {"decision": "REVIEW_REQUIRED"}}],
        }
        self.calls = []
        self.snapshots = {}
        self.sequence = 0

    def list(self, owner, kind, task=None):
        self.calls.append(("list", owner, kind, task))
        if owner != self.owner:
            return []
        if kind == "task":
            return copy.deepcopy(self.tasks)
        if kind == "run":
            values = self.runs.get(task, []) if task else [
                row for group in self.runs.values() for row in group
            ]
            return [json.loads(row) if isinstance(row, str) else copy.deepcopy(row)
                    for row in values]
        raise AssertionError(kind)

    def runs_for_tasks(self, owner, task_ids):
        self.calls.append(("batch", owner, tuple(task_ids)))
        assert 0 < len(task_ids) <= 64
        if owner != self.owner:
            return {key: [] for key in task_ids}
        return {key: copy.deepcopy(self.runs.get(key, [])) for key in task_ids}

    def legacy(self, owner, kind):
        self.calls.append(("legacy", owner, kind))
        return copy.deepcopy(self.legacy_rows[kind]) if owner == self.owner else []

    def page(self, owner, rows, filters, limit, cursor=""):
        self.calls.append(("page", owner, bool(cursor)))
        if cursor:
            identity, offset = cursor.rsplit(".", 1)
            if identity not in self.snapshots or self.snapshots[identity][0] != owner:
                raise KeyError(identity)
            rows = self.snapshots[identity][1]
            offset = int(offset)
        else:
            self.sequence += 1
            identity = f"page_{self.sequence}"
            offset = 0
            self.snapshots[identity] = owner, copy.deepcopy(rows)
        selected = rows[offset:offset + limit]
        next_offset = offset + len(selected)
        return {"items": selected,
                "next_cursor": f"{identity}.{next_offset}" if next_offset < len(rows) else None}


def baseline_register():
    source = os.environ.get("VANTALINE_LABEL_LIST_BASELINE_SOURCE")
    if not source:
        return None
    path = Path(source)
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    node = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "register")
    namespace = dict(vars(api))
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["register"]


def list_client(register, repo, root, expected_status=200):
    app = FastAPI()
    access = SimpleNamespace(require_permission=lambda _: None,
                             owner=lambda: (repo.owner, "test"))
    repositories = SimpleNamespace(repository=lambda: repo)
    imports = SimpleNamespace(data_directory=lambda: root)
    with patch.object(api.pdf_import, "register", lambda *_: None), \
         patch.dict(register.__globals__, {
             "LabelRepository": lambda raw: raw,
             "MediaStore": lambda *_: object(),
         }):
        register(app, access, repositories, imports, lambda: None,
                 lambda: {"enabled": True})
        client = TestClient(app)
        first = client.get(api.PREFIX + "/tasks", params={"limit": 100})
        assert first.status_code == expected_status, first.text[:300]
        if expected_status != 200:
            return first.status_code, first.json()
        result = first.json()
        items = list(result["items"])
        cursor = result["next_cursor"]
        while cursor:
            response = client.get(api.PREFIX + "/tasks",
                                  params={"limit": 100, "cursor": cursor})
            assert response.status_code == 200, response.text[:300]
            page = response.json()
            items += page["items"]
            cursor = page["next_cursor"]
        return items


class ListContract(unittest.TestCase):
    def test_empty_and_batch_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            for count, batches in ((0, 0), (1, 1), (64, 1), (65, 2), (129, 3)):
                with self.subTest(count=count):
                    repo = FakeRepository(count)
                    items = list_client(api.register, repo, Path(temp))
                    self.assertEqual(len(items), count + 3)
                    calls = [c for c in repo.calls if c[0] == "batch"]
                    self.assertEqual(len(calls), batches)
                    self.assertEqual(sum(len(c[2]) for c in calls), count)
                    self.assertFalse(any(c[0] == "list" and c[2] == "run"
                                         for c in repo.calls))
                    self.assertEqual(len({item["id"] for item in items}), len(items))
                    self.assertEqual(items, sorted(items, key=lambda x: (x["updated_at"], x["id"]), reverse=True))
                    if count:
                        self.assertEqual(items[0]["run_count"], 1)
                        self.assertEqual(items[0]["status"], "succeeded")

    def test_large_synthetic_list_query_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            for count, expected_batches in ((1000, 16), (10000, 157)):
                with self.subTest(count=count):
                    repo = FakeRepository(count)
                    items = list_client(api.register, repo, Path(temp))
                    self.assertEqual(len(items), count + 3)
                    self.assertEqual(sum(c[0] == "batch" for c in repo.calls),
                                     expected_batches)
                    self.assertFalse(any(c[0] == "list" and c[2] == "run"
                                         for c in repo.calls))
                    self.assertEqual(len({item["id"] for item in items}), len(items))

    def test_read_only_missing_revision_and_falsey_id(self):
        with tempfile.TemporaryDirectory() as temp:
            for register in filter(None, (baseline_register(), api.register)):
                repo = FakeRepository(0)
                repo.tasks = [
                    {"id": "read_only", "read_only": True, "name": "只读",
                     "assets": [], "updated_at": 3, "status": "ready"},
                    {"id": "", "revision": 1, "name": "空 ID", "assets": [],
                     "updated_at": 2, "status": "ready"},
                ]
                repo.runs = {"other": [
                    {"id": "run", "task_id": "other", "created_at": 1,
                     "decision": "MATCH", "status": "succeeded"},
                ]}
                items = list_client(register, repo, Path(temp))
                by_id = {item["id"]: item for item in items}
                self.assertEqual(by_id["read_only"]["run_count"], 0)
                self.assertEqual(by_id[""]["run_count"], 1)
                self.assertEqual(by_id[""]["decision"], "MATCH")
                self.assertFalse(any(c[0] == "batch" for c in repo.calls))

    def test_first_task_error_precedes_later_missing_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            for missing in ("revision", "id"):
                for register in filter(None, (baseline_register(), api.register)):
                    repo = FakeRepository(2)
                    first, second = repo.tasks
                    repo.runs[first["id"]] = ["{malformed first json"]
                    second.pop(missing)
                    status, body = list_client(register, repo, Path(temp), 422)
                    self.assertEqual(status, 422)
                    self.assertIn("Expecting property name", body["detail"])

    def test_first_task_error_precedes_later_malformed_json(self):
        with tempfile.TemporaryDirectory() as temp:
            for register in filter(None, (baseline_register(), api.register)):
                repo = FakeRepository(2)
                first, second = repo.tasks
                repo.runs[first["id"]] = [{"id": "missing_created_at", "status": "failed"}]
                repo.runs[second["id"]] = ["{malformed json"]
                status, body = list_client(register, repo, Path(temp), 404)
                self.assertEqual(status, 404)
                self.assertEqual(body, {"detail": "任务或记录不存在"})

    @unittest.skipUnless(os.environ.get("VANTALINE_LABEL_LIST_BASELINE_SOURCE"),
                         "accepted source path not provided")
    def test_accepted_main_exact_projection(self):
        with tempfile.TemporaryDirectory() as temp:
            for count in (0, 1, 64, 65, 129):
                with self.subTest(count=count):
                    old_repo, new_repo = FakeRepository(count), FakeRepository(count)
                    old = list_client(baseline_register(), old_repo, Path(temp))
                    new = list_client(api.register, new_repo, Path(temp))
                    self.assertEqual(new, old)
                    self.assertEqual(sum(c[0] == "list" and c[2] == "run"
                                         for c in old_repo.calls), count)
                    self.assertFalse(any(c[0] == "batch" for c in old_repo.calls))


if __name__ == "__main__":
    unittest.main()