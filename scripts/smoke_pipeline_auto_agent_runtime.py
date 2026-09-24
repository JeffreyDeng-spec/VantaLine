"""Accepted-main versus candidate contract for pipeline auto-Agent background execution."""
import ast
import copy
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
NAMES = {"_run_pipeline_auto_agent_step", "schedule_pipeline_auto_agent"}


class AutoAgentRuntimeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        root = Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix="pipeline-auto-agent-runtime-")))
        (root / "local_inspection_service/static").mkdir(parents=True)
        for key in ("DATABASE_URL", "VANTALINE_POSTGRES_DSN", "PGDSN"):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE="json",
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false",
                          YOLO_AUTOINSTALL="false")
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            cls.lifetime.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))
        baseline = os.environ.get("VANTALINE_AUTO_AGENT_RUNTIME_BASELINE_SOURCE")
        if baseline:
            tree = ast.parse(Path(baseline).read_text(encoding="utf-8"))
            functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
            assert {node.name for node in functions} == NAMES
            for node in functions:
                node.decorator_list = []
            cls.api = types.ModuleType("accepted_main_auto_agent_runtime")
            import traceback
            cls.api.__dict__.update(Any=object, copy=copy, threading=threading, sys=sys, traceback=traceback)
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
        self.task = {"id": "task", "stage": "training", "status": "completed", "orchestration": {"auto_steps": 1}}
        self.inflight = {"task"}
        events = self.events
        class Lock:
            def __init__(self, name): self.name = name
            def __enter__(self): events.append((self.name, "enter"))
            def __exit__(self, *_): events.append((self.name, "exit"))
        self.task_lock = Lock("task-lock")
        self.registry_lock = Lock("registry-lock")
        self.replace("_pipeline_tasks_lock", self.task_lock)
        self.replace("_pipeline_auto_agent_lock", self.registry_lock)
        self.replace("_pipeline_auto_agent_inflight", self.inflight)
        self.replace("load_pipeline_task", lambda task_id: events.append(("load", task_id)) or self.task)
        self.replace("pipeline_task_needs_auto_agent", lambda task: events.append(("needs", task["id"])) or True)
        self.replace("agent_mcp_orchestration", lambda task: events.append("orchestration") or task["orchestration"])
        self.replace("pipeline_task_decision_signature", lambda task: events.append("signature") or "sig")
        self.replace("AGENT_MCP_AUTO_MAX_STEPS", 3)
        self.replace("pause_agent_mcp_task", lambda *args, **kwargs: events.append(("pause", args, kwargs)))
        self.replace("agent_mcp_append_conversation", lambda *args, **kwargs: events.append(("conversation", args, kwargs)))
        self.replace("save_pipeline_task", lambda task: events.append(("save", task["orchestration"].copy())))
        self.replace("load_config", lambda: events.append("load-config") or {"base": True})
        self.replace("scope_config_for_user", lambda config, user: events.append(("scope-config", config, user)) or {"scoped": True})
        self.replace("agent_pipeline_decide", lambda snapshot, config, **kw: events.append(("decide", snapshot, config, kw)) or {"action": "go"})
        self.replace("commit_pipeline_agent_turn", lambda task, config, user, message, decision, trigger, **kw:
                     events.append(("commit", task, config, user, message, decision, trigger)) or kw["pending_advances"].append("advance"))
        self.replace("agent_mcp_now", lambda: events.append("now") or 123)
        self.replace("schedule_pipeline_advance", lambda task_id, user: events.append(("advance", task_id, user)))
        class Identity:
            def set(self, user): events.append(("set", user)); return "token"
            def reset(self, token): events.append(("reset", token))
        self.replace("_request_user", Identity())
        self.replace("traceback", types.SimpleNamespace(print_exc=lambda **kw: events.append(("traceback", kw))))
        self.replace("sys", types.SimpleNamespace(stderr="stderr"))

    def replace(self, name, value):
        self.stack.enter_context(patch.object(self.api, name, value, create=True))
        return value

    def run_task(self, user=None):
        fn = self.api._run_pipeline_auto_agent_step
        if not os.environ.get("VANTALINE_AUTO_AGENT_RUNTIME_BASELINE_SOURCE"):
            fn = fn.__wrapped__
        fn("task", user)

    def test_success_order_and_unlocked_decision(self):
        user = {"id": "alice"}
        self.run_task(user)
        events = self.events
        self.assertEqual(events[0:9], [("set", user), ("task-lock", "enter"), ("load", "task"),
                         ("needs", "task"), "orchestration", "signature", ("task-lock", "exit"),
                         "load-config", ("scope-config", {"base": True}, user)])
        self.assertEqual(events[9][0], "decide")
        self.assertEqual(events[9][3], {"user_message": None, "trigger": "auto"})
        self.assertEqual(events[10:14], [("task-lock", "enter"), ("load", "task"), ("needs", "task"), "orchestration"])
        self.assertEqual(events[14][0], "commit")
        self.assertEqual(events[15:19], ["orchestration", "now", ("save", {"auto_steps": 2, "last_auto_signature": "sig", "last_auto_step_at": 123}),
                                           ("task-lock", "exit")])
        self.assertEqual(events[19:23], [("advance", "advance", user), ("reset", "token"),
                                          ("registry-lock", "enter"), ("registry-lock", "exit")])
        self.assertFalse(self.inflight)

    def test_not_needed_short_circuits_and_cleans_registry(self):
        self.replace("pipeline_task_needs_auto_agent", lambda task: False)
        self.run_task()
        self.assertNotIn("load-config", self.events)
        self.assertFalse(self.inflight)

    def test_duplicate_signature_short_circuits(self):
        self.task["orchestration"]["last_auto_signature"] = "sig"
        self.run_task()
        self.assertNotIn("load-config", self.events)
        self.assertFalse(self.inflight)

    def test_max_step_pauses_and_saves_under_first_lock(self):
        self.task["orchestration"]["auto_steps"] = 3
        self.run_task()
        self.assertEqual(self.task["orchestration"]["last_auto_signature"], "sig")
        names = [item[0] if isinstance(item, tuple) else item for item in self.events]
        self.assertLess(names.index("pause"), names.index("conversation"))
        self.assertLess(names.index("conversation"), names.index("save"))
        self.assertLess(names.index("save"), names.index("task-lock", names.index("save") + 1))
        self.assertNotIn("load-config", names)
        self.assertFalse(self.inflight)

    def test_stale_second_signature_does_not_commit(self):
        def decide(*args, **kwargs):
            self.task["orchestration"]["last_auto_signature"] = "sig"
            return {"action": "go"}
        self.replace("agent_pipeline_decide", decide)
        self.run_task()
        self.assertFalse(any(isinstance(item, tuple) and item[0] == "commit" for item in self.events))
        self.assertFalse(self.inflight)

    def test_scope_callee_selected_before_config_loader_rebind(self):
        self.replace("scope_config_for_user", lambda config, user: self.events.append("original-scope") or config)
        def load():
            self.replace("scope_config_for_user", lambda *_: self.events.append("rebound-scope") or {})
            return {"base": True}
        self.replace("load_config", load)
        self.run_task()
        self.assertIn("original-scope", self.events)
        self.assertNotIn("rebound-scope", self.events)

    def test_decision_uses_deep_snapshot_and_commit_reloads_orchestration(self):
        old = self.task["orchestration"]
        def decide(snapshot, config, **kwargs):
            self.assertIsNot(snapshot, self.task)
            self.assertIsNot(snapshot["orchestration"], old)
            snapshot["orchestration"]["auto_steps"] = 99
            self.assertEqual(old["auto_steps"], 1)
            return {"action": "go"}
        self.replace("agent_pipeline_decide", decide)
        def commit(task, config, user, message, decision, trigger, *, pending_advances):
            task["orchestration"] = {"auto_steps": 5}
        self.replace("commit_pipeline_agent_turn", commit)
        self.run_task()
        self.assertEqual(old, {"auto_steps": 1})
        self.assertEqual(self.task["orchestration"], {"auto_steps": 6,
                         "last_auto_signature": "sig", "last_auto_step_at": 123})
        self.assertEqual(self.events.count("orchestration"), 3)

    def test_deleted_second_task_does_not_commit(self):
        def decide(*args, **kwargs):
            self.replace("load_pipeline_task", lambda _: None)
            return {"action": "go"}
        self.replace("agent_pipeline_decide", decide)
        self.run_task()
        self.assertFalse(any(isinstance(item, tuple) and item[0] == "commit" for item in self.events))
        self.assertFalse(self.inflight)

    def test_advance_failure_keeps_saved_effect_and_stops_later_advances(self):
        def commit(task, config, user, message, decision, trigger, *, pending_advances):
            pending_advances.extend(["first", "second", "third"])
        self.replace("commit_pipeline_agent_turn", commit)
        def advance(task_id, user):
            self.events.append(("advance", task_id))
            if task_id == "second": raise RuntimeError("advance")
        self.replace("schedule_pipeline_advance", advance)
        self.run_task()
        self.assertIn(("save", {"auto_steps": 2, "last_auto_signature": "sig", "last_auto_step_at": 123}), self.events)
        self.assertIn(("advance", "first"), self.events)
        self.assertIn(("advance", "second"), self.events)
        self.assertNotIn(("advance", "third"), self.events)
        self.assertEqual(self.events[-3:], [("traceback", {"file": "stderr"}),
                                         ("registry-lock", "enter"), ("registry-lock", "exit")])
        self.assertFalse(self.inflight)

    def test_pause_arguments_and_append_failure_partial_effect(self):
        self.task["orchestration"]["auto_steps"] = 3
        self.run_task()
        pause = next(item for item in self.events if isinstance(item, tuple) and item[0] == "pause")
        self.assertIs(pause[1][0], self.task)
        self.assertIs(pause[1][1], self.task["orchestration"])
        self.assertEqual(pause[2], {"stage": "training", "reason": "自动编排已达到步数上限，请人工确认后再继续。",
                                    "suggested_actions": ["continue_training", "replan", "cancel"]})
        conversation = next(item for item in self.events if isinstance(item, tuple) and item[0] == "conversation")
        self.assertEqual(conversation[1][1:], ("agent", "自动编排步数已达上限，已暂停等待人工确认。"))
        self.assertEqual(conversation[2], {"action": "pause_and_ask", "source": "rules", "needs_user": True})
        self.inflight.add("task")
        self.task["orchestration"].pop("last_auto_signature")
        self.replace("agent_mcp_append_conversation", Mock(side_effect=ValueError("append")))
        self.events.clear()
        self.run_task()
        self.assertEqual(self.task["orchestration"]["last_auto_signature"], "sig")
        self.assertTrue(any(isinstance(item, tuple) and item[0] == "pause" for item in self.events))
        self.assertFalse(any(isinstance(item, tuple) and item[0] == "save" for item in self.events))
        self.assertIn(("traceback", {"file": "stderr"}), self.events)
        self.assertFalse(self.inflight)

    def test_second_lock_uses_first_signature_and_does_not_recheck_max(self):
        signature = Mock(return_value="original")
        self.replace("pipeline_task_decision_signature", signature)
        live = {"id": "replacement", "stage": "training", "orchestration": {"auto_steps": 999}}
        class SecondLock:
            def __enter__(inner): self.events.append("second-enter")
            def __exit__(inner, *_): self.events.append("second-exit")
        def decide(*args, **kwargs):
            self.replace("load_pipeline_task", lambda _: self.events.append("rebound-load") or live)
            self.replace("_pipeline_tasks_lock", SecondLock())
            self.replace("AGENT_MCP_AUTO_MAX_STEPS", 0)
            return {"action": "go"}
        self.replace("agent_pipeline_decide", decide)
        self.run_task()
        signature.assert_called_once_with(self.task)
        self.assertEqual(live["orchestration"]["last_auto_signature"], "original")
        self.assertEqual(live["orchestration"]["auto_steps"], 1000)
        section = self.events[self.events.index("second-enter"):self.events.index("second-exit") + 1]
        self.assertEqual(section[:3], ["second-enter", "rebound-load", ("needs", "replacement")])
        self.assertIn("commit", [item[0] if isinstance(item, tuple) else item for item in section])
        self.assertFalse(any(isinstance(item, tuple) and item[0] == "pause" for item in section))

    def test_clock_failure_keeps_committed_partial_mutation(self):
        self.replace("agent_mcp_now", Mock(side_effect=OverflowError("clock")))
        self.run_task()
        self.assertEqual(self.task["orchestration"]["last_auto_signature"], "sig")
        self.assertEqual(self.task["orchestration"]["auto_steps"], 2)
        self.assertNotIn("last_auto_step_at", self.task["orchestration"])
        self.assertFalse(any(isinstance(item, tuple) and item[0] == "save" for item in self.events))
        self.assertIn(("traceback", {"file": "stderr"}), self.events)
        self.assertFalse(self.inflight)

    def test_later_advance_callback_is_resolved_after_first(self):
        def rebound(task_id, user): self.events.append(("rebound-advance", task_id))
        def first(task_id, user):
            self.events.append(("first-advance", task_id))
            self.replace("schedule_pipeline_advance", rebound)
        self.replace("schedule_pipeline_advance", first)
        self.replace("commit_pipeline_agent_turn", lambda *args, **kwargs: kwargs["pending_advances"].extend(["a", "b"]))
        self.run_task()
        self.assertIn(("first-advance", "a"), self.events)
        self.assertIn(("rebound-advance", "b"), self.events)
        self.assertFalse(self.inflight)

    def test_decision_failure_swallowed_then_context_reset_and_registry_discard(self):
        self.replace("agent_pipeline_decide", Mock(side_effect=ValueError("decision")))
        self.run_task({"id": "u"})
        self.assertEqual(self.events[-4:], [("traceback", {"file": "stderr"}), ("reset", "token"),
                         ("registry-lock", "enter"), ("registry-lock", "exit")])
        self.assertFalse(self.inflight)

    def test_reset_failure_keeps_registry(self):
        class Identity:
            def set(self, user): return "token"
            def reset(self, token): raise RuntimeError("reset")
        self.replace("_request_user", Identity())
        with self.assertRaisesRegex(RuntimeError, "reset"):
            self.run_task({"id": "u"})
        self.assertEqual(self.inflight, {"task"})

    def test_schedule_duplicate_and_failed_start(self):
        self.inflight.clear()
        made = []
        class Thread:
            def __init__(self, **kwargs): made.append(kwargs)
            def start(self): pass
        self.replace("threading", types.SimpleNamespace(Thread=Thread))
        user = {"id": "u"}
        self.api.schedule_pipeline_auto_agent(["", "a", "a", "b"], user)
        self.assertEqual(len(made), 2)
        self.assertIs(made[0]["target"], self.api._run_pipeline_auto_agent_step)
        self.assertEqual(made[0]["args"], ("a", user))
        self.assertIs(made[0]["daemon"], True)
        self.assertEqual(self.inflight, {"a", "b"})
        self.inflight.clear()
        class FailThread:
            def __init__(self, **kwargs): pass
            def start(self): raise RuntimeError("start")
        self.replace("threading", types.SimpleNamespace(Thread=FailThread))
        with self.assertRaisesRegex(RuntimeError, "start"):
            self.api.schedule_pipeline_auto_agent(["c"], None)
        self.assertEqual(self.inflight, {"c"})


    def test_scheduler_rebinds_decorated_root_between_items(self):
        self.inflight.clear()
        targets = []
        def replacement(*_): pass
        class Thread:
            def __init__(inner, **kwargs): targets.append(kwargs["target"])
            def start(inner):
                if len(targets) == 1:
                    self.replace("_run_pipeline_auto_agent_step", replacement)
        self.replace("threading", types.SimpleNamespace(Thread=Thread))
        first = self.api._run_pipeline_auto_agent_step
        self.api.schedule_pipeline_auto_agent(["first", "second"], None)
        self.assertEqual(targets, [first, replacement])
        self.assertEqual(self.inflight, {"first", "second"})

    def test_decorated_root_binds_model_before_identity(self):
        if os.environ.get("VANTALINE_AUTO_AGENT_RUNTIME_BASELINE_SOURCE"):
            self.skipTest("original AST strips model decorator")
        events = self.events
        class Scope:
            def __enter__(self): events.append("scope-enter")
            def __exit__(self, *_): events.append("scope-exit")
        class Service:
            def current_snapshot(self): events.append("snapshot"); return {"model": "bound"}
            def scope(self, snapshot): events.append(("scope", snapshot)); return Scope()
        self.replace("model_profile_service", Service())
        self.api._run_pipeline_auto_agent_step("task", {"id": "u"})
        self.assertEqual(events[:4], [("load", "task"), "snapshot", ("scope", {"model": "bound"}), "scope-enter"])
        self.assertEqual(events[4][0], "set")
        self.assertEqual(events[-1], "scope-exit")
        self.assertEqual(events.count(("load", "task")), 3)

    def test_model_binding_failure_keeps_registry(self):
        if os.environ.get("VANTALINE_AUTO_AGENT_RUNTIME_BASELINE_SOURCE"):
            self.skipTest("original AST strips model decorator")
        self.replace("model_profile_service", None)
        with self.assertRaises(Exception):
            self.api._run_pipeline_auto_agent_step("task", {"id": "u"})
        self.assertEqual(self.events, [])
        self.assertEqual(self.inflight, {"task"})

    def test_independent_auto_agent_instances_a_b_a(self):
        if os.environ.get("VANTALINE_AUTO_AGENT_RUNTIME_BASELINE_SOURCE"):
            self.skipTest("candidate-only runtime isolation")
        from local_inspection_service.pipeline.auto_agent_runtime import PipelineAutoAgentRuntime
        from local_inspection_service.pipeline.auto_agent_runtime_ports import (
            AutoAgentTasks, AutoAgentDecision, AutoAgentExecution, AutoAgentScheduling,
        )
        reads = {"a": [], "b": []}
        effects = {"a": [], "b": []}
        class Lock:
            def __enter__(self): pass
            def __exit__(self, *_): pass
        def make(label):
            record = {"id": label, "stage": "training", "orchestration": {"auto_steps": 1}}
            inflight = {"task"}
            def get(name, value):
                def resolve(): reads[label].append(name); return value
                return resolve
            class Identity:
                def set(self, user): effects[label].append("set"); return "token"
                def reset(self, token): effects[label].append("reset")
            class Thread:
                def __init__(self, **kwargs): effects[label].append(("thread", kwargs["args"], kwargs["daemon"]))
                def start(self): effects[label].append("start")
            def commit(task, config, user, message, decision, trigger, *, pending_advances):
                effects[label].append("commit")
                pending_advances.append(label)
            runtime = PipelineAutoAgentRuntime(
                AutoAgentTasks(get("task_lock", Lock()), get("load", lambda _: record),
                               get("needs", lambda _: True), get("orchestration", lambda task: task["orchestration"]),
                               get("signature", lambda _: label), get("max_steps", 5),
                               get("pause", lambda *_args, **_kw: effects[label].append("pause")),
                               get("append", lambda *_args, **_kw: effects[label].append("append")),
                               get("save", lambda _: effects[label].append("save")), get("deepcopy", copy.deepcopy)),
                AutoAgentDecision(get("scope_config", lambda config, user: config),
                                  get("load_config", lambda: {}), get("decide", lambda *_args, **_kw: {}),
                                  get("commit", commit), get("now", lambda: 7),
                                  get("schedule_advance", lambda task_id, user: effects[label].append(("advance", task_id)))),
                AutoAgentExecution(get("identity", Identity()),
                                   get("traceback", lambda **_kw: effects[label].append("error")),
                                   get("stderr", "stderr")),
                AutoAgentScheduling(get("registry_lock", Lock()), get("inflight", inflight),
                                    get("thread", Thread), get("runner", lambda *_: None)),
            )
            return runtime, record, inflight
        a, a_record, a_inflight = make("a")
        b, b_record, b_inflight = make("b")
        self.assertEqual(reads, {"a": [], "b": []})
        a.run("task", {"id": "a"})
        b.run("task", {"id": "b"})
        a_record["orchestration"].pop("last_auto_signature")
        a.run("task", {"id": "a"})
        b_record["orchestration"].pop("last_auto_signature")
        b_record["orchestration"]["auto_steps"] = 5
        b.run("task", {"id": "b"})
        b_record["orchestration"].pop("last_auto_signature")
        b_record["orchestration"]["auto_steps"] = "invalid"
        b.run("task", {"id": "b"})
        a.schedule(["again"], None)
        b.schedule(["other"], None)
        self.assertEqual(effects["a"].count("commit"), 2)
        self.assertEqual(effects["b"].count("commit"), 1)
        self.assertIn("pause", effects["b"])
        self.assertIn("append", effects["b"])
        self.assertIn("error", effects["b"])
        self.assertIn(("advance", "a"), effects["a"])
        self.assertIn(("advance", "b"), effects["b"])
        self.assertEqual(a_inflight, {"again"})
        self.assertEqual(b_inflight, {"other"})
        all_getters = {"task_lock", "load", "needs", "orchestration", "signature", "max_steps", "pause",
                       "append", "save", "deepcopy", "scope_config", "load_config", "decide", "commit",
                       "now", "schedule_advance", "identity", "traceback", "stderr", "registry_lock",
                       "inflight", "thread", "runner"}
        self.assertLessEqual(all_getters - {"pause", "append", "traceback", "stderr"}, set(reads["a"]))
        self.assertLessEqual(all_getters, set(reads["b"]))


if __name__ == "__main__":
    unittest.main()
