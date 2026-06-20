#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

ROOT = Path(tempfile.mkdtemp(prefix="vantaline_phase3c_locate_label_"))
(ROOT / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
os.environ["LOCAL_INSPECTION_ROOT"] = str(ROOT)

from fastapi.testclient import TestClient  # noqa: E402

from local_inspection_service import server  # noqa: E402


def assert_status(response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise AssertionError(f"{label}: expected HTTP {expected}, got {response.status_code}: {response.text[:500]}")


def login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert_status(response, 200, f"{username} login")


def logout(client: TestClient, label: str) -> None:
    response = client.post("/api/auth/logout")
    assert_status(response, 200, label)


def create_user(client: TestClient, username: str, permissions: list[str]) -> dict[str, str]:
    response = client.post(
        "/api/auth/users",
        json={
            "username": username,
            "display_name": username,
            "password": f"{username}-password-1",
            "role": "user",
            "permissions": permissions,
        },
    )
    assert_status(response, 200, f"create {username}")
    return response.json()["user"]


def encoded_image() -> bytes:
    image = np.full((96, 180, 3), 250, dtype=np.uint8)
    cv2.rectangle(image, (12, 16), (168, 80), (30, 30, 30), 2, cv2.LINE_AA)
    cv2.putText(image, "QA LABEL", (24, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 20), 2, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise AssertionError("could not encode smoke image")
    return encoded.tobytes()


def assert_react_phase3c_routes() -> None:
    shell = (REPO_ROOT / "local_inspection_service" / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    label_page = (REPO_ROOT / "local_inspection_service" / "frontend" / "src" / "features" / "label" / "LabelSheetPage.tsx").read_text(encoding="utf-8")
    locate_page = (REPO_ROOT / "local_inspection_service" / "frontend" / "src" / "features" / "locate" / "LocateAnythingPage.tsx").read_text(encoding="utf-8")
    expected_shell = {
        "label route": 'path="/label-sheet"',
        "locate route": 'path="/locate-anything"',
        "label component": "LabelSheetPage",
        "locate component": "LocateAnythingPage",
        "label placeholder exclusion": '"labelSheet"',
        "locate placeholder exclusion": '"locateAnything"',
    }
    missing_shell = [label for label, snippet in expected_shell.items() if snippet not in shell]
    if missing_shell:
        raise AssertionError("React Phase 3C route wiring missing: " + ", ".join(missing_shell))
    expected_label = {
        "references query": "getLabelSheetReferences(auth)",
        "reference upload": "addLabelSheetReferences(form)",
        "match upload": "matchLabelSheet(form)",
        "camera capture": "navigator.mediaDevices?.getUserMedia",
    }
    missing_label = [label for label, snippet in expected_label.items() if snippet not in label_page]
    if missing_label:
        raise AssertionError("React Label Sheet contract missing: " + ", ".join(missing_label))
    expected_locate = {
        "accessories query": "getLocateAccessories(auth)",
        "status query": "getLocateStatus(\"\")",
        "inspect upload": "inspectLocateAnything(form)",
        "prompt upload": "locateAnythingPrompt(form)",
        "config permission": '"locate_config"',
    }
    missing_locate = [label for label, snippet in expected_locate.items() if snippet not in locate_page]
    if missing_locate:
        raise AssertionError("React LocateAnything contract missing: " + ", ".join(missing_locate))


def main() -> None:
    assert_react_phase3c_routes()
    if server.route_allowed_permissions("/api/label-sheets/references", "GET") != ("label_sheet",):
        raise AssertionError("label sheet references must require label_sheet permission")
    if server.route_allowed_permissions("/api/locateanything/inspect", "POST") != ("locate_anything",):
        raise AssertionError("LocateAnything inspect must require locate_anything permission")
    if server.route_allowed_permissions("/api/locateanything/config", "GET") != ("locate_config",):
        raise AssertionError("LocateAnything config must require locate_config permission")

    client = TestClient(server.app, base_url="https://testserver")
    response = client.post(
        "/api/auth/bootstrap",
        json={"username": "admin", "display_name": "Admin", "password": "admin-password-1"},
    )
    assert_status(response, 200, "bootstrap admin")
    create_user(client, "label_user", ["label_sheet"])
    create_user(client, "locate_user", ["locate_anything"])
    create_user(client, "locate_config_user", ["locate_config"])
    create_user(client, "zero_user", [])
    logout(client, "admin logout")

    image_bytes = encoded_image()

    login(client, "label_user", "label_user-password-1")
    response = client.get("/api/label-sheets/references")
    assert_status(response, 200, "label user lists references")
    response = client.post(
        "/api/label-sheets/references",
        data={"annotation": "QA label 标签"},
        files={"files": ("qa_label.png", image_bytes, "image/png")},
    )
    assert_status(response, 200, "label user adds reference")
    references = response.json()["references"]
    if not references:
        raise AssertionError(f"label reference upload did not return references: {response.json()}")
    response = client.post(
        "/api/label-sheets/match",
        files={"file": ("not-image.jpg", b"not an image", "image/jpeg")},
    )
    assert_status(response, 400, "label user reaches matcher decoder")
    response = client.get("/api/locateanything/status")
    assert_status(response, 403, "label user cannot read LocateAnything status")
    logout(client, "label user logout")

    login(client, "locate_user", "locate_user-password-1")
    response = client.get("/api/locateanything/status")
    assert_status(response, 200, "locate user reads status")
    response = client.get("/api/locateanything/accessories")
    assert_status(response, 200, "locate user reads locate source items")
    if not response.json()["items"]:
        raise AssertionError("LocateAnything source item list should not be empty")
    response = client.get("/api/locateanything/config")
    assert_status(response, 403, "locate user cannot read config endpoint")
    response = client.get("/api/locateanything/status", params={"endpoint_url": "http://127.0.0.1:9/locate"})
    assert_status(response, 403, "locate user cannot override endpoint on status")
    response = client.post(
        "/api/locateanything/inspect",
        data={"rules": "[]"},
        files={"file": ("smoke.png", image_bytes, "image/png")},
    )
    assert_status(response, 200, "locate user reaches inspect with no rules")
    payload = response.json()
    if payload["error"] != "No inspection items selected.":
        raise AssertionError(f"unexpected no-rule inspect payload: {payload}")
    response = client.post(
        "/api/locateanything/inspect",
        data={"rules": '[{"id":"phase3c","label":"Phase 3C part","expected_present":true,"expected_count":1}]'},
        files={"file": ("smoke.png", image_bytes, "image/png")},
    )
    assert_status(response, 200, "locate user reaches configured inspect path")
    payload = response.json()
    if payload["configured"] is not False or "not configured" not in payload["error"]:
        raise AssertionError(f"unexpected unconfigured inspect payload: {payload}")
    logout(client, "locate user logout")

    login(client, "locate_config_user", "locate_config_user-password-1")
    response = client.get("/api/locateanything/config")
    assert_status(response, 200, "locate_config user reads config")
    response = client.post(
        "/api/locateanything/config",
        json={"enabled": True, "endpoint_url": "http://127.0.0.1:9/locate", "generation_mode": "fast"},
    )
    assert_status(response, 200, "locate_config user saves config")
    if response.json()["endpoint_url"] != "http://127.0.0.1:9/locate":
        raise AssertionError("LocateAnything config save did not persist endpoint")
    logout(client, "locate_config user logout")

    login(client, "zero_user", "zero_user-password-1")
    response = client.get("/api/label-sheets/references")
    assert_status(response, 403, "zero user cannot list label references")
    response = client.get("/api/locateanything/status")
    assert_status(response, 403, "zero user cannot read locate status")

    print("smoke_phase3c_locate_label: ok")


if __name__ == "__main__":
    main()
