#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import cv2

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from local_inspection_service import server  # noqa: E402


TARGET_ACCURACY = 0.95
DEFAULT_MIN_CASES = 20
KNOWN_RECORD_ID = "analysis_1781453854_e070f6382c"
KNOWN_IMAGE_NAME = "1781453849_491978d6_Weixin_Image_20260613223549_487_231.jpg"
LOCAL_EARPODS_IMAGE = (
    REPO_ROOT
    / "local_inspection_service"
    / "data"
    / "worker_image_jobs"
    / "image_job_28uyzq7c"
    / "inputs"
    / "02_1781365211_909f647b_Weixin_Image_20260613223549_487_231.jpg"
)


def image_size(path: Path | None, fallback: dict[str, int] | None = None) -> dict[str, int]:
    if path and path.exists():
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is not None:
            height, width = image.shape[:2]
            return {"width": int(width), "height": int(height)}
    return fallback or {"width": 1000, "height": 1000}


def charger_profile() -> dict[str, Any]:
    return server.normalize_accessory_locateanything_profile(
        {},
        {
            "id": "acc_charger_eval",
            "name": "充电器",
            "material_type": "object",
            "ai_profile": {
                "accessory_id": "acc_charger_eval",
                "name": "充电器",
                "material_type": "object",
                "description": "white charger adapter or charging cable accessory",
                "visual_signature": "real physical charger, adapter brick, plug, or cable",
                "negative_cues": ["printed cable image", "earphone package"],
            },
        },
    )


def document_profile() -> dict[str, Any]:
    return server.normalize_accessory_locateanything_profile(
        {},
        {
            "id": "acc_manual_eval",
            "name": "说明书",
            "material_type": "text",
            "ai_profile": {
                "accessory_id": "acc_manual_eval",
                "name": "说明书",
                "material_type": "text",
                "description": "flat printed manual document",
                "visual_signature": "complete paper sheet with printed instructions",
            },
        },
    )


def eval_cases() -> list[dict[str, Any]]:
    charger = charger_profile()
    manual = document_profile()
    local_case_image = LOCAL_EARPODS_IMAGE if LOCAL_EARPODS_IMAGE.exists() else None
    return [
        {
            "id": "known_earpods_package_charger_false_positive_replay",
            "record_id": KNOWN_RECORD_ID,
            "image_filename": KNOWN_IMAGE_NAME,
            "local_image_path": str(local_case_image or ""),
            "task_type": "data_analysis_comparison",
            "expected_accept": False,
            "rule": {
                "id": "analysis:acc_charger_eval",
                "source": "data_analysis",
                "task_type": "data_analysis_comparison",
                "label": "充电器",
                "display_label": "充电器",
                "material_type": "object",
                "visual_prompt": "real physical charger, adapter brick, plug, or cable",
                "target_scope": charger["target_scope"],
                "locateanything_profile": charger,
                "reject_cues": charger["reject_cues"],
                "packaging_exclusions": charger["packaging_exclusions"],
                "subpart_text_logo_exclusions": charger["subpart_text_logo_exclusions"],
                "count_strategy": charger["count_strategy"],
                "box_constraints": charger["box_constraints"],
                "expected_present": False,
                "expected_count": 0,
            },
            "offline_raw_answer": "<ref>printed charger cable on package</ref><box><80><120><880><820></box>",
            "image_size": image_size(local_case_image, {"width": 3072, "height": 4096}),
        },
        {
            "id": "known_earpods_package_no_charger_box",
            "record_id": KNOWN_RECORD_ID,
            "image_filename": KNOWN_IMAGE_NAME,
            "local_image_path": str(local_case_image or ""),
            "task_type": "data_analysis_comparison",
            "expected_accept": True,
            "rule": {
                "id": "analysis:acc_charger_eval",
                "source": "data_analysis",
                "task_type": "data_analysis_comparison",
                "label": "充电器",
                "display_label": "充电器",
                "material_type": "object",
                "visual_prompt": "real physical charger, adapter brick, plug, or cable",
                "target_scope": charger["target_scope"],
                "locateanything_profile": charger,
                "reject_cues": charger["reject_cues"],
                "packaging_exclusions": charger["packaging_exclusions"],
                "subpart_text_logo_exclusions": charger["subpart_text_logo_exclusions"],
                "count_strategy": charger["count_strategy"],
                "box_constraints": charger["box_constraints"],
                "expected_present": False,
                "expected_count": 0,
            },
            "offline_raw_answer": "<ref>no accepted real charger visible</ref><box>None</box>",
            "image_size": image_size(local_case_image, {"width": 3072, "height": 4096}),
        },
        {
            "id": "known_earpods_package_physical_charger_false_positive_replay",
            "record_id": KNOWN_RECORD_ID,
            "image_filename": KNOWN_IMAGE_NAME,
            "local_image_path": str(local_case_image or ""),
            "task_type": "object_presence",
            "expected_accept": False,
            "rule": {
                "id": "accessory:acc_charger_eval",
                "source": "accessory",
                "task_type": "object_presence",
                "label": "充电器",
                "display_label": "充电器",
                "material_type": "object",
                "visual_prompt": "real physical charger, adapter brick, plug, or cable",
                "target_scope": charger["target_scope"],
                "locateanything_profile": charger,
                "reject_cues": charger["reject_cues"],
                "packaging_exclusions": charger["packaging_exclusions"],
                "subpart_text_logo_exclusions": charger["subpart_text_logo_exclusions"],
                "count_strategy": charger["count_strategy"],
                "box_constraints": charger["box_constraints"],
                "expected_present": True,
                "expected_count": 1,
            },
            "offline_raw_answer": "<ref>printed charger cable on package</ref><box><80><120><880><820></box>",
            "image_size": image_size(local_case_image, {"width": 3072, "height": 4096}),
        },
        {
            "id": "physical_charger_present_one_box",
            "task_type": "object_presence",
            "expected_accept": True,
            "rule": {
                "id": "accessory:acc_charger_eval",
                "source": "accessory",
                "task_type": "object_presence",
                "label": "充电器",
                "display_label": "充电器",
                "material_type": "object",
                "visual_prompt": "real white charger adapter",
                "target_scope": charger["target_scope"],
                "locateanything_profile": charger,
                "reject_cues": charger["reject_cues"],
                "packaging_exclusions": charger["packaging_exclusions"],
                "subpart_text_logo_exclusions": charger["subpart_text_logo_exclusions"],
                "count_strategy": charger["count_strategy"],
                "box_constraints": charger["box_constraints"],
                "expected_present": True,
                "expected_count": 1,
            },
            "offline_raw_answer": "<ref>real charger</ref><box><100><120><420><620></box>",
            "image_size": {"width": 1000, "height": 1000},
            "expected_boxes": [{"x1": 100, "y1": 120, "x2": 420, "y2": 620}],
            "min_iou": 0.5,
        },
        {
            "id": "document_manual_present_one_box",
            "task_type": "text_document",
            "expected_accept": True,
            "rule": {
                "id": "accessory:acc_manual_eval",
                "source": "accessory",
                "task_type": "text_document",
                "label": "说明书",
                "display_label": "说明书",
                "material_type": "text",
                "visual_prompt": "complete printed manual sheet",
                "target_scope": manual["target_scope"],
                "locateanything_profile": manual,
                "reject_cues": manual["reject_cues"],
                "packaging_exclusions": manual["packaging_exclusions"],
                "subpart_text_logo_exclusions": manual["subpart_text_logo_exclusions"],
                "count_strategy": manual["count_strategy"],
                "box_constraints": manual["box_constraints"],
                "expected_present": True,
                "expected_count": 1,
            },
            "offline_raw_answer": "<ref>manual sheet</ref><box><50><80><900><920></box>",
            "image_size": {"width": 1000, "height": 1000},
            "expected_boxes": [{"x1": 50, "y1": 80, "x2": 900, "y2": 920}],
            "min_iou": 0.5,
        },
        {
            "id": "object_count_mismatch_two_required_one_box",
            "task_type": "ai_detection",
            "expected_accept": False,
            "rule": {
                "id": "analysis:acc_charger_eval",
                "source": "ai_detection",
                "task_type": "ai_detection",
                "label": "充电器",
                "display_label": "充电器",
                "material_type": "object",
                "visual_prompt": "real charger adapter",
                "target_scope": charger["target_scope"],
                "locateanything_profile": charger,
                "reject_cues": charger["reject_cues"],
                "packaging_exclusions": charger["packaging_exclusions"],
                "subpart_text_logo_exclusions": charger["subpart_text_logo_exclusions"],
                "count_strategy": charger["count_strategy"],
                "box_constraints": charger["box_constraints"],
                "expected_present": True,
                "expected_count": 2,
            },
            "offline_raw_answer": "<ref>one charger</ref><box><100><120><420><620></box>",
            "image_size": {"width": 1000, "height": 1000},
        },
    ]


def live_raw_answer(case: dict[str, Any], endpoint_url: str, timeout_seconds: float, max_side: int, max_new_tokens: int) -> str:
    image_path = Path(str(case.get("local_image_path") or ""))
    if not image_path.exists():
        raise RuntimeError("case image is not available locally")
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("case image could not be decoded")
    sent = server.resize_bgr_max_side(image, max_side)
    ok, encoded = cv2.imencode(".jpg", sent, [int(cv2.IMWRITE_JPEG_QUALITY), server.LOCATEANYTHING_PROXY_IMAGE_QUALITY])
    if not ok:
        raise RuntimeError("case image could not be encoded")
    prompt = server.locateanything_prompt_for_rule(case["rule"])
    payload = server.post_locateanything_endpoint(
        endpoint_url,
        encoded.tobytes(),
        prompt=prompt,
        generation_mode="fast",
        max_new_tokens=max_new_tokens,
        timeout_seconds=timeout_seconds,
    )
    return server.extract_locateanything_answer(payload)


def localization_ok(case: dict[str, Any], boxes: list[dict[str, Any]]) -> bool | None:
    expected_boxes = case.get("expected_boxes") if isinstance(case.get("expected_boxes"), list) else []
    if not expected_boxes:
        return None
    min_iou = float(case.get("min_iou") or 0.5)
    if len(boxes) < len(expected_boxes):
        return False
    for expected in expected_boxes:
        if not any(server.locateanything_box_iou(expected, box) >= min_iou for box in boxes):
            return False
    return True


def run_eval(args: argparse.Namespace) -> dict[str, Any]:
    cases = eval_cases()
    results = []
    for case in cases:
        size = case.get("image_size") if isinstance(case.get("image_size"), dict) else {"width": 1000, "height": 1000}
        error = ""
        try:
            raw_answer = (
                live_raw_answer(case, args.endpoint_url, args.timeout_seconds, args.max_side, args.max_new_tokens)
                if args.endpoint_url
                else str(case.get("offline_raw_answer") or "")
            )
        except Exception as exc:  # noqa: BLE001 - eval should report per-case runtime errors.
            raw_answer = ""
            error = str(exc)[:240]
        boxes = server.parse_locateanything_boxes(raw_answer, int(size["width"]), int(size["height"]))
        boxes = server.dedupe_locateanything_rule_boxes(case["rule"], boxes)
        evaluated = server.evaluate_locateanything_rule(case["rule"], boxes, error, raw_answer)
        loc_ok = localization_ok(case, boxes)
        judgement_correct = evaluated["passed"] == bool(case["expected_accept"])
        results.append(
            {
                "id": case["id"],
                "record_id": case.get("record_id") or "",
                "image_filename": case.get("image_filename") or "",
                "local_image_path": case.get("local_image_path") or "",
                "task_type": evaluated["task_type"],
                "judgement_policy": evaluated["judgement_policy"],
                "expected_accept": bool(case["expected_accept"]),
                "passed": bool(evaluated["passed"]),
                "status": evaluated["status"],
                "box_count": evaluated["box_count"],
                "judgement_correct": judgement_correct,
                "localization_ok": loc_ok,
                "raw_answer_snippet": server.bounded_text(raw_answer, 240),
                "error": error,
            }
        )
    total = len(results)
    judgement_correct = sum(1 for item in results if item["judgement_correct"])
    localization_cases = [item for item in results if item["localization_ok"] is not None]
    localization_correct = sum(1 for item in localization_cases if item["localization_ok"] is True)
    judgement_accuracy = judgement_correct / total if total else 0.0
    localization_accuracy = localization_correct / len(localization_cases) if localization_cases else None
    live_rule_accuracy = (
        sum(1 for item in results if item["passed"]) / total
        if args.endpoint_url and total
        else None
    )
    blockers = []
    if total < args.min_cases:
        blockers.append(f"labeled case count {total} is below required minimum {args.min_cases}")
    if not args.endpoint_url:
        blockers.append("live LocateAnything endpoint was not exercised; offline replay only")
    if live_rule_accuracy is not None and live_rule_accuracy < TARGET_ACCURACY:
        blockers.append(f"live rule accuracy {live_rule_accuracy:.3f} is below target {TARGET_ACCURACY:.2f}")
    if localization_accuracy is not None and localization_accuracy < TARGET_ACCURACY:
        blockers.append(f"localization sanity {localization_accuracy:.3f} is below target {TARGET_ACCURACY:.2f}")
    target_met = not blockers and live_rule_accuracy is not None and live_rule_accuracy >= TARGET_ACCURACY
    return {
        "status": "pass" if target_met else "partial_blocked",
        "mode": "live_endpoint" if args.endpoint_url else "offline_replay",
        "target_accuracy": TARGET_ACCURACY,
        "min_cases": args.min_cases,
        "case_count": total,
        "judgement_accuracy": round(judgement_accuracy, 6),
        "live_rule_accuracy": round(live_rule_accuracy, 6) if live_rule_accuracy is not None else None,
        "localization_accuracy": round(localization_accuracy, 6) if localization_accuracy is not None else None,
        "target_met": target_met,
        "blockers": blockers,
        "known_false_positive_record": KNOWN_RECORD_ID,
        "known_false_positive_image": KNOWN_IMAGE_NAME,
        "generated_at": int(time.time()),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate LocateAnything profiles, prompts, and rule judgement.")
    parser.add_argument("--endpoint-url", default="", help="Optional live LocateAnything /locate endpoint URL.")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--max-side", type=int, default=640)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--min-cases", type=int, default=DEFAULT_MIN_CASES)
    parser.add_argument("--output", default="", help="Optional JSON report path.")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero when the 95% target is not proven.")
    args = parser.parse_args()

    report = run_eval(args)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    if args.strict and not report["target_met"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
