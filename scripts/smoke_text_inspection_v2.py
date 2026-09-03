"""Focused, dependency-light checks for the text inspection v2 contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.text_inspection_v2 import (
    UnsafeDocument,
    _classify,
    extract_docx_candidates,
    inspect_pdf,
    normalize_vlm_provider_result,
    validate_vlm_result,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--customer-docx", type=Path)
    args = parser.parse_args()

    assert _classify("1.标贴", 800, 300)[:2] == ("candidate", "label")
    assert _classify("8.彩盒展开稿", 800, 300)[0] == "excluded"
    assert _classify("标贴粘贴位置", 800, 300)[:2] == ("excluded", "placement_diagram")
    checked = validate_vlm_result({"decision": "DIFFERENCES", "message": "case", "differences": [{"type": "case", "reference_text": "O", "actual_text": "o", "confidence": 0.99, "box": [0.1, 0.2, 0.3, 0.4]}]})
    assert checked["differences"][0]["reference_text"] == "O"
    qwen = normalize_vlm_provider_result(
        {
            "decision": "DIFFERENCES",
            "differences": [
                {"type": "text_mismatch", "reference_text": "MODEL A", "actual_text": "", "confidence": 100, "box": [0, 100, 1000, 250]},
                {"type": "text_mismatch", "reference_text": "40Wh", "actual_text": "40Wh", "confidence": 1.0, "box": [200, 300, 400, 350]},
            ],
        },
        "qwen",
    )
    qwen_checked = validate_vlm_result(qwen)
    assert qwen_checked["differences"] == [{
        "id": "diff-1", "type": "missing", "reference_text": "MODEL A", "actual_text": "",
        "confidence": 1.0, "box": [0.0, 0.1, 1.0, 0.25],
    }]
    unchanged_only = normalize_vlm_provider_result(
        {"decision": "DIFFERENCES", "differences": [{"type": "text_mismatch", "reference_text": "same", "actual_text": "same", "confidence": 1, "box": [0, 0, 1000, 1000]}]},
        "qwen",
    )
    assert unchanged_only["decision"] == "REVIEW_REQUIRED" and unchanged_only["differences"] == []
    for unsafe in (b"not a docx", b"not a pdf"):
        try:
            extract_docx_candidates(unsafe) if unsafe == b"not a docx" else inspect_pdf(unsafe)
        except UnsafeDocument:
            pass
        else:
            raise AssertionError("unsafe document accepted")

    if args.customer_docx:
        metadata, _ = extract_docx_candidates(args.customer_docx.read_bytes())
        by_source = {Path(item["source_part"]).name: item for item in metadata}
        for index in range(1, 7):
            item = next(value for name, value in by_source.items() if name.startswith(f"image{index}."))
            assert item["status"] == "candidate", (index, item)
        for index in range(7, 19):
            item = next(value for name, value in by_source.items() if name.startswith(f"image{index}."))
            assert item["status"] == "excluded", (index, item)

    print("text inspection v2 smoke checks passed")


if __name__ == "__main__":
    main()
