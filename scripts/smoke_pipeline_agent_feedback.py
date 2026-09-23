"""Offline accepted-main/candidate behavior contract for pipeline Agent feedback."""
import ast
from contextlib import ExitStack
from dataclasses import fields, replace
from pathlib import Path
import os
import sys
import tempfile
from unittest.mock import patch

from fastapi import HTTPException

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
    with tempfile.TemporaryDirectory(prefix="pipeline-agent-feedback-") as tmp, patch.dict(os.environ, {
        "LOCAL_INSPECTION_ROOT": tmp,
        "VANTALINE_DATA_STORE": "json",
        "LOCAL_INSPECTION_AUTO_RESUME_WORKER": "0",
        "VANTALINE_LABEL_INSPECTION_ENABLED": "false",
        "YOLO_AUTOINSTALL": "false",
    }):
        (Path(tmp) / "local_inspection_service" / "static").mkdir(parents=True)
        os.environ.pop("VANTALINE_POSTGRES_DSN", None)
        from local_inspection_service import server
        from local_inspection_service.schemas.pipeline import PipelineAgentFeedbackRequest
        baseline_source = os.environ.get("VANTALINE_FEEDBACK_BASELINE_SOURCE")
        if baseline_source:
            tree = ast.parse(Path(baseline_source).read_text(encoding="utf-8-sig"))
            function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "pipeline_agent_feedback")
            function.decorator_list = []
            exec(compile(ast.Module(body=[function], type_ignores=[]), baseline_source, "exec"), server.__dict__)
        else:
            route = next(route for route in server.app.routes if getattr(route, "path", "") == "/api/pipeline/tasks/{task_id}/agent-feedback" and "POST" in getattr(route, "methods", set()))
            assert route.endpoint is server.pipeline_agent_feedback

        def exercise(action, *, decision=None, message=" note ", updated_plan=None, sprite=False,
                     configured=False, execute=False, stage="draft", active_stage="", method="yolo",
                     missing=False, denied=False, pause_present=False, fail=None, rebind_schedule=False,
                     rebind_scope_on_load=False, rebind_clock_after_first=False,
                     execute_sets_pause=False, fail_execute_after_mutation=False,
                     fail_now_number=None, assert_plan_identity=False):
            events = []
            lock = Lock(events)
            user = {"id": "owner"}
            config = {"owner": "owner"}
            task = {"id": "pipe-1", "detection_method": method, "stage": stage, "status": "running"}
            orchestration = {"state": "active", "active_stage": active_stage}
            pause_from_execute = {"reason": "from execute"}
            if pause_present:
                orchestration["pause"] = {"reason": "existing"}
            error = RuntimeError(fail or "unused")
            denied_error = HTTPException(status_code=403, detail="denied")
            now_calls = 0
            saves = []
            scheduled = []

            def mark(name, *args):
                events.append((name, *args, lock.held))
                if fail == name:
                    raise error

            def current_user():
                mark("user")
                return user

            def load_config():
                mark("config.load")
                if rebind_scope_on_load:
                    server.scope_config_for_user = lambda value, actor: (_ for _ in ()).throw(AssertionError("scope rebound"))
                return config

            def scope(value, actor):
                mark("config.scope", value is config, actor is user)
                return value

            def load_task(identifier):
                mark("task.load", identifier)
                return None if missing else task

            def access(value, actor, *, write):
                mark("access", value is task, actor is user, write)
                if denied:
                    raise denied_error

            def normalize(value):
                mark("normalize", value)
                return value

            def training(value):
                mark("training", value)
                return value == "yolo"

            def ensure(value, scoped, *, force=False):
                mark("ensure", force, value is task, scoped is config)
                if force:
                    return {"state": "replanned", "active_stage": "pose_image_generation"}
                return orchestration

            def now():
                nonlocal now_calls
                now_calls += 1
                mark("now", now_calls)
                if fail_now_number == now_calls:
                    raise error
                if rebind_clock_after_first and now_calls == 1:
                    server.agent_mcp_now = lambda: (events.append(("now.rebound", lock.held)) or 900)
                return 100 + now_calls

            def sprite_flow(value, scoped):
                mark("sprite", value is task, scoped is config)
                return sprite

            def skip_legacy(value, scoped, plan):
                mark("skip.legacy", plan is orchestration)
                return {"state": "skipped", "active_stage": "pose_image_generation"}

            def mark_advancing(value):
                mark("advance.mark", value is task)
                value["advancing"] = True

            def pose_calls(value, scoped):
                mark("pose.calls", value is task)
                return value["agent_mcp"]

            def image_config():
                mark("image.config")
                return {"configured": configured, "message": "unavailable"}

            def execute_calls(value, scoped):
                mark("execute", value is task)
                if fail_execute_after_mutation:
                    assert lock.held
                    task["execute_marker"] = "persisted in memory"
                    raise error
                if execute_sets_pause:
                    orchestration["pause"] = pause_from_execute
                return execute

            def pause_task(value, plan, *, stage, reason, suggested_actions):
                mark("pause", stage, reason, tuple(suggested_actions))
                plan["pause"] = {"reason": reason}

            def save_task(value):
                mark("save", value is task)
                saves.append(dict(value))

            def public(value, scoped):
                mark("public", value is task, scoped is config)
                if rebind_schedule:
                    server.schedule_pipeline_advance = lambda identifier, actor: events.append(("schedule.rebound", identifier, lock.held))
                return value

            def schedule(identifier, actor):
                mark("schedule", identifier, actor is user)
                scheduled.append(identifier)

            replacements = {
                "current_auth_user": current_user,
                "load_config": load_config,
                "scope_config_for_user": scope,
                "_pipeline_tasks_lock": lock,
                "load_pipeline_task": load_task,
                "require_record_access": access,
                "normalize_pipeline_detection_method": normalize,
                "pipeline_method_uses_training": training,
                "ensure_agent_mcp_pose_plan": ensure,
                "agent_mcp_now": now,
                "pipeline_uses_photo_highlight_sprite_flow": sprite_flow,
                "mark_legacy_pose_flow_skipped_for_photo_highlight": skip_legacy,
                "mark_pipeline_task_advancing": mark_advancing,
                "ensure_agent_mcp_pose_tool_calls": pose_calls,
                "agent_mcp_gemini_image_config": image_config,
                "execute_agent_mcp_pose_tool_calls": execute_calls,
                "pause_agent_mcp_task": pause_task,
                "save_pipeline_task": save_task,
                "pipeline_task_public": public,
                "schedule_pipeline_advance": schedule,
                "HTTPException": HTTPException,
            }
            with ExitStack() as stack:
                for name, value in replacements.items():
                    stack.enter_context(patch.object(server, name, value))
                try:
                    request = PipelineAgentFeedbackRequest(
                        action=action, decision=decision, message=message, updated_plan=updated_plan,
                    )
                    result = server.pipeline_agent_feedback("pipe-1", request)
                    if assert_plan_identity:
                        assert orchestration["pose_plan"] is request.updated_plan
                    raised = None
                except Exception as exc:
                    result, raised = None, exc
            assert not lock.held
            return result, raised, events, task, orchestration, saves, scheduled, error, denied_error

        result, raised, events, task, plan, saves, scheduled, *_ = exercise("cancel", message=" x ")
        assert raised is None and result is task and task["status"] == "stopped" and len(saves) == 1 and not scheduled
        assert plan["feedback"] == [{"action": "cancel", "decision": "cancel", "message": "x", "created_at": 101}]
        assert [event[0] for event in events if isinstance(event, tuple)] == [
            "user", "config.load", "config.scope", "task.load", "access", "normalize", "training", "ensure",
            "now", "now", "now", "save", "public",
        ]
        assert events.index("lock.exit") > next(i for i, e in enumerate(events) if isinstance(e, tuple) and e[0] == "public")

        for action, decision in ((" cancel ", "replan"), ("other", "cancelled")):
            result, raised, events, task, plan, saves, scheduled, *_ = exercise(action, decision=decision)
            assert raised is None and task["status"] == "stopped" and len(saves) == 1

        for kwargs in (
            {"sprite": True},
            {"sprite": False, "configured": True, "execute": True},
            {"sprite": False, "configured": False},
            {"sprite": False, "configured": True, "execute": False},
        ):
            result, raised, events, task, plan, saves, scheduled, *_ = exercise("replan", **kwargs)
            assert raised is None and len(saves) == 1
            if kwargs["sprite"]:
                assert task["agent_mcp"]["state"] == "skipped" and scheduled == ["pipe-1"]
                assert not any(isinstance(e, tuple) and e[0] == "image.config" for e in events)
            else:
                assert task["agent_mcp"]["state"] == "replanned"
                assert ("ensure", True, True, True, True) in events
                assert bool(scheduled) is False
                if kwargs["configured"] and kwargs.get("execute"):
                    assert task["status"] == "ready" and not any(isinstance(e, tuple) and e[0] == "pause" for e in events)
                else:
                    assert any(isinstance(e, tuple) and e[0] == "pause" for e in events)

        result, raised, events, task, plan, saves, scheduled, *_ = exercise("update_plan", updated_plan={"view": "top"}, assert_plan_identity=True)
        assert raised is None and plan["pose_plan"] == {"view": "top"} and plan["state"] == "needs_user_action"
        assert any(isinstance(e, tuple) and e[0] == "pause" for e in events)
        for kwargs, status in (({"sprite": True, "updated_plan": {}}, 409), ({"updated_plan": None}, 400)):
            result, raised, events, task, plan, saves, scheduled, *_ = exercise("update", **kwargs)
            assert isinstance(raised, HTTPException) and raised.status_code == status and not saves
            assert len(plan["feedback"]) == 1

        for kwargs in (
            {"sprite": True},
            {"sprite": False, "execute": True},
            {"sprite": False, "execute": False},
            {"sprite": False, "execute": False, "pause_present": True},
        ):
            result, raised, events, task, plan, saves, scheduled, *_ = exercise("retry", **kwargs)
            assert raised is None and len(saves) == 1
            assert bool(scheduled) == kwargs["sprite"]
            if not kwargs["sprite"] and kwargs["execute"]:
                assert task["status"] == "ready"
            if not kwargs["sprite"] and not kwargs["execute"]:
                assert any(isinstance(e, tuple) and e[0] == "pause" for e in events)

        result, raised, events, task, plan, saves, scheduled, *_ = exercise("retry", execute_sets_pause=True)
        assert raised is None and plan["pause"] == {"reason": "from execute"}
        assert not any(isinstance(e, tuple) and e[0] in {"image.config", "pause"} for e in events)
        assert len(saves) == 1 and not scheduled
        for stage, active, decision in (("samples", "", None), ("draft", "model_training", None), ("draft", "", "continue_training"), ("draft", "", None)):
            result, raised, events, task, plan, saves, scheduled, *_ = exercise("resume", stage=stage, active_stage=active, decision=decision)
            assert raised is None and len(saves) == 1 and scheduled == ["pipe-1"]
            assert task["advancing"] is True
            assert bool(plan.get("training_quality_ack")) is (stage == "samples" or active == "model_training" or decision == "continue_training")
            if stage == "samples":
                assert task["status"] == "completed"

        result, raised, events, task, plan, saves, scheduled, *_ = exercise("continue_training", stage="samples")
        assert raised is None and task["status"] == "completed" and scheduled == ["pipe-1"]
        result, raised, events, task, plan, saves, scheduled, *_ = exercise("continue_training", stage="draft")
        assert isinstance(raised, HTTPException) and raised.status_code == 409 and not saves
        assert plan["training_quality_ack"] is True and plan["pause"] is None

        result, raised, events, task, plan, saves, scheduled, *_ = exercise("unknown")
        assert isinstance(raised, HTTPException) and raised.status_code == 400 and not saves and len(plan["feedback"]) == 1

        for kwargs, status in (({"missing": True}, 404), ({"method": "ai"}, 409)):
            result, raised, events, task, plan, saves, scheduled, *_ = exercise("resume", **kwargs)
            assert isinstance(raised, HTTPException) and raised.status_code == status and not saves and "feedback" not in plan
        result, raised, events, task, plan, saves, scheduled, _, denied_error = exercise("resume", denied=True)
        assert raised is denied_error and not saves and "feedback" not in plan

        for point in ("user", "config.load", "task.load", "ensure", "now", "sprite", "advance.mark", "save", "public", "schedule"):
            action = "retry" if point == "sprite" else "resume"
            result, raised, events, task, plan, saves, scheduled, failure, _ = exercise(action, fail=point)
            assert result is None and raised is failure, point
            if point in {"save", "public", "schedule"}:
                assert task["advancing"] is True
            if point in {"public", "schedule"}:
                assert len(saves) == 1
            if point == "schedule":
                assert scheduled == []

        result, raised, events, task, plan, saves, scheduled, *_ = exercise("cancel", rebind_scope_on_load=True)
        assert raised is None and task["status"] == "stopped"
        assert ("config.scope", True, True, False) in events

        result, raised, events, task, plan, saves, scheduled, *_ = exercise("cancel", rebind_clock_after_first=True)
        assert raised is None and plan["feedback"][0]["created_at"] == 101
        assert plan["updated_at"] == 900 and task["updated_at"] == 900
        assert events.count(("now.rebound", True)) == 2

        for failure_index in (2, 3):
            result, raised, events, task, plan, saves, scheduled, failure, _ = exercise("cancel", fail_now_number=failure_index)
            assert result is None and raised is failure and not saves and not scheduled
            assert len(plan["feedback"]) == 1 and task["status"] == "running"
            assert plan["state"] == ("active" if failure_index == 2 else "cancelled")

        for action in ("replan", "retry"):
            result, raised, events, task, plan, saves, scheduled, failure, _ = exercise(action, fail_execute_after_mutation=True, configured=True)
            assert result is None and raised is failure and task["execute_marker"] == "persisted in memory"
            assert len(plan["feedback"]) == 1 and not saves and not scheduled
            assert ("execute", True, True) in events
            assert not any(isinstance(e, tuple) and e[0] in {"public", "schedule"} for e in events)
        result, raised, events, task, plan, saves, scheduled, *_ = exercise("resume", decision=" ")
        assert raised is None and plan["feedback"][0]["decision"] == ""
        result, raised, events, task, plan, saves, scheduled, *_ = exercise("cancel", message="a" * 600)
        assert raised is None and len(plan["feedback"][0]["message"]) == 500
        result, raised, events, task, plan, saves, scheduled, *_ = exercise("resume", rebind_schedule=True)
        assert raised is None and not scheduled and ("schedule.rebound", "pipe-1", False) in events

        if not baseline_source:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from local_inspection_service.pipeline.agent_feedback import PipelineAgentFeedback
            from local_inspection_service.pipeline.agent_feedback_api import register_pipeline_agent_feedback_api
            from local_inspection_service.pipeline.agent_feedback_ports import AgentFeedbackAccess, AgentFeedbackPolicy, AgentFeedbackRuntime

            def unread():
                raise AssertionError("constructor read a capability")

            PipelineAgentFeedback(*(
                cls(**{item.name: unread for item in fields(cls)})
                for cls in (AgentFeedbackAccess, AgentFeedbackPolicy, AgentFeedbackRuntime)
            ))

            class HttpController:
                def feedback(self, task_id, request):
                    if task_id == "forbidden":
                        raise HTTPException(status_code=403, detail="denied")
                    return {"task_id": task_id, "action": request.action, "message": request.message}

            tiny_app = FastAPI()
            register_pipeline_agent_feedback_api(tiny_app, HttpController())
            tiny_client = TestClient(tiny_app)
            assert tiny_client.post("/api/pipeline/tasks/one/agent-feedback", json={"action": "cancel"}).json() == {"task_id": "one", "action": "cancel", "message": None}
            forbidden = tiny_client.post("/api/pipeline/tasks/forbidden/agent-feedback", json={"action": "cancel"})
            assert forbidden.status_code == 403 and forbidden.json() == {"detail": "denied"}
            assert tiny_client.post("/api/pipeline/tasks/one/agent-feedback", json={}).status_code == 422

            def isolated(label):
                events = []
                task = {"id": label, "detection_method": "yolo", "stage": "draft"}
                plan = {"state": "active", "active_stage": "draft"}
                task_lock = Lock(events)
                access = replace(server._pipeline_agent_feedback.access,
                    current_user=lambda: (lambda: {"id": label}),
                    load_config=lambda: (lambda: {"owner": label}),
                    scope_config=lambda: (lambda config, user: config),
                    load_task=lambda: (lambda task_id: task),
                    require_record_access=lambda: (lambda task, user, **kwargs: events.append(("access", label))),
                )
                policy = replace(server._pipeline_agent_feedback.policy,
                    normalize_method=lambda: (lambda value: value),
                    uses_training=lambda: (lambda value: True),
                )
                runtime = replace(server._pipeline_agent_feedback.runtime,
                    task_lock=lambda: task_lock,
                    ensure_plan=lambda: (lambda task, config, **kwargs: plan),
                    now=lambda: (lambda: 123),
                    mark_advancing=lambda: (lambda task: events.append(("mark", label))),
                    save_task=lambda: (lambda task: events.append(("save", label))),
                    public_task=lambda: (lambda task, config: {"instance": label}),
                    schedule_advance=lambda: (lambda task_id, user: events.append(("schedule", label, task_id))),
                )
                return PipelineAgentFeedback(access, policy, runtime), events

            first, first_events = isolated("A")
            second, second_events = isolated("B")
            for controller, label in ((first, "A"), (second, "B"), (first, "A")):
                assert controller.feedback("one", PipelineAgentFeedbackRequest(action="resume")) == {"instance": label}
            assert first_events.count(("schedule", "A", "one")) == 2
            assert second_events.count(("schedule", "B", "one")) == 1
            assert not any(isinstance(event, tuple) and "B" in event for event in first_events)
            assert not any(isinstance(event, tuple) and "A" in event for event in second_events)
    print("PASS pipeline feedback action, partial effect, lock and schedule contracts")


if __name__ == "__main__":
    main()