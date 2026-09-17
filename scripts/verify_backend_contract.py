"""Snapshot the assembled HTTP application without starting workers or providers.

Recording is an explicit maintenance operation. Normal CI only compares the
checked-in baseline; module paths and source locations are deliberately excluded.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests/backend_contract/application.json"


def capture():
    # Never inherit a developer/production runtime or provider admission settings.
    with tempfile.TemporaryDirectory(prefix="vantaline-contract-") as temporary:
        runtime = Path(temporary)
        (runtime / "local_inspection_service/static").mkdir(parents=True)
        os.environ["LOCAL_INSPECTION_ROOT"] = str(runtime)
        os.environ["VANTALINE_DATA_STORE"] = "json"
        os.environ["VANTALINE_LABEL_INSPECTION_ENABLED"] = "false"
        os.environ["LOCAL_INSPECTION_AUTO_RESUME_WORKER"] = "0"
        os.environ["INSPECTION_ENABLE_LAN_CORS"] = "0"
        os.environ.pop("INSPECTION_CORS_ORIGIN_REGEX", None)
        os.environ["INSPECTION_CORS_ORIGINS"] = ""
        sys.path.insert(0, str(ROOT))
        from local_inspection_service import server
        from starlette.routing import Mount

        assert server._record_access.identity is server._request_user
        assert server._access_control.identity is server._request_user
        assert server._record_access.ownership is server._record_ownership
        assert server._record_audit.ownership is server._record_ownership
        assert server._candidate_queries.repository is server._candidate_repository
        assert server._accessory_files.projection is server._accessory_projection
        assert server._accessory_creation.projection is server._accessory_projection
        assert server._accessory_confirmation.projection is server._accessory_projection
        assert server._accessory_confirmation.store.lock() is server._candidate_store_lock
        assert server._accessory_removal.projection is server._accessory_projection
        assert server._accessory_gallery.projection is server._accessory_projection
        assert server._image_job_metadata.model_resolver() is server.resolve_model_profiles()
        assert server._accessory_preparation.paths.normalized() == server.NORMALIZED_DIR
        assert server._candidate_factory.storage.directory() == server.ACCESSORY_CANDIDATES_DIR
        assert server._accessory_routing.allowed_routes() is server.ACCESSORY_DETECTION_ROUTES
        assert server._label_imports.data_directory() == server.DATA_DIR
        assert server._codex_media.data_directory() == server.DATA_DIR
        assert server._text_records.dependencies.guard() is server._incoming_text_store_lock
        assert server._text_media.directory() == server.TEXT_INSPECTION_MEDIA_DIR
        from local_inspection_service.text_inspection.projection import public_record
        from local_inspection_service.text_inspection import revisions, diagnostics
        assert server._text_v2_public is public_record
        assert server._text_v2_expected_revision is revisions.expected_revision
        assert server._text_v2_confirmed_snapshot is revisions.confirmed_snapshot
        assert server._text_v2_diagnostic_value is diagnostics.diagnostic_value
        assert server._text_v2_diagnostic_event is diagnostics.diagnostic_event
        assert server._text_v2_provider_diagnostics is diagnostics.provider_diagnostics
        assert server._text_diagnostics.logger() is server.TEXT_INSPECTION_DIAGNOSTIC_LOGGER
        assert server._text_records.dependencies.guard() is server._preparation_records.guard()
        assert server.standard_preparation_jobs.records is server._preparation_records
        assert server.standard_preparation_jobs.media_dependencies is server._preparation_media
        assert server.add_accessory_files is server._accessory_file_routes.add_accessory_files
        assert server._candidate_repository.dependencies.lock() is server._candidate_store_lock

        routes = []
        for route in server.app.routes:
            item = {
                "path": route.path,
                "name": route.name,
                "kind": "mount" if isinstance(route, Mount) else "route",
            }
            if not isinstance(route, Mount):
                methods = sorted(route.methods or [])
                item.update(
                    methods=methods,
                    include_in_schema=getattr(route, "include_in_schema", False),
                    status_code=getattr(route, "status_code", None),
                    response_model_exclude_unset=getattr(route, "response_model_exclude_unset", False),
                    permission={
                        method: list(server.route_allowed_permissions(route.path, method))
                        for method in methods
                    },
                )
            routes.append(item)
        return {
            "routes": routes,
            "openapi": server.app.openapi(),
            "middleware": [
                {"class": entry.cls.__name__, "options": {
                    key: value.__name__ if callable(value) else value
                    for key, value in entry.kwargs.items()
                }} for entry in server.app.user_middleware
            ],
            "startup": [fn.__name__ for fn in server.app.router.on_startup],
            "shutdown": [fn.__name__ for fn in server.app.router.on_shutdown],
            "http_errors": capture_http_errors(server.app),
        }


def capture_http_errors(app):
    """Exercise middleware and endpoint guards with real ASGI thread dispatch.

    No lifespan is entered: the fixture cannot launch provider/background work.
    All requests use the disposable JSON store created by capture().
    """
    from fastapi.testclient import TestClient

    errors = {}
    anonymous = TestClient(app, base_url="https://testserver")

    def record(name, response, expected_status):
        assert response.status_code == expected_status, (name, response.status_code, response.text)
        content_type = response.headers.get("content-type", "")
        errors[name] = {
            "status": response.status_code,
            "content_type": content_type,
            "body": response.json() if "application/json" in content_type else response.text,
        }

    record("setup_required", anonymous.get("/api/status"), 503)
    admin = TestClient(app, base_url="https://testserver")
    password = "contract-fixture-password-only"
    response = admin.post("/api/auth/bootstrap", json={"username": "contract-admin", "password": password})
    assert response.status_code == 200, response.text
    response = admin.post("/api/auth/users", json={
        "username": "contract-reader", "password": password, "role": "user", "permissions": [],
    })
    assert response.status_code == 200, response.text
    reader = TestClient(app, base_url="https://testserver")
    response = reader.post("/api/auth/login", json={"username": "contract-reader", "password": password})
    assert response.status_code == 200, response.text
    # Label guards live in the endpoint, while other guards live in middleware.
    # Test both instead of trusting only the central permission table.
    paths = ["/api/auth/users", "/api/docs", "/api/admin/model-profiles",
             "/api/label-inspection/capabilities", "/api/label-inspection/tasks/missing",
             "/api/text-inspection/standards/missing", "/api/accessories",
             "/api/plc/config", "/api/analyze/image"]
    for path in paths:
        method = "POST" if path == "/api/analyze/image" else "GET"
        record("anonymous " + path, anonymous.request(method, path), 401)
        record("reader " + path, reader.request(method, path), 403)
    record("private_media", anonymous.get("/outputs/missing.png"), 401)
    record("hidden_openapi", anonymous.get("/openapi.json"), 404)
    record("cross_origin", admin.post("/api/auth/logout", headers={"origin": "https://untrusted.invalid"}), 403)
    record("invalid_login", anonymous.post("/api/auth/login", json={"username": "x", "password": "x"}), 401)
    anonymous.close()
    admin.close()
    reader.close()
    return errors


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    actual = encoded(capture())
    if args.record:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(actual, encoding="utf-8")
        print(f"Recorded {BASELINE.relative_to(ROOT)}")
        return
    expected = BASELINE.read_text(encoding="utf-8")
    if expected != actual:
        difference = "".join(difflib.unified_diff(
            expected.splitlines(True), actual.splitlines(True),
            fromfile="contract baseline", tofile="assembled application",
        ))
        raise SystemExit(difference)
    print("PASS assembled routes/order, mounts, permissions, OpenAPI and lifecycle baseline")


if __name__ == "__main__":
    main()
