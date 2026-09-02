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
    shell = (APP_DIR / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    assert "包材文字检验（旧版）" not in shell
    assert 'task_kind: "incoming_material_text"' not in shell
    print("text compare beta smoke: PASS")

if __name__ == "__main__":
    main()
