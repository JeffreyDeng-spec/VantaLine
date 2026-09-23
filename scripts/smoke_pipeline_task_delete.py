"""Offline contract for pipeline task deletion and partial cleanup effects."""
import ast
from contextlib import ExitStack
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace
import os
import sys
import tempfile
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TracedLock:
    def __init__(self, events, name="lock"):
        self.events = events
        self.name = name
        self.held = False

    def __enter__(self):
        assert not self.held
        self.held = True
        self.events.append(self.name + ".enter")

    def __exit__(self, *_):
        self.events.append(self.name + ".exit")
        self.held = False


def main():
    with tempfile.TemporaryDirectory(prefix="pipeline-delete-") as tmp, patch.dict(os.environ, {
        "LOCAL_INSPECTION_ROOT": tmp,
        "VANTALINE_DATA_STORE": "json",
        "LOCAL_INSPECTION_AUTO_RESUME_WORKER": "0",
        "VANTALINE_LABEL_INSPECTION_ENABLED": "false",
        "YOLO_AUTOINSTALL": "false",
    }):
        (Path(tmp) / "local_inspection_service" / "static").mkdir(parents=True)
        os.environ.pop("VANTALINE_POSTGRES_DSN", None)
        from local_inspection_service import server

        baseline_source = os.environ.get("VANTALINE_DELETE_BASELINE_SOURCE")
        if baseline_source:
            tree = ast.parse(Path(baseline_source).read_text(encoding="utf-8"))
            function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "delete_pipeline_task")
            function.decorator_list = []
            exec(compile(ast.Module(body=[function], type_ignores=[]), baseline_source, "exec"), server.__dict__)
        else:
            route = next(route for route in server.app.routes if getattr(route, "path", "") == "/api/pipeline/tasks/{task_id}" and "DELETE" in getattr(route, "methods", set()))
            assert route.endpoint is server.delete_pipeline_task

        def exercise(task=None, *, fail=None, denied=False, row_deleted=True,
                     absent=False, missing=(), rebind_lock=False, rebind_model=False,
                     access_mutation=None, cleanup_values=None):
            events = []
            lock = TracedLock(events)
            alternate = TracedLock(events, "alternate")
            user = {"id": "owner"}
            failure = RuntimeError(fail or "unused")
            task = dict(task or {}) if not absent else None

            def current_user():
                events.append("user")
                if fail == "user":
                    raise failure
                return user

            def cancel(task_id):
                events.append(("cancel", task_id))
                if rebind_lock:
                    server._pipeline_tasks_lock = alternate
                if fail == "cancel":
                    raise failure
                return True

            def load(task_id):
                events.append(("load", task_id, lock.held, alternate.held))
                if fail == "load":
                    raise failure
                return task

            def access(value, actor, *, write):
                events.append(("access", value is task, actor is user, write, lock.held, alternate.held))
                if access_mutation:
                    value.update(access_mutation)
                if denied:
                    raise denied_error

            denied_error = HTTPException(status_code=403, detail="denied")

            def delete_row(task_id):
                events.append(("row", task_id, lock.held, alternate.held))
                if fail == "row":
                    raise failure
                return row_deleted

            def retire(kind):
                def delete(identifier, actor, *, missing_ok):
                    events.append((kind, identifier, actor is user, missing_ok, lock.held, alternate.held))
                    if fail == kind:
                        raise failure
                    if rebind_model and kind == "dataset":
                        server.delete_training_model_resource = lambda *args, **kwargs: (events.append(("model.rebound", args[0])) or {"id": args[0]})
                    if (kind, identifier) in missing:
                        return None
                    if cleanup_values and (kind, identifier) in cleanup_values:
                        return cleanup_values[kind, identifier]
                    return {"id": identifier}
                return delete

            replacements = {
                "current_auth_user": current_user,
                "cancel_pipeline_advance": cancel,
                "_pipeline_tasks_lock": lock,
                "load_pipeline_task": load,
                "require_record_access": access,
                "delete_pipeline_task_row": delete_row,
                "delete_training_dataset_resource": retire("dataset"),
                "delete_training_model_resource": retire("model"),
                "delete_training_task_record": retire("job"),
                "delete_ai_detection_task_record": retire("ai"),
                "HTTPException": HTTPException,
            }
            with ExitStack() as stack:
                for name, value in replacements.items():
                    stack.enter_context(patch.object(server, name, value))
                try:
                    result = server.delete_pipeline_task("pipe-1")
                    error = None
                except Exception as exc:
                    result, error = None, exc
            assert not lock.held and not alternate.held
            return result, error, events, failure, denied_error

        linked = {
            "samples_task_id": "job-1", "training_task_id": "job-1",
            "dataset_id": "dataset-1", "model_run_id": "model-1", "ai_task_id": "ai-1",
        }
        result, error, events, *_ = exercise(linked)
        assert error is None and result == {
            "status": "deleted", "deleted_task_id": "pipe-1",
            "deleted_datasets": ["dataset-1", "job-1"],
            "deleted_models": ["model-1", "job-1"],
            "deleted_ai_tasks": ["ai-1"], "deleted_training_jobs": ["job-1", "job-1"],
        }
        assert events[:5] == ["user", ("cancel", "pipe-1"), "lock.enter", ("load", "pipe-1", True, False), ("access", True, True, True, True, False)]
        assert events[5:7] == [("row", "pipe-1", True, False), "lock.exit"]
        assert [event[0] for event in events[7:]] == ["dataset", "dataset", "model", "model", "job", "job", "ai"]
        assert all(event[2:] == (True, True, False, False) for event in events[7:])

        result, error, events, *_ = exercise({}, absent=True)
        assert error is None and result["status"] == "deleted"
        assert [event[0] for event in events if isinstance(event, tuple)] == ["cancel", "load", "row"]
        assert not any(event == "access" for event in events)

        result, error, events, *_ = exercise({})
        assert error is None and not any(isinstance(event, tuple) and event[0] == "access" for event in events)

        result, error, events, *_ = exercise({}, row_deleted=False)
        assert isinstance(error, HTTPException) and error.status_code == 404
        assert events[-1] == "lock.exit"

        result, error, events, _, denied_error = exercise(linked, denied=True)
        assert error is denied_error and events[-1] == "lock.exit"
        assert not any(isinstance(event, tuple) and event[0] == "row" for event in events)

        for point, last in [("user", "user"), ("cancel", ("cancel", "pipe-1")), ("load", "lock.exit"), ("row", "lock.exit")]:
            _, error, events, failure, _ = exercise(linked, fail=point)
            assert error is failure and events[-1] == last

        for kind, previous in [
            ("dataset", []), ("model", ["dataset", "dataset"]),
            ("job", ["dataset", "dataset", "model", "model"]),
            ("ai", ["dataset", "dataset", "model", "model", "job", "job"]),
        ]:
            _, error, events, failure, _ = exercise(linked, fail=kind)
            assert error is failure
            cleanup = [event[0] for event in events if isinstance(event, tuple) and event[0] in {"dataset", "model", "job", "ai"}]
            assert cleanup == previous + [kind]
            assert events.index("lock.exit") < events.index(next(event for event in events if isinstance(event, tuple) and event[0] == kind))

        result, error, events, *_ = exercise(linked, missing={("dataset", "job-1"), ("model", "model-1"), ("job", "job-1"), ("ai", "ai-1")})
        assert error is None and result["deleted_datasets"] == ["dataset-1"]
        assert result["deleted_models"] == ["job-1"] and result["deleted_training_jobs"] == [] and result["deleted_ai_tasks"] == []
        assert [event[0] for event in events if isinstance(event, tuple) and event[0] == "job"] == ["job", "job"]

        result, error, events, *_ = exercise(linked, rebind_lock=True)
        assert error is None and "alternate.enter" in events and "lock.enter" not in events
        assert ("row", "pipe-1", False, True) in events

        result, error, events, *_ = exercise(linked, rebind_model=True)
        assert error is None and ("model.rebound", "model-1") in events and ("model.rebound", "job-1") in events

        result, error, events, *_ = exercise(linked, access_mutation={"samples_task_id": "changed", "dataset_id": " changed "})
        assert error is None
        assert result["deleted_datasets"] == [" changed ", "changed"]
        assert result["deleted_models"] == ["model-1", "job-1"]
        assert result["deleted_training_jobs"] == ["changed", "job-1"]
        assert ("dataset", " changed ", True, True, False, False) in events

        result, error, events, *_ = exercise({
            "samples_task_id": " duplicate ", "training_task_id": " duplicate ",
            "dataset_id": "  ", "model_run_id": 0, "ai_task_id": "0",
        })
        assert error is None and result["deleted_datasets"] == [" duplicate "]
        assert result["deleted_models"] == [" duplicate "]
        assert result["deleted_training_jobs"] == [" duplicate ", " duplicate "]
        assert result["deleted_ai_tasks"] == ["0"]

        result, error, events, *_ = exercise({
            "samples_task_id": "same", "training_task_id": "same",
            "dataset_id": "same", "model_run_id": "same",
        })
        assert error is None
        assert result["deleted_datasets"] == ["same"] and result["deleted_models"] == ["same"]
        assert result["deleted_training_jobs"] == ["same", "same"]
        assert [event[0] for event in events if isinstance(event, tuple) and event[0] in {"dataset", "model", "job"}] == [
            "dataset", "model", "job", "job",
        ]

        result, error, events, *_ = exercise(linked, cleanup_values={
            ("dataset", "dataset-1"): False,
            ("dataset", "job-1"): {"id": "normalized-other"},
            ("model", "model-1"): 0,
            ("model", "job-1"): "ok",
            ("job", "job-1"): [],
            ("ai", "ai-1"): {"id": "different"},
        })
        assert error is None and result["deleted_datasets"] == ["job-1"]
        assert result["deleted_models"] == ["job-1"]
        assert result["deleted_training_jobs"] == [] and result["deleted_ai_tasks"] == ["ai-1"]

        if not baseline_source:
            from local_inspection_service.pipeline.task_delete import PipelineTaskDeleter
            from local_inspection_service.pipeline.task_delete_ports import TaskDeleteAccess, TaskDeleteRuntime, TaskDeleteCleanup

            def unread():
                raise AssertionError("constructor read a capability")

            PipelineTaskDeleter(*(
                cls(**{item.name: unread for item in fields(cls)})
                for cls in (TaskDeleteAccess, TaskDeleteRuntime, TaskDeleteCleanup)
            ))

            def isolated(label):
                events = []
                lock = TracedLock(events, label)
                access = replace(server._pipeline_task_deleter.access,
                    current_user=lambda: (lambda: {"id": label}),
                    require_record_access=lambda: (lambda task, user, **kwargs: None),
                    load_task=lambda: (lambda task_id: {
                        "id": task_id, "dataset_id": "data-" + label, "model_run_id": "model-" + label,
                        "samples_task_id": "job-" + label, "training_task_id": "job-" + label,
                        "ai_task_id": "ai-" + label,
                    }),
                )
                runtime = replace(server._pipeline_task_deleter.runtime,
                    cancel_advance=lambda: (lambda task_id: events.append(("cancel", label))),
                    lock=lambda: lock,
                    delete_task_row=lambda: (lambda task_id: events.append(("row", label)) or True),
                )
                cleanup = replace(server._pipeline_task_deleter.cleanup,
                    delete_dataset=lambda: (lambda item_id, *args, **kwargs: events.append(("dataset", label, item_id)) or {"id": item_id}),
                    delete_model=lambda: (lambda item_id, *args, **kwargs: events.append(("model", label, item_id)) or {"id": item_id}),
                    delete_training_job=lambda: (lambda item_id, *args, **kwargs: events.append(("job", label, item_id)) or {"id": item_id}),
                    delete_ai_task=lambda: (lambda item_id, *args, **kwargs: events.append(("ai", label, item_id)) or {"id": item_id}),
                )
                return PipelineTaskDeleter(access, runtime, cleanup), events

            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from local_inspection_service.pipeline.task_delete_api import register_pipeline_task_delete_api

            class HttpDeleter:
                def delete(self, task_id):
                    if task_id == "forbidden":
                        raise HTTPException(status_code=403, detail="denied")
                    if task_id == "missing":
                        raise HTTPException(status_code=404, detail="流水线任务不存在")
                    return {"status": "deleted", "deleted_task_id": task_id}

            tiny_app = FastAPI()
            register_pipeline_task_delete_api(tiny_app, HttpDeleter())
            tiny_client = TestClient(tiny_app)
            assert tiny_client.delete("/api/pipeline/tasks/one").json() == {"status": "deleted", "deleted_task_id": "one"}
            denied_response = tiny_client.delete("/api/pipeline/tasks/forbidden")
            assert denied_response.status_code == 403 and denied_response.json() == {"detail": "denied"}
            missing_response = tiny_client.delete("/api/pipeline/tasks/missing")
            assert missing_response.status_code == 404 and missing_response.json() == {"detail": "流水线任务不存在"}

            first, first_events = isolated("A")
            second, second_events = isolated("B")
            assert first.delete("one")["deleted_ai_tasks"] == ["ai-A"]
            assert second.delete("two")["deleted_ai_tasks"] == ["ai-B"]
            assert first.delete("three")["deleted_ai_tasks"] == ["ai-A"]
            def expected(label):
                return [
                    ("cancel", label), label + ".enter", ("row", label), label + ".exit",
                    ("dataset", label, "data-" + label), ("dataset", label, "job-" + label),
                    ("model", label, "model-" + label), ("model", label, "job-" + label),
                    ("job", label, "job-" + label), ("job", label, "job-" + label),
                    ("ai", label, "ai-" + label),
                ]
            assert first_events == expected("A") * 2
            assert second_events == expected("B")

    print("PASS pipeline task delete authorization, ordering, partial cleanup and late bindings")


if __name__ == "__main__":
    main()
