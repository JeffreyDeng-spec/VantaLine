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
    other_login = other.post("/api/auth/login", json=dict(username="other", password=PASSWORD)).json()
    assert_status(other.get(base+"/preparation"), 404, "cross owner status")
    assert_status(other.get(detail["assets"][0]["content_url"]), 404, "cross owner media")
    qwen_mode = os.getenv("PREPARATION_TEST_QWEN")
    qwen_calls = []
    if qwen_mode:
        from local_inspection_service import qwen_evidence_jobs as qj
        os.environ["VANTALINE_QWEN_OCR_ACCOUNTS"] = owner
        server.ai_detection_settings = lambda: dict(provider="qwen", model="fixture", api_key="private-fixture", base_url="https://dashscope.aliyuncs.com")
        def remote_ocr(settings, blob, size, timeout):
            claims = server._text_v2_load("ocr_evidence")
            assert len(claims) == 1 and claims[0]["status"] == "attempting"
            qwen_calls.append("ocr")
            result = []
            for index, e in enumerate(elements):
                x,y,w,h = e["box"]
                result.append(dict(id=f"o{index}", type="text", text=e["text"], box=[x,y,x+w,y+h], confidence=None, provenance="qwen_ocr"))
            return result, dict(model=qj.ocr.MODEL, usage={})
        def mapping(settings, request, timeout):
            assert any(r.get("diagnostics",{}).get("llm_call",{}).get("state") == "attempting" for r in server._text_v2_load("records"))
            qwen_calls.append("llm")
            return {"mappings":[]}, dict(model="fixture", usage={})
        qj.ocr.recognize = remote_ocr
        qj.llm = mapping
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
    if qwen_mode:
        assert qwen_calls.count("ocr") == 1
        assert record["diagnostics"]["provider"] == "qwen_ocr"
        source_url = f"/api/text-inspection/prepared-comparisons/{record['id']}/media/source"
        assert_status(admin.get(source_url),200,"actual source evidence")
        assert_status(other.get(source_url),404,"cross owner actual evidence")
        duplicate = admin.post("/api/text-inspection/label/compare", data=dict(standard_asset_id=asset["id"],comparison_id="prepared_test_001"), files={"captured_file":("actual.png",data)}).json()
        assert duplicate["id"] == record["id"] and qwen_calls.count("ocr") == 1
        cached = admin.post("/api/text-inspection/label/compare", data=dict(standard_asset_id=asset["id"],comparison_id="prepared_test_cached"), files={"captured_file":("actual.png",data)}).json()
        for _ in range(200):
            cached = admin.get(f"/api/text-inspection/prepared-comparisons/{cached['id']}").json()
            if cached["status"] != "attempting": break
            time.sleep(.02)
        assert cached["status"] == "completed" and cached["diagnostics"]["cache_hit"]
        assert qwen_calls.count("ocr") == 1
        late = copy.deepcopy(server._text_v2_owned("records",record["id"],owner))
        late.update(status="attempting",decision="MATCH")
        assert server._text_v2_update_attempt("records",late) is False
        assert server._text_v2_owned("records",record["id"],owner)["decision"] == "REVIEW_REQUIRED"
        claim = server._text_v2_load("ocr_evidence")[0]
        claim["status"] = "unknown"
        server._text_v2_save("ocr_evidence",claim)  # Isolated fixture only.
        before_calls = len(qwen_calls)
        unknown = admin.post("/api/text-inspection/label/compare", data=dict(standard_asset_id=asset["id"],comparison_id="prepared_test_unknown"), files={"captured_file":("actual.png",data)}).json()
        for _ in range(200):
            unknown = admin.get(f"/api/text-inspection/prepared-comparisons/{unknown['id']}").json()
            if unknown["status"] != "attempting": break
            time.sleep(.02)
        assert unknown["status"] == "review_required" and len(qwen_calls) == before_calls
        assert unknown["diagnostics"]["error"] == "prior_ocr_pending_or_unknown_not_replayed"
        interrupted = server._text_v2_owned("records",unknown["id"],owner)
        interrupted.update(status="attempting",created_at=int(time.time())-121,deadline_at=time.time()-1)
        server._text_v2_save("records",interrupted)
        expired = admin.get(f"/api/text-inspection/prepared-comparisons/{unknown['id']}").json()
        assert expired["status"] == "review_required" and expired["diagnostics"]["phase"] == "timeout"
        assert not server._text_v2_update_attempt("records",{**interrupted,"status":"completed","decision":"MATCH"})
        assert len(qwen_calls) == before_calls, "restart/status must not replay calls"
    assert_status(admin.post("/api/text-inspection/label/compare", data=dict(standard_asset_id=asset["id"], comparison_id="prepared_test_001"), files={"captured_file": ("actual.png", png(image.resize((300,250))))}), 409, "comparison identity conflict")
    # Isolated graphics-only fixture, including zero recognized text. Never
    # confuse a provider failure with an intentionally non-comparable template.
    from PIL import Image, ImageDraw
    graphic = Image.new("RGBA", (100,100), "white")
    ImageDraw.Draw(graphic).rectangle((30,30,60,60), fill="black")
    stored = server._text_v2_owned("assets",asset["id"],owner)
    graphic_data=png(graphic)
    server._text_v2_write(server.Path(stored["media_path"]),graphic_data)
    stored["sha256"]=server.sha256_bytes(graphic_data)
    stored["preparation_attempt"].update(elements=[],result={"kind":"label_design","coverage_complete":True},diagnostics={"ok":True})
    server._text_v2_save("assets",stored)
    graphics_body=dict(source_sha256=stored["sha256"],expected_draft=stored["preparation_draft"],elements=[])
    route=base+f"/preparation/{asset['id']}/confirm"
    assert_status(admin.post(route,json=graphics_body),409,"graphics require explicit confirmation")
    assert_status(admin.post(route,json={**graphics_body,"allow_graphics_only":"true"}),400,"strict graphics boolean")
    graphics_body["allow_graphics_only"]=True
    for bad in ({"ok":False},{"ok":True,"failure":"TimeoutError"},{"ok":True,"recovery":{"reasons":["incomplete"]}}):
        stored["preparation_attempt"]["diagnostics"]=bad; server._text_v2_save("assets",stored)
        assert_status(admin.post(route,json=graphics_body),409,"failed recognition is not graphics-only")
    stored["preparation_attempt"]["diagnostics"]={"ok":True}; server._text_v2_save("assets",stored)
    os.environ["VANTALINE_STANDARD_PREPARATION_ACCOUNTS"] = owner+","+other_login["user"]["id"]
    assert_status(other.post(route,json=graphics_body),404,"cross owner graphics write")
    os.environ["VANTALINE_STANDARD_PREPARATION_ACCOUNTS"] = owner
    assert_status(admin.post(route,json=graphics_body),200,"explicit graphics-only save")
    updated=admin.get(base).json()["assets"][0]
    assert updated["comparison_ready"] is False
    assert updated["active_preparation"]["graphics_only"] is True
    assert_status(admin.get(updated["content_url"]),200,"graphics cleaned media")
    before=len(observed)
    assert_status(admin.post("/api/text-inspection/label/compare",data=dict(standard_asset_id=asset["id"],comparison_id="graphics_blocked"),files={"captured_file":("actual.png",data)}),409,"graphics cannot compare")
    assert len(observed)==before and len(calls)==1,"no OCR or VLM for unsupported comparison"
    assert_status(admin.post(route,json=graphics_body),409,"graphics stale save rejected")
    from types import SimpleNamespace
    from local_inspection_service.standard_preparation_compare import run
    legacy=dict(diagnostics={"template":{"elements":[]}})
    writes=[]
    run(SimpleNamespace(_text_v2_save=lambda kind,value:writes.append(copy.deepcopy(value)),clear_thread_runtime_repository_selection=lambda:None),None,legacy,b'')
    assert legacy["decision"]=="REVIEW_REQUIRED" and legacy["diagnostics"]["phase"]=="unsupported_template"
    assert len(writes)==1,"legacy empty worker terminates before OCR or slots"
    print("preparation routes/auth/version/dedup/manual/graphics: PASS")


if __name__ == "__main__": main()
