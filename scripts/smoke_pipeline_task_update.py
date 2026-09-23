"""Offline regression for the extracted pipeline PATCH use case."""
import ast
from dataclasses import fields, replace
from contextlib import ExitStack
from pathlib import Path
import os
import sys
import tempfile
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TracedLock:
    def __init__(self, events, label="lock"):
        self.events = events
        self.label = label
        self.held = False

    def __enter__(self):
        assert not self.held
        self.held = True
        self.events.append(f"{self.label}.enter")

    def __exit__(self, *_):
        self.events.append(f"{self.label}.exit")
        self.held = False


def main():
    with tempfile.TemporaryDirectory(prefix="pipeline-update-") as tmp, patch.dict(os.environ, {
        "LOCAL_INSPECTION_ROOT": tmp,
        "VANTALINE_DATA_STORE": "json",
        "LOCAL_INSPECTION_AUTO_RESUME_WORKER": "0",
        "VANTALINE_LABEL_INSPECTION_ENABLED": "false",
        "YOLO_AUTOINSTALL": "false",
    }):
        (Path(tmp) / "local_inspection_service" / "static").mkdir(parents=True)
        os.environ.pop("VANTALINE_POSTGRES_DSN", None)
        from local_inspection_service import server
        from local_inspection_service.schemas.pipeline import PipelineTaskUpdateRequest

        baseline_source = os.environ.get("VANTALINE_UPDATE_BASELINE_SOURCE")
        if baseline_source:
            tree = ast.parse(Path(baseline_source).read_text(encoding="utf-8"))
            function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "update_pipeline_task")
            function.decorator_list = []
            exec(compile(ast.Module(body=[function], type_ignores=[]), baseline_source, "exec"), server.__dict__)
        else:
            route = next(route for route in server.app.routes if getattr(route, "path", "") == "/api/pipeline/tasks/{task_id}" and "PATCH" in getattr(route, "methods", set()))
            assert route.endpoint is server.update_pipeline_task

        def exercise(task, payload, *, public_failure=False, save_failure=False, rebind_scope=False, broken_names=False, access_error=None, rebind_lock=False):
            events = []
            lock = TracedLock(events)
            alternate_lock = TracedLock(events, "alternate")
            saved = []
            scoped = {"accessories": []}

            def load_config():
                events.append("config.load")
                if rebind_scope:
                    server.scope_config_for_user = lambda *_: (_ for _ in ()).throw(AssertionError("scope rebound too soon"))
                return scoped

            def scope_config(config, user):
                events.append("config.scope")
                if rebind_lock:
                    server._pipeline_tasks_lock = alternate_lock
                return config

            def public(item, config):
                events.append(("public", lock.held))
                if public_failure:
                    raise RuntimeError("public failed")
                return dict(item)

            def save(item):
                events.append("save")
                saved.append(dict(item))
                if save_failure:
                    raise RuntimeError("save failed")

            def unique(name, owner, **kwargs):
                events.append("unique")


            def owner_id(item):
                server.assert_unique_task_name = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unique rebound too soon"))
                return "owner"

            def require_access(*args, **kwargs):
                events.append("access")
                if access_error:
                    raise access_error

            def accessory_snapshot(config, item, ids):
                return ({x: x for x in ids}, [] if broken_names else list(ids))

            replacements = {
                "current_auth_user": lambda: {"id": "owner"},
                "load_config": load_config,
                "scope_config_for_user": scope_config,
                "_pipeline_tasks_lock": lock,
                "load_pipeline_task": lambda *_: task,
                "require_record_access": require_access,
                "require_permission": lambda *args, **kwargs: events.append("permission"),
                "assert_unique_task_name": unique,
                "record_owner_id": owner_id,
                "canonical_pipeline_accessory_ids": lambda config, ids: ids,
                "normalize_pipeline_accessory_counts": lambda config, ids, counts: counts or {},
                "pipeline_task_accessory_snapshot": accessory_snapshot,
                "normalize_pipeline_detection_method": lambda value: value,
                "pipeline_method_uses_training": lambda value: value == "training",
                "PIPELINE_DETECTION_METHODS": {"training", "label_text_compare"},
                "normalize_expected_production_count": lambda value: int(value),
                "save_pipeline_task": save,
                "pipeline_task_public": public,
            }
            with ExitStack() as stack:
                for name, value in replacements.items():
                    stack.enter_context(patch.object(server, name, value))
                try:
                    result = server.update_pipeline_task("task-1", PipelineTaskUpdateRequest(**payload))
                    error = None
                except Exception as exc:
                    result, error = None, exc
            assert not lock.held and not alternate_lock.held
            return result, error, events, saved, task

        original = {"id": "task-1", "name": "Old", "stage": "running", "task_kind": "normal"}
        result, error, events, saved, task = exercise(original, {"name": "New", "accessory_ids": ["a"]})
        assert result is None and isinstance(error, HTTPException) and error.status_code == 409
        assert task["name"] == "New" and not saved and events[-1] == "lock.exit"

        incoming = {"id": "task-1", "name": "Old", "stage": "draft", "task_kind": "incoming_material_text"}
        _, error, events, saved, task = exercise(incoming, {"material_code": "  A  ", "inspection_user_ids": ["other"]})
        assert isinstance(error, HTTPException) and error.status_code == 409
        assert task["material_code"] == "A" and not saved and events[-1] == "lock.exit"

        incoming = {"id": "task-1", "name": "Old", "stage": "draft", "task_kind": "incoming_material_text"}
        result, error, events, saved, _ = exercise(incoming, {"material_name": " name "})
        assert error is None and result["material_name"] == "name" and saved
        assert ("public", True) in events and events.index("save") < events.index(("public", True)) < events.index("lock.exit")

        normal = {"id": "task-1", "name": "Old", "stage": "running", "task_kind": "normal", "agent_mcp": {"keep": True}}
        result, error, events, saved, _ = exercise(normal, {"params": {"epochs": "501"}}, public_failure=True)
        assert result is None and isinstance(error, RuntimeError) and saved[0]["params"]["epochs"] == 500
        assert normal["agent_mcp"] == {"keep": True} and events.index("lock.exit") < events.index(("public", False))

        normal = {"id": "task-1", "name": "Old", "stage": "draft", "task_kind": "normal"}
        _, error, events, saved, _ = exercise(normal, {"name": "New"}, save_failure=True)
        assert isinstance(error, RuntimeError) and events.index("unique") < events.index("save") < events.index("lock.exit")
        assert not any(isinstance(x, tuple) and x[0] == "public" for x in events)

        normal = {"id": "task-1", "name": "Old", "stage": "draft", "task_kind": "normal"}
        result, error, events, saved, _ = exercise(normal, {"name": "New"}, rebind_scope=True)
        assert error is None and result["name"] == "New" and saved
        assert events.index("config.load") < events.index("config.scope") < events.index("lock.enter")

        normal = {"id": "task-1", "name": "Old", "stage": "draft", "task_kind": "normal"}
        _, error, events, saved, task = exercise(normal, {"params": {"sample_count": float("inf")}})
        assert isinstance(error, OverflowError) and not saved and events[-1] == "lock.exit"

        draft = {"id": "task-1", "name": "Old", "stage": "draft", "task_kind": "normal", "agent_mcp": {"stale": True}}
        result, error, events, saved, task = exercise(draft, {
            "accessory_ids": ["a"], "accessory_counts": {"a": 3}, "detection_method": "training",
            "params": {"route": "label_text_compare", "sample_count": "49", "expected_production_count": "7"},
            "expected_production_count": 8, "auto_advance": True,
        })
        assert error is None and saved and result == task
        assert task["accessory_names"] == ["a"] and task["accessory_labels"] == {"a": "a"}
        assert task["accessory_counts"] == {"a": 3} and "agent_mcp" not in task
        assert task["detection_method"] == "label_text_compare" and task["params"]["route"] == "label_text_compare"
        assert "train_mode" not in task["params"] and task["params"]["sample_count"] == 50
        assert task["params"]["expected_production_count"] == 8 and task["auto_advance"] is True

        draft = {"id": "task-1", "name": "Old", "stage": "draft", "task_kind": "normal"}
        _, error, events, saved, task = exercise(draft, {"accessory_ids": ["a"]}, broken_names=True)
        assert isinstance(error, IndexError) and not saved and events[-1] == "lock.exit"
        assert task["accessory_ids"] == ["a"] and task["accessory_names"] == []

        _, error, events, saved, _ = exercise(None, {"name": "New"})
        assert isinstance(error, HTTPException) and error.status_code == 404 and not saved
        assert "access" not in events and events[-1] == "lock.exit"

        denied = HTTPException(status_code=403, detail="denied")
        _, error, events, saved, task = exercise({"id": "task-1", "stage": "draft"}, {"name": "New"}, access_error=denied)
        assert error is denied and not saved and "name" not in task and events[-1] == "lock.exit"

        normal = {"id": "task-1", "name": "Old", "stage": "draft", "task_kind": "normal"}
        result, error, events, saved, _ = exercise(normal, {}, rebind_lock=True)
        assert error is None and saved and "alternate.enter" in events and "lock.enter" not in events

        if not baseline_source:
            from local_inspection_service.pipeline.task_update import PipelineTaskUpdater
            from local_inspection_service.pipeline.task_update_ports import TaskUpdateAccess, TaskUpdatePolicy, TaskUpdateRuntime

            def unread():
                raise AssertionError("constructor read a capability")

            PipelineTaskUpdater(
                TaskUpdateAccess(**{item.name: unread for item in fields(TaskUpdateAccess)}),
                TaskUpdatePolicy(**{item.name: unread for item in fields(TaskUpdatePolicy)}),
                TaskUpdateRuntime(**{item.name: unread for item in fields(TaskUpdateRuntime)}),
            )

            def isolated(label):
                events = []
                lock = TracedLock(events, label)
                task = {"id": label, "stage": "draft", "name": label}
                access = replace(server._pipeline_task_updater.access,
                    current_user=lambda: (lambda: {"id": label}),
                    load_config=lambda: (lambda: {}),
                    scope_config=lambda: (lambda config, user: config),
                    load_task=lambda: (lambda task_id: task),
                    require_record_access=lambda: (lambda *args, **kwargs: None),
                )
                runtime = replace(server._pipeline_task_updater.runtime,
                    lock=lambda: lock,
                    now=lambda: (lambda: 123),
                    save_task=lambda: (lambda item: events.append(("save", label, item["id"]))),
                    public_task=lambda: (lambda item, config: {"instance": label, **item}),
                )
                return PipelineTaskUpdater(access, server._pipeline_task_updater.policy, runtime), events

            first, first_events = isolated("A")
            second, second_events = isolated("B")
            empty = PipelineTaskUpdateRequest()
            assert first.update("A", empty)["instance"] == "A"
            assert second.update("B", empty)["instance"] == "B"
            assert first.update("A", empty)["instance"] == "A"
            assert [item for item in first_events if isinstance(item, tuple)] == [("save", "A", "A")] * 2
            assert [item for item in second_events if isinstance(item, tuple)] == [("save", "B", "B")]

    print("PASS pipeline task update lock, mutation, error and late-binding contracts")


if __name__ == "__main__":
    main()
