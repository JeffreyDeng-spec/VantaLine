"""Accepted-main versus candidate contract for recommendation pre-generation."""
import ast
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

NAMES = {"_run_pipeline_recommendation_pregen", "schedule_pipeline_recommendation_pregen"}


class RecommendationRuntimeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        root = Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix="pipeline-recommendation-runtime-")))
        (root / "local_inspection_service/static").mkdir(parents=True)
        for key in ("DATABASE_URL", "VANTALINE_POSTGRES_DSN", "PGDSN"):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE="json",
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false",
                          YOLO_AUTOINSTALL="false")
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            cls.lifetime.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))
        baseline = os.environ.get("VANTALINE_RECOMMENDATION_RUNTIME_BASELINE_SOURCE")
        if baseline:
            tree = ast.parse(Path(baseline).read_text(encoding="utf-8"))
            functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
            assert {node.name for node in functions} == NAMES
            for node in functions:
                node.decorator_list = []
            cls.api = types.ModuleType("accepted_main_recommendation_runtime")
            cls.api.__dict__.update(Any=object, threading=threading, sys=sys)
            import time, traceback
            cls.api.__dict__.update(time=time, traceback=traceback)
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
        self.task = {"id": "task", "accessory_ids": [1, "two"], "params": {"sample_count": "4"}}
        self.inflight = {"task|samples"}
        events = self.events
        class Lock:
            def __init__(self, name): self.name = name
            def __enter__(self): events.append((self.name, "enter"))
            def __exit__(self, *_): events.append((self.name, "exit"))
        self.lock = Lock("task")
        self.registry_lock = Lock("registry")
        self.replace("_pipeline_tasks_lock", self.lock)
        self.replace("_pipeline_recommendation_lock", self.registry_lock)
        self.replace("_pipeline_recommendation_inflight", self.inflight)
        self.replace("load_pipeline_task", lambda task_id: events.append(("load", task_id)) or self.task)
        self.replace("pipeline_next_recommendation_stage", lambda task: events.append("stage") or "samples")
        self.replace("pipeline_recommendation_ready", lambda task, stage: events.append("ready") or False)
        self.replace("pipeline_recommendation_signature", lambda task, stage: events.append("signature") or "signature")
        self.replace("agent_recommendation", lambda stage, ids, count: events.append(("recommend", stage, ids, count)) or
                     {"params": {"x": 1}, "reason": "reason", "source": "model"})
        self.replace("save_pipeline_task", lambda task: events.append(("save", task.copy())))
        class Identity:
            def set(self, user): events.append(("set", user)); return "token"
            def reset(self, token): events.append(("reset", token))
        self.replace("_request_user", Identity())
        self.time = self.replace("time", types.SimpleNamespace(time=lambda: 100))
        self.replace("traceback", types.SimpleNamespace(print_exc=lambda **kw: events.append(("traceback", kw))))
        self.replace("sys", types.SimpleNamespace(stderr="stderr"))

    def replace(self, name, value):
        self.stack.enter_context(patch.object(self.api, name, value, create=True))
        return value

    def run_task(self, user=None):
        runner = self.api._run_pipeline_recommendation_pregen
        if not os.environ.get("VANTALINE_RECOMMENDATION_RUNTIME_BASELINE_SOURCE"):
            runner = runner.__wrapped__
        runner("task", "samples", user)

    def test_success_lock_sequence_and_snapshot(self):
        user = {"name": "alice"}
        self.run_task(user)
        self.assertEqual(self.task["recommended_params"], {"stage": "samples", "params": {"x": 1},
                         "reason": "reason", "source": "model", "signature": "signature", "created_at": 100})
        self.assertEqual(self.task["updated_at"], 100)
        self.assertEqual(self.events, [("set", user), ("task", "enter"), ("load", "task"), "stage", "ready", "signature",
                         ("task", "exit"), ("recommend", "samples", ["1", "two"], 4),
                         ("task", "enter"), ("load", "task"), "stage", "signature", ("save", self.task.copy()),
                         ("task", "exit"), ("reset", "token"), ("registry", "enter"), ("registry", "exit")])
        self.assertFalse(self.inflight)

    def test_recommendation_params_alias_and_falsey_identity(self):
        params = {"chosen": [1, 2]}
        self.replace("agent_recommendation", lambda *_: {"params": params})
        self.run_task({})
        self.assertIs(self.task["recommended_params"]["params"], params)
        self.assertEqual(self.task["recommended_params"]["source"], "rules")
        self.assertFalse(any(isinstance(item, tuple) and item[0] in {"set", "reset"} for item in self.events))

    def test_ready_skips_recommendation_and_releases_registry(self):
        self.replace("pipeline_recommendation_ready", lambda task, stage: True)
        self.run_task()
        self.assertNotIn("recommended_params", self.task)
        self.assertFalse(self.inflight)
        self.assertNotIn(("recommend", "samples", ["1", "two"], 4), self.events)

    def test_stage_changed_during_call_skips_save(self):
        def recommend(*_):
            self.task["stage"] = "changed"
            return {"params": {"a": 1}}
        self.replace("agent_recommendation", recommend)
        self.replace("pipeline_next_recommendation_stage", lambda task: "changed" if task.get("stage") else "samples")
        self.run_task()
        self.assertNotIn("recommended_params", self.task)
        self.assertFalse(any(isinstance(item, tuple) and item[0] == "save" for item in self.events))
        self.assertFalse(self.inflight)

    def test_signature_changed_during_call_skips_save(self):
        def recommend(*_):
            self.task["new_signature"] = True
            return {}
        self.replace("agent_recommendation", recommend)
        self.replace("pipeline_recommendation_signature", lambda task, stage: "new" if task.get("new_signature") else "old")
        self.run_task()
        self.assertNotIn("recommended_params", self.task)
        self.assertFalse(self.inflight)

    def test_failure_swallowed_and_identity_reset_before_registry(self):
        self.replace("agent_recommendation", Mock(side_effect=ValueError("failed")))
        self.run_task({"name": "a"})
        self.assertEqual(self.events[-4:], [("traceback", {"file": "stderr"}), ("reset", "token"),
                         ("registry", "enter"), ("registry", "exit")])
        self.assertFalse(self.inflight)

    def test_second_clock_failure_preserves_partial_mutation(self):
        clock = iter([100, OverflowError("clock")])
        # Raise the exception value on the second read.
        def tick():
            value = next(clock)
            if isinstance(value, Exception): raise value
            return value
        self.replace("time", types.SimpleNamespace(time=tick))
        self.run_task()
        self.assertEqual(self.task["recommended_params"]["created_at"], 100)
        self.assertNotIn("updated_at", self.task)
        self.assertFalse(any(isinstance(item, tuple) and item[0] == "save" for item in self.events))
        self.assertFalse(self.inflight)

    def test_schedule_duplicates_and_thread_arguments(self):
        self.inflight.clear()
        made = []
        class Thread:
            def __init__(self, **kwargs): made.append(kwargs)
            def start(self): self.started = True
        self.replace("threading", types.SimpleNamespace(Thread=Thread))
        user = {"id": "u"}
        self.api.schedule_pipeline_recommendation_pregen([("", "samples"), ("a", ""), ("a", "samples"),
                                                           ("a", "samples"), ("b", "training")], user)
        self.assertEqual(len(made), 2)
        self.assertIs(made[0]["target"], self.api._run_pipeline_recommendation_pregen)
        self.assertEqual(made[0]["args"], ("a", "samples", user))
        self.assertIs(made[0]["daemon"], True)
        self.assertEqual(self.inflight, {"a|samples", "b|training"})

    def test_thread_start_failure_keeps_key(self):
        self.inflight.clear()
        class Thread:
            def __init__(self, **kwargs): pass
            def start(self): raise RuntimeError("start")
        self.replace("threading", types.SimpleNamespace(Thread=Thread))
        with self.assertRaisesRegex(RuntimeError, "start"):
            self.api.schedule_pipeline_recommendation_pregen([("a", "samples")], None)
        self.assertEqual(self.inflight, {"a|samples"})

    def test_decorated_root_binds_model_before_user(self):
        if os.environ.get("VANTALINE_RECOMMENDATION_RUNTIME_BASELINE_SOURCE"):
            self.skipTest("original AST contract strips the model decorator")
        events = self.events
        class Scope:
            def __enter__(self): events.append("scope-enter")
            def __exit__(self, *_): events.append("scope-exit")
        class Service:
            def current_snapshot(self): events.append("snapshot"); return {"model": "bound"}
            def scope(self, snapshot): events.append(("scope", snapshot)); return Scope()
        self.replace("model_profile_service", Service())
        self.api._run_pipeline_recommendation_pregen("task", "samples", {"name": "a"})
        self.assertEqual(events[:4], [("load", "task"), "snapshot",
                                      ("scope", {"model": "bound"}), "scope-enter"])
        self.assertEqual(events[4][0], "set")
        self.assertEqual(events[-1], "scope-exit")
        self.assertEqual(events.count(("load", "task")), 3)

    def test_model_binding_failure_does_not_enter_runtime_or_clear_registry(self):
        if os.environ.get("VANTALINE_RECOMMENDATION_RUNTIME_BASELINE_SOURCE"):
            self.skipTest("original AST contract strips the model decorator")
        self.replace("model_profile_service", None)
        with self.assertRaises(Exception):
            self.api._run_pipeline_recommendation_pregen("task", "samples", {"name": "a"})
        self.assertEqual(self.events, [])
        self.assertEqual(self.inflight, {"task|samples"})


    def test_reset_failure_preserves_registry(self):
        class Identity:
            def set(self, user): return "token"
            def reset(self, token): raise RuntimeError("reset")
        self.replace("_request_user", Identity())
        with self.assertRaisesRegex(RuntimeError, "reset"):
            self.run_task({"id": "u"})
        self.assertEqual(self.inflight, {"task|samples"})

    def test_rebind_second_read_and_next_scheduled_target(self):
        second = {"id": "second", "accessory_ids": [], "params": {}}
        first_signature = Mock(side_effect=lambda task, stage: "signature")
        second_signature = Mock(side_effect=lambda task, stage: self.events.append("rebound-signature") or "signature")
        self.replace("pipeline_recommendation_signature", first_signature)
        self.replace("load_pipeline_task", lambda _: self.task)
        class SecondLock:
            def __enter__(inner): self.events.append("second-lock-enter")
            def __exit__(inner, *_): self.events.append("second-lock-exit")
        def recommend(*_):
            self.replace("pipeline_recommendation_signature", second_signature)
            self.replace("_pipeline_tasks_lock", SecondLock())
            self.replace("load_pipeline_task", lambda _: self.events.append("rebound-load") or second)
            return {"params": {"late": 1}}
        self.replace("agent_recommendation", recommend)
        self.run_task()
        self.assertEqual(second["recommended_params"]["params"], {"late": 1})
        first_signature.assert_called_once_with(self.task, "samples")
        second_signature.assert_called_once_with(second, "samples")
        section = self.events[self.events.index("second-lock-enter"):self.events.index("second-lock-exit") + 1]
        self.assertEqual(section[0:3], ["second-lock-enter", "rebound-load", "stage"])
        self.assertEqual(section[3], "rebound-signature")
        self.assertEqual(section[4][0], "save")
        self.assertEqual(section[5], "second-lock-exit")
        self.inflight.clear()
        targets = []
        def next_runner(*_): pass
        class Thread:
            def __init__(inner, **kwargs): targets.append(kwargs["target"])
            def start(inner):
                if len(targets) == 1:
                    self.replace("_run_pipeline_recommendation_pregen", next_runner)
        self.replace("threading", types.SimpleNamespace(Thread=Thread))
        first = self.api._run_pipeline_recommendation_pregen
        self.api.schedule_pipeline_recommendation_pregen([("a", "samples"), ("b", "samples")], None)
        self.assertEqual(targets, [first, next_runner])

    def test_independent_runtime_instances_a_b_a(self):
        if os.environ.get("VANTALINE_RECOMMENDATION_RUNTIME_BASELINE_SOURCE"):
            self.skipTest("candidate-only instance independence")
        from local_inspection_service.pipeline.recommendation_runtime import PipelineRecommendationRuntime
        from local_inspection_service.pipeline.recommendation_runtime_ports import (
            RecommendationTasks, RecommendationExecution, RecommendationScheduling,
        )
        traces = {"a": [], "b": []}
        reads = {"a": [], "b": []}
        class Lock:
            def __enter__(self): pass
            def __exit__(self, *_): pass
        def make(label):
            trace = traces[label]
            record = {"accessory_ids": [label], "params": {"sample_count": 2}}
            inflight = {"task|samples"}
            def get(name, value):
                def resolve():
                    reads[label].append(name)
                    return value
                return resolve
            class Identity:
                def set(self, user): trace.append("set"); return "token"
                def reset(self, token): trace.append("reset")
            class Thread:
                def __init__(self, **kwargs): trace.append(("thread", kwargs["args"], kwargs["daemon"]))
                def start(self): trace.append("start")
            runtime = PipelineRecommendationRuntime(
                RecommendationTasks(get("task_lock", Lock()), get("load", lambda _: record),
                                    get("next_stage", lambda _: "samples"), get("ready", lambda *_: False),
                                    get("signature", lambda *_: label), get("save", lambda _: trace.append("save"))),
                RecommendationExecution(get("identity", Identity()),
                                        get("recommend", lambda *_: {"params": {"owner": label}}),
                                        get("clock", lambda: 20), get("traceback", lambda **_: trace.append("error")),
                                        get("stderr", "stderr")),
                RecommendationScheduling(get("registry_lock", Lock()), get("inflight", inflight), get("thread", Thread),
                                         get("runner", lambda *_: trace.append("runner"))),
            )
            return runtime, record, inflight
        a, a_record, a_inflight = make("a")
        b, b_record, b_inflight = make("b")
        self.assertEqual(reads, {"a": [], "b": []})
        a.run("task", "samples", {"id": "a"})
        b.run("task", "samples", {"id": "b"})
        a.run("task", "samples", {"id": "a"})
        a.schedule([("again", "samples")], None)
        b.schedule([("other", "samples")], None)
        b_record["params"]["sample_count"] = "invalid"
        b.run("task", "samples", {"id": "b"})
        self.assertEqual(a_record["recommended_params"]["params"], {"owner": "a"})
        self.assertEqual(b_record["recommended_params"]["params"], {"owner": "b"})
        self.assertEqual(traces["a"], ["set", "save", "reset", "set", "save", "reset",
                                        ("thread", ("again", "samples", None), True), "start"])
        self.assertEqual(traces["b"], ["set", "save", "reset",
                                        ("thread", ("other", "samples", None), True), "start",
                                        "set", "error", "reset"])
        self.assertEqual(a_inflight, {"again|samples"})
        self.assertEqual(b_inflight, {"other|samples"})
        exercised = {"identity", "task_lock", "load", "next_stage", "ready", "signature", "recommend",
                     "clock", "save", "registry_lock", "inflight", "thread", "runner",
                     "traceback", "stderr"}
        self.assertLessEqual(exercised - {"traceback", "stderr"}, set(reads["a"]))
        self.assertLessEqual(exercised, set(reads["b"]))


if __name__ == "__main__":
    unittest.main()
