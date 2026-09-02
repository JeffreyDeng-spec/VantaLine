#!/usr/bin/env python3
"""Static contract for browser camera selection and accessible file drops."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "local_inspection_service" / "frontend" / "src"


def require(text: str, snippets: dict[str, str], surface: str) -> None:
    missing = [label for label, snippet in snippets.items() if snippet not in text]
    if missing:
        raise AssertionError(f"missing {surface} contract: " + ", ".join(missing))


def main() -> None:
    drop_zone_path = FRONTEND / "components" / "FileDropZone.tsx"
    drop_zone = drop_zone_path.read_text(encoding="utf-8")
    require(
        drop_zone,
        {
            "shared accept filtering": "fileMatchesAccept(file, accept)",
            "testable accept export": "export function fileMatchesAccept",
            "same chooser and drop selection path": "const selectFiles = (incoming: File[])",
            "single-file bound": "accepted.slice(0, 1)",
            "multi-file preservation": "multiple ? accepted",
            "disabled selection guard": "if (disabled) return",
            "keyboard button role": 'role="button"',
            "stable drop marker": 'data-file-drop-zone="true"',
            "disabled focus removal": "tabIndex={disabled ? -1 : 0}",
            "keyboard enter": 'event.key !== "Enter"',
            "keyboard space": 'event.key !== " "',
            "drag enter": "onDragEnter=",
            "drag over": "onDragOver=",
            "drag leave": "onDragLeave=",
            "drop files": "Array.from(event.dataTransfer.files || [])",
            "native accept": "accept={accept}",
            "native multiple": "multiple={multiple}",
            "native disabled": "disabled={disabled}",
            "reselect same file": 'event.currentTarget.value = ""',
            "visible rejection": 'role="alert"',
        },
        "file drop zone",
    )

    upload_surfaces = {
        "accessory library": FRONTEND / "features" / "accessories" / "AccessoriesPage.tsx",
        "detection workbench": FRONTEND / "features" / "detection" / "DetectionWorkbenchPage.tsx",
        "legacy text reference": FRONTEND / "features" / "incoming-text" / "IncomingTextTaskPage.tsx",
        "locate anything": FRONTEND / "features" / "locate" / "LocateAnythingPage.tsx",
        "training pipeline": FRONTEND / "features" / "pipeline" / "TrainingPipelinePage.tsx",
        "label sheet": FRONTEND / "features" / "label" / "LabelSheetPage.tsx",
        "text comparison": FRONTEND / "features" / "text-compare" / "TextCompareBetaPage.tsx",
    }
    for label, path in upload_surfaces.items():
        source = path.read_text(encoding="utf-8")
        require(
            source,
            {
                "shared component import": 'components/FileDropZone"',
                "drop zone usage": "<FileDropZone",
                "explicit accept contract": "accept=",
                "file callback": "onFiles=",
            },
            label,
        )

    direct_inputs: dict[str, int] = {}
    for path in FRONTEND.rglob("*.tsx"):
        if path == drop_zone_path:
            continue
        count = path.read_text(encoding="utf-8").count('type="file"')
        if count:
            direct_inputs[str(path.relative_to(FRONTEND))] = count
    if direct_inputs:
        raise AssertionError(f"unexpected file inputs outside shared drag/drop contract: {direct_inputs}")

    text_compare = upload_surfaces["text comparison"].read_text(encoding="utf-8")
    require(
        text_compare,
        {
            "standard image drop": 'ariaLabel="拖拽或选择标准图片"',
            "actual image drop": 'ariaLabel="拖拽或选择实物图片"',
            "standard image validation": "replaceReference(file)",
            "actual image validation": "replaceCaptured(file)",
            "camera enumeration": "navigator.mediaDevices?.enumerateDevices",
            "video-only devices": 'device.kind === "videoinput"',
            "selected exact device": "deviceId: { exact: deviceId }",
            "actual device reconciliation": "getSettings().deviceId",
            "request generation": "cameraRequestRef.current",
            "stale stream rejection": "requestId !== cameraRequestRef.current",
            "stale track stop": "stream.getTracks().forEach((track) => track.stop())",
            "device change listener": 'addEventListener?.("devicechange"',
            "device change cleanup": 'removeEventListener?.("devicechange"',
            "permission denial": 'cameraFailure.name === "NotAllowedError"',
            "missing selected device": 'cameraFailure.name === "OverconstrainedError"',
            "removed device": 'cameraFailure.name === "NotFoundError"',
            "no-device fallback": "未检测到可用摄像头",
            "label fallback": "摄像头 ${index + 1}",
            "accessible selector": 'aria-label="选择摄像头设备"',
            "selector busy guard": "disabled={cameraStarting || mutation.isPending || !cameraDevices.length}",
            "selection clears capture": "setSelectedDeviceId(deviceId); clearCaptured(); void startCamera(deviceId)",
            "capture busy guard": "disabled={mutation.isPending || cameraStarting}",
            "image mode cancels camera": "++cameraRequestRef.current;",
        },
        "text comparison camera picker",
    )
    device_change = text_compare[
        text_compare.index("const handleDeviceChange"):
        text_compare.index('addEventListener?.("devicechange"')
    ]
    if "!streamRef.current" in device_change:
        raise AssertionError("devicechange must recover a device lost while getUserMedia is still pending")
    require(
        device_change,
        {
            "active surface guard": "cameraSurfaceActiveRef.current",
            "live track check": 'track.readyState === "live"',
            "available-device fallback": "startCamera(next.selectedId)",
        },
        "camera devicechange fallback",
    )

    print("smoke_frontend_media_inputs: ok")


if __name__ == "__main__":
    main()
