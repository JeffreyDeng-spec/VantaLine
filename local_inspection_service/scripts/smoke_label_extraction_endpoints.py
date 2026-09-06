#!/usr/bin/env python3
"""Exercise real auth/storage/routes with a controlled one-call image provider."""
import json
import os
import sys
import time
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from local_inspection_service.scripts.smoke_text_inspection_v2_endpoints import server, TestClient, PASSWORD, assert_status, docx, picture, login


def main():
    admin=TestClient(server.app,base_url="https://testserver")
    bootstrap=admin.post("/api/auth/bootstrap",json={"username":"admin","password":PASSWORD})
    assert_status(bootstrap,200,"bootstrap")
    uid=bootstrap.json()["user"]["id"]
    assert_status(admin.get("/api/text-inspection/extraction-capabilities"),200,"capabilities route precedes SPA")
    assert not admin.get("/api/text-inspection/extraction-capabilities").json()["enabled"]
    os.environ["VANTALINE_LABEL_EXTRACTION_ACCOUNTS"]=uid
    admin.post("/api/auth/users",json={"username":"other","password":PASSWORD,"display_name":"other","role":"user","permissions":["inspection"]})
    other=TestClient(server.app,base_url="https://testserver"); login(other,"other")
    standard=admin.post("/api/text-inspection/standards/import",data={"name":"label","material_code":"EXTRACT","version_label":"V1"},files={"file":("labels.docx",docx(),"application/octet-stream")}).json()
    asset=standard["assets"][0]
    assert_status(admin.post(f"/api/text-inspection/standards/{standard['id']}/confirm"),200,"confirm standard")
    def create(request_id="manual_001",method="manual",target="[0.1,0.1,0.8,0.8]"):
        return admin.post("/api/text-inspection/extractions",data={"target":target,"request_id":request_id,"method":method},files={"file":("disguised.data",picture("ABC"),"application/octet-stream")})
    initial=create(); assert_status(initial,200,"manual extraction")
    root=initial.json(); assert root["status"]=="needs_adjustment"
    assert create().json()["id"]==root["id"]
    assert_status(create(target="[0.2,0.2,0.6,0.6]"),409,"identity conflict")
    assert_status(other.get(f"/api/text-inspection/extractions/{root['id']}"),404,"account isolation")
    assert_status(other.get(root["media"]["source"]),404,"media isolation")
    assert_status(admin.get(root["media"]["source"]),200,"source")
    compare={"standard_asset_id":asset["id"],"extraction_id":root["id"],"comparison_id":"cmp_extract_001"}
    assert_status(admin.post("/api/text-inspection/label/compare",data=compare),409,"unconfirmed denied")
    points=[[.15,.15],[.85,.15],[.85,.85],[.15,.85]]
    route=f"/api/text-inspection/extractions/{root['id']}/revise"
    assert_status(admin.post(route,json={"version":0,"polygon":points,"confirm":True,"standard_asset_id":asset["id"]}),409,"must preview first")
    bad=[[.1,.1],[.9,.9],[.1,.9],[.9,.1]]
    assert_status(admin.post(route,json={"version":0,"polygon":bad}),400,"self intersection")
    revision=admin.post(route,json={"version":0,"polygon":points}); assert_status(revision,200,"save edit")
    rev=revision.json(); assert rev["version"]==1 and rev["status"]=="ready"
    assert_status(admin.post(route,json={"version":0,"polygon":points}),409,"stale edit denied")
    confirmed=admin.post(route,json={"version":1,"polygon":points,"confirm":True,"standard_asset_id":asset["id"]})
    assert_status(confirmed,200,"confirm extraction")
    conf=confirmed.json(); compare["extraction_id"]=conf["id"]
    server.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED=False
    result=admin.post("/api/text-inspection/label/compare",data=compare)
    assert_status(result,200,"compare server crop")
    assert result.json()["diagnostics"]["extraction"]["crop_sha256"]==conf["crop_sha256"]
    assert_status(admin.post("/api/text-inspection/label/compare",data=compare,files={"captured_file":("a.png",picture("A"),"image/png")}),400,"ambiguous input denied")
    assert_status(admin.post(route,json={"version":2,"polygon":points}),200,"edit invalidates confirmation")
    compare["comparison_id"]="cmp_extract_002"
    assert_status(admin.post("/api/text-inspection/label/compare",data=compare),409,"old confirmation rejected")
    # Provider timeout/response-loss does not cause a second external call.
    calls=[]; release=threading.Event()
    class Provider:
        def generate_image(self,*args,**kwargs):
            calls.append(1); release.wait(5); raise TimeoutError("simulated")
    server.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED=True
    server.image_generation_settings=lambda:{"configured":True,"provider":"gemini","model":"fixture","timeout_seconds":10}
    server.image_generation_provider_from_settings=lambda settings:Provider()
    attempt=create("ai_request_001","ai"); assert_status(attempt,200,"AI attempt")
    assert_status(create("ai_request_001","ai"),200,"duplicate AI attempt")
    release.set()
    for _ in range(100):
        final=admin.get(f"/api/text-inspection/extractions/{attempt.json()['id']}").json()
        if final["status"]!="attempting": break
        time.sleep(.02)
    assert final["status"]=="uncertain" and len(calls)==1
    create("ai_request_001","ai"); assert len(calls)==1
    # Expiration retains tombstones and never deletes a previously confirmed root.
    expired=create("expired_draft_001").json()
    stored=server._text_v2_owned("extractions",expired["id"],uid)
    stored["created_at"]=int(time.time())-8*86400
    server._text_v2_save("extractions",stored)
    old=server._text_v2_owned("extractions",root["id"],uid)
    old["created_at"]=int(time.time())-8*86400
    server._text_v2_save("extractions",old)
    admin.get("/api/text-inspection/extraction-capabilities")
    assert admin.get(f"/api/text-inspection/extractions/{expired['id']}").json()["status"]=="expired"
    assert_status(admin.get(expired["media"]["source"]),404,"expired draft media removed")
    assert_status(admin.get(root["media"]["source"]),200,"confirmed evidence retained")
    assert_status(create("expired_draft_001"),410,"expired ID cannot replay")
    print("single label extraction endpoint smoke: PASS")


if __name__=="__main__": main()
