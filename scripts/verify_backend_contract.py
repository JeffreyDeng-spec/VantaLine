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

        for provider, name in [(server._detection_task_store.rows.decode, 'row_raw_json_list'),
                               (server._detection_task_store.normalize_background, 'safe_background_set_id')]:
            original = getattr(server, name)
            try:
                assert provider() is original
                replacement = lambda *args, **kwargs: None
                setattr(server, name, replacement)
                assert provider() is replacement
                setattr(server, name, None)
                assert provider() is None
            finally:
                setattr(server, name, original)
            assert provider() is original
        from local_inspection_service.detection import geometry, postprocessing, drawing
        assert server.polygon_area is geometry.polygon_area
        assert server.postprocess_detections is postprocessing.postprocess_detections
        assert server.draw_detections is drawing.draw_detections
        assert server.parse_detections.__self__ is server._detection_results
        assert server.apply_rule.__self__ is server._detection_rules
        assert server._detection_rules.class_labels() is server.CLASS_LABELS
        assert server._detection_rules.manual_labels() is server.MANUAL_TYPE_LABELS
        from local_inspection_service.runtime import paddle
        from local_inspection_service.detection import ocr_images, ocr_matching, ocr_scoring
        assert server.prepare_paddle_runtime is paddle.prepare_runtime
        assert server.normalize_ocr_text is ocr_matching.normalize_ocr_text
        assert server.crop_detection_region is ocr_images.crop_detection_region
        assert server.better_ocr_result is ocr_scoring.better_ocr_result
        assert server.score_ocr_variants.__self__ is server._ocr_scoring
        assert server.attach_ocr_results.__self__ is server._ocr_attachment
        for field, name in [('crop', 'crop_detection_region'), ('score', 'score_ocr_variants'), ('match', 'match_ocr_text_accessory')]:
            provider = getattr(server._ocr_attachment.dependencies, field)
            original = getattr(server, name)
            try:
                assert provider() is original
                replacement = lambda *args, **kwargs: None
                setattr(server, name, replacement)
                assert provider() is replacement
                setattr(server, name, None)
                assert provider() is None
            finally:
                setattr(server, name, original)
            assert provider() is original

        assert server._ocr_matching.stopwords() is server.OCR_ACCESSORY_PROFILE_STOPWORDS
        assert server._manual_classifier.keywords() is server.MANUAL_TYPE_KEYWORDS
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
        from local_inspection_service.runtime.json_records import read_json_list, write_json_list
        assert server._incoming_text_json_list is read_json_list
        assert server._save_incoming_text_json_list is write_json_list
        assert server._incoming_text_store.guard() is server._text_records.dependencies.guard()
        assert server._incoming_text_store.paths.references() == server.INCOMING_TEXT_REFERENCES_PATH
        assert server._incoming_text_store.paths.inspections() == server.INCOMING_TEXT_INSPECTIONS_PATH
        assert server._incoming_text_store.paths.audit() == server.INCOMING_TEXT_AUDIT_PATH
        assert server._incoming_text_store.rows.decode() is server.row_raw_json_list
        from local_inspection_service.text_inspection import incoming_analysis
        assert server.decode_incoming_reference is incoming_analysis.decode_reference
        assert server._ocr_result_mapping is incoming_analysis.result_mapping
        assert server._field_observation is incoming_analysis.field_observation
        assert server._incoming_text_ocr_lock is server._incoming_ocr_engine.lock
        assert server._text_compare_beta_cache is server._beta_comparison.cache
        assert server._text_compare_beta_cache_lock is server._beta_comparison.lock
        assert server._beta_comparison.observer() is server.incoming_text_ocr_observations
        assert [route.endpoint for route in server.app.routes if route.name == "analyze_text_compare_beta"] == [server.analyze_text_compare_beta]


        assert server._incoming_catalog.access is server._incoming_execution.access is server._incoming_reviews.access
        assert server._incoming_catalog.writes is server._incoming_reviews.writes is server._incoming_retention.writes
        assert server._incoming_writes.guard() is server._incoming_text_store_lock
        assert server._incoming_json.paths is server._incoming_text_store.paths
        incoming_getters = (
            (server._incoming_task_access.allowed, "incoming_text_task_access_allowed"),
            (server._incoming_access.task, "require_incoming_text_task"),
            (server._incoming_access.record, "require_record_access"),
            (server._incoming_tasks.public, "pipeline_task_public"),
            (server._incoming_media.output, "output_write_dir_for_owner"),
            (server._incoming_media.decode, "decode_incoming_reference"),
            (server._incoming_reviews.decode_rows, "row_raw_json_list"),
            (server._incoming_execution.ocr.field, "_field_observation"),
            (server._incoming_execution.imaging.rectify, "rectify_label"),
            (server._incoming_execution.imaging.similarity, "local_visual_similarity"),
            (server._incoming_execution.imaging.annotate, "annotate_inspection"),
            (server._incoming_execution.capacity, "require_incoming_text_storage_capacity"),
            (server._incoming_retention.audit, "append_incoming_text_audit"),
        )
        for getter, name in incoming_getters:
            original = getattr(server, name)
            assert getter() is original
            replacement = lambda *args, **kwargs: None
            try:
                setattr(server, name, replacement)
                assert getter() is replacement
                setattr(server, name, None)
                assert getter() is None
            finally:
                setattr(server, name, original)
            assert getter() is original
        for routes in (server._incoming_catalog_routes, server._incoming_inspection_routes):
            for name in routes.__dataclass_fields__:
                endpoint = getattr(server, name)
                assert endpoint is getattr(routes, name)
                assert [route.endpoint for route in server.app.routes if route.name == name] == [endpoint]

        for name in server._training_resource_routes.__dataclass_fields__:
            endpoint = getattr(server, name)
            assert endpoint is getattr(server._training_resource_routes, name)
            assert [route.endpoint for route in server.app.routes if route.name == name] == [endpoint]
        assert server._dataset_catalog.paths.output() == server.OUTPUT_DIR
        for name in server._training_resource_write_routes.__dataclass_fields__:
            endpoint = getattr(server, name)
            assert endpoint is getattr(server._training_resource_write_routes, name)
            assert [route.endpoint for route in server.app.routes if route.name == name] == [endpoint]
        assert server._training_dataset_links.guard() is server._training_task_lock
        assert server._pipeline_resource_links.guard() is server._pipeline_tasks_lock

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
        assert server._standard_imports.records is server._standard_library.records is server._standard_edits.records
        assert server._standard_imports.access is server._standard_library.access is server._standard_edits.access
        assert server._standard_edits.writes.guard() is server._incoming_text_store_lock
        from unittest.mock import patch
        bindings = (
            (server, "bounded_text", (server._standard_imports.bounded_text, server._standard_edits.bounded_text)),
            (server, "extract_doc_images", (server._standard_imports.parsers.doc,)),
            (server, "_text_v2_write", (server._standard_media.write,)),
            (server.document_import_jobs, "mark_unavailable", (server._standard_imports.classification.mark_unavailable,)),
            (server, "_text_v2_expected_revision", (server._standard_edits.revisions.expected,)),
            (server, "_text_v2_public", (server._standard_records.public,)),
            (server, "_text_v2_apply_revision", (server._standard_edits.revisions.apply,)),
            (server, '_text_v2_owned', (server._inspection_records.owned,)),
            (server, '_text_v2_media_path', (server._comparison_submission.media.path,)),
            (server, 'sha256_bytes', (server._comparison_submission.media.digest,)),
            (server, '_text_v2_prepare_image', (server._comparison_submission.images.prepare,)),
            (server, '_text_v2_annotate', (server._comparison_submission.images.annotate,)),
            (server, 'call_ai_mcp_tool', (server._comparison_submission.models.call,)),
            (server, 'normalize_vlm_provider_result', (server._comparison_submission.models.normalize,)),
            (server, '_text_v2_diagnostic_event', (server._comparison_submission.diagnostics.event,)),
            (server, '_text_v2_read_verified', (server._inspection_reviews.read_verified,)),
            (server, 'append_incoming_text_audit', (server._inspection_reviews.audit,)),
            (server, 'bounded_text', (server._inspection_reviews.bounded_text,)),
        )
        for owner, attribute, getters in bindings:
            original = getattr(owner, attribute)
            for getter in getters:
                assert getter() == original  # Bound methods are recreated on attribute access.
            replacement = lambda *args, **kwargs: None
            with patch.object(owner, attribute, replacement):
                for getter in getters:
                    assert getter() is replacement
            for getter in getters:
                assert getter() == original
        assert server._comparison_submission.records is server._inspection_reviews.records
        assert server._comparison_submission.access is server._inspection_reviews.access is server._inspection_access
        for name in ("compare_text_inspection_label", "get_text_inspection_v2_evidence",
                     "create_text_manual_session", "inspect_text_manual_page",
                     "complete_text_manual_session", "review_text_inspection_v2"):
            endpoint = getattr(server, name)
            assert endpoint is getattr(server._inspection_routes, name)
            assert [route.endpoint for route in server.app.routes if route.name == name] == [endpoint]

        for name in ("import_text_inspection_standard", "list_text_inspection_standards",
                     "get_text_inspection_standard", "get_text_inspection_asset_content",
                     "add_text_inspection_standard_asset", "patch_text_inspection_asset",
                     "confirm_text_inspection_standard"):
            endpoint = getattr(server, name)
            assert endpoint is getattr(server._standard_routes, name)
            assert [route.endpoint for route in server.app.routes if route.name == name] == [endpoint]

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
