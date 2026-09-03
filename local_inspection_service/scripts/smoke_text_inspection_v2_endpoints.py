#!/usr/bin/env python3
from __future__ import annotations

import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = Path(tempfile.mkdtemp(prefix="vantaline_text_v2_api_"))
(TMP_ROOT / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
os.environ["LOCAL_INSPECTION_ROOT"] = str(TMP_ROOT)
os.environ["VANTALINE_DATA_STORE"] = "json"
SMOKE_MODE = os.environ.get("VANTALINE_TEXT_V2_SMOKE_MODE", "fail_closed")
if SMOKE_MODE in {"external_only", "enabled"}:
    os.environ["VANTALINE_TEXT_INSPECTION_EXTERNAL_VLM_ENABLED"] = "true"
if SMOKE_MODE == "enabled":
    os.environ["VANTALINE_TEXT_INSPECTION_AUTOMATIC_MATCH_VERIFIED"] = "true"
sys.path.insert(0, str(REPO_ROOT))

from local_inspection_service.scripts import testclient_threadpool_shim  # noqa: E402
from local_inspection_service import server  # noqa: E402

testclient_threadpool_shim.install()
TestClient = testclient_threadpool_shim.SmokeASGIClient
PASSWORD = "password-12345"


def assert_status(response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise AssertionError(f"{label}: expected {expected}, got {response.status_code}: {response.text[:600]}")


def picture(text: str) -> bytes:
    image = np.full((500, 900, 3), 255, np.uint8)
    cv2.putText(image, text, (50, 280), cv2.FONT_HERSHEY_SIMPLEX, 2, (10, 10, 10), 4, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


def bitmap_picture(text: str) -> bytes:
    image = np.full((500, 900, 3), 255, np.uint8)
    cv2.putText(image, text, (50, 280), cv2.FONT_HERSHEY_SIMPLEX, 2, (10, 10, 10), 4, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".bmp", image)
    assert ok
    return encoded.tobytes()


def large_picture(text: str) -> bytes:
    image = np.full((1800, 3200, 3), 255, np.uint8)
    cv2.putText(image, text, (120, 950), cv2.FONT_HERSHEY_SIMPLEX, 5, (10, 10, 10), 10, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    assert ok
    return encoded.tobytes()


def docx() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/></Types>')
        archive.writestr("word/_rels/document.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="media/image1.png" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"/></Relationships>')
        archive.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body><w:p><w:r><w:t>1.标贴</w:t></w:r></w:p><w:p><w:r><w:drawing><a:blip r:embed="rId1"/></w:drawing></w:r></w:p></w:body></w:document>')
        archive.writestr("word/media/image1.png", picture("MODEL: PPLBP-2020"))
    return output.getvalue()


def login(client: TestClient, username: str) -> None:
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert_status(response, 200, f"login {username}")


def main() -> None:
    # The browser may label a file image/jpeg purely because its name ends in
    # .jpg. Backend acceptance follows decoded bytes and normalizes readable
    # formats instead of rejecting that mismatch.
    prepared, mime, suffix, source_format = server._text_v2_prepare_image(bitmap_picture("BMP AS JPG"))
    assert source_format == "BMP"
    assert mime == "image/jpeg" and suffix == ".jpg"
    assert prepared.startswith(b"\xff\xd8")
    assert cv2.imdecode(np.frombuffer(prepared, np.uint8), cv2.IMREAD_COLOR) is not None
    provider_image, provider_mime, provider_format = server._text_v2_prepare_provider_image(large_picture("LARGE"), "image/jpeg")
    provider_decoded = cv2.imdecode(np.frombuffer(provider_image, np.uint8), cv2.IMREAD_COLOR)
    assert provider_decoded is not None
    assert max(provider_decoded.shape[:2]) == server.TEXT_INSPECTION_PROVIDER_IMAGE_MAX_SIDE
    assert provider_mime == "image/jpeg" and provider_format == "JPEG"

    admin = TestClient(server.app, base_url="https://testserver")
    bootstrap = admin.post("/api/auth/bootstrap", json={"username": "admin", "password": PASSWORD})
    assert_status(bootstrap, 200, "bootstrap")
    admin_user_id = bootstrap.json()["user"]["id"]
    created = admin.post("/api/auth/users", json={"username": "other", "password": PASSWORD, "display_name": "Other", "role": "user", "permissions": ["inspection"]})
    assert_status(created, 200, "create other")
    other = TestClient(server.app, base_url="https://testserver")
    login(other, "other")

    imported = admin.post("/api/text-inspection/standards/import", data={"name": "参数标", "material_code": "PKG-1", "version_label": "V1"}, files={"file": ("standard.docx", docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert_status(imported, 200, "import docx")
    standard = imported.json()
    asset = standard["assets"][0]
    assert asset["status"] == "candidate"
    assert_status(other.get(f"/api/text-inspection/standards/{standard['id']}"), 404, "cross account standard")
    assert_status(other.get(f"/api/text-inspection/assets/{asset['id']}/content"), 404, "cross account media")

    confirmed = admin.post(f"/api/text-inspection/standards/{standard['id']}/confirm")
    assert_status(confirmed, 200, "confirm")
    assert confirmed.json()["revision_number"] == 1
    assert confirmed.json()["current_revision_id"].startswith("rev_")

    removed = admin.patch(
        f"/api/text-inspection/standards/{standard['id']}/assets/{asset['id']}",
        json={"action": "remove", "expected_revision": 1},
    )
    assert_status(removed, 200, "remove from confirmed standard")
    assert removed.json()["status"] == "excluded"
    assert removed.json()["standard"]["revision_number"] == 2
    assert removed.json()["standard"]["asset_count"] == 0
    assert_status(admin.get(f"/api/text-inspection/assets/{asset['id']}/content"), 200, "soft-removed media retained")
    assert_status(
        admin.post(
            "/api/text-inspection/label/compare",
            data={"standard_asset_id": asset["id"], "comparison_id": "cmp_removed_0001"},
            files={"captured_file": ("capture.png", picture("removed"), "image/png")},
        ),
        404,
        "removed last asset cannot compare",
    )
    assert_status(
        admin.patch(
            f"/api/text-inspection/standards/{standard['id']}/assets/{asset['id']}",
            json={"action": "restore", "expected_revision": 1},
        ),
        409,
        "stale revision",
    )
    assert_status(
        admin.patch(
            f"/api/text-inspection/standards/{standard['id']}/assets/{asset['id']}",
            json={"action": "restore", "expected_revision": True},
        ),
        400,
        "invalid revision type",
    )
    restored = admin.patch(
        f"/api/text-inspection/standards/{standard['id']}/assets/{asset['id']}",
        json={"action": "restore", "expected_revision": 2},
    )
    assert_status(restored, 200, "restore confirmed asset")
    assert restored.json()["standard"]["revision_number"] == 3
    added = admin.post(
        f"/api/text-inspection/standards/{standard['id']}/assets",
        data={"expected_revision": "3"},
        files={"file": ("extra.png", picture("EXTRA LABEL"), "image/png")},
    )
    assert_status(added, 200, "add confirmed asset")
    assert added.json()["asset"]["content_url"].endswith("/content")
    assert added.json()["standard"]["revision_number"] == 4
    assert added.json()["standard"]["asset_count"] == 2
    revisions = sorted(
        [item for item in server._text_v2_load("revisions") if item["standard_id"] == standard["id"]],
        key=lambda item: item["revision_number"],
    )
    assert [item["revision_number"] for item in revisions] == [1, 2, 3, 4]
    assert revisions[0]["confirmed_asset_ids"] == [asset["id"]]
    assert revisions[1]["confirmed_asset_ids"] == []
    assert revisions[2]["confirmed_asset_ids"] == [asset["id"]]
    assert revisions[3]["confirmed_asset_ids"] == [asset["id"], added.json()["asset"]["id"]]

    # Standards confirmed before revision-ledger rollout must preserve their
    # pre-edit membership as revision 1 before the first live mutation becomes
    # revision 2.
    legacy_asset_id = "ast_legacy_baseline"
    legacy_standard_id = "std_legacy_baseline"
    legacy_bytes = picture("LEGACY LABEL")
    legacy_path = server._text_v2_media_path(admin_user_id, legacy_standard_id, f"{legacy_asset_id}.png")
    server._text_v2_write(legacy_path, legacy_bytes)
    legacy_asset = {
        "id": legacy_asset_id, "standard_id": legacy_standard_id, "owner_user_id": admin_user_id,
        "asset_kind": "label_candidate", "ordinal": 1, "status": "candidate",
        "sha256": server.sha256_bytes(legacy_bytes), "mime_type": "image/png",
        "media_path": str(legacy_path), "created_at": 1_700_000_000, "updated_at": 1_700_000_000,
    }
    legacy_standard = {
        "id": legacy_standard_id, "owner_user_id": admin_user_id, "name": "旧标准",
        "material_code": "PKG-LEGACY", "version_label": "V1", "standard_type": "label",
        "status": "confirmed", "source_sha256": "legacy", "asset_count": 1,
        "confirmed_assets": [{"id": legacy_asset_id, "sha256": legacy_asset["sha256"], "ordinal": 1, "mime_type": "image/png"}],
        "confirmed_asset_ids": [legacy_asset_id], "created_at": 1_700_000_000, "updated_at": 1_700_000_000,
    }
    assert server._text_v2_save("standards", legacy_standard, insert_only=True)
    assert server._text_v2_save("assets", legacy_asset, insert_only=True)
    legacy_removed = admin.patch(
        f"/api/text-inspection/standards/{legacy_standard_id}/assets/{legacy_asset_id}",
        json={"action": "remove", "expected_revision": 0},
    )
    assert_status(legacy_removed, 200, "legacy confirmed first mutation")
    assert legacy_removed.json()["standard"]["revision_number"] == 2
    legacy_revisions = sorted(
        [item for item in server._text_v2_load("revisions") if item["standard_id"] == legacy_standard_id],
        key=lambda item: item["revision_number"],
    )
    assert [item["action"] for item in legacy_revisions] == ["baseline", "remove"]
    assert legacy_revisions[0]["confirmed_asset_ids"] == [legacy_asset_id]
    assert legacy_revisions[1]["confirmed_asset_ids"] == []
    assert_status(
        other.post(
            f"/api/text-inspection/standards/{standard['id']}/assets",
            files={"file": ("other.png", picture("OTHER"), "image/png")},
        ),
        404,
        "cross account add",
    )
    assert_status(
        other.patch(
            f"/api/text-inspection/standards/{standard['id']}/assets/{asset['id']}",
            json={"action": "remove"},
        ),
        404,
        "cross account remove",
    )

    same_source_new_business = admin.post(
        "/api/text-inspection/standards/import",
        data={"name": "参数标二", "material_code": "PKG-2", "version_label": "V1"},
        files={"file": ("standard.docx", docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert_status(same_source_new_business, 200, "same source different business key")
    assert same_source_new_business.json()["id"] != standard["id"]

    original_call = server.call_ai_mcp_tool
    calls = []
    provider_payload = {"decision": "MATCH", "message": "same", "differences": []} if SMOKE_MODE == "external_only" else {"decision": "DIFFERENCES", "message": "case", "differences": [{"type": "case", "reference_text": "O", "actual_text": "o", "confidence": 0.99, "box": [0.1, 0.2, 0.3, 0.4]}]}
    server.call_ai_mcp_tool = lambda _tool, call_payload: calls.append(call_payload) or {"ok": True, "parsed": provider_payload, "latency_ms": 5, "provider": "qwen", "model": "qwen-test"}
    try:
        payload = {"standard_asset_id": asset["id"], "comparison_id": "cmp_endpoint_0001"}
        files = {"captured_file": ("capture.jpg", large_picture("MoDEL: PPLBP-2020"), "image/jpeg")}
        first = admin.post("/api/text-inspection/label/compare", data=payload, files=files)
        assert_status(first, 200, "compare")
        assert first.json()["standard_revision_id"] == added.json()["standard"]["current_revision_id"]
        assert first.json()["standard_revision_number"] == 4
        assert first.json()["reference_sha256"]
        if SMOKE_MODE == "fail_closed":
            assert first.json()["decision"] == "REVIEW_REQUIRED"
            assert first.json()["external_media_send_status"] == "not_sent"
            assert first.json()["diagnostics"]["events"][-1]["stage"] == "external_media_gate"
            assert len(calls) == 0
        elif SMOKE_MODE == "external_only":
            assert first.json()["decision"] == "REVIEW_REQUIRED"
            assert first.json()["external_media_send_status"] == "sent"
            assert first.json()["diagnostics"]["provider_result"]["parsed_response"] == provider_payload
        else:
            assert first.json()["decision"] == "DIFFERENCES"
            assert first.json()["diagnostics"]["provider_result"]["parsed_response"] == provider_payload
        if SMOKE_MODE != "fail_closed":
            assert calls[0]["provider_config"]["timeout_seconds"] >= server.TEXT_INSPECTION_PROVIDER_TIMEOUT_SECONDS
            assert first.json()["diagnostics"]["request"]["prepared_actual"]["width"] == 3200
            assert first.json()["diagnostics"]["request"]["provider_actual"]["width"] == server.TEXT_INSPECTION_PROVIDER_IMAGE_MAX_SIDE
            assert first.json()["diagnostics"]["request"]["provider_actual"]["height"] == 1152
        inspection_id = first.json()["id"]
        assert "annotated_path" not in first.json() and "source_path" not in first.json()
        evidence_kind = "source" if SMOKE_MODE == "fail_closed" else "annotated"
        assert_status(admin.get(f"/api/text-inspection/inspections/{inspection_id}/evidence/{evidence_kind}"), 200, "owner evidence")
        assert_status(other.get(f"/api/text-inspection/inspections/{inspection_id}/evidence/{evidence_kind}"), 404, "cross account evidence")
        second = admin.post("/api/text-inspection/label/compare", data=payload, files=files)
        assert_status(second, 200, "idempotent compare")
        compatibility = admin.post(
            "/api/text-inspection/label/compare",
            data={"standard_asset_id": asset["id"], "comparison_id": "cmp_disguised_jpg_0001"},
            files={"captured_file": ("camera-export.jpg", bitmap_picture("BMP AS JPG"), "image/jpeg")},
        )
        assert_status(compatibility, 200, "decoded-content compatibility")
        assert compatibility.json()["source_format"] == "BMP"
        assert compatibility.json()["source_upload_sha256"] != compatibility.json()["source_sha256"]
        assert len(calls) == (0 if SMOKE_MODE == "fail_closed" else 2)
    finally:
        server.call_ai_mcp_tool = original_call

    assert server._text_v2_diagnostic_value(
        {"Authorization": "Bearer secret", "image_url": "data:image/png;base64,AAAA"}
    ) == {"Authorization": "<redacted>", "image_url": "<embedded-media:26-chars>"}
    logged: list[str] = []

    class CaptureLogger:
        def info(self, _pattern: str, payload: str) -> None:
            logged.append(payload)

    original_logger = server.TEXT_INSPECTION_DIAGNOSTIC_LOGGER
    try:
        server.TEXT_INSPECTION_DIAGNOSTIC_LOGGER = CaptureLogger()
        server._text_v2_write_server_diagnostic(
            {
                "id": "ins_log_redaction",
                "comparison_id": "cmp_log_redaction",
                "status": "uncertain",
                "diagnostics": {
                    "request_received_at_ms": int(server.time.time() * 1000),
                    "failure": {"stage": "provider_result", "error_type": "AuthError", "message": "Bearer secret"},
                },
            }
        )
    finally:
        server.TEXT_INSPECTION_DIAGNOSTIC_LOGGER = original_logger
    assert logged and "Bearer secret" not in logged[0] and "error_message_sha256" in logged[0]

    if SMOKE_MODE in {"external_only", "enabled"}:
        original_call = server.call_ai_mcp_tool
        try:
            server.call_ai_mcp_tool = lambda *_args, **_kwargs: {
                "ok": False,
                "parsed": {},
                "latency_ms": 10_000,
                "provider": "qwen",
                "provider_model": "qwen-test",
                "timed_out": True,
                "provider_failure": True,
                "error_type": "AiProviderTimeout",
                "error": "AI provider timed out",
                "attempts": 1,
            }
            provider_failed = admin.post(
                "/api/text-inspection/label/compare",
                data={"standard_asset_id": asset["id"], "comparison_id": "cmp_diagnostic_provider_failure"},
                files={"captured_file": ("capture.png", picture("PROVIDER FAILURE"), "image/png")},
            )
            assert_status(provider_failed, 200, "provider failure diagnostics")
            provider_failure_json = provider_failed.json()
            assert provider_failure_json["status"] == "uncertain"
            assert provider_failure_json["diagnostics"]["failure"] == {
                "stage": "provider_result",
                "error_type": "AiProviderTimeout",
                "message": "AI provider timed out",
            }
            assert provider_failure_json["diagnostics"]["provider_result"]["timed_out"] is True
            assert provider_failure_json["diagnostics"]["provider_result"]["error_type"] == "AiProviderTimeout"

            invalid_payload = {"decision": "MATCH", "differences": [], "message": "same", "unexpected": True}
            server.call_ai_mcp_tool = lambda *_args, **_kwargs: {
                "ok": True,
                "parsed": invalid_payload,
                "latency_ms": 7,
                "provider": "qwen",
                "provider_model": "qwen-test",
            }
            validation_failed = admin.post(
                "/api/text-inspection/label/compare",
                data={"standard_asset_id": asset["id"], "comparison_id": "cmp_diagnostic_validation_failure"},
                files={"captured_file": ("capture.png", picture("SCHEMA FAILURE"), "image/png")},
            )
            assert_status(validation_failed, 200, "validation failure diagnostics")
            validation_failure_json = validation_failed.json()
            assert validation_failure_json["status"] == "uncertain"
            assert validation_failure_json["diagnostics"]["failure"]["stage"] == "response_validation"
            assert "结构不符合约定" in validation_failure_json["diagnostics"]["failure"]["message"]
            assert validation_failure_json["diagnostics"]["provider_result"]["parsed_response"] == invalid_payload
        finally:
            server.call_ai_mcp_tool = original_call

    if SMOKE_MODE == "fail_closed":
        now = 1_800_000_000
        manual_standard = {"id": "std_manual_gate", "owner_user_id": admin_user_id, "name": "manual", "material_code": "MAN-1", "version_label": "V1", "standard_type": "manual", "status": "confirmed", "source_sha256": "x", "created_at": now, "updated_at": now, "confirmed_asset_ids": ["manual_asset_1"], "confirmed_assets": [{"id": "manual_asset_1", "sha256": "x", "ordinal": 1, "mime_type": "image/png"}]}
        session = {"id": "manual_session_gate", "owner_user_id": manual_standard["owner_user_id"], "standard_id": manual_standard["id"], "status": "active", "created_at": now, "updated_at": now}
        page = {"id": "manual_page_gate", "session_id": session["id"], "owner_user_id": manual_standard["owner_user_id"], "capture_id": "capture_gate_001", "standard_asset_id": "manual_asset_1", "status": "completed", "decision": "MATCH", "source_sha256": "capture", "created_at": now, "updated_at": now}
        server._text_v2_save("standards", manual_standard, insert_only=True)
        server._text_v2_save("sessions", session, insert_only=True)
        server._text_v2_save("pages", page, insert_only=True)
        completed = admin.post(f"/api/text-inspection/manual/sessions/{session['id']}/complete")
        assert_status(completed, 200, "manual pass gate")
        assert completed.json()["decision"] == "REVIEW_REQUIRED"

    print(f"text inspection v2 endpoint smoke passed: {SMOKE_MODE}")


if __name__ == "__main__":
    main()
