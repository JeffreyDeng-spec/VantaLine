"""Synthetic original contracts for pipeline dataset and model resource status."""
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class PipelineResourceStatusContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root = Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix="pipeline-resource-status-")))
        (cls.root / "local_inspection_service/static").mkdir(parents=True)
        for key in ("DATABASE_URL", "VANTALINE_POSTGRES_DSN", "PGDSN"):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(cls.root), VANTALINE_DATA_STORE="json",
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
        self.task = {"stage": "draft", "status": "ready", "detection_method": "yolo"}
        self.finder = self.replace("find_dataset_resource", side_effect=AssertionError("finder not expected"))
        self.ai_loader = self.replace("load_ai_detection_tasks", side_effect=AssertionError("AI loader not expected"))
        self.spec_loader = self.replace("list_trained_model_specs", side_effect=AssertionError("spec loader not expected"))

    def replace(self, name, **kwargs):
        return self.stack.enter_context(patch.object(self.api, name, **kwargs))

    def test_dataset_no_id_precedes_deleted_and_skips_finder(self):
        self.task["dataset_status"] = "deleted"
        self.assertEqual(self.api.pipeline_task_dataset_status(self.task), "none")
        self.finder.assert_not_called()

    def test_dataset_deleted_with_id_skips_finder(self):
        self.task.update(dataset_id=" data ", dataset_status="deleted")
        self.assertEqual(self.api.pipeline_task_dataset_status(self.task), "deleted")
        self.finder.assert_not_called()

    def test_dataset_alias_and_existing_directory_are_available(self):
        self.task["samples_task_id"] = "  sample-1  "
        self.finder.side_effect = None
        self.finder.return_value = (self.root, None)
        self.assertEqual(self.api.pipeline_task_dataset_status(self.task), "available")
        self.finder.assert_called_once_with("sample-1")

    def test_dataset_primary_id_precedes_alias(self):
        self.task.update(dataset_id=" primary ", samples_task_id="alias")
        self.finder.side_effect = None
        self.finder.return_value = (None, None)
        self.assertEqual(self.api.pipeline_task_dataset_status(self.task), "missing")
        self.finder.assert_called_once_with("primary")

    def test_dataset_pending_states_only_for_samples_stage(self):
        self.task.update(dataset_id="d", stage="samples", status="queued")
        self.finder.side_effect = None
        self.finder.return_value = (None, None)
        self.assertEqual(self.api.pipeline_task_dataset_status(self.task), "pending")
        self.task["status"] = "completed"
        self.assertEqual(self.api.pipeline_task_dataset_status(self.task), "missing")
        self.task.update(stage="training", status="running")
        self.assertEqual(self.api.pipeline_task_dataset_status(self.task), "missing")

    def test_dataset_finder_error_propagates_identically(self):
        error = RuntimeError("synthetic finder")
        self.task["dataset_id"] = "d"
        self.finder.side_effect = error
        with self.assertRaises(RuntimeError) as raised:
            self.api.pipeline_task_dataset_status(self.task)
        self.assertIs(raised.exception, error)

    def test_dataset_exists_error_propagates_identically(self):
        error = OSError("synthetic exists")
        self.task["dataset_id"] = "d"
        self.finder.side_effect = None
        self.finder.return_value = (self.root, None)
        with patch.object(Path, "exists", side_effect=error):
            with self.assertRaises(OSError) as raised:
                self.api.pipeline_task_dataset_status(self.task)
        self.assertIs(raised.exception, error)

    def test_dataset_stringification_happens_before_deleted_gate(self):
        class Id:
            def __str__(inner):
                self.task["dataset_status"] = "deleted"
                return "d"
        self.task["dataset_id"] = Id()
        self.assertEqual(self.api.pipeline_task_dataset_status(self.task), "deleted")
        self.finder.assert_not_called()

    def test_dataset_resolves_finder_after_effectful_id_string(self):
        old = self.finder
        class Id:
            def __str__(inner):
                self.api.find_dataset_resource = lambda dataset_id: (self.root, None)
                return "d"
        self.task["dataset_id"] = Id()
        self.assertEqual(self.api.pipeline_task_dataset_status(self.task), "available")
        old.assert_not_called()
    def test_model_deleted_precedes_every_loader(self):
        self.task.update(model_status="deleted", detection_method="ai", ai_task_id="ai", model_run_id="run")
        self.assertEqual(self.api.pipeline_task_model_status(self.task), "deleted")
        self.ai_loader.assert_not_called()
        self.spec_loader.assert_not_called()

    def test_model_ai_empty_set_is_authoritative_and_skips_loader(self):
        self.task.update(detection_method="ai", ai_task_id=" ai ")
        self.assertEqual(self.api.pipeline_task_model_status(self.task, ai_task_ids=set()), "missing")
        self.assertEqual(self.api.pipeline_task_model_status(self.task, ai_task_ids={"ai"}), "available")
        self.ai_loader.assert_not_called()

    def test_model_ai_loader_first_matching_id(self):
        self.task.update(detection_method="ai", ai_task_id="ai")
        self.ai_loader.side_effect = None
        self.ai_loader.return_value = [{"id": 2}, {"id": "ai"}, {"id": "ai"}]
        self.assertEqual(self.api.pipeline_task_model_status(self.task), "available")
        self.ai_loader.assert_called_once_with()

    def test_model_ai_branch_precedes_run_id_and_pending(self):
        self.task.update(detection_method="ai", ai_task_id="ai", model_run_id="run",
                         stage="training", status="running")
        self.assertEqual(self.api.pipeline_task_model_status(self.task, ai_task_ids=set()), "missing")
        self.spec_loader.assert_not_called()

    def test_model_no_run_id_returns_none_without_spec_loader(self):
        self.assertEqual(self.api.pipeline_task_model_status(self.task), "none")
        self.spec_loader.assert_not_called()

    def test_model_empty_specs_are_authoritative_and_training_can_be_pending(self):
        self.task.update(model_run_id="run", stage="training", status="queued")
        self.assertEqual(self.api.pipeline_task_model_status(self.task, trained_model_specs=[]), "pending")
        self.spec_loader.assert_not_called()

    def test_model_nested_run_id_normalization_and_directory_exists(self):
        self.task["training_task_id"] = "trained_bad?run"
        self.assertEqual(self.api.pipeline_task_model_status(
            self.task, trained_model_specs=[{"run_id": "bad_run", "path": str(self.root)}]), "available")

    def test_model_first_matching_spec_wins_and_missing_precedes_pending(self):
        self.task.update(model_run_id="run", stage="training", status="completed")
        specs = [{"run_id": "run", "path": str(self.root / "absent")},
                 {"run_id": "run", "path": str(self.root)}]
        self.assertEqual(self.api.pipeline_task_model_status(self.task, trained_model_specs=specs), "missing")
        self.task["status"] = "running"
        self.assertEqual(self.api.pipeline_task_model_status(self.task, trained_model_specs=specs), "pending")

    def test_model_resolves_ai_loader_after_second_id_string(self):
        self.task["detection_method"] = "ai"
        calls = []
        class Id:
            def __str__(inner):
                calls.append("id")
                if len(calls) == 2:
                    self.api.load_ai_detection_tasks = lambda: [{"id": "ai"}]
                return "ai"
        self.task["ai_task_id"] = Id()
        self.assertEqual(self.api.pipeline_task_model_status(self.task), "available")
        self.assertEqual(calls, ["id", "id"])
        self.ai_loader.assert_not_called()

    def test_model_resolves_spec_loader_after_effectful_run_id_string(self):
        class Id:
            def __str__(inner):
                self.api.list_trained_model_specs = lambda: [
                    {"run_id": "run", "path": str(self.root)}
                ]
                return "run"
        self.task["model_run_id"] = Id()
        self.assertEqual(self.api.pipeline_task_model_status(self.task), "available")
        self.spec_loader.assert_not_called()
    def test_model_loader_error_propagates_identically(self):
        error = RuntimeError("synthetic spec loader")
        self.task["model_run_id"] = "run"
        self.spec_loader.side_effect = error
        with self.assertRaises(RuntimeError) as raised:
            self.api.pipeline_task_model_status(self.task)
        self.assertIs(raised.exception, error)

    def test_model_exists_error_propagates_identically(self):
        error = OSError("synthetic model exists")
        self.task["model_run_id"] = "run"
        specs = [{"run_id": "run", "path": str(self.root)}]
        with patch.object(Path, "exists", side_effect=error):
            with self.assertRaises(OSError) as raised:
                self.api.pipeline_task_model_status(self.task, trained_model_specs=specs)
        self.assertIs(raised.exception, error)


    def test_independent_services_use_all_three_links_without_root(self):
        from local_inspection_service.pipeline.resource_status_ports import PipelineResourceStatusLinks
        from local_inspection_service.pipeline.resource_status import PipelineResourceStatus
        events = []
        def build(tag):
            directory = self.root / tag
            directory.mkdir()
            def find(dataset_id):
                events.append((tag, "find"))
                return directory, None
            def ai():
                events.append((tag, "ai"))
                return [{"id": tag}]
            def specs():
                events.append((tag, "specs"))
                return [{"run_id": tag, "path": str(directory)}]
            def get_find():
                events.append((tag, "get_find"))
                return find
            def get_ai():
                events.append((tag, "get_ai"))
                return ai
            def get_specs():
                events.append((tag, "get_specs"))
                return specs
            return PipelineResourceStatus(PipelineResourceStatusLinks(
                find_dataset=get_find, load_ai_tasks=get_ai, list_trained_specs=get_specs
            ))
        first = build("first")
        second = build("second")
        self.assertEqual(events, [])
        dataset = {"dataset_id": "d"}
        ai_task = {"detection_method": "ai", "ai_task_id": "first"}
        model = {"model_run_id": "first"}
        for service, tag in ((first, "first"), (second, "second"), (first, "first")):
            ai_task["ai_task_id"] = tag
            model["model_run_id"] = tag
            self.assertEqual(service.pipeline_task_dataset_status(dataset), "available")
            self.assertEqual(service.pipeline_task_model_status(ai_task), "available")
            self.assertEqual(service.pipeline_task_model_status(model), "available")
        self.finder.assert_not_called()
        self.ai_loader.assert_not_called()
        self.spec_loader.assert_not_called()
        self.assertEqual(events, [
            (tag, name)
            for tag in ("first", "second", "first")
            for name in ("get_find", "find", "get_ai", "ai", "get_specs", "specs")
        ])

if __name__ == "__main__":
    unittest.main()