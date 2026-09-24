"""Original-versus-candidate contract for trained-model pipeline linkage."""

import ast
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TrainedModelLinkContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        root = Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix="pipeline-model-link-")))
        (root / "local_inspection_service/static").mkdir(parents=True)
        for key in ("DATABASE_URL", "VANTALINE_POSTGRES_DSN", "PGDSN"):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE="json",
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false",
                          YOLO_AUTOINSTALL="false")
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            cls.lifetime.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))
        baseline = os.environ.get("VANTALINE_MODEL_LINK_BASELINE_SOURCE")
        if baseline:
            tree = ast.parse(Path(baseline).read_text(encoding="utf-8"))
            function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                            and node.name == "link_pipeline_trained_model")
            cls.api = types.ModuleType("accepted_main_trained_model_link")
            cls.api.__dict__["Any"] = object
            exec(compile(ast.Module(body=[function], type_ignores=[]), baseline, "exec"), cls.api.__dict__)
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

    def test_empty_id_skips_catalog_and_mutation(self):
        listing = self.replace("list_trained_model_specs", Mock(side_effect=AssertionError("catalog")))
        task = {"training_task_id": "   ", "model_label": "old"}
        self.assertIsNone(self.api.link_pipeline_trained_model(task))
        self.assertEqual(task, {"training_task_id": "   ", "model_label": "old"})
        listing.assert_not_called()

    def test_first_matching_spec_wins_and_identity_is_returned(self):
        first = {"run_id": "run", "id": 7, "label": 8, "path": "/missing/model"}
        second = {"run_id": "run", "id": "second", "path": ""}
        listing = self.replace("list_trained_model_specs", Mock(return_value=[{"run_id": "x"}, first, second]))
        task = {"training_task_id": " run ", "unrelated": 42}
        self.assertIs(self.api.link_pipeline_trained_model(task), first)
        self.assertEqual((task["model_run_id"], task["ai_model_id"], task["model_label"],
                          task["model_exists"], task["linked_view"]), ("run", "7", "8", True, "inspect"))
        self.assertEqual(task["unrelated"], 42)
        listing.assert_called_once_with()

    def test_catalog_run_id_is_not_stripped_and_first_nonmatching_is_skipped(self):
        self.replace("list_trained_model_specs", lambda: [{"run_id": " run ", "id": "bad"},
                                                         {"run_id": "run", "id": "good", "path": ""}])
        task = {"training_task_id": "run"}
        self.assertEqual(self.api.link_pipeline_trained_model(task)["id"], "good")
        self.assertFalse(task["model_exists"])

    def test_fallback_priority_and_stale_fields_are_preserved(self):
        self.replace("list_trained_model_specs", lambda: [])
        task = {"training_task_id": " x ", "params": {"train_mode": "custom"}, "detection_method": "other",
                "model_label": "stale", "model_exists": True}
        self.assertIsNone(self.api.link_pipeline_trained_model(task))
        self.assertEqual(task["ai_model_id"], "trained_x__custom")
        self.assertEqual((task["model_label"], task["model_exists"]), ("stale", True))
        task["params"] = {"train_mode": 0}
        self.api.link_pipeline_trained_model(task)
        self.assertEqual(task["ai_model_id"], "trained_x__other")
        task["detection_method"] = ""
        self.api.link_pipeline_trained_model(task)
        self.assertEqual(task["ai_model_id"], "trained_x__yolo")

    def test_fallback_invalid_params_raises_without_update(self):
        self.replace("list_trained_model_specs", lambda: [])
        task = {"training_task_id": "x", "params": ["bad"], "model_run_id": "old"}
        with self.assertRaises(AttributeError):
            self.api.link_pipeline_trained_model(task)
        self.assertEqual(task["model_run_id"], "old")

    def test_catalog_getter_resolves_after_id_conversion(self):
        events = []
        old = self.replace("list_trained_model_specs", Mock(side_effect=AssertionError("old catalog")))
        class Id:
            def __str__(self):
                self_outer.replace("list_trained_model_specs", lambda: events.append("new catalog") or [])
                events.append("id str")
                return "run"
        self_outer = self
        self.api.link_pipeline_trained_model({"training_task_id": Id()})
        old.assert_not_called()
        self.assertEqual(events, ["id str", "new catalog"])

    def test_update_method_is_selected_before_spec_value_evaluation(self):
        events = []
        class Task(dict):
            def __getattribute__(self, name):
                if name == "update": events.append("select update")
                return super().__getattribute__(name)
            def update(self, value):
                events.append("call update")
                return super().update(value)
        class Spec(dict):
            def get(self, key, default=None):
                events.append(("get", key))
                return super().get(key, default)
        self.replace("list_trained_model_specs", lambda: [Spec(run_id="x", id="id", label="label", path="p")])
        task = Task(training_task_id="x")
        self.api.link_pipeline_trained_model(task)
        self.assertEqual(events, [("get", "run_id"), "select update", ("get", "id"),
                                  ("get", "label"), ("get", "path"), "call update"])

    def test_spec_value_error_prevents_update_call(self):
        error = RuntimeError("bad id")
        class Task(dict):
            def update(self, value):
                raise AssertionError("update called")
        class Spec(dict):
            def get(self, key, default=None):
                if key == "id": raise error
                return super().get(key, default)
        self.replace("list_trained_model_specs", lambda: [Spec(run_id="x")])
        task = Task(training_task_id="x")
        with self.assertRaises(RuntimeError) as raised:
            self.api.link_pipeline_trained_model(task)
        self.assertIs(raised.exception, error)
        self.assertEqual(task, {"training_task_id": "x"})

    def test_real_terminal_sync_keeps_two_catalog_reads_and_link_error_partial_state(self):
        from local_inspection_service.pipeline.training_sync import (
            PipelineTrainingSync, PipelineTrainingRecords, PipelineTrainingModels,
        )
        events = []
        class Guard:
            active = False
            def __enter__(self): self.active = True; events.append("lock"); return self
            def __exit__(self, *args): self.active = False; events.append("unlock"); return False
        guard = Guard()
        task = {"id": "pipe", "ai_task_id": "ai", "detection_method": "yolo", "stage": "training", "status": "running"}
        first = {"run_id": "run", "id": "resolver", "path": "first"}
        second = {"run_id": "run", "id": "linker", "path": "second"}
        catalogs = iter(([first], [second]))
        def catalog():
            events.append(("catalog", guard.active))
            return next(catalogs)
        self.replace("list_trained_model_specs", catalog)
        def resolve(record, job_id):
            return catalog()[0]["id"]
        def save(record):
            events.append(("save", guard.active, record["ai_model_id"]))
            return record
        sink = lambda record, **kwargs: events.append(("candidate", guard.active))
        service = PipelineTrainingSync(
            guard=lambda: guard,
            records=PipelineTrainingRecords(load=lambda task_id: task, save=save),
            models=PipelineTrainingModels(resolve=resolve, link=lambda record: self.api.link_pipeline_trained_model(record)),
            normalize_method=lambda: (lambda value: value),
            clean_id=lambda: (lambda value: str(value)), sync_candidate=sink,
        )
        training = {"job_id": "run", "pipeline_task_id": "pipe", "status": "completed"}
        service.sync_pipeline_training_state_from_task(training)
        self.assertEqual(events[:4], [("catalog", False), "lock", ("catalog", True),
                                      ("save", True, "linker")])
        self.assertEqual(task["ai_model_id"], "linker")
        self.assertEqual(task["stage"], "library")
        self.assertEqual(events[-2:], ["unlock", ("candidate", False)])
        events.clear()
        task.clear(); task.update({"id": "pipe", "ai_task_id": "ai", "detection_method": "yolo", "stage": "training", "status": "running"})
        error = RuntimeError("link catalog failed")
        def fail_catalog():
            events.append(("catalog", guard.active))
            if guard.active:
                raise error
            return [first]
        self.replace("list_trained_model_specs", fail_catalog)
        def fail_resolve(record, job_id):
            return fail_catalog()[0]["id"]
        failed_service = PipelineTrainingSync(
            guard=lambda: guard,
            records=PipelineTrainingRecords(load=lambda task_id: task, save=save),
            models=PipelineTrainingModels(resolve=fail_resolve, link=lambda record: self.api.link_pipeline_trained_model(record)),
            normalize_method=lambda: (lambda value: value),
            clean_id=lambda: (lambda value: str(value)), sync_candidate=sink,
        )
        with self.assertRaises(RuntimeError) as raised:
            failed_service.sync_pipeline_training_state_from_task(training)
        self.assertIs(raised.exception, error)
        self.assertEqual(task["stage"], "library")
        self.assertEqual(task["ai_model_id"], "resolver")
        self.assertEqual(events, [("catalog", False), "lock", ("catalog", True), "unlock"])

    def test_candidate_instances_are_passive_and_isolated(self):
        if os.environ.get("VANTALINE_MODEL_LINK_BASELINE_SOURCE"):
            self.skipTest("candidate-only constructor contract")
        from local_inspection_service.pipeline.training_links import PipelineTrainedModelLink
        events = []
        def make(label):
            def catalog():
                events.append((label, "getter"))
                def list_specs():
                    events.append((label, "catalog"))
                    return [{"run_id": "r", "id": label}]
                return list_specs
            return PipelineTrainedModelLink(catalog)
        a, b = make("a"), make("b")
        self.assertEqual(events, [])
        self.replace("list_trained_model_specs", Mock(side_effect=AssertionError("root catalog used")))
        for service, label in ((a, "a"), (b, "b"), (a, "a")):
            task = {"training_task_id": "r"}
            self.assertEqual(service.link_pipeline_trained_model(task)["id"], label)
            self.assertEqual(task["ai_model_id"], label)
        self.assertEqual(events, [(label, name) for label in ("a", "b", "a")
                                  for name in ("getter", "catalog")])


if __name__ == "__main__":
    unittest.main()
