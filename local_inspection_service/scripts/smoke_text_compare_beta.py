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
    assert "Ctrl+V" in frontend and "getUserMedia" in frontend and "track.stop()" in frontend
    assert "comparisonIdentityRef" in frontend and "disabled={mutation.isPending}" in frontend
    assert 'useState<"camera" | "image">("camera")' in frontend
    assert "上传实物图片" in frontend and "请先上传需要对比的实物图片" in frontend
    assert "text-compare-lightbox" in frontend and "zoomScale" in frontend and "点击放大查看" in frontend
    # Standard-library navigation and inspection must remain a real master/detail
    # workflow instead of growing another inline form inside the comparison bench.
    assert 'className="text-standard-thumbnail"' in frontend and "openZoom(asset.content_url" in frontend
    assert 'aria-expanded={expanded}' in frontend and 'data-testid="standard-order-detail"' in frontend
    assert 'aria-labelledby="text-standard-import-title"' in frontend and 'aria-label="返回标准库"' in frontend
    assert 'aria-labelledby="text-standard-manager-title"' in frontend and 'aria-label="返回订单"' in frontend
    assert 'role="dialog"' in frontend and 'aria-modal="true"' in frontend
    assert 'role="tab"' in frontend and 'role="tabpanel"' in frontend and 'event.key !== "Escape"' in frontend
    assert 'data-testid={managing ? "standard-manager-assets" : "standard-library-assets"}' in frontend
    assert "查看第 ${asset.ordinal} 张标准大图" in frontend and "第 ${asset.ordinal} 张标准缩略图" in frontend
    assert "setShowImport(true)" in frontend and "setShowManager(true)" in frontend
    # A local reference and a library asset are mutually exclusive. Every order,
    # mode or reference change must clear stale results and comparison identity.
    assert "const resetComparison" in frontend and "comparisonIdentityRef.current = null" in frontend
    assert 'setSelectedAssetId(""); setReference(file);' in frontend
    assert "function isActiveAsset" in frontend and 'asset.status === "needs_confirmation" ? "confirm"' in frontend
    assert "target?.closest(\"input, textarea, [contenteditable='true']\")" in frontend
    assert 'setSelectedStandardId(""); setSelectedAssetId(""); setShowManager(false); setShowImport(false); resetComparison({ clearReference: true, clearCaptured: true });' in frontend
    assert 'standardQuery.data?.status !== "confirmed"' in frontend
    assert "这个订单还没有启用" in frontend
    # Logical standards remain manageable after confirmation, while the backend
    # records immutable revisions and only soft-removes their assets.
    assert "addTextInspectionStandardAsset" in frontend
    assert 'action: asset.status === "excluded" ? "restore" : asset.status === "needs_confirmation" ? "confirm" : "remove"' in frontend
    assert "添加到标准" in frontend and "移除" in frontend and "恢复" in frontend
    assert "standard_revision_id" in source and "standard_revision_number" in source
    assert '"revisions": "text_inspection_standard_revisions"' in source
    assert "仅辅助检查文字" not in frontend and "颜色、材质与印刷质量仍需肉眼确认" not in frontend
    shell = (APP_DIR / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    assert "包材文字检验（旧版）" not in shell
    assert 'task_kind: "incoming_material_text"' not in shell
    print("text compare beta smoke: PASS")

if __name__ == "__main__":
    main()
