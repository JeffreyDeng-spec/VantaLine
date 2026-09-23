"""Synthetic original contracts for pipeline task label and accessory snapshots."""
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class PipelineTaskSnapshotContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        root = Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix="pipeline-task-snapshots-")))
        (root / "local_inspection_service/static").mkdir(parents=True)
        for key in ("DATABASE_URL", "VANTALINE_POSTGRES_DSN", "PGDSN"):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE="json",
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false",
                          YOLO_AUTOINSTALL="false")
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            cls.lifetime.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.lifetime.close()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.task = {"accessory_labels": {"a": "Task A", " ": "drop", "b": "  "},
                     "accessory_names": ["Old A", "Old B"], "ai_task_id": ""}
        self.config = {}
        self.replace("accessory_lookup_by_id", return_value={})

    def replace(self, name, **kwargs):
        return self.stack.enter_context(patch.object(self.api, name, **kwargs))

    def test_task_labels_stringify_and_filter_without_stripping_output(self):
        self.task["accessory_labels"] = {1: 2, " ": "drop", "blank": "  ", " a ": " A "}
        self.assertEqual(self.api.pipeline_task_label_snapshot(self.task), {"1": "2", " a ": " A "})

    def test_task_labels_empty_or_null(self):
        self.assertEqual(self.api.pipeline_task_label_snapshot({}), {})
        self.assertEqual(self.api.pipeline_task_label_snapshot({"accessory_labels": None}), {})

    def test_task_labels_linked_first_match_overrides(self):
        self.task["ai_task_id"] = "  ai-1 "
        loader = self.replace("load_ai_detection_tasks", return_value=[
            {"id": "ai-1", "accessory_labels": {"a": "First A"}},
            {"id": "ai-1", "accessory_labels": {"a": "Linked A", "c": "Linked C"}},
            {"id": "ai-1", "accessory_labels": {"a": "third"}},
        ])
        self.assertEqual(self.api.pipeline_task_label_snapshot(self.task),
                         {"a": "First A"})
        loader.assert_called_once_with()

    def test_task_labels_missing_link_leaves_local(self):
        self.task["ai_task_id"] = "missing"
        loader = self.replace("load_ai_detection_tasks", return_value=[{"id": "other", "accessory_labels": {"a": "other"}}])
        self.assertEqual(self.api.pipeline_task_label_snapshot(self.task), {"a": "Task A"})
        loader.assert_called_once_with()

    def test_task_labels_blank_id_skips_loader(self):
        self.task["ai_task_id"] = "  "
        loader = self.replace("load_ai_detection_tasks", side_effect=AssertionError("should not load"))
        self.assertEqual(self.api.pipeline_task_label_snapshot(self.task), {"a": "Task A"})
        loader.assert_not_called()

    def test_task_labels_local_malformed_raises_before_loader(self):
        self.task.update(ai_task_id="linked", accessory_labels=("bad",))
        loader = self.replace("load_ai_detection_tasks", side_effect=AssertionError("should not load"))
        with self.assertRaises(AttributeError):
            self.api.pipeline_task_label_snapshot(self.task)
        loader.assert_not_called()

    def test_task_labels_loader_error_propagates_after_local_stringification(self):
        events = []
        error = RuntimeError("synthetic loader")
        class Value:
            def __str__(self):
                events.append("local")
                return "A"
        self.task.update(ai_task_id="linked", accessory_labels={"a": Value()})
        self.replace("load_ai_detection_tasks", side_effect=lambda: events.append("loader") or (_ for _ in ()).throw(error))
        with self.assertRaises(RuntimeError) as raised:
            self.api.pipeline_task_label_snapshot(self.task)
        self.assertIs(raised.exception, error)
        self.assertEqual(events, ["local", "local", "loader"])

    def test_task_labels_linked_malformed_raises(self):
        self.task["ai_task_id"] = "linked"
        self.replace("load_ai_detection_tasks", return_value=[{"id": "linked", "accessory_labels": ("bad",)}])
        with self.assertRaises(AttributeError):
            self.api.pipeline_task_label_snapshot(self.task)

    def test_accessory_snapshot_name_precedence(self):
        self.task["ai_task_id"] = "linked"
        self.replace("load_ai_detection_tasks", return_value=[{"id": "linked", "accessory_labels": {"c": "Linked C"}}])
        self.replace("accessory_lookup_by_id", return_value={
            "a": {"name": "Current A", "label": "Label A"},
            "b": {"label": "Current B"},
            "c": {},
        })
        labels, names = self.api.pipeline_task_accessory_snapshot(self.config, self.task, ["a", "b", "c", "d"])
        self.assertEqual(labels, {"a": "Task A", "c": "Linked C"})
        self.assertEqual(names, ["Current A", "Current B", "Linked C", "d"])

    def test_accessory_snapshot_raw_name_fallback_by_position(self):
        self.task.update(accessory_labels={}, accessory_names=[" Old A ", "", "Old C"])
        labels, names = self.api.pipeline_task_accessory_snapshot(self.config, self.task, ["x", "y", "x"])
        self.assertEqual(labels, {})
        self.assertEqual(names, [" Old A ", "Old C", "x"])

    def test_accessory_snapshot_lookup_before_label_loader(self):
        events = []
        self.task["ai_task_id"] = "linked"
        self.replace("accessory_lookup_by_id", side_effect=lambda config: events.append("lookup") or {})
        self.replace("load_ai_detection_tasks", side_effect=lambda: events.append("linked") or [])
        self.api.pipeline_task_accessory_snapshot(self.config, self.task, ["a"])
        self.assertEqual(events, ["lookup", "linked"])

    def test_accessory_snapshot_lookup_error_skips_label_work(self):
        error = RuntimeError("synthetic lookup")
        self.replace("accessory_lookup_by_id", side_effect=error)
        self.task["ai_task_id"] = "linked"
        loader = self.replace("load_ai_detection_tasks", side_effect=AssertionError("should not load"))
        with self.assertRaises(RuntimeError) as raised:
            self.api.pipeline_task_accessory_snapshot(self.config, self.task, ["a"])
        self.assertIs(raised.exception, error)
        loader.assert_not_called()

    def test_accessory_snapshot_resolves_root_label_helper_late(self):
        self.replace("pipeline_task_label_snapshot", return_value={"a": "late"})
        self.assertEqual(self.api.pipeline_task_accessory_snapshot(self.config, self.task, ["a"]),
                         ({"a": "late"}, ["late"]))

    def test_task_labels_resolves_loader_after_effectful_id_string(self):
        old = self.replace("load_ai_detection_tasks", side_effect=AssertionError("stale loader"))
        class Id:
            def __str__(inner):
                self.api.load_ai_detection_tasks = lambda: [
                    {"id": "linked", "accessory_labels": {"a": "new"}}
                ]
                return "linked"
        self.task["ai_task_id"] = Id()
        self.assertEqual(self.api.pipeline_task_label_snapshot(self.task), {"a": "new"})
        old.assert_not_called()

    def test_accessory_snapshot_resolves_label_after_effectful_lookup_and_keeps_alias(self):
        stale = self.replace("pipeline_task_label_snapshot", side_effect=AssertionError("stale label"))
        labels = {"a": "current"}
        accessories = {"a": {}}
        def lookup(config):
            def current_label(task):
                accessories["a"]["name"] = "updated"
                return labels
            self.api.pipeline_task_label_snapshot = current_label
            return accessories
        self.replace("accessory_lookup_by_id", side_effect=lookup)
        actual_labels, names = self.api.pipeline_task_accessory_snapshot(self.config, self.task, ["a"])
        self.assertIs(actual_labels, labels)
        self.assertEqual(names, ["updated"])
        stale.assert_not_called()
    def test_accessory_snapshot_keeps_empty_ids_and_order(self):
        self.task.update(accessory_labels={}, accessory_names=[])
        self.assertEqual(self.api.pipeline_task_accessory_snapshot(self.config, self.task, ["", "x", "x"]),
                         ({}, ["", "x", "x"]))


    def test_independent_services_keep_three_links_isolated(self):
        from local_inspection_service.pipeline.task_snapshot_ports import PipelineTaskSnapshotLinks
        from local_inspection_service.pipeline.task_snapshots import PipelineTaskSnapshots
        events = []
        def build(tag):
            def load():
                events.append((tag, "load"))
                return [{"id": "linked", "accessory_labels": {"x": tag}}]
            def lookup(config):
                events.append((tag, "lookup"))
                return {"x": {}}
            def get_load():
                events.append((tag, "get_load"))
                return load
            def get_lookup():
                events.append((tag, "get_lookup"))
                return lookup
            def get_label():
                events.append((tag, "get_label"))
                return service.pipeline_task_label_snapshot
            links = PipelineTaskSnapshotLinks(
                load_ai_tasks=get_load,
                accessory_lookup=get_lookup,
                label_snapshot=get_label,
            )
            service = PipelineTaskSnapshots(links)
            return service
        first = build("first")
        second = build("second")
        self.assertEqual(events, [])
        self.replace("load_ai_detection_tasks", side_effect=AssertionError("root loader used"))
        self.replace("accessory_lookup_by_id", side_effect=AssertionError("root lookup used"))
        self.replace("pipeline_task_label_snapshot", side_effect=AssertionError("root label used"))
        task = {"ai_task_id": "linked", "accessory_labels": {}}
        self.assertEqual(first.pipeline_task_accessory_snapshot({}, task, ["x"]), ({"x": "first"}, ["first"]))
        self.assertEqual(second.pipeline_task_accessory_snapshot({}, task, ["x"]), ({"x": "second"}, ["second"]))
        self.assertEqual(first.pipeline_task_accessory_snapshot({}, task, ["x"]), ({"x": "first"}, ["first"]))
        self.assertEqual(events, [
            ("first", "get_lookup"), ("first", "lookup"), ("first", "get_label"), ("first", "get_load"), ("first", "load"),
            ("second", "get_lookup"), ("second", "lookup"), ("second", "get_label"), ("second", "get_load"), ("second", "load"),
            ("first", "get_lookup"), ("first", "lookup"), ("first", "get_label"), ("first", "get_load"), ("first", "load"),
        ])

if __name__ == "__main__":
    unittest.main()