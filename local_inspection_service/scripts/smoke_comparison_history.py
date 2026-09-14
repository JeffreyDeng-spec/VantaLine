"""Real auth/routes with isolated data, no provider calls or production writes."""
import copy
import time
from local_inspection_service.scripts.smoke_text_inspection_v2_endpoints import server, TestClient, PASSWORD, docx, picture, assert_status, login
from local_inspection_service.comparison_history import project, state


def main():
    admin = TestClient(server.app, base_url="https://testserver")
    uid = admin.post("/api/auth/bootstrap", json=dict(username="admin", password=PASSWORD)).json()["user"]["id"]
    other_uid = admin.post("/api/auth/users", json=dict(username="other", password=PASSWORD, display_name="Other", role="user", permissions=["inspection"])).json()["user"]["id"]
    other = TestClient(server.app, base_url="https://testserver"); login(other, "other")
    anon = TestClient(server.app, base_url="https://testserver")
    standard = admin.post("/api/text-inspection/standards/import", data=dict(name="current name", material_code="MAT", version_label="1"), files={"file": ("test.docx", docx())}).json()
    sid = standard["id"]; asset = standard["assets"][0]
    stored_asset = server._text_v2_owned("assets", asset["id"], uid)
    server._text_v2_save("revisions", dict(id="rev_test", owner_user_id=uid, standard_id=sid, revision_number=1, created_at=1, confirmed_assets=[stored_asset]))
    image = picture("HISTORY")
    for index in range(25):
        rid = f"ins_history_{index:02}"
        path = server._text_v2_media_path(uid, sid, rid + ".png"); server._text_v2_write(path, image)
        r = dict(id=rid, owner_user_id=uid, standard_id=sid, standard_asset_id=asset["id"], comparison_id=rid,
                 standard_revision_id="rev_test", standard_revision_number=1, reference_sha256=stored_asset["sha256"],
                 created_at=100, updated_at=100, status="completed", decision="MATCH", auto_decision="MATCH", final_decision="",
                 source_path=str(path), source_sha256=server.sha256_bytes(image), differences=[],
                 diagnostics={"phase":"completed", "provider_result":{"parsed_response":{"safe":"raw"}}})
        if index % 2:
            r["history_display"] = dict(name="original name", material_code="OLD", version_label="V1", ordinal=1)
        server._text_v2_save("records", r, insert_only=True)
    r = {**r, "id":"ins_other", "comparison_id":"other", "owner_user_id":other_uid}
    server._text_v2_save("records", r, insert_only=True)
    base = "/api/text-inspection/history"
    before = copy.deepcopy(server._text_v2_load("records"))
    server.call_ai_mcp_tool = lambda *a, **k: (_ for _ in ()).throw(AssertionError("history called provider"))
    first = admin.get(base).json(); assert len(first["items"]) == 20
    assert first["items"][0]["id"] == "ins_history_24"
    second = admin.get(base, params={"cursor":first["next_cursor"]}).json()
    assert len(second["items"]) == 5 and second["next_cursor"] is None
    assert len({r["id"] for r in first["items"]+second["items"]}) == 25
    assert all("diagnostics" not in r and "source_path" not in r for r in first["items"])
    assert len(admin.get(base, params={"q":"original"}).json()["items"]) == 12
    assert admin.get(base, params={"result":"DIFFERENCES"}).json()["items"] == []
    assert admin.get(base, params={"q":"%' OR 1=1"}).json()["items"] == []
    for params in ({"limit":0},{"cursor":"bad"},{"result":"unknown"}):
        assert admin.get(base, params=params).status_code in {400,422}
    rid = "ins_history_23"
    for suffix in ("", "/diagnostics", "/media/preview", "/media/thumbnail", "/media/source", "/media/reference"):
        assert_status(admin.get(base+"/"+rid+suffix), 200, suffix)
        assert_status(other.get(base+"/"+rid+suffix), 404, "cross owner"+suffix)
        assert anon.get(base+"/"+rid+suffix).status_code == 401
    detail = admin.get(base+"/"+rid).json()
    assert admin.get(base+"/"+rid+"/media/source").content == image
    import io
    from PIL import Image
    with Image.open(io.BytesIO(admin.get(base+"/"+rid+"/media/thumbnail").content)) as thumbnail:
        assert max(thumbnail.size) <= 240
    assert detail["history"]["display"]["name"] == "original name"
    assert "source_path" not in detail and "provider_result" not in detail["diagnostics"]
    assert admin.get(detail["diagnostics_url"]).json()["provider_result"]["parsed_response"] == {"safe":"raw"}
    stored = server._text_v2_owned("standards", sid, uid); stored.update(status="deleted", name="renamed")
    server._text_v2_save("standards", stored)
    assert admin.get(base+"/"+rid).json()["history"]["display"]["name"] == "original name"
    assert admin.get(base+"/"+rid+"/media/reference").status_code == 200
    assert admin.get(base+"/"+rid+"/media/reference").headers["cache-control"] == "private, no-store"
    # Missing evidence is explicit; newer asset bytes cannot masquerade as history.
    stored_asset["sha256"] = "changed"; server._text_v2_save("assets", stored_asset)
    assert admin.get(base+"/"+rid+"/media/reference").status_code == 404
    assert server._text_v2_load("records") == before
    assert state(project({"id":"pending", "status":"attempting", "created_at":int(time.time())})) == "processing"
    assert state(project({"id":"old", "status":"attempting", "created_at":1})) == "timeout"
    assert state(project({"id":"failed", "status":"review_required", "diagnostics":{"phase":"failed"}})) == "failed"
    assert state(project({"id":"review", "status":"completed", "decision":"REVIEW_REQUIRED"})) == "completed"
    print("comparison history: pagination/search/auth/old evidence/deleted standard/nonmutation PASS")


if __name__ == "__main__": main()
