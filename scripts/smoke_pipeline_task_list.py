"""Offline accepted-main/candidate contract for pipeline task list orchestration."""
import ast
from contextlib import ExitStack
from dataclasses import fields, replace
from pathlib import Path
import os
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Lock:
    def __init__(self, events):
        self.events = events
        self.held = False

    def __enter__(self):
        assert not self.held
        self.held = True
        self.events.append("lock.enter")

    def __exit__(self, *_):
        self.events.append("lock.exit")
        self.held = False


def main():
    with tempfile.TemporaryDirectory(prefix="pipeline-task-list-") as tmp, patch.dict(os.environ, {
        "LOCAL_INSPECTION_ROOT": tmp,
        "VANTALINE_DATA_STORE": "json",
        "LOCAL_INSPECTION_AUTO_RESUME_WORKER": "0",
        "VANTALINE_LABEL_INSPECTION_ENABLED": "false",
        "YOLO_AUTOINSTALL": "false",
    }):
        (Path(tmp) / "local_inspection_service" / "static").mkdir(parents=True)
        os.environ.pop("VANTALINE_POSTGRES_DSN", None)
        from local_inspection_service import server
        baseline_source = os.environ.get("VANTALINE_LIST_BASELINE_SOURCE")
        if baseline_source:
            tree = ast.parse(Path(baseline_source).read_text(encoding="utf-8-sig"))
            function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "get_pipeline_tasks")
            function.decorator_list = []
            exec(compile(ast.Module(body=[function], type_ignores=[]), baseline_source, "exec"), server.__dict__)
        else:
            route = next(route for route in server.app.routes if getattr(route, "path", "") == "/api/pipeline/tasks" and "GET" in getattr(route, "methods", set()))
            assert route.endpoint is server.get_pipeline_tasks

        def exercise(*, admin=False, user_id=None, now=10.0, last=0.0,
                     changed=(False, False, False, False, False),
                     tasks=None, ai_tasks=None, fail=None, rebind=False,
                     permission=True, repeat=False, mutate_on_schedule=False,
                     rebind_scope_after_save=False, rebind_sanitizer=False,
                     rebind_after_first_advance=False, fail_second_advance=False,
                     rebind_last_on_clock=False, rebind_interval_on_clock=False):
            events = []
            lock = Lock(events)
            user = {"id": "owner", "admin": admin}
            full = {"full": True}
            scoped = {"scope": 1}
            rescoped = {"scope": 2}
            supplied_tasks = tasks if tasks is not None else [
                {"id": "normal", "task_kind": "pipeline"},
                {"id": "incoming", "task_kind": "incoming_material_text"},
            ]
            supplied_ai = ai_tasks if ai_tasks is not None else [{"id": "ai-1"}, {"id": ""}, {"id": "ai-1"}]
            error = RuntimeError(fail or "unused")
            scopes = 0
            scheduled = []
            saves = []
            model_specs = ["model"]
            auto_states = [{"task_id": "normal"}]
            auto_by_id = {"normal": "state"}

            def mark(name, *args):
                events.append((name, *args, lock.held))
                if fail == name:
                    raise error

            def current_user():
                mark("user")
                return user

            def is_admin(actor):
                mark("admin", actor is user)
                return admin

            def config_load():
                mark("config.load")
                return full

            def scope(config, actor, target=None):
                nonlocal scopes
                scopes += 1
                mark("scope", scopes, config is full, actor is user, target)
                return scoped if scopes == 1 else rescoped

            def load_ai():
                mark("ai.load")
                return supplied_ai

            def load_tasks():
                mark("tasks.load")
                return supplied_tasks

            def monotonic():
                mark("clock")
                if rebind_last_on_clock:
                    server._pipeline_tasks_sync_last_at = now
                if rebind_interval_on_clock:
                    server.PIPELINE_TASKS_SYNC_MIN_INTERVAL_SECONDS = 20.0
                return now

            def ensure(config, value):
                mark("ensure", config is full, value is supplied_tasks)
                return changed[0]

            def save_config(config):
                mark("config.save", config is full)
                if rebind_scope_after_save:
                    server.scope_config_for_user = lambda config, actor, target: (events.append(("scope.rebound", target, lock.held)) or rescoped)

            def sync_ai(value, config, actor, target, *, ai_tasks):
                mark("ai.sync", value is supplied_tasks, config is (rescoped if changed[0] else scoped), actor is user, target, ai_tasks is supplied_ai)
                return changed[1]

            def sync_ready(value, config, actor, target):
                mark("ready.sync", value is supplied_tasks, actor is user, target)
                return changed[2]

            def defaults(value):
                mark("defaults", value is supplied_tasks)
                return changed[3]

            def sync_auto(value):
                mark("auto.sync", value is supplied_tasks)
                return changed[4], ["auto-1"], ["advance-1", "advance-1"]

            def save_tasks(value):
                mark("tasks.save", value is supplied_tasks)
                saves.append(value)

            def visible(task, actor, target):
                mark("visible", task["id"], actor is user, target)
                return task["id"] != "hidden"

            def incoming_allowed(task, actor):
                mark("incoming.allowed", task["id"], actor is user)
                return task["id"] != "incoming-denied"

            def has_permission(actor, permission_name):
                mark("permission", actor is user, permission_name)
                return permission

            def pregen(value):
                mark("pregen", [task["id"] for task in value])
                return ["rec-1"]

            def schedule_auto(ids, actor):
                mark("auto.schedule", tuple(ids), actor is user)
                scheduled.append("auto")
                if mutate_on_schedule:
                    supplied_tasks[0]["after_schedule"] = True
                if rebind:
                    server.schedule_pipeline_advance = lambda item, actor: mark("advance.rebound", item)

            def schedule_advance(item, actor):
                mark("advance.schedule", item, actor is user)
                scheduled.append(item)
                if rebind_after_first_advance and scheduled.count(item) == 1:
                    server.schedule_pipeline_advance = lambda task_id, actor: events.append(("advance.next", task_id, lock.held))
                if fail_second_advance and scheduled.count(item) == 2:
                    raise error

            def schedule_pregen(items, actor):
                mark("pregen.schedule", tuple(items), actor is user)
                scheduled.append("pregen")

            def specs(config):
                mark("specs", config is (rescoped if changed[0] and now - last >= 5 else scoped))
                return model_specs

            def states():
                mark("states")
                return auto_states

            def states_by_id(value):
                mark("states.by.id", len(value))
                return auto_by_id

            def public(task, config, **kwargs):
                mark("task.public", task["id"], kwargs["sanitize"], kwargs["ai_task_ids"] == ({"ai-1"} if supplied_ai else set()),
                     kwargs["trained_model_specs"] is model_specs, kwargs["auto_optimize_states"] is auto_states,
                     kwargs["auto_optimize_states_by_id"] is auto_by_id)
                if rebind_sanitizer:
                    server.public_path_sanitized = lambda value: (_ for _ in ()).throw(AssertionError("sanitizer rebound"))
                return {"id": task["id"], "after_schedule": task.get("after_schedule")}

            def agent_config():
                mark("agent.config")
                return {"mode": "agent"}

            def accessories(config, actor, target):
                mark("accessories", actor is user, target)
                return {"accessories": ["a"]}

            def sanitize(value):
                mark("sanitize", [item["id"] for item in value["items"]])
                return value

            replacements = {
                "current_auth_user": current_user,
                "user_is_admin": is_admin,
                "load_config": config_load,
                "scope_config_for_user": scope,
                "load_ai_detection_tasks": load_ai,
                "_pipeline_tasks_lock": lock,
                "load_pipeline_tasks": load_tasks,
                "time": SimpleNamespace(monotonic=monotonic),
                "_pipeline_tasks_sync_last_at": last,
                "PIPELINE_TASKS_SYNC_MIN_INTERVAL_SECONDS": 5.0,
                "ensure_pipeline_task_accessory_objects": ensure,
                "save_config": save_config,
                "sync_pipeline_ai_detection_tasks": sync_ai,
                "sync_ready_pipeline_ai_detection_tasks": sync_ready,
                "normalize_pipeline_task_auto_advance_defaults": defaults,
                "sync_and_auto_advance_pipeline": sync_auto,
                "save_pipeline_tasks": save_tasks,
                "record_visible_to_user": visible,
                "incoming_text_task_access_allowed": incoming_allowed,
                "user_has_permission": has_permission,
                "collect_pipeline_recommendation_pregen": pregen,
                "schedule_pipeline_auto_agent": schedule_auto,
                "schedule_pipeline_advance": schedule_advance,
                "schedule_pipeline_recommendation_pregen": schedule_pregen,
                "list_trained_model_specs": specs,
                "list_auto_optimize_states": states,
                "auto_optimize_states_by_task_id": states_by_id,
                "pipeline_task_public": public,
                "public_agent_config": agent_config,
                "pipeline_accessories_payload": accessories,
                "public_path_sanitized": sanitize,
            }
            with ExitStack() as stack:
                for name, value in replacements.items():
                    stack.enter_context(patch.object(server, name, value))
                try:
                    result = server.get_pipeline_tasks(user_id)
                    if repeat:
                        result = server.get_pipeline_tasks(user_id)
                    raised = None
                except Exception as exc:
                    result, raised = None, exc
                persisted_last = server._pipeline_tasks_sync_last_at
            assert not lock.held
            return result, raised, events, saves, scheduled, persisted_last, error

        result, error, events, saves, scheduled, last, _ = exercise(changed=(True, True, False, False, False), admin=True, user_id="other")
        assert error is None and last == 10.0 and len(saves) == 1
        assert scheduled == ["auto", "advance-1", "advance-1", "pregen"]
        assert [item["id"] for item in result["items"]] == ["normal", "incoming"]
        names = [event[0] if isinstance(event, tuple) else event for event in events]
        assert names == [
            "user", "admin", "config.load", "scope", "ai.load", "lock.enter", "tasks.load", "clock",
            "ensure", "config.save", "scope", "ai.sync", "ready.sync", "defaults", "auto.sync", "tasks.save",
            "visible", "visible", "incoming.allowed", "permission", "pregen", "lock.exit",
            "auto.schedule", "advance.schedule", "advance.schedule", "pregen.schedule", "specs", "states",
            "states.by.id", "task.public", "task.public", "agent.config", "accessories", "sanitize",
        ]
        assert events.index("lock.exit") < next(i for i, value in enumerate(events) if isinstance(value, tuple) and value[0] == "auto.schedule")
        assert all(event[2:] == (False, True, True, True, True, False) for event in events if isinstance(event, tuple) and event[0] == "task.public")

        result, error, events, saves, scheduled, last, _ = exercise(now=12.0, last=10.0, user_id="other")
        assert error is None and last == 10.0 and not saves and scheduled == ["pregen"]
        assert not any(isinstance(e, tuple) and e[0] in {"ensure", "ai.sync", "auto.sync"} for e in events)
        assert ("scope", 1, True, True, None, False) in events

        tasks = [
            {"id": "normal", "task_kind": "pipeline"},
            {"id": "hidden", "task_kind": "pipeline"},
            {"id": "incoming-denied", "task_kind": "incoming_material_text"},
            {"id": "incoming", "task_kind": "incoming_material_text"},
        ]
        result, error, events, *_ = exercise(tasks=tasks)
        assert error is None and [item["id"] for item in result["items"]] == ["normal", "incoming"]
        assert ("pregen", ["normal", "incoming"], True) in events

        result, error, events, saves, scheduled, last, failure = exercise(fail="ensure")
        assert error is failure and last == 10.0 and not saves and not scheduled
        assert events[-1] == "lock.exit"

        for point in ("user", "config.load", "ai.load", "tasks.load", "clock", "config.save", "ai.sync", "ready.sync", "defaults", "auto.sync", "tasks.save", "auto.schedule", "advance.schedule", "specs", "task.public", "sanitize"):
            kwargs = {"changed": (True, True, False, False, False), "fail": point}
            result, raised, events, saves, scheduled, last, failure = exercise(**kwargs)
            assert result is None and raised is failure, point
            assert last == (0.0 if point in {"user", "config.load", "ai.load", "tasks.load", "clock"} else 10.0), point

        result, error, events, saves, scheduled, last, _ = exercise(now=15.0, last=10.0)
        assert error is None and last == 15.0 and sum(isinstance(e, tuple) and e[0] == "ensure" for e in events) == 1

        result, error, events, saves, scheduled, last, _ = exercise(repeat=True)
        assert error is None and last == 10.0 and sum(isinstance(e, tuple) and e[0] == "ensure" for e in events) == 1
        assert sum(isinstance(e, tuple) and e[0] == "tasks.load" for e in events) == 2

        result, error, events, saves, scheduled, last, _ = exercise(tasks=[], ai_tasks=[])
        assert error is None and result["items"] == [] and result["agent"] == {"mode": "agent"}
        assert result["accessories"] == ["a"] and ("ai.load", False) in events and ("tasks.load", True) in events
        assert ("sanitize", [], False) in events

        result, error, events, saves, scheduled, last, _ = exercise(rebind_last_on_clock=True)
        assert error is None and last == 10.0 and not any(isinstance(e, tuple) and e[0] == "ensure" for e in events)

        result, error, events, saves, scheduled, last, _ = exercise(rebind_interval_on_clock=True)
        assert error is None and last == 0.0 and not any(isinstance(e, tuple) and e[0] == "ensure" for e in events)
        result, error, events, saves, scheduled, last, _ = exercise(permission=False)
        assert error is None and [item["id"] for item in result["items"]] == ["incoming"]
        assert ("pregen", ["incoming"], True) in events

        for changed_index in range(5):
            flags = tuple(index == changed_index for index in range(5))
            result, error, events, saves, scheduled, last, _ = exercise(changed=flags)
            assert error is None and len(saves) == (0 if changed_index == 0 else 1) and last == 10.0
        result, error, events, saves, scheduled, last, _ = exercise()
        assert error is None and not saves

        result, error, events, saves, scheduled, last, _ = exercise(changed=(True, False, False, False, False), rebind_scope_after_save=True)
        assert error is None and ("scope.rebound", None, True) in events

        result, error, events, saves, scheduled, last, _ = exercise(mutate_on_schedule=True, rebind_sanitizer=True)
        assert error is None and result["items"][0]["after_schedule"] is True

        result, error, events, saves, scheduled, last, _ = exercise(rebind_after_first_advance=True)
        assert error is None and ("advance.next", "advance-1", False) in events and scheduled == ["auto", "advance-1", "pregen"]

        result, raised, events, saves, scheduled, last, failure = exercise(fail_second_advance=True)
        assert result is None and raised is failure and scheduled == ["auto", "advance-1", "advance-1"]
        assert not any(isinstance(e, tuple) and e[0] in {"specs", "task.public"} for e in events)
        result, error, events, saves, scheduled, last, _ = exercise(rebind=True)
        assert error is None and scheduled == ["auto", "pregen"]
        assert [event for event in events if isinstance(event, tuple) and event[0] == "advance.rebound"] == [
            ("advance.rebound", "advance-1", False), ("advance.rebound", "advance-1", False),
        ]

        if not baseline_source:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from local_inspection_service.pipeline.task_list import PipelineTaskList
            from local_inspection_service.pipeline.task_list_api import register_pipeline_task_list_api
            from local_inspection_service.pipeline.task_list_ports import TaskListAccess, TaskListReconciliation, TaskListPresentation

            def unread():
                raise AssertionError("constructor read a capability")

            PipelineTaskList(*(
                cls(**{item.name: unread for item in fields(cls)})
                for cls in (TaskListAccess, TaskListReconciliation, TaskListPresentation)
            ))

            class HttpController:
                def list_tasks(self, user_id=None):
                    return {"user_id": user_id, "items": []}

            tiny_app = FastAPI()
            register_pipeline_task_list_api(tiny_app, HttpController())
            tiny_client = TestClient(tiny_app)
            assert tiny_client.get("/api/pipeline/tasks").json() == {"user_id": None, "items": []}
            assert tiny_client.get("/api/pipeline/tasks?user_id=other").json() == {"user_id": "other", "items": []}

            shared_last = [0.0]
            clock = [10.0]

            def isolated(label):
                events = []
                task = {"id": label, "task_kind": "pipeline"}
                task_lock = Lock(events)
                access = replace(server._pipeline_task_list.access,
                    current_user=lambda: (lambda: {"id": label}),
                    is_admin=lambda: (lambda user: False),
                    load_config=lambda: (lambda: {"owner": label}),
                    scope_config=lambda: (lambda config, user, target: config),
                    load_ai_tasks=lambda: (lambda: []),
                    visible=lambda: (lambda task, user, target: True),
                    incoming_allowed=lambda: (lambda task, user: True),
                    has_permission=lambda: (lambda user, permission: True),
                )
                reconciliation = replace(server._pipeline_task_list.reconciliation,
                    task_lock=lambda: task_lock,
                    load_tasks=lambda: (lambda: [task]),
                    monotonic=lambda: (lambda: clock[0]),
                    last_sync_at=lambda: shared_last[0],
                    set_last_sync_at=lambda value: shared_last.__setitem__(0, value),
                    min_interval=lambda: 5.0,
                    ensure_accessories=lambda: (lambda config, tasks: events.append(("sync", label)) or False),
                    save_config=lambda: (lambda config: None),
                    sync_ai_tasks=lambda: (lambda *args, **kwargs: False),
                    sync_ready_ai_tasks=lambda: (lambda *args: False),
                    normalize_auto_defaults=lambda: (lambda tasks: False),
                    sync_and_advance=lambda: (lambda tasks: (False, [], [])),
                    save_tasks=lambda: (lambda tasks: None),
                    collect_pregen=lambda: (lambda tasks: []),
                )
                presentation = replace(server._pipeline_task_list.presentation,
                    trained_specs=lambda: (lambda config: []),
                    optimize_states=lambda: (lambda: []),
                    optimize_by_id=lambda: (lambda states: {}),
                    public_task=lambda: (lambda task, config, **kwargs: {"id": task["id"]}),
                    public_agent_config=lambda: (lambda: {}),
                    accessories_payload=lambda: (lambda config, user, target: {}),
                    sanitize=lambda: (lambda value: value),
                )
                return PipelineTaskList(access, reconciliation, presentation), events

            first, first_events = isolated("A")
            second, second_events = isolated("B")
            assert first.list_tasks()["items"] == [{"id": "A"}]
            assert second.list_tasks()["items"] == [{"id": "B"}]
            clock[0] = 15.0
            assert first.list_tasks()["items"] == [{"id": "A"}]
            assert first_events.count(("sync", "A")) == 2 and ("sync", "B") not in second_events
            assert not any(isinstance(event, tuple) and "B" in event for event in first_events)
            assert not any(isinstance(event, tuple) and "A" in event for event in second_events)
    print("PASS pipeline list throttle, lock, side-effect and projection contracts")


if __name__ == "__main__":
    main()