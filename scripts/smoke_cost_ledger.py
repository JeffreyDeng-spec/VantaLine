"""Synthetic cost domain regression: real aggregation/storage adapters, no provider."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from local_inspection_service.analytics.cost_api import register_cost_api
from local_inspection_service.analytics.cost_pricing import (
    api_cost_from_usage, runpod_gpu_usd_per_second,
)
from local_inspection_service.analytics.cost_repository import CostPaths, CostRepository, CostStoreDependencies
from local_inspection_service.analytics.costs import CostLedger


NOW = 1700000000


def usage(model="gemini-2.5-flash", created_at=NOW):
    return {"model": model, "created_at": created_at,
            "usage_metadata": {"prompt_tokens": 1000000, "completion_tokens": 200000}}


class CostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vantaline-cost-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = CostPaths(self.root, self.root / "data_analysis_records.json",
                               self.root / "ai_detection_tasks.json", self.root / "pipeline_tasks.json",
                               self.root / "auto_optimize", self.root / "ai_profile_cache.json")
        self.pg = None
        self.events = []
        self.training = []
        self.states = []
        self.repository = CostRepository(CostStoreDependencies(
            paths=lambda: self.paths, runtime_repository=lambda: self.pg,
            detection_tasks=lambda: [], pipeline_tasks=lambda: [],
            auto_states=lambda: self.states, training_tasks=lambda: self.training,
            sanitize_task_id=lambda value: value.replace("/", ""),
        ))
        self.ledger = CostLedger(self.repository, timestamp=lambda value: int(float(value or 0)))

    def test_pricing_aliases_cache_image_and_unknown(self):
        cost, tokens, priced = api_cost_from_usage("gemini-3.1-flash-image", {
            "input_tokens": 1000000, "cached_tokens": 100000,
            "output_tokens": 20000, "reasoning_tokens": 5000,
            "outputTokensDetails": [{"modality": "IMAGE", "token_count": 1000}],
        })
        self.assertAlmostEqual(cost, .587)
        self.assertEqual(tokens, {"input": 900000, "cached_input": 100000,
                                  "output_text": 24000, "output_image": 1000, "total": 1025000})
        self.assertTrue(priced)
        self.assertEqual(api_cost_from_usage("unknown", {"promptTokenCount": -5})[::2], (0, False))
        cost, tokens, _ = api_cost_from_usage("gemini-2.5-flash-lite", {
            "promptTokenCount": "bad", "input_tokens": 900000, "completion_tokens": "1e5"})
        self.assertAlmostEqual(cost, .13)
        self.assertEqual(tokens["output_text"], 100000)
        for raw, expected in [("bad", .00026), ("0", .00026), (".001", .001)]:
            with patch.dict(os.environ, VANTALINE_RUNPOD_GPU_USD_PER_SECOND=raw):
                self.assertEqual(runpod_gpu_usd_per_second(), expected)

    def test_raw_store_precedence_and_legacy_paths(self):
        self.paths.analysis.write_text(json.dumps({"records": [usage("stale-json")]}), encoding="utf-8")
        payload = {"extra_unrecognized_field": usage()}

        class Repository:
            def fetch_all(inner, table):
                self.events.append(table)
                return [{"raw_json": json.dumps(payload)}]

        self.pg = Repository()
        pairs = self.repository.store_payloads()
        self.assertEqual(self.events, ["data_analysis_records"])
        self.assertEqual(pairs[0], (self.paths.analysis, {"records": [payload]}))
        record = self.ledger.collect_records()[0]
        pointer = "records/0/extra_unrecognized_field"
        self.assertEqual(record["id"], hashlib.sha1(f"{self.paths.analysis}:{pointer}".encode()).hexdigest()[:16])
        self.assertEqual(record["category"], "structured_output")
        self.assertEqual(record["cost_usd"], .8)
        self.pg = None
        self.assertEqual(self.repository.store_payloads()[0][1]["records"][0]["model"], "stale-json")
        self.paths.analysis.write_text("{invalid", encoding="utf-8")
        self.assertEqual(self.repository.store_payloads()[0][1], {"records": []})

    def test_file_patterns_invalid_files_and_sensitive_branches(self):
        cache = {"calls": [usage()], "api_key": usage("skip-secret"), "image_bytes": usage("skip-media")}
        self.paths.profile_cache.write_text(json.dumps(cache), encoding="utf-8")
        media = self.root / "outputs/users/user/agent_mcp_pose_images/x.metadata.json"
        media.parent.mkdir(parents=True)
        media.write_text(json.dumps(usage(created_at=NOW + 2)), encoding="utf-8")
        bad = self.root / "image_worker_logs/broken.json"
        bad.parent.mkdir()
        bad.write_text("{invalid", encoding="utf-8")
        (self.root / "unrelated.json").write_text(json.dumps(usage("skip-unrelated")), encoding="utf-8")
        records = self.ledger.collect_records()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["category"], "image_generation")
        self.assertEqual(records[1]["subcategory"], "AI Profile cache")
        self.assertEqual(records[1]["pointer"], "calls/0")

    def test_deduplication_source_order_and_summary(self):
        events = self.events

        class Sources:
            def store_payloads(inner):
                events.append("store")
                return [(Path("shared"), usage())]
            def metadata_payloads(inner):
                events.append("metadata")
                return [(Path("shared"), usage("must-not-replace")), (Path("unknown"), usage("unknown"))]
            def training_tasks(inner):
                events.append("training")
                return [{"training_executor": "runpod", "job_id": "first", "created_at": NOW + 1,
                         "remote_training_response": {"executionTime": 100000}},
                        {"training_executor": "runpod", "job_id": "failed", "created_at": NOW},
                        {"training_executor": "windows", "job_id": "legacy"}]
            def auto_states(inner):
                return [{"samples": [{"label_status": "trainable"}, {"label_status": "negative"},
                                      {"label_status": "pending"}, "ignored"]}]

        ledger = CostLedger(Sources(), timestamp=lambda value: int(value or 0))
        with patch.dict(os.environ, VANTALINE_RUNPOD_GPU_USD_PER_SECOND=".00026"), patch("time.time", return_value=NOW):
            records = ledger.collect_records()
            summary = ledger.summary(records + [{"estimated": True, "cost_usd": 999}])
        self.assertEqual(events, ["store", "metadata", "training"])
        self.assertEqual(len(records), 4)
        self.assertEqual(records[0]["category"], "training")
        self.assertEqual(records[1]["model"], "gemini-2.5-flash")
        self.assertEqual(summary["summary"]["total_cost_usd"], .826)
        self.assertEqual(summary["summary"]["call_count"], 4)
        self.assertEqual(summary["summary"]["unpriced_call_count"], 2)
        self.assertEqual(summary["summary"]["training_sample_count"], 2)
        self.assertEqual(summary["summary"]["avg_cost_per_training_sample_usd"], .413)
        self.assertEqual(summary["updated_at"], NOW)
        self.assertEqual(len(summary["recent_calls"]), 4)

    def test_admin_guard_precedes_sources_and_separate_apps_do_not_share(self):
        reads = []

        class Ledger:
            def __init__(inner, name):
                inner.name = name
            def collect_records(inner):
                reads.append(inner.name)
                return []
            def summary(inner, records):
                return {"summary": records, "source": inner.name}

        clients = []
        for name, status in (("anonymous", 401), ("member", 403), ("first", 200), ("second", 200)):
            app = FastAPI()
            def guard(status=status):
                if status != 200:
                    raise HTTPException(status_code=status, detail="denied")
            register_cost_api(app, guard, Ledger(name))
            self.assertEqual(len([r for r in app.routes if r.path == "/api/admin/api-cost-ledger"]), 1)
            client = TestClient(app)
            self.addCleanup(client.close)
            clients.append((client, name, status))
        # Register every app first, then interleave requests to expose shared router state.
        for index in (3, 0, 2, 1, 3, 2):
            client, name, status = clients[index]
            response = client.get("/api/admin/api-cost-ledger")
            self.assertEqual(response.status_code, status)
            if status == 200:
                self.assertEqual(response.json()["source"], name)
        self.assertEqual(reads, ["second", "first", "second", "first"])


if __name__ == "__main__":
    unittest.main()
