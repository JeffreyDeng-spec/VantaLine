"""Dashboard task creation/update preserves original ordering and partial effects."""
import ast
import copy
from dataclasses import fields
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE = os.environ.get("VANTALINE_DASHBOARD_TASK_BASELINE_SOURCE")
NAME = "upsert_dashboard_ai_task"


def build(bindings):
    if BASELINE:
        fn = next(n for n in ast.parse(Path(BASELINE).read_text(encoding="utf-8-sig")).body
                  if isinstance(n, ast.FunctionDef) and n.name == NAME)
        namespace = dict(bindings, Any=object)
        exec(compile(ast.Module(body=[fn], type_ignores=[]), BASELINE, "exec"), namespace)
        return SimpleNamespace(**{NAME: namespace[NAME]}), namespace
    from local_inspection_service.detection.task_requests import DetectionTaskRequests
    from local_inspection_service.detection.task_request_ports import (
        TaskRequestAccess, TaskRequestPolicy, TaskRequestStore, TaskPipelineSync, TaskRequestClock,
    )
    def ports(cls):
        return cls(**{f.name: lambda name=f.name: bindings[name] for f in fields(cls)})
    return DetectionTaskRequests(*(ports(cls) for cls in
        (TaskRequestAccess, TaskRequestPolicy, TaskRequestStore, TaskPipelineSync, TaskRequestClock))), bindings


class DashboardTaskContract(unittest.TestCase):
    def setUp(self):
        self.tasks = []
        self.events = []
        self.saved = []
        self.config = {"fixture": True}
        self.catalog = {"a": {"name": "A"}, "b": {"name": ""}}
        def lookup(config):
            self.assertIs(config, self.config)
            self.events.append("catalog")
            return self.catalog
        def load():
            self.events.append("load")
            return self.tasks
        def save(task):
            self.events.append("save")
            self.saved.append(copy.deepcopy(task))
        def serialize(task, config):
            self.assertIs(config, self.config)
            self.events.append("serialize")
            return {"task": task}
        bindings = dict(accessory_lookup_by_id=lookup, load_ai_detection_tasks=load,
            save_ai_detection_task=save, serialize_ai_detection_task=serialize,
            DASHBOARD_AI_TASK_NAME="Dashboard", PIPELINE_DASHBOARD_AI_TASK_SOURCE="dashboard",
            time=SimpleNamespace(time=lambda: self.events.append("clock") or 123),
            uuid=SimpleNamespace(uuid4=lambda: self.events.append("uuid") or SimpleNamespace(hex="a"*32)),
            current_owner_fields=lambda: self.events.append("owner") or {"owner_user_id": "alice"})
        self.service, self.bindings = build(bindings)

    def invoke(self, identifier="a"):
        return self.service.upsert_dashboard_ai_task(identifier, self.config)

    def test_create_exact_payload_order_and_list_identity(self):
        result = self.invoke()["task"]
        self.assertIs(result, self.tasks[0])
        self.assertEqual(result, dict(id="aitask_aaaaaaaaaa", created_at=123, updated_at=123,
            owner_user_id="alice", name="Dashboard", selected_accessory_ids=["a"],
            required_accessory_counts={"a": 1}, accessory_labels={"a": "A"}, source="dashboard"))
        self.assertEqual(self.events, ["catalog", "load", "clock", "uuid", "owner", "save", "serialize"])

    def test_first_name_match_dedup_filter_counts_and_owner_retained(self):
        first = dict(id="first", name="Dashboard", source="workbench", created_at=7,
            owner_user_id="existing", selected_accessory_ids=["b", "gone", "a", "b"],
            required_accessory_counts={"a": 0, "b": "2"}, extra=True)
        second = dict(first, id="second")
        self.tasks.extend([first, second])
        result = self.invoke()["task"]
        self.assertIs(result, first)
        self.assertEqual(result["selected_accessory_ids"], ["b", "a"])
        self.assertEqual(result["required_accessory_counts"], {"b": 2, "a": 1})
        self.assertEqual(result["accessory_labels"], {"b": "b", "a": "A"})
        self.assertEqual((result["created_at"], result["owner_user_id"]), (7, "existing"))
        self.assertNotIn("updated_at", second)
        self.assertEqual(self.events, ["catalog", "load", "clock", "save", "serialize"])

    def test_unknown_accessory_still_saves_empty_task(self):
        self.assertEqual(self.invoke("missing")["task"]["selected_accessory_ids"], [])
        self.assertEqual(len(self.saved), 1)

    def test_bad_existing_counts_fail_before_mutation_and_clock(self):
        task = dict(name="Dashboard", selected_accessory_ids=["a"], required_accessory_counts={"a": "bad"})
        self.tasks.append(task)
        before = copy.deepcopy(task)
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual(task, before)
        self.assertEqual(self.events, ["catalog", "load"])

    def test_save_failure_retains_insert_or_update_without_projection(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                self.setUp()
                if existing:
                    self.tasks.append(dict(id="old", name="Dashboard", selected_accessory_ids=[]))
                sentinel = RuntimeError("save")
                def fail(task):
                    raise sentinel
                self.bindings["save_ai_detection_task"] = fail
                with self.assertRaises(RuntimeError) as caught:
                    self.invoke()
                self.assertIs(caught.exception, sentinel)
                self.assertEqual(self.tasks[0]["updated_at"], 123)
                self.assertEqual(self.tasks[0]["selected_accessory_ids"], ["a"])
                self.assertNotIn("serialize", self.events)

    def test_projection_failure_after_one_save_and_owner_overlay(self):
        self.bindings["current_owner_fields"] = lambda: {"id": "owner-id", "name": "ignored", "created_at": 5}
        self.bindings["serialize_ai_detection_task"] = lambda *_: (_ for _ in ()).throw(RuntimeError("projection"))
        with self.assertRaisesRegex(RuntimeError, "projection"):
            self.invoke()
        self.assertEqual(len(self.saved), 1)
        self.assertEqual((self.saved[0]["id"], self.saved[0]["name"], self.saved[0]["created_at"]),
                         ("owner-id", "Dashboard", 5))

    def test_clock_effect_changes_late_store_and_serializer(self):
        def clock():
            self.bindings["save_ai_detection_task"] = lambda task: self.events.append("late-save")
            self.bindings["serialize_ai_detection_task"] = lambda *_: "late-result"
            return 321
        self.bindings["time"] = SimpleNamespace(time=clock)
        self.assertEqual(self.invoke(), "late-result")
        self.assertEqual(self.tasks[0]["created_at"], 321)
        self.assertEqual(self.events[-1], "late-save")

    @unittest.skipIf(BASELINE, "candidate root owner binding")
    def test_actual_root_binding_and_independent_capabilities(self):
        tree = ast.parse(read_checked_application_source(ROOT / 'local_inspection_service/server.py'))
        alias = next(n for n in tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == NAME for t in n.targets))
        self.assertEqual(ast.unparse(alias.value), "_detection_task_requests.upsert_dashboard_ai_task")
        self.assertEqual(self.events, [])
        other, _ = build(dict(self.bindings, current_owner_fields=lambda: {"owner_user_id": "bob"},
                              load_ai_detection_tasks=lambda: []))
        self.assertEqual(other.upsert_dashboard_ai_task("a", self.config)["task"]["owner_user_id"], "bob")
        self.assertEqual(self.invoke()["task"]["owner_user_id"], "alice")


if __name__ == "__main__":
    unittest.main()
