"""Offline geometry, source safety and real-route document import regression."""
import io
import json
import os
from pathlib import Path
import sys
import threading
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from local_inspection_service.scripts.smoke_text_inspection_v2_endpoints import server, TestClient, PASSWORD, picture, docx, login
from local_inspection_service import document_label_crop as crop
from local_inspection_service import document_label_source as source
from local_inspection_service import document_label_convert as converter


def main():
    image = crop.decode(picture("SOURCE"))
    box = [.1234, .2045, .8756, .9071]
    pixels = crop.rectangle(box, image.size)
    normalized = crop.decode(crop.png(image.crop(pixels)))
    assert normalized.tobytes() == image.crop(pixels).tobytes()
    for value, exact in zip(pixels, [box[0]*image.width, box[1]*image.height, box[2]*image.width, box[3]*image.height]):
        assert abs(value - exact) < 1
    for invalid in ([0, 0, 0, 1], [0, 0, 1.01, 1], [0, float("nan"), 1, 1], [False, 0, 1, 1], None):
        try:
            crop.rectangle(invalid, image.size)
            raise AssertionError("invalid coordinates accepted")
        except ValueError:
            pass
    assert crop.classify({"classification": "label_design", "box": [0, 0, 1, 1]})["box"] == [0, 0, 1, 1]
    assert not converter.available()  # never run an uncommissioned converter
    original_doc = docx()
    # Duplicate references retain context and do not create two inference pairs.
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original_doc)) as old, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as new:
        for name in old.namelist():
            data = old.read(name)
            if name == "word/document.xml":
                data = data.replace(b"</w:body>", b'<w:p><w:r><w:drawing><a:blip r:embed="rId1"/></w:drawing></w:r></w:p></w:body>')
            new.writestr(name, data)
    duplicate_doc = output.getvalue()
    assets = source.extract(duplicate_doc)
    assert len(assets) == 1 and len(assets[0]["references"]) == 2
    def altered_doc(extra_xml="", corrupt=False):
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(original_doc)) as old, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as new:
            for name in old.namelist():
                data = old.read(name)
                if name == "word/document.xml":
                    data = data.replace(b"</w:drawing>", extra_xml.encode() + b"</w:drawing>")
                if corrupt and name.endswith("image1.png"):
                    data = b"not-an-image"
                new.writestr(name, data)
        return output.getvalue()
    assert not source.extract(altered_doc('<a:srcRect l="-5" r="-20"/><a:xfrm rot="0" flipH="false"/>'))[0]["review_reason"]
    assert source.extract(altered_doc('<a:srcRect l="5"/>'))[0]["review_reason"]
    assert source.extract(altered_doc('<a:effectLst><a:shadow/></a:effectLst>'))[0]["review_reason"]
    assert source.extract(altered_doc(corrupt=True))[0]["review_reason"]

    admin = TestClient(server.app, base_url="https://testserver")
    uid = admin.post("/api/auth/bootstrap", json={"username": "admin", "password": PASSWORD}).json()["user"]["id"]
    assert not admin.get("/api/text-inspection/document-import-capabilities").json()["enabled"]
    os.environ["VANTALINE_DOCUMENT_LABEL_ACCOUNTS"] = uid
    def upload(material, data=duplicate_doc):
        return admin.post("/api/text-inspection/standards/import", data={"name": "test", "material_code": material, "version_label": "V1"}, files={"file": ("test.docx", data, "application/octet-stream")})
    assert upload("unavailable").status_code == 503
    server.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED = True
    server.ai_detection_settings = lambda: {"configured": True, "provider": "qwen", "model": "test-model", "api_key": "test-secret", "base_url": "https://fixture.invalid"}
    calls = []
    response_kind = "label_design"
    verify_pass = True
    release = threading.Event()
    def transport(request, settings, timeout):
        assert settings["single_attempt"] is True
        payload = json.loads(request.data)
        calls.append(payload)
        release.wait(3)
        images = [v for v in payload["messages"][0]["content"] if v["type"] == "image_url"]
        result = {"classification": response_kind, "box": box if response_kind == "label_design" else None, "reason": "test"} if len(images) == 1 else {
            "target_correct": verify_pass, "content_complete": True, "outside_notes_absent": True, "other_objects_absent": True, "reason": "test-secret"}
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": json.dumps(result)}}], "usage": {"total_tokens": 10}}).encode())
    server.ai_urlopen = transport
    standard = upload("pass").json()
    assert upload("pass").json()["id"] == standard["id"]
    assert upload("pass", original_doc).status_code == 409
    root_url = "/api/text-inspection/document-imports/" + standard["import_job_id"]
    assert admin.post(f"/api/text-inspection/standards/{standard['id']}/confirm").status_code == 409
    release.set()
    def wait(url):
        for _ in range(200):
            value = admin.get(url).json()
            if value.get("status") != "processing":
                return value
            time.sleep(.02)
        raise AssertionError("import stuck")
    result = wait(root_url)
    assert result["status"] == "completed", result
    assert result["counts"]["candidate"] == 1 and len(calls) == 2, result
    assert "test-secret" not in json.dumps(result)
    item = result["items"][0]
    actual = admin.get(item["result"]["media"]["crop"]).content
    source_image = crop.decode(assets[0]["blob"])
    assert crop.decode(actual).tobytes() == source_image.crop(crop.rectangle(box, source_image.size)).tobytes()
    standard_detail = admin.get("/api/text-inspection/standards/" + standard["id"]).json()
    assert len(standard_detail["assets"]) == 1
    assert admin.get(standard_detail["assets"][0]["content_url"]).content == actual
    assert admin.post(f"/api/text-inspection/standards/{standard['id']}/confirm").status_code == 200
    review_url = root_url + "/items/" + item["id"] + "/review"
    revised = admin.post(review_url, json={"version": 0, "action": "confirm", "box": [.1, .1, .9, .9]})
    assert revised.status_code == 200, revised.text
    assert len(calls) == 2
    assert admin.post(review_url, json={"version": 0, "action": "exclude"}).status_code == 409
    changed = admin.get("/api/text-inspection/standards/" + standard["id"]).json()
    assert changed["revision_number"] == 2
    assert len(changed["assets"]) == 2 and sum(a["status"] == "candidate" for a in changed["assets"]) == 1
    assert admin.get(standard_detail["assets"][0]["content_url"]).content == actual
    admin.post("/api/auth/users", json={"username": "other", "password": PASSWORD, "role": "user", "permissions": ["inspection"]})
    other = TestClient(server.app, base_url="https://testserver"); login(other, "other")
    for url in (root_url, item["media"]["normalized"], item["result"]["media"]["crop"]):
        assert other.get(url).status_code == 404
    assert other.post(review_url, json={"version": 1, "action": "exclude"}).status_code == 404
    response_kind = "non_label"
    excluded = upload("nonlabel").json()
    value = wait("/api/text-inspection/document-imports/" + excluded["import_job_id"])
    assert value["counts"]["excluded"] == 1 and len(calls) == 3
    response_kind = "label_design"; verify_pass = False
    failed = upload("review").json()
    failed_url = "/api/text-inspection/document-imports/" + failed["import_job_id"]
    failed_result = wait(failed_url)
    assert failed_result["counts"]["needs_confirmation"] == 1 and len(calls) == 5
    assert not admin.get("/api/text-inspection/standards/" + failed["id"]).json()["assets"]
    def timeout(*args, **kwargs):
        calls.append({}); raise TimeoutError("secret-url-do-not-log")
    server.ai_urlopen = timeout
    unknown = upload("unknown").json()
    unknown_url = "/api/text-inspection/document-imports/" + unknown["import_job_id"]
    unknown_result = wait(unknown_url)
    assert unknown_result["counts"]["needs_confirmation"] == 1 and len(calls) == 6
    assert "secret-url-do-not-log" not in json.dumps(unknown_result)
    upload("unknown"); admin.get(unknown_url)
    assert len(calls) == 6
    retry_url = unknown_url + "/items/" + unknown_result["items"][0]["id"] + "/retry"
    body = {"version": 0, "request_id": "explicit-retry-001"}
    assert admin.post(retry_url, json=body).status_code == 200
    assert admin.post(retry_url, json=body).status_code == 200
    for _ in range(100):
        if len(calls) == 7:
            break
        time.sleep(.02)
    assert len(calls) == 7
    assert admin.post(retry_url, json={"version": "wrong", "request_id": "explicit-retry-001"}).status_code == 400
    assert admin.post(review_url, json=[]).status_code == 400
    # Simulate a lost worker without resubmission, then preserve its review state.
    lost_id = "lost_doc_root"
    lost = {"id": lost_id, "root_id": lost_id, "standard_id": standard["id"], "owner_user_id": uid,
            "kind": "root", "created_at": time.time() - 200, "stage": "定位"}
    server._text_v2_save("document_imports", lost, insert_only=True)
    before = len(calls)
    recovered = admin.get("/api/text-inspection/document-imports/" + lost_id).json()
    assert recovered["status"] == "interrupted" and len(calls) == before
    print("document label import: PASS (offline; no accuracy/production claim)")


if __name__ == "__main__":
    main()
