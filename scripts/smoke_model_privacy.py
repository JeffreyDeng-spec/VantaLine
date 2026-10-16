"""Exercise real security + privacy middleware with synthetic domain records.

No model calls, physical I/O, production data or application startup are used.
"""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware
from local_inspection_service.auth.middleware import SecurityDependencies, register_security_middleware
from local_inspection_service.runtime.identity import RequestIdentity
from local_inspection_service.privacy.presentation import Presentation, SENSITIVE
from local_inspection_service.privacy.references import References, runtime_key

MODEL = "trained_train_real_0123456789abcdef0123456789abcdef__yolo"
RAW = {
    "available_models": [{"id": MODEL, "task_id": "pipeline-one", "task_label": "Privacy sample", "variant": "yolo", "label": "YOLO v8", "exists": True, "path": "/private/model.pt"}],
    "active_model_id": MODEL,
    "yolo_warmup": {"loaded_model_ids": [MODEL], "selected_model_id": MODEL, "selected_model_ready": True},
    "ai_detection": {"provider_label": "豆包", "model": "doubao-vision-1", "configured": True, "status": "ready"},
    "items": [{"id": "history-1", "diagnostics": {"provider": "gemini", "model": "gemini-2.5"}, "profile_snapshot": {"model": "new-unknown-provider"}, "internal_model_detail": "private", "reference_text": "客户正文 Gemini YOLO", "actual_text": "客户正文 Gemini YOLO", "model_id": MODEL}],
    "required_accessory_counts": {"part-123": 2},
    "annotated_url": "/outputs/users/member/yolo_result.jpg",
    "rule": {"passed": True, "missing": []}, "passed": True,
    "error": "Gemini transport error", "session_id": "provider-session",
}


def fixture(presentation, dist=None):
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=32)
    identity = RequestIdentity()
    touched = []
    def authenticate(request, **kwargs):
        role = request.cookies.get("role")
        if not role:
            return None, {"users": [1]}, False
        user = {"id": "admin" if role in {"admin", "downgraded"} else "member", "username": "privacy-test", "display_name": "Privacy test", "role": "admin" if role == "admin" else "user", "permissions": ["inspection", "training_pipeline", "model_library", "ai_config", "agent_config", "system_settings", "worker_settings"]}
        return user, {"users": [1]}, False
    security = SecurityDependencies(authenticate, lambda s: bool(s["users"]), identity, lambda path, user: "/users/member/" in path, lambda a,b: True, lambda origin: True)
    register_security_middleware(app, security, presentation=presentation)

    @app.get("/api/status")
    def status(): return RAW

    @app.get("/api/provider-failure")
    def provider_failure():
        return JSONResponse({"detail":"unlisted-private-engine failed at internal endpoint", "debug":{"internal":"provider response"}}, status_code=502)

    @app.post("/api/analyze/camera")
    async def camera(file: UploadFile = File(...), model_id: str = Form(...), plc_session_id: str = Form(...)):
        touched.append((model_id, plc_session_id, await file.read()))
        return {"passed": True, "model": {"id": model_id, "variant": "yolo"}, "plc_sync": {"session_id": plc_session_id, "model_id": model_id, "write_frame_hex": "0244303303", "dispatch_id": "dispatch-one"}}

    @app.post("/api/pipeline/tasks")
    async def pipeline(request: Request):
        body = await request.json()
        touched.append(body)
        return body

    @app.get("/api/text-compare-codex/tasks/{task_id}")
    def task(task_id: str): return {"id": task_id, "model": "gemini-3", "status": "completed", "summary": {"message": "检查完成"}}

    @app.get("/api/ai/config")
    @app.post("/api/ai/config")
    @app.get("/api/agent/config")
    @app.post("/api/agent/config")
    @app.get("/api/admin/model-profiles")
    @app.post("/api/admin/model-profiles")
    @app.get("/api/text-inspection/history/one/diagnostics")
    @app.get("/api/text-inspection/prepared-comparisons/one/media/audit-one")
    def private(request: Request):
        touched.append("PRIVATE")
        if dist and request.url.path == "/api/admin/model-profiles":
            return {"revision": 1, "bindings": {"pipeline": "profile-one"}, "profiles": [{"id": "profile-one", "name": "Gemini production", "version": 1, "provider": "gemini", "model": "gemini-3", "capabilities": ["vision"], "used_by": ["pipeline"], "enabled": True}], "providers": [{"id": "gemini", "model": "gemini-3", "base_url": ""}], "purposes": [{"id": "pipeline", "label": "AI 检测", "capability": "vision", "advanced": False}]}
        return {"model": "gemini-3", "provider": "gemini"}

    @app.get("/api/plc/capture-events")
    def events():
        async def pieces():
            body = b'data: {"model_id":"'+MODEL.encode()+b'","provider":"gemini","session_id":"lease-original","passed":true}\n\n'
            for byte in body:
                yield bytes([byte])
        return StreamingResponse(pieces(), media_type="text/event-stream")

    @app.get("/api/auth/status")
    def auth_status(request: Request):
        user, _, _ = authenticate(request)
        return {"authenticated": bool(user), "user": user, "features": {"worker_settings": "RunPod / 远程执行设置"}}

    @app.get("/api/{path:path}")
    def browser_support(path: str):
        if path == "user/preferences/tasks": return {"exists": True, "pinned_task_ids": [], "archived_task_ids": []}
        if path == "version": return {"release": "development", "git_commit": "unknown", "consistent": True}
        if path == "training/resources": return {"ai_detection_tasks": [], "models": [], "datasets": [], "tasks": []}
        if path == "pipeline/tasks": return {"items": [{"id": "pipeline-one", "name": "Privacy sample", "stage": "library", "status": "completed", "detection_method": "yolo", "model_exists": True, "accessory_ids": ["part-A"], "accessory_names": ["Test part"], "accessory_counts": {"part-A":2}}]}
        if path.startswith("admin/model-profiles/"): return {"items": []}
        return {"items": [], "tasks": [], "enabled": False, "configured": False}

    @app.get("/outputs/{path:path}")
    @app.get("/static/{path:path}")
    def output(path: str):
        if dist:
            target = (dist/path).resolve()
            if target.is_relative_to(dist.resolve()) and target.is_file():
                return FileResponse(target)
        return PlainTextResponse(path)

    @app.get("/{path:path}")
    def index(path: str):
        return FileResponse(dist/"index.html") if dist else PlainTextResponse("index")
    return TestClient(app), touched


class Privacy(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.presentation = Presentation(References(lambda: runtime_key(Path(self.directory.name))))
        self.client, self.touched = fixture(self.presentation)

    def tearDown(self): self.directory.cleanup()

    def role(self, role="member"):
        self.client.cookies.clear()
        if role: self.client.cookies.set("role", role)

    def test_import_is_inert_and_middleware_checkpoint_rejects_mutants(self):
        # A fresh import must not invoke the crypto library's platform subprocess
        # or initialize runtime resources during isolated application composition.
        subprocess.run([sys.executable, "-c", "from unittest.mock import patch; "
            "guard=patch('subprocess.Popen', side_effect=AssertionError('external operation')); "
            "guard.start(); from local_inspection_service.privacy.presentation import Presentation; "
            "from local_inspection_service.privacy.references import References; "
            "Presentation(References(lambda: (_ for _ in ()).throw(AssertionError('key read'))))"], check=True)
        from model_privacy_source_contract import middleware_checkpoint
        from starlette.middleware import Middleware
        from local_inspection_service.privacy.http import ModelPrivacyMiddleware
        entry = Middleware(ModelPrivacyMiddleware, presentation=self.presentation)
        other = Middleware(GZipMiddleware)
        self.assertEqual(middleware_checkpoint([other, entry], self.presentation), [other])
        for entries in ([entry, other], [entry, entry], [other],
                        [Middleware(ModelPrivacyMiddleware, presentation=object())]):
            with self.assertRaises(AssertionError): middleware_checkpoint(entries, self.presentation)

    def test_closed_projection_history_and_customer_text(self):
        self.role()
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        public = response.json()
        reference = public["active_model_id"]
        self.assertTrue(reference.startswith("ref1_"))
        self.assertEqual(public["available_models"][0]["id"], reference)
        self.assertEqual(public["vision_warmup"]["loaded_model_ids"], [reference])
        self.assertEqual(public["available_models"][0]["variant"], "vision")
        self.assertTrue(public["available_models"][0]["is_real_photo"])
        self.assertEqual(public["items"][0]["reference_text"], RAW["items"][0]["reference_text"])
        self.assertNotIn("diagnostics", public["items"][0])
        self.assertNotIn("internal_model_detail", public["items"][0])
        self.assertNotIn("provider_label", public["ai_detection"])
        self.assertEqual(public["required_accessory_counts"], {"part-123": 2})
        self.assertNotIn("session_id", public)
        self.assertEqual(self.presentation.references.decode(reference), MODEL)
        self.assertEqual(self.presentation.path(public["annotated_url"], incoming=True), RAW["annotated_url"])
        # Compression remains outside the presentation adapter.
        self.assertEqual(response.headers["content-encoding"], "gzip")
        self.assertIn("no-store", response.headers["cache-control"])

    def test_role_checks_precede_every_side_effect(self):
        for role, status in [(None, 401), ("member", 403), ("delegated", 403)]:
            self.role(role)
            for path in ["/api/ai/config", "/api/agent/config", "/api/admin/model-profiles"]:
                for method in (self.client.get, self.client.post):
                    self.assertEqual(method(path).status_code, status)
            for path in ["/api/text-inspection/history/one/diagnostics", "/api/text-inspection/prepared-comparisons/one/media/audit-one"]:
                self.assertEqual(self.client.get(path).status_code, status)
        self.assertEqual(self.touched, [])
        self.role("admin")
        self.assertEqual(self.client.get("/api/admin/model-profiles").json()["model"], "gemini-3")

    def test_admin_details_and_public_wire_modes(self):
        self.role("admin")
        public = self.client.get("/api/status").json()
        self.assertEqual(public["active_model_id"], MODEL)
        self.assertEqual(public["ai_detection"]["model"], "doubao-vision-1")
        self.assertEqual(public["available_models"][0]["variant"], "vision")
        self.assertIn("diagnostics", public["items"][0])

    def test_json_modes_and_references_round_trip_without_changing_text(self):
        self.role()
        reference = self.presentation.references.encode(MODEL)
        result = self.client.post("/api/pipeline/tasks", json={"model_id": reference, "method": "vision_text", "note": "Gemini YOLO"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.touched[-1], {"model_id": MODEL, "method": "yolo_ocr", "note": "Gemini YOLO"})
        self.assertEqual(result.json()["model_id"], reference)
        self.assertEqual(result.json()["method"], "vision_text")
        before = list(self.touched)
        self.assertEqual(self.client.post("/api/pipeline/tasks", json={"model_id": reference[:-3]+"xxx"}).status_code, 422)
        self.assertEqual(before, self.touched)

    def test_file_bytes_and_plc_capabilities_remain_exact(self):
        self.role()
        reference = self.presentation.references.encode(MODEL)
        image = b"\x00\xffGemini YOLO\r\nref1_file_content"
        response = self.client.post("/api/analyze/camera", data={"model_id": reference, "plc_session_id": "lease-original"}, files={"file": ("Gemini.jpg", image, "image/jpeg")})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.touched[-1], (MODEL, "lease-original", image))
        public = response.json()
        self.assertEqual(public["model"]["id"], reference)
        self.assertEqual(public["plc_sync"]["session_id"], "lease-original")
        self.assertEqual(public["plc_sync"]["write_frame_hex"], "0244303303")

    def test_neutral_and_legacy_routes(self):
        self.role()
        self.assertEqual(self.client.get("/api/label-check/tasks/one").json()["id"], "one")
        self.assertEqual(self.client.get("/api/text-compare-codex/tasks/one").status_code, 403)
        self.role("admin")
        self.assertEqual(self.client.get("/api/text-compare-codex/tasks/one").status_code, 200)

    def test_static_assets_and_output_files(self):
        for role in (None, "member", "delegated"):
            self.role(role)
            for asset in ["admin-any.js", "app.js", "styles.css", "styles.css/", "index.html", "assets/admin-123.js", "assets/old.js.map", "assets/admin-123.js/", "assets/admin-123.js/%2e", "app.js/", "assets/old.js.map/%2e", "assets/ADMIN-123.JS/", "assets%5cadmin-123.js"]:
                self.assertEqual(self.client.get("/static/"+asset).status_code, 404)
                self.assertEqual(self.client.head("/static/"+asset).status_code, 404)
        self.role()
        self.assertEqual(self.client.get("/outputs/users/member/best.pt").status_code, 403)
        self.assertEqual(self.client.get("/outputs/users/member/model.zip").status_code, 403)
        self.assertEqual(self.client.get("/outputs/users/other/photo.jpg").status_code, 404)
        self.assertEqual(self.client.get("/outputs/users/member/photo.jpg").status_code, 200)
        self.role("admin")
        self.assertEqual(self.client.get("/static/assets/admin-123.js").status_code, 200)
        self.assertEqual(self.client.get("/static/assets/admin-123.js").headers["cache-control"], "private, no-store")
        self.assertEqual(self.client.get("/static/assets/admin-123.js/").headers["cache-control"], "private, no-store")

    def test_reference_key_is_stable_across_workers_and_restarts(self):
        directory = Path(self.directory.name)
        with ThreadPoolExecutor(max_workers=8) as pool:
            keys = list(pool.map(lambda _: runtime_key(directory), range(24)))
        self.assertEqual(len(set(keys)), 1)
        self.assertEqual((directory/"model-reference.key").stat().st_mode & 0o777, 0o600)
        first = self.presentation.references.encode(MODEL)
        second = References(lambda: runtime_key(directory)).encode(MODEL)
        self.assertEqual(first, second)

    def test_auth_feature_names_are_public(self):
        self.role()
        value = self.client.get("/api/auth/status").json()
        self.assertFalse(SENSITIVE.search(value["features"]["worker_settings"]))
        self.assertEqual(value["user"]["id"], "member")

    def test_split_event_stream_is_projected(self):
        self.role()
        response = self.client.get("/api/plc/capture-events")
        line = next(line for line in response.text.splitlines() if line.startswith("data:"))
        data = json.loads(line[5:])
        self.assertTrue(data["model_id"].startswith("ref1_"))
        self.assertNotIn("provider", data)
        self.assertEqual(data["session_id"], "lease-original")

    def test_model_urls_with_query_references_round_trip(self):
        url = "/api/models/warmup?model_id="+MODEL
        public = self.presentation.path(url)
        self.assertFalse(SENSITIVE.search(public))
        self.assertEqual(self.presentation.path(public, incoming=True), url)

    def test_customer_named_keys_and_values_are_preserved(self):
        value = {"name": "Gemini 客户任务", "accessory_labels": {"part-yolo": "Gemini 支架"}, "note": "ref1_customer-input"}
        self.assertEqual(self.presentation.outgoing(value), value)
        self.assertEqual(self.presentation.incoming(value), value)

    def test_business_overlay_survives_private_diagnostic_removal(self):
        evidence = {"elements": [{"element_id": "e1", "expected": "Gemini customer text", "standard_box": [0,0,1,1], "state": "matched", "evidence": [{"evidence_id":"o1","start":0,"end":3}]}], "observations": [{"id":"o1","text":"Gemini customer text","type":"text","box":[0,0,1,1]}]}
        value = {"id": "ins_one", "diagnostics": {"provider":"qwen_ocr", "normalized_response": {**evidence, "provider":"qwen", "raw": "private"}}}
        public = self.presentation.outgoing(value)
        self.assertNotIn("diagnostics", public)
        self.assertEqual(public["match_evidence"], evidence)

    def test_all_model_references_are_opaque_even_for_new_provider_names(self):
        value = {"available_models": [{"id":"unlisted-family-2030","variant":"unlisted-family","label":"Unlisted provider 2030","display_name":"Unlisted model family","description":"Unlisted model architecture","run_dir":"/private/model-artifacts"}], "active_model_id":"unlisted-family-2030", "loaded_model_ids":["unlisted-family-2030"]}
        public = self.presentation.outgoing(value)
        self.assertTrue(public["active_model_id"].startswith("ref1_"))
        self.assertEqual(public["available_models"][0]["id"], public["active_model_id"])
        self.assertEqual(public["loaded_model_ids"], [public["active_model_id"]])
        self.assertEqual(public["available_models"][0]["variant"], "vision")
        self.assertTrue(public["available_models"][0]["label"].startswith("视觉模型 · "))
        self.assertNotIn("Unlisted", json.dumps(public))
        self.assertNotIn("run_dir", public["available_models"][0])
        for source in ("agent_cursor_empty_surface", "agent_agnes_empty_surface"):
            public_source = self.presentation.outgoing({"source": source})["source"]
            self.assertNotIn("cursor", public_source.lower())
            self.assertNotIn("agnes", public_source.lower())

    def test_exact_source_delta_rejects_unknown_edits(self):
        from model_privacy_source_contract import checkpoint_bytes
        path = "local_inspection_service/auth/middleware.py"
        actual = (Path(__file__).resolve().parents[1]/path).read_bytes()
        parent = checkpoint_bytes(path, actual)
        self.assertNotEqual(parent, actual)
        with self.assertRaises(AssertionError):
            checkpoint_bytes(path, actual+b"\n# unreviewed mutation\n")

    def test_binary_urls_cursors_and_plc_tokens_are_not_text_replacements(self):
        value = {"annotated_image_data_url":"data:image/png;base64,abcdYOLOefgh", "next_cursor":"opaqueGeminiCursor", "cursor":"opaqueAgnesCursor", "plc_sync":{"session_id":"lease-YOLO", "binding_token":"tokenGemini", "dispatch_id":"dispatch-YOLO", "model_id":"internal-detector"}}
        public = self.presentation.outgoing(value)
        self.assertEqual(public["annotated_image_data_url"], value["annotated_image_data_url"])
        self.assertEqual(public["next_cursor"], value["next_cursor"])
        self.assertEqual(public["cursor"], value["cursor"])
        for key in ("session_id", "binding_token", "dispatch_id"):
            self.assertEqual(public["plc_sync"][key], value["plc_sync"][key])
        self.assertTrue(public["plc_sync"]["model_id"].startswith("ref1_"))

    def test_actual_status_policy_uses_role_instead_of_delegated_permissions(self):
        from local_inspection_service.auth.status import PublicStatusProjection
        from local_inspection_service.auth.status_ports import StatusPolicy, StatusSources, StatusProjectionCalls
        from local_inspection_service.auth.public_network import PublicNetworkPolicy
        from local_inspection_service.auth.public_network_ports import OriginPolicy, PublicEndpointPolicy, RuntimeDetailAccess
        admin = lambda user: bool(user and user.get("role") == "admin")
        graph = PublicStatusProjection(
            StatusPolicy(lambda:admin, lambda:lambda user, permission:True, lambda:{"id", "label", "is_ai_detection"}, lambda:lambda value:value),
            StatusSources(lambda:lambda:{"enabled":True,"configured":True,"status":"ready","provider_label":"Gemini","model":"gemini-3"}, lambda:lambda:{}),
            StatusProjectionCalls(lambda:graph.public_ai_detection_status, lambda:graph.public_image_generation_status, lambda:graph.public_status_model_for_user, lambda:graph.public_ai_detection_status_for_user),
        )
        member = {"role":"user", "permissions":["ai_config", "system_settings"]}
        self.assertNotIn("model", graph.public_ai_detection_status_for_user(member))
        self.assertNotIn("provider_label", graph.public_ai_detection_status_for_user(member))
        self.assertEqual(graph.public_ai_detection_status_for_user({"role":"admin"})["model"], "gemini-3")
        policy = PublicNetworkPolicy(
            OriginPolicy(lambda:lambda value:value, lambda:[], lambda:""),
            PublicEndpointPolicy(lambda:lambda value:False, lambda:lambda value:value),
            RuntimeDetailAccess(lambda:admin, lambda:lambda user, permission:True),
        )
        self.assertFalse(policy.include_internal_runtime_details(member))
        self.assertTrue(policy.include_internal_runtime_details({"role":"admin"}))

    def test_business_count_maps_rules_and_scores_retain_dynamic_keys(self):
        value = {"accessory_counts":{"part-A":2}, "required_counts":{"part-A":2}, "ai_counts":{"part-A":1}, "count_mismatches":{"part-A":{"expected":2,"actual":1}}, "task_rules":{"task-A":{"min_counts":{"part-A":2},"confidence_threshold":0.7}}, "metrics":{"mAP50":0.9,"provider":"gemini"}, "summary":{"digit_regions":4,"provider":"gemini"}}
        public = self.presentation.outgoing(value)
        for key in ("accessory_counts", "required_counts", "ai_counts", "count_mismatches", "task_rules"):
            self.assertEqual(public[key], value[key])
        self.assertEqual(public["metrics"], {"mAP50":0.9})
        self.assertEqual(public["summary"], {"digit_regions":4})

    def test_unknown_provider_server_errors_are_not_forwarded(self):
        self.role()
        response = self.client.get("/api/provider-failure")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["code"], "service_unavailable")
        self.assertNotIn("unlisted-private-engine", response.text)
        self.assertNotIn("internal endpoint", response.text)
        self.role("admin")
        self.assertIn("unlisted-private-engine", self.client.get("/api/provider-failure").text)

    def test_agent_history_preserves_user_input_and_neutralizes_platform_reply(self):
        conversation = {"conversation": [
            {"role": "user", "message": "请检查写着 Gemini YOLO 的客户标签"},
            {"role": "agent", "message": "已使用 YOLO 完成检测"},
        ]}
        public = self.presentation.outgoing(conversation)
        self.assertEqual(public["conversation"][0], conversation["conversation"][0])
        self.assertEqual(public["conversation"][1]["message"], "已使用 AI 检测 完成检测")
        self.assertEqual(self.presentation.outgoing(conversation, admin=True), conversation)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        import uvicorn
        dist = Path(__file__).resolve().parents[1]/"local_inspection_service/frontend/dist-production"
        client, _ = fixture(Presentation(References(lambda: b"s"*64)), dist)
        uvicorn.run(client.app, host="127.0.0.1", port=5196, log_level="warning")
    else:
        unittest.main(verbosity=2)
