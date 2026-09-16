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
        "text comparison": FRONTEND / "features" / "label-inspection" / "LabelWorkspace.tsx",
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
            "unified PDF upload": 'accept=".doc,.docx,.pdf,.jpg,.jpeg,.png,.webp,.bmp"',
            "camera enumeration": "navigator.mediaDevices.enumerateDevices()",
            "video-only devices": 'x.kind === "videoinput"',
            "selected exact device": "deviceId: { exact: device }",
            "request generation": "const token = generation.current",
            "stale stream rejection": "token !== generation.current",
            "stale track stop": "s.getTracks().forEach((t) => t.stop())",
            "hidden window stop": "if (document.hidden) stop()",
            "read-only stop": "if (readOnly || disabled) stop()",
            "removed device": "摄像头已断开，请重新开启",
            "accessible selector": 'aria-label="选择摄像头"',
            "capture generation guard": "blob && token === generation.current",
            "selection from grid": "setSelected(a.id)",
        },
        "unified comparison camera and PDF picker",
    )
    retired = (FRONTEND / "features" / "text-compare" / "TextCompareBetaPage.tsx").read_text()
    require(retired, {"read-only redirect": "LegacyManualRedirect"}, "retired manual entry")

    print("smoke_frontend_media_inputs: ok")


if __name__ == "__main__":
    main()
