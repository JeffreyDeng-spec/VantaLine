#!/usr/bin/env python3
"""Deterministic contract smoke for package-material text inspection."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np


APP_DIR = Path(__file__).resolve().parents[1]
ROOT = APP_DIR.parent
sys.path.insert(0, str(ROOT))

from local_inspection_service.incoming_text_inspection import (  # noqa: E402
    FAIL,
    PASS,
    REVIEW_REQUIRED,
    IncomingTextValidationError,
    TextObservation,
    apply_commissioning_gate,
    assess_image_quality,
    decide_inspection,
    normalize_field_rules,
)
from local_inspection_service.storage.postgres_schema import postgres_ddl  # noqa: E402


def rule(expected: str, *, importance: str = "critical", mode: str = "exact", case_sensitive: bool = True):
    return {
        "field_id": "model",
        "name": "产品型号",
        "region_normalized": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.2},
        "expected_text": expected,
        "match_mode": mode,
        "importance": importance,
        "case_sensitive": case_sensitive,
    }


def decision(rule_value, observation, *, similarity=0.95):
    rules = normalize_field_rules([rule_value])
    return decide_inspection(
        rules,
        {"model": observation},
        quality={"accepted": True, "reasons": []},
        alignment={"accepted": True},
        visual_similarities={"model": similarity},
    )


def main() -> None:
    correct = TextObservation("MODEL: PPLBP-2020", 0.99, corroborated=True)
    assert decision(rule("MODEL: PPLBP-2020"), correct)["decision"] == PASS
    whitespace_rule = rule("MODEL: PPLBP-2020")
    whitespace_rule["ignore_whitespace"] = True
    no_layout_space = TextObservation("MODEL:PPLBP-2020", 0.99, corroborated=True)
    assert decision(whitespace_rule, no_layout_space)["decision"] == PASS
    wrong_punctuation = TextObservation("MODEL-PPLBP-2020", 0.99, corroborated=True)
    assert decision(whitespace_rule, wrong_punctuation)["decision"] == FAIL
    gated = apply_commissioning_gate(
        decision(rule("MODEL: PPLBP-2020"), correct), automatic_decisions_verified=False
    )
    assert gated["decision"] == REVIEW_REQUIRED
    assert gated["candidate_decision"] == PASS
    assert "commissioning_not_verified" in gated["reasons"]

    lower_o = TextObservation("20V Max o-560/min", 0.99, corroborated=True)
    assert decision(rule("20V Max O-560/min"), lower_o)["decision"] == FAIL

    missing = TextObservation("", 1.0, corroborated=True)
    assert decision(rule("MODEL: PPLBP-2020"), missing)["decision"] == FAIL

    punctuation = TextObservation("MODEL PPLBP–2020", 0.99, corroborated=True)
    assert decision(rule("MODEL: PPLBP-2020"), punctuation)["decision"] == FAIL

    normal_rule = rule("WARNING: Read the manual.", importance="normal")
    normal_rule["field_id"] = "warning"
    mixed_rules = normalize_field_rules([rule("MODEL: PPLBP-2020"), normal_rule])
    normal_result = decide_inspection(
        mixed_rules,
        {
            "model": correct,
            "warning": TextObservation("Warning: read manual", 0.99, corroborated=True),
        },
        quality={"accepted": True, "reasons": []},
        alignment={"accepted": True},
        visual_similarities={"model": 0.95, "warning": 0.95},
    )
    assert normal_result["decision"] == REVIEW_REQUIRED

    low_confidence = TextObservation("MODEL: PPLBP-2020", 0.72, corroborated=True)
    assert decision(rule("MODEL: PPLBP-2020"), low_confidence)["decision"] == REVIEW_REQUIRED

    single_pass = TextObservation("MODEL: PPLBP-2020", 0.99, corroborated=False)
    assert decision(rule("MODEL: PPLBP-2020"), single_pass)["decision"] == REVIEW_REQUIRED

    regex_rule = rule(r"LOT-[0-9]{8}", mode="regex", importance="normal")
    regex_rule["field_id"] = "lot"
    regex_rules = normalize_field_rules([rule("MODEL: PPLBP-2020"), regex_rule])
    regex_result = decide_inspection(
        regex_rules,
        {"model": correct, "lot": TextObservation("LOT-20260806", 0.99, corroborated=True)},
        quality={"accepted": True, "reasons": []},
        alignment={"accepted": True},
        visual_similarities={"model": 0.95, "lot": 0.95},
    )
    assert regex_result["decision"] == PASS

    try:
        normalize_field_rules([rule("(a|aa)+", mode="regex")])
        raise AssertionError("unsafe alternation regex accepted")
    except IncomingTextValidationError:
        pass

    blurred = np.full((800, 1200, 3), 128, dtype=np.uint8)
    assert not assess_image_quality(blurred)["accepted"]
    sharp = np.full((800, 1200, 3), 150, dtype=np.uint8)
    cv2.putText(sharp, "MODEL: PPLBP-2020", (100, 400), cv2.FONT_HERSHEY_SIMPLEX, 3, (245, 245, 245), 7)
    assert assess_image_quality(sharp)["accepted"]

    ddl = postgres_ddl()
    assert "incoming_text_reference_versions" in ddl
    assert "incoming_text_inspections" in ddl
    assert 'UNIQUE ("owner_user_id", "task_id", "capture_id")' in ddl
    assert "uq_incoming_text_reference_active" in ddl

    server_text = (APP_DIR / "server.py").read_text(encoding="utf-8")
    assert 'task_kind = str(request.task_kind or "product_inspection")' in server_text
    assert 'detection_method = "label_text_compare"' in server_text
    assert "def _duplicate_incoming_capture" in server_text
    assert "review_incoming_text_inspection" in server_text
    assert 'text_detection_model_name="PP-OCRv6_medium_det"' in server_text
    assert 'text_recognition_model_name="PP-OCRv6_medium_rec"' in server_text
    assert "def incoming_text_corroboration_observations" in server_text
    assert "def list_incoming_text_inspectors" in server_text
    assert "def require_incoming_text_storage_capacity" in server_text
    assert "VANTALINE_INCOMING_TEXT_MIN_FREE_BYTES" in server_text
    assert "normalize_ocr_text" not in server_text[server_text.index("# Package-material incoming text inspection"):]

    frontend_text = (APP_DIR / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    assert "包材文字检验" in frontend_text
    assert "uploadIncomingTextReference" in frontend_text
    assert "inspection_user_ids: selectedInspectorIds" in frontend_text
    print("incoming text inspection smoke: PASS")


if __name__ == "__main__":
    main()
