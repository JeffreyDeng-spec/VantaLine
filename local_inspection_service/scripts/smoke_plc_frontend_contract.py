#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "local_inspection_service" / "frontend" / "src"


def require(text: str, snippets: dict[str, str]) -> None:
    missing = [label for label, snippet in snippets.items() if snippet not in text]
    if missing:
        raise AssertionError("missing PLC frontend contract: " + ", ".join(missing))


def main() -> None:
    rules = (FRONTEND / "features" / "rules" / "RulesPage.tsx").read_text(encoding="utf-8")
    detection = (FRONTEND / "features" / "detection" / "DetectionWorkbenchPage.tsx").read_text(encoding="utf-8")
    queries = (FRONTEND / "api" / "queries.ts").read_text(encoding="utf-8")
    types = (FRONTEND / "api" / "types.ts").read_text(encoding="utf-8")
    web_serial = (FRONTEND / "features" / "plc" / "webSerialClient.ts").read_text(encoding="utf-8")
    server = (ROOT / "local_inspection_service" / "server.py").read_text(encoding="utf-8")

    require(
        rules,
        {
            "PLC settings tab": '{ value: "plc", label: "PLC 同步" }',
            "server-backed workstation query": "getPlcWorkstation",
            "server-backed workstation save": "savePlcWorkstationConfig",
            "station pairing": "pairPlcWorkstation",
            "enabled toggle": 'name="enabled"',
            "live ACK gate": "标记真实 ACK 已验证",
            "effective enabled": "effective_enabled",
            "result register": 'name="result_register"',
            "optional output point": 'name="output_control_point"',
            "audit display": "recent_dispatches",
            "server has zero serial I/O": "服务器永远不会打开串口",
        },
    )
    require(
        detection,
        {
            "result status": "result.plc_sync.status",
            "disabled no-I/O copy": "PLC 同步已关闭（未打开串口）",
            "failure copy": "PLC 同步失败",
            "diagnostic payload": "plc_sync: result.plc_sync || null",
            "workstation status": "getPlcWorkstation",
            "explicit connect": "connectPlc",
            "camera-only upload": "analyzeCamera",
            "browser execution": "plcClientRef.current.execute",
            "manual D206 diagnostic": "写入 6 并读取 D206",
        },
    )
    require(
        queries,
        {
            "workstation query key": 'plcWorkstation: ["plc", "workstation"]',
            "GET workstation": 'apiClient.get<PlcWorkstationResponse>("/api/plc/workstation")',
            "POST config": 'apiClient.post<PlcWorkstationResponse>("/api/plc/workstation/config", payload)',
            "camera endpoint": 'apiClient.upload<DetectionResult>("/api/analyze/camera"',
            "diagnostic endpoint": 'apiClient.post<PlcWebSerialDiagnosticPlan>("/api/plc/workstation/diagnostic-plan"',
        },
    )
    require(
        types,
        {
            "PLC v3 config type": "export interface PlcWebSerialConfig",
            "workstation type": "export interface PlcWorkstationResponse",
            "attempt type": "export interface PlcWebSerialAttempt",
            "effective enabled response": "effective_enabled: boolean",
            "detection result integration": "plc_sync?: PlcSyncStatus",
        },
    )
    if "localStorage" in rules:
        raise AssertionError("PLC settings must not use browser-only localStorage")
    analyze_start = server.index("def analyze_bgr(")
    auth_start = server.index('@app.get("/api/auth/status")', analyze_start)
    if "dispatch_plc_for_detection" in server[analyze_start:auth_start]:
        raise AssertionError("PLC dispatch must not run inside analyze_bgr or per video frame")
    if server.count("await dispatch_plc_for_detection_async(") != 0:
        raise AssertionError("server-side pyserial dispatch must have zero call sites")
    if "plc_sync" in server[server.index('@app.post("/api/analyze/image")'):server.index('@app.post("/api/analyze/camera")')]:
        raise AssertionError("ordinary image endpoint must not generate PLC plans")
    video_start = server.index('@app.post("/api/analyze/video")')
    video_end = server.index('@app.post("/api/stream/config")', video_start)
    if "dispatch_plc_for_detection" in server[video_start:video_end]:
        raise AssertionError("video endpoint must not generate PLC plans")
    require(
        web_serial,
        {
            "feature detection": "Boolean(navigator.serial)",
            "web lock": "navigator.locks.request",
            "explicit port chooser": "navigator.serial.requestPort()",
            "no retry": "端口已关闭；检查线路后人工重连",
            "D ACK gates Y": 'dResult.status === "acknowledged" && attempt.frames[1]',
            "heartbeat": "heartbeatPlcWorkstationConnection",
            "model rebind keeps serial open": "rebindPlcWorkstationModel",
            "NAK does not force close": "const requiresClose = uncertain",
            "NAK residual becomes auditable uncertain": 'operation.status = "unexpected_response"',
            "diagnostic read parser": "parseDiagnosticWordResponse",
        },
    )
    if "页面已离开前台，PLC 已安全断开" in detection:
        raise AssertionError("temporary page hiding must not disconnect PLC")

    phase1_surface = "\n".join(
        [
            (ROOT / "local_inspection_service" / "plc_fx_ascii.py").read_text(encoding="utf-8"),
            rules,
            detection,
        ]
    )
    forbidden = [token for token in ("modbus_rtu",) if token in phase1_surface]
    if forbidden:
        raise AssertionError("out-of-scope PLC handshake/protocol surfaced: " + ", ".join(forbidden))

    print("smoke_plc_frontend_contract: ok")


if __name__ == "__main__":
    main()
