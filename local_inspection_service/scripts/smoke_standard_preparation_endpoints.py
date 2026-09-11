"""Actual auth/routes/storage, fake OCR/VLM: not semantic acceptance."""
import copy
import json
import os
import time
from local_inspection_service.scripts.smoke_text_inspection_v2_endpoints import server, TestClient, PASSWORD, assert_status, docx
from local_inspection_service.scripts.smoke_standard_preparation import fixture
from local_inspection_service.standard_preparation import png


def main():
    admin = TestClient(server.app, base_url="https://testserver")
    owner = admin.post("/api/auth/bootstrap", json=dict(username="admin", password=PASSWORD)).json()["user"]["id"]
    os.environ["VANTALINE_STANDARD_PREPARATION_ACCOUNTS"] = owner
    server.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED = True
    server.ai_detection_settings = lambda: dict(configured=True, provider="qwen", model="fixture", api_key="private-fixture")
    image, elements = fixture()
    calls = []
    recovery_mode = os.environ.get("PREPARATION_TEST_RECOVERY")
    observed = []
    region = dict(box=[.04,.04,.20,.08], state="exclude", reason="outside dimensions")
    initial = elements[1:] if recovery_mode else elements
    def observe(picture, **kwargs):
        observed.append(picture.size)
        if len(observed) == 1 or not recovery_mode:
            return copy.deepcopy(initial)
        stored_asset = next(a for a in server._text_v2_load("assets") if a.get("preparation_attempt"))
        assert stored_asset["preparation_attempt"]["state"] == "supplementing"
        assert stored_asset["preparation_attempt"]["original_elements"] == initial
        assert stored_asset["preparation_attempt"]["result"]["missing_regions"] == [region]
        if recovery_mode == "timeout": raise TimeoutError("local fixture timeout")
        if recovery_mode == "interrupted":
            standard = server._text_v2_owned("standards", stored_asset["standard_id"], owner)
            standard["preparation_job"]["heartbeat"] = 0
            server._text_v2_save("standards", standard)
            server.standard_preparation_jobs.view(standard["id"], owner)
        from local_inspection_service import standard_preparation as engine
        l,t,r,b = engine.pixels(region["box"], image.size)
        x,y,w,h = elements[0]["box"]
        return [{**elements[0], "box": [(x*600-l)/(r-l),(y*500-t)/(b-t),w*600/(r-l),h*500/(b-t)]}]
    server.standard_preparation_jobs.observe = observe
    def provider(*args):
        assert any(a.get("preparation_attempt", {}).get("state") == "classifying" for a in server._text_v2_load("assets"))
        calls.append(1)
        return dict(ok=True, parsed=dict(kind="label_design", coverage_complete=os.environ.get("PREPARATION_TEST_INCOMPLETE") != "1", missing_regions=[region] if recovery_mode else [], reason="fixture", elements=[{k: e[k] for k in ("id", "state", "reason")} for e in initial]))
    server.call_ai_mcp_tool = provider
    response = admin.post("/api/text-inspection/standards/import", data=dict(name="fixture", material_code="fixture", version_label="1"), files={"file": ("test.docx", docx())})
    assert_status(response, 200, "import")
    standard = response.json(); identity = standard["id"]; asset = standard["assets"][0]
    stored = server._text_v2_owned("assets", asset["id"], owner)
    data = png(image)
    server._text_v2_write(server.Path(stored["media_path"]), data)
    stored.update(sha256=server.sha256_bytes(data), status="candidate")
    server._text_v2_save("assets", stored)
    base = f"/api/text-inspection/standards/{identity}"
    assert_status(admin.post(base+"/confirm"), 200, "prepare activation")
    def wait():
        for _ in range(200):
            result = admin.get(base+"/preparation").json()
            if result["job"].get("state") != "processing": return result
            time.sleep(.02)
        raise AssertionError("preparation timeout")
    result = wait()
    if recovery_mode:
        item = result["items"][0]
        assert item["attempt"]["original_elements"] == initial
        assert len(calls) == 1 and len(observed) == 2
        if recovery_mode in {"timeout", "interrupted"}:
            assert not item.get("active"), result
            assert item["attempt"]["state"] == "review", result
            if recovery_mode == "interrupted":
                assert result["job"]["state"] == "interrupted", result
                assert not item["revisions"], result
        else:
            assert item["active"], result
            assert item["attempt"]["elements"][-1]["id"] == "r1e1"
            assert item["attempt"]["elements"][-1]["text"] == elements[0]["text"]
            media = item["attempt"]["diagnostics"]["recovery"]["regions"][0]
            assert_status(admin.get(media["region_url"]), 200, "local region evidence")
            assert_status(admin.get(media["ocr_url"]), 200, "local OCR evidence")
            admin.post("/api/auth/users", json=dict(username="other", password=PASSWORD, role="user", permissions=["inspection"]))
            other = TestClient(server.app, base_url="https://testserver")
            other.post("/api/auth/login", json=dict(username="other", password=PASSWORD))
            assert_status(other.get(media["ocr_url"]), 404, "cross owner local evidence")
        assert_status(admin.post(base+"/confirm"), 200, "local recovery dedup")
        assert len(calls) == 1 and len(observed) == 2
        print("local recovery state/evidence/no replay:", recovery_mode, "PASS")
        return
    if os.environ.get("PREPARATION_TEST_INCOMPLETE") == "1":
        assert not result["items"][0].get("active"), result
        assert not admin.get(base).json().get("confirmed_assets"), result
        assert_status(admin.post(base+"/confirm"), 200, "incomplete coverage dedup")
        assert len(calls) == 1, "incomplete coverage must not automatically retry"
        print("incomplete OCR coverage blocks activation: PASS")
        return
    assert result["items"][0]["active"], result
    assert len(calls) == 1
    assert "private-fixture" not in json.dumps(result)
    detail = admin.get(base).json()
    assert detail["confirmed_assets"][0]["preparation"]["id"] == result["items"][0]["active"]
    assert_status(admin.get(detail["assets"][0]["content_url"]), 200, "clean media")
    assert_status(admin.post(base+"/confirm"), 200, "idempotent activation")
    assert len(calls) == 1
    previous = copy.deepcopy(server._text_v2_load("revisions"))
    item = result["items"][0]
    edited = copy.deepcopy(elements)
    edited[2]["text"] = "21V"
    body = dict(source_sha256=item["source_sha256"], expected_draft=item["draft"], elements=edited)
    assert_status(admin.post(base+f"/preparation/{asset['id']}/confirm", json=body), 200, "manual revision")
    assert len(calls) == 1
    assert all(old in server._text_v2_load("revisions") for old in previous)
    assert_status(admin.post(base+f"/preparation/{asset['id']}/confirm", json=body), 409, "stale revision")
    admin.post("/api/auth/users", json=dict(username="other", password=PASSWORD, role="user", permissions=["inspection"]))
    other = TestClient(server.app, base_url="https://testserver")
    other.post("/api/auth/login", json=dict(username="other", password=PASSWORD))
    assert_status(other.get(base+"/preparation"), 404, "cross owner status")
    assert_status(other.get(detail["assets"][0]["content_url"]), 404, "cross owner media")
    response = admin.post("/api/text-inspection/label/compare", data=dict(standard_asset_id=asset["id"], comparison_id="prepared_test_001"), files={"captured_file": ("actual.png", data)})
    assert_status(response, 200, "prepared comparison")
    record = response.json()
    for _ in range(200):
        record = admin.get("/api/text-inspection/prepared-comparisons/"+record["id"]).json()
        if record["status"] != "attempting": break
        time.sleep(.02)
    assert record["status"] == "completed", record
    assert record["decision"] == "REVIEW_REQUIRED"  # Edited 21V is not present.
    assert len(calls) == 1, "comparison must not send another VLM request"
    assert_status(admin.get(record["reference_overlay_url"]), 200, "reference evidence")
    assert_status(other.get(record["reference_overlay_url"]), 404, "cross owner evidence")
    assert_status(admin.post("/api/text-inspection/label/compare", data=dict(standard_asset_id=asset["id"], comparison_id="prepared_test_001"), files={"captured_file": ("actual.png", png(image.resize((300,250))))}), 409, "comparison identity conflict")
    print("preparation routes/auth/version/dedup/manual: PASS")


if __name__ == "__main__": main()
