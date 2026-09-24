"""Accepted-main versus candidate contract for pipeline advance background runtime."""
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
NAMES = {"advance_pipeline_task_guarded", "_run_pipeline_advance",
         "schedule_pipeline_advance", "cancel_pipeline_advance"}


class Cancelled(Exception): pass
class HttpError(Exception):
    def __init__(self, detail): self.detail = detail


class AdvanceRuntimeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        root = Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix="pipeline-advance-runtime-")))
        (root / "local_inspection_service/static").mkdir(parents=True)
        for key in ("DATABASE_URL", "VANTALINE_POSTGRES_DSN", "PGDSN"):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE="json",
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false",
                          YOLO_AUTOINSTALL="false")
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            cls.lifetime.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))
        baseline = os.environ.get("VANTALINE_ADVANCE_RUNTIME_BASELINE_SOURCE")
        if baseline:
            tree = ast.parse(Path(baseline).read_text(encoding="utf-8"))
            functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
            assert {node.name for node in functions} == NAMES
            for node in functions: node.decorator_list = []
            cls.api = types.ModuleType("accepted_main_advance_runtime")
            import traceback, time
            cls.api.__dict__.update(Any=object, copy=copy, threading=threading, sys=sys,
                                    traceback=traceback, time=time)
            exec(compile(ast.Module(body=functions, type_ignores=[]), baseline, "exec"), cls.api.__dict__)
        else:
            from local_inspection_service import server
            cls.api = server

    @classmethod
    def tearDownClass(cls): cls.lifetime.close()

    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.events = []
        self.task = {"id": "task", "stage": "samples", "status": "running", "auto_advance": True}
        self.inflight = {"task"}
        self.cancel = {}
        events = self.events
        class Lock:
            def __init__(self, name): self.name = name
            def __enter__(self): events.append((self.name, "enter"))
            def __exit__(self, *_): events.append((self.name, "exit"))
        self.task_lock = Lock("task-lock")
        self.registry_lock = Lock("registry-lock")
        self.replace("_pipeline_tasks_lock", self.task_lock)
        self.replace("_pipeline_advance_registry_lock", self.registry_lock)
        self.replace("_pipeline_advance_inflight", self.inflight)
        self.replace("_pipeline_advance_cancel", self.cancel)
        self.replace("load_pipeline_task", lambda key: events.append(("load", key)) or self.task)
        self.replace("sync_pipeline_task", lambda task: events.append(("sync", task["id"])))
        self.replace("save_pipeline_task", lambda task: events.append(("save", task.copy())))
        self.replace("load_config", lambda: events.append("config-load") or {"base": True})
        self.replace("scope_config_for_user", lambda config, user: events.append(("config-scope", config, user)) or {"scoped": True})
        self.real_guard = self.api.advance_pipeline_task_guarded
        self.replace("advance_pipeline_task_guarded", lambda snapshot, config, event: events.append(("guarded", snapshot, config, event)))
        self.replace("PipelineAdvanceCancelled", Cancelled)
        self.replace("HTTPException", HttpError)
        self.replace("agent_mcp_orchestration", lambda task: events.append("orchestration") or {"active_stage": "pose"})
        self.replace("pause_agent_mcp_task", lambda *args, **kwargs: events.append(("pause", args, kwargs)))
        self.replace("bounded_text", lambda text, limit: events.append(("bounded", text, limit)) or "bounded")
        self.replace("advance_pipeline_task", lambda task, **kw: events.append(("advance-stage", task, kw)))
        self.replace("print", lambda *args, **kw: events.append(("print", args, kw)))
        self.replace("time", types.SimpleNamespace(time=lambda: events.append("time") or 100))
        self.replace("copy", types.SimpleNamespace(deepcopy=copy.deepcopy))
        self.replace("traceback", types.SimpleNamespace(print_exc=lambda **kw: events.append(("traceback", kw))))
        self.replace("sys", types.SimpleNamespace(stderr="stderr"))
        class Identity:
            def set(self, user): events.append(("set", user)); return "token"
            def reset(self, token): events.append(("reset", token))
        self.replace("_request_user", Identity())
        class Event:
            def __init__(self): self.signalled = False; events.append("event-new")
            def set(self): self.signalled = True; events.append("event-set")
            def is_set(self): events.append("event-is-set"); return self.signalled
        self.Event = Event
        class Thread:
            def __init__(self, **kw): events.append(("thread", kw))
            def start(self): events.append("thread-start")
        self.replace("threading", types.SimpleNamespace(Event=Event, Thread=Thread))

    def replace(self, name, value):
        self.stack.enter_context(patch.object(self.api, name, value, create=True)); return value

    def runner(self, user=None):
        fn = self.api._run_pipeline_advance
        if not os.environ.get("VANTALINE_ADVANCE_RUNTIME_BASELINE_SOURCE"): fn = fn.__wrapped__
        fn("task", user)

    def test_guard_sync_then_advance(self):
        self.real_guard(self.task, {"x": 1})
        self.assertEqual(self.events[:2], [("sync", "task"), ("advance-stage", self.task, {"cancel_event": None})])

    def test_guard_cancel_rethrows_and_http_pauses(self):
        self.replace("advance_pipeline_task", Mock(side_effect=Cancelled()))
        with self.assertRaises(Cancelled):
            self.real_guard(self.task, {}, self.Event())
        self.assertFalse(any(isinstance(x, tuple) and x[0] == "pause" for x in self.events))
        self.replace("advance_pipeline_task", Mock(side_effect=HttpError("detail")))
        self.real_guard(self.task, {})
        pause = next(x for x in self.events if isinstance(x, tuple) and x[0] == "pause")
        self.assertIs(pause[1][0], self.task)
        self.assertEqual(pause[2], {"stage": "pose", "reason": "bounded",
                                     "suggested_actions": ["retry_pose_image_generation", "replan", "cancel"]})
        self.assertIn(("bounded", "detail", 240), self.events)

    def test_runner_success_snapshot_then_final_writeback(self):
        event = self.Event(); self.cancel["task"] = event
        user = {"id": "u"}
        self.runner(user)
        names = [x[0] if isinstance(x, tuple) else x for x in self.events]
        self.assertEqual(names.count("sync"), 1)  # guarded callback is substituted here
        self.assertLess(names.index("save"), names.index("config-load"))
        self.assertLess(names.index("config-load"), names.index("guarded"))
        self.assertLess(names.index("guarded"), names.index("event-is-set"))
        self.assertEqual(names.count("save"), 2)
        self.assertEqual(self.task["advance_started_at"] if "advance_started_at" in self.task else None, None)
        self.assertNotIn("advancing", self.task)
        self.assertFalse(self.inflight)
        self.assertFalse(self.cancel)
        self.assertIn(("reset", "token"), self.events)

    def test_runner_missing_first_task_cleans_registry(self):
        self.replace("load_pipeline_task", lambda _: None)
        self.runner()
        self.assertFalse(self.inflight)
        self.assertFalse(self.cancel)
        self.assertFalse(any(isinstance(x, tuple) and x[0] == "save" for x in self.events))

    def test_runner_cancelled_mid_advance_updates_stored(self):
        self.cancel["task"] = self.Event()
        self.replace("advance_pipeline_task_guarded", Mock(side_effect=Cancelled()))
        self.runner()
        self.assertFalse(self.task["auto_advance"])
        self.assertEqual(self.task["job_note"], "已暂停，自动推进已关闭。")
        self.assertEqual(self.task["last_error"], "")
        self.assertNotIn("advancing", self.task)
        self.assertTrue(any(isinstance(x, tuple) and x[0] == "print" for x in self.events))
        self.assertFalse(self.inflight)
        self.assertFalse(self.cancel)

    def test_runner_failure_records_error_and_clears_flags(self):
        self.replace("advance_pipeline_task_guarded", Mock(side_effect=ValueError("failed")))
        self.runner()
        self.assertEqual(self.task["last_error"], "推进任务时发生内部错误，请稍后重试。")
        self.assertNotIn("advancing", self.task)
        self.assertEqual(sum(1 for x in self.events if isinstance(x, tuple) and x[0] == "traceback"), 1)
        self.assertFalse(self.inflight)

    def test_runner_completed_step_with_cancel_signal_pauses(self):
        event = self.Event(); event.signalled = True; self.cancel["task"] = event
        self.runner()
        self.assertFalse(self.task["auto_advance"])
        self.assertEqual(self.task["job_note"], "已在当前步骤完成后暂停，自动推进已关闭。")
        self.assertEqual(self.task["last_error"], "")

    def test_guard_sync_runs_again_on_snapshot_outside_task_lock(self):
        self.replace("advance_pipeline_task_guarded", self.real_guard)
        self.runner()
        syncs = [x for x in self.events if isinstance(x, tuple) and x[0] == "sync"]
        self.assertEqual(syncs, [("sync", "task"), ("sync", "task")])
        names = [x[0] if isinstance(x, tuple) else x for x in self.events]
        first_enter = self.events.index(("task-lock", "enter"))
        first_exit = self.events.index(("task-lock", "exit"))
        second_enter = self.events.index(("task-lock", "enter"), first_exit + 1)
        sync_indexes = [i for i, item in enumerate(self.events) if isinstance(item, tuple) and item[0] == "sync"]
        self.assertTrue(first_enter < sync_indexes[0] < first_exit < sync_indexes[1] < second_enter)
        self.assertEqual(names.count("advance-stage"), 1)

    def test_fallback_event_is_not_written_into_cancel_mapping(self):
        observed = []
        self.replace("advance_pipeline_task_guarded", lambda snapshot, config, event:
                     observed.append((event, dict(self.cancel))))
        self.runner()
        self.assertEqual(len(observed), 1)
        self.assertIsInstance(observed[0][0], self.Event)
        self.assertEqual(observed[0][1], {})
        self.assertEqual(self.events.count("event-new"), 1)

    def test_deleted_before_final_writeback_drops_snapshot(self):
        def guarded(snapshot, config, event):
            self.replace("load_pipeline_task", lambda _: None)
            snapshot["result"] = "finished"
        self.replace("advance_pipeline_task_guarded", guarded)
        self.runner()
        self.assertNotIn("result", self.task)
        self.assertEqual(sum(1 for x in self.events if isinstance(x, tuple) and x[0] == "save"), 1)
        self.assertFalse(self.inflight)

    def test_final_writeback_keeps_object_identity_but_replaces_concurrent_fields(self):
        original = self.task
        def guarded(snapshot, config, event):
            original["concurrent"] = "later"
            snapshot["result"] = "finished"
        self.replace("advance_pipeline_task_guarded", guarded)
        self.runner()
        self.assertIs(self.task, original)
        self.assertNotIn("concurrent", original)
        self.assertEqual(original["result"], "finished")
        self.assertNotIn("advancing", original)

    def test_mid_advance_cancel_preserves_status_distinctions(self):
        self.replace("advance_pipeline_task_guarded", Mock(side_effect=Cancelled()))
        self.task["stage"] = "draft"; self.task.pop("status")
        self.runner()
        self.assertEqual(self.task["status"], "stopped")
        self.inflight.add("task")
        self.task["stage"] = "samples"; self.task["status"] = None
        self.runner()
        self.assertIsNone(self.task["status"])
        self.inflight.add("task")
        self.task.pop("status")
        self.runner()
        self.assertEqual(self.task["status"], "stopped")

    def test_config_scope_callee_selected_before_loader_rebind(self):
        self.replace("scope_config_for_user", lambda config, user: self.events.append("old-scope") or config)
        def load():
            self.replace("scope_config_for_user", lambda *_: self.events.append("new-scope") or {})
            return {"base": True}
        self.replace("load_config", load)
        self.runner()
        self.assertIn("old-scope", self.events)
        self.assertNotIn("new-scope", self.events)

    def test_event_and_thread_failures_keep_original_registry_partial_effects(self):
        self.inflight.clear()
        class EventFails:
            def __init__(self): raise RuntimeError("event")
        self.replace("threading", types.SimpleNamespace(Event=EventFails, Thread=object))
        with self.assertRaisesRegex(RuntimeError, "event"):
            self.api.schedule_pipeline_advance("a", None)
        self.assertEqual(self.inflight, {"a"})
        self.assertEqual(self.cancel, {})
        self.inflight.clear()
        class ThreadFails:
            def __init__(self, **kw): raise RuntimeError("thread")
        self.replace("threading", types.SimpleNamespace(Event=self.Event, Thread=ThreadFails))
        with self.assertRaisesRegex(RuntimeError, "thread"):
            self.api.schedule_pipeline_advance("b", None)
        self.assertEqual(self.inflight, {"b"})
        self.assertIsInstance(self.cancel["b"], self.Event)
        self.inflight.clear(); self.cancel.clear()
        class StartFails:
            def __init__(self, **kw): pass
            def start(self): raise RuntimeError("start")
        self.replace("threading", types.SimpleNamespace(Event=self.Event, Thread=StartFails))
        with self.assertRaisesRegex(RuntimeError, "start"):
            self.api.schedule_pipeline_advance("c", None)
        self.assertEqual(self.inflight, {"c"})
        self.assertIsInstance(self.cancel["c"], self.Event)

    def test_event_constructor_rebinds_mapping_before_subscript_assignment(self):
        self.inflight.clear()
        original = self.cancel
        rebound = {}
        contract = self
        class EventRebind:
            def __init__(self): contract.replace("_pipeline_advance_cancel", rebound)
            def set(self): pass
            def is_set(self): return False
        class Thread:
            def __init__(self, **kw): pass
            def start(self): pass
        self.replace("threading", types.SimpleNamespace(Event=EventRebind, Thread=Thread))
        self.assertTrue(self.api.schedule_pipeline_advance("late", None))
        self.assertEqual(original, {})
        self.assertIn("late", rebound)
        self.assertIsInstance(rebound["late"], EventRebind)

    def test_guard_exception_type_resolves_after_sync_rebind(self):
        class NewCancelled(HttpError): pass
        exact = NewCancelled("same")
        def sync(task):
            self.replace("PipelineAdvanceCancelled", NewCancelled)
        self.replace("sync_pipeline_task", sync)
        self.replace("advance_pipeline_task", Mock(side_effect=exact))
        with self.assertRaises(NewCancelled) as caught:
            self.real_guard(self.task, {})
        self.assertIs(caught.exception, exact)
        self.assertFalse(any(isinstance(item, tuple) and item[0] == "pause" for item in self.events))

    def test_identity_reset_failure_prevents_registry_cleanup(self):
        class Identity:
            def set(self, user): return "token"
            def reset(self, token): raise RuntimeError("reset")
        self.replace("_request_user", Identity())
        self.cancel["task"] = self.Event()
        with self.assertRaisesRegex(RuntimeError, "reset"):
            self.runner({"id": "u"})
        self.assertEqual(self.inflight, {"task"})
        self.assertIn("task", self.cancel)

    def test_schedule_and_cancel_registry_semantics(self):
        self.inflight.clear()
        self.assertFalse(self.api.schedule_pipeline_advance("", None))
        self.assertTrue(self.api.schedule_pipeline_advance("a", {"id": "u"}))
        self.assertFalse(self.api.schedule_pipeline_advance("a", None))
        self.assertIn("a", self.inflight)
        self.assertIn("a", self.cancel)
        self.assertTrue(self.api.cancel_pipeline_advance("a"))
        self.assertTrue(self.cancel["a"].signalled)
        self.assertFalse(self.api.cancel_pipeline_advance(""))
        self.assertFalse(self.api.cancel_pipeline_advance("unknown"))

    def test_cancel_sets_event_even_when_not_inflight(self):
        self.cancel["a"] = self.Event()
        self.assertFalse(self.api.cancel_pipeline_advance("a"))
        self.assertTrue(self.cancel["a"].signalled)


    def test_guard_selects_pause_before_reason_callback_rebind(self):
        old_pause = Mock()
        new_pause = Mock()
        self.replace("pause_agent_mcp_task", old_pause)
        def bounded(detail, limit):
            self.replace("pause_agent_mcp_task", new_pause)
            return "bounded"
        self.replace("bounded_text", bounded)
        self.replace("advance_pipeline_task", Mock(side_effect=HttpError("detail")))
        self.real_guard(self.task, {})
        old_pause.assert_called_once()
        new_pause.assert_not_called()

    def test_first_save_failure_keeps_advancing_partial_state(self):
        self.replace("save_pipeline_task", Mock(side_effect=RuntimeError("save")))
        self.runner()
        self.assertTrue(self.task["advancing"])
        self.assertEqual(self.task["advance_started_at"], 100)
        self.assertNotIn("last_error", self.task)
        self.assertIn(("traceback", {"file": "stderr"}), self.events)
        self.assertFalse(self.inflight)

    def test_scheduler_resolves_root_target_after_previous_thread_start(self):
        self.inflight.clear(); self.cancel.clear()
        targets = []
        def rebound(*_): pass
        class Thread:
            def __init__(inner, **kw): targets.append(kw["target"])
            def start(inner):
                if len(targets) == 1:
                    self.replace("_run_pipeline_advance", rebound)
        self.replace("threading", types.SimpleNamespace(Event=self.Event, Thread=Thread))
        first = self.api._run_pipeline_advance
        self.assertTrue(self.api.schedule_pipeline_advance("a", None))
        self.assertTrue(self.api.schedule_pipeline_advance("b", None))
        self.assertEqual(targets, [first, rebound])

    def test_decorated_root_binds_model_before_identity(self):
        if os.environ.get("VANTALINE_ADVANCE_RUNTIME_BASELINE_SOURCE"):
            self.skipTest("original AST strips model decorator")
        events = self.events
        class Scope:
            def __enter__(self): events.append("scope-enter")
            def __exit__(self, *_): events.append("scope-exit")
        class Service:
            def current_snapshot(self): events.append("snapshot"); return {"model": "bound"}
            def scope(self, snapshot): events.append(("scope", snapshot)); return Scope()
        self.replace("model_profile_service", Service())
        self.api._run_pipeline_advance("task", {"id": "u"})
        self.assertEqual(events[:4], [("load", "task"), "snapshot", ("scope", {"model": "bound"}), "scope-enter"])
        self.assertEqual(events[4][0], "set")
        self.assertEqual(events[-1], "scope-exit")
        self.assertEqual(events.count(("load", "task")), 3)

    def test_model_binding_failure_does_not_clear_registry(self):
        if os.environ.get("VANTALINE_ADVANCE_RUNTIME_BASELINE_SOURCE"):
            self.skipTest("original AST strips model decorator")
        self.replace("model_profile_service", None)
        with self.assertRaises(Exception):
            self.api._run_pipeline_advance("task", {"id": "u"})
        self.assertEqual(self.events, [])
        self.assertEqual(self.inflight, {"task"})

    def test_independent_advance_instances_a_b_a(self):
        if os.environ.get("VANTALINE_ADVANCE_RUNTIME_BASELINE_SOURCE"):
            self.skipTest("candidate-only runtime isolation")
        from local_inspection_service.pipeline.advance_runtime import PipelineAdvanceRuntime
        from local_inspection_service.pipeline.advance_runtime_ports import (
            AdvanceTasks, AdvancePolicy, AdvanceExecution, AdvanceScheduling,
        )
        from typing import get_type_hints
        self.assertIn("cancel_event", get_type_hints(PipelineAdvanceRuntime.guarded))
        reads = {"a": [], "b": []}; effects = {"a": [], "b": []}
        class Lock:
            def __enter__(self): pass
            def __exit__(self, *_): pass
        def make(label):
            record = {"id": label, "stage": "samples", "status": "running"}
            inflight = {"task"}; cancel = {}; behavior = {"guarded": "ok", "advance": "ok"}
            def get(name, value):
                def resolve(): reads[label].append(name); return value
                return resolve
            class Identity:
                def set(self, user): effects[label].append("set"); return "token"
                def reset(self, token): effects[label].append("reset")
            class Event:
                def __init__(self): self.signalled = False
                def set(self): self.signalled = True
                def is_set(self): return self.signalled
            class Thread:
                def __init__(self, **kw): effects[label].append(("thread", kw["args"], kw["daemon"]))
                def start(self): effects[label].append("start")
            def guarded(snapshot, config, event):
                if behavior["guarded"] == "cancel": raise Cancelled()
                if behavior["guarded"] == "error": raise ValueError("advance")
                snapshot["owner"] = label
            def advance(task, **kw):
                if behavior["advance"] == "http": raise HttpError("http")
                effects[label].append("advance")
            runtime = PipelineAdvanceRuntime(
                AdvanceTasks(get("task_lock", Lock()), get("load", lambda _: record),
                             get("sync", lambda _: effects[label].append("sync")),
                             get("save", lambda _: effects[label].append("save")), get("deepcopy", copy.deepcopy)),
                AdvancePolicy(get("advance", advance), get("guarded", guarded),
                              get("cancelled_error", Cancelled), get("http_error", HttpError),
                              get("orchestration", lambda _: {"active_stage": "pose"}),
                              get("pause", lambda *_args, **_kw: effects[label].append("pause")),
                              get("bounded_text", lambda detail, limit: str(detail))),
                AdvanceExecution(get("identity", Identity()), get("scope_config", lambda config, user: config),
                                 get("load_config", lambda: {}), get("clock", lambda: 100),
                                 get("traceback", lambda **_kw: effects[label].append("error")),
                                 get("stderr", "stderr"), get("print", lambda *_args, **_kw: effects[label].append("print"))),
                AdvanceScheduling(get("registry_lock", Lock()), get("inflight", inflight),
                                  get("cancel_events", cancel), get("event", Event), get("thread", Thread),
                                  get("runner", lambda *_: None)),
            )
            return runtime, record, inflight, cancel, behavior
        a, a_record, a_inflight, a_cancel, a_behavior = make("a")
        b, b_record, b_inflight, b_cancel, b_behavior = make("b")
        self.assertEqual(reads, {"a": [], "b": []})
        a.run("task", {"id": "a"})
        b.run("task", {"id": "b"})
        a.run("task", {"id": "a"})
        self.assertEqual(a_record["owner"], "a")
        self.assertEqual(b_record["owner"], "b")
        b_behavior["advance"] = "http"
        b.guarded(b_record, {}, None)
        b_behavior["guarded"] = "cancel"
        b.run("task", None)
        b_behavior["guarded"] = "error"
        b.run("task", None)
        a.schedule("again", None)
        b.schedule("other", None)
        self.assertTrue(b.cancel("other"))
        self.assertEqual(a_inflight, {"again"})
        self.assertEqual(b_inflight, {"other"})
        self.assertIn("pause", effects["b"])
        self.assertIn("print", effects["b"])
        self.assertIn("error", effects["b"])
        self.assertNotIn("pause", effects["a"])
        self.assertNotIn("error", effects["a"])
        all_getters = {"task_lock", "load", "sync", "save", "deepcopy", "advance", "guarded",
                       "cancelled_error", "http_error", "orchestration", "pause", "bounded_text",
                       "identity", "scope_config", "load_config", "clock", "traceback", "stderr", "print",
                       "registry_lock", "inflight", "cancel_events", "event", "thread", "runner"}
        self.assertLessEqual(all_getters - {"advance", "cancelled_error", "http_error", "orchestration",
                                            "pause", "bounded_text", "traceback", "stderr", "print"}, set(reads["a"]))
        self.assertLessEqual(all_getters, set(reads["b"]))


if __name__ == "__main__": unittest.main()
