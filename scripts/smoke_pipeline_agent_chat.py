"""Offline contract for pipeline Agent chat's two-lock, one-decision request."""
import ast
import copy as standard_copy
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
    def __init__(self, events, name="task"):
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
    with tempfile.TemporaryDirectory(prefix="pipeline-agent-chat-") as tmp, patch.dict(os.environ, {
        "LOCAL_INSPECTION_ROOT": tmp,
        "VANTALINE_DATA_STORE": "json",
        "LOCAL_INSPECTION_AUTO_RESUME_WORKER": "0",
        "VANTALINE_LABEL_INSPECTION_ENABLED": "false",
        "YOLO_AUTOINSTALL": "false",
    }):
        (Path(tmp) / "local_inspection_service" / "static").mkdir(parents=True)
        os.environ.pop("VANTALINE_POSTGRES_DSN", None)
        from local_inspection_service import server
        from local_inspection_service.schemas.pipeline import PipelineAgentChatRequest

        baseline_source = os.environ.get("VANTALINE_CHAT_BASELINE_SOURCE")
        if baseline_source:
            tree = ast.parse(Path(baseline_source).read_text(encoding="utf-8"))
            function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "pipeline_agent_chat")
            function.decorator_list = []
            exec(compile(ast.Module(body=[function], type_ignores=[]), baseline_source, "exec"), server.__dict__)
        else:
            route = next(route for route in server.app.routes if getattr(route, "path", "") == "/api/pipeline/tasks/{task_id}/chat" and "POST" in getattr(route, "methods", set()))
            assert route.endpoint is server.pipeline_agent_chat

        def exercise(*, message=" Hello ", first=None, second="same", fail=None,
                     deny_first=False, deny_second=False, pending=(), rebind_lock=False,
                     rebind_load=False, rebind_commit=False, rebind_schedule=False,
                     mutate_snapshot=False, second_method=None, schedule_false=False,
                     rebind_scope_on_load=False, rebind_schedule_after_first=False,
                     public_object=None):
            events = []
            lock = TracedLock(events)
            alternate = TracedLock(events, "alternate")
            user = {"id": "owner"}
            config = {"scope": "owner"}
            first = dict(first if first is not None else {"id": "pipe-1", "detection_method": "yolo", "nested": {"value": 1}})
            if second == "same":
                second_task = first
            elif second is None:
                second_task = None
            else:
                second_task = dict(second)
            if second_method is not None and second_task is not None:
                second_task["detection_method"] = second_method
            failure = RuntimeError(fail or "unused")
            denied_error = HTTPException(status_code=403, detail="denied")
            decision = {"decision": "resume"}
            reads = 0
            saves = []
            scheduled = []

            def current_user():
                events.append("user")
                if fail == "user":
                    raise failure
                return user

            def load_config():
                events.append("config.load")
                if rebind_scope_on_load:
                    server.scope_config_for_user = lambda config, actor: (_ for _ in ()).throw(AssertionError("scope rebound"))
                if fail == "config":
                    raise failure
                return config

            def scope(value, actor):
                events.append(("config.scope", value is config, actor is user))
                if fail == "scope":
                    raise failure
                return value

            def bounded(value, limit):
                events.append(("bounded", value, limit))
                if fail == "bounded":
                    raise failure
                return str(value or "").strip()[:limit]

            def load(task_id):
                nonlocal reads
                reads += 1
                events.append(("load", reads, lock.held, alternate.held))
                if fail == "first_load" and reads == 1 or fail == "second_load" and reads == 2:
                    raise failure
                return first if reads == 1 else second_task

            def access(task, actor, *, write):
                events.append(("access", reads, actor is user, write, lock.held, alternate.held))
                if deny_first and reads == 1 or deny_second and reads == 2:
                    raise denied_error

            def normalize(value):
                events.append(("normalize", value))
                return value

            def uses_training(value):
                events.append(("training", value))
                return value == "yolo"

            def deepcopy(value):
                events.append(("deepcopy", lock.held, alternate.held))
                if fail == "deepcopy":
                    raise failure
                return standard_copy.deepcopy(value)

            def decide(snapshot, scoped, *, user_message, trigger):
                events.append(("decide", snapshot is first, snapshot.get("nested") is first.get("nested"), scoped is config, user_message, trigger, lock.held, alternate.held))
                if mutate_snapshot:
                    snapshot["nested"]["value"] = 99
                if rebind_lock:
                    server._pipeline_tasks_lock = alternate
                if rebind_load:
                    server.load_pipeline_task = lambda task_id: (events.append(("load.rebound", task_id)) or second_task)
                if rebind_commit:
                    server.commit_pipeline_agent_turn = lambda *args, **kwargs: events.append(("commit.rebound", args[3]))
                if fail == "decide":
                    raise failure
                return decision

            def commit(task, scoped, actor, text, actual_decision, trigger, *, pending_advances):
                events.append(("commit", reads, task is second_task, scoped is config, actor is user, text, actual_decision is decision, trigger, lock.held, alternate.held))
                task["chat_done"] = True
                pending_advances.extend(pending)
                if fail == "commit":
                    raise failure

            def save(task):
                events.append(("save", reads, lock.held, alternate.held))
                saves.append(dict(task))
                if fail == "save":
                    raise failure

            def public(task, scoped):
                events.append(("public", reads, lock.held, alternate.held))
                if rebind_schedule:
                    server.schedule_pipeline_advance = lambda task_id, actor: events.append(("schedule.rebound", task_id))
                if fail == "public":
                    raise failure
                return public_object if public_object is not None else dict(task)

            def schedule(task_id, actor):
                events.append(("schedule", task_id, actor is user, lock.held, alternate.held))
                scheduled.append(task_id)
                if rebind_schedule_after_first and len(scheduled) == 1:
                    server.schedule_pipeline_advance = lambda task_id, actor: events.append(("schedule.rebound.next", task_id))
                if fail == "schedule" and len(scheduled) == 1 or fail == "second_schedule" and len(scheduled) == 2:
                    raise failure
                return False if schedule_false else True

            replacements = {
                "current_auth_user": current_user,
                "load_config": load_config,
                "scope_config_for_user": scope,
                "bounded_text": bounded,
                "_pipeline_tasks_lock": lock,
                "load_pipeline_task": load,
                "require_record_access": access,
                "normalize_pipeline_detection_method": normalize,
                "pipeline_method_uses_training": uses_training,
                "copy": SimpleNamespace(deepcopy=deepcopy),
                "agent_pipeline_decide": decide,
                "commit_pipeline_agent_turn": commit,
                "save_pipeline_task": save,
                "pipeline_task_public": public,
                "schedule_pipeline_advance": schedule,
                "HTTPException": HTTPException,
            }
            with ExitStack() as stack:
                for name, value in replacements.items():
                    stack.enter_context(patch.object(server, name, value))
                try:
                    result = server.pipeline_agent_chat("pipe-1", PipelineAgentChatRequest(message=message))
                    error = None
                except Exception as exc:
                    result, error = None, exc
            assert not lock.held and not alternate.held
            return result, error, events, saves, scheduled, first, second_task, failure, denied_error

        result, error, events, saves, scheduled, first, *_ = exercise(pending=("a", "b"))
        assert error is None and result["chat_done"] is True and scheduled == ["a", "b"]
        assert len(saves) == 1 and first["nested"]["value"] == 1
        assert events == [
            "user", "config.load", ("config.scope", True, True), ("bounded", " Hello ", 1000),
            "task.enter", ("load", 1, True, False), ("access", 1, True, True, True, False),
            ("normalize", "yolo"), ("training", "yolo"), ("deepcopy", True, False), "task.exit",
            ("decide", False, False, True, "Hello", "chat", False, False),
            "task.enter", ("load", 2, True, False), ("access", 2, True, True, True, False),
            ("commit", 2, True, True, True, "Hello", True, "chat", True, False),
            ("save", 2, True, False), ("public", 2, True, False), "task.exit",
            ("schedule", "a", True, False, False), ("schedule", "b", True, False, False),
        ]

        result, error, events, saves, *_ = exercise(message="  ")
        assert isinstance(error, HTTPException) and error.status_code == 400 and not saves
        assert not any(isinstance(event, tuple) and event[0] == "load" for event in events)

        result, error, events, saves, *_ = exercise(first={})
        assert isinstance(error, HTTPException) and error.status_code == 404 and not saves
        assert not any(isinstance(event, tuple) and event[0] == "decide" for event in events)

        result, error, events, saves, *_ = exercise(first={"id": "pipe-1", "detection_method": "ai"})
        assert isinstance(error, HTTPException) and error.status_code == 409 and not saves
        assert not any(isinstance(event, tuple) and event[0] == "decide" for event in events)

        result, error, events, saves, *_ = exercise(first={"id": "pipe-1", "params": {"train_mode": "yolo"}})
        assert error is None and result["chat_done"] is True and ("normalize", "yolo") in events

        _, error, events, saves, _, _, _, _, denied_error = exercise(deny_first=True)
        assert error is denied_error and not saves and not any(isinstance(event, tuple) and event[0] == "decide" for event in events)

        _, error, events, saves, _, _, _, _, denied_error = exercise(deny_second=True)
        assert error is denied_error and not saves and sum(isinstance(event, tuple) and event[0] == "decide" for event in events) == 1

        result, error, events, saves, scheduled, first, second, *_ = exercise(second=None)
        assert isinstance(error, HTTPException) and error.status_code == 404 and not saves and not scheduled
        assert sum(isinstance(event, tuple) and event[0] == "decide" for event in events) == 1

        result, error, events, saves, scheduled, first, second, *_ = exercise(
            second={"id": "pipe-1", "detection_method": "ai"}, mutate_snapshot=True, second_method="ai",
        )
        assert error is None and result["chat_done"] is True and first.get("chat_done") is None and second["chat_done"] is True
        assert first["nested"]["value"] == 1
        assert sum(isinstance(event, tuple) and event[0] == "training" for event in events) == 1

        result, error, events, saves, scheduled, first, second, *_ = exercise(rebind_lock=True, rebind_load=True, rebind_commit=True)
        assert error is None and ("load.rebound", "pipe-1") in events and ("commit.rebound", "Hello") in events
        assert events.count("task.enter") == 1 and events.count("alternate.enter") == 1
        assert not saves or ("save", 1, False, True) in events

        result, error, events, saves, scheduled, *_ = exercise(pending=("a", "a", "b"), schedule_false=True)
        assert error is None and scheduled == ["a", "a", "b"] and len(saves) == 1

        result, error, events, *_ = exercise(rebind_scope_on_load=True)
        assert error is None and result["chat_done"] is True and ("config.scope", True, True) in events

        public_object = {"identity": object()}
        result, error, *_ = exercise(public_object=public_object)
        assert error is None and result is public_object

        result, error, events, saves, scheduled, *_ = exercise(pending=("a", "b"), rebind_schedule_after_first=True)
        assert error is None and scheduled == ["a"] and ("schedule.rebound.next", "b") in events
        result, error, events, saves, scheduled, *_ = exercise(pending=("a",), rebind_schedule=True)
        assert error is None and ("schedule.rebound", "a") in events and not scheduled

        result, error, events, saves, scheduled, _, _, failure, _ = exercise(pending=("a", "b"), fail="second_schedule")
        assert result is None and error is failure and len(saves) == 1 and scheduled == ["a", "b"]
        assert events[-1] == ("schedule", "b", True, False, False)

        for point in ("user", "config", "scope", "bounded", "first_load", "deepcopy", "decide", "second_load", "commit", "save", "public", "schedule"):
            result, error, events, saves, scheduled, first, second, failure, _ = exercise(pending=("a",), fail=point)
            assert result is None and error is failure
            assert not scheduled if point != "schedule" else scheduled == ["a"]
            if point in {"commit", "save", "public", "schedule"}:
                assert second["chat_done"] is True
            if point in {"save", "public", "schedule"}:
                assert len(saves) == 1

        if not baseline_source:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from local_inspection_service.pipeline.agent_chat import PipelineAgentChat
            from local_inspection_service.pipeline.agent_chat_api import register_pipeline_agent_chat_api
            from local_inspection_service.pipeline.agent_chat_ports import AgentChatAccess, AgentChatRuntime

            def unread():
                raise AssertionError("constructor read a capability")

            PipelineAgentChat(*(
                cls(**{item.name: unread for item in fields(cls)})
                for cls in (AgentChatAccess, AgentChatRuntime)
            ))

            class HttpController:
                def chat(self, task_id, request):
                    if task_id == "missing":
                        raise HTTPException(status_code=404, detail="流水线任务不存在")
                    if task_id == "forbidden":
                        raise HTTPException(status_code=403, detail="denied")
                    return {"task_id": task_id, "message": request.message}

            tiny_app = FastAPI()
            register_pipeline_agent_chat_api(tiny_app, HttpController())
            tiny_client = TestClient(tiny_app)
            assert tiny_client.post("/api/pipeline/tasks/one/chat", json={"message": "hi"}).json() == {"task_id": "one", "message": "hi"}
            missing = tiny_client.post("/api/pipeline/tasks/missing/chat", json={"message": "hi"})
            assert missing.status_code == 404 and missing.json() == {"detail": "流水线任务不存在"}
            forbidden = tiny_client.post("/api/pipeline/tasks/forbidden/chat", json={"message": "hi"})
            assert forbidden.status_code == 403 and forbidden.json() == {"detail": "denied"}
            assert tiny_client.post("/api/pipeline/tasks/one/chat", json={}).status_code == 422

            def isolated(label):
                events = []
                task = {"id": label, "detection_method": "yolo"}
                lock = TracedLock(events, label)
                access = replace(server._pipeline_agent_chat.access,
                    current_user=lambda: (lambda: {"id": label}),
                    load_config=lambda: (lambda: {"owner": label}),
                    scope_config=lambda: (lambda config, user: config),
                    bounded_text=lambda: (lambda text, limit: text.strip()),
                    load_task=lambda: (lambda task_id: task),
                    require_record_access=lambda: (lambda task, user, **kwargs: events.append(("access", label))),
                )
                runtime = replace(server._pipeline_agent_chat.runtime,
                    task_lock=lambda: lock,
                    normalize_method=lambda: (lambda value: value),
                    uses_training=lambda: (lambda value: True),
                    deepcopy=lambda: standard_copy.deepcopy,
                    decide=lambda: (lambda snapshot, config, **kwargs: events.append(("decide", label)) or {"next": label}),
                    commit_turn=lambda: (lambda task, config, user, message, decision, trigger, *, pending_advances: events.append(("commit", label, decision["next"])) or pending_advances.append(label)),
                    save_task=lambda: (lambda task: events.append(("save", label))),
                    public_task=lambda: (lambda task, config: {"instance": label}),
                    schedule_advance=lambda: (lambda task_id, user: events.append(("schedule", label, task_id))),
                )
                return PipelineAgentChat(access, runtime), events

            first, first_events = isolated("A")
            second, second_events = isolated("B")
            for controller, label in ((first, "A"), (second, "B"), (first, "A")):
                assert controller.chat("one", PipelineAgentChatRequest(message=" hi ")) == {"instance": label}
            assert first_events.count(("decide", "A")) == 2 and second_events.count(("decide", "B")) == 1
            assert first_events.count(("schedule", "A", "A")) == 2
            assert second_events.count(("schedule", "B", "B")) == 1
            assert not any(isinstance(event, tuple) and "B" in event for event in first_events)
            assert not any(isinstance(event, tuple) and "A" in event for event in second_events)
    print("PASS pipeline chat two-lock snapshot, decision and scheduling contracts")


if __name__ == "__main__":
    main()
