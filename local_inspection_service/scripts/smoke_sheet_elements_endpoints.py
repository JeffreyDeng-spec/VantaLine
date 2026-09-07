"""Real routes/auth/store with injected OCR; no paid requests or models."""
import copy
import io
import json
import os
import threading
import time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from local_inspection_service.scripts.smoke_text_inspection_v2_endpoints import server,TestClient,PASSWORD,assert_status,docx,picture,login


def main():
    admin=TestClient(server.app,base_url="https://testserver")
    uid=admin.post("/api/auth/bootstrap",json={"username":"admin","password":PASSWORD}).json()["user"]["id"]
    assert not admin.get("/api/text-inspection/sheet/capabilities").json()["enabled"]
    os.environ["VANTALINE_SHEET_ELEMENTS_ACCOUNTS"]=uid
    admin.post("/api/auth/users",json={"username":"other","password":PASSWORD,"display_name":"other","role":"user","permissions":["inspection"]})
    other=TestClient(server.app,base_url="https://testserver");login(other,"other")
    standard=admin.post("/api/text-inspection/standards/import",data={"name":"sheet","material_code":"SHEET","version_label":"V1"},files={"file":("labels.docx",docx(),"application/octet-stream")}).json()
    asset=standard["assets"][0];admin.post(f"/api/text-inspection/standards/{standard['id']}/confirm")
    calls=[]
    def ocr(image):
        calls.append(1)
        return [{"text":"20V","confidence":.99,"polygon":[[80,80],[180,80],[180,110],[80,110]]}]
    server.sheet_elements_ocr=ocr
    body={"standard_asset_id":asset["id"],"request_id":"template_001"}
    def poll(root):
        for _ in range(200):
            response=admin.get(f"/api/text-inspection/sheet/resources/{root}")
            assert_status(response,200,"poll")
            value=response.json()
            if value["status"] in {"draft","confirmed","completed","review"}:return value
            time.sleep(.02)
        raise AssertionError("task stuck")
    created=admin.post("/api/text-inspection/sheet/templates",json=body);assert_status(created,200,"template")
    root=created.json()["id"];draft=poll(root)
    assert draft["status"]=="draft",draft
    assert admin.post("/api/text-inspection/sheet/templates",json=body).json()["root_id"]==root
    route=f"/api/text-inspection/sheet/templates/{root}/revise"
    elements=[{"id":"one","type":"parameter","expected":"20V","box":[.1,.1,.2,.1],"required":True,"ignore_reason":"","match":"exact"}]
    assert_status(admin.post(route,json={"version":0,"elements":elements,"confirm":True}),409,"save before confirmation")
    edited=admin.post(route,json={"version":0,"elements":elements});assert_status(edited,200,"edit")
    assert_status(admin.post(route,json={"version":0,"elements":elements}),409,"stale edit")
    confirm={"version":1,"elements":elements,"confirm":True,"inventory_confirmed":True}
    confirmed=admin.post(route,json=confirm);assert_status(confirmed,200,"confirm")
    template=confirmed.json()
    assert_status(other.get(template["media"]["source"]),404,"template media isolation")
    assert_status(other.post(route,json=confirm),403,"gated edit")
    def create(rid="comparison_001",file=None):
        return admin.post("/api/text-inspection/sheet/jobs",data={"template_id":template["id"],"request_id":rid},files={"file":("fake.data",file or picture("ACTUAL"),"application/octet-stream")})
    started=create();assert_status(started,200,"compare")
    final=poll(started.json()["id"])
    assert final["result"]["candidate_decision"]=="MATCH" and final["result"]["decision"]=="REVIEW_REQUIRED",final
    assert final["diagnostics"]["external_attempts"]==0
    assert_status(other.get(f"/api/text-inspection/sheet/resources/{started.json()['id']}"),404,"task isolation")
    assert_status(other.get(final["media"]["actual_overlay"]),404,"evidence isolation")
    count=len(calls);assert create().json()["id"]==final["id"] and len(calls)==count
    assert_status(create(file=picture("CHANGED")),409,"identity conflict")
    assert_status(admin.post(route,json={"version":2,"elements":elements}),200,"edit invalidates confirmation")
    assert_status(create("comparison_002"),409,"old confirmation rejected")
    assert create().json()["id"]==final["id"],"historic idempotency must survive template edit"
    # Persisted lost-worker root expires exactly once; no automatic reexecution.
    lost=copy.deepcopy(server._text_v2_owned("sheet_elements",started.json()["id"],uid))
    lost.update(id="sej_lost",root_id="sej_lost",deadline_at=time.time()-1)
    server._text_v2_save("sheet_elements",lost,insert_only=True)
    recovered=poll("sej_lost");assert recovered["status"]=="review" and len(calls)==count
    assert poll("sej_lost")["id"]==recovered["id"]
    # Optional advisory is claimed once and never provides MATCH evidence.
    provider_calls=[]
    os.environ["VANTALINE_SHEET_ELEMENTS_VLM_ACCOUNTS"]=uid
    server.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED=True
    server.ai_detection_settings=lambda:{"configured":True,"provider":"qwen","model":"fixture","base_url":"https://fixture.invalid/v1/chat/completions","api_key":"fixture-secret"}
    def provider(request,settings,timeout):
        provider_calls.append(1)
        return io.BytesIO(json.dumps({"choices":[{"message":{"content":json.dumps({"elements":[{"type":"graphic","expected":"logo","box":[.1,.1,.3,.2]}],"api_key":"fixture-secret"})}}],"usage":{"total_tokens":123}}).encode())
    server.ai_urlopen=provider
    advisory_body={**body,"request_id":"template_advisory_001"}
    attempt=admin.post("/api/text-inspection/sheet/templates",json=advisory_body);assert_status(attempt,200,"advisory template")
    proposed=poll(attempt.json()["root_id"])
    assert len(provider_calls)==1 and proposed["status"]=="draft"
    assert any(v["type"]=="graphic" for v in proposed["elements"])
    assert "fixture-secret" not in json.dumps(proposed)
    assert proposed["diagnostics"]["vlm"]["usage"]["total_tokens"]==123
    sent=proposed["diagnostics"]["vlm"]["media"]["advisory_0"]
    assert_status(other.get(sent),404,"advisory input isolation")
    assert_status(admin.get(sent),200,"advisory input evidence")
    admin.post("/api/text-inspection/sheet/templates",json=advisory_body);assert len(provider_calls)==1
    def timeout_provider(*args,**kwargs):
        provider_calls.append(1);raise TimeoutError("fixture-secret")
    server.ai_urlopen=timeout_provider
    timeout_body={**body,"request_id":"template_advisory_timeout"}
    timed=admin.post("/api/text-inspection/sheet/templates",json=timeout_body).json()
    outcome=poll(timed["root_id"]);assert outcome["diagnostics"]["vlm"]["status"]=="uncertain"
    admin.post("/api/text-inspection/sheet/templates",json=timeout_body);assert len(provider_calls)==2
    assert "fixture-secret" not in json.dumps(outcome)
    print("whole-sheet auth, immutable revisions, idempotency, restart, media and gate smoke: PASS")


if __name__=="__main__": main()
