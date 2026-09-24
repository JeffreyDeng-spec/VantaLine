"""Synthetic contract for pipeline views of training jobs and status mapping."""

import ast
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import types
from typing import Callable
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

NAMES = {"linked_training_job", "sync_pipeline_task"}


class PipelineTrainingStatusContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        root = Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix="pipeline-training-status-")))
        (root / "local_inspection_service/static").mkdir(parents=True)
        for key in ("DATABASE_URL", "VANTALINE_POSTGRES_DSN", "PGDSN"):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE="json",
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false",
                          YOLO_AUTOINSTALL="false")
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            cls.lifetime.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))
        baseline = os.environ.get("VANTALINE_TRAINING_STATUS_BASELINE_SOURCE")
        if baseline:
            tree = ast.parse(Path(baseline).read_text(encoding="utf-8"))
            functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
            if {node.name for node in functions} != NAMES:
                raise AssertionError("accepted-main training status functions missing")
            cls.api = types.ModuleType("accepted_main_training_status")
            cls.api.__dict__.update(Any=object, Callable=Callable, Path=Path)
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

    def test_linked_early_return_avoids_all_calls(self):
        path = self.replace("training_task_path", Mock(side_effect=AssertionError("path")))
        load = self.replace("load_training_task", Mock(side_effect=AssertionError("load")))
        public = self.replace("public_refreshed_training_task", Mock(side_effect=AssertionError("public")))
        self.assertIsNone(self.api.linked_training_job({"stage": "training", "training_task_id": 0}))
        self.assertIsNone(self.api.linked_training_job({"stage": "samples", "samples_task_id": None}))
        path.assert_not_called(); load.assert_not_called(); public.assert_not_called()

    def test_linked_stage_selection_and_projection_identity(self):
        events = []
        task = {"stage": "training", "training_task_id": 7, "samples_task_id": "other"}
        job = {"id": "job"}; projected = {"id": "projected"}
        self.replace("training_task_path", lambda value: events.append(("path", value)) or Path(value))
        self.replace("load_training_task", lambda path: events.append(("load", path)) or job)
        self.replace("public_refreshed_training_task", lambda value: events.append(("public", value is job)) or projected)
        self.assertIs(self.api.linked_training_job(task), projected)
        task["stage"] = "samples"
        self.assertIs(self.api.linked_training_job(task), projected)
        self.assertEqual(events, [("path", "7"), ("load", Path("7")), ("public", True),
                                  ("path", "other"), ("load", Path("other")), ("public", True)])

    def test_linked_truthy_loader_selection_and_late_projection(self):
        events = []
        class FalseLoader:
            def __bool__(self):
                events.append("bool")
                return False
            def __call__(self, path):
                raise AssertionError("false loader called")
        job = {"status": "running"}
        self.replace("load_training_task", lambda path: events.append("default") or job)
        self.replace("training_task_path", lambda value: events.append("path") or Path(value))
        self.replace("public_refreshed_training_task", lambda value: events.append("projection") or value)
        self.assertIs(self.api.linked_training_job({"stage": "training", "training_task_id": "a"}, FalseLoader()), job)
        self.assertEqual(events, ["bool", "path", "default", "projection"])

    def test_linked_selected_loader_stays_fixed_when_path_rebinds_it(self):
        events = []
        def selected(path):
            events.append("selected")
            return {"status": "running"}
        def path(value):
            self.replace("load_training_task", lambda p: events.append("rebound") or {})
            events.append("path")
            return Path(value)
        self.replace("load_training_task", selected)
        self.replace("training_task_path", path)
        self.replace("public_refreshed_training_task", lambda job: events.append("projection") or job)
        self.api.linked_training_job({"stage": "training", "training_task_id": "a"})
        self.assertEqual(events, ["path", "selected", "projection"])

    def test_linked_projection_is_resolved_after_loader(self):
        events = []
        job = {"status": "running"}
        old = Mock(side_effect=AssertionError("old projection"))
        self.replace("public_refreshed_training_task", old)
        self.replace("training_task_path", lambda value: Path(value))
        def load(path):
            self.replace("public_refreshed_training_task", lambda record: events.append(("new", record is job)) or record)
            return job
        self.replace("load_training_task", load)
        self.assertIs(self.api.linked_training_job({"stage": "training", "training_task_id": "j"}), job)
        old.assert_not_called()
        self.assertEqual(events, [("new", True)])

    def test_linked_falsey_job_skips_projection(self):
        public = self.replace("public_refreshed_training_task", Mock(side_effect=AssertionError("public")))
        self.replace("training_task_path", lambda value: Path(value))
        self.replace("load_training_task", lambda path: {})
        self.assertIsNone(self.api.linked_training_job({"stage": "training", "training_task_id": "a"}))
        public.assert_not_called()

    def test_sync_early_return_avoids_lookup(self):
        linked = self.replace("linked_training_job", Mock(side_effect=AssertionError("linked")))
        for task in ({"stage": "draft"}, {"stage": "samples", "status": "completed"},
                     {"stage": "training", "status": "failed"}, {"stage": "training", "status": "stopped"}):
            self.assertFalse(self.api.sync_pipeline_task(task))
        linked.assert_not_called()

    def test_sync_uses_late_root_link_and_original_task(self):
        task = {"stage": "samples", "status": "running", "progress": 0}
        finder = lambda path: None
        linked = self.replace("linked_training_job", Mock(return_value={"status": "completed", "progress": 3}))
        self.assertTrue(self.api.sync_pipeline_task(task, finder))
        linked.assert_called_once_with(task, finder)
        self.assertEqual((task["status"], task["progress"]), ("completed", 3))

    def test_sync_status_mapping_and_only_note_change(self):
        job = {"status": "cancelled", "progress": 4, "note": "new note"}
        self.replace("linked_training_job", lambda task, load: job)
        task = {"stage": "samples", "status": "running", "progress": 4, "job_note": "old note"}
        self.assertFalse(self.api.sync_pipeline_task(task))
        self.assertEqual(task["job_note"], "old note")
        job["progress"] = 5
        self.assertTrue(self.api.sync_pipeline_task(task))
        self.assertEqual((task["status"], task["progress"], task["job_note"]), ("running", 5, "new note"))
        for status, expected in (("completed", "completed"), ("failed", "failed"), ("stopped", "stopped"),
                                 ("canceled", "running")):
            job["status"] = status
            job["progress"] += 1
            task["status"] = "running"
            self.assertTrue(self.api.sync_pipeline_task(task))
            self.assertEqual(task["status"], expected)

    def test_sync_progress_exception_precedes_mutation(self):
        error = ValueError("bad progress")
        class Bad:
            def __int__(self): raise error
        self.replace("linked_training_job", lambda task, load: {"status": "failed", "progress": Bad()})
        task = {"stage": "training", "status": "running", "progress": 0}
        with self.assertRaises(ValueError) as raised:
            self.api.sync_pipeline_task(task)
        self.assertIs(raised.exception, error)
        self.assertEqual(task, {"stage": "training", "status": "running", "progress": 0})

    def test_sync_epoch_zero_reads_twice_and_fallback(self):
        reads = []
        class Job(dict):
            def get(self, key, default=None):
                reads.append(key)
                return super().get(key, default)
        job = Job(status="completed", progress="0", note="n", current_epoch=0, total_epochs=0, epochs=8)
        self.replace("linked_training_job", lambda task, load: job)
        task = {"stage": "training", "status": "running", "progress": 1}
        self.assertTrue(self.api.sync_pipeline_task(task))
        self.assertEqual((task["current_epoch"], task["total_epochs"]), (0, 8))
        self.assertEqual(reads.count("current_epoch"), 2)

    def test_sync_training_success_rebinds_stage_setter_after_orchestration(self):
        events = []
        orchestration = {}
        old = Mock(side_effect=AssertionError("old setter"))
        self.replace("set_agent_mcp_stage", old)
        self.replace("linked_training_job", lambda task, load: {"status": "completed", "progress": 8})
        def get_orchestration(task):
            self.replace("set_agent_mcp_stage", lambda obj, stage, status, progress:
                         events.append((obj is orchestration, stage, status, progress)))
            return orchestration
        self.replace("agent_mcp_orchestration", get_orchestration)
        task = {"stage": "training", "status": "running", "progress": 1, "agent_mcp": {"enabled": True}}
        self.assertTrue(self.api.sync_pipeline_task(task))
        old.assert_not_called()
        self.assertEqual(events, [(True, "model_training", "completed", 100)])
        self.assertEqual(orchestration["state"], "completed")

    def test_real_view_lifecycle_can_settle_local_job_with_write_guard(self):
        from local_inspection_service.runtime.training_tasks import TrainingTaskState
        from local_inspection_service.training.task_lifecycle import (
            TrainingTaskLifecycle, TrainingTaskRecords, TrainingTaskWrites,
        )
        from local_inspection_service.training.task_views import TrainingTaskViews, TrainingViewAccess
        events = []
        stored = {"j": {"job_id": "j", "status": "running", "progress": 2}}
        class Guard:
            def __enter__(self): events.append("lock"); return self
            def __exit__(self, *args): events.append("unlock"); return False
        records = TrainingTaskRecords(
            path=lambda job_id: Path(job_id),
            load=lambda path: events.append("load") or stored.get(str(path)),
            save=lambda task: events.append(("save", task["status"])) or stored.__setitem__(task["job_id"], dict(task)),
            find=lambda job_id: stored.get(job_id),
        )
        lifecycle = TrainingTaskLifecycle(
            TrainingTaskState(guard=lambda: Guard(), threads=lambda: {}, tombstones=lambda: {}),
            records,
            TrainingTaskWrites(repository=lambda: None, row=lambda task: {}, invalidate=lambda job_id: None),
            require_access=lambda record, user, write=False: None,
        )
        views = TrainingTaskViews(
            records=lambda: list(stored.values()), refresh=lifecycle.refresh_interrupted_local_training_task,
            access=TrainingViewAccess(enrich=lambda task: dict(task), sanitize=lambda: (lambda task: task),
                                      visible=lambda record, user, target: True),
        )
        self.replace("training_task_path", lambda job_id: Path(job_id))
        self.replace("load_training_task", lambda path: stored.get(str(path)))
        self.replace("public_refreshed_training_task", views.public_refreshed_training_task)
        projected = self.api.linked_training_job({"stage": "training", "training_task_id": "j"})
        self.assertEqual(projected["status"], "stopped")
        self.assertEqual(stored["j"]["status"], "stopped")
        self.assertEqual(events[:3], ["lock", "load", ("save", "stopped")])
        self.assertEqual(events[-1], "unlock")
        events.clear()
        self.api.linked_training_job({"stage": "training", "training_task_id": "j"})
        self.assertEqual(events, [])
        stored["legacy"] = {"job_id": "legacy", "status": "running", "training_executor": "worker"}
        self.api.linked_training_job({"stage": "training", "training_task_id": "legacy"})
        self.assertEqual(events, [])

    def test_candidate_instances_are_passive_and_isolated(self):
        if os.environ.get("VANTALINE_TRAINING_STATUS_BASELINE_SOURCE"):
            self.skipTest("candidate-only constructor contract")
        from local_inspection_service.pipeline.training_status import PipelineTrainingStatus
        from local_inspection_service.pipeline.training_status_ports import TrainingJobLookup, TrainingStatusEffects
        events = []
        def make(label):
            def getter(name, value):
                return lambda: events.append((label, name)) or value
            job = {"status": "completed", "progress": 4}
            lookup = TrainingJobLookup(
                load=getter("load", lambda path: job),
                path=getter("path", lambda name: Path(name)),
                public=getter("public", lambda record: dict(record, label=label)),
                linked=getter("linked", lambda task, load: job),
            )
            effects = TrainingStatusEffects(
                orchestration=getter("orchestration", lambda task: task["agent_mcp"]),
                set_stage=getter("set_stage", lambda obj, stage, status, progress: obj.update(stage=stage)),
            )
            return PipelineTrainingStatus(lookup, effects)
        a, b = make("a"), make("b")
        self.assertEqual(events, [])
        for root_name in ("load_training_task", "training_task_path", "public_refreshed_training_task",
                          "linked_training_job", "agent_mcp_orchestration", "set_agent_mcp_stage"):
            self.replace(root_name, Mock(side_effect=AssertionError("root callback used: " + root_name)))
        task = {"stage": "training", "training_task_id": "j"}
        self.assertEqual(a.linked_training_job(task)["label"], "a")
        self.assertEqual(b.linked_training_job(task)["label"], "b")
        self.assertEqual(a.linked_training_job(task)["label"], "a")
        self.assertEqual(events, [(label, name) for label in ("a", "b", "a")
                                  for name in ("load", "path", "public")])
        events.clear()
        for service in (a, b, a):
            task = {"stage": "samples", "status": "running", "progress": 0, "agent_mcp": {"enabled": True}}
            self.assertTrue(service.sync_pipeline_task(task))
            self.assertEqual(task["agent_mcp"]["stage"], "sample_generation")
        self.assertEqual(events, [(label, name) for label in ("a", "b", "a")
                                  for name in ("linked", "orchestration", "set_stage")])

    def test_sync_agent_mapping_and_setter_failure_partial_effect(self):
        events = []
        error = RuntimeError("setter failed")
        job = {"status": "completed", "progress": 80, "note": "done"}
        self.replace("linked_training_job", lambda task, load: job)
        orchestration = {}
        self.replace("agent_mcp_orchestration", lambda task: events.append("orchestration") or orchestration)
        def set_stage(obj, stage, status, progress):
            events.append((obj is orchestration, stage, status, progress))
            raise error
        self.replace("set_agent_mcp_stage", set_stage)
        task = {"stage": "samples", "status": "running", "progress": 2, "agent_mcp": {"enabled": True}}
        with self.assertRaises(RuntimeError) as raised:
            self.api.sync_pipeline_task(task)
        self.assertIs(raised.exception, error)
        self.assertEqual((task["status"], task["progress"], task["job_note"]), ("completed", 80, "done"))
        self.assertEqual(events, ["orchestration", (True, "sample_generation", "completed", 100)])
        self.assertEqual(orchestration, {})


if __name__ == "__main__":
    unittest.main()
