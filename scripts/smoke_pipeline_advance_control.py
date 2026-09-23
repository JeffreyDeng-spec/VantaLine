"""Offline contracts for pipeline manual advance and cancel request boundaries."""
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
    def __init__(self, events, name):
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
    with tempfile.TemporaryDirectory(prefix="pipeline-advance-control-") as tmp, patch.dict(os.environ, {
        "LOCAL_INSPECTION_ROOT": tmp,
        "VANTALINE_DATA_STORE": "json",
        "LOCAL_INSPECTION_AUTO_RESUME_WORKER": "0",
        "VANTALINE_LABEL_INSPECTION_ENABLED": "false",
        "YOLO_AUTOINSTALL": "false",
    }):
        (Path(tmp) / "local_inspection_service" / "static").mkdir(parents=True)
        os.environ.pop("VANTALINE_POSTGRES_DSN", None)
        from local_inspection_service import server

        baseline_source = os.environ.get("VANTALINE_ADVANCE_CONTROL_BASELINE_SOURCE")
        if baseline_source:
            tree = ast.parse(Path(baseline_source).read_text(encoding="utf-8"))
            functions = [
                node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name in {
                    "advance_pipeline_task_endpoint", "cancel_pipeline_advance_endpoint",
                }
            ]
            assert len(functions) == 2
            for function in functions:
                function.decorator_list = []
            exec(compile(ast.Module(body=functions, type_ignores=[]), baseline_source, "exec"), server.__dict__)
        else:
            routes = {
                route.path: route.endpoint for route in server.app.routes
                if "POST" in getattr(route, "methods", set())
                and route.path in {
                    "/api/pipeline/tasks/{task_id}/advance",
                    "/api/pipeline/tasks/{task_id}/cancel-advance",
                }
            }
            assert routes["/api/pipeline/tasks/{task_id}/advance"] is server.advance_pipeline_task_endpoint
            assert routes["/api/pipeline/tasks/{task_id}/cancel-advance"] is server.cancel_pipeline_advance_endpoint

        def exercise(mode, *, task=None, second_task="same", already=False, inflight=False,
                     denied=False, fail=None, access_mutation=None, rebind_schedule=False,
                     rebind_lock=False, cancel_mutation=None, rebind_scope=False,
                     rebind_first_lock=False, rebind_inflight=False, rebind_public=False,
                     rebind_clock=False, schedule_result=None, public_alias=False,
                     fractional_clock=False, observe_inflight=False):
            events = []
            task_lock = TracedLock(events, "task")
            alternate = TracedLock(events, "alternate")
            registry_lock = TracedLock(events, "registry")
            user = {"id": "owner"}
            config = {"scope": "owner"}
            task = dict(task if task is not None else {"id": "pipe-1", "stage": "draft", "status": "ready"})
            if second_task == "same":
                second = task
            elif second_task is None:
                second = None
            else:
                second = dict(second_task)
            failure = RuntimeError(fail or "unused")
            denied_error = HTTPException(status_code=403, detail="denied")
            reads = 0
            saves = []
            ticks = iter([100.9, 101.8, 102.7] if fractional_clock else [100, 101, 102])
            clock_reads = 0

            def current_user():
                events.append("user")
                if fail == "user":
                    raise failure
                return user

            def load_config():
                events.append("config.load")
                if rebind_scope:
                    server.scope_config_for_user = lambda *args: (_ for _ in ()).throw(AssertionError("scope chosen too late"))
                if fail == "config":
                    raise failure
                return config

            def scope(value, actor):
                events.append(("config.scope", value is config, actor is user))
                if rebind_first_lock:
                    server._pipeline_tasks_lock = alternate
                if fail == "scope":
                    raise failure
                return value

            def load(task_id):
                nonlocal reads
                reads += 1
                events.append(("load", reads, task_lock.held, alternate.held))
                if fail == "load" or fail == "second_load" and reads == 2:
                    raise failure
                return task if reads == 1 else second

            def access(value, actor, *, write):
                events.append(("access", reads, value is (task if reads == 1 else second), actor is user, write, task_lock.held, alternate.held))
                if access_mutation:
                    value.update(access_mutation)
                if denied:
                    raise denied_error

            def sync(value):
                events.append(("sync", task_lock.held, alternate.held))
                if rebind_inflight:
                    server._pipeline_advance_inflight = {"pipe-1"}
                if fail == "sync":
                    raise failure

            def now():
                nonlocal clock_reads
                clock_reads += 1
                events.append("clock")
                if rebind_clock:
                    server.time = SimpleNamespace(time=lambda: (events.append("clock.rebound") or 202))
                if fail == "clock" or fail == "second_clock" and clock_reads == 2:
                    raise failure
                return next(ticks)

            def save(value):
                events.append(("save", reads, task_lock.held, alternate.held))
                saves.append(dict(value))
                if rebind_public:
                    server.pipeline_task_public = lambda task, config: (events.append("public.rebound") or task)
                if fail == "save":
                    raise failure

            def public(value, scoped):
                events.append(("public", reads, task_lock.held, alternate.held))
                if rebind_schedule:
                    server.schedule_pipeline_advance = lambda *args: events.append(("schedule.rebound", args[0]))
                if fail == "public":
                    raise failure
                return value if public_alias else dict(value)

            def schedule(task_id, actor):
                events.append(("schedule", task_id, actor is user, task_lock.held, alternate.held))
                if fail == "schedule":
                    raise failure
                return schedule_result

            def cancel(task_id):
                events.append(("cancel", task_id, task_lock.held, alternate.held))
                if rebind_lock:
                    server._pipeline_tasks_lock = alternate
                if cancel_mutation is not None and second is not None:
                    second.update(cancel_mutation)
                if fail == "cancel":
                    raise failure
                return inflight

            class ObservedInflight:
                def __contains__(self, task_id):
                    events.append(("inflight.contains", task_id, task_lock.held, alternate.held, registry_lock.held))
                    return already

            replacements = {
                "current_auth_user": current_user,
                "load_config": load_config,
                "scope_config_for_user": scope,
                "load_pipeline_task": load,
                "require_record_access": access,
                "sync_pipeline_task": sync,
                "time": SimpleNamespace(time=now),
                "save_pipeline_task": save,
                "pipeline_task_public": public,
                "schedule_pipeline_advance": schedule,
                "cancel_pipeline_advance": cancel,
                "_pipeline_tasks_lock": task_lock,
                "_pipeline_advance_registry_lock": registry_lock,
                "_pipeline_advance_inflight": ObservedInflight() if observe_inflight else ({"pipe-1"} if already else set()),
                "HTTPException": HTTPException,
            }
            with ExitStack() as stack:
                for name, value in replacements.items():
                    stack.enter_context(patch.object(server, name, value))
                try:
                    result = (server.advance_pipeline_task_endpoint if mode == "advance" else server.cancel_pipeline_advance_endpoint)("pipe-1")
                    error = None
                except Exception as exc:
                    result, error = None, exc
            assert not task_lock.held and not alternate.held and not registry_lock.held
            return result, error, events, saves, task, second, failure, denied_error

        result, error, events, saves, task, *_ = exercise("advance")
        assert error is None and result["advancing"] is True and result["advance_started_at"] == 100
        assert result["updated_at"] == 101 and result["last_error"] == "" and result["job_note"] == "正在推进…"
        assert len(saves) == 1 and saves[0]["advancing"] is True
        assert events == [
            "user", "config.load", ("config.scope", True, True), "task.enter",
            ("load", 1, True, False), ("access", 1, True, True, True, True, False),
            ("sync", True, False), "registry.enter", "registry.exit", "clock", "clock",
            ("save", 1, True, False), ("public", 1, True, False), "task.exit",
            ("schedule", "pipe-1", True, False, False),
        ]

        result, error, events, saves, *_ = exercise("advance", already=True)
        assert error is None and "advancing" not in result and not saves
        assert "clock" not in events and not any(isinstance(event, tuple) and event[0] == "schedule" for event in events)
        assert events.index("registry.enter") < events.index("registry.exit") < events.index(("public", 1, True, False))

        _, error, events, saves, *_ = exercise("advance", task={})
        assert isinstance(error, HTTPException) and error.status_code == 404 and not saves
        assert events[-1] == "task.exit"

        _, error, events, saves, _, _, _, denied_error = exercise("advance", denied=True)
        assert error is denied_error and not saves and "registry.enter" not in events

        for point, last in [
            ("user", "user"), ("config", "config.load"), ("scope", ("config.scope", True, True)),
            ("load", "task.exit"), ("sync", "task.exit"), ("clock", "task.exit"),
            ("save", "task.exit"), ("public", "task.exit"), ("schedule", ("schedule", "pipe-1", True, False, False)),
        ]:
            _, error, events, saves, _, _, failure, _ = exercise("advance", fail=point)
            assert error is failure and events[-1] == last
            assert ("schedule" in point) or not any(isinstance(event, tuple) and event[0] == "schedule" for event in events)

        result, error, events, saves, *_ = exercise("advance", access_mutation={"name": "authorized"})
        assert error is None and result["name"] == "authorized" and saves[0]["name"] == "authorized"

        result, error, events, saves, *_ = exercise("advance", rebind_schedule=True)
        assert error is None and ("schedule.rebound", "pipe-1") in events

        result, error, events, saves, *_ = exercise("advance", schedule_result=False)
        assert error is None and len(saves) == 1 and ("schedule", "pipe-1", True, False, False) in events

        result, error, events, saves, *_ = exercise("advance", rebind_scope=True, rebind_first_lock=True)
        assert error is None and "alternate.enter" in events and "task.enter" not in events
        assert events.index("config.load") < events.index(("config.scope", True, True)) < events.index("alternate.enter")

        result, error, events, saves, *_ = exercise("advance", rebind_inflight=True)
        assert error is None and not saves and "clock" not in events
        assert "registry.enter" in events and not any(isinstance(event, tuple) and event[0] == "schedule" for event in events)

        result, error, events, saves, *_ = exercise("advance", observe_inflight=True)
        assert error is None and ("inflight.contains", "pipe-1", True, False, True) in events
        assert events.index("registry.enter") < events.index(("inflight.contains", "pipe-1", True, False, True)) < events.index("registry.exit")

        result, error, events, saves, *_ = exercise("advance", fractional_clock=True)
        assert error is None and result["advance_started_at"] == 100 and result["updated_at"] == 101

        result, error, events, saves, task, _, failure, _ = exercise(
            "advance", task={"id": "pipe-1", "updated_at": 7}, fail="second_clock", fractional_clock=True,
        )
        assert result is None and error is failure and not saves
        assert task["advancing"] is True and task["advance_started_at"] == 100
        assert task["job_note"] == "正在推进…" and task["last_error"] == "" and task["updated_at"] == 7
        assert events.count("clock") == 2 and not any(isinstance(event, tuple) and event[0] == "schedule" for event in events)

        result, error, events, saves, *_ = exercise("advance", rebind_clock=True)
        assert error is None and result["advance_started_at"] == 100 and result["updated_at"] == 202
        assert events.count("clock") == 1 and events.count("clock.rebound") == 1

        result, error, events, saves, task, *_ = exercise("advance", rebind_public=True)
        assert error is None and result is task and "public.rebound" in events

        result, error, events, saves, task, *_ = exercise("advance", public_alias=True)
        assert error is None and result is task

        for point in ("clock", "save", "public", "schedule"):
            result, error, events, saves, task, _, failure, _ = exercise("advance", fail=point)
            assert result is None and error is failure and task["advancing"] is True
            assert len(saves) == (0 if point == "clock" else 1)
            assert not any(isinstance(event, tuple) and event[0] == "schedule" for event in events) if point != "schedule" else events[-1][0] == "schedule"

        paused = {"id": "pipe-1", "stage": "draft", "status": "running", "advancing": True, "advance_started_at": 5, "pause_requested": True}
        result, error, events, saves, *_ = exercise("cancel", task=paused)
        assert error is None and result["auto_advance"] is False and result["status"] == "stopped"
        assert "advancing" not in result and "advance_started_at" not in result and "pause_requested" not in result
        assert result["updated_at"] == 100 and result["job_note"] == "已暂停，自动推进已关闭。"
        assert len(saves) == 1 and events == [
            "user", "config.load", ("config.scope", True, True), "task.enter",
            ("load", 1, True, False), ("access", 1, True, True, True, True, False), "task.exit",
            ("cancel", "pipe-1", False, False), "task.enter", ("load", 2, True, False),
            "clock", ("save", 2, True, False), ("public", 2, True, False), "task.exit",
        ]

        result, error, events, saves, *_ = exercise("cancel", task=paused, inflight=True)
        assert error is None and result["status"] == "running" and result["advancing"] is True
        assert result["pause_requested"] is True and "检查点停止" in result["job_note"]
        assert len(saves) == 1 and events.index(("cancel", "pipe-1", False, False)) < events.index(("load", 2, True, False))

        for status in ("ready", "running", "stopped", "failed"):
            for stage in ("draft", "training"):
                result, error, *_ = exercise("cancel", task={"id": "pipe-1", "stage": stage, "status": status})
                assert error is None
                assert result["status"] == ("stopped" if stage == "draft" and status in {"ready", "running"} else status)

        _, error, events, saves, *_ = exercise("cancel", task={})
        assert isinstance(error, HTTPException) and error.status_code == 404
        assert not saves and not any(isinstance(event, tuple) and event[0] == "cancel" for event in events)

        _, error, events, saves, _, _, _, denied_error = exercise("cancel", denied=True)
        assert error is denied_error and not saves
        assert not any(isinstance(event, tuple) and event[0] == "cancel" for event in events)

        _, error, events, saves, *_ = exercise("cancel", second_task=None)
        assert isinstance(error, HTTPException) and error.status_code == 404 and not saves
        assert events.index(("cancel", "pipe-1", False, False)) < events.index(("load", 2, True, False))

        for point, last in [
            ("user", "user"), ("config", "config.load"), ("scope", ("config.scope", True, True)),
            ("load", "task.exit"), ("cancel", ("cancel", "pipe-1", False, False)),
            ("second_load", "task.exit"), ("clock", "task.exit"),
            ("save", "task.exit"), ("public", "task.exit"),
        ]:
            _, error, events, saves, _, _, failure, _ = exercise("cancel", fail=point)
            assert error is failure and events[-1] == last

        result, error, events, saves, first, second, *_ = exercise(
            "cancel", task={"id": "pipe-1", "stage": "draft", "status": "ready"},
            second_task={"id": "pipe-1", "stage": "training", "status": "running"},
            rebind_lock=True, cancel_mutation={"job_note": "from cancel"},
        )
        assert error is None and first["status"] == "ready" and second["status"] == "running"
        assert result["job_note"] == "已暂停，自动推进已关闭。"
        assert events.count("task.enter") == 1 and events.count("alternate.enter") == 1
        assert ("load", 2, False, True) in events and ("save", 2, False, True) in events
        assert sum(isinstance(event, tuple) and event[0] == "access" for event in events) == 1

        result, error, events, saves, *_ = exercise("cancel", task={"id": "pipe-1"})
        assert error is None and "status" not in result and result["auto_advance"] is False

        result, error, events, saves, *_ = exercise("cancel", rebind_scope=True, rebind_first_lock=True)
        assert error is None and events.count("alternate.enter") == 2 and "task.enter" not in events

        for point in ("save", "public"):
            result, error, events, saves, first, second, failure, _ = exercise("cancel", fail=point)
            assert result is None and error is failure and second["auto_advance"] is False
            assert len(saves) == 1 and events.index(("cancel", "pipe-1", False, False)) < events.index(("save", 2, True, False))

        if not baseline_source:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from local_inspection_service.pipeline.advance_control import PipelineAdvanceController
            from local_inspection_service.pipeline.advance_control_api import register_pipeline_advance_control_api
            from local_inspection_service.pipeline.advance_control_ports import AdvanceControlAccess, AdvanceControlRuntime

            def unread():
                raise AssertionError("constructor read a capability")

            PipelineAdvanceController(*(
                cls(**{item.name: unread for item in fields(cls)})
                for cls in (AdvanceControlAccess, AdvanceControlRuntime)
            ))

            class HttpController:
                def advance(self, task_id):
                    if task_id == "missing":
                        raise HTTPException(status_code=404, detail="流水线任务不存在")
                    return {"action": "advance", "task_id": task_id}

                def cancel(self, task_id):
                    if task_id == "forbidden":
                        raise HTTPException(status_code=403, detail="denied")
                    return {"action": "cancel", "task_id": task_id}

            tiny_app = FastAPI()
            register_pipeline_advance_control_api(tiny_app, HttpController())
            tiny_client = TestClient(tiny_app)
            assert tiny_client.post("/api/pipeline/tasks/one/advance").json() == {"action": "advance", "task_id": "one"}
            assert tiny_client.post("/api/pipeline/tasks/one/cancel-advance").json() == {"action": "cancel", "task_id": "one"}
            missing = tiny_client.post("/api/pipeline/tasks/missing/advance")
            assert missing.status_code == 404 and missing.json() == {"detail": "流水线任务不存在"}
            forbidden = tiny_client.post("/api/pipeline/tasks/forbidden/cancel-advance")
            assert forbidden.status_code == 403 and forbidden.json() == {"detail": "denied"}

            def isolated(label):
                events = []
                task = {"id": label, "stage": "draft", "status": "ready"}
                task_lock = TracedLock(events, label + ".task")
                registry_lock = TracedLock(events, label + ".registry")
                access = replace(server._pipeline_advance_controller.access,
                    current_user=lambda: (lambda: {"id": label}),
                    load_config=lambda: (lambda: {"owner": label}),
                    scope_config=lambda: (lambda config, user: config),
                    load_task=lambda: (lambda task_id: task),
                    require_record_access=lambda: (lambda task, user, **kwargs: events.append(("access", label))),
                )
                runtime = replace(server._pipeline_advance_controller.runtime,
                    task_lock=lambda: task_lock,
                    registry_lock=lambda: registry_lock,
                    inflight=lambda: set(),
                    sync_task=lambda: (lambda task: events.append(("sync", label))),
                    now=lambda: (lambda: 123),
                    save_task=lambda: (lambda task: events.append(("save", label, task["id"]))),
                    public_task=lambda: (lambda task, config: {"instance": label, **task}),
                    schedule_advance=lambda: (lambda task_id, user: events.append(("schedule", label, task_id))),
                    cancel_advance=lambda: (lambda task_id: events.append(("cancel", label, task_id)) or False),
                )
                return PipelineAdvanceController(access, runtime), events

            first, first_events = isolated("A")
            second, second_events = isolated("B")
            assert first.advance("one")["instance"] == "A"
            assert second.advance("two")["instance"] == "B"
            assert first.cancel("three")["instance"] == "A"
            assert second.cancel("four")["instance"] == "B"
            assert first.advance("five")["instance"] == "A"
            assert ("schedule", "A", "one") in first_events and ("schedule", "A", "five") in first_events
            assert ("schedule", "B", "two") in second_events
            assert ("cancel", "A", "three") in first_events and ("cancel", "B", "four") in second_events
            assert not any(isinstance(event, tuple) and "B" in event for event in first_events)
            assert not any(isinstance(event, tuple) and "A" in event for event in second_events)

    print("PASS pipeline advance/cancel request order, locks, errors and partial effects")


if __name__ == "__main__":
    main()
