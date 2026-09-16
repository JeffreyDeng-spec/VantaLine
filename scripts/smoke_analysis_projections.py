"""Synthetic analysis views/publication through explicit real domain services."""
import copy
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from local_inspection_service.analytics.analysis_processing import ProcessingDependencies, ProcessingProjection, image_processing_status
from local_inspection_service.analytics.analysis_scope import AnalysisScope, ScopeDependencies
from local_inspection_service.analytics.analysis_projection import AnalysisProjection, ProjectionDependencies
from local_inspection_service.analytics.analysis_publication import AnalysisPublisher, PublicationDependencies
from local_inspection_service.analytics.analysis_repository import AnalysisRepository, AnalysisStoreDependencies
from smoke_analysis_records import normalizer, seed


class AnalysisProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="analysis-projections-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "outputs"
        self.output.mkdir()
        self.identity = {"id": "alice", "username": "alice"}
        self.cache = {}
        self.manifest_reads = []
        self.captures = []
        self.manifest = {"samples": [{"source_sample_id": "sample", "image": "image.png", "label_count": 2}]}
        self.state = {"datasets": [{"id": "dataset", "manifest_path": "manifest.json"}]}
        def load_json(path):
            self.manifest_reads.append(path)
            return copy.deepcopy(self.manifest)
        self.processing = ProcessingProjection(ProcessingDependencies(
            safe_id=lambda value: re.sub(r"[^a-zA-Z0-9_-]", "_", str(value)),
            bounded_text=lambda value, length: str(value or "")[:length],
            sanitize_paths=lambda value: {key: val for key, val in value.items() if key != "private_path"},
            output_url=lambda path: "/outputs/" + path.name, resolve_path=lambda value: self.root / str(value),
            load_json=load_json, current_cache=lambda: self.cache,
            created_at=lambda record: int(record.get("created_at") or 0),
            updated_at=lambda record: int(record.get("updated_at") or 0), auto_state=lambda task_id: self.state,
        ))
        part = {"id": "socket", "name": "Socket", "english_name": "Socket"}
        self.scope = AnalysisScope(ScopeDependencies(
            current_user=lambda: self.identity, load_config=lambda: {}, scope_config=lambda config, user: config,
            accessory_lookup=lambda config: {"old-alias": part, "socket": part},
            detection_tasks=lambda: [{"id": "task-1", "required_accessory_counts": {"socket": 9}}],
            serialize_task=lambda task, config: task, normalize_counts=lambda value: dict(value),
            accessory_id=lambda value: value["id"], accessory_aliases=lambda value: ["socket", "old-alias"],
            english_name=lambda value: str(value or ""), bounded_text=lambda value, length: str(value)[:length],
        ))
        self.views = AnalysisProjection(ProjectionDependencies(
            created_at=lambda record: int(record.get("created_at") or 0),
            updated_at=lambda record: int(record.get("updated_at") or 0),
            owner_id=lambda record: record.get("owner_user_id", "legacy"),
            owner_username=lambda record: record.get("owner_username", "legacy"),
            default_task_label="Task", output_directory=lambda: self.output,
            resolve_path=lambda value: self.root / str(value),
            path_is_under=lambda candidate, root: candidate.resolve().is_relative_to(root.resolve()),
        ), self.processing, self.scope)
        lock = threading.RLock()
        self.repository = AnalysisRepository(AnalysisStoreDependencies(
            path=lambda: self.root / "records.json", runtime_repository=lambda: None,
            lock=lambda: lock, ensure_dirs=lambda: None,
        ), normalizer())
        def capture(record, result, request_id, path):
            assert self.repository.load_data_analysis_record(record["record_id"]) is not None
            self.captures.append((copy.deepcopy(record), request_id))
        self.publisher = AnalysisPublisher(PublicationDependencies(
            current_user=lambda: self.identity,
            owner_fields=lambda: {"owner_user_id": self.identity["id"], "owner_username": self.identity["username"]},
            owner_id=lambda record: record.get("owner_user_id", "legacy"),
            owner_username=lambda record: record.get("owner_username", "legacy"),
            default_task_id="default-task", default_task_label="Task",
            clean_task_name=lambda value, fallback: str(value or fallback),
            string_list=lambda value, **kwargs: list(value or [])[:kwargs["max_items"]],
            resolve_path=lambda value: self.root / str(value), safe_name=lambda value: value.replace("/", "_"),
            output_url=lambda path: "/outputs/" + path.name, capture=capture,
        ), self.repository, self.processing)

    def test_processing_cache_merge_status_and_sanitization(self):
        sample = {"sample_id": "sample"}
        first = self.processing.auto_optimize_dataset_processing_items_for_sample(self.state, sample, record_id="r", task_id="t")
        second = self.processing.auto_optimize_dataset_processing_items_for_sample(self.state, sample, record_id="r", task_id="t")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        self.assertEqual(len(self.manifest_reads), 1)
        self.cache = {}
        self.processing.auto_optimize_dataset_processing_items_for_sample(self.state, sample, record_id="r", task_id="t")
        self.assertEqual(len(self.manifest_reads), 2)
        merged = self.processing.merge_image_processing_items([{"id": "same", "created_at": 1, "status": "queued"}],
                                                               [{"id": "same", "status": "completed"}])
        self.assertEqual(merged, [{"id": "same", "created_at": 1, "status": "completed"}])
        item = self.processing.image_processing_item(item_id="sample/one", item_type="ai_mask", status="trainable",
                                                     metrics={"private_path": "internal", "score": .9})
        self.assertEqual((item["id"], item["status"], item["metrics"]), ("sample_one", "completed", {"score": .9}))
        self.assertEqual([image_processing_status(s) for s in ["labeling", "skipped", "error", ""]],
                         ["running", "rejected", "failed", "pending"])

    def test_scope_priority_and_normal_vs_debug_projection(self):
        record = seed("record")
        record["ai_detection_result"] = {
            "model": {"task_id": "task-1", "required_accessory_counts": {"old-alias": 2}, "selected_accessory_ids": ["old-alias"]},
            "rule": {"counts": {"old-alias": 2}}, "ai": {"provider_status": "fixture", "latency_ms": 7},
            "raw_answer": "private synthetic evidence", "prompt": "private synthetic prompt",
        }
        scope = self.scope.public_data_analysis_scope_payload(record)["required_accessories"]
        self.assertEqual(scope, [{"accessory_id": "socket", "label": "Socket", "required_count": 2, "ai_detection_count": 2}])
        self.assertTrue(self.scope.data_analysis_scoped_ai_summary(record)["passed"])
        normal = self.views.public_data_analysis_record(record, detail=True, include_auto_optimize=False)
        self.assertNotIn("raw_answer", normal["ai_detection_result"])
        self.assertNotIn("prompt", normal["ai_detection_result"])
        debug = self.views.public_data_analysis_record(record, detail=True, include_debug=True, include_auto_optimize=False)
        self.assertEqual(debug["ai_detection_result"], record["ai_detection_result"])
        self.assertGreater(len(debug["image_processing_items"]), 40)
        listing = self.views.public_data_analysis_record(record, include_auto_optimize=False, include_scope=False)
        self.assertEqual(len(listing["image_processing_items"]), 40)
        self.assertEqual(listing["required_accessory_scope"], {})
        record["task"]["type"] = "image_processing"
        self.assertEqual(self.scope.data_analysis_record_required_scope(record), {})

    def test_image_lookup_and_unavailable_path(self):
        image = self.output / "synthetic.png"
        image.write_bytes(b"fixture")
        self.assertEqual(self.views.data_analysis_record_image_path({"source_image": {"url": "/outputs/synthetic.png?cache=1"}}), image.resolve())
        (self.root / "outside.png").write_bytes(b"fixture")
        with self.assertRaises(HTTPException) as error:
            self.views.data_analysis_record_image_path({"source_image": {"url": "/outputs/../outside.png"}})
        self.assertEqual(error.exception.status_code, 404)

    def test_publication_order_failure_and_anonymous_guard(self):
        result = {"passed": True, "rule": {"counts": {"socket": 2}}, "model": {"task_id": "task-1"}}
        record = self.publisher.persist_data_analysis_record_for_ai_detection(result, "request", image_path=self.output / "synthetic.png")
        self.assertEqual(record["owner_user_id"], "alice")
        self.assertEqual(self.captures[0][1], "request")
        with patch.object(self.repository, "save_data_analysis_record", side_effect=RuntimeError("synthetic persistence failure")):
            with self.assertRaises(RuntimeError):
                self.publisher.persist_data_analysis_record_for_ai_detection(result, "failed")
        self.assertEqual(len(self.captures), 1)
        failed_captures = []
        def failing_capture(*args):
            failed_captures.append(True)
            raise RuntimeError("synthetic capture failure")
        dependencies = replace(self.publisher.dependencies, capture=failing_capture)
        with patch.object(self.publisher, "dependencies", dependencies):
            with self.assertRaises(RuntimeError):
                self.publisher.persist_data_analysis_record_for_ai_detection(result, "capture-failed")
        self.assertEqual(failed_captures, [True])
        self.assertEqual(len(self.repository.load_data_analysis_records()), 2)
        self.identity = None
        self.assertIsNone(self.publisher.persist_data_analysis_record_for_ai_detection(result, "anonymous"))
        self.assertEqual(len(self.captures), 1)

    def test_processing_upsert_retains_owner_and_concurrent_items(self):
        kwargs = dict(record_id="same-record", task={"id": "task", "owner_user_id": "alice", "owner_username": "alice"}, source_path=self.output / "synthetic.png")
        self.publisher.upsert_data_analysis_image_processing_record(**kwargs, items=[{"id": "initial"}])
        kwargs["task"] = {"id": "task", "owner_user_id": "bob", "owner_username": "bob"}
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: self.publisher.upsert_data_analysis_image_processing_record(**kwargs, items=[{"id": f"item_{i}"}]), range(20)))
        record = self.repository.load_data_analysis_record("same-record")
        self.assertEqual(record["owner_user_id"], "alice")
        self.assertEqual(len(record["image_processing_items"]), 21)


if __name__ == "__main__":
    unittest.main()
