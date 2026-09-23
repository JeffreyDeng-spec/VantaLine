"""Synthetic contract for pipeline reconciliation, replayable against accepted main."""

import ast
from contextlib import ExitStack
import copy
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

NAMES = {
    "pipeline_task_decision_signature",
    "pipeline_task_needs_auto_agent",
    "reap_pipeline_advance_zombie",
    "sync_and_auto_advance_pipeline",
}


class ReconciliationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        root = Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix="pipeline-reconciliation-")))
        (root / "local_inspection_service/static").mkdir(parents=True)
        for key in ("DATABASE_URL", "VANTALINE_POSTGRES_DSN", "PGDSN"):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE="json",
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false",
                          YOLO_AUTOINSTALL="false")
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            cls.lifetime.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))
        baseline = os.environ.get("VANTALINE_RECONCILIATION_BASELINE_SOURCE")
        if baseline:
            source = Path(baseline).read_text(encoding="utf-8")
            tree = ast.parse(source)
            functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
            if {node.name for node in functions} != NAMES:
                raise AssertionError("accepted-main reconciliation functions missing")
            cls.api = types.ModuleType("accepted_main_pipeline_reconciliation")
            cls.api.__dict__["Any"] = object
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

    def replace(self, name, value):
        self.stack.enter_context(patch.object(self.api, name, value, create=True))
        return value

    def policy(self, *, normalize="yolo", uses=True):
        events = []
        self.replace("normalize_pipeline_detection_method", lambda raw: events.append(("normalize", raw)) or normalize)
        self.replace("pipeline_method_uses_training", lambda method: events.append(("uses", method)) or uses)
        return events

    def sync_dependencies(self, events, *, llm=True, finder=None, sync=None, reap=None, needs=None,
                          orchestration=None, signature=None):
        self.replace("load_agent_config", lambda: events.append("config") or {"x": 1})
        self.replace("agent_recommendation_supported", lambda config: events.append(("supported", config)) or llm)
        chosen_finder = finder or object()
        self.replace("training_task_finder", lambda: events.append("finder") or chosen_finder)
        self.replace("reap_pipeline_advance_zombie", reap or (lambda task: events.append(("reap", task.get("id"))) or False))
        self.replace("sync_pipeline_task", sync or (lambda task, found: events.append(("sync", task.get("id"), found is chosen_finder)) or False))
        self.replace("pipeline_task_needs_auto_agent", needs or (lambda task: events.append(("needs", task.get("id"))) or True))
        self.replace("agent_mcp_orchestration", orchestration or (lambda task: events.append(("orchestration", task.get("id"))) or {}))
        self.replace("pipeline_task_decision_signature", signature or (lambda task: events.append(("signature", task.get("id"))) or "sig"))

    def test_signature_exact_string_and_bad_progress(self):
        self.assertEqual(self.api.pipeline_task_decision_signature({"stage": 0, "status": None, "progress": "02"}), "0|None|2")
        with self.assertRaises(ValueError):
            self.api.pipeline_task_decision_signature({"progress": "bad"})

    def test_eligibility_short_circuits_and_policy_order(self):
        events = self.policy()
        self.assertFalse(self.api.pipeline_task_needs_auto_agent({"task_kind": "incoming_material_text", "auto_advance": True}))
        self.assertFalse(self.api.pipeline_task_needs_auto_agent({"auto_advance": False, "detection_method": "yolo"}))
        self.assertEqual(events, [])
        task = {"auto_advance": True, "params": {"train_mode": "fallback"}, "stage": "samples", "status": "completed"}
        self.assertTrue(self.api.pipeline_task_needs_auto_agent(task))
        self.assertEqual(events, [("normalize", "fallback"), ("uses", "yolo")])
        task.update(stage="draft", status="failed")
        self.assertTrue(self.api.pipeline_task_needs_auto_agent(task))
        task.update(stage="draft", status="completed")
        self.assertFalse(self.api.pipeline_task_needs_auto_agent(task))

    def test_eligibility_malformed_params_fails_before_normalize(self):
        events = self.policy()
        with self.assertRaises(AttributeError):
            self.api.pipeline_task_needs_auto_agent({"auto_advance": True, "params": ["bad"]})
        self.assertEqual(events, [])

    def test_zombie_paths_and_boundary(self):
        class Lock:
            def __enter__(self): return self
            def __exit__(self, *args): return False
        self.replace("_pipeline_advance_registry_lock", Lock())
        inflight = self.replace("_pipeline_advance_inflight", {"live"})
        times = Mock(side_effect=[110, 110, 111])
        self.replace("time", types.SimpleNamespace(time=times))
        self.replace("PIPELINE_ADVANCE_ZOMBIE_TIMEOUT_S", 10)
        self.assertFalse(self.api.reap_pipeline_advance_zombie({"id": "x"}))
        self.assertFalse(self.api.reap_pipeline_advance_zombie({"id": "live", "advancing": True}))
        self.assertFalse(self.api.reap_pipeline_advance_zombie({"id": "early", "advancing": True, "advance_started_at": 101}))
        task = {"id": "edge", "advancing": True, "advance_started_at": 100}
        self.assertTrue(self.api.reap_pipeline_advance_zombie(task))
        self.assertEqual(task["updated_at"], 111)
        self.assertNotIn("advancing", task)
        self.assertNotIn("advance_started_at", task)
        self.assertEqual(times.call_count, 3)
        self.assertIn("live", inflight)

    def test_zombie_missing_started_and_second_clock_failure(self):
        class Lock:
            def __enter__(self): return self
            def __exit__(self, *args): return False
        self.replace("_pipeline_advance_registry_lock", Lock())
        self.replace("_pipeline_advance_inflight", set())
        self.replace("PIPELINE_ADVANCE_ZOMBIE_TIMEOUT_S", 10)
        zero_clock = Mock(side_effect=[RuntimeError("zero clock")])
        self.replace("time", types.SimpleNamespace(time=zero_clock))
        zero = {"id": "zero", "advancing": True, "advance_started_at": 0}
        with self.assertRaisesRegex(RuntimeError, "zero clock"):
            self.api.reap_pipeline_advance_zombie(zero)
        self.assertEqual(zero_clock.call_count, 1)
        self.assertNotIn("advancing", zero)
        self.assertNotIn("updated_at", zero)
        second_error = RuntimeError("second clock")
        second_clock = Mock(side_effect=[110, second_error])
        self.replace("time", types.SimpleNamespace(time=second_clock))
        task = {"id": "x", "advancing": True, "advance_started_at": 100}
        with self.assertRaisesRegex(RuntimeError, "second clock") as raised:
            self.api.reap_pipeline_advance_zombie(task)
        self.assertIs(raised.exception, second_error)
        self.assertEqual(second_clock.call_count, 2)
        self.assertNotIn("advancing", task)
        self.assertNotIn("advance_started_at", task)
        self.assertIn("last_error", task)
        self.assertIn("job_note", task)
        self.assertNotIn("updated_at", task)

    def test_registry_membership_under_lock_and_clock_after_release(self):
        events = []
        class Lock:
            active = False
            def __enter__(self):
                self.active = True
                events.append("enter")
                return self
            def __exit__(self, *args):
                self.active = False
                events.append("exit")
                return False
        lock = Lock()
        class Membership:
            def __contains__(self, task_id):
                self_outer.assertTrue(lock.active)
                events.append(("member", task_id))
                return False
        self_outer = self
        self.replace("_pipeline_advance_registry_lock", lock)
        self.replace("_pipeline_advance_inflight", Membership())
        self.replace("PIPELINE_ADVANCE_ZOMBIE_TIMEOUT_S", 10)
        def now():
            self.assertFalse(lock.active)
            events.append("clock")
            return 110
        self.replace("time", types.SimpleNamespace(time=now))
        self.assertTrue(self.api.reap_pipeline_advance_zombie({"id": "x", "advancing": True, "advance_started_at": 100}))
        self.assertEqual(events, ["enter", ("member", "x"), "exit", "clock", "clock"])

    def test_empty_still_loads_config_support_and_finder(self):
        events = []
        self.sync_dependencies(events)
        self.assertEqual(self.api.sync_and_auto_advance_pipeline([]), (False, [], []))
        self.assertEqual(events, ["config", ("supported", {"x": 1}), "finder"])

    def test_reap_sync_needs_order_identity_and_changed(self):
        events = []
        finder = object()
        task = {"id": "x", "stage": "samples", "status": "completed"}
        def reap(item):
            events.append("reap")
            item["reaped"] = True
            return True
        def sync(item, found):
            events.append(("sync", item is task, found is finder, item["reaped"]))
            item["synced"] = True
            return False
        self.sync_dependencies(events, finder=finder, reap=reap, sync=sync)
        self.assertEqual(self.api.sync_and_auto_advance_pipeline([task]), (True, ["x"], []))
        self.assertEqual(events, ["config", ("supported", {"x": 1}), "finder", "reap", ("sync", True, True, True), ("needs", "x"), ("orchestration", "x"), ("signature", "x")])
        self.assertTrue(task["synced"])

    def test_llm_same_signature_suppression_duplicates_and_missing_id(self):
        events = []
        self.sync_dependencies(events, orchestration=lambda task: {"last_auto_signature": "sig"} if task.get("id") == "same" else {})
        tasks = [{"id": "same"}, {}, {}, {"id": "other"}, {"id": "other"}]
        self.assertEqual(self.api.sync_and_auto_advance_pipeline(tasks), (False, ["None", "None", "other", "other"], []))

    def test_rules_queue_only_completed_samples_training(self):
        events = []
        self.sync_dependencies(events, llm=False)
        tasks = [{"id": "a", "stage": "samples", "status": "completed"},
                 {"id": "b", "stage": "training", "status": "completed"},
                 {"id": "c", "stage": "draft", "status": "completed"},
                 {"id": "d", "stage": "samples", "status": "failed"}, {}]
        self.assertEqual(self.api.sync_and_auto_advance_pipeline(tasks), (False, [], ["a", "b"]))
        self.assertFalse(any(isinstance(item, tuple) and item[0] == "orchestration" for item in events))

    def test_previous_mutation_survives_later_exception(self):
        events = []
        tasks = [{"id": "first"}, {"id": "second"}]
        def reap(task):
            task["visited"] = True
            if task["id"] == "second":
                raise RuntimeError("second failed")
            return True
        self.sync_dependencies(events, reap=reap)
        with self.assertRaisesRegex(RuntimeError, "second failed"):
            self.api.sync_and_auto_advance_pipeline(tasks)
        self.assertTrue(tasks[0]["visited"])
        self.assertTrue(tasks[1]["visited"])

    def test_candidate_instances_are_isolated_and_constructor_is_passive(self):
        if os.environ.get("VANTALINE_RECONCILIATION_BASELINE_SOURCE"):
            self.skipTest("candidate-only constructor contract")
        from local_inspection_service.pipeline.reconciliation import PipelineReconciliation
        from local_inspection_service.pipeline.reconciliation_ports import (
            ReconciliationCalls, ReconciliationPolicy, ReconciliationRegistry,
        )
        reads = []
        def getter(name, value):
            return lambda: reads.append(name) or value
        def unused():
            raise AssertionError("constructor read unused capability")
        calls = ReconciliationCalls(*(unused for _ in range(8)))
        registry = ReconciliationRegistry(*(unused for _ in range(4)))
        a = PipelineReconciliation(ReconciliationPolicy(getter("a-normalize", lambda raw: "a"),
                                                        getter("a-uses", lambda method: True)), registry, calls)
        b = PipelineReconciliation(ReconciliationPolicy(getter("b-normalize", lambda raw: "b"),
                                                        getter("b-uses", lambda method: False)), registry, calls)
        self.assertEqual(reads, [])
        task = {"auto_advance": True, "stage": "samples", "status": "completed"}
        self.assertTrue(a.pipeline_task_needs_auto_agent(task))
        self.assertFalse(b.pipeline_task_needs_auto_agent(task))
        self.assertTrue(a.pipeline_task_needs_auto_agent(task))
        self.assertEqual(reads, ["a-normalize", "a-uses", "b-normalize", "b-uses", "a-normalize", "a-uses"])

    def test_callback_rebinding_during_loop(self):
        events = []
        tasks = [{"id": "first"}, {"id": "second"}]
        def reap(task):
            events.append(("reap", task["id"]))
            if task["id"] == "first":
                self.replace("sync_pipeline_task", lambda t, finder: events.append(("new-sync", t["id"])) or False)
            return False
        self.sync_dependencies(events, reap=reap)
        self.api.sync_and_auto_advance_pipeline(tasks)
        self.assertEqual([item for item in events if isinstance(item, tuple) and item[0] == "new-sync"],
                         [("new-sync", "first"), ("new-sync", "second")])


if __name__ == "__main__":
    unittest.main()
