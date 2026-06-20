#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "local_inspection_service" / "static"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    app_js = (STATIC / "app.js").read_text(encoding="utf-8")
    css = (STATIC / "styles.css").read_text(encoding="utf-8")

    nav_views = re.findall(r'<button class="nav-item[^"]*" data-view="([^"]+)"', html)
    for view in nav_views:
        require(f'id="{view}View"' in html, f"missing view section for nav item {view}")

    locate_start = html.index('<section id="locateAnythingView"')
    locate_end = html.index('<section id="rulesView"', locate_start)
    locate_html = html[locate_start:locate_end]

    require("LocateAnything工作台" in locate_html, "LocateAnything tab title missing")
    require("启动本地模型" in locate_html, "runtime start action missing")
    require("连续检测" in locate_html and "停止" in locate_html, "camera loop controls missing")
    require("通过" in app_js and "不通过" in app_js, "PASS/FAIL result language missing")
    require("Raw Answer" not in locate_html, "raw model answer must not be in normal UI")
    require("Generation Mode" not in locate_html, "generation mode must be hidden from normal UI")
    require("NVIDIA non-commercial" in locate_html, "required NVIDIA non-commercial warning missing")
    require("commercial use is not permitted" in locate_html, "commercial-use restriction copy missing")
    require("Gemini" not in locate_html, "LocateAnything view must not mention Gemini")

    required_ids = [
        "locateStatusBadge",
        "startLocateRuntime",
        "checkLocateStatus",
        "locateStatusText",
        "locateCameraMenu",
        "locateCameraVideo",
        "locateSourceImage",
        "locateSourceEmpty",
        "locateCameraSampleSeconds",
        "refreshLocateCameras",
        "captureLocateFrame",
        "startLocateCameraLoop",
        "stopLocateCameraLoop",
        "locateImageFile",
        "runLocateImage",
        "toggleLocateRecipeDetails",
        "addLocateRecipeItem",
        "locateRecipeConfiguredCount",
        "locateRecipeEnabledCount",
        "locateRecipeExpectedTotal",
        "locateRecipePicker",
        "locateRecipeSearch",
        "locateRecipePickerList",
        "locateAccessoryList",
        "locateOverallResult",
        "locateResultStatus",
        "locateBoxCount",
        "locateFrameCount",
        "locateInspectionItems",
        "locatePreviewImage",
        "locateEmptyPreview",
        "locateLatencyText",
        "locateDiagnosticText",
        "locateEndpointUrl",
        "saveLocateConfig",
        "locateMaxSide",
        "locateMaxTokens",
    ]
    for element_id in required_ids:
        require(f'id="{element_id}"' in locate_html, f"missing LocateAnything control #{element_id}")

    for endpoint in (
        "/api/locateanything/config",
        "/api/locateanything/status",
        "/api/locateanything/runtime/start",
        "/api/locateanything/accessories",
        "/api/locateanything/inspect",
    ):
        require(endpoint in app_js, f"missing frontend API wiring for {endpoint}")
    require("runLocateImage" in app_js, "image locate runner missing")
    require("startLocateCameraLoop" in app_js and "locateCameraLoop" in app_js, "camera loop runner missing")
    require("locateCameraSampleDelayMs" in app_js, "camera sample interval helper missing")
    require("setTimeout(locateCameraLoop, locateCameraSampleDelayMs())" in app_js, "camera loop must use low-frequency sampling delay")
    require("低频帧采样" in locate_html and "30 FPS" in locate_html, "low-frequency camera sampling copy missing")
    require('data-view="locateAnything"' in html, "sidebar nav item missing")
    require('data-view="inspect"' in html and 'data-view="aiInspect"' in html and 'data-view="labelSheet"' in html, "existing workbench nav items missing")
    require("function bindViews()" in app_js and "stopLocateCameraStream()" in app_js, "generic view switching cleanup missing")

    stale_ids = [
        "locateStatusPill",
        "locateBoxesTable",
        "locateBoxTable",
        "locateVideoSecond",
        "locateVideoFile",
        "locateVideoSampleSeconds",
        "runLocateVideoSample",
        "captureLocateCamera",
        "locatePrompt",
        "locatePromptTemplates",
        "locateRawAnswer",
        "locateSuitabilityText",
        'data-locate-mode="',
    ]
    for stale in stale_ids:
        require(stale not in locate_html, f"stale LocateAnything markup remains: {stale}")

    stale_js = [
        "LOCATEANYTHING_PROMPT_TEMPLATES",
        "LOCATE_PROMPT_TEMPLATES",
        "state.locateAnything.",
        "runLocateWithFile",
        "runLocateVideoSample",
        "/api/locateanything/locate",
    ]
    for stale in stale_js:
        require(stale not in app_js, f"stale LocateAnything JS remains: {stale}")

    for css_class in (
        ".hidden",
        ".locate-worker-grid",
        ".locate-recipe-summary",
        ".locate-recipe-picker",
        ".locate-picker-list",
        ".locate-rule-list",
        ".locate-overall",
        ".locate-result-grid",
        ".debug-pre",
    ):
        require(css_class in css, f"missing CSS class {css_class}")
    require(re.search(r"\.hidden\s*\{[^}]*display:\s*none\s*!important", css, re.S), "global .hidden must visually hide controls")
    require("repeat(auto-fit, minmax(118px, 1fr))" in css, "tablet sidebar nav must wrap instead of forcing horizontal overflow")
    require(re.search(r"\.locate-rule-list\s*\{[^}]*max-height:\s*318px", css, re.S), "LocateAnything recipe list must be bounded by default")
    require("function upsertLocateRule" in app_js and "function removeLocateRule" in app_js, "recipe add/remove state helpers missing")
    require("state.locateRecipeExpanded" in app_js and "state.locateRecipePickerOpen" in app_js, "recipe collapsed/picker state missing")

    print("locateanything frontend smoke passed")


if __name__ == "__main__":
    main()
