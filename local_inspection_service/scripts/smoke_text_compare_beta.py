from __future__ import annotations
import ast
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
    api_source = (APP_DIR / "text_inspection/beta_api.py").read_text(encoding="utf-8")
    assert '@app.post("/api/text-compare-beta/analyze")' in api_source
    assert 'from .text_inspection.beta_api import register as register_beta_comparison, BetaAccess' in source
    assert 'analyze_text_compare_beta = register_beta_comparison(' in source
    assert '@app.post("/api/incoming-text/tasks/{task_id}/inspect")' in source
    assert '@app.post("/api/incoming-text/inspections/{inspection_id}/review")' in source
    retired = (APP_DIR / "frontend/src/features/text-compare/TextCompareBetaPage.tsx").read_text()
    redirect = (APP_DIR / "frontend/src/features/label-inspection/LegacyManualRedirect.tsx").read_text()
    history = (APP_DIR / "frontend/src/features/label-inspection/ManualHistory.tsx").read_text()
    result = (APP_DIR / "frontend/src/features/text-compare/ComparisonResult.tsx").read_text()
    assert "LegacyManualRedirect" in retired and "getUserMedia" not in retired
    assert "legacy-manual:" in redirect and "/workspace/label-inspection" in redirect
    assert 'params.get("session_id")' in redirect and 'params.get("inspection_id")' in redirect
    assert "历史记录（只读）" in history and "原记录未保留实物照片" in history
    assert "has_photo" in history and "final_decision" in history
    comparison_source = (APP_DIR / "text_inspection/comparison_submission.py").read_text(encoding="utf-8")
    assert "standard_revision_id" in comparison_source and "standard_revision_number" in comparison_source
    tree = ast.parse(source)
    assert any(isinstance(node, ast.ImportFrom) and node.module == "text_inspection.comparison_submission"
               and any(alias.name == "ComparisonSubmission" for alias in node.names) for node in tree.body)
    assignments = {target.id: node.value for node in tree.body if isinstance(node, ast.Assign)
                   for target in node.targets if isinstance(target, ast.Name)}
    composition = assignments["_comparison_submission"]
    assert isinstance(composition, ast.Call) and isinstance(composition.func, ast.Name) and composition.func.id == "ComparisonSubmission"
    assert ast.dump(assignments["_inspection_routes"]) == ast.dump(ast.parse(
        "register_text_inspections(app, _comparison_submission, _inspection_reviews, _inspection_access)", mode="eval").body)
    assert ast.dump(assignments["compare_text_inspection_label"]) == ast.dump(ast.parse(
        "_inspection_routes.compare_text_inspection_label", mode="eval").body)
    record_source = (APP_DIR / "text_inspection/record_store.py").read_text(encoding="utf-8")
    assert '"revisions": "text_inspection_standard_revisions"' in record_source
    assert "tables=lambda: TEXT_INSPECTION_TABLES," in source
    # The historical result reader still renders bounded original diagnostics.
    assert "parsed_response" in result and "response_preview" in result and "normalized_response" in result
    assert "MAX_DIAGNOSTIC_OUTPUT_CHARS = 20_000" in result and "formatDiagnosticOutput" in result
    # Current upload/camera/grid coverage lives in smoke_frontend_media_inputs and
    # test_label_workspace_ui; no test should require resurrecting the retired UI.
    shell = (APP_DIR / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    assert "包材文字检验（旧版）" not in shell
    assert 'task_kind: "incoming_material_text"' not in shell
    print("text compare beta smoke: PASS")

if __name__ == "__main__":
    main()
