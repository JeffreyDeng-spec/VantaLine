"""Offline contracts for AI detection task cards in the pipeline."""
from contextlib import ExitStack
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class PipelineAiTaskSyncContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack = ExitStack()
        cls.stack.enter_context(patch.dict(os.environ))
        cls.root = Path(cls.stack.enter_context(tempfile.TemporaryDirectory(prefix="pipeline-ai-sync-")))
        (cls.root / "local_inspection_service/static").mkdir(parents=True)
        for key in ("DATABASE_URL", "VANTALINE_POSTGRES_DSN", "PGDSN"):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(cls.root), VANTALINE_DATA_STORE="json",
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false",
                          YOLO_AUTOINSTALL="false")
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            cls.stack.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.stack.close()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.calls = []
        self.user = {"id": "owner"}
        self.ai = {"id": "ai-1", "name": "One", "selected_accessory_ids": ["part"],
                   "required_accessory_counts": {"part": 2}, "owner_user_id": "owner",
                   "owner_username": "Owner", "created_at": 11.9, "updated_at": 12.8}
        self.config = {"parts": True}
        self.items = {"part": {"id": "part", "material_type": "object", "training_role": ""},
                      "text": {"id": "text", "material_type": "text"},
                      "ocr": {"id": "ocr", "training_role": "detect_then_ocr"}}
        self.replace("PIPELINE_DASHBOARD_AI_TASK_SOURCE", new="pipeline-dashboard")
        self.replace("safe_record_id", side_effect=lambda x: self.calls.append(("safe", x)) or str(x))
        self.replace("sanitize_ai_detection_task_id", side_effect=lambda x: self.calls.append(("sanitize", x)) or str(x))
        self.replace("accessory_lookup_by_id", side_effect=lambda c: self.calls.append(("lookup", c)) or self.items)
        self.replace("canonical_pipeline_accessory_ids",
                     side_effect=lambda c, ids: self.calls.append(("canonical", tuple(ids))) or ids)
        self.replace("accessory_material_type", side_effect=lambda item: self.calls.append(("material", item["id"])) or item.get("material_type", "object"))
        self.replace("record_visible_to_user", side_effect=lambda item, user, target=None: self.calls.append(("visible", item["id"], target)) or item.get("owner_user_id") == "owner")
        self.replace("clean_ai_detection_task_name", side_effect=lambda name, fallback: self.calls.append(("name", name)) or str(name or fallback))
        self.replace("normalize_pipeline_accessory_counts", side_effect=lambda c, ids, counts: self.calls.append(("counts", tuple(ids))) or counts)
        self.replace("ai_detection_task_model_id", side_effect=lambda id: self.calls.append(("model", id)) or "model-" + id)
        self.replace("load_ai_detection_tasks", side_effect=lambda: self.calls.append(("load",)) or [self.ai])
        self.stack.enter_context(patch.object(self.api.time, "time", return_value=77.9))

    def replace(self, name, **kwargs):
        return self.stack.enter_context(patch.object(self.api, name, **kwargs))

    def sync(self, tasks=None, ai_tasks=None, use_default=False):
        tasks = [] if tasks is None else tasks
        if use_default:
            return tasks, self.api.sync_pipeline_ai_detection_tasks(tasks, self.config, self.user)
        return tasks, self.api.sync_pipeline_ai_detection_tasks(tasks, self.config, self.user, ai_tasks=[self.ai] if ai_tasks is None else ai_tasks)

    def test_id_order_and_route_types(self):
        self.assertEqual(self.api.pipeline_ai_task_id(" raw "), "pipe_ai_ raw ")
        self.assertEqual(self.calls[:2], [("sanitize", " raw "), ("safe", " raw ")])
        for selected, expected in ((["part"], "yolo"), (["text"], "yolo_ocr"), (["ocr"], "yolo_ocr")):
            self.ai["selected_accessory_ids"] = selected
            self.assertEqual(self.api.pipeline_ai_task_training_route(self.ai, self.config), expected)

    def test_new_card_exact_payload_and_existing_order(self):
        older = {"id": "older"}
        tasks, changed = self.sync([older])
        self.assertTrue(changed)
        self.assertIs(tasks[1], older)
        self.assertEqual(tasks[0], {
            "id": "pipe_ai_ai-1", "name": "One", "task_kind": "ai_optimization",
            "accessory_ids": ["part"], "accessory_counts": {"part": 2},
            "detection_method": "ai", "optimization_route": "yolo", "stage": "library",
            "status": "completed", "progress": 100,
            "params": {"route": "ai", "recommended_train_mode": "yolo"},
            "auto_advance": True, "ai_task_id": "ai-1", "ai_model_id": "model-ai-1",
            "linked_view": "aiInspect",
            "job_note": "AI 检测任务已纳入任务流水线，可持续采集数据并自动优化 YOLO。",
            "last_error": "", "created_at": 11, "updated_at": 12,
            "owner_user_id": "owner", "owner_username": "Owner", "shared_with_user_ids": []
        })

    def test_default_loader_and_supplied_empty_list(self):
        tasks, changed = self.sync(use_default=True)
        self.assertTrue(changed)
        self.assertIn(("load",), self.calls)
        self.calls.clear()
        tasks, changed = self.sync(ai_tasks=[])
        self.assertFalse(changed)
        self.assertEqual(tasks, [])
        self.assertNotIn(("load",), self.calls)

    def test_skip_source_visibility_empty_id_and_empty_accessories(self):
        entries = [dict(self.ai, source="pipeline-dashboard"), dict(self.ai, id="secret", owner_user_id="other"),
                   dict(self.ai, id=""), dict(self.ai, id="empty", selected_accessory_ids=[])]
        tasks, changed = self.sync(ai_tasks=entries)
        self.assertFalse(changed)
        self.assertEqual(tasks, [])
        self.assertEqual([x for x in self.calls if x[0] == "visible"], [("visible", "secret", None), ("visible", "", None), ("visible", "empty", None)])

    def test_existing_alias_and_preserved_fields(self):
        existing = {"id": "old-custom-id", "ai_task_id": "ai-1", "stage": "training",
                    "status": "running", "progress": 0, "auto_advance": False,
                    "pause_requested": False, "agent_mcp": {"keep": 1}, "datasets": [],
                    "candidate_models": ["x"], "other": "retained"}
        tasks = [existing]
        ref = tasks[0]
        got, changed = self.sync(tasks)
        self.assertIs(got[0], ref)
        self.assertTrue(changed)
        self.assertEqual(got[0]["id"], "pipe_ai_ai-1")
        self.assertEqual({k: got[0][k] for k in ("stage", "status", "progress", "auto_advance", "pause_requested", "agent_mcp", "datasets", "candidate_models", "other")},
                         {"stage": "training", "status": "running", "progress": 0, "auto_advance": True,
                          "pause_requested": False, "agent_mcp": {"keep": 1}, "datasets": [],
                          "candidate_models": ["x"], "other": "retained"})
        got2, changed2 = self.sync(tasks)
        self.assertIs(got2[0], ref)
        self.assertFalse(changed2)

    def test_stopped_and_paused_keep_auto_advance_off(self):
        for field in ({"status": "stopped"}, {"pause_requested": True}):
            old = {"id": "pipe_ai_ai-1", **field}
            tasks, changed = self.sync([old])
            self.assertTrue(changed)
            self.assertIs(tasks[0], old)
            self.assertFalse(old["auto_advance"])

    def test_timestamp_fallback_and_shared_list_alias(self):
        shares = ["second"]
        self.ai.update(created_at=0, updated_at=None, shared_with_user_ids=shares)
        tasks, changed = self.sync()
        self.assertTrue(changed)
        self.assertEqual((tasks[0]["created_at"], tasks[0]["updated_at"]), (77, 77))
        self.assertIs(tasks[0]["shared_with_user_ids"], shares)

    def test_duplicate_input_updates_first_card_and_keeps_second(self):
        first = {"id": "custom", "ai_task_id": "ai-1", "stage": "samples"}
        second = {"id": "pipe_ai_ai-1", "ai_task_id": "ai-1", "stage": "training"}
        tasks, changed = self.sync([first, second])
        self.assertTrue(changed)
        self.assertIs(tasks[0], first)
        self.assertIs(tasks[1], second)
        self.assertEqual((first["id"], first["stage"], second["id"], second["stage"]), ("custom", "samples", "pipe_ai_ai-1", "training"))

    def test_error_before_mutation_and_partial_mutation(self):
        self.ai["created_at"] = "bad-time"
        tasks = [{"id": "existing"}]
        before = copy.deepcopy(tasks)
        with self.assertRaises(ValueError):
            self.sync(tasks)
        self.assertEqual(tasks, before)
        good = dict(self.ai, created_at=1, id="good")
        bad = dict(self.ai, created_at="bad", id="bad")
        with self.assertRaises(ValueError):
            self.sync(tasks, ai_tasks=[good, bad])
        self.assertEqual([x["id"] for x in tasks], ["pipe_ai_good", "existing"])


    def test_new_cards_reverse_input_order_and_duplicate_source_updates(self):
        second = dict(self.ai, id="ai-2", name="Two")
        tasks, changed = self.sync(ai_tasks=[self.ai, second])
        self.assertTrue(changed)
        self.assertEqual([item["ai_task_id"] for item in tasks], ["ai-2", "ai-1"])
        self.assertEqual([item["name"] for item in tasks], ["Two", "One"])
        duplicate = dict(self.ai, name="Updated")
        same, updated = self.sync(tasks, ai_tasks=[duplicate])
        self.assertIs(same, tasks)
        self.assertTrue(updated)
        self.assertEqual(tasks[1]["name"], "Updated")

    def test_ai_task_id_precedes_pipeline_id_and_none_progress_survives(self):
        ai_match = {"id": "old", "ai_task_id": "ai-1", "progress": None,
                    "stage": "", "status": "", "params": {"previous": True}}
        id_match = {"id": "pipe_ai_ai-1", "ai_task_id": "other", "stage": "training"}
        id_match_before = copy.deepcopy(id_match)
        tasks, changed = self.sync([ai_match, id_match])
        self.assertTrue(changed)
        self.assertIs(tasks[0], ai_match)
        self.assertEqual(tasks[0]["id"], "pipe_ai_ai-1")
        self.assertEqual(tasks[0]["progress"], 100)
        self.assertEqual((tasks[0]["stage"], tasks[0]["status"]), ("library", "completed"))
        self.assertEqual(tasks[0]["params"], {"route": "ai", "recommended_train_mode": "yolo"})
        self.assertIs(tasks[1], id_match)
        self.assertEqual(tasks[1], id_match_before)

    def test_target_forwarding_short_circuit_and_route_canonical_twice(self):
        self.ai["selected_accessory_ids"] = ["text", "part"]
        user = {"id": "admin"}
        calls = []
        self.replace("record_visible_to_user", side_effect=lambda item, who, target:
                     calls.append((item["id"], who, target)) or True)
        tasks = []
        changed = self.api.sync_pipeline_ai_detection_tasks(
            tasks, self.config, user, "target", ai_tasks=[dict(self.ai, source="pipeline-dashboard"), self.ai])
        self.assertTrue(changed)
        self.assertEqual(calls, [("ai-1", user, "target")])
        self.assertEqual(tasks[0]["optimization_route"], "yolo_ocr")
        self.assertEqual(len([x for x in self.calls if x[0] == "canonical"]), 2)
        self.assertEqual([x for x in self.calls if x[0] == "material"], [("material", "text")])

    def test_safe_callee_is_selected_before_sanitize_and_existing_mutation_is_partial(self):
        events = []
        def safe(value):
            events.append(("call_safe", value))
            return value
        def sanitize(value):
            events.append(("sanitize", value))
            self.api.safe_record_id = lambda value: "late-" + value
            return value
        self.replace("safe_record_id", new=safe)
        self.replace("sanitize_ai_detection_task_id", new=sanitize)
        self.assertEqual(self.api.pipeline_ai_task_id("x"), "pipe_ai_x")
        self.assertEqual(events, [("sanitize", "x"), ("call_safe", "x")])
        self.api.safe_record_id = safe
        previous = {"id": "old", "ai_task_id": "ai-1", "stage": "training"}
        broken = dict(self.ai, id="broken", updated_at="bad")
        with self.assertRaises(ValueError):
            self.sync([previous], ai_tasks=[self.ai, broken])
        self.assertEqual(previous["id"], "pipe_ai_ai-1")
        self.assertEqual(previous["stage"], "training")


    def test_independent_sync_instances_use_only_their_ports(self):
        from local_inspection_service.pipeline.ai_task_sync import PipelineAiTaskSync
        from local_inspection_service.pipeline.ai_task_sync_ports import (
            PipelineAiAccess, PipelineAiAccessories, PipelineAiIdentity, PipelineAiProjection,
        )
        poison = Mock(side_effect=AssertionError("root dependency escape"))
        root_names = (
            "safe_record_id", "sanitize_ai_detection_task_id", "ai_detection_task_model_id",
            "accessory_lookup_by_id", "canonical_pipeline_accessory_ids",
            "accessory_material_type", "normalize_pipeline_accessory_counts",
            "record_visible_to_user", "load_ai_detection_tasks", "clean_ai_detection_task_name",
            "pipeline_ai_task_training_route", "pipeline_ai_task_id",
        )
        for name in root_names:
            self.replace(name, new=poison)
        events = []
        def make(label):
            record = dict(self.ai, id=label, name=label, owner_user_id=label)
            values = {
                "safe_record_id": lambda value: str(value),
                "sanitize_ai_detection_task_id": str,
                "ai_detection_task_model_id": lambda value: label + "-model-" + value,
                "accessory_lookup_by_id": lambda config: {"part": {"id": "part"}},
                "canonical_pipeline_accessory_ids": lambda config, ids: ids,
                "accessory_material_type": lambda item: "object",
                "normalize_pipeline_accessory_counts": lambda config, ids, counts: counts,
                "source": "dashboard",
                "record_visible_to_user": lambda record, user, target: record["owner_user_id"] == label,
                "load_ai_detection_tasks": lambda: [record],
                "clean_ai_detection_task_name": lambda name, fallback: name or fallback,
                "training_route": lambda record, config: label + "-route",
                "task_id": lambda value: "pipe_ai_" + value,
                "now": lambda: 42.5,
            }
            def getter(key):
                def get():
                    events.append((label, key))
                    return values[key]
                return get
            groups = (
                (PipelineAiIdentity, ("safe_record_id", "sanitize_ai_detection_task_id", "ai_detection_task_model_id")),
                (PipelineAiAccessories, ("accessory_lookup_by_id", "canonical_pipeline_accessory_ids",
                                         "accessory_material_type", "normalize_pipeline_accessory_counts")),
                (PipelineAiAccess, ("source", "record_visible_to_user", "load_ai_detection_tasks")),
                (PipelineAiProjection, ("clean_ai_detection_task_name", "training_route", "task_id", "now")),
            )
            service = PipelineAiTaskSync(*(kind(**{key: getter(key) for key in keys}) for kind, keys in groups))
            return service, values
        a = make("A")
        b = make("B")
        self.assertEqual(events, [])
        for label, (service, values) in (("A", a), ("B", b), ("A", a)):
            start = len(events)
            tasks = []
            self.assertEqual(service.pipeline_ai_task_id(label), "pipe_ai_" + label)
            self.assertEqual(service.pipeline_ai_task_training_route(
                {"selected_accessory_ids": ["part"]}, {}), "yolo")
            self.assertTrue(service.sync_pipeline_ai_detection_tasks(tasks, {}, {"id": label}))
            self.assertEqual(tasks[0]["name"], label)
            self.assertEqual(tasks[0]["ai_model_id"], label + "-model-" + label)
            self.assertEqual(tasks[0]["optimization_route"], label + "-route")
            self.assertEqual(tasks[0]["created_at"], 11)
            self.assertEqual({who for who, key in events[start:]}, {label})
            self.assertEqual({key for who, key in events[start:]}, set(values))
        poison.assert_not_called()

    def test_root_sync_reselects_route_and_id_wrappers(self):
        self.replace("pipeline_ai_task_training_route", return_value="late-route")
        self.replace("pipeline_ai_task_id", return_value="late-id")
        tasks, changed = self.sync()
        self.assertTrue(changed)
        self.assertEqual((tasks[0]["id"], tasks[0]["optimization_route"],
                          tasks[0]["params"]["recommended_train_mode"]), ("late-id", "late-route", "late-route"))


    def test_canonical_callee_selected_before_effectful_ids(self):
        events = []
        def original(config, ids):
            events.append(("original", ids))
            return ids
        def replacement(config, ids):
            raise AssertionError("late canonical binding used during this call")
        self.replace("canonical_pipeline_accessory_ids", new=original)
        class SelectedId:
            def __str__(inner):
                events.append(("stringify",))
                self.api.canonical_pipeline_accessory_ids = replacement
                return "part"
        self.ai["selected_accessory_ids"] = [SelectedId()]
        self.assertEqual(self.api.pipeline_ai_task_training_route(self.ai, self.config), "yolo")
        self.assertEqual(events, [("stringify",), ("original", ["part"])])

    def test_sync_refreshes_root_route_and_id_between_records(self):
        second = dict(self.ai, id="ai-2", name="Two")
        route_calls = []
        id_calls = []
        def first_route(record, config):
            route_calls.append(record["id"])
            self.api.pipeline_ai_task_training_route = lambda record, config: "late-route"
            return "first-route"
        def first_id(value):
            id_calls.append(value)
            self.api.pipeline_ai_task_id = lambda value: "late-" + value
            return "first-" + value
        self.replace("pipeline_ai_task_training_route", new=first_route)
        self.replace("pipeline_ai_task_id", new=first_id)
        tasks, changed = self.sync(ai_tasks=[self.ai, second])
        self.assertTrue(changed)
        self.assertEqual(route_calls, ["ai-1"])
        self.assertEqual(id_calls, ["ai-1"])
        self.assertEqual([(item["id"], item["optimization_route"]) for item in tasks],
                         [("late-ai-2", "late-route"), ("first-ai-1", "first-route")])

    def test_explicit_empty_still_reads_clock_and_visibility_error_keeps_prior_card(self):
        self.calls.clear()
        clock = self.api.time.time
        before = clock.call_count
        tasks, changed = self.sync(ai_tasks=[])
        self.assertFalse(changed)
        self.assertEqual(tasks, [])
        self.assertNotIn(("load",), self.calls)
        self.assertEqual(clock.call_count, before + 1)
        first = dict(self.ai, id="first")
        second = dict(self.ai, id="second")
        error = RuntimeError("synthetic visibility error")
        def visible(record, user, target):
            if record["id"] == "second":
                raise error
            return True
        self.replace("record_visible_to_user", side_effect=visible)
        tasks = []
        with self.assertRaises(RuntimeError) as raised:
            self.api.sync_pipeline_ai_detection_tasks(tasks, self.config, self.user, ai_tasks=[first, second])
        self.assertIs(raised.exception, error)
        self.assertEqual([task["ai_task_id"] for task in tasks], ["first"])


if __name__ == "__main__":
    unittest.main()
