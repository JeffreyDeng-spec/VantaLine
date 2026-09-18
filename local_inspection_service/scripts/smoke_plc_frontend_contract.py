#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "local_inspection_service" / "frontend" / "src"


def require(text: str, snippets: dict[str, str]) -> None:
    missing = [label for label, snippet in snippets.items() if snippet not in text]
    if missing:
        raise AssertionError("missing PLC frontend contract: " + ", ".join(missing))


def require_detection_analysis_boundary(server: str, implementations: dict[str, str]) -> None:
    """Follow root adapters to both business bodies; do not inspect an empty shell."""
    tree = ast.parse(server)
    for receiver, class_name, module in (
        ("_detection_analysis", "DetectionAnalysis", "detection.analysis"),
        ("_ai_detection_analysis", "AiDetectionAnalysis", "detection.ai_analysis"),
    ):
        bindings = [node for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))
                    and any(isinstance(target, ast.Name) and target.id == receiver
                            for target in (node.targets if isinstance(node, ast.Assign) else [node.target]))]
        if (len(bindings) != 1 or not isinstance(bindings[0].value, ast.Call)
                or not isinstance(bindings[0].value.func, ast.Name) or bindings[0].value.func.id != class_name):
            raise AssertionError("Detection adapter must construct the inspected class: " + receiver)
        imports = [(node, alias) for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
                   for alias in node.names if (alias.asname or alias.name.split('.')[0]) == class_name]
        shadowed = any((isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == class_name)
                       or (isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
                           and any(isinstance(target, ast.Name) and target.id == class_name
                                   for target in (node.targets if isinstance(node, ast.Assign) else [node.target])))
                       for node in tree.body)
        if (len(imports) != 1 or shadowed or not isinstance(imports[0][0], ast.ImportFrom)
                or imports[0][0].level != 1 or imports[0][0].module != module or imports[0][1].name != class_name):
            raise AssertionError("Detection class must come from the inspected module: " + class_name)
    contracts = (
        ("analyze_bgr", "DetectionAnalysis", "analysis.py",
         "return _detection_analysis.analyze_bgr(image_bgr, request_id, model_id, image_path=image_path)", []),
        ("analyze_bgr_ai_detection", "AiDetectionAnalysis", "ai_analysis.py",
         "return _ai_detection_analysis.analyze_bgr_ai_detection(image_bgr, request_id, spec, config, image_path=image_path)",
         [ast.parse("pinned_model_profiles(resolve_model_profiles)", mode="eval").body]),
    )
    for name, class_name, filename, forwarding, decorators in contracts:
        roots = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
        if len(roots) != 1 or ast.dump(ast.Module(body=roots[0].body, type_ignores=[])) != ast.dump(ast.parse(forwarding)):
            raise AssertionError("Detection root must forward to the inspected implementation: " + name)
        if [ast.dump(node) for node in roots[0].decorator_list] != [ast.dump(node) for node in decorators]:
            raise AssertionError("Detection snapshot decorator changed: " + name)
        source = implementations[filename]
        classes = [node for node in ast.parse(source).body if isinstance(node, ast.ClassDef) and node.name == class_name]
        methods = [node for cls in classes for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name]
        if len(classes) != 1 or len(methods) != 1:
            raise AssertionError("PLC no-dispatch contract must inspect the actual implementation: " + name)
        if "dispatch_plc_for_detection" in ast.get_source_segment(source, methods[0]):
            raise AssertionError("PLC dispatch must not run inside ordinary or AI analysis")
    routes = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name) and node.func.id == "AnalysisRouting"]
    if (len(routes) != 1 or len(routes[0].args) < 2 or not isinstance(routes[0].args[1], ast.Lambda)
            or not isinstance(routes[0].args[1].body, ast.Call)
            or not isinstance(routes[0].args[1].body.func, ast.Name)
            or routes[0].args[1].body.func.id != "analyze_bgr_ai_detection"):
        raise AssertionError("Ordinary analysis must delegate through the pinned AI entry")


def main() -> None:
    rules = (FRONTEND / "features" / "rules" / "RulesPage.tsx").read_text(encoding="utf-8")
    rules += (FRONTEND / "features" / "rules" / "DeviceSettings.tsx").read_text(encoding="utf-8")
    detection = (FRONTEND / "features" / "detection" / "DetectionWorkbenchPage.tsx").read_text(encoding="utf-8")
    queries = (FRONTEND / "api" / "queries.ts").read_text(encoding="utf-8")
    types = (FRONTEND / "api" / "types.ts").read_text(encoding="utf-8")
    web_serial = (FRONTEND / "features" / "plc" / "webSerialClient.ts").read_text(encoding="utf-8")
    server = (ROOT / "local_inspection_service" / "server.py").read_text(encoding="utf-8")

    require(
        rules,
        {
            "PLC settings tab": '设备与运行',
            "server-backed workstation query": "getPlcWorkstation",
            "server-backed workstation save": "savePlcWorkstationConfig",
            "station pairing": "pairPlcWorkstation",
            "enabled toggle": 'name="enabled"',
            "live ACK gate": "标记真实 ACK 已验证",
            "effective enabled": "effective_enabled",
            "result register": 'name="result_register"',
            "optional output point": 'name="output_control_point"',
            "capture trigger toggle": 'name="capture_trigger_enabled"',
            "capture input register": 'name="capture_input_register"',
            "capture trigger value": 'name="capture_trigger_value"',
            "FX3GA profile": "mitsubishi_fx3ga_40mr",
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
            "capture edge requires reset": "先出现非",
            "capture missed is not queued": "本次不补拍",
            "capture diagnostics": "PLC 到位拍照状态",
            "automatic trigger never falls back": "禁止降级为普通图片检测",
            "atomic camera lock": "cameraCaptureLockRef",
            "executable edge reducer": "nextCaptureTriggerState",
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
    require_detection_analysis_boundary(server, {
        name: (ROOT / "local_inspection_service" / "detection" / name).read_text(encoding="utf-8")
        for name in ("analysis.py", "ai_analysis.py")
    })
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
            "capture input read": "readCaptureInput",
            "result write priority": "priorityOperations",
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
