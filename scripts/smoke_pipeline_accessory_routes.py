"""Accepted-main/candidate contract for pipeline accessory add/remove routes."""
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


def main():
    with tempfile.TemporaryDirectory(prefix="pipeline-accessory-routes-") as tmp, patch.dict(os.environ, {
        "LOCAL_INSPECTION_ROOT": tmp,
        "VANTALINE_DATA_STORE": "json",
        "LOCAL_INSPECTION_AUTO_RESUME_WORKER": "0",
        "VANTALINE_LABEL_INSPECTION_ENABLED": "false",
        "YOLO_AUTOINSTALL": "false",
    }):
        (Path(tmp) / "local_inspection_service" / "static").mkdir(parents=True)
        os.environ.pop("VANTALINE_POSTGRES_DSN", None)
        from local_inspection_service import server
        baseline_source = os.environ.get("VANTALINE_ACCESSORY_ROUTES_BASELINE_SOURCE")
        if baseline_source:
            tree = ast.parse(Path(baseline_source).read_text(encoding="utf-8-sig"))
            functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {"add_pipeline_accessory", "remove_pipeline_accessory"}]
            assert len(functions) == 2
            for function in functions:
                function.decorator_list = []
                exec(compile(ast.Module(body=[function], type_ignores=[]), baseline_source, "exec"), server.__dict__)
        else:
            for method, endpoint in (("POST", server.add_pipeline_accessory), ("DELETE", server.remove_pipeline_accessory)):
                route = next(route for route in server.app.routes if getattr(route, "path", "") == "/api/pipeline/accessories/{accessory_id}" and method in getattr(route, "methods", set()))
                assert route.endpoint is endpoint

        def exercise(method, *, resolved=True, aliases=("alias-1", "alias-1", "canonical"),
                     fail=None, rebind_remove=False, rebind_scope_on_load=False,
                     rebind_projection=False, fail_second_remove=False,
                     override_payload=False, nonmapping_payload=False,
                     rebind_payload_on_mutation=False):
            events = []
            user = {"id": "owner"}
            config = {"owner": "owner"}
            item = {"id": "canonical"}
            error = RuntimeError(fail or "unused")
            removed = []
            added = []

            def mark(name, *args):
                events.append((name, *args))
                if fail == name:
                    raise error

            def current_user():
                mark("user")
                return user

            def load_config():
                mark("config.load")
                if rebind_scope_on_load:
                    server.scope_config_for_user = lambda config, user: (_ for _ in ()).throw(AssertionError("scope rebound"))
                return config

            def scope(value, actor):
                mark("config.scope", value is config, actor is user)
                return value

            def resolve(value, identifier):
                mark("resolve", value is config, identifier)
                return ("canonical", item) if resolved else None

            def add(identifier):
                mark("add", identifier)
                added.append(identifier)
                if rebind_payload_on_mutation:
                    server.pipeline_accessories_payload = lambda scoped, actor: (events.append(("projection.rebound", scoped is config, actor is user, len(added))) or {"from_rebound": True})

            def alias_items(value):
                mark("aliases", value is item)
                for index, alias in enumerate(aliases):
                    events.append(("alias.yield", index, alias))
                    if fail == "alias.yield" and index == 1:
                        raise error
                    yield alias

            def remove(identifier):
                mark("remove", identifier)
                removed.append(identifier)
                if rebind_payload_on_mutation and len(removed) == len(aliases):
                    server.pipeline_accessories_payload = lambda scoped, actor: (events.append(("projection.rebound", scoped is config, actor is user, len(removed))) or {"from_rebound": True})
                if fail_second_remove and len(removed) == 2:
                    raise error
                if rebind_remove and len(removed) == 1:
                    server.remove_pipeline_accessory_id = lambda alias: events.append(("remove.rebound", alias))

            def projection(value, actor):
                mark("projection", value is config, actor is user)
                if rebind_projection:
                    server.pipeline_accessories_payload = lambda config, user: (_ for _ in ()).throw(AssertionError("projection rebound"))
                if nonmapping_payload:
                    return None
                return {"status": "from-payload", "accessory_id": "from-payload", "items": ["visible"]} if override_payload else {"items": ["visible"]}

            replacements = {
                "current_auth_user": current_user,
                "load_config": load_config,
                "scope_config_for_user": scope,
                "resolve_accessory_id": resolve,
                "add_pipeline_accessory_id": add,
                "accessory_id_aliases": alias_items,
                "remove_pipeline_accessory_id": remove,
                "pipeline_accessories_payload": projection,
                "HTTPException": HTTPException,
            }
            with ExitStack() as stack:
                for name, value in replacements.items():
                    stack.enter_context(patch.object(server, name, value))
                try:
                    function = server.add_pipeline_accessory if method == "add" else server.remove_pipeline_accessory
                    result = function("alias-input")
                    raised = None
                except Exception as exc:
                    result, raised = None, exc
            return result, raised, events, added, removed, error

        result, raised, events, added, removed, _ = exercise("add")
        assert raised is None and result == {"status": "added", "accessory_id": "canonical", "items": ["visible"]}
        assert added == ["canonical"] and not removed
        assert events == [
            ("user",), ("config.load",), ("config.scope", True, True),
            ("resolve", True, "alias-input"), ("add", "canonical"), ("projection", True, True),
        ]

        result, raised, events, added, removed, _ = exercise("remove")
        assert raised is None and result == {"status": "removed", "accessory_id": "canonical", "items": ["visible"]}
        assert not added and removed == ["alias-1", "alias-1", "canonical"]
        assert events[-1] == ("projection", True, True)

        for method in ("add", "remove"):
            result, raised, events, added, removed, _ = exercise(method, resolved=False)
            assert isinstance(raised, HTTPException) and raised.status_code == 404 and raised.detail == "配件不存在"
            assert not added and not removed and not any(event[0] == "projection" for event in events)

            result, raised, events, added, removed, _ = exercise(method, rebind_scope_on_load=True)
            assert raised is None and ("config.scope", True, True) in events

            result, raised, events, added, removed, _ = exercise(method, rebind_projection=True)
            assert raised is None and result["items"] == ["visible"]

        result, raised, events, added, removed, _ = exercise("remove", aliases=())
        assert raised is None and removed == [] and result["status"] == "removed"

        result, raised, events, added, removed, _ = exercise("remove", rebind_remove=True)
        assert raised is None and removed == ["alias-1"]
        assert ("remove.rebound", "alias-1") in events and ("remove.rebound", "canonical") in events

        result, raised, events, added, removed, failure = exercise("remove", fail="alias.yield")
        assert result is None and raised is failure and removed == ["alias-1"]
        assert not any(event[0] == "projection" for event in events)

        for method, expected_writes in (("add", 1), ("remove", 3)):
            result, raised, events, added, removed, _ = exercise(method, rebind_payload_on_mutation=True)
            assert raised is None and result["from_rebound"] is True
            assert ("projection.rebound", True, True, expected_writes) in events
            assert not any(event[0] == "projection" for event in events)
        result, raised, events, added, removed, failure = exercise("remove", fail_second_remove=True)
        assert result is None and raised is failure and removed == ["alias-1", "alias-1"]
        assert not any(event[0] == "projection" for event in events)

        for method in ("add", "remove"):
            result, raised, events, added, removed, _ = exercise(method, override_payload=True)
            assert raised is None and result["status"] == "from-payload" and result["accessory_id"] == "from-payload"
            result, raised, events, added, removed, _ = exercise(method, nonmapping_payload=True)
            assert result is None and isinstance(raised, TypeError)
            assert (added if method == "add" else removed)
        for method, points in (("add", ("user", "config.load", "config.scope", "resolve", "add", "projection")),
                               ("remove", ("user", "config.load", "config.scope", "resolve", "aliases", "remove", "projection"))):
            for point in points:
                result, raised, events, added, removed, failure = exercise(method, fail=point)
                assert result is None and raised is failure, (method, point)
                if point == "projection":
                    assert (added if method == "add" else removed)

        if not baseline_source:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from local_inspection_service.pipeline.accessory_routes import PipelineAccessoryRoutes
            from local_inspection_service.pipeline.accessory_routes_api import register_pipeline_accessory_routes_api
            from local_inspection_service.pipeline.accessory_routes_ports import PipelineAccessoryAccess, PipelineAccessoryCatalog

            def unread():
                raise AssertionError("constructor read a capability")

            PipelineAccessoryRoutes(*(
                cls(**{item.name: unread for item in fields(cls)})
                for cls in (PipelineAccessoryAccess, PipelineAccessoryCatalog)
            ))

            class HttpController:
                def add(self, accessory_id):
                    if accessory_id == "missing":
                        raise HTTPException(status_code=404, detail="配件不存在")
                    return {"action": "add", "id": accessory_id}

                def remove(self, accessory_id):
                    if accessory_id == "missing":
                        raise HTTPException(status_code=404, detail="配件不存在")
                    return {"action": "remove", "id": accessory_id}

            tiny_app = FastAPI()
            register_pipeline_accessory_routes_api(tiny_app, HttpController())
            tiny_client = TestClient(tiny_app)
            assert tiny_client.post("/api/pipeline/accessories/one").json() == {"action": "add", "id": "one"}
            assert tiny_client.delete("/api/pipeline/accessories/one").json() == {"action": "remove", "id": "one"}
            for method in (tiny_client.post, tiny_client.delete):
                response = method("/api/pipeline/accessories/missing")
                assert response.status_code == 404 and response.json() == {"detail": "配件不存在"}

            def isolated(label):
                events = []
                user = {"id": label}
                config = {"owner": label}
                access = replace(server._pipeline_accessory_routes.access,
                    current_user=lambda: (lambda: user),
                    load_config=lambda: (lambda: config),
                    scope_config=lambda: (lambda config, user: config),
                )
                catalog = replace(server._pipeline_accessory_routes.catalog,
                    resolve=lambda: (lambda config, accessory_id: (label, {"id": label})),
                    add_id=lambda: (lambda accessory_id: events.append(("add", label, accessory_id))),
                    aliases=lambda: (lambda item: [label]),
                    remove_id=lambda: (lambda accessory_id: events.append(("remove", label, accessory_id))),
                    public_payload=lambda: (lambda config, user: {"instance": label}),
                )
                return PipelineAccessoryRoutes(access, catalog), events

            first, first_events = isolated("A")
            second, second_events = isolated("B")
            assert first.add("one")["instance"] == "A"
            assert second.remove("two")["instance"] == "B"
            assert first.remove("three")["instance"] == "A"
            assert first_events == [("add", "A", "A"), ("remove", "A", "A")]
            assert second_events == [("remove", "B", "B")]
    print("PASS pipeline accessory routes resolution, aliases, partial effects and late bindings")


if __name__ == "__main__":
    main()