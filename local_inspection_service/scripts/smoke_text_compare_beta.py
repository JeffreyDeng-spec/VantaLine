from __future__ import annotations
import sys
from pathlib import Path
import cv2
import numpy as np

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from local_inspection_service import text_compare_beta as beta
from local_inspection_service.incoming_text_inspection import TextObservation

def observation(text: str, confidence: float = .99, y: int = 80) -> TextObservation:
    return TextObservation(text=text, confidence=confidence, polygon=((60,y),(520,y),(520,y+50),(60,y+50)))

def run(left, right, *, aligned=True):
    image = np.full((800, 1200, 3), 255, np.uint8)
    calls = iter([left, right])
    original_quality, original_rectify = beta.assess_image_quality, beta.rectify_label
    beta.assess_image_quality = lambda _: {"accepted": True, "reasons": []}
    beta.rectify_label = lambda captured, size: (captured.copy(), {"accepted": aligned})
    try:
        return beta.compare_images(image, image.copy(), "cmp_smoke_123", lambda _: next(calls))
    finally:
        beta.assess_image_quality, beta.rectify_label = original_quality, original_rectify

def main():
    assert run([observation("MODEL: PPLBP-2020")], [observation("MODEL: PPLBP-2020")])["decision"] == "MATCH"
    mismatch = run([observation("NO. 0-560/min")], [observation("No. 0-560/min")])
    assert mismatch["decision"] == "DIFFERENCES"
    assert mismatch["differences"][0]["reference_text"] == "NO. 0-560/min"
    assert mismatch["differences"][0]["region_normalized"]
    assert run([observation("MODEL: PPLBP-2020")], [observation("MODEL: PPLBP-2020", .72)])["decision"] == "REVIEW_REQUIRED"
    assert run([observation("MODEL")], [observation("MODEL")], aligned=False)["decision"] == "REVIEW_REQUIRED"
    source = (APP_DIR / "server.py").read_text(encoding="utf-8")
    assert '@app.post("/api/text-compare-beta/analyze")' in source
    assert '@app.post("/api/incoming-text/tasks/{task_id}/inspect")' in source
    assert '@app.post("/api/incoming-text/inspections/{inspection_id}/review")' in source
    frontend = (APP_DIR / "frontend" / "src" / "features" / "text-compare" / "TextCompareBetaPage.tsx").read_text(encoding="utf-8")
    styles = (APP_DIR / "frontend" / "src" / "styles" / "global.css").read_text(encoding="utf-8")
    assert "getUserMedia" in frontend and "track.stop()" in frontend
    assert "comparisonIdentityRef" in frontend and "disabled={mutation.isPending}" in frontend
    assert 'useState<"camera" | "image">("camera")' in frontend
    assert 'const IMAGE_ACCEPT = "image/*' in frontend
    assert "ACCEPTED_TYPES" not in frontend and "仅支持 PNG、JPG 或 WEBP 图片。" not in frontend
    assert "支持常见图片格式" in frontend
    assert "上传实物图片" in frontend and "请先上传需要对比的实物图片" in frontend
    assert "text-compare-lightbox" in frontend and "zoomScale" in frontend and "查看大图" in frontend
    # Standard-library navigation and inspection stays in the order detail: users
    # should not have to enter a second manager dialog to edit the same standard.
    assert 'className="text-standard-thumbnail"' in frontend and "openZoom(asset.content_url" in frontend
    assert 'aria-expanded={expanded}' in frontend and 'data-testid="standard-order-detail"' in frontend
    assert 'aria-labelledby="text-standard-import-title"' in frontend and 'aria-label="返回标准库"' in frontend
    assert 'role="dialog"' in frontend and 'aria-modal="true"' in frontend
    assert 'role="tab"' in frontend and 'role="tabpanel"' in frontend and 'event.key !== "Escape"' in frontend
    assert 'data-testid="standard-library-assets"' in frontend
    assert "查看第 ${asset.ordinal} 张标准大图" in frontend and "第 ${asset.ordinal} 张标准缩略图" in frontend
    assert 'className={`text-standard-asset-card ${selected ? "selected" : ""}' in frontend
    assert 'aria-pressed={selectable ? selected : undefined}' in frontend
    assert 'selectable ? chooseAsset(asset)' in frontend and "已选标准" in frontend and "点击选中" in frontend
    assert 'className={mode === "label" ? "text-compare-workbench" : ""}' in frontend
    assert 'className="text-compare-compact-topbar"' in frontend
    assert "100dvh" in styles and "max-height: 800px" in styles
    assert ".text-compare-workbench .text-compare-actual-panel .text-compare-stage" in styles
    assert "setShowImport(true)" in frontend
    assert "showManager" not in frontend and "管理标准" not in frontend
    # Label comparison accepts only an enabled gallery asset as its standard.
    # Changing that selection clears stale output but preserves the actual image.
    assert "const resetComparison" in frontend and "comparisonIdentityRef.current = null" in frontend
    assert 'resetComparison();\n    setSelectedAssetId(asset.id);' in frontend
    assert 'setSelectedStandardId(nextId); setSelectedAssetId(""); setAssetUploadFile(null);\n    resetComparison();' in frontend
    assert "standardAssetId: selectedAsset.id" in frontend
    assert 'form.set("standard_asset_id", selectedAsset.id)' in frontend
    assert "analyzeTextCompareBeta" not in frontend and "replaceReference" not in frontend
    assert 'ariaLabel="拖拽或选择标准图片"' not in frontend
    assert "请先在左侧订单画廊中选择一张已启用的标签图片" in frontend
    assert "function isActiveAsset" in frontend and 'asset.status === "needs_confirmation" ? "confirm"' in frontend
    assert 'setSelectedStandardId(""); setSelectedAssetId(""); setShowImport(false); resetComparison({ clearCaptured: true });' in frontend
    assert 'standardQuery.data?.status !== "confirmed"' in frontend
    assert "这个订单还没有启用" in frontend
    # Logical standards remain manageable after confirmation, while the backend
    # records immutable revisions and only soft-removes their assets.
    assert "addTextInspectionStandardAsset" in frontend
    assert 'action: asset.status === "excluded" ? "restore" : asset.status === "needs_confirmation" ? "confirm" : "remove"' in frontend
    assert "添加到标准" in frontend and "停用" in frontend and "启用" in frontend
    assert "standard_revision_id" in source and "standard_revision_number" in source
    assert '"revisions": "text_inspection_standard_revisions"' in source
    assert "仅辅助检查文字" not in frontend and "颜色、材质与印刷质量仍需肉眼确认" not in frontend
    assert '<details className="text-compare-raw-output">' in frontend
    assert "Raw Output（调试信息）" in frontend and "默认折叠" in frontend
    assert "parsed_response" in frontend and "response_preview" in frontend and "normalized_response" in frontend
    assert "MAX_DIAGNOSTIC_OUTPUT_CHARS = 20_000" in frontend and "formatDiagnosticOutput" in frontend
    assert '.text-compare-raw-output[open] > summary svg' in styles
    shell = (APP_DIR / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    assert "包材文字检验（旧版）" not in shell
    assert 'task_kind: "incoming_material_text"' not in shell
    print("text compare beta smoke: PASS")

if __name__ == "__main__":
    main()
