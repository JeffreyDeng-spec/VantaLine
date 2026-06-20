#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

ROOT = Path(tempfile.mkdtemp(prefix="vantaline_phase3d_pipeline_"))
(ROOT / "local_inspection_service" / "static").mkdir(parents=True, exist_ok=True)
os.environ["LOCAL_INSPECTION_ROOT"] = str(ROOT)

from fastapi.testclient import TestClient  # noqa: E402

from local_inspection_service import server  # noqa: E402
from local_inspection_service.scripts import windows_worker_gateway  # noqa: E402


def seed_anchor_pose_guides() -> None:
    server.POSE_ANCHOR_DIR.mkdir(parents=True, exist_ok=True)
    image = server.np.full((32, 32, 3), 245, dtype=server.np.uint8)
    server.cv2.rectangle(image, (6, 12), (26, 20), (80, 80, 80), -1, server.cv2.LINE_AA)
    for path in [*server.POSE_ANCHOR_IMAGES.values(), server.POSE_ANCHOR_DIR / "circle_endface_9target_guide.png"]:
        server.cv2.imwrite(str(path), image)


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


def seed_accessory(accessory_id: str, name: str, owner: dict[str, str]) -> None:
    config = server.load_config()
    config["accessories"] = [
        item for item in config.get("accessories", []) if str(item.get("id") or server.accessory_uid(item)) != accessory_id
    ]
    config["accessories"].append(
        {
            "id": accessory_id,
            "class_id": 8300 + len(config["accessories"]),
            "name": name,
            "label": name,
            "material_type": "object",
            "material_alpha_policy": "opaque",
            "object_alpha_policy_label": "不透明",
            "training_role": "detect_and_classify",
            "detection_route": "yolo",
            "physical_size": server.physical_size_payload("object"),
            "status": "active",
            "source_files": [],
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
            "owner_user_id": owner["id"],
            "owner_username": owner["username"],
        }
    )
    server.save_config(config)


def seed_training_dataset(dataset_id: str, owner: dict[str, str], accessory_id: str) -> dict[str, str]:
    dataset_dir = server.output_write_dir_for_owner("training_datasets", owner["id"]) / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=True)
    image_path = dataset_dir / "sample_0001.png"
    label_path = dataset_dir / "sample_0001.txt"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    label_path.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    server.write_dataset_yaml(dataset_dir / "dataset.yaml", dataset_dir, [accessory_id])
    manifest = {
        "display_name": dataset_id,
        "sample_count": 1,
        "selected_accessory_ids": [accessory_id],
        "background_set_id": "",
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
        "samples": [
            {
                "image": str(image_path),
                "label": str(label_path),
                "owner_user_id": owner["id"],
                "owner_username": owner["username"],
            }
        ],
    }
    (dataset_dir / "manifest.json").write_text(
        server.json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "id": dataset_id,
        "dataset_dir": str(dataset_dir),
        "dataset_yaml": str(dataset_dir / "dataset.yaml"),
        "manifest_path": str(dataset_dir / "manifest.json"),
    }


def assert_react_pipeline_route() -> None:
    shell = (REPO_ROOT / "local_inspection_service" / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    nav = (REPO_ROOT / "local_inspection_service" / "frontend" / "src" / "app" / "navigation.tsx").read_text(encoding="utf-8")
    page = (REPO_ROOT / "local_inspection_service" / "frontend" / "src" / "features" / "pipeline" / "TrainingPipelinePage.tsx").read_text(encoding="utf-8")
    styles = (REPO_ROOT / "local_inspection_service" / "frontend" / "src" / "styles" / "global.css").read_text(encoding="utf-8")
    server = (REPO_ROOT / "local_inspection_service" / "server.py").read_text(encoding="utf-8")
    expected_shell = {
        "pipeline route": 'path="/pipeline"',
        "pipeline component": "TrainingPipelinePage",
        "pipeline placeholder exclusion": '"pipeline"',
    }
    missing_shell = [label for label, snippet in expected_shell.items() if snippet not in shell]
    if missing_shell:
        raise AssertionError("React pipeline route wiring missing: " + ", ".join(missing_shell))
    if "系统概况" in nav or "StatusOverview" in shell:
        raise AssertionError("React preview still exposes the system overview nav/page")
    expected_page = {
        "dnd context": "DndContext",
        "droppable usage": "useDroppable",
        "add accessory API": "addPipelineAccessory",
        "task patch API": "updatePipelineTask",
        "advance API": "advancePipelineTask",
        "full card drag guard": "stopCardDragFromInteractive",
        "root role guard exemption": "blocker !== event.currentTarget",
        "card drag listeners": "拖动卡片",
        "params modal": "ParamsModal",
        "detail counts": "pipeline-quantity-control",
        "agent mcp panel": "AgentMcpPanel",
        "react-only pose planner": "inferAgentPosePlan",
        "cube pose fixture": "face_a_down",
        "bottle pose fixture": "upright_base_down",
        "thin object pose fixture": "face_up",
        "one accessory image contract": "one_accessory_per_image",
        "pose image tool contract": "generate_accessory_pose_image",
        "sample tool contract": "generate_training_samples",
        "training tool contract": "start_model_training",
        "feedback API call": "sendPipelineAgentFeedback",
        "chat API call": "sendPipelineAgentChat",
        "persisted orchestration read": "task.agent_mcp",
        "persisted conversation read": "agentMcp.conversation",
        "agent action labels": "AGENT_ACTION_LABELS",
        "needs user badge": "pipeline-needs-user",
        "thinking loader": "pipeline-agent-thinking",
        "thinking copy": "thinking",
        "spinner icon": "Loader2",
        "running controls disabled": "controlsDisabled",
        "image error fallback component": "PipelineThumb",
        "image error onError handler": "onError",
        "pregenerated params reuse": "recommended_params",
    }
    missing_page = [label for label, snippet in expected_page.items() if snippet not in page]
    if missing_page:
        raise AssertionError("React pipeline page contract missing: " + ", ".join(missing_page))
    expected_styles = {
        "agent mcp shell": ".pipeline-agent-mcp",
        "agent stage grid": ".pipeline-agent-stage-grid",
        "tool contracts": ".pipeline-tool-contracts",
        "pose plans": ".pipeline-pose-plan-list",
        "thinking stage": ".pipeline-agent-stage.thinking",
        "thinking badge": ".pipeline-agent-thinking",
    }
    missing_styles = [label for label, snippet in expected_styles.items() if snippet not in styles]
    if missing_styles:
        raise AssertionError("React Agent/MCP styles missing: " + ", ".join(missing_styles))
    expected_server = {
        "agent mcp version": "AGENT_MCP_ORCHESTRATION_VERSION",
        "gemini image model": "AGENT_MCP_GEMINI_IMAGE_DEFAULT_MODEL",
        "gemini image generation": "gemini_native_image_generation",
        "gemini image provider method": "def generate_image",
        "synthid metadata": "synthid_watermark_expected",
        "feedback request model": "PipelineAgentFeedbackRequest",
        "feedback endpoint": "/api/pipeline/tasks/{task_id}/agent-feedback",
        "chat request model": "PipelineAgentChatRequest",
        "chat endpoint": "/api/pipeline/tasks/{task_id}/chat",
        "decision brain": "def agent_pipeline_decide",
        "decision normalizer": "def normalize_agent_pipeline_decision",
        "rule fallback decision": "def agent_pipeline_rule_decision",
        "agent turn committer": "def commit_pipeline_agent_turn",
        "conversation persistence": "def agent_mcp_append_conversation",
        "auto agent scheduler": "def schedule_pipeline_auto_agent",
        "auto step guardrail": "AGENT_MCP_AUTO_MAX_STEPS",
        "pose planner persistence": "build_agent_mcp_pose_plan",
        "pose tool calls": "ensure_agent_mcp_pose_tool_calls",
        "pose asset materialization": "materialize_agent_mcp_pose_assets",
        "skip validation": "agent_mcp_missing_existing_asset_names",
        "stale production prefix": '"/opt/vantalane/app"',
        "missing tool state": "missing_configuration",
        "sample tool call": "log_agent_mcp_sample_tool_call",
        "training tool call": "log_agent_mcp_training_tool_call",
        "shared output visibility": "Shared/legacy outputs written to the OUTPUT_DIR root",
        "trained model linker": "def link_pipeline_trained_model",
        "recommendation pregen": "def _run_pipeline_recommendation_pregen",
        "recommendation consume": "def consume_pipeline_recommendation",
        "recommendation scheduler": "def schedule_pipeline_recommendation_pregen",
        "worker training watcher": "def _worker_training_watch_once",
        "worker watcher startup": "start_worker_training_watcher",
        "worker request retry": "def windows_worker_request_with_retry",
    }
    missing_server = [label for label, snippet in expected_server.items() if snippet not in server]
    if missing_server:
        raise AssertionError("Backend Agent/MCP preview skeleton missing: " + ", ".join(missing_server))
    forbidden = ["<pre", "JSON.stringify("]
    exposed = [snippet for snippet in forbidden if snippet in page]
    if exposed:
        raise AssertionError("React pipeline page exposes raw/debug payload affordances: " + ", ".join(exposed))


def assert_worker_gateway_rewrites_imported_dataset_yaml_to_windows_path() -> None:
    dataset_dir = ROOT / "worker_gateway_imported_dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = dataset_dir / "dataset.yaml"
    yaml_path.write_text(
        "path: F:/stale/source/path\ntrain: images/train\nval: images/val\nnames:\n  0: acc_pipe\n",
        encoding="utf-8",
    )
    original = windows_worker_gateway.path_for_windows_training
    try:
        windows_worker_gateway.path_for_windows_training = lambda path: "F:/CodexWorkspace/imported_dataset"
        windows_worker_gateway.rewrite_dataset_yaml_path(dataset_dir)
    finally:
        windows_worker_gateway.path_for_windows_training = original
    first_line = yaml_path.read_text(encoding="utf-8").splitlines()[0]
    if first_line != "path: F:/CodexWorkspace/imported_dataset":
        raise AssertionError(f"Worker dataset.yaml path was not rewritten to Windows path: {first_line}")
    translated = windows_worker_gateway.path_from_wsl_mount(
        "/mnt/f/CodexWorkspace/assembly_line_optimize/local_inspection_service/data/outputs/training_runs/run/weights/best.pt"
    )
    if translated != "F:/CodexWorkspace/assembly_line_optimize/local_inspection_service/data/outputs/training_runs/run/weights/best.pt":
        raise AssertionError(f"Worker artifact path was not translated from WSL mount path: {translated}")


def assert_worker_gateway_training_preflight_blocks_when_local_backend_down() -> None:
    original_status = windows_worker_gateway.local_vantaline_status
    try:
        windows_worker_gateway.local_vantaline_status = lambda: {
            "ok": False,
            "status_code": 0,
            "error": "connection refused",
        }
        worker_client = TestClient(windows_worker_gateway.app)
        response = worker_client.post(
            "/training/jobs",
            json={"selected_accessory_ids": ["acc_pipe"], "dataset_id": "samples_smoke", "epochs": 1},
        )
        assert_status(response, 503, "worker training preflight blocks missing local backend")
        if "Local VantaLine backend is unavailable" not in response.text:
            raise AssertionError(f"worker training preflight returned unclear error: {response.text}")
        response = worker_client.post(
            "/training/jobs/import",
            data={
                "metadata": server.json.dumps(
                    {
                        "job_id": "worker_preflight_smoke",
                        "selected_accessory_ids": ["acc_pipe"],
                        "dataset_archive": {"sha256": server.hashlib.sha256(b"zip").hexdigest()},
                    }
                )
            },
            files={"dataset_archive": ("dataset.zip", b"zip", "application/zip")},
        )
        assert_status(response, 503, "worker import preflight blocks missing local backend")
    finally:
        windows_worker_gateway.local_vantaline_status = original_status


def assert_worker_gateway_bootstraps_local_backend_session() -> None:
    class FakeResponse:
        def __init__(self, status_code: int, body: dict[str, object]):
            self.status_code = status_code
            self._body = body
            self.text = server.json.dumps(body)

        def json(self) -> dict[str, object]:
            return self._body

    class FakeSession:
        bootstrapped = False
        authenticated = False
        status_calls = 0
        training_calls = 0

        def get(self, url: str, **_: object) -> FakeResponse:
            if url.endswith("/api/auth/status"):
                return FakeResponse(200, {"authenticated": self.authenticated, "setup_required": not self.bootstrapped})
            raise AssertionError(f"unexpected GET {url}")

        def post(self, url: str, json: dict[str, object], **_: object) -> FakeResponse:
            if url.endswith("/api/auth/bootstrap"):
                if json.get("username") != windows_worker_gateway.LOCAL_VANTALINE_DEFAULT_USERNAME:
                    raise AssertionError(f"unexpected bootstrap payload: {json}")
                self.bootstrapped = True
                self.authenticated = True
                return FakeResponse(200, {"status": "created"})
            if url.endswith("/api/auth/login"):
                self.authenticated = True
                return FakeResponse(200, {"status": "authenticated"})
            raise AssertionError(f"unexpected POST {url}")

        def request(self, method: str, url: str, json: dict[str, object] | None = None, **_: object) -> FakeResponse:
            if not self.authenticated:
                return FakeResponse(401, {"detail": "Authentication required"})
            if method == "GET" and url.endswith("/api/status"):
                self.status_calls += 1
                return FakeResponse(200, {"service": "running"})
            if method == "POST" and url.endswith("/api/training/start"):
                self.training_calls += 1
                return FakeResponse(200, {"job_id": "train_fake", "status": "queued", "payload": json or {}})
            raise AssertionError(f"unexpected request {method} {url}")

    original_session = windows_worker_gateway.LOCAL_VANTALINE_SESSION
    original_token = windows_worker_gateway.WORKER_TOKEN
    original_password_env = os.environ.get(windows_worker_gateway.LOCAL_VANTALINE_PASSWORD_ENV)
    fake = FakeSession()
    try:
        windows_worker_gateway.LOCAL_VANTALINE_SESSION = fake
        windows_worker_gateway.WORKER_TOKEN = "worker-token-for-smoke"
        os.environ.pop(windows_worker_gateway.LOCAL_VANTALINE_PASSWORD_ENV, None)
        status = windows_worker_gateway.local_vantaline_status()
        if status.get("status_code") != 200 or not fake.bootstrapped or fake.status_calls != 1:
            raise AssertionError(f"gateway did not bootstrap and authenticate local backend status: {status}")
        body = windows_worker_gateway.proxy_json(
            "POST",
            f"{windows_worker_gateway.LOCAL_VANTALINE_BASE_URL}/api/training/start",
            json_body={"dataset_id": "samples_smoke"},
        )
        if body.get("job_id") != "train_fake" or fake.training_calls != 1:
            raise AssertionError(f"gateway did not proxy training through authenticated local session: {body}")
    finally:
        windows_worker_gateway.LOCAL_VANTALINE_SESSION = original_session
        windows_worker_gateway.WORKER_TOKEN = original_token
        if original_password_env is None:
            os.environ.pop(windows_worker_gateway.LOCAL_VANTALINE_PASSWORD_ENV, None)
        else:
            os.environ[windows_worker_gateway.LOCAL_VANTALINE_PASSWORD_ENV] = original_password_env


def assert_gemini_auto_local_proxy_settings() -> None:
    original_local_proxy_available = server.local_proxy_available
    original_auto_proxy_env = os.environ.get(server.AI_AUTO_LOCAL_PROXY_ENV)
    original_proxy_env = {name: os.environ.get(name) for name in server.AI_PROXY_ENV_NAMES}
    try:
        server.local_proxy_available = lambda proxy_url=server.AI_LOCAL_PROXY_URL: True
        os.environ.pop(server.AI_AUTO_LOCAL_PROXY_ENV, None)
        for name in server.AI_PROXY_ENV_NAMES:
            os.environ.pop(name, None)
        server.save_ai_local_config(
            {
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "timeout_seconds": 10.0,
                "api_keys": [{"id": "key_smoke", "label": "smoke", "key": "smoke-gemini-key"}],
                "active_key_id": "key_smoke",
                "proxy_url": "",
                "auto_local_proxy": True,
            }
        )
        status = server.ai_detection_settings()
    finally:
        server.local_proxy_available = original_local_proxy_available
        if original_auto_proxy_env is None:
            os.environ.pop(server.AI_AUTO_LOCAL_PROXY_ENV, None)
        else:
            os.environ[server.AI_AUTO_LOCAL_PROXY_ENV] = original_auto_proxy_env
        for name, value in original_proxy_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    if not status.get("configured") or not status.get("proxy_configured"):
        raise AssertionError(f"Gemini auto-local proxy was not configured in diagnostics: {status}")
    if status.get("proxy_source_name") != "auto_local_mihomo" or status.get("proxy_auto_local") is not True:
        raise AssertionError(f"Gemini auto-local proxy source was not reported: {status}")


def smoke_clean_sprite(path: Path, metadata: dict[str, object] | None = None) -> dict[str, object]:
    image = server.np.full((96, 128, 3), 245, dtype=server.np.uint8)
    mask = server.np.zeros((96, 128), dtype=server.np.uint8)
    server.cv2.rectangle(image, (22, 24), (106, 72), (45, 80, 160), -1, server.cv2.LINE_AA)
    server.cv2.rectangle(mask, (22, 24), (106, 72), 255, -1, server.cv2.LINE_AA)
    payload = {
        "task_id": "smoke_clean_sprite",
        "source_pose_collection_job_id": "smoke_clean_sprite",
        "pose_family": "lying",
        "source_pose_family": "lying",
        "pose_position": "center",
        "source_position": "center",
        "source_image_size_px": [128, 96],
        "source_image_width": 128,
        "source_image_height": 96,
        "source_region_bbox_xyxy": [0, 0, 128, 96],
        "source_object_bbox_xyxy": [22, 24, 106, 72],
        "source_object_center_xy": [64, 48],
        "source_object_size_px": [84, 48],
        "physical_size_mm": server.physical_size_payload("object"),
        "material_alpha_policy": server.object_alpha_material_policy({}),
    }
    if metadata:
        payload.update(metadata)
    asset = server.write_clean_sprite(path, image, mask, payload)
    if not asset:
        raise AssertionError("failed to create smoke clean sprite")
    asset["method"] = str(payload.get("method") or "smoke_clean_sprite")
    return asset


def write_agent_mcp_reference(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = server.np.zeros((96, 128, 4), dtype=server.np.uint8)
    image[:, :, :3] = 248
    server.cv2.ellipse(image, (64, 48), (38, 20), 0, 0, 360, (35, 35, 35, 255), -1, server.cv2.LINE_AA)
    server.cv2.circle(image, (45, 48), 8, (235, 235, 235, 255), -1, server.cv2.LINE_AA)
    server.cv2.circle(image, (83, 48), 8, (235, 235, 235, 255), -1, server.cv2.LINE_AA)
    if not server.cv2.imwrite(str(path), image):
        raise AssertionError(f"failed to write Agent/MCP reference image: {path}")


def assert_agent_mcp_pose_assets_satisfy_normalized_gate(owner: dict[str, str]) -> None:
    config = server.load_config()
    physical_size = server.physical_size_payload("object")

    stale_accessory_id = "acc_stale_prod_path"
    stale_sprite_path = server.NORMALIZED_DIR / stale_accessory_id / "clean_sprites" / "sprite_01.png"
    stale_asset = smoke_clean_sprite(stale_sprite_path, {"task_id": "stale_prod_path"})
    stale_asset["path"] = str(stale_sprite_path).replace(str(ROOT), "/opt/vantalane/app")
    stale_item = {
        "id": stale_accessory_id,
        "class_id": 8350,
        "name": "Stale prod path accessory",
        "label": "Stale prod path accessory",
        "material_type": "object",
        "material_alpha_policy": server.object_alpha_material_policy({}),
        "physical_size": physical_size,
        "status": "active",
        "source_files": [],
        "normalized_assets": [stale_asset],
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
    }

    agent_accessory_id = "acc_agent_mcp_ref"
    agent_ref_path = server.OUTPUT_DIR / "agent_mcp_pose_images" / "pipe_smoke_agent_ref" / "acc_agent_mcp_ref_pose.png"
    write_agent_mcp_reference(agent_ref_path)
    agent_item = {
        "id": agent_accessory_id,
        "class_id": 8351,
        "name": "Agent MCP reference accessory",
        "label": "Agent MCP reference accessory",
        "material_type": "object",
        "material_alpha_policy": server.object_alpha_material_policy({}),
        "physical_size": physical_size,
        "status": "active",
        "source_files": [],
        "normalized_assets": [],
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
    }

    config["accessories"] = [
        item
        for item in config.get("accessories", [])
        if server.accessory_uid(item) not in {stale_accessory_id, agent_accessory_id}
    ] + [stale_item, agent_item]

    task = {
        "id": "pipe_smoke_agent_ref",
        "name": "Agent MCP reference smoke",
        "accessory_ids": [agent_accessory_id],
        "agent_mcp": {
            "tool_calls": [
                {
                    "call_id": "call_smoke_agent_ref",
                    "tool": server.AGENT_MCP_TOOL_POSE_IMAGE,
                    "status": "completed",
                    "accessory_id": agent_accessory_id,
                    "pose_id": "pose_smoke",
                    "provider": "gemini_native_image_generation",
                    "model": server.AGENT_MCP_GEMINI_IMAGE_DEFAULT_MODEL,
                    "output_path": str(agent_ref_path),
                    "sha256": server.file_sha256(agent_ref_path),
                }
            ]
        },
    }
    if not server.materialize_agent_mcp_pose_assets(task, config):
        raise AssertionError("Agent/MCP completed pose image was not materialized into accessory assets")
    if not server.agent_mcp_pose_reference_assets(agent_item):
        raise AssertionError("Agent/MCP pose reference asset was not discoverable")
    server.ensure_training_normalized_assets_for_selection(config, [stale_accessory_id, agent_accessory_id])

    stale_path_after = str((stale_item.get("normalized_assets") or [{}])[0].get("path") or "")
    if stale_path_after.startswith("/opt/vantalane/app") or not Path(stale_path_after).exists():
        raise AssertionError(f"stale production path was not rebased to an existing sprite: {stale_path_after}")
    agent_sprites = server.clean_sprite_assets(agent_item)
    if not agent_sprites or not Path(str(agent_sprites[0].get("path") or "")).exists():
        raise AssertionError(f"Agent/MCP pose reference did not produce a clean sprite: {agent_item}")
    if server.pending_pose_collection_jobs(agent_item):
        raise AssertionError(f"Agent/MCP pose reference should not queue legacy pose collection jobs: {agent_item.get('codex_image_jobs')}")


def assert_agent_pipeline_decision_helpers() -> None:
    advance_decision = server.agent_pipeline_rule_decision({"stage": "samples", "status": "completed"}, None, "auto")
    if advance_decision["action"] != "advance" or advance_decision["source"] != "rules":
        raise AssertionError(f"rule fallback should advance a completed sample stage: {advance_decision}")
    failure_decision = server.agent_pipeline_rule_decision({"stage": "draft", "status": "failed"}, None, "auto")
    if failure_decision["action"] != "pause_and_ask" or not failure_decision["needs_user"]:
        raise AssertionError(f"rule fallback should escalate failures to the user: {failure_decision}")
    cancel_decision = server.agent_pipeline_rule_decision({"stage": "draft", "status": "ready"}, "请取消这个任务", "chat")
    if cancel_decision["action"] != "cancel":
        raise AssertionError(f"rule fallback did not parse cancel intent: {cancel_decision}")
    clamped = server.normalize_agent_pipeline_decision(
        {"action": "set_params", "params": {"sample_count": 999999, "epochs": 0, "image_size": 99}}
    )
    if clamped["params"].get("sample_count") != 20000 or clamped["params"].get("epochs") != 1 or clamped["params"].get("image_size") != 320:
        raise AssertionError(f"decision params were not clamped to constraints: {clamped}")
    unknown = server.normalize_agent_pipeline_decision({"action": "drop_database"})
    if unknown["action"] != "reply":
        raise AssertionError(f"unknown actions must fall back to reply: {unknown}")
    changed, auto_ids = server.sync_and_auto_advance_pipeline([])
    if changed or auto_ids:
        raise AssertionError(f"empty pipeline sync should be a no-op: {changed}, {auto_ids}")
    if server.pipeline_task_needs_auto_agent({"auto_advance": True, "detection_method": "ai", "stage": "draft", "status": "completed"}):
        raise AssertionError("AI tasks must not trigger the training auto agent")
    if not server.pipeline_task_needs_auto_agent(
        {"auto_advance": True, "detection_method": "yolo", "stage": "samples", "status": "completed"}
    ):
        raise AssertionError("completed YOLO sample stage with auto-advance should need the auto agent")


def assert_output_path_visibility_rules() -> None:
    admin = {"id": "admin_user", "role": "admin"}
    member = {"id": "member_user", "role": "user", "permissions": ["training_pipeline"]}
    other = {"id": "other_user", "role": "user", "permissions": ["training_pipeline"]}
    # Shared/legacy outputs written to the OUTPUT_DIR root must be loadable by any
    # authenticated user so pose/sample images of legacy-owned tasks still render.
    if not server.output_path_visible_to_user("/outputs/agent_mcp_pose_images/pipe/a__b.png", member):
        raise AssertionError("shared root outputs should be visible to authenticated users")
    # Per-user subtrees stay private to their owner.
    if not server.output_path_visible_to_user("/outputs/users/member_user/training_datasets/d/sample.png", member):
        raise AssertionError("user should access their own per-user outputs")
    if server.output_path_visible_to_user("/outputs/users/other_user/training_datasets/d/sample.png", member):
        raise AssertionError("user must not access another user's per-user outputs")
    if not server.output_path_visible_to_user("/outputs/users/other_user/training_datasets/d/sample.png", admin):
        raise AssertionError("admin should access any output")
    # Path traversal outside OUTPUT_DIR must be denied for non-admins.
    if server.output_path_visible_to_user("/outputs/../../etc/passwd", other):
        raise AssertionError("path traversal outside OUTPUT_DIR must be denied")


def assert_pipeline_recommendation_pregen_helpers() -> None:
    draft_task = {
        "id": "rec_draft",
        "detection_method": "yolo",
        "stage": "draft",
        "status": "ready",
        "accessory_ids": ["acc_pipe"],
        "params": {"train_mode": "yolo"},
    }
    if server.pipeline_next_recommendation_stage(draft_task) != "samples":
        raise AssertionError("draft training task should pre-generate the samples recommendation")
    samples_done = {
        "id": "rec_samples",
        "detection_method": "yolo",
        "stage": "samples",
        "status": "completed",
        "accessory_ids": ["acc_pipe"],
        "params": {"train_mode": "yolo", "sample_count": 200},
    }
    if server.pipeline_next_recommendation_stage(samples_done) != "training":
        raise AssertionError("completed samples stage should pre-generate the training recommendation")
    ai_task = {"id": "rec_ai", "detection_method": "ai", "stage": "draft", "status": "ready", "params": {}}
    if server.pipeline_next_recommendation_stage(ai_task) != "":
        raise AssertionError("non-training tasks must not pre-generate recommendations")

    signature = server.pipeline_recommendation_signature(draft_task, "samples")
    draft_task["recommended_params"] = {
        "stage": "samples",
        "params": {"sample_count": 321, "train_mode": "yolo"},
        "reason": "smoke",
        "source": "rules",
        "signature": signature,
        "created_at": int(time.time()),
    }
    if not server.pipeline_recommendation_ready(draft_task, "samples"):
        raise AssertionError("stored recommendation with matching signature should report ready")
    if server.collect_pipeline_recommendation_pregen([draft_task]):
        raise AssertionError("ready recommendation should not be re-scheduled")
    consumed = server.consume_pipeline_recommendation(draft_task, "samples")
    if not consumed or int(consumed.get("sample_count") or 0) != 321:
        raise AssertionError(f"consume should return the pre-generated params: {consumed}")
    if draft_task.get("recommended_params") is not None:
        raise AssertionError("consume should clear the stored recommendation")
    if draft_task.get("agent_source") != "rules":
        raise AssertionError("consume should surface the recommendation source on the task")


def assert_worker_training_watcher_is_safe_without_worker() -> None:
    original_base = os.environ.get(server.WINDOWS_WORKER_BASE_URL_ENV)
    try:
        os.environ.pop(server.WINDOWS_WORKER_BASE_URL_ENV, None)
        if server._worker_training_watch_once() != 0:
            raise AssertionError("worker watcher should be a no-op when no worker base url is configured")
    finally:
        if original_base is None:
            os.environ.pop(server.WINDOWS_WORKER_BASE_URL_ENV, None)
        else:
            os.environ[server.WINDOWS_WORKER_BASE_URL_ENV] = original_base
    if not server.worker_training_watcher_enabled():
        raise AssertionError("worker watcher should be enabled by default")


def assert_agent_pipeline_chat(client: TestClient, owner: dict[str, str]) -> None:
    response = client.post("/api/pipeline/tasks", json={"name": "Agent chat smoke", "detection_method": "yolo"})
    assert_status(response, 200, "create YOLO task for chat")
    chat_task_id = response.json()["id"]
    response = client.patch(f"/api/pipeline/tasks/{chat_task_id}", json={"accessory_ids": ["acc_pipe"]})
    assert_status(response, 200, "add accessory to chat task")

    response = client.post(f"/api/pipeline/tasks/{chat_task_id}/chat", json={"message": "  "})
    assert_status(response, 400, "blank chat message is rejected")

    response = client.post(f"/api/pipeline/tasks/{chat_task_id}/chat", json={"message": "请重新规划姿态方案，每个配件只保留俯视角"})
    assert_status(response, 200, "chat replans via rule fallback when Agent is offline")
    chat_task = response.json()
    conversation = (chat_task.get("agent_mcp") or {}).get("conversation") or []
    roles = [entry.get("role") for entry in conversation]
    if "user" not in roles or "agent" not in roles:
        raise AssertionError(f"chat did not persist a two-way conversation: {conversation}")
    agent_turn = next((entry for entry in conversation if entry.get("role") == "agent"), {})
    if agent_turn.get("action") != "replan" or agent_turn.get("source") != "rules":
        raise AssertionError(f"chat agent turn did not record the rule-fallback replan action: {agent_turn}")
    if not (chat_task.get("agent_mcp") or {}).get("pose_plan"):
        raise AssertionError(f"replan via chat did not build a pose plan: {chat_task}")

    response = client.post(f"/api/pipeline/tasks/{chat_task_id}/chat", json={"message": "算了，取消这个任务"})
    assert_status(response, 200, "chat cancels task via rule fallback")
    cancelled_task = response.json()
    if cancelled_task.get("status") != "stopped":
        raise AssertionError(f"chat cancel intent did not stop the task: {cancelled_task}")
    cancel_conversation = (cancelled_task.get("agent_mcp") or {}).get("conversation") or []
    if not any(entry.get("action") == "cancel" for entry in cancel_conversation if entry.get("role") == "agent"):
        raise AssertionError(f"chat cancel turn was not recorded: {cancel_conversation}")

    response = client.delete(f"/api/pipeline/tasks/{chat_task_id}")
    assert_status(response, 200, "delete chat task")

    response = client.post("/api/pipeline/tasks", json={"name": "AI chat guard", "detection_method": "ai"})
    assert_status(response, 200, "create AI task for chat guard")
    ai_chat_task_id = response.json()["id"]
    response = client.post(f"/api/pipeline/tasks/{ai_chat_task_id}/chat", json={"message": "帮我推进一下"})
    assert_status(response, 409, "chat is rejected for non-training detection methods")
    response = client.delete(f"/api/pipeline/tasks/{ai_chat_task_id}")
    assert_status(response, 200, "delete AI chat guard task")


def main() -> None:
    seed_anchor_pose_guides()
    assert_react_pipeline_route()
    assert_agent_pipeline_decision_helpers()
    assert_output_path_visibility_rules()
    assert_pipeline_recommendation_pregen_helpers()
    assert_worker_training_watcher_is_safe_without_worker()
    assert_worker_gateway_rewrites_imported_dataset_yaml_to_windows_path()
    assert_worker_gateway_training_preflight_blocks_when_local_backend_down()
    assert_worker_gateway_bootstraps_local_backend_session()
    assert_gemini_auto_local_proxy_settings()
    if server.route_allowed_permissions("/api/pipeline/tasks", "GET") != ("training_pipeline",):
        raise AssertionError("pipeline task list must require training_pipeline permission")
    if server.route_allowed_permissions("/api/pipeline/accessories/acc_pipe", "POST") != ("training_pipeline",):
        raise AssertionError("pipeline accessory add must require training_pipeline permission")
    if server.route_allowed_permissions("/api/training/resources", "GET") != ("model_library", "training_pipeline"):
        raise AssertionError("training resources must allow model_library or training_pipeline")

    client = TestClient(server.app, base_url="https://testserver")
    response = client.post(
        "/api/auth/bootstrap",
        json={"username": "admin", "display_name": "Admin", "password": "admin-password-1"},
    )
    assert_status(response, 200, "bootstrap admin")
    pipeline_user = create_user(client, "pipeline_user", ["training_pipeline"])
    create_user(client, "zero_user", [])
    seed_accessory("acc_pipe", "Pipeline smoke accessory", pipeline_user)
    assert_agent_mcp_pose_assets_satisfy_normalized_gate(pipeline_user)
    logout(client, "admin logout")

    login(client, "pipeline_user", "pipeline_user-password-1")
    response = client.get("/api/pipeline/tasks")
    assert_status(response, 200, "pipeline user lists tasks")
    payload = response.json()
    if payload["items"] or payload["accessories"]:
        raise AssertionError(f"fresh pipeline should be empty: {payload}")

    response = client.post("/api/pipeline/accessories/acc_pipe")
    assert_status(response, 200, "pipeline user adds in-flow accessory")
    if response.json()["accessory_id"] != "acc_pipe":
        raise AssertionError("pipeline accessory add returned wrong id")

    response = client.get("/api/pipeline/tasks")
    assert_status(response, 200, "pipeline user reloads in-flow accessories")
    if {item["id"] for item in response.json()["accessories"]} != {"acc_pipe"}:
        raise AssertionError(f"in-flow accessory missing: {response.json()}")

    original_ai_detection_settings = server.ai_detection_settings
    original_generate_image = server.GeminiAiProvider.generate_image

    response = client.post("/api/pipeline/tasks", json={"name": "YOLO pending smoke", "detection_method": "yolo"})
    assert_status(response, 200, "pipeline user creates YOLO task")
    pending_task_id = response.json()["id"]
    response = client.patch(f"/api/pipeline/tasks/{pending_task_id}", json={"accessory_ids": ["acc_pipe"]})
    assert_status(response, 200, "pipeline user adds accessory to YOLO task")
    try:
        server.ai_detection_settings = lambda: {
            "configured": False,
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "api_key_present": False,
            "api_key_env": "GEMINI_API_KEY",
            "api_key": "",
            "timeout_seconds": 10.0,
            "proxy_configured": False,
            "proxy_auto_local": False,
            "proxy_url_raw": "",
            "status": "missing_api_key",
            "message": "Missing AI provider API key (GEMINI_API_KEY).",
        }
        response = client.post(f"/api/pipeline/tasks/{pending_task_id}/advance")
        assert_status(response, 200, "pipeline records Agent/MCP needs-user-action")
        pending_task = response.json()
        agent_mcp = pending_task.get("agent_mcp") or {}
        pose_plan = agent_mcp.get("pose_plan") or {}
        pose_accessories = pose_plan.get("accessories") or []
        pose_calls = [call for call in agent_mcp.get("tool_calls") or [] if call.get("tool") == "generate_accessory_pose_image"]
        if pending_task.get("stage") != "draft" or pending_task.get("status") != "needs_user_action" or pending_task.get("samples_task_id"):
            raise AssertionError(f"pipeline should pause before samples while Gemini image settings are blank: {pending_task}")
        if not pose_accessories or pose_plan.get("pose_count", 0) <= 0:
            raise AssertionError(f"Agent/MCP pose plan was not persisted: {pending_task}")
        if not pose_calls or {call.get("status") for call in pose_calls} != {"missing_configuration"}:
            raise AssertionError(f"pose image tool calls did not record missing configuration: {pose_calls}")
        if {call.get("provider") for call in pose_calls} != {"gemini_native_image_generation"}:
            raise AssertionError(f"pose image tool calls did not use Gemini provider contract: {pose_calls}")
        if any((pose.get("request") or {}).get("target_paper") or (pose.get("request") or {}).get("grid_layout") for plan in pose_accessories for pose in plan.get("poses") or []):
            raise AssertionError(f"new Agent/MCP path leaked target-paper/grid request: {pose_accessories}")
        response = client.post(f"/api/pipeline/tasks/{pending_task_id}/agent-feedback", json={"action": "replan", "decision": "replan"})
        assert_status(response, 200, "pipeline user replans Agent/MCP task")
        if (response.json().get("agent_mcp") or {}).get("state") != "needs_user_action":
            raise AssertionError(f"replan did not keep task paused for missing Gemini config: {response.json()}")
        response = client.post(
            f"/api/pipeline/tasks/{pending_task_id}/agent-feedback",
            json={"action": "resume", "decision": "continue_existing_assets"},
        )
        assert_status(response, 200, "pipeline user resumes with existing assets")
        pending_task = response.json()
        if not (pending_task.get("agent_mcp") or {}).get("skip_pose_image_generation"):
            raise AssertionError(f"resume did not persist skip decision: {pending_task}")
        if pending_task.get("samples_task_id"):
            sample_calls = [call for call in (pending_task.get("agent_mcp") or {}).get("tool_calls") or [] if call.get("tool") == "generate_training_samples"]
            if not sample_calls:
                raise AssertionError(f"sample tool call was not logged after resume: {pending_task}")
        else:
            pause = (pending_task.get("agent_mcp") or {}).get("pause") or {}
            reason = str(pending_task.get("last_error") or pause.get("reason") or "")
            if (
                pending_task.get("status") != "needs_user_action"
                or pause.get("stage") != "pose_image_generation"
                or "缺少可用于样本生成的规范化/参考素材" not in reason
            ):
                raise AssertionError(f"resume should pause with explicit missing-asset reason when existing assets are missing: {pending_task}")
    finally:
        server.ai_detection_settings = original_ai_detection_settings
    response = client.delete(f"/api/pipeline/tasks/{pending_task_id}")
    assert_status(response, 200, "pipeline user deletes pending YOLO task")

    response = client.post("/api/pipeline/tasks", json={"name": "YOLO Gemini pose smoke", "detection_method": "yolo"})
    assert_status(response, 200, "pipeline user creates Gemini YOLO task")
    gemini_task_id = response.json()["id"]
    response = client.patch(f"/api/pipeline/tasks/{gemini_task_id}", json={"accessory_ids": ["acc_pipe"]})
    assert_status(response, 200, "pipeline user adds accessory to Gemini YOLO task")

    png_bytes = server.base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADElEQVR42mP8z8AARQAFAAHiAMW2AAAAAElFTkSuQmCC"
    )

    def fake_ai_detection_settings() -> dict[str, object]:
        return {
            "configured": True,
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "api_key_present": True,
            "api_key_env": "GEMINI_API_KEY",
            "api_key": "test-gemini-key",
            "timeout_seconds": 10.0,
            "proxy_configured": True,
            "proxy_url": "http://127.0.0.1:17890",
            "proxy_source_name": "auto_local_mihomo",
            "proxy_auto_local": True,
            "proxy_url_raw": "http://127.0.0.1:17890",
            "status": "ready",
            "message": "AI provider is configured.",
        }

    def fake_generate_image(self, prompt: str, user_content: list[dict[str, object]], *, model: str) -> dict[str, object]:
        if model != server.AGENT_MCP_GEMINI_IMAGE_DEFAULT_MODEL:
            raise AssertionError(f"Gemini pose image used wrong model: {model}")
        if "target paper" not in prompt.lower() or "do not" not in prompt.lower():
            raise AssertionError(f"Gemini pose prompt lost target-paper guard: {prompt}")
        return {
            "bytes": png_bytes,
            "mime_type": "image/png",
            "latency_ms": 12,
            "model": model,
            "usage_metadata": {"totalTokenCount": 3},
            "text": "generated",
            "proxy_used": True,
            "proxy_source_name": "auto_local_mihomo",
            "proxy_url": "http://127.0.0.1:17890",
            "proxy_auto_local": True,
        }

    try:
        server.ai_detection_settings = fake_ai_detection_settings
        server.GeminiAiProvider.generate_image = fake_generate_image
        response = client.post(f"/api/pipeline/tasks/{gemini_task_id}/advance")
        assert_status(response, 200, "pipeline executes Gemini native pose images")
        gemini_task = response.json()
    finally:
        server.ai_detection_settings = original_ai_detection_settings
        server.GeminiAiProvider.generate_image = original_generate_image

    gemini_mcp = gemini_task.get("agent_mcp") or {}
    gemini_calls = [call for call in gemini_mcp.get("tool_calls") or [] if call.get("tool") == "generate_accessory_pose_image"]
    if not gemini_calls or {call.get("status") for call in gemini_calls} != {"completed"}:
        raise AssertionError(f"Gemini pose image calls did not complete: {gemini_calls}")
    if {call.get("model") for call in gemini_calls} != {server.AGENT_MCP_GEMINI_IMAGE_DEFAULT_MODEL}:
        raise AssertionError(f"Gemini pose image calls did not record default model: {gemini_calls}")
    for call in gemini_calls:
        output_path = Path(str(call.get("output_path") or ""))
        metadata_path = Path(str(call.get("metadata_path") or ""))
        if not output_path.exists() or not metadata_path.exists():
            raise AssertionError(f"Gemini pose image artifact missing: {call}")
        metadata = server.json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("provider") != "gemini_native_image_generation" or metadata.get("model") != server.AGENT_MCP_GEMINI_IMAGE_DEFAULT_MODEL:
            raise AssertionError(f"Gemini pose metadata missing provider/model: {metadata}")
        if not ((metadata.get("generated_source_metadata") or {}).get("synthid_watermark_expected")):
            raise AssertionError(f"Gemini pose metadata missing SynthID expectation: {metadata}")
        proxy = metadata.get("proxy") or {}
        if proxy.get("used") is not True or proxy.get("source_name") != "auto_local_mihomo":
            raise AssertionError(f"Gemini pose metadata missing proxy provenance: {metadata}")
    if (gemini_mcp.get("tool_config") or {}).get("pose_image_generation", {}).get("provider") != "gemini_native_image_generation":
        raise AssertionError(f"Gemini tool config was not persisted: {gemini_mcp}")
    if gemini_task.get("status") == "needs_user_action":
        raise AssertionError(f"configured Gemini pose generation should not pause for missing configuration: {gemini_task}")
    response = client.delete(f"/api/pipeline/tasks/{gemini_task_id}")
    assert_status(response, 200, "pipeline user deletes Gemini YOLO task")

    response = client.post("/api/pipeline/tasks", json={"name": "AI pipeline smoke", "detection_method": "ai"})
    assert_status(response, 200, "pipeline user creates task")
    task = response.json()
    task_id = task["id"]
    if task["stage"] != "draft" or task["detection_method"] != "ai":
        raise AssertionError(f"created pipeline task wrong stage/method: {task}")

    response = client.patch(
        f"/api/pipeline/tasks/{task_id}",
        json={"accessory_ids": ["acc_pipe"], "accessory_counts": {"acc_pipe": 2}},
    )
    assert_status(response, 200, "pipeline user adds accessory to task")
    task = response.json()
    if 2 not in set((task.get("accessory_counts") or {}).values()) or task["accessories"][0]["count"] != 2:
        raise AssertionError(f"pipeline task count did not persist: {task}")

    response = client.post(f"/api/pipeline/tasks/{task_id}/advance")
    assert_status(response, 200, "pipeline user advances AI task")
    task = response.json()
    if task["stage"] != "library" or task["linked_view"] != "aiInspect" or not task.get("ai_task_id"):
        raise AssertionError(f"AI pipeline task did not archive into linked workbench: {task}")

    response = client.delete(f"/api/pipeline/tasks/{task_id}")
    assert_status(response, 200, "pipeline user deletes task")

    assert_agent_pipeline_chat(client, pipeline_user)

    response = client.delete("/api/pipeline/accessories/acc_pipe")
    assert_status(response, 200, "pipeline user removes in-flow accessory")

    linked_job_id = "samples_pipeline_cleanup"
    server.save_training_task(
        {
            "job_id": linked_job_id,
            "task_id": linked_job_id,
            "action": "generate_samples",
            "status": "running",
            "progress": 30,
            "created_at": int(time.time()),
            "selected_accessory_ids": ["acc_pipe"],
            "sample_count": 50,
            "owner_user_id": pipeline_user["id"],
            "owner_username": pipeline_user["username"],
        }
    )
    cleanup_task_id = "pipe_cleanup_sample"
    tasks = server.load_pipeline_tasks()
    tasks.append(
        {
            "id": cleanup_task_id,
            "name": "Cleanup sample job",
            "accessory_ids": ["acc_pipe"],
            "accessory_counts": {"acc_pipe": 1},
            "detection_method": "yolo",
            "stage": "samples",
            "status": "running",
            "progress": 30,
            "samples_task_id": linked_job_id,
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
            "owner_user_id": pipeline_user["id"],
            "owner_username": pipeline_user["username"],
        }
    )
    server.save_pipeline_tasks(tasks)
    response = client.delete(f"/api/pipeline/tasks/{cleanup_task_id}")
    assert_status(response, 200, "pipeline delete cleans linked sample job")
    if response.json().get("deleted_training_jobs") != [linked_job_id]:
        raise AssertionError(f"linked training job was not reported deleted: {response.json()}")
    if server.training_task_path(linked_job_id).exists():
        raise AssertionError("linked sample job file remained after pipeline task delete")
    response = client.get("/api/training/resources")
    assert_status(response, 200, "training resources after linked cleanup")
    resources = response.json()
    leaked = []
    for collection_name in ("tasks", "training_tasks"):
        leaked.extend(
            item
            for item in resources.get(collection_name) or []
            if item.get("job_id") == linked_job_id
        )
    if leaked:
        raise AssertionError(f"linked sample job leaked in training resources: {leaked}")

    active_job_id = "samples_pipeline_active_cleanup"
    server.save_training_task(
        {
            "job_id": active_job_id,
            "task_id": active_job_id,
            "action": "generate_samples",
            "status": "running",
            "progress": 30,
            "created_at": int(time.time()),
            "selected_accessory_ids": ["acc_pipe"],
            "sample_count": 50,
            "owner_user_id": pipeline_user["id"],
            "owner_username": pipeline_user["username"],
        }
    )
    active_cleanup_task_id = "pipe_cleanup_active_sample"
    tasks = server.load_pipeline_tasks()
    tasks.append(
        {
            "id": active_cleanup_task_id,
            "name": "Cleanup active sample job",
            "accessory_ids": ["acc_pipe"],
            "accessory_counts": {"acc_pipe": 1},
            "detection_method": "yolo",
            "stage": "samples",
            "status": "running",
            "progress": 30,
            "samples_task_id": active_job_id,
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
            "owner_user_id": pipeline_user["id"],
            "owner_username": pipeline_user["username"],
        }
    )
    server.save_pipeline_tasks(tasks)
    active_thread_stop = threading.Event()
    active_thread = threading.Thread(target=active_thread_stop.wait, args=(5,), name="smoke-active-sample-task", daemon=True)
    active_thread.start()
    server._training_task_threads[active_job_id] = active_thread
    try:
        response = client.delete(f"/api/pipeline/tasks/{active_cleanup_task_id}")
        assert_status(response, 200, "pipeline delete stops active linked sample job")
        server.update_training_task(
            active_job_id,
            status="completed",
            progress=100,
            completed_at=int(time.time()),
            note="训练样本已生成完成。",
        )
        active_task = server.load_training_task(server.training_task_path(active_job_id))
        if not active_task or active_task.get("status") != "stopped" or active_task.get("progress") != 100:
            raise AssertionError(f"active linked sample job was not preserved as stopped: {active_task}")
        if active_task.get("note") == "训练样本已生成完成。":
            raise AssertionError(f"late active sample completion update was persisted: {active_task}")
    finally:
        active_thread_stop.set()
        active_thread.join(timeout=1)
        server._training_task_threads.pop(active_job_id, None)

    worker_local_job_id = "samples_worker_local_completion"
    server.save_training_task(
        {
            "job_id": worker_local_job_id,
            "task_id": worker_local_job_id,
            "action": "generate_samples",
            "status": "queued",
            "progress": 0,
            "created_at": int(time.time()),
            "selected_accessory_ids": ["acc_pipe"],
            "sample_count": 50,
            "owner_user_id": pipeline_user["id"],
            "owner_username": pipeline_user["username"],
        }
    )
    original_executor = os.environ.get("INSPECTION_TRAINING_EXECUTOR")
    original_generate = server.generate_training_dataset
    original_worker_request = server.windows_worker_request
    worker_calls: list[tuple[str, str]] = []

    def fake_worker_request(method: str, path: str, **_: object) -> dict[str, object]:
        worker_calls.append((method, path))
        raise AssertionError("generate_samples should not call Windows Worker in worker executor mode")

    def fake_generate_dataset(task: dict[str, object]) -> dict[str, str]:
        return {
            "dataset_dir": str(server.OUTPUT_DIR / "training_datasets" / str(task["job_id"])),
            "dataset_yaml": str(server.OUTPUT_DIR / "training_datasets" / str(task["job_id"]) / "dataset.yaml"),
            "manifest_path": str(server.OUTPUT_DIR / "training_datasets" / str(task["job_id"]) / "manifest.json"),
        }

    try:
        os.environ["INSPECTION_TRAINING_EXECUTOR"] = "worker"
        server.generate_training_dataset = fake_generate_dataset
        server.windows_worker_request = fake_worker_request
        server.run_training_task(worker_local_job_id)
    finally:
        if original_executor is None:
            os.environ.pop("INSPECTION_TRAINING_EXECUTOR", None)
        else:
            os.environ["INSPECTION_TRAINING_EXECUTOR"] = original_executor
        server.generate_training_dataset = original_generate
        server.windows_worker_request = original_worker_request
    if worker_calls:
        raise AssertionError(f"worker sample generation made unexpected worker calls: {worker_calls}")
    worker_task = server.load_training_task(server.training_task_path(worker_local_job_id))
    if not worker_task or worker_task.get("status") != "completed" or worker_task.get("progress") != 100:
        raise AssertionError(f"worker-mode sample generation did not complete locally: {worker_task}")
    if worker_task.get("training_executor") != "local" or not worker_task.get("worker_sample_generation_bypassed"):
        raise AssertionError(f"worker-mode sample generation did not record local execution: {worker_task}")

    worker_dataset = seed_training_dataset("samples_worker_hk_dataset", pipeline_user, "acc_pipe")
    original_executor = os.environ.get("INSPECTION_TRAINING_EXECUTOR")
    original_run_training_task = server.run_training_task
    started_training_jobs: list[str] = []

    def fake_run_training_task(job_id: str) -> None:
        started_training_jobs.append(job_id)

    try:
        os.environ["INSPECTION_TRAINING_EXECUTOR"] = "worker"
        server.run_training_task = fake_run_training_task
        response = client.post(
            "/api/training/start",
            json={
                "selected_accessory_ids": ["acc_pipe"],
                "dataset_id": worker_dataset["id"],
                "epochs": 1,
                "image_size": 480,
            },
        )
        assert_status(response, 200, "worker-mode training start keeps HK dataset metadata")
        worker_train_job_id = response.json()["job_id"]
        server._training_task_threads[worker_train_job_id].join(timeout=1)
    finally:
        if original_executor is None:
            os.environ.pop("INSPECTION_TRAINING_EXECUTOR", None)
        else:
            os.environ["INSPECTION_TRAINING_EXECUTOR"] = original_executor
        server.run_training_task = original_run_training_task
    if started_training_jobs != [worker_train_job_id]:
        raise AssertionError(f"training job thread did not start as expected: {started_training_jobs}")
    worker_train_task = server.load_training_task(server.training_task_path(worker_train_job_id))
    if not worker_train_task or worker_train_task.get("dataset_yaml") != worker_dataset["dataset_yaml"]:
        raise AssertionError(f"worker-mode training task lost HK dataset metadata: {worker_train_task}")

    fake_archive_path = Path(tempfile.mkdtemp(prefix="phase3d_bundle_manifest_")) / "dataset.zip"
    fake_archive_path.write_bytes(b"phase3d-bundle")
    bundle_metadata = server.worker_training_bundle_metadata(
        worker_train_job_id,
        worker_train_task,
        worker_dataset,
        Path(worker_dataset["dataset_dir"]),
        fake_archive_path,
    )
    encoded_metadata = server.json.dumps(bundle_metadata, ensure_ascii=False)
    if worker_dataset["dataset_dir"] in encoded_metadata or worker_dataset["dataset_yaml"] in encoded_metadata:
        raise AssertionError(f"worker bundle metadata leaked HK filesystem paths: {bundle_metadata}")
    if bundle_metadata["dataset_archive"]["sha256"] != server.file_sha256(fake_archive_path):
        raise AssertionError(f"worker bundle metadata did not include archive checksum: {bundle_metadata}")
    if not bundle_metadata["dataset_files"] or any(Path(item["path"]).is_absolute() for item in bundle_metadata["dataset_files"]):
        raise AssertionError(f"worker bundle metadata did not use relative dataset file manifest paths: {bundle_metadata}")

    original_executor = os.environ.get("INSPECTION_TRAINING_EXECUTOR")
    original_worker_request = server.windows_worker_request
    original_post_worker_training_bundle = server.post_worker_training_bundle
    original_popen = server.subprocess.Popen
    original_device = os.environ.get("INSPECTION_YOLO_DEVICE")
    original_yolo_command = os.environ.get("INSPECTION_YOLO_COMMAND")
    original_local_fallback = os.environ.get("INSPECTION_WORKER_LOCAL_TRAINING_FALLBACK")
    worker_train_calls: list[tuple[str, str]] = []
    worker_bundle_calls: list[tuple[str, str]] = []

    def fake_training_worker_request(method: str, path: str, **_: object) -> dict[str, object]:
        worker_train_calls.append((method, path))
        raise AssertionError("HK dataset training should use bundle import instead of JSON path submission")

    def fake_post_worker_training_bundle(job_id: str, task: dict[str, object], dataset: dict[str, object]) -> dict[str, object]:
        worker_bundle_calls.append((job_id, str(dataset.get("dataset_yaml") or "")))
        if not Path(str(dataset.get("dataset_yaml") or "")).exists():
            raise AssertionError(f"worker bundle did not receive a resolvable HK dataset yaml: {dataset}")
        return {
            "job_id": f"worker_{job_id}",
            "status": "submitted",
            "transfer": {
                "mode": "archive_upload",
                "imported_dataset_id": f"imported_{job_id}",
                "archive_sha256": "0" * 64,
            },
        }

    class FakeTrainingProcess:
        pid = 4242
        returncode = 0

        def poll(self) -> int:
            return 0

    def fake_popen(command: list[str], **_: object) -> FakeTrainingProcess:
        if command[0] != "/tmp/fake-yolo":
            raise AssertionError(f"local HK training did not use resolved YOLO command: {command}")
        expected_cpu_flags = {"device=cpu", "batch=1", "cache=False", "amp=False", "plots=False"}
        missing_cpu_flags = sorted(expected_cpu_flags - set(command))
        if missing_cpu_flags:
            raise AssertionError(f"local HK training did not use CPU-safe flags {missing_cpu_flags}: {command}")
        return FakeTrainingProcess()

    try:
        os.environ["INSPECTION_TRAINING_EXECUTOR"] = "worker"
        os.environ["INSPECTION_YOLO_DEVICE"] = "cpu"
        os.environ["INSPECTION_YOLO_COMMAND"] = "/tmp/fake-yolo"
        os.environ.pop("INSPECTION_WORKER_LOCAL_TRAINING_FALLBACK", None)
        server.windows_worker_request = fake_training_worker_request
        server.post_worker_training_bundle = fake_post_worker_training_bundle
        server.subprocess.Popen = fake_popen
        server.run_training_task(worker_train_job_id)
    finally:
        if original_executor is None:
            os.environ.pop("INSPECTION_TRAINING_EXECUTOR", None)
        else:
            os.environ["INSPECTION_TRAINING_EXECUTOR"] = original_executor
        if original_device is None:
            os.environ.pop("INSPECTION_YOLO_DEVICE", None)
        else:
            os.environ["INSPECTION_YOLO_DEVICE"] = original_device
        if original_yolo_command is None:
            os.environ.pop("INSPECTION_YOLO_COMMAND", None)
        else:
            os.environ["INSPECTION_YOLO_COMMAND"] = original_yolo_command
        if original_local_fallback is None:
            os.environ.pop("INSPECTION_WORKER_LOCAL_TRAINING_FALLBACK", None)
        else:
            os.environ["INSPECTION_WORKER_LOCAL_TRAINING_FALLBACK"] = original_local_fallback
        server.windows_worker_request = original_worker_request
        server.post_worker_training_bundle = original_post_worker_training_bundle
        server.subprocess.Popen = original_popen
    if worker_train_calls:
        raise AssertionError(f"HK dataset training made unexpected worker calls: {worker_train_calls}")
    if len(worker_bundle_calls) != 1 or worker_bundle_calls[0][0] != worker_train_job_id:
        raise AssertionError(f"HK dataset training did not submit exactly one worker bundle: {worker_bundle_calls}")
    worker_train_task = server.load_training_task(server.training_task_path(worker_train_job_id))
    if not worker_train_task or worker_train_task.get("status") != "running" or worker_train_task.get("progress") != 30:
        raise AssertionError(f"worker-mode HK dataset training did not enter remote running state: {worker_train_task}")
    if worker_train_task.get("training_executor") != "worker" or not worker_train_task.get("worker_transfer_required"):
        raise AssertionError(f"worker-mode HK dataset training did not record worker transfer execution: {worker_train_task}")
    if worker_train_task.get("remote_training_job_id") != f"worker_{worker_train_job_id}":
        raise AssertionError(f"worker-mode HK dataset training did not preserve remote worker job id: {worker_train_task}")

    fallback_job_id = "train_worker_local_emergency_fallback"
    server.save_training_task(
        {
            "job_id": fallback_job_id,
            "task_id": fallback_job_id,
            "action": "train_model",
            "status": "queued",
            "progress": 0,
            "created_at": int(time.time()),
            "selected_accessory_ids": ["acc_pipe"],
            "sample_count": 1,
            "mode": "yolo_ocr",
            "epochs": 1,
            "image_size": 480,
            "source_dataset_id": worker_dataset["id"],
            "dataset_dir": worker_dataset["dataset_dir"],
            "dataset_yaml": worker_dataset["dataset_yaml"],
            "manifest_path": worker_dataset["manifest_path"],
            "owner_user_id": pipeline_user["id"],
            "owner_username": pipeline_user["username"],
        }
    )
    original_executor = os.environ.get("INSPECTION_TRAINING_EXECUTOR")
    original_worker_request = server.windows_worker_request
    original_popen = server.subprocess.Popen
    original_device = os.environ.get("INSPECTION_YOLO_DEVICE")
    original_yolo_command = os.environ.get("INSPECTION_YOLO_COMMAND")
    original_local_fallback = os.environ.get("INSPECTION_WORKER_LOCAL_TRAINING_FALLBACK")
    fallback_worker_calls: list[tuple[str, str]] = []

    def fake_fallback_worker_request(method: str, path: str, **_: object) -> dict[str, object]:
        fallback_worker_calls.append((method, path))
        raise AssertionError("Emergency local fallback should not call Windows Worker")

    try:
        os.environ["INSPECTION_TRAINING_EXECUTOR"] = "worker"
        os.environ["INSPECTION_WORKER_LOCAL_TRAINING_FALLBACK"] = "1"
        os.environ["INSPECTION_YOLO_DEVICE"] = "cpu"
        os.environ["INSPECTION_YOLO_COMMAND"] = "/tmp/fake-yolo"
        server.windows_worker_request = fake_fallback_worker_request
        server.subprocess.Popen = fake_popen
        server.run_training_task(fallback_job_id)
    finally:
        if original_executor is None:
            os.environ.pop("INSPECTION_TRAINING_EXECUTOR", None)
        else:
            os.environ["INSPECTION_TRAINING_EXECUTOR"] = original_executor
        if original_local_fallback is None:
            os.environ.pop("INSPECTION_WORKER_LOCAL_TRAINING_FALLBACK", None)
        else:
            os.environ["INSPECTION_WORKER_LOCAL_TRAINING_FALLBACK"] = original_local_fallback
        if original_device is None:
            os.environ.pop("INSPECTION_YOLO_DEVICE", None)
        else:
            os.environ["INSPECTION_YOLO_DEVICE"] = original_device
        if original_yolo_command is None:
            os.environ.pop("INSPECTION_YOLO_COMMAND", None)
        else:
            os.environ["INSPECTION_YOLO_COMMAND"] = original_yolo_command
        server.windows_worker_request = original_worker_request
        server.subprocess.Popen = original_popen
    if fallback_worker_calls:
        raise AssertionError(f"emergency local fallback made unexpected worker calls: {fallback_worker_calls}")
    fallback_task = server.load_training_task(server.training_task_path(fallback_job_id))
    if not fallback_task or fallback_task.get("status") != "completed" or fallback_task.get("training_executor") != "local":
        raise AssertionError(f"emergency local fallback did not complete locally: {fallback_task}")
    if not fallback_task.get("worker_training_bypassed") or not fallback_task.get("worker_transfer_required"):
        raise AssertionError(f"emergency local fallback was not explicitly labeled: {fallback_task}")

    import_job_id = "train_worker_artifact_import"
    model_payload = b"phase3d-worker-model"
    import_task = {
        "job_id": import_job_id,
        "task_id": import_job_id,
        "action": "train_model",
        "status": "running",
        "progress": 90,
        "created_at": int(time.time()),
        "selected_accessory_ids": ["acc_pipe"],
        "required_accessory_counts": {"acc_pipe": 1},
        "accessory_class_map": {"0": "acc_pipe"},
        "model_variant": "yolo_ocr",
        "mode": "yolo_ocr",
        "remote_training_job_id": f"worker_{import_job_id}",
        "dataset_dir": worker_dataset["dataset_dir"],
        "dataset_yaml": worker_dataset["dataset_yaml"],
        "manifest_path": worker_dataset["manifest_path"],
        "owner_user_id": pipeline_user["id"],
        "owner_username": pipeline_user["username"],
    }
    server.save_training_task(import_task)
    import_updates = server.import_worker_training_artifacts(
        import_task,
        {
            "models": [
                {
                    "artifact_filename": "best.pt",
                    "artifact_sha256": server.hashlib.sha256(model_payload).hexdigest(),
                    "artifact_b64": server.base64.b64encode(model_payload).decode("ascii"),
                }
            ]
        },
    )
    server.update_training_task(import_job_id, status="completed", progress=100, completed_at=int(time.time()), **import_updates)
    imported_task = server.load_training_task(server.training_task_path(import_job_id))
    imported_model_path = Path(str(imported_task.get("imported_model_path") or ""))
    if not imported_model_path.exists() or imported_model_path.read_bytes() != model_payload:
        raise AssertionError(f"worker artifact was not imported into HK model storage: {imported_task}")
    response = client.get("/api/training/resources")
    assert_status(response, 200, "training resources include imported worker model")
    imported_model = next((item for item in response.json().get("models", []) if item.get("run_id") == import_job_id), None)
    if not imported_model or imported_model.get("owner_user_id") != pipeline_user["id"]:
        raise AssertionError(f"imported worker model was not registered in library: {imported_model}")

    model_run_id = "train_phase3d_library_smoke"
    model_run_dir = server.output_write_dir_for_owner("training_runs", pipeline_user["id"]) / model_run_id
    (model_run_dir / "weights").mkdir(parents=True, exist_ok=True)
    (model_run_dir / "weights" / "best.pt").write_bytes(b"phase3d-smoke-model")
    server.save_training_task(
        {
            "job_id": model_run_id,
            "task_id": model_run_id,
            "action": "train_model",
            "status": "completed",
            "progress": 100,
            "created_at": int(time.time()),
            "completed_at": int(time.time()),
            "selected_accessory_ids": ["acc_pipe"],
            "required_accessory_counts": {"acc_pipe": 1},
            "accessory_class_map": {"0": "acc_pipe"},
            "model_variant": "yolo_ocr",
            "mode": "yolo_ocr",
            "dataset_dir": worker_dataset["dataset_dir"],
            "dataset_yaml": worker_dataset["dataset_yaml"],
            "manifest_path": worker_dataset["manifest_path"],
            "training_run_dir": str(model_run_dir),
            "owner_user_id": pipeline_user["id"],
            "owner_username": pipeline_user["username"],
        }
    )
    response = client.get("/api/training/resources")
    assert_status(response, 200, "training resources include completed model")
    resources = response.json()
    model = next((item for item in resources.get("models", []) if item.get("run_id") == model_run_id), None)
    if not model or not model.get("exists") or model.get("owner_user_id") != pipeline_user["id"]:
        raise AssertionError(f"completed training model was not registered in library: {model}")

    response = client.patch(
        f"/api/training/resources/models/{model_run_id}",
        json={"display_name": "Phase 3D library smoke", "note": "verified by smoke"},
    )
    assert_status(response, 200, "pipeline user updates model metadata")
    updated_model = next((item for item in response.json().get("models", []) if item.get("run_id") == model_run_id), None)
    if not updated_model or updated_model.get("label") != "Phase 3D library smoke":
        raise AssertionError(f"model metadata update did not refresh library payload: {updated_model}")

    archive_task_id = "pipe_archive_training_model"
    tasks = server.load_pipeline_tasks()
    tasks.append(
        {
            "id": archive_task_id,
            "name": "Archive trained model",
            "accessory_ids": ["acc_pipe"],
            "accessory_counts": {"acc_pipe": 1},
            "detection_method": "yolo_ocr",
            "stage": "training",
            "status": "completed",
            "progress": 100,
            "training_task_id": model_run_id,
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
            "owner_user_id": pipeline_user["id"],
            "owner_username": pipeline_user["username"],
        }
    )
    server.save_pipeline_tasks(tasks)
    response = client.post(f"/api/pipeline/tasks/{archive_task_id}/advance")
    assert_status(response, 200, "pipeline user archives completed training into library")
    archived_task = response.json()
    if archived_task.get("stage") != "library" or archived_task.get("status") != "completed":
        raise AssertionError(f"completed training task did not archive into library lane: {archived_task}")
    if archived_task.get("ai_model_id") != f"trained_{model_run_id}__yolo_ocr" or archived_task.get("linked_view") != "inspect":
        raise AssertionError(f"archived training task did not link the trained model for detection: {archived_task}")
    if archived_task.get("model_run_id") != model_run_id:
        raise AssertionError(f"archived training task did not record the model run id: {archived_task}")

    response = client.delete(f"/api/training/resources/models/{model_run_id}")
    assert_status(response, 200, "pipeline user drops model from library")
    dropped_model = next((item for item in response.json().get("models", []) if item.get("run_id") == model_run_id), None)
    if dropped_model is not None or model_run_dir.exists():
        raise AssertionError(f"deleted model run still appears in library/drop state: {dropped_model}")

    stale_job_id = "samples_stale_local"
    server.save_training_task(
        {
            "job_id": stale_job_id,
            "task_id": stale_job_id,
            "action": "generate_samples",
            "status": "running",
            "progress": 30,
            "created_at": int(time.time()),
            "selected_accessory_ids": ["acc_pipe"],
            "sample_count": 50,
            "owner_user_id": pipeline_user["id"],
            "owner_username": pipeline_user["username"],
        }
    )
    response = client.get("/api/training/resources")
    assert_status(response, 200, "training resources mark stale local job")
    stale = next((item for item in response.json().get("tasks", []) if item.get("job_id") == stale_job_id), None)
    if not stale or stale.get("status") != "stopped" or not stale.get("error"):
        raise AssertionError(f"stale local training job was not surfaced as stopped: {stale}")
    response = client.delete(f"/api/training/tasks/{stale_job_id}")
    assert_status(response, 200, "pipeline user deletes stale local training job")

    logout(client, "pipeline user logout")

    login(client, "zero_user", "zero_user-password-1")
    response = client.get("/api/pipeline/tasks")
    assert_status(response, 403, "zero user cannot list pipeline")

    print("smoke_phase3d_pipeline: ok")


if __name__ == "__main__":
    main()
