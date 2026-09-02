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
    server.call_ai_mcp_tool = lambda *_args, **_kwargs: calls.append(1) or {"ok": True, "parsed": provider_payload, "latency_ms": 5, "provider": "qwen", "model": "qwen-test"}
    try:
        payload = {"standard_asset_id": asset["id"], "comparison_id": "cmp_endpoint_0001"}
        files = {"captured_file": ("capture.png", picture("MoDEL: PPLBP-2020"), "image/png")}
        first = admin.post("/api/text-inspection/label/compare", data=payload, files=files)
        assert_status(first, 200, "compare")
        assert first.json()["standard_revision_id"] == added.json()["standard"]["current_revision_id"]
        assert first.json()["standard_revision_number"] == 4
        assert first.json()["reference_sha256"]
        if SMOKE_MODE == "fail_closed":
            assert first.json()["decision"] == "REVIEW_REQUIRED"
            assert first.json()["external_media_send_status"] == "not_sent"
            assert len(calls) == 0
        elif SMOKE_MODE == "external_only":
            assert first.json()["decision"] == "REVIEW_REQUIRED"
            assert first.json()["external_media_send_status"] == "sent"
        else:
            assert first.json()["decision"] == "DIFFERENCES"
        inspection_id = first.json()["id"]
        assert "annotated_path" not in first.json() and "source_path" not in first.json()
        evidence_kind = "source" if SMOKE_MODE == "fail_closed" else "annotated"
        assert_status(admin.get(f"/api/text-inspection/inspections/{inspection_id}/evidence/{evidence_kind}"), 200, "owner evidence")
        assert_status(other.get(f"/api/text-inspection/inspections/{inspection_id}/evidence/{evidence_kind}"), 404, "cross account evidence")
        second = admin.post("/api/text-inspection/label/compare", data=payload, files=files)
        assert_status(second, 200, "idempotent compare")
        assert len(calls) == (0 if SMOKE_MODE == "fail_closed" else 1)
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
