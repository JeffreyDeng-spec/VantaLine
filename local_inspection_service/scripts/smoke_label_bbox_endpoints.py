"""Actual extraction routes, controlled Qwen transport, no external requests."""
import io
import json
import os
import sys
import threading
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from local_inspection_service.scripts.smoke_text_inspection_v2_endpoints import server,TestClient,PASSWORD,picture,docx,login
from local_inspection_service import label_bbox


def main():
    admin=TestClient(server.app,base_url="https://testserver")
    uid=admin.post("/api/auth/bootstrap",json={"username":"admin","password":PASSWORD}).json()["user"]["id"]
    os.environ["VANTALINE_LABEL_EXTRACTION_ACCOUNTS"]=uid
    def create(identity="bbox_request_001",method="vlm_bbox"):
        return admin.post("/api/text-inspection/extractions",data={"target":"[0,0,1,1]","request_id":identity,"method":method},files={"file":("disguised.txt",picture("ABC"),"application/octet-stream")})
    assert create().status_code==403
    assert not admin.get("/api/text-inspection/extraction-capabilities").json()["bbox_enabled"]
    os.environ["VANTALINE_LABEL_BBOX_ACCOUNTS"]=uid
    server.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED=True
    server.ai_detection_settings=lambda:{"configured":True,"provider":"qwen","model":"frozen-fixture","api_key":"fixture-secret","base_url":"https://fixture.invalid"}
    calls=[];release=threading.Event()
    result={"isMultiLabel":True,"labelCount":6,"cropRect":{"x":.1,"y":.1,"w":.5,"h":.5}}
    def transport(request,settings,timeout):
        calls.append(json.loads(request.data));release.wait(3)
        return io.BytesIO(json.dumps({"choices":[{"message":{"content":json.dumps(result)}}],"usage":{"total_tokens":20}}).encode())
    server.ai_urlopen=transport
    root=create().json()
    assert create().json()["id"]==root["id"]
    assert create(method="manual").status_code==409
    release.set()
    def wait(root):
        for _ in range(100):
            value=admin.get("/api/text-inspection/extractions/"+root["id"]).json()
            if value["status"]!="attempting":return value
            time.sleep(.02)
        raise AssertionError("worker stuck")
    final=wait(root); assert final["status"]=="ready" and len(calls)==1,final
    assert calls[0]["temperature"]==.1 and calls[0]["max_tokens"]==512
    assert "fixture-secret" not in json.dumps(final)
    assert admin.get(final["media"]["input"]).content.startswith(b"\xff\xd8")
    admin.post("/api/auth/users",json={"username":"other","password":PASSWORD,"role":"user","permissions":["inspection"]})
    other=TestClient(server.app,base_url="https://testserver");login(other,"other")
    for url in ["/api/text-inspection/extractions/"+root["id"],*final["media"].values()]:assert other.get(url).status_code==404
    standard=admin.post("/api/text-inspection/standards/import",data={"name":"test","material_code":"BB","version_label":"V1"},files={"file":("s.docx",docx(),"application/octet-stream")}).json()
    asset=standard["assets"][0]["id"]
    assert admin.patch(f"/api/text-inspection/standards/{standard['id']}/assets/{asset}",json={"action":"confirm"}).status_code == 200
    assert admin.post(f"/api/text-inspection/standards/{standard['id']}/confirm").status_code == 200
    compare={"standard_asset_id":asset,"extraction_id":root["id"],"comparison_id":"compare_bbox_001"}
    assert admin.post("/api/text-inspection/label/compare",data=compare).status_code==409
    route=f"/api/text-inspection/extractions/{root['id']}/revise"
    confirmed=admin.post(route,json={"version":0,"polygon":final["polygon"],"confirm":True,"standard_asset_id":asset}).json()
    assert confirmed["status"]=="confirmed",confirmed
    assert admin.get(final["media"]["crop"]).content==admin.get(confirmed["media"]["crop"]).content
    assert admin.post(route,json={"version":0,"polygon":final["polygon"]}).status_code==409
    edited=admin.post(route,json={"version":1,"polygon":final["polygon"]}).json()
    assert edited["status"]=="ready"
    compare["extraction_id"]=confirmed["id"]
    assert admin.post("/api/text-inspection/label/compare",data=compare).status_code==409
    def timeout(*args,**kwargs): calls.append(1);raise TimeoutError("secret URL must not escape")
    server.ai_urlopen=timeout
    failed=wait(create("bbox_timeout_001").json());assert failed["status"]=="uncertain"
    before=len(calls);create("bbox_timeout_001");assert len(calls)==before
    assert "secret URL" not in json.dumps(failed)
    server.ai_urlopen=lambda *args,**kwargs:io.BytesIO(b"not json")
    invalid=wait(create("bbox_invalid_001").json())
    assert invalid["status"]=="needs_adjustment" and "crop" not in invalid["media"]
    altered=admin.post("/api/text-inspection/extractions",data={"target":"[0,0,1,1]","request_id":"bbox_request_001","method":"vlm_bbox"},files={"file":("changed.png",picture("CHANGED"),"image/png")})
    assert altered.status_code==409
    # Simulate a server restart losing an already-started worker: polling/reuse
    # must not call the provider even when its stored deadline has elapsed.
    lost=server._text_v2_owned("extractions",invalid["id"],uid)
    lost.update(status="attempting",deadline_at=0)
    server._text_v2_save("extractions",lost)
    def forbidden(*args,**kwargs):raise AssertionError("replayed lost task")
    server.ai_urlopen=forbidden
    recovered=create("bbox_invalid_001").json()
    assert recovered["status"]=="uncertain"
    # Small rectangles produce inspection evidence, but cannot be confirmed.
    tiny={"isMultiLabel":True,"labelCount":6,"cropRect":{"x":.1,"y":.1,"w":.08,"h":.1}}
    server.ai_urlopen=lambda *args,**kwargs:io.BytesIO(json.dumps({"choices":[{"message":{"content":json.dumps(tiny)}}]}).encode())
    small=wait(create("bbox_small_001").json())
    assert small["status"]=="needs_adjustment" and small["media"]["crop"]
    assert admin.post(f"/api/text-inspection/extractions/{small['id']}/revise",json={"version":0,"polygon":small["polygon"],"confirm":True,"standard_asset_id":asset}).status_code==400
    print("label bbox endpoints: PASS")


if __name__=="__main__":main()
