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
    server = (ROOT / "local_inspection_service" / "server.py").read_text(encoding="utf-8")

    require(
        rules,
        {
            "PLC settings tab": '{ value: "plc", label: "PLC 同步" }',
            "server-backed query": "getPlcConfig",
            "server-backed save": "savePlcConfig",
            "enabled toggle": 'name="enabled"',
            "fixed protocol": 'value="fx_programming_port_ascii"',
            "checksum mode": 'name="checksum_mode"',
            "legacy VB executable mode": "exclude_etx_legacy_vb",
            "documented-comment mode": "include_etx_documented_comment",
            "checksum contradiction": "VB 可执行循环排除 ETX",
            "live ACK gate": "真实 PLC ACK gate",
            "effective enabled": "effective_enabled",
            "PG capability reason": "validation_errors",
            "serial port": 'name="serial_port"',
            "baudrate": 'name="baudrate"',
            "parity": 'name="parity"',
            "data bits": 'name="data_bits"',
            "stop bits": 'name="stop_bits"',
            "D206": 'name="d206_address"',
            "Y04": 'name="y04_address"',
            "write Y04": 'name="write_y04"',
            "timeout": 'name="timeout"',
            "retries": 'name="retries"',
            "audit display": "recent_dispatches",
            "no live test action": "本页不提供真实 PLC 扫描或测试写入",
        },
    )
    require(
        detection,
        {
            "result status": "result.plc_sync.status",
            "disabled no-I/O copy": "PLC 同步已关闭（未打开串口）",
            "failure copy": "PLC 同步失败",
            "diagnostic payload": "plc_sync: result.plc_sync || null",
        },
    )
    require(
        queries,
        {
            "PLC query key": 'plcConfig: ["plc", "config"]',
            "GET config": 'apiClient.get<PlcConfigResponse>("/api/plc/config")',
            "POST config": 'apiClient.post<PlcConfigResponse>("/api/plc/config", payload)',
        },
    )
    require(
        types,
        {
            "PLC config type": "export interface PlcConfig",
            "PLC sync state": '"disabled" | "queued" | "attempting" | "sent" | "acknowledged" | "failed"',
            "checksum type": "export type PlcChecksumMode",
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
    if server.count("await dispatch_plc_for_detection_async(") != 2:
        raise AssertionError("image/video final results must use exactly two async PLC worker dispatch points")
    if 'source="image"' not in server[server.index('@app.post("/api/analyze/image")'):server.index("def video_frame_result_payload")]:
        raise AssertionError("image final result must have exactly one explicit PLC dispatch point")
    video_start = server.index('@app.post("/api/analyze/video")')
    video_end = server.index('@app.post("/api/stream/config")', video_start)
    if 'source="video"' not in server[video_start:video_end]:
        raise AssertionError("video aggregate result must have exactly one explicit PLC dispatch point")

    phase1_surface = "\n".join(
        [
            (ROOT / "local_inspection_service" / "plc_fx_ascii.py").read_text(encoding="utf-8"),
            rules,
            detection,
        ]
    )
    forbidden = [token for token in ("D207", "D210", "D211", "D212", "modbus_rtu") if token in phase1_surface]
    if forbidden:
        raise AssertionError("out-of-scope PLC handshake/protocol surfaced: " + ", ".join(forbidden))

    print("smoke_plc_frontend_contract: ok")


if __name__ == "__main__":
    main()
