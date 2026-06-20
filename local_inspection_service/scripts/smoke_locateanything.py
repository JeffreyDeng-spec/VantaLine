#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = Path(tempfile.mkdtemp(prefix="vantaline_locateanything_smoke_"))
(TMP_ROOT / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
os.environ["LOCAL_INSPECTION_ROOT"] = str(TMP_ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service import server as server_module
from local_inspection_service.server import (
    app,
    data_analysis_locate_rules,
    dedupe_locateanything_rule_boxes,
    evaluate_locateanything_rule,
    locateanything_box_visible_label,
    locateanything_prompt_for_rule,
    locateanything_source_items,
    locateanything_visual_prompt_for_item,
    normalize_accessory_locateanything_profile,
    parse_locateanything_boxes,
    parse_locateanything_inspection_rules,
)


def encoded_smoke_image() -> bytes:
    image = np.full((80, 120, 3), 245, dtype=np.uint8)
    cv2.rectangle(image, (12, 18), (62, 64), (20, 120, 220), -1, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    assert ok
    return encoded.tobytes()


def seed_config() -> None:
    config = json.loads(json.dumps(server_module.DEFAULT_CONFIG))
    config["required_classes"] = [9101]
    config["min_counts"] = {"9101": 1}
    config["accessories"] = [
        {
            "id": "acc_glass_bottle",
            "class_id": 9101,
            "name": "玻璃瓶",
            "label": "玻璃瓶",
            "material_type": "object",
            "status": "active",
            "source_files": [],
            "normalized_assets": [],
            "ai_profile": {
                "accessory_id": "acc_glass_bottle",
                "name": "玻璃瓶",
                "english_name": "Glass Bottle",
                "material_type": "object",
                "description": "clear cylindrical glass bottle with visible cap or dispenser top",
                "visual_signature": "clear cylindrical glass bottle with orange dispenser top",
                "tags": ["bottle", "glass"],
                "distinguishing_text": [],
                "negative_cues": ["opaque bottle", "wrong accessory"],
                "expected_count": 1,
            },
        },
        {
            "id": "acc_pipe",
            "class_id": 9102,
            "name": "管子",
            "label": "管子",
            "material_type": "object",
            "status": "active",
            "source_files": [],
            "normalized_assets": [],
            "ai_profile": {
                "accessory_id": "acc_pipe",
                "name": "管子",
                "material_type": "object",
                "description": "long tube or pipe",
                "visual_signature": "long cylindrical tube",
                "tags": ["tube"],
                "distinguishing_text": [],
                "negative_cues": ["short block"],
                "expected_count": 1,
            },
        },
    ]
    server_module.save_config(config)


def run_mock_server(
    answer: str,
    *,
    health_payload: dict[str, object] | None = None,
    get_status_code: int = 200,
    endpoint_path: str = "/locate",
) -> tuple[HTTPServer, str]:
    class MockLocateHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/health" and health_payload is not None:
                body = json.dumps(health_payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if get_status_code >= 400:
                body = json.dumps({"ok": False}).encode("utf-8")
                self.send_response(get_status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = json.dumps({"ok": True}).encode("utf-8")
            self.send_response(get_status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length:
                self.rfile.read(length)
            payload = {"answer": answer}
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), MockLocateHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}{endpoint_path}"


def main() -> None:
    boxes = parse_locateanything_boxes("x <box> <100> <200> <500> <800> </box>", 120, 80)
    assert boxes == [
        {
            "index": 1,
            "x1": 12,
            "y1": 16,
            "x2": 60,
            "y2": 64,
            "normalized": {"x1": 100.0, "y1": 200.0, "x2": 500.0, "y2": 800.0},
        }
    ], boxes
    assert parse_locateanything_boxes("no box here", 120, 80) == []
    assert parse_locateanything_boxes("<box><100><100><1200><400></box>", 200, 100) == []
    ref_boxes = parse_locateanything_boxes("<ref>printed charger cable on package</ref><box><100><200><500><800></box>", 120, 80)
    assert ref_boxes[0]["ref_text"] == "printed charger cable on package", ref_boxes
    deduped = dedupe_locateanything_rule_boxes(
        {"expected_count": 1},
        [
            {"x1": 3, "y1": 34, "x2": 112, "y2": 51},
            {"x1": 3, "y1": 34, "x2": 112, "y2": 51},
            {"x1": 82, "y1": 42, "x2": 99, "y2": 47},
        ],
    )
    assert len(deduped) == 1 and deduped[0]["x1"] == 3, deduped

    client = TestClient(app)
    bootstrap = client.post("/api/auth/bootstrap", json={"username": "admin", "password": "password-12345"})
    assert bootstrap.status_code == 200, bootstrap.text
    seed_config()
    image_bytes = encoded_smoke_image()
    unavailable = client.post(
        "/api/locateanything/locate",
        data={
            "prompt": "Locate all the instances that match the following description: blue part.",
            "endpoint_url": "http://127.0.0.1:9/locate",
            "generation_mode": "fast",
            "max_new_tokens": "512",
            "max_side": "640",
        },
        files={"file": ("smoke.jpg", image_bytes, "image/jpeg")},
    )
    assert unavailable.status_code == 200, unavailable.text
    unavailable_payload = unavailable.json()
    assert unavailable_payload["ok"] is False, unavailable_payload
    assert unavailable_payload["configured"] is True, unavailable_payload
    assert unavailable_payload["boxes"] == [], unavailable_payload
    assert "unavailable" in unavailable_payload["error"].lower(), unavailable_payload

    server, endpoint_url = run_mock_server("Located target <box><100><200><500><800></box> and another <box> <600> <100> <900> <400> </box>.")
    try:
        success = client.post(
            "/api/locateanything/locate",
            data={
                "prompt": "Locate all the instances that match the following description: blue part.",
                "endpoint_url": endpoint_url,
                "generation_mode": "fast",
                "max_new_tokens": "512",
                "max_side": "256",
            },
            files={"file": ("smoke.jpg", image_bytes, "image/jpeg")},
        )
    finally:
        server.shutdown()
        server.server_close()

    assert success.status_code == 200, success.text
    payload = success.json()
    assert payload["ok"] is True, payload
    assert payload["source_image_size"] == {"width": 120, "height": 80}, payload
    assert max(payload["sent_image_size"].values()) <= 256, payload
    assert len(payload["boxes"]) == 2, payload
    assert payload["boxes"][0]["x1"] == 12 and payload["boxes"][0]["y1"] == 16, payload
    assert payload["overlay_url"].startswith("/outputs/locateanything/"), payload

    client.post(
        "/api/locateanything/config",
        json={"enabled": True, "endpoint_url": "http://example.test/locate", "generation_mode": "fast"},
    )
    original_runtime_script = server_module.LOCATEANYTHING_RUNTIME_SCRIPT_PATH
    original_health_status = server_module.locateanything_runtime_health_status
    original_service_status = server_module.locateanything_runtime_service_status
    try:
        server_module.locateanything_runtime_health_status = lambda *args, **kwargs: {"ok": False, "status": "unavailable", "message": "mock unavailable"}
        server_module.locateanything_runtime_service_status = lambda: {"service_active": False, "service_state": "inactive"}
        server_module.LOCATEANYTHING_RUNTIME_SCRIPT_PATH = ROOT / "local_inspection_service" / "scripts" / "missing_locateanything_runtime.sh"
        runtime_start = client.post("/api/locateanything/runtime/start")
    finally:
        server_module.LOCATEANYTHING_RUNTIME_SCRIPT_PATH = original_runtime_script
        server_module.locateanything_runtime_health_status = original_health_status
        server_module.locateanything_runtime_service_status = original_service_status
    assert runtime_start.status_code == 200, runtime_start.text
    runtime_payload = runtime_start.json()
    assert runtime_payload["ok"] is False, runtime_payload
    assert runtime_payload["status"] == "failed", runtime_payload
    assert "preflight" in runtime_payload, runtime_payload

    loading_server, loading_endpoint = run_mock_server("unused", health_payload={"ok": True, "loaded": False})
    try:
        loading_status = client.get("/api/locateanything/status", params={"endpoint_url": loading_endpoint})
    finally:
        loading_server.shutdown()
        loading_server.server_close()
    assert loading_status.status_code == 200, loading_status.text
    loading_payload = loading_status.json()
    assert loading_payload["ok"] is False, loading_payload
    assert loading_payload["status"] == "starting", loading_payload
    assert loading_payload["health"]["loaded"] is False, loading_payload

    ready_server, ready_endpoint = run_mock_server("unused", health_payload={"ok": True, "loaded": True})
    try:
        ready_status = client.get("/api/locateanything/status", params={"endpoint_url": ready_endpoint})
        assert ready_status.status_code == 200, ready_status.text
        ready_payload = ready_status.json()
        assert ready_payload["ok"] is True, ready_payload
        assert ready_payload["status"] == "ready", ready_payload
        assert ready_payload["health"]["loaded"] is True, ready_payload

        client.post(
            "/api/locateanything/config",
            json={"enabled": True, "endpoint_url": ready_endpoint, "generation_mode": "fast"},
        )
        original_runtime_script = server_module.LOCATEANYTHING_RUNTIME_SCRIPT_PATH
        original_health_status = server_module.locateanything_runtime_health_status
        try:
            server_module.locateanything_runtime_health_status = lambda *args, **kwargs: {
                "ok": True,
                "status": "ready",
                "status_code": 200,
                "latency_ms": 0,
                "health": {"ok": True, "loaded": True},
                "message": "本地模型已加载。",
            }
            server_module.LOCATEANYTHING_RUNTIME_SCRIPT_PATH = ROOT / "local_inspection_service" / "scripts" / "missing_locateanything_runtime.sh"
            idempotent_start = client.post("/api/locateanything/runtime/start")
        finally:
            server_module.LOCATEANYTHING_RUNTIME_SCRIPT_PATH = original_runtime_script
            server_module.locateanything_runtime_health_status = original_health_status
        assert idempotent_start.status_code == 200, idempotent_start.text
        idempotent_payload = idempotent_start.json()
        assert idempotent_payload["ok"] is True, idempotent_payload
        assert idempotent_payload["status"] == "ready", idempotent_payload
    finally:
        ready_server.shutdown()
        ready_server.server_close()

    method_server, method_endpoint = run_mock_server("unused", get_status_code=405, endpoint_path="/probe")
    try:
        method_status = client.get("/api/locateanything/status", params={"endpoint_url": method_endpoint})
    finally:
        method_server.shutdown()
        method_server.server_close()
    assert method_status.status_code == 200, method_status.text
    method_payload = method_status.json()
    assert method_payload["ok"] is False, method_payload
    assert method_payload["status"] == "reachable", method_payload
    assert method_payload["status_code"] == 405, method_payload

    sources = client.get("/api/locateanything/accessories")
    assert sources.status_code == 200, sources.text
    source_payload = sources.json()
    assert source_payload["items"], source_payload
    first_item = source_payload["items"][0]
    glass_source = next((item for item in source_payload["items"] if item.get("accessory_id") == "acc_glass_bottle"), None)
    assert glass_source is not None, source_payload
    assert glass_source["label"] == "Glass Bottle", glass_source
    assert glass_source["display_label"] == "Glass Bottle", glass_source
    assert glass_source["native_label"] == "玻璃瓶", glass_source
    assert "?" not in glass_source["display_label"], glass_source
    pipe_source = next((item for item in source_payload["items"] if item.get("accessory_id") == "acc_pipe"), None)
    assert pipe_source is not None, source_payload
    assert pipe_source["label"] == "Tube", pipe_source
    assert pipe_source["display_label"] == "Tube", pipe_source
    saved_config = server_module.load_config()
    saved_pipe = next(item for item in saved_config["accessories"] if item["id"] == "acc_pipe")
    assert saved_pipe["english_name"] == "Tube", saved_pipe
    assert saved_pipe["ai_profile"]["english_name"] == "Tube", saved_pipe
    assert saved_pipe["locateanything_profile"]["english_name"] == "Tube", saved_pipe
    assert saved_pipe["locateanything_profile"]["display_label"] == "Tube", saved_pipe
    charger_profile = normalize_accessory_locateanything_profile(
        {},
        {
            "id": "acc_charger",
            "name": "充电器",
            "material_type": "object",
            "ai_profile": {
                "accessory_id": "acc_charger",
                "name": "充电器",
                "material_type": "object",
                "visual_signature": "AI_ONLY_SIGNATURE",
                "description": "AI_ONLY_DESCRIPTION",
                "negative_cues": ["wrong accessory"],
            },
        },
    )
    for key in (
        "positive_visual_prompt",
        "target_scope",
        "material_type",
        "required_features",
        "optional_features",
        "reject_cues",
        "packaging_exclusions",
        "subpart_text_logo_exclusions",
        "count_strategy",
        "box_constraints",
    ):
        assert charger_profile.get(key), f"missing LocateAnything profile key: {key}"
    assert charger_profile["english_name"] == "Charger", charger_profile
    assert charger_profile["display_label"] == "Charger", charger_profile
    assert "printed cable graphics" in " ".join(charger_profile["packaging_exclusions"]), charger_profile

    custom_item = {
        "id": "acc_custom",
        "name": "custom charger",
        "material_type": "object",
        "ai_profile": {"visual_signature": "AI_ONLY_SIGNATURE"},
        "locateanything_profile": {
            **charger_profile,
            "accessory_id": "acc_custom",
            "name": "custom charger",
            "positive_visual_prompt": "LA_ONLY_SIGNATURE",
            "required_features": ["real charger brick"],
            "optional_features": [],
        },
    }
    custom_visual = locateanything_visual_prompt_for_item(custom_item)
    assert "LA_ONLY_SIGNATURE" in custom_visual, custom_visual
    assert "AI_ONLY_SIGNATURE" not in custom_visual, custom_visual

    fp_rule = parse_locateanything_inspection_rules(
        [
            {
                "id": "analysis:acc_charger",
                "label": "充电器",
                "material_type": "object",
                "task_type": "data_analysis_comparison",
                "visual_prompt": "real charger brick or cable",
                "locateanything_profile": charger_profile,
                "expected_present": False,
                "expected_count": 0,
            }
        ],
        [],
    )[0]
    fp_prompt = locateanything_prompt_for_rule(fp_rule)
    assert "Packaging and printed-image exclusions" in fp_prompt, fp_prompt
    assert "Subpart/text/logo exclusions" in fp_prompt, fp_prompt
    false_positive = evaluate_locateanything_rule(fp_rule, [{"x1": 4, "y1": 4, "x2": 80, "y2": 60}])
    assert false_positive["passed"] is False and false_positive["status"] == "comparison_extra", false_positive
    absent_match = evaluate_locateanything_rule(fp_rule, [])
    assert absent_match["passed"] is True and absent_match["status"] == "comparison_same_absent", absent_match

    object_fp_rule = parse_locateanything_inspection_rules(
        [
            {
                "id": "accessory:acc_charger",
                "label": "充电器",
                "material_type": "object",
                "task_type": "object_presence",
                "visual_prompt": "real charger brick or cable",
                "locateanything_profile": charger_profile,
                "expected_present": True,
                "expected_count": 1,
            }
        ],
        [],
    )[0]
    object_fp_answer = "<ref>printed charger cable on package</ref><box><100><200><500><800></box>"
    object_fp_boxes = parse_locateanything_boxes(object_fp_answer, 120, 80)
    object_false_positive = evaluate_locateanything_rule(object_fp_rule, object_fp_boxes, raw_answer=object_fp_answer)
    assert object_false_positive["passed"] is False and object_false_positive["status"] == "rejected_by_profile_cues", object_false_positive
    assert locateanything_box_visible_label({"index": 1, "label": "充电器", "english_name": "Charger"}) == "Charger"
    assert locateanything_box_visible_label({"index": 1, "display_label": "?", "english_name": "Charger"}) == "Charger"
    assert locateanything_box_visible_label({"index": 2}) == "LA 2"

    doc_rule = parse_locateanything_inspection_rules(
        [{"id": "doc", "label": "说明书", "material_type": "text", "expected_count": 1}],
        [],
    )[0]
    assert doc_rule["task_type"] == "text_document", doc_rule

    auth_token = server_module._request_user.set(bootstrap.json()["user"])
    try:
        analysis_rules = data_analysis_locate_rules(
            {
                "ai_detection_result": {
                    "model": {
                        "required_accessory_counts": {"acc_glass_bottle": 1},
                        "accessory_labels": {"acc_glass_bottle": "玻璃瓶"},
                    },
                    "rule": {"counts": {"acc_glass_bottle": 0}},
                    "detections": [{"accessory_id": "acc_glass_bottle", "label": "玻璃瓶", "present": False, "count": 0}],
                }
            }
        )
    finally:
        server_module._request_user.reset(auth_token)
    assert analysis_rules[0]["task_type"] == "data_analysis_comparison", analysis_rules
    assert analysis_rules[0]["display_label"] == "Glass Bottle", analysis_rules
    assert analysis_rules[0]["label"] == "玻璃瓶", analysis_rules
    assert analysis_rules[0]["expected_present"] is True and analysis_rules[0]["expected_count"] == 1, analysis_rules
    assert analysis_rules[0]["ai_detection_count"] == 0 and analysis_rules[0]["ai_detection_present"] is False, analysis_rules

    auth_token = server_module._request_user.set(bootstrap.json()["user"])
    try:
        source_items = locateanything_source_items()
    finally:
        server_module._request_user.reset(auth_token)
    rich_item = next((item for item in source_items if item.get("accessory_id") == "acc_glass_bottle"), None)
    assert rich_item is not None, "expected current glass bottle accessory"
    assert rich_item["label"] == "Glass Bottle", rich_item
    assert rich_item["display_label"] == "Glass Bottle", rich_item
    assert rich_item["native_label"] == "玻璃瓶", rich_item
    assert "transparent glass bottle" in rich_item["visual_prompt"].lower(), rich_item
    rich_rule = parse_locateanything_inspection_rules([{"id": rich_item["id"], "label": "玻璃瓶", "expected_count": 1}], source_items)[0]
    assert rich_rule["display_label"] == "Glass Bottle", rich_rule
    assert rich_rule["label"] == "玻璃瓶", rich_rule
    rich_prompt = locateanything_prompt_for_rule(rich_rule)
    assert "transparent glass bottle" in rich_prompt.lower(), rich_prompt
    assert rich_prompt != "Locate all the instances that match the following description: 玻璃瓶.", rich_prompt
    pipe_item = next((item for item in source_items if item.get("accessory_id") == "acc_pipe"), None)
    if pipe_item is not None:
        assert pipe_item["display_label"] == "Tube", pipe_item
        assert "tube" in pipe_item["visual_prompt"].lower() or "pipe" in pipe_item["visual_prompt"].lower(), pipe_item

    pass_server, pass_endpoint = run_mock_server(
        "<ref>玻璃瓶</ref><box><100><100><500><500></box>"
        "<ref>管子</ref><box><600><100><900><400></box>"
    )
    try:
        inspect_pass = client.post(
            "/api/locateanything/inspect",
            data={
                "endpoint_url": pass_endpoint,
                "rules": json.dumps(
                    [
                        {
                            "id": first_item["id"],
                            "label": first_item["label"],
                            "expected_present": True,
                            "expected_count": 1,
                        }
                    ]
                ),
            },
            files={"file": ("smoke.jpg", image_bytes, "image/jpeg")},
        )
    finally:
        pass_server.shutdown()
        pass_server.server_close()
    assert inspect_pass.status_code == 200, inspect_pass.text
    pass_payload = inspect_pass.json()
    assert pass_payload["overall_pass"] is True, pass_payload
    assert pass_payload["items"][0]["label"] == "Glass Bottle", pass_payload
    assert pass_payload["items"][0]["status"] == "found", pass_payload
    assert pass_payload["items"][0]["box_count"] == 1, pass_payload
    pass_boxes = pass_payload["items"][0]["boxes"]
    assert pass_boxes[0]["label"] == "Glass Bottle", pass_payload
    assert pass_boxes[0]["display_label"] == "Glass Bottle", pass_payload
    assert pass_boxes[0]["english_name"] == "Glass Bottle", pass_payload
    assert pass_boxes[0]["native_label"] == "玻璃瓶", pass_payload
    serialized_pass = json.dumps(pass_payload, ensure_ascii=False)
    assert "?" not in serialized_pass, pass_payload
    assert pass_payload["items"][0]["raw_box_count"] == 2, pass_payload
    assert pass_payload["items"][0]["filtered_out_box_count"] == 1, pass_payload
    assert pass_payload["diagnostics"][0]["raw_box_count"] == 2, pass_payload
    assert pass_payload["diagnostics"][0]["filtered_out_box_count"] == 1, pass_payload
    assert len(pass_payload["diagnostics"][0]["filtered_out_boxes"]) == 1, pass_payload
    assert pass_payload["items"][0]["prompt"], pass_payload
    assert pass_payload["diagnostics"][0]["prompt"] == pass_payload["items"][0]["prompt"], pass_payload
    assert "raw_answer" not in pass_payload["diagnostics"][0], pass_payload
    assert pass_payload["diagnostics"][0]["raw_answer_snippet"], pass_payload
    overlay_path = server_module.OUTPUT_DIR / pass_payload["overlay_url"].removeprefix("/outputs/")
    assert overlay_path.exists(), pass_payload

    missing_server, missing_endpoint = run_mock_server("no matching object")
    try:
        inspect_fail = client.post(
            "/api/locateanything/inspect",
            data={
                "endpoint_url": missing_endpoint,
                "rules": json.dumps(
                    [
                        {
                            "id": first_item["id"],
                            "label": first_item["label"],
                            "expected_present": True,
                            "expected_count": 1,
                        }
                    ]
                ),
            },
            files={"file": ("smoke.jpg", image_bytes, "image/jpeg")},
        )
    finally:
        missing_server.shutdown()
        missing_server.server_close()
    assert inspect_fail.status_code == 200, inspect_fail.text
    fail_payload = inspect_fail.json()
    assert fail_payload["overall_pass"] is False, fail_payload
    assert fail_payload["items"][0]["status"] == "missing", fail_payload
    assert fail_payload["items"][0]["box_count"] == 0, fail_payload

    print("locateanything smoke passed")


if __name__ == "__main__":
    main()
