"""Offline contract for pipeline task creation and its partial side effects."""
import ast
from dataclasses import fields, replace
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
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
        self.events.append(self.label + ".enter")

    def __exit__(self, *_):
        self.events.append(self.label + ".exit")
        self.held = False


def main():
    with tempfile.TemporaryDirectory(prefix="pipeline-create-") as tmp, patch.dict(os.environ, {
        "LOCAL_INSPECTION_ROOT": tmp,
        "VANTALINE_DATA_STORE": "json",
        "LOCAL_INSPECTION_AUTO_RESUME_WORKER": "0",
        "VANTALINE_LABEL_INSPECTION_ENABLED": "false",
        "YOLO_AUTOINSTALL": "false",
    }):
        (Path(tmp) / "local_inspection_service" / "static").mkdir(parents=True)
        os.environ.pop("VANTALINE_POSTGRES_DSN", None)
        from local_inspection_service import server
        from local_inspection_service.schemas.pipeline import PipelineTaskCreateRequest

        baseline_source = os.environ.get("VANTALINE_CREATE_BASELINE_SOURCE")
        if baseline_source:
            tree = ast.parse(Path(baseline_source).read_text(encoding="utf-8"))
            function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "create_pipeline_task")
            function.decorator_list = []
            exec(compile(ast.Module(body=[function], type_ignores=[]), baseline_source, "exec"), server.__dict__)
        else:
            route = next(route for route in server.app.routes if getattr(route, "path", "") == "/api/pipeline/tasks" and "POST" in getattr(route, "methods", set()))
            assert route.endpoint is server.create_pipeline_task

        def exercise(payload, *, user_id=None, admin=False, denied=None, ai=False,
                     init_error=None, schedule_error=None, bad_accessory=False,
                     rebind_scope=False, rebind_lock=False, owner_fallback=False, alias_name=False,
                     second_save_error=None, no_existing=False, context_error=False,
                     rebind_scheduler=False, public_error=None, rebind_second_lock=False):
            events = []
            lock = TracedLock(events)
            alternate = TracedLock(events, "alternate")
            saves = []
            clock_values = iter([100, 101, 102])
            config = {"items": []}
            owner = {"owner_user_id": "" if owner_fallback else "owner", "owner_account_id": "account"}
            accessory_catalog = {"a": {"name": "Accessory A"}}

            def permission(name, **kwargs):
                events.append(("permission", name))
                if denied == name:
                    raise denied_error

            denied_error = HTTPException(status_code=403, detail="denied")

            def load_config():
                events.append("config.load")
                if rebind_scope:
                    server.scope_config_for_user = lambda *args: (_ for _ in ()).throw(AssertionError("scope rebound too soon"))
                return config

            def scope_config(value, user, target=None):
                events.append(("config.scope", target))
                if rebind_lock:
                    server._pipeline_tasks_lock = alternate
                return value

            def save(task):
                events.append(("save", lock.held, alternate.held))
                saves.append(dict(task))
                if second_save_error and len(saves) == 2:
                    raise second_save_error

            def activate(task, scoped):
                events.append(("activate", lock.held, alternate.held))
                task["ai_task_id"] = "ai-1"

            def initialize(task, scoped):
                events.append(("initialize", lock.held, alternate.held))
                if rebind_second_lock:
                    server._pipeline_tasks_lock = alternate
                if init_error:
                    raise init_error

            def schedule(items, user):
                events.append(("schedule", items, user, lock.held, alternate.held))
                if schedule_error:
                    raise schedule_error

            def canonical(scoped, ids):
                events.append("canonical")
                if alias_name:
                    accessory_catalog["a"]["name"] = "Changed via alias"
                return list(ids)

            def fallback_owner(user):
                events.append("owner.fallback")
                return "owner-fallback"

            def uuid4():
                events.append("uuid")
                return SimpleNamespace(hex="1234567890abcdef")

            def counts(scoped, ids, value):
                events.append("counts")
                return value or {}

            def context_user():
                if context_error:
                    raise AssertionError("context read without pregen")
                if rebind_scheduler:
                    server.schedule_pipeline_recommendation_pregen = lambda *args: (_ for _ in ()).throw(AssertionError("scheduler rebound too soon"))
                return "requester"

            def public(task, scoped):
                events.append(("public", lock.held, alternate.held))
                if public_error:
                    raise public_error
                return dict(task)

            replacements = {
                "current_auth_user": lambda: {"id": "owner"},
                "require_permission": permission,
                "HTTPException": HTTPException,
                "user_is_admin": lambda user: admin,
                "owner_fields_for_new_record": lambda user, target: (events.append(("owner", target)) or owner),
                "resource_owner_id_for_new_record": fallback_owner,
                "load_config": load_config,
                "scope_config_for_user": scope_config,
                "accessory_lookup_by_id": lambda scoped: {} if bad_accessory else accessory_catalog,
                "canonical_pipeline_accessory_ids": canonical,
                "load_agent_config": lambda: {"auto_advance_default": True},
                "normalize_pipeline_detection_method": lambda method: method or "training",
                "normalize_expected_production_count": lambda count: int(count or 0),
                "pipeline_method_uses_training": lambda method: method == "training",
                "normalize_pipeline_accessory_counts": counts,
                "uuid": SimpleNamespace(uuid4=uuid4),
                "time": SimpleNamespace(time=lambda: (events.append("clock") or next(clock_values))),
                "_pipeline_tasks_lock": lock,
                "assert_unique_task_name": lambda name, owner_id: events.append(("unique", name, owner_id)),
                "activate_pipeline_ai_detection_task": activate,
                "save_pipeline_task": save,
                "initialize_auto_optimize_for_pipeline_task": initialize,
                "load_pipeline_task": lambda task_id: None if no_existing else {"id": task_id, "from_store": True, "name": "stale"},
                "pipeline_next_recommendation_stage": lambda task: "train" if ai else None,
                "schedule_pipeline_recommendation_pregen": schedule,
                "_request_user": SimpleNamespace(get=context_user),
                "pipeline_task_public": public,
            }
            with ExitStack() as stack:
                for name, value in replacements.items():
                    stack.enter_context(patch.object(server, name, value))
                try:
                    result = server.create_pipeline_task(PipelineTaskCreateRequest(**payload), user_id)
                    error = None
                except Exception as exc:
                    result, error = None, exc
            assert not lock.held and not alternate.held
            return result, error, events, saves, denied_error

        result, error, events, saves, _ = exercise({"accessory_ids": ["a"]}, user_id="other")
        assert error is None and result["id"] == "pipe_1234567890" and len(saves) == 1
        assert result["name"] == "Accessory A" and result["created_at"] == 100 and result["updated_at"] == 101
        assert ("owner", None) in events and ("config.scope", None) in events
        assert events.count("clock") == 2 and events.index("lock.enter") < events.index(("save", True, False)) < events.index("lock.exit")
        assert events[-1] == ("public", False, False)

        result, error, events, saves, _ = exercise({"task_kind": "incoming_material_text", "material_code": " M ", "material_name": " Manual "})
        assert error is None and result["stage"] == "library" and result["status"] == "setup_required"
        assert result["name"] == "Manual" and result["auto_advance"] is False and len(saves) == 1
        assert events[:2] == [("permission", "incoming_material_config"), ("permission", "inspection")]

        _, error, events, saves, _ = exercise({"task_kind": "unknown"})
        assert isinstance(error, HTTPException) and error.status_code == 400 and not saves
        assert events[0] == ("permission", "training_pipeline") and "clock" not in events

        _, error, events, saves, denied_error = exercise({}, denied="training_pipeline")
        assert error is denied_error and events == [("permission", "training_pipeline")] and not saves

        result, error, events, saves, _ = exercise({}, user_id="other", admin=True)
        assert error is None and ("owner", "other") in events and ("config.scope", "other") in events

        _, error, events, saves, _ = exercise({"detection_method": "ai"})
        assert isinstance(error, HTTPException) and error.status_code == 400 and not saves and "clock" not in events

        result, error, events, saves, _ = exercise({"detection_method": "ai", "expected_production_count": 3, "accessory_ids": ["a"]}, ai=True)
        assert error is None and len(saves) == 2 and saves[0]["ai_task_id"] == "ai-1"
        assert saves[1]["from_store"] is True and saves[1]["name"] == "Accessory A" and saves[1]["updated_at"] == 102
        assert events.index(("save", True, False)) < events.index(("initialize", False, False))
        assert events.count("lock.enter") == 2 and events.count("lock.exit") == 2
        assert events.index(("schedule", [("pipe_1234567890", "train")], "requester", False, False)) < events.index(("public", False, False))

        failure = RuntimeError("initialization failed")
        _, error, events, saves, _ = exercise({"detection_method": "ai", "expected_production_count": 3, "accessory_ids": ["a"]}, ai=True, init_error=failure)
        assert error is failure and len(saves) == 1 and events[-1] == ("initialize", False, False)

        failure = RuntimeError("schedule failed")
        _, error, events, saves, _ = exercise({}, ai=True, schedule_error=failure)
        assert error is failure and len(saves) == 1 and events[-1][0] == "schedule"

        _, error, events, saves, _ = exercise({"accessory_ids": ["a"]}, bad_accessory=True)
        assert isinstance(error, KeyError) and not saves and "clock" not in events

        result, error, events, saves, _ = exercise({}, rebind_scope=True, rebind_lock=True)
        assert error is None and saves and "alternate.enter" in events and "lock.enter" not in events
        assert events.index("config.load") < events.index(("config.scope", None)) < events.index("alternate.enter")

        result, error, events, saves, _ = exercise({"accessory_ids": ["a"]}, owner_fallback=True, alias_name=True)
        assert error is None and result["name"] == "Changed via alias" and result["owner_user_id"] == ""
        assert ("unique", "Changed via alias", "owner-fallback") in events and "owner.fallback" in events
        assert events.index("canonical") < events.index("uuid") < events.index("counts") < events.index("clock")

        result, error, events, saves, _ = exercise({}, context_error=True)
        assert error is None and len(saves) == 1 and not any(isinstance(x, tuple) and x[0] == "schedule" for x in events)

        result, error, events, saves, _ = exercise({}, ai=True, rebind_scheduler=True)
        assert error is None and len(saves) == 1 and any(isinstance(x, tuple) and x[0] == "schedule" for x in events)

        result, error, events, saves, _ = exercise(
            {"detection_method": "ai", "expected_production_count": 3, "accessory_ids": ["a"]},
            rebind_second_lock=True,
        )
        assert error is None and len(saves) == 2 and ("save", True, False) in events and ("save", False, True) in events
        assert events.index("lock.exit") < events.index(("initialize", False, False)) < events.index("alternate.enter")

        failure = RuntimeError("second save failed")
        _, error, events, saves, _ = exercise({"detection_method": "ai", "expected_production_count": 3, "accessory_ids": ["a"]}, second_save_error=failure)
        assert error is failure and len(saves) == 2 and events.count("lock.exit") == 2
        assert not any(isinstance(x, tuple) and x[0] == "schedule" for x in events)

        result, error, events, saves, _ = exercise({"detection_method": "ai", "expected_production_count": 3, "accessory_ids": ["a"]}, ai=True, no_existing=True)
        assert error is None and len(saves) == 1 and result["ai_task_id"] == "ai-1"
        assert ("initialize", False, False) in events

        failure = RuntimeError("public failed")
        _, error, events, saves, _ = exercise({}, public_error=failure)
        assert error is failure and len(saves) == 1 and events[-1] == ("public", False, False)

        if not baseline_source:
            from local_inspection_service.pipeline.task_create import PipelineTaskCreator
            from local_inspection_service.pipeline.task_create_ports import TaskCreateAccess, TaskCreatePolicy, TaskCreateRuntime

            def unread():
                raise AssertionError("constructor read a capability")

            PipelineTaskCreator(
                TaskCreateAccess(**{item.name: unread for item in fields(TaskCreateAccess)}),
                TaskCreatePolicy(**{item.name: unread for item in fields(TaskCreatePolicy)}),
                TaskCreateRuntime(**{item.name: unread for item in fields(TaskCreateRuntime)}),
            )

            def isolated(label):
                events = []
                lock = TracedLock(events, label)
                access = replace(server._pipeline_task_creator.access,
                    current_user=lambda: (lambda: {"id": label}),
                    require_permission=lambda: (lambda *args, **kwargs: None),
                    is_admin=lambda: (lambda user: False),
                    owner_fields=lambda: (lambda user, target: {"owner_user_id": label}),
                    scope_config=lambda: (lambda config, user, target: config),
                    load_config=lambda: (lambda: {}),
                    accessory_lookup=lambda: (lambda config: {}),
                    load_agent_config=lambda: (lambda: {}),
                )
                policy = replace(server._pipeline_task_creator.policy,
                    canonical_accessory_ids=lambda: (lambda config, ids: []),
                    normalize_detection_method=lambda: (lambda method: "training"),
                    normalize_expected_count=lambda: (lambda value: 0),
                    method_uses_training=lambda: (lambda method: True),
                    normalize_accessory_counts=lambda: (lambda config, ids, counts: {}),
                    assert_unique_name=lambda: (lambda name, owner: None),
                    next_recommendation_stage=lambda: (lambda task: None),
                )
                runtime = replace(server._pipeline_task_creator.runtime,
                    uuid4=lambda: (lambda: SimpleNamespace(hex=label.lower() * 16)),
                    now=lambda: (lambda: 123),
                    lock=lambda: lock,
                    save_task=lambda: (lambda task: events.append(("save", label, task["id"]))),
                    public_task=lambda: (lambda task, config: {"instance": label, **task}),
                )
                return PipelineTaskCreator(access, policy, runtime), events

            first, first_events = isolated("A")
            second, second_events = isolated("B")
            empty = PipelineTaskCreateRequest()
            assert first.create(empty)["instance"] == "A"
            assert second.create(empty)["instance"] == "B"
            assert first.create(empty)["instance"] == "A"
            assert [item for item in first_events if isinstance(item, tuple)] == [("save", "A", "pipe_aaaaaaaaaa")] * 2
            assert [item for item in second_events if isinstance(item, tuple)] == [("save", "B", "pipe_bbbbbbbbbb")]

    print("PASS pipeline task create permissions, ordering, partial effects and late bindings")


if __name__ == "__main__":
    main()
