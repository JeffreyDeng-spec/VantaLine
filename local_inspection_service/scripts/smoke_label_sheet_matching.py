#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_inspection_service.server import collect_label_sheet_references, match_label_sheet_to_references


def make_label(text: str, color: tuple[int, int, int]) -> np.ndarray:
    image = np.full((120, 260, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (6, 6), (253, 113), (20, 20, 20), 3, cv2.LINE_AA)
    cv2.rectangle(image, (18, 18), (72, 102), color, -1, cv2.LINE_AA)
    cv2.putText(image, text, (88, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(image, "LOT 2026", (88, 88), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (70, 70, 70), 1, cv2.LINE_AA)
    return image


def make_sheet(label: np.ndarray) -> np.ndarray:
    cell_h, cell_w = label.shape[:2]
    sheet = np.full((cell_h * 3 + 56, cell_w * 2 + 48, 3), 245, dtype=np.uint8)
    for row in range(3):
        for col in range(2):
            y = 18 + row * (cell_h + 14)
            x = 16 + col * (cell_w + 16)
            sheet[y : y + cell_h, x : x + cell_w] = label
    return sheet


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp_raw:
        tmp = Path(tmp_raw)
        label = make_label("QA LABEL A", (40, 160, 80))
        label_b = make_label("QA LABEL B", (40, 160, 80))
        box = make_label("BOX PANEL", (170, 80, 40))
        label_path = tmp / "qa_label_reference.png"
        box_path = tmp / "shipping_box.png"
        cv2.imwrite(str(label_path), label)
        cv2.imwrite(str(box_path), box)

        config = {
            "accessories": [
                {
                    "id": "acc_label",
                    "class_id": 101,
                    "name": "QA label 标签",
                    "material_type": "text",
                    "source_files": [str(label_path)],
                },
                {
                    "id": "acc_box",
                    "class_id": 102,
                    "name": "包装盒 box",
                    "material_type": "object",
                    "source_files": [str(box_path)],
                },
            ]
        }
        references, stats = collect_label_sheet_references(config, write_previews=False)
        assert stats["kept_count"] == 1, stats
        assert stats["filtered_count"] == 1, stats
        assert references[0]["accessory_id"] == "acc_label", references

        result = match_label_sheet_to_references(
            make_sheet(label),
            references,
            request_id="smoke_label_sheet",
            output_dir=tmp / "outputs",
            doc_filter_stats=stats,
        )
        assert result["status"] == "matched", result
        assert result["matched_reference_id"].startswith("acc_label"), result
        assert float(result["score"]) >= 0.78, result

        changed_text = match_label_sheet_to_references(
            make_sheet(label_b),
            references,
            request_id="smoke_label_sheet_changed_text",
            output_dir=tmp / "outputs",
            doc_filter_stats=stats,
        )
        assert changed_text["status"] == "unclear", changed_text
        assert changed_text["matched_reference_id"] == "", changed_text
        assert changed_text["low_confidence_reason"] == "strict comparison did not pass", changed_text
        changed_metrics = changed_text["candidates"][0]["metrics"]
        assert changed_metrics["status"] in {"fail", "review"}, changed_text
        assert not changed_metrics["auto_match_eligible"], changed_text
        assert float(changed_metrics["template_similarity"]) > float(changed_metrics["strict_score"]), changed_text

        box_text = match_label_sheet_to_references(
            make_sheet(box),
            references,
            request_id="smoke_label_sheet_box_text",
            output_dir=tmp / "outputs",
            doc_filter_stats=stats,
        )
        assert box_text["status"] == "unclear", box_text
        assert box_text["matched_reference_id"] == "", box_text
        assert box_text["low_confidence_reason"] == "strict comparison did not pass", box_text
        box_metrics = box_text["candidates"][0]["metrics"]
        assert box_metrics["status"] == "fail", box_text
        assert not box_metrics["auto_match_eligible"], box_text

    print("label sheet smoke passed")


if __name__ == "__main__":
    main()
