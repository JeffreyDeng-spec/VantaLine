"""Accepted-source label legacy list projection and indexing contract."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.smoke_label_run_batch import FakeRepository, baseline_register, list_client
from local_inspection_service.label_inspection import api
from local_inspection_service.text_inspection import history


def fixture():
    repo = FakeRepository(0)
    repo.tasks = [{
        "id": "li_extension", "kind": "task", "revision": 1,
        "legacy_id": "s1", "name": "扩展订单", "assets": [],
        "source": {"type": "legacy"}, "created_at": 4, "updated_at": 4,
        "status": "ready",
    }]
    repo.legacy_rows["standards"] = [
        {"id": "s1", "standard_type": "label", "name": "原单 1",
         "created_at": 1, "updated_at": 1},
        {"id": "s2", "standard_type": "label", "name": "原单 2",
         "created_at": 1, "updated_at": 2},
        {"id": "batch-unused", "standard_type": "label", "name": "批量未引用",
         "import_source": "label-batch-v3", "created_at": 1},
    ]
    repo.legacy_rows["records"] = [
        {"id": "r1", "standard_id": "s1", "standard_type": "label",
         "created_at": 10, "status": "completed", "decision": "MATCH"},
        {"id": "r1", "standard_id": "s1", "standard_type": "label",
         "created_at": 10, "status": "completed", "decision": "DIFFERENCES"},
        {"id": "r2", "standard_id": "s2", "standard_type": "label",
         "created_at": 9, "status": "failed", "decision": "REVIEW_REQUIRED"},
        {"id": "orphan", "standard_id": "", "standard_type": "label",
         "created_at": 8, "status": "completed", "decision": "MATCH"},
    ]
    repo.legacy_rows["assets"] = [
        {"id": "asset1", "standard_id": "s2", "ordinal": 2},
        {"id": "asset0", "standard_id": "s2", "ordinal": 1},
    ]
    return repo


class LegacyIndexContract(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("VANTALINE_LABEL_LIST_BASELINE_SOURCE"),
                         "accepted source path not provided")
    def test_accepted_full_projection(self):
        with tempfile.TemporaryDirectory() as temp:
            old = list_client(baseline_register(), fixture(), Path(temp))
            new = list_client(api.register, fixture(), Path(temp))
        self.assertEqual(new, old)
        by_id = {item["id"]: item for item in new}
        self.assertEqual(by_id["li_extension"]["run_count"], 2)
        self.assertEqual(by_id["li_extension"]["decision"], "MATCH")
        self.assertEqual(by_id["legacy:s2"]["standard_count"], 2)
        self.assertIn("legacy:orphan-orphan", by_id)
        self.assertNotIn("legacy:s1", by_id)
        self.assertNotIn("legacy:batch-unused", by_id)

    def test_native_decode_error_precedes_later_legacy_bad_field(self):
        with tempfile.TemporaryDirectory() as temp:
            for register in filter(None, (baseline_register(), api.register)):
                repo = fixture()
                repo.runs["li_extension"] = ["{bad native json"]
                repo.legacy_rows["records"].append(
                    {"standard_id": "s2", "created_at": 11, "status": "completed"}
                )
                status, body = list_client(register, repo, Path(temp), 422)
                self.assertEqual(status, 422)
                self.assertIn("Expecting property name", body["detail"])

    def test_attempting_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            for now, expected in ((1000.0, "processing"), (1000.001, "timeout")):
                for register in filter(None, (baseline_register(), api.register)):
                    repo = fixture()
                    repo.legacy_rows["records"] = [{
                        "id": "attempt", "standard_id": "s2", "standard_type": "label",
                        "created_at": 880, "status": "attempting",
                    }]
                    with patch.object(history.time, "time", return_value=now):
                        items = list_client(register, repo, Path(temp))
                    row = next(item for item in items if item["id"] == "legacy:s2")
                    self.assertEqual(row["status"], expected)



    def test_missing_orphan_id_precedes_native_json_error(self):
        with tempfile.TemporaryDirectory() as temp:
            for register in filter(None, (baseline_register(), api.register)):
                repo = fixture()
                repo.runs["li_extension"] = ["{bad native json"]
                repo.legacy_rows["records"].append(
                    {"standard_id": "", "created_at": 11, "status": "completed"}
                )
                status, body = list_client(register, repo, Path(temp), 404)
                self.assertEqual((status, body),
                                 (404, {"detail": "任务或记录不存在"}))

    def test_two_extensions_recompute_attempting_state(self):
        with tempfile.TemporaryDirectory() as temp:
            for use_baseline in ((True, False) if os.environ.get("VANTALINE_LABEL_LIST_BASELINE_SOURCE") else (False,)):
                repo = fixture()
                first = repo.tasks[0]
                repo.tasks = [first, {**first, "id": "li_second", "name": "扩展订单 2"}]
                repo.legacy_rows["records"] = [{
                    "id": "attempt", "standard_id": "s1", "standard_type": "label",
                    "created_at": 880, "status": "attempting",
                }]
                times = iter((1000.0, 1000.001))
                def timed_state(row):
                    return history.state(row, now=next(times))
                with patch.object(api, "state", side_effect=timed_state) as state_call:
                    register = baseline_register() if use_baseline else api.register
                    items = list_client(register, repo, Path(temp))
                self.assertEqual(state_call.call_count, 2)
                by_id = {item["id"]: item for item in items}
                self.assertEqual(by_id["li_extension"]["status"], "processing")
                self.assertEqual(by_id["li_second"]["status"], "timeout")

if __name__ == "__main__":
    unittest.main()