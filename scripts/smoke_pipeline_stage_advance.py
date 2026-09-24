"""Accepted-main and extracted stage-transition behavior on synthetic tasks."""
import ast
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class HttpError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code, self.detail = status_code, detail


class Cancelled(Exception):
    pass


class StageAdvanceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        root = Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix="pipeline-stage-advance-")))
        (root / "local_inspection_service/static").mkdir(parents=True)
        for key in ("DATABASE_URL", "VANTALINE_POSTGRES_DSN", "PGDSN"):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE="json",
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false",
                          YOLO_AUTOINSTALL="false")
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            cls.lifetime.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))
        baseline = os.environ.get("VANTALINE_STAGE_ADVANCE_BASELINE_SOURCE")
        if baseline:
            tree = ast.parse(Path(baseline).read_text(encoding="utf-8"))
            functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "advance_pipeline_task"]
            assert len(functions) == 1
            cls.api = types.ModuleType("accepted_main_stage_advance")
            cls.api.__dict__.update(Any=Any, threading=threading, time=time)
            exec(compile(ast.Module(body=functions, type_ignores=[]), baseline, "exec"), cls.api.__dict__)
        else:
            from local_inspection_service import server
            cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.lifetime.close()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.events = []
        self.task = {"id": "task", "stage": "draft", "status": "pending", "accessory_ids": ["a"], "params": {}}
        self.cancel = threading.Event()
        events = self.events
        self.replace("HTTPException", HttpError)
        self.replace("PipelineAdvanceCancelled", Cancelled)
        self.replace("print", lambda *args, **kwargs: events.append(("print", args, kwargs)))
        self.replace("time", types.SimpleNamespace(monotonic=lambda: events.append("mono") or 5.0,
                                                        time=lambda: events.append("time") or 123.0))
        self.replace("normalize_pipeline_detection_method", lambda value: events.append(("method", value)) or "yolo_ocr")
        self.replace("load_config", lambda: events.append("load-config") or {"config": 1})
        self.replace("save_config", lambda config: events.append(("save-config", config.copy())))
        self.replace("canonical_pipeline_accessory_ids", lambda config, ids: events.append(("canonical", ids.copy())) or ids)
        self.replace("consume_pipeline_recommendation", lambda task, stage: events.append(("consume", stage)) or None)
        self.replace("agent_recommendation", lambda *args: events.append(("recommend", args)) or
                     {"params": {"sample_count": 10, "epochs": 3}, "reason": "reason", "source": "test"})
        self.replace("activate_pipeline_ai_detection_task", lambda task, config: events.append("activate-ai"))
        self.replace("prepare_agent_mcp_before_sample_generation", lambda task, config: events.append("prepare") or True)
        self.replace("materialize_agent_mcp_pose_assets", lambda task, config: events.append("materialize") or False)
        self.replace("ensure_training_normalized_assets_for_selection", lambda config, ids: events.append("normalize-assets") or False)
        self.replace("persist_pipeline_task_progress", lambda task_id, **kwargs: events.append(("persist", task_id, kwargs)))
        self.replace("agent_mcp_orchestration", lambda task: events.append("orchestration") or {})
        self.replace("pause_agent_mcp_task", lambda *args, **kwargs: events.append(("pause", kwargs)))
        self.replace("TrainingStartRequest", lambda **kwargs: events.append(("request-model", kwargs)) or kwargs)
        self.replace("request_sample_generation", lambda request: events.append(("request-samples", request)) or {"job_id": "samples-id"})
        self.replace("request_training", lambda request: events.append(("request-training", request)) or {"job_id": "training-id"})
        self.replace("task_record_name", lambda task: events.append("task-name") or "Task")
        self.replace("log_agent_mcp_sample_tool_call", lambda task, job: events.append("log-samples"))
        self.replace("log_agent_mcp_training_tool_call", lambda task, job: events.append("log-training"))
        self.replace("agent_mcp_training_quality_gate", lambda task: events.append("quality") or True)
        self.replace("link_pipeline_trained_model", lambda task: events.append("link-model"))

    def replace(self, name, value):
        self.stack.enter_context(patch.object(self.api, name, value, create=True))

    def run_advance(self):
        self.api.advance_pipeline_task(self.task, self.cancel)

    def test_draft_missing_accessory_and_initial_cancellation(self):
        self.task["accessory_ids"] = []
        with self.assertRaises(HttpError) as caught:
            self.run_advance()
        self.assertEqual(caught.exception.status_code, 400)
        self.assertNotIn("load-config", self.events)
        self.cancel.set()
        with self.assertRaises(Cancelled):
            self.run_advance()
        self.assertNotIn("load-config", self.events)

    def test_draft_ai_and_locate_early_returns(self):
        self.replace("normalize_pipeline_detection_method", lambda _: "ai")
        self.run_advance()
        self.assertIn("activate-ai", self.events)
        self.assertNotIn("persist", [item[0] for item in self.events if isinstance(item, tuple)])
        self.task["stage"] = "draft"
        self.replace("normalize_pipeline_detection_method", lambda _: "locate")
        self.run_advance()
        self.assertEqual((self.task["stage"], self.task["linked_view"], self.task["updated_at"]),
                         ("library", "locateAnything", 123))

    def test_draft_sample_success_order_and_alias(self):
        original_params = self.task["params"]
        self.run_advance()
        self.assertEqual((self.task["stage"], self.task["samples_task_id"], self.task["params"]["sample_count"]),
                         ("samples", "samples-id", 10))
        self.assertIsNot(self.task["params"], original_params)
        labels = [entry[0] if isinstance(entry, tuple) else entry for entry in self.events]
        self.assertLess(labels.index("request-model"), labels.index("request-samples"))
        self.assertLess(labels.index("request-samples"), labels.index("log-samples"))
        self.assertEqual(labels.count("persist"), 4)

    def test_draft_cached_recommendation_and_prepare_pause(self):
        self.replace("consume_pipeline_recommendation", lambda task, stage: {"sample_count": 7})
        self.replace("prepare_agent_mcp_before_sample_generation", lambda task, config: False)
        self.task["status"] = "needs_user_action"
        self.task["last_error"] = "needs photo"
        self.run_advance()
        self.assertEqual(self.task["params"]["sample_count"], 7)
        self.assertEqual(self.task["stage"], "draft")
        self.assertTrue(any(isinstance(item, tuple) and item[0] == "pause" for item in self.events))
        self.assertFalse(any(isinstance(item, tuple) and item[0] == "recommend" for item in self.events))

    def test_normalization_409_and_save_failure(self):
        self.replace("ensure_training_normalized_assets_for_selection", lambda *_: (_ for _ in ()).throw(HttpError(409, "busy")))
        self.run_advance()
        labels = [entry[0] if isinstance(entry, tuple) else entry for entry in self.events]
        self.assertLess(labels.index("save-config"), labels.index("time"))
        self.assertEqual((self.task["stage"], self.task["status"], self.task["last_error"]),
                         ("draft", "pending", "busy"))
        self.events.clear()
        self.task = {"id": "task2", "stage": "draft", "status": "running",
                     "accessory_ids": ["a"], "params": {"sample_count": 4}}
        save_error = ValueError("save failed")
        self.replace("save_config", lambda _: (_ for _ in ()).throw(save_error))
        with self.assertRaises(ValueError) as caught:
            self.run_advance()
        self.assertIs(caught.exception, save_error)
        self.assertEqual((self.task["stage"], self.task["status"], self.task["progress"]),
                         ("draft", "running", 55))
        self.assertNotIn("updated_at", self.task)
        self.assertEqual(self.task["params"], {"sample_count": 4})

    def test_samples_precondition_quality_and_training_success(self):
        self.task.update(stage="samples", status="running")
        with self.assertRaises(HttpError) as caught:
            self.run_advance()
        self.assertEqual(caught.exception.status_code, 409)
        self.task["status"] = "completed"
        self.replace("agent_mcp_training_quality_gate", lambda _: False)
        self.run_advance()
        self.assertEqual(self.task["stage"], "samples")
        self.replace("agent_mcp_training_quality_gate", lambda _: True)
        self.run_advance()
        self.assertEqual((self.task["stage"], self.task["training_task_id"]), ("training", "training-id"))

    def test_training_link_and_terminal_rejection(self):
        self.task.update(stage="training", status="completed")
        self.run_advance()
        self.assertEqual((self.task["stage"], self.task["updated_at"]), ("library", 123))
        self.assertIn("link-model", self.events)
        with self.assertRaises(HttpError) as caught:
            self.run_advance()
        self.assertEqual(caught.exception.status_code, 409)

    def test_mid_step_cancellation_preserves_progress(self):
        def persist(*args, **kwargs):
            self.cancel.set()
            self.events.append("persist-set-cancel")
        self.replace("persist_pipeline_task_progress", persist)
        with self.assertRaises(Cancelled):
            self.run_advance()
        self.assertEqual(self.task["progress"], 10)
        self.assertEqual(self.task["stage"], "draft")


    def test_request_callee_is_selected_before_model_arguments(self):
        def first(request):
            self.events.append("first-request")
            return {"job_id": "first"}
        def second(request):
            self.events.append("second-request")
            return {"job_id": "second"}
        def request_model(**kwargs):
            self.events.append("request-model-rebind")
            setattr(self.api, "request_sample_generation", second)
            return kwargs
        self.replace("request_sample_generation", first)
        self.replace("TrainingStartRequest", request_model)
        self.run_advance()
        self.assertEqual(self.task["samples_task_id"], "first")
        self.assertNotIn("second-request", self.events)

    def test_non_409_normalization_error_saves_before_reraise(self):
        self.replace("ensure_training_normalized_assets_for_selection", lambda *_: (_ for _ in ()).throw(HttpError(422, "bad")))
        with self.assertRaises(HttpError) as caught:
            self.run_advance()
        self.assertEqual(caught.exception.status_code, 422)
        self.assertTrue(any(isinstance(item, tuple) and item[0] == "save-config" for item in self.events))
        self.assertEqual((self.task["job_note"], self.task["progress"]), ("规范化训练素材…", 55))

    def test_progress_failure_keeps_memory_change(self):
        self.replace("persist_pipeline_task_progress", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("db")))
        with self.assertRaisesRegex(ValueError, "db"):
            self.run_advance()
        self.assertEqual((self.task["job_note"], self.task["progress"], self.task["stage"]),
                         ("准备实拍高亮抠图与背景底板…", 10, "draft"))

    def test_training_link_failure_keeps_stage_change(self):
        self.task.update(stage="training", status="completed")
        self.replace("link_pipeline_trained_model", lambda _: (_ for _ in ()).throw(ValueError("link")))
        with self.assertRaisesRegex(ValueError, "link"):
            self.run_advance()
        self.assertEqual((self.task["stage"], self.task["status"]), ("library", "completed"))
        self.assertNotIn("updated_at", self.task)
    def test_constructor_and_two_instance_isolation(self):
        if os.environ.get("VANTALINE_STAGE_ADVANCE_BASELINE_SOURCE"):
            self.skipTest("candidate composition only")
        from local_inspection_service.pipeline.stage_advance import PipelineStageAdvancer
        from local_inspection_service.pipeline.stage_advance_ports import (
            StageAdvanceAssets, StageAdvanceJobs, StageAdvancePolicy, StageAdvanceRuntime)
        reads = []
        def getter(name, value):
            return lambda: reads.append(name) or value
        def build(label):
            policy = StageAdvancePolicy(*[getter(label + field, value) for field, value in [
                ("method", lambda _: "locate"), ("consume", lambda *_: None),
                ("recommend", lambda *_: {}), ("canonical", lambda *_: []),
                ("orchestration", lambda *_: {}), ("pause", lambda *_: None),
                ("quality", lambda *_: True), ("link", lambda *_: None),
                ("http", HttpError), ("cancel", Cancelled)]])
            assets = StageAdvanceAssets(*[getter(label + str(i), lambda *_: None) for i in range(6)])
            jobs = StageAdvanceJobs(*[getter(label + str(i), lambda *_: None) for i in range(6)])
            runtime = StageAdvanceRuntime(getter(label + "persist", lambda *_a, **_k: None),
                                          getter(label + "mono", lambda: 1.0),
                                          getter(label + "clock", lambda: 42),
                                          getter(label + "print", lambda *_a, **_k: None))
            return PipelineStageAdvancer(policy, assets, jobs, runtime)
        a, b = build("a"), build("b")
        self.assertEqual(reads, [])
        first = {"id": "a", "stage": "draft", "accessory_ids": ["x"], "params": {}}
        second = {"id": "b", "stage": "draft", "accessory_ids": ["y"], "params": {}}
        a.advance(first)
        b.advance(second)
        a.advance({"id": "a2", "stage": "draft", "accessory_ids": ["z"], "params": {}})
        self.assertEqual((first["updated_at"], second["updated_at"]), (42, 42))
        self.assertEqual([name[0] for name in reads if name.endswith("method")], ["a", "b", "a"])
if __name__ == "__main__":
    unittest.main()
